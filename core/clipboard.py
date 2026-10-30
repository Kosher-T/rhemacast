"""
core/clipboard.py

Clipboard bridge with platform-tool fallback.

Platform table (selection is by tool AVAILABILITY, never by OS sniffing,
so exotic setups just work):
  Windows / macOS (healthy) .... QClipboard native (sound bridges).
    No tool in the table below exists on Windows, so no console process
    is ever spawned there (no CREATE_NO_WINDOW games needed).
  Wayland ...................... wl-paste reads; wl-copy writes (async).
  X11 .......................... xclip reads; xsel reads (either suffices).
  macOS (belt & braces) ........ pbpaste reads; pbcopy writes (both
    instant, always present — never hang, so the write leg is inline).

Qt's bridge can be blind on some desktops (observed: Qt 6.11 clients on
COSMIC/Wayland see zero formats for outside copies, in BOTH directions,
on both the wayland and xcb backends — while wl-paste works fine).
Same-process copies still work through QClipboard, so:

- write_text() records a baseline: the system text sampled at write
  time (always a live probe — a snapshot could predate an outside copy
  that landed just before our write), plus our text. One fast system
  read per copy.
- A background snapshot (start_cache(), app boot only) polls the
  system clipboard and refreshes on window activation and clipboard
  change signals. Reads prefer a fresh snapshot over a live probe, so
  paste never blocks on a wedged compositor; only a stale/missing
  snapshot falls back to a bounded synchronous probe. Unanswered probes
  never clobber a good snapshot.
- read_text(): re-reads the system clipboard; if it matches the
  baseline, no outside copy happened since — our Qt text is fresh even
  when Qt could not publish it, so Qt wins. If it differs, an outside
  copy landed after ours — the system wins. With no baseline on record,
  the system wins when non-empty, else Qt.
- write_text() publishes through QClipboard (in-app + healthy systems)
  AND wl-copy on a daemon thread (broken-outbound systems; same content
  → harmless duplicate where the bridge works, and the thread absorbs
  the wedged-handshake freeze so the GUI never blocks). xclip-write is
  deliberately absent (xclip -i never exits → leaked process holding
  the selection hostage).

Helpers never raise into key handling; subprocess calls are timeout-
guarded (reads short — paste is synchronous; writes async) and speak
explicit UTF-8 (replacement on decode, so a weird byte never kills a
paste and never depends on locale). A tool that times out (wedged
compositor handshake) is skipped for a cooldown rather than freezing
every subsequent paste/copy.
"""

import logging
import shutil
import subprocess
import threading
import time

logger = logging.getLogger(__name__)

_READ_TIMEOUT_S = 2
_WRITE_TIMEOUT_S = 5
_TOOL_ENCODING = "utf-8"
# After a tool wedges (timeout, not mere absence/failure), skip it for a
# while: every synchronous probe would otherwise freeze paste/copy for
# the full timeout. Keyed per tool — a Wayland wedge need not implicate
# the X11 socket. Module state, GUI thread only (plus fire-and-forget
# write threads, which only ever add entries).
_WEDGE_COOLDOWN_S = 30
_wedge_until: dict[str, float] = {}


def _wedged(tool: str) -> bool:
    return time.monotonic() < _wedge_until.get(tool, 0.0)


def _qt_clipboard():
    try:
        from PyQt6.QtWidgets import QApplication
        return QApplication.clipboard()
    except Exception:
        return None


def _run_tool(args: list[str], input_text: str | None = None,
              timeout: int = _READ_TIMEOUT_S) -> str | None:
    """Run a clipboard tool, return stdout (None on any failure).

    Offer handshakes (wl-copy) can wedge against some compositors and
    never return — callers must never run writes on the GUI thread
    (see write_text); reads use a short timeout. Console processes are
    never spawned on Windows: no tabled tool exists there (Qt native
    covers it), and every call site is which()-guarded first.
    """
    if not args or shutil.which(args[0]) is None:
        return None
    if _wedged(args[0]):
        logger.debug("Clipboard tool %s skipped (wedged cooldown)", args[0])
        return None
    try:
        proc = subprocess.run(
            args, input=input_text, capture_output=True, text=True,
            encoding=_TOOL_ENCODING, errors="replace", timeout=timeout)
        if proc.returncode != 0:
            return None
        return proc.stdout
    except subprocess.TimeoutExpired:
        # A timeout means the compositor stopped answering THIS tool
        # (observed: wedged offer/selection handshakes). Back off rather
        # than freezing every paste/copy for the full timeout again.
        # (Killing our own wedged child is contained; the cooldown bounds
        # any harm a half-finished handshake leaves behind.)
        _wedge_until[args[0]] = time.monotonic() + _WEDGE_COOLDOWN_S
        logger.warning("Clipboard tool %s wedged — cooling down %ds",
                       args[0], _WEDGE_COOLDOWN_S)
        return None
    except Exception as e:
        logger.debug("Clipboard tool %s failed: %s", args[0], e)
        return None


_READ_TOOLS = (["wl-paste", "--no-newline"],
               ["pbpaste"],
               ["xclip", "-o", "-selection", "clipboard"],
               ["xsel", "--clipboard", "--output"])


def _probe_tool(args: list[str],
                timeout: int = _READ_TIMEOUT_S) -> tuple[bool, str]:
    """Run one read tool: (answered, text). answered is False only when
    the tool could not run at all (missing, wedged, crashed) — as
    opposed to running fine against an empty clipboard (True, "")."""
    if not args or shutil.which(args[0]) is None:
        return (False, "")
    if _wedged(args[0]):
        logger.debug("Clipboard tool %s skipped (wedged cooldown)", args[0])
        return (False, "")
    try:
        proc = subprocess.run(
            args, input=None, capture_output=True, text=True,
            encoding=_TOOL_ENCODING, errors="replace", timeout=timeout)
        if proc.returncode != 0:
            return (False, "")
        return (True, proc.stdout or "")
    except subprocess.TimeoutExpired:
        _wedge_until[args[0]] = time.monotonic() + _WEDGE_COOLDOWN_S
        logger.warning("Clipboard tool %s wedged — cooling down %ds",
                       args[0], _WEDGE_COOLDOWN_S)
        return (False, "")
    except Exception as e:
        logger.debug("Clipboard tool %s failed: %s", args[0], e)
        return (False, "")


def _system_probe() -> tuple[bool, str]:
    """First answering tool wins (its text, possibly empty)."""
    for args in _READ_TOOLS:
        answered, text = _probe_tool(args)
        if answered:
            return (True, text)
    return (False, "")


def _system_read() -> str:
    """System clipboard text via platform tools (Wayland → macOS → X11)."""
    return _system_probe()[1]


# Background snapshot: the system clipboard as last seen by a worker
# thread, plus when. Paste/copy read the snapshot (memory, never the
# wire) while it is fresh, so a wedged compositor cannot freeze the UI;
# only a stale/missing snapshot falls back to a bounded synchronous
# probe. Unanswered probes never clobber a good snapshot.
_CACHE_POLL_S = 2.0
_CACHE_STALE_AFTER_S = 6.0
_snapshot_lock = threading.Lock()
_snapshot_text: str | None = None
_snapshot_at: float = 0.0
_snapshot_inflight = False
_cache_poller = None
_cache_started = False
_cache_poll_s = _CACHE_POLL_S
_cache_stale_after_s = _CACHE_STALE_AFTER_S


def _snapshot_store(text: str):
    global _snapshot_text, _snapshot_at
    with _snapshot_lock:
        _snapshot_text = text
        _snapshot_at = time.monotonic()


def _snapshot_get(max_age_s: float) -> str | None:
    """Snapshot text, or None when absent/older than max_age_s."""
    with _snapshot_lock:
        if _snapshot_text is None:
            return None
        if time.monotonic() - _snapshot_at > max_age_s:
            return None
        return _snapshot_text


def _snapshot_take():
    """One background sample (worker thread): answered probes refresh
    the snapshot; unanswered ones leave the last good value alone."""
    global _snapshot_inflight, _snapshot_text, _snapshot_at
    answered, text = _system_probe()
    with _snapshot_lock:
        _snapshot_inflight = False
        if answered:
            _snapshot_text = text
            _snapshot_at = time.monotonic()


def _refresh_snapshot_async():
    """Queue one background sample; coalesces while one is in flight."""
    global _snapshot_inflight
    with _snapshot_lock:
        if _snapshot_inflight:
            return
        _snapshot_inflight = True

    def _work():
        try:
            _snapshot_take()
        except Exception:
            logger.debug("Clipboard snapshot failed", exc_info=True)
            with _snapshot_lock:
                _snapshot_inflight = False

    thread = threading.Thread(target=_work, daemon=True)
    thread.start()


def start_cache(poll_interval_s: float = _CACHE_POLL_S,
                stale_after_s: float = _CACHE_STALE_AFTER_S) -> bool:
    """Start the background clipboard snapshot (app boot only).

    Polls the system clipboard, refreshes on window activation and on
    clipboard change signals. Idempotent. Returns False without a
    QApplication (tests drive the cache explicitly). Test-friendly
    intervals are parameters, not globals.
    """
    global _cache_poller, _cache_started
    global _cache_poll_s, _cache_stale_after_s
    if _cache_started:
        return True
    try:
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            return False
        _cache_poll_s = poll_interval_s
        _cache_stale_after_s = stale_after_s
        timer = QTimer()
        timer.setInterval(int(poll_interval_s * 1000))
        timer.timeout.connect(_refresh_snapshot_async)
        timer.start()
        _cache_poller = timer
        try:
            app.applicationStateChanged.connect(
                lambda _state: _refresh_snapshot_async())
        except Exception:
            pass
        try:
            cb = app.clipboard()
            cb.dataChanged.connect(_refresh_snapshot_async)
        except Exception:
            pass
        _cache_started = True
        _refresh_snapshot_async()  # warm the cache immediately
        logger.info("Clipboard snapshot cache started (poll %.1fs)",
                    poll_interval_s)
        return True
    except Exception:
        logger.debug("Clipboard cache not started", exc_info=True)
        return False


def stop_cache():
    """Stop the poller (tests). In-flight snapshots may still land."""
    global _cache_poller, _cache_started
    _cache_started = False
    timer, _cache_poller = _cache_poller, None
    if timer is not None:
        try:
            timer.stop()
        except Exception:
            pass


def _current_system() -> str:
    """System text, preferring a fresh snapshot over a live probe."""
    cached = _snapshot_get(_cache_stale_after_s)
    if cached is not None:
        return cached
    return _system_read()


# Baseline of the last in-app write: (system text then, our text).
# Guardianship for blind bridges — module state, GUI thread only.
_baseline: tuple[str, str] | None = None


def read_text() -> str:
    """Best-effort clipboard text, never raises.

    System unchanged since our last write → our Qt text is fresh (it
    may simply be unpublished on a blind bridge) → Qt wins. System
    changed → an outside copy landed after ours → system wins. No
    baseline → system wins when non-empty, else Qt.
    """
    qt_text = ""
    try:
        cb = _qt_clipboard()
        if cb is not None:
            qt_text = cb.text() or ""
    except Exception:
        logger.debug("QClipboard read failed", exc_info=True)
    sys_text = ""
    if _tools_available():
        sys_text = _current_system()
    else:
        return qt_text
    if _baseline is not None and sys_text == _baseline[0]:
        # No outside copy since our write: OUR text is the truth, even
        # when it is empty (the system still holds the pre-write text;
        # returning that would resurrect a stale selection).
        return qt_text
    return sys_text or qt_text


def _tools_available() -> bool:
    return any(shutil.which(t) is not None
               for t in ("wl-paste", "pbpaste", "xclip", "xsel"))


def _publish_system(text: str):
    """Second write leg for broken-outbound bridges (daemon thread).

    wl-copy's offer handshake can wedge and block indefinitely; pbcopy
    is instant and safe inline but shares this path for uniformity.
    Same content as the Qt leg → harmless duplicate where Qt publishing
    already works. The thread absorbs any freeze so the GUI never
    blocks. xclip-write is deliberately absent (xclip -i never exits).
    """
    def _serve():
        if _run_tool(["wl-copy"], input_text=text,
                     timeout=_WRITE_TIMEOUT_S) is not None:
            return
        _run_tool(["pbcopy"], input_text=text, timeout=_WRITE_TIMEOUT_S)

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()


def write_text(text: str) -> bool:
    """Publish text to the clipboard and record the baseline.

    The baseline (system text sampled NOW + our text) lets later reads
    tell "no outside activity, ours is fresh" from "an outside copy
    landed after ours". Never raises, never blocks: the wl-copy leg
    runs on a daemon thread.
    """
    global _baseline
    ok = False
    try:
        cb = _qt_clipboard()
        if cb is not None:
            cb.setText(text or "")
            ok = True
    except Exception:
        logger.debug("QClipboard write failed", exc_info=True)
    try:
        # Baseline is always a live probe, never the snapshot: the
        # snapshot may predate an outside copy that landed just before
        # our write, which would corrupt the comparison. Bounded and
        # cooldown-guarded like any probe.
        _baseline = (_system_read(), text or "")
    except Exception:
        _baseline = ("", text or "")
    # Second leg for broken-outbound bridges (same content → harmless
    # duplicate where Qt publishing already works).
    if text:
        _publish_system(text)
    return ok


def has_html() -> bool:
    """Whether the Qt clipboard currently offers HTML (rich paste)."""
    try:
        cb = _qt_clipboard()
        mime = cb.mimeData() if cb is not None else None
        return bool(mime is not None and mime.hasHtml())
    except Exception:
        return False


def qt_formats() -> list[str]:
    """MIME formats QClipboard currently reports (diagnostics)."""
    try:
        cb = _qt_clipboard()
        mime = cb.mimeData() if cb is not None else None
        if mime is not None:
            return [str(f) for f in mime.formats()]
    except Exception:
        pass
    return []


def system_formats() -> list[str]:
    """MIME types the system clipboard offers (diagnostics)."""
    out = _run_tool(["wl-paste", "--list-types"])
    if out is None:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]

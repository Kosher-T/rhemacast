"""Clipboard bridge: Qt + system-tool fallback (core/clipboard.py).

Needs offscreen Qt. System-leg tests need wl-copy/wl-paste (skipped
without them) and save/restore the real clipboard around themselves.
"""

import os
import shutil

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import ui.widgets.display_view  # noqa: F401

from PyQt6.QtWidgets import QApplication
import pytest

import core.database as db

_OPEN = []


@pytest.fixture(autouse=True)
def _close():
    yield
    while _OPEN:
        w = _OPEN.pop()
        try:
            w.close()
            w.deleteLater()
        except RuntimeError:
            pass
    _qt().processEvents()


_app = None


@pytest.fixture(autouse=True)
def _reset_baseline():
    import core.clipboard as _cb
    old_base, old_text, old_at = \
        _cb._baseline, _cb._snapshot_text, _cb._snapshot_at
    _cb._baseline = None
    _cb._snapshot_text = None
    _cb._snapshot_at = 0.0
    _cb._snapshot_inflight = False
    yield
    _cb.stop_cache()
    _cb._baseline = old_base
    _cb._snapshot_text = old_text
    _cb._snapshot_at = old_at
    _cb._snapshot_inflight = False


def _set_qt(text: str):
    _qt()
    QApplication.clipboard().setText(text)
    _qt().processEvents()


def _qt():
    global _app
    _app = QApplication.instance()
    if _app is None:
        _app = QApplication(["t"])
    return _app


needs_wl = pytest.mark.skipif(
    shutil.which("wl-copy") is None or shutil.which("wl-paste") is None,
    reason="wl-copy/wl-paste not available")


def _seed_works() -> bool:
    """Whether this compositor takes wl-copy offers, probed once per
    session (a wedged handshake blocks for the full timeout — never
    pay it more than once)."""
    if _seed_works.cached is None:
        import subprocess
        try:
            p = subprocess.run(["wl-copy"], input="probe", capture_output=True,
                               text=True, timeout=8)
            _seed_works.cached = p.returncode == 0
        except Exception:
            _seed_works.cached = False
    return _seed_works.cached


_seed_works.cached = None


def _seed_system(text: str) -> bool:
    """Put text on the system clipboard like an outside app would.

    Returns False (caller skips) when the compositor won't take the
    offer — the offer handshake wedges on some setups, which is exactly
    what the async write leg is designed to survive.
    """
    import subprocess
    if not _seed_works():
        return False
    try:
        p = subprocess.run(["wl-copy"], input=text, capture_output=True,
                           text=True, timeout=8)
        return p.returncode == 0
    except Exception:
        return False


@pytest.fixture()
def saved_clipboard():
    """Save/restore the system clipboard around system-leg tests."""
    import subprocess
    before = None
    try:
        p = subprocess.run(["wl-paste", "--no-newline"], capture_output=True,
                           text=True, timeout=5)
        if p.returncode == 0:
            before = p.stdout
    except Exception:
        before = None
    yield
    if not _seed_works.cached:
        return  # offers wedge here; nothing of ours could be out there
    try:
        if before:
            subprocess.run(["wl-copy"], input=before, capture_output=True,
                           text=True, timeout=8)
    except Exception:
        pass


def test_qt_owned_text_preferred(tmp_path):
    """In-app copy reads back through the baseline: system unchanged
    since our write, so our Qt text wins even when Qt could not publish
    it (blind bridge)."""
    _qt()
    from core.clipboard import read_text, write_text
    assert write_text("in-app words")
    _qt().processEvents()
    assert read_text() == "in-app words"


def test_outside_copy_wins_after_inapp_copy(saved_clipboard):
    """System text differing from the write baseline wins (an outside
    copy landed after ours) — needs a working system seed."""
    _qt()
    from core.clipboard import read_text, write_text
    assert write_text("in-app words")
    if not _seed_system("outside wins"):
        pytest.skip("compositor would not take the offer here")
    assert read_text() == "outside wins"


@needs_wl
def test_system_leg_reads_outside_copy(saved_clipboard):
    """An outside copy (system clipboard, Qt blind) is visible via the bridge."""
    _qt()
    from core.clipboard import read_text
    # Fresh Qt clipboard with no ownership: simulate the blind bridge by
    # clearing Qt state, then copying outside the process.
    QApplication.clipboard().clear()
    _qt().processEvents()
    if not _seed_system("outside bridge probe"):
        pytest.skip("compositor would not take the offer here")
    assert read_text() == "outside bridge probe"


@needs_wl
def test_designer_pastes_outside_copy(tmp_path, saved_clipboard):
    """End to end: outside text lands in the editor via Ctrl+V."""
    from PyQt6.QtTest import QTest
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QTextCursor
    _qt()
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    from core.slide_service import create_deck
    from ui.widgets.lite_designer.lite_designer import LiteDesigner
    deck = create_deck("# T\n\n\n*1\nFirst slide words\n")
    w = LiteDesigner(deck_id=deck["id"])
    w.show()
    w._edit.setFocus()
    _qt().processEvents()
    _OPEN.append(w)
    QApplication.clipboard().clear()
    _qt().processEvents()
    if not _seed_system("from outside"):
        pytest.skip("compositor would not take the offer here")
    cur = w._edit.textCursor()
    cur.movePosition(QTextCursor.MoveOperation.End)
    w._edit.setTextCursor(cur)
    QTest.keyClick(w._edit, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    _qt().processEvents()
    assert "from outside" in w._edit.document().toPlainText()


def test_empty_clipboard_reports_nothing():
    from core.clipboard import qt_formats
    assert isinstance(qt_formats(), list)


def test_wedged_compositor_paste_stays_fast(tmp_path, monkeypatch):
    """Simulated fully-wedged compositor: the first paste pays one
    probe timeout, then cooldown makes every later paste instant —
    and the in-app copy still lands via the baseline rule."""
    import subprocess
    import time
    import core.clipboard as cb
    _qt()
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    from core.slide_service import create_deck
    from ui.widgets.lite_designer.lite_designer import LiteDesigner

    def _wedged_run(*a, **k):
        raise subprocess.TimeoutExpired(cmd=a[0], timeout=2)

    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/tool")
    monkeypatch.setattr(subprocess, "run", _wedged_run)
    assert cb.write_text("in-app words") is True
    assert cb.read_text() == "in-app words"

    deck = create_deck("# T\n\n\n*1\nFirst slide words\n")
    w = LiteDesigner(deck_id=deck["id"])
    w.show()
    w._edit.setFocus()
    _qt().processEvents()
    _OPEN.append(w)
    from PyQt6.QtTest import QTest
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QTextCursor
    cur = w._edit.textCursor()
    cur.movePosition(QTextCursor.MoveOperation.End)
    w._edit.setTextCursor(cur)
    t0 = time.monotonic()
    QTest.keyClick(w._edit, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(w._edit, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    dt_ms = (time.monotonic() - t0) * 1000.0
    assert "in-app words" in w._edit.document().toPlainText()
    assert dt_ms < 1500, f"wedged paste froze the UI: {dt_ms:.0f}ms"


# ── hermetic backend selection (monkeypatched — OS-independent) ─────


def test_read_prefers_qt_when_system_unchanged(monkeypatch):
    import core.clipboard as cb
    _set_qt("ours")
    monkeypatch.setattr(cb, "_system_read", lambda: "base")
    cb._baseline = ("base", "ours")
    assert cb.read_text() == "ours"


def test_read_prefers_system_when_changed(monkeypatch):
    import core.clipboard as cb
    _set_qt("ours")
    monkeypatch.setattr(cb, "_system_read", lambda: "new")
    cb._baseline = ("base", "ours")
    assert cb.read_text() == "new"


def test_read_no_baseline_system_first(monkeypatch):
    import core.clipboard as cb
    _set_qt("qt-text")
    monkeypatch.setattr(cb, "_system_read", lambda: "sys-text")
    assert cb.read_text() == "sys-text"
    monkeypatch.setattr(cb, "_system_read", lambda: "")
    assert cb.read_text() == "qt-text"


def test_read_no_tools_pure_qt(monkeypatch):
    import core.clipboard as cb
    _set_qt("qt-only")
    monkeypatch.setattr(cb, "_tools_available", lambda: False)
    monkeypatch.setattr(
        cb, "_system_read",
        lambda: (_ for _ in ()).throw(AssertionError("must not query tools")))
    assert cb.read_text() == "qt-only"


def test_system_read_tries_in_order(monkeypatch):
    import core.clipboard as cb
    calls = []

    def fake_probe(args, timeout=3):
        calls.append(args[0])
        return (True, "X") if args[0] == "xsel" else (False, "")

    monkeypatch.setattr(cb, "_probe_tool", fake_probe)
    assert cb._system_read() == "X"
    assert calls == ["wl-paste", "pbpaste", "xclip", "xsel"]


def test_no_subprocess_without_tools(monkeypatch):
    import subprocess
    import core.clipboard as cb
    monkeypatch.setattr("shutil.which", lambda _name: None)

    def _boom(*a, **k):
        raise AssertionError("must not spawn processes")

    monkeypatch.setattr(subprocess, "run", _boom)
    assert cb._system_read() == ""
    assert cb.system_formats() == []
    _set_qt("qt-text")
    assert cb.read_text() == "qt-text"


def test_write_records_baseline_and_publishes(monkeypatch):
    import core.clipboard as cb
    published = []
    monkeypatch.setattr(cb, "_publish_system",
                        lambda text: published.append(text))
    monkeypatch.setattr(cb, "_system_read", lambda: "sys-before")
    assert cb.write_text("hello") is True
    assert cb._baseline == ("sys-before", "hello")
    assert published == ["hello"]
    # Baseline fresh → our Qt text wins even if unpublished.
    monkeypatch.setattr(cb, "_system_read", lambda: "sys-before")
    assert cb.read_text() == "hello"


def test_run_tool_uses_explicit_utf8(monkeypatch):
    import subprocess
    import core.clipboard as cb
    seen = {}

    class _Proc:
        returncode = 0
        stdout = "out"

    def fake_run(*a, **k):
        seen.update(k)
        return _Proc()

    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/tool")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert cb._run_tool(["tool"]) == "out"
    assert seen.get("encoding") == "utf-8"


def test_wedge_cools_down_tool(monkeypatch):
    """A wedged tool is skipped (not re-probed) until cooldown expiry;
    other tools are unaffected."""
    import subprocess
    import core.clipboard as cb
    calls = []

    def fake_run(*a, **k):
        calls.append(a[0][0])
        raise subprocess.TimeoutExpired(cmd=a[0], timeout=2)

    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/tool")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert cb._run_tool(["wedged-tool"], timeout=2) is None
    assert cb._run_tool(["wedged-tool"], timeout=2) is None
    assert calls == ["wedged-tool"]  # second probe skipped: no new call
    assert cb._run_tool(["other-tool"], timeout=2) is None
    assert calls == ["wedged-tool", "other-tool"]


def test_wedge_cooldown_expires(monkeypatch):
    import subprocess
    import time
    import core.clipboard as cb
    calls = []

    def fake_run(*a, **k):
        calls.append(a[0][0])
        raise subprocess.TimeoutExpired(cmd=a[0], timeout=2)

    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/tool")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(time, "monotonic", lambda: 1000.0)
    assert cb._run_tool(["cooldown-tool"], timeout=2) is None
    assert calls == ["cooldown-tool"]
    monkeypatch.setattr(time, "monotonic",
                        lambda: 1000.0 + cb._WEDGE_COOLDOWN_S + 1.0)
    assert cb._run_tool(["cooldown-tool"], timeout=2) is None
    assert calls == ["cooldown-tool", "cooldown-tool"]  # probed again


# ── background snapshot cache ────────────────────────────────────────

def _wait_snapshot(cb, timeout_s: float = 5.0) -> bool:
    import time
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        with cb._snapshot_lock:
            if cb._snapshot_text is not None:
                return True
        time.sleep(0.02)
    return False


def test_snapshot_refresh_stores_answered(monkeypatch):
    import core.clipboard as cb
    monkeypatch.setattr(cb, "_system_probe", lambda: (True, "snap"))
    cb._refresh_snapshot_async()
    assert _wait_snapshot(cb)
    assert cb._snapshot_get(60.0) == "snap"


def test_snapshot_unanswered_keeps_good(monkeypatch):
    import core.clipboard as cb
    monkeypatch.setattr(cb, "_system_probe", lambda: (True, "good"))
    cb._refresh_snapshot_async()
    assert _wait_snapshot(cb)
    monkeypatch.setattr(cb, "_system_probe", lambda: (False, ""))
    cb._refresh_snapshot_async()
    import time
    time.sleep(0.2)
    assert cb._snapshot_get(60.0) == "good"


def test_snapshot_expiry(monkeypatch):
    import time
    import core.clipboard as cb
    cb._snapshot_store("old")
    monkeypatch.setattr(time, "monotonic",
                        lambda: cb._snapshot_at + cb._cache_stale_after_s + 1.0)
    assert cb._snapshot_get(cb._cache_stale_after_s) is None


def test_read_prefers_fresh_cache_without_probing(monkeypatch):
    """The seamlessness guarantee: with a fresh snapshot, paste performs
    zero subprocess I/O (would freeze on a wedged compositor)."""
    import subprocess
    import core.clipboard as cb
    _set_qt("ours")

    def _boom(*a, **k):
        raise AssertionError("must not touch subprocesses")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(cb, "_system_probe", _boom)
    cb._snapshot_store("base")
    cb._baseline = ("base", "ours")
    assert cb.read_text() == "ours"
    cb._snapshot_store("new")
    assert cb.read_text() == "new"


def test_stale_cache_falls_back_to_probe(monkeypatch):
    import core.clipboard as cb
    _set_qt("ours")
    cb._snapshot_store("stale")
    old_at = cb._snapshot_at
    monkeypatch.setattr(cb, "_snapshot_at",
                        old_at - cb._cache_stale_after_s - 1.0)
    monkeypatch.setattr(cb, "_system_probe", lambda: (True, "probed"))
    cb._baseline = ("stale", "ours")
    assert cb.read_text() == "probed"


def test_start_stop_cache_idempotent():
    import core.clipboard as cb
    _qt()
    assert cb.start_cache(poll_interval_s=60.0, stale_after_s=60.0) is True
    first = cb._cache_poller
    assert cb.start_cache() is True  # second start: no duplicate poller
    assert cb._cache_poller is first
    cb.stop_cache()
    assert cb._cache_started is False

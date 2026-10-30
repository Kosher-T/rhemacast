"""
core/network_watcher.py

Live LAN-address watcher for the operator UI.

The Outputs page prints a display URL containing the machine's LAN address.
Reading that address once at widget construction is wrong for a laptop that
joins a different Wi-Fi network mid-service: the operator would have to
relaunch the whole app to learn the new address.

There is no portable OS "address changed" signal (Netlink on Linux,
NotifyIpInterfaceChange on Windows, ... all platform-specific), and the
address itself is a single cheap kernel route lookup. So this watches by
polling it on a daemon thread and emits ONLY when the value actually
changes — a stable network produces no UI work. Where Qt has a network
backend, ``QNetworkInformation.reachabilityChanged`` wakes the poller
immediately instead of waiting for the next tick.

The probe opens a UDP socket and calls connect() on it: no packets are
sent, the kernel just reports which source address it would use. That is
exactly the address a phone on the same network must reach.
"""

from __future__ import annotations

import logging
import socket
import threading

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

# Route lookup target, not a real destination (no traffic is sent).
# 10.255.255.255 is the limited broadcast address for the private 10/8
# range, so the lookup succeeds on any interface with an IPv4 route.
_PROBE_TARGET = ("10.255.255.255", 1)
_PROBE_TIMEOUT_S = 0.5


def detect_lan_ip() -> str | None:
    """The machine's preferred LAN IPv4 address, or None when offline.

    None means "no usable non-loopback address" — the network display URL
    cannot work, and the Outputs page shows the network row as offline.
    Never raises: a probe failure is reported as None.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except OSError:
        logger.debug("Could not open LAN-address probe socket", exc_info=True)
        return None
    try:
        sock.settimeout(_PROBE_TIMEOUT_S)
        sock.connect(_PROBE_TARGET)
        address = sock.getsockname()[0]
    except OSError:
        return None
    finally:
        try:
            sock.close()
        except OSError:
            pass
    if not address or address.startswith("127."):
        return None
    return address


class NetworkAddressWatcher(QObject):
    """Polls ``detect_lan_ip`` off the GUI thread; emits on change only.

    ``address_changed`` carries the new address, or "" when the machine has
    no LAN address (Wi-Fi dropped, cable unplugged). Receivers may live in
    the GUI thread; Qt queues the cross-thread emission for them.
    """

    address_changed = pyqtSignal(str)

    def __init__(self, probe=None, interval_ms: int | None = None,
                 parent=None):
        super().__init__(parent)
        from core.constants import NETWORK_WATCH_INTERVAL_MS

        self._probe = probe or detect_lan_ip
        interval = NETWORK_WATCH_INTERVAL_MS if interval_ms is None \
            else interval_ms
        self._interval_s = max(0.02, float(interval) / 1000.0)
        self._lock = threading.Lock()
        self._address: str = ""
        self._known = False
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._reachability_hooked = False

    # ── State ────────────────────────────────────────────────────────────
    def current(self) -> str:
        """The last detected address ("" when offline/not probed yet)."""
        with self._lock:
            return self._address

    def poll_once(self) -> str:
        """Run one probe synchronously and emit if the address changed.

        Exposed for tests and for a manual refresh; the background thread
        calls this every interval.
        """
        try:
            address = self._probe() or ""
        except Exception:
            logger.debug("LAN-address probe failed", exc_info=True)
            address = ""

        with self._lock:
            changed = (not self._known) or address != self._address
            self._address = address
            self._known = True

        if changed:
            self.address_changed.emit(address)
        return address

    # ── Lifecycle ────────────────────────────────────────────────────────
    def start(self):
        """Start polling (idempotent). Safe to call before any listener."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._wake_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="LAN-Address-Watcher", daemon=True)
        self._thread.start()
        self._install_reachability_hook()
        logger.info("LAN address watcher started (every %.1fs)",
                    self._interval_s)

    def stop(self, join_timeout_s: float = 1.0):
        """Stop polling. Idempotent; a wedged probe is bounded by its timeout."""
        self._stop_event.set()
        self._wake_event.set()
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            thread.join(join_timeout_s)

    def trigger(self):
        """Ask the poller to re-check immediately (OS reachability event)."""
        self._wake_event.set()

    def _run(self):
        while not self._stop_event.is_set():
            self.poll_once()
            # Wakes early for stop()/trigger(); otherwise waits one interval.
            self._wake_event.wait(self._interval_s)
            self._wake_event.clear()

    # ── Optional OS-level hint ───────────────────────────────────────────
    def _install_reachability_hook(self):
        """Use Qt's network backend (when present) to wake the poller early."""
        if self._reachability_hooked:
            return
        try:
            from PyQt6.QtNetwork import QNetworkInformation
            if not QNetworkInformation.loadDefaultBackend():
                logger.debug("No QNetworkInformation backend; polling only")
                return
            info = QNetworkInformation.instance()
            if info is None:
                return
            info.reachabilityChanged.connect(self._on_reachability_changed)
            self._reachability_hooked = True
        except Exception:
            logger.debug("QNetworkInformation hook unavailable", exc_info=True)

    def _on_reachability_changed(self, _reachability):
        self.trigger()


_watcher: NetworkAddressWatcher | None = None


def network_watcher() -> NetworkAddressWatcher:
    """Process-wide watcher, started on first use.

    One thread and one probe per interval no matter how many output columns
    (or tabs) ask for it.
    """
    global _watcher
    if _watcher is None:
        _watcher = NetworkAddressWatcher()
        # Seed before starting: the first Outputs render asks current()
        # immediately, and a "Not connected" flash on a healthy network is
        # worse than one route lookup here (the probe sends no traffic).
        _watcher.poll_once()
        _watcher.start()
    return _watcher


def stop_network_watcher():
    """Stop and drop the singleton (app shutdown / tests)."""
    global _watcher
    if _watcher is not None:
        _watcher.stop()
        _watcher = None

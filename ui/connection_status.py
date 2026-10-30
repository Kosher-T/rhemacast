"""One source of truth for the browser-display connection.

The bottom-left status badge and the Live viewport border both subscribe to
this monitor, so a state change can never paint them differently. The state
comes from the WebSocket server's client count:

    CONNECTED     at least one browser display client is attached
    DISCONNECTED  clients had attached, but none remain
    CAUTION       the display server isn't accepting clients, so we can't tell
    IDLE          the server is ready, but no client has ever attached

IDLE is deliberately neutral: an operator who hasn't opened the display yet
is not making a mistake. A lost link is the only warning that persists.

The state-to-colour mapping lives in STATE_COLORS only. The border QSS and the
badge dot both read it.
"""

from dataclasses import dataclass
from enum import Enum

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from core.constants import WS_STATUS_POLL_MS
from ui.tokens import ACCENT, DISCONNECTED, TEXT_MUTED, WARNING


class ConnectionState(Enum):
    IDLE = "idle"
    CONNECTED = "connected"
    CAUTION = "caution"
    DISCONNECTED = "disconnected"


# The only place a state picks a colour. ACCENT is the healthy/connected
# role; WARNING is the "can't tell" caution; DISCONNECTED is the muted orange
# that reads as a status rather than an alarm. IDLE is neutral, not a warning.
STATE_COLORS = {
    ConnectionState.IDLE: TEXT_MUTED,
    ConnectionState.CONNECTED: ACCENT,
    ConnectionState.CAUTION: WARNING,
    ConnectionState.DISCONNECTED: DISCONNECTED,
}

STATE_WORDS = {
    ConnectionState.IDLE: "Idle",
    ConnectionState.CONNECTED: "Connected",
    ConnectionState.CAUTION: "Unavailable",
    ConnectionState.DISCONNECTED: "Disconnected",
}


@dataclass(frozen=True)
class ConnectionSnapshot:
    """One immutable reading, shared by every subscriber."""

    state: ConnectionState
    clients: int = 0

    @property
    def color(self) -> str:
        return STATE_COLORS[self.state]

    @property
    def label(self) -> str:
        if self.state is ConnectionState.CONNECTED:
            return f"Connected ({self.clients})"
        return STATE_WORDS[self.state]


def derive_state(clients: int, seen_client: bool, server_ready: bool) -> ConnectionState:
    """Map the server facts to the four states the UI can honestly show."""
    if not server_ready:
        return ConnectionState.CAUTION
    if clients > 0:
        return ConnectionState.CONNECTED
    return ConnectionState.DISCONNECTED if seen_client else ConnectionState.IDLE


def live_viewport_qss(state: ConnectionState) -> str:
    """The Live viewport border for one state (always visible, always 1px)."""
    return f"""
        QFrame#LiveOutputViewport {{
            background: black;
            border: 1px solid {STATE_COLORS[state]};
            border-radius: 8px;
        }}
    """


def _client_count() -> int:
    from core.websocket_server import get_connected_client_count
    return get_connected_client_count()


def _seen_client() -> bool:
    from core.websocket_server import has_seen_client
    return has_seen_client()


def _server_ready() -> bool:
    from core.websocket_server import is_server_ready
    return is_server_ready()


class ConnectionMonitor(QObject):
    """Polls the display server and emits one snapshot per real change."""

    changed = pyqtSignal(object)  # ConnectionSnapshot

    def __init__(
        self,
        parent=None,
        *,
        poll_ms: int = WS_STATUS_POLL_MS,
        count_provider=None,
        seen_provider=None,
        ready_provider=None,
        autostart: bool = True,
    ):
        super().__init__(parent)
        self._count_provider = count_provider or _client_count
        self._seen_provider = seen_provider or _seen_client
        self._ready_provider = ready_provider or _server_ready
        self._snapshot = ConnectionSnapshot(ConnectionState.IDLE, 0)

        self._timer = QTimer(self)
        self._timer.setInterval(poll_ms)
        self._timer.timeout.connect(self.refresh)
        if autostart:
            self._timer.start()

    @property
    def snapshot(self) -> ConnectionSnapshot:
        return self._snapshot

    def refresh(self) -> ConnectionSnapshot:
        """Read the server once and publish a snapshot if anything changed."""
        clients = max(0, int(self._count_provider() or 0))
        snapshot = ConnectionSnapshot(
            derive_state(
                clients=clients,
                seen_client=bool(self._seen_provider()),
                server_ready=bool(self._ready_provider()),
            ),
            clients,
        )
        if snapshot != self._snapshot:
            self._snapshot = snapshot
            self.changed.emit(snapshot)
        return snapshot


_monitor = None


def connection_monitor() -> ConnectionMonitor:
    """The process-wide monitor shared by the badge and every Live panel."""
    global _monitor
    if _monitor is None:
        _monitor = ConnectionMonitor()
    return _monitor

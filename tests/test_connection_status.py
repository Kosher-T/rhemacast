"""Display-link status: one monitor feeds the badge and the Live border.

The badge used to poll the WebSocket client count on its own and call it
"OBS"; the Live border was a fixed red. These tests pin the replacement:
the badge is named for the browser clients it actually counts, the border
wears the shared state colour, and a client that connects and drops between
polls still counts as "seen" (so a lost link is not mistaken for idle).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import asyncio
from types import SimpleNamespace

import pytest

from PyQt6.QtWidgets import QApplication

import core.websocket_server as ws
from core import constants
from ui import tokens
from ui.connection_status import (
    STATE_COLORS,
    ConnectionMonitor,
    ConnectionSnapshot,
    ConnectionState,
    derive_state,
    live_viewport_qss,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(["test-connection-status"])


@pytest.fixture()
def facts():
    """Mutable server facts the monitor reads through its providers."""
    return {"clients": 0, "seen": False, "ready": True}


def _monitor(facts):
    return ConnectionMonitor(
        poll_ms=60_000,
        autostart=False,
        count_provider=lambda: facts["clients"],
        seen_provider=lambda: facts["seen"],
        ready_provider=lambda: facts["ready"],
    )


@pytest.mark.parametrize(
    "clients,seen,ready,expected",
    [
        (0, False, True, ConnectionState.IDLE),
        (1, False, True, ConnectionState.CONNECTED),
        (3, True, True, ConnectionState.CONNECTED),
        (0, True, True, ConnectionState.DISCONNECTED),
        (0, False, False, ConnectionState.CAUTION),
        (0, True, False, ConnectionState.CAUTION),
    ],
)
def test_state_derivation(clients, seen, ready, expected):
    assert derive_state(clients, seen, ready) is expected


def test_snapshot_labels():
    assert ConnectionSnapshot(ConnectionState.IDLE, 0).label == "Idle"
    assert ConnectionSnapshot(ConnectionState.CONNECTED, 2).label == "Connected (2)"
    assert ConnectionSnapshot(ConnectionState.DISCONNECTED, 0).label == "Disconnected"
    assert ConnectionSnapshot(ConnectionState.CAUTION, 0).label == "Unavailable"


def test_colour_mapping_is_the_single_status_role_map():
    assert STATE_COLORS == {
        ConnectionState.IDLE: tokens.TEXT_MUTED,
        ConnectionState.CONNECTED: tokens.ACCENT,
        ConnectionState.CAUTION: tokens.WARNING,
        ConnectionState.DISCONNECTED: tokens.DISCONNECTED,
    }


def test_live_border_is_always_visible_and_token_driven():
    for state, colour in STATE_COLORS.items():
        qss = live_viewport_qss(state)
        assert "QFrame#LiveOutputViewport" in qss
        assert f"border: 1px solid {colour}" in qss
    # The old fixed red border is gone; red now only means "on air".
    assert "rgba(239, 68, 68, 0.4)" not in live_viewport_qss(
        ConnectionState.CONNECTED)


def test_monitor_emits_only_when_the_snapshot_changes(qapp, facts):
    monitor = _monitor(facts)
    seen = []
    monitor.changed.connect(seen.append)

    assert monitor.refresh() == ConnectionSnapshot(ConnectionState.IDLE, 0)
    assert seen == [], "the initial idle snapshot is already current"

    facts.update(clients=1, seen=True)
    assert monitor.refresh() == ConnectionSnapshot(ConnectionState.CONNECTED, 1)
    assert len(seen) == 1

    monitor.refresh()
    assert len(seen) == 1, "same snapshot: no redundant repaint"

    facts["clients"] = 2
    monitor.refresh()
    assert seen[-1].label == "Connected (2)", "the count still updates"

    facts["clients"] = 0
    assert monitor.refresh() == ConnectionSnapshot(
        ConnectionState.DISCONNECTED, 0)
    assert seen[-1].state is ConnectionState.DISCONNECTED


def test_badge_names_the_browser_and_follows_the_monitor(qapp, facts):
    from ui.widgets.status_bar import StatusBar

    monitor = _monitor(facts)
    bar = StatusBar(monitor=monitor)
    try:
        assert "Browser: Idle" in bar.browser_label.text()
        assert tokens.TEXT_MUTED in bar.browser_label.text()
        assert "OBS:" not in bar.browser_label.text()

        facts.update(clients=1, seen=True)
        monitor.refresh()
        assert "Browser: Connected (1)" in bar.browser_label.text()
        assert tokens.ACCENT in bar.browser_label.text()

        facts["clients"] = 0
        monitor.refresh()
        assert "Browser: Disconnected" in bar.browser_label.text()
        assert tokens.DISCONNECTED in bar.browser_label.text()

        facts["ready"] = False
        monitor.refresh()
        assert "Browser: Unavailable" in bar.browser_label.text()
        assert tokens.WARNING in bar.browser_label.text()
    finally:
        bar.deleteLater()


def test_badge_text_and_border_qss_read_one_snapshot(qapp, facts):
    """Both surfaces subscribe to the same object; neither polls on its own."""
    monitor = _monitor(facts)
    labels, borders = [], []
    monitor.changed.connect(lambda snapshot: labels.append(
        f"Browser: {snapshot.label}"))
    monitor.changed.connect(lambda snapshot: borders.append(
        live_viewport_qss(snapshot.state)))

    facts.update(clients=1, seen=True)
    monitor.refresh()
    assert labels[-1] == "Browser: Connected (1)"
    assert tokens.ACCENT in borders[-1]

    facts["clients"] = 0
    monitor.refresh()
    assert labels[-1] == "Browser: Disconnected"
    assert tokens.DISCONNECTED in borders[-1]

    facts["ready"] = False
    monitor.refresh()
    assert labels[-1] == "Browser: Unavailable"
    assert tokens.WARNING in borders[-1]


def test_keepalive_is_short_enough_to_spot_a_pulled_cable():
    options = ws._ws_server_options()
    assert options["ping_interval"] == constants.WS_PING_INTERVAL_S == 2.0
    assert options["ping_timeout"] == constants.WS_PING_TIMEOUT_S == 2.0
    # Without this cap the handler waits websockets' 10 s default before
    # the dead client leaves connected_clients (~14 s total).
    assert options["close_timeout"] == constants.WS_CLOSE_TIMEOUT_S == 1.0
    assert options["max_size"] == 1024


def test_connection_seen_survives_a_drop_between_polls(monkeypatch):
    monkeypatch.setattr(ws, "_clients_seen", 0)
    monkeypatch.setattr(
        ws, "connected_clients", {oid: set() for oid in ws.ALL_OUTPUTS})

    class OneShotClient:
        request = SimpleNamespace(path="/?output=1")

        async def send(self, message):
            pass

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    asyncio.run(ws.ws_handler(OneShotClient()))

    assert ws.has_seen_client() is True
    assert ws.get_connected_client_count() == 0


def test_server_ready_flag_is_exposed(monkeypatch):
    monkeypatch.setattr(ws, "_server_ready", False)
    assert ws.is_server_ready() is False
    monkeypatch.setattr(ws, "_server_ready", True)
    assert ws.is_server_ready() is True

"""Display links: live LAN address, hover preview, and copy card.

The Outputs page used to print a network URL captured once, at widget
construction, with a text-only tooltip. These tests pin the replacement:
the address watcher emits on change (and only on change), hovering an
output name previews the addresses beside the cursor, clicking it pins a
card whose buttons copy the exact URL shown, and an output column follows
the watcher without being rebuilt.
"""

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(["test-output-links"])


def _spin(app, ms: int):
    deadline = time.monotonic() + ms / 1000.0
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)


def _wait_for(app, predicate, timeout_s: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return bool(predicate())


# ─── Address detection / URL construction ───────────────────────────────────

def test_urls_keep_the_existing_format_and_mark_offline():
    from ui.panels.themes_panel import output_display_urls

    local, network = output_display_urls("2", "192.168.1.42")
    assert local == "http://127.0.0.1:8766/display.html?output=2"
    assert network == "http://192.168.1.42:8766/display.html?output=2"

    local, network = output_display_urls("2", None)
    assert local == "http://127.0.0.1:8766/display.html?output=2"
    assert network is None, "offline must not print a loopback network URL"


def test_legacy_helper_still_falls_back_to_loopback(monkeypatch):
    import core.network_watcher as nw
    from ui.panels import themes_panel

    monkeypatch.setattr(nw, "detect_lan_ip", lambda: None)
    assert themes_panel._get_lan_ip() == "127.0.0.1"
    monkeypatch.setattr(nw, "detect_lan_ip", lambda: "10.0.0.7")
    assert themes_panel._get_lan_ip() == "10.0.0.7"


def test_detect_lan_ip_never_returns_loopback():
    from core.network_watcher import detect_lan_ip

    address = detect_lan_ip()
    assert address is None or not address.startswith("127.")


# ─── Watcher ─────────────────────────────────────────────────────────────────

def test_watcher_emits_on_first_probe_and_then_only_on_change(qapp):
    import core.network_watcher as nw

    values = iter(["192.168.1.5", "192.168.1.5", "", "10.0.0.9"])
    watcher = nw.NetworkAddressWatcher(probe=lambda: next(values),
                                       interval_ms=10_000)
    seen = []
    watcher.address_changed.connect(seen.append)

    assert watcher.poll_once() == "192.168.1.5"
    assert watcher.poll_once() == "192.168.1.5"
    assert watcher.poll_once() == ""
    assert watcher.poll_once() == "10.0.0.9"

    assert seen == ["192.168.1.5", "", "10.0.0.9"]
    assert watcher.current() == "10.0.0.9"


def test_watcher_treats_probe_errors_as_offline(qapp):
    import core.network_watcher as nw

    def boom():
        raise OSError("no route")

    watcher = nw.NetworkAddressWatcher(probe=boom, interval_ms=10_000)
    seen = []
    watcher.address_changed.connect(seen.append)

    assert watcher.poll_once() == ""
    assert watcher.current() == ""
    assert seen == [""], "an error is reported once, as offline"


def test_watcher_thread_follows_a_mid_service_network_change(qapp):
    """The whole point: an address change lands without a relaunch."""
    import core.network_watcher as nw

    state = {"ip": "192.168.1.10"}
    watcher = nw.NetworkAddressWatcher(probe=lambda: state["ip"],
                                       interval_ms=25)
    seen = []
    watcher.address_changed.connect(seen.append)
    watcher.start()
    thread = watcher._thread
    try:
        deadline = time.monotonic() + 2.0
        while watcher.current() != "192.168.1.10" and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.005)
        assert watcher.current() == "192.168.1.10"

        state["ip"] = "10.42.0.3"
        deadline = time.monotonic() + 2.0
        while watcher.current() != "10.42.0.3" and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.005)
        assert watcher.current() == "10.42.0.3", "change was not picked up"
        _spin(qapp, 50)
        assert "10.42.0.3" in seen
    finally:
        watcher.stop()
    assert thread is not None and not thread.is_alive()
    assert watcher._thread is None


def test_singleton_is_shared_and_stoppable(qapp, monkeypatch):
    import core.network_watcher as nw

    monkeypatch.setattr(nw, "_watcher", None)
    first = nw.network_watcher()
    second = nw.network_watcher()
    assert first is second, "one watcher per process, not one per output"
    assert first.current() == nw.detect_lan_ip() or first.current() == ""
    nw.stop_network_watcher()
    assert nw._watcher is None


# ─── Hover card ──────────────────────────────────────────────────────────────

def _popup(qapp):
    from ui.widgets.output_links import OutputLinksPopup
    popup = OutputLinksPopup()
    popup.set_links("http://127.0.0.1:8766/display.html?output=1",
                    "http://192.168.1.42:8766/display.html?output=1",
                    title="Output 1")
    return popup


def test_popup_shows_both_urls_and_updates_in_place(qapp):
    popup = _popup(qapp)
    assert popup.local_row.url.endswith("output=1")
    assert "192.168.1.42" in popup.network_row.url

    popup.set_links("http://127.0.0.1:8766/display.html?output=1",
                    "http://10.20.30.40:8766/display.html?output=1",
                    title="Output 1")
    assert "10.20.30.40" in popup.network_row.value_label.text()
    assert popup.local_row is not None, "rows update in place, never rebuild"
    popup.deleteLater()


def test_copy_button_writes_the_exact_url(qapp, monkeypatch):
    import core.clipboard as clipboard

    written = []
    monkeypatch.setattr(clipboard, "write_text",
                        lambda text: written.append(text) or True)

    popup = _popup(qapp)
    popup.local_row.copy_button.click()
    assert written == ["http://127.0.0.1:8766/display.html?output=1"]
    assert popup.local_row.copy_button.toolTip() == "Copied"
    assert popup.local_row.copy_button.text() == "\u2713"

    popup.network_row.copy_button.click()
    assert written[-1] == "http://192.168.1.42:8766/display.html?output=1"

    popup.local_row._restore_copy_icon()
    assert popup.local_row.copy_button.text() == ""
    popup.deleteLater()


def test_offline_network_row_disables_copy(qapp, monkeypatch):
    import core.clipboard as clipboard
    from ui.widgets.output_links import OutputLinksPopup

    written = []
    monkeypatch.setattr(clipboard, "write_text",
                        lambda text: written.append(text) or True)

    popup = OutputLinksPopup()
    popup.set_links("http://127.0.0.1:8766/display.html?output=1", None,
                    title="Output 1")
    assert popup.network_row.value_label.text() == "Not connected"
    assert not popup.network_row.copy_button.isEnabled()
    popup.network_row.copy_button.click()
    assert written == [], "a disabled button must not copy an empty address"

    assert popup.local_row.copy_button.isEnabled()
    popup.deleteLater()


def test_popup_flags_never_take_focus(qapp):
    popup = _popup(qapp)
    flags = popup.windowFlags()
    assert bool(flags & Qt.WindowType.Tool)
    assert bool(flags & Qt.WindowType.WindowDoesNotAcceptFocus)
    assert popup.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    popup.deleteLater()


def test_card_centres_on_the_anchor_screen(qapp):
    from PyQt6.QtWidgets import QWidget

    anchor = QWidget()
    anchor.setGeometry(0, 0, 80, 20)
    anchor.show()
    popup = _popup(qapp)
    popup.show_persistent(anchor)
    _spin(qapp, 20)

    available = QApplication.primaryScreen().availableGeometry()
    centre = popup.frameGeometry().center()
    assert abs(centre.x() - available.center().x()) <= 1
    assert abs(centre.y() - available.center().y()) <= 1

    popup.hide()
    anchor.hide()
    popup.deleteLater()
    anchor.deleteLater()


def test_popup_emits_closed_when_dismissed(qapp):
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtWidgets import QWidget

    anchor = QWidget()
    anchor.setGeometry(0, 0, 80, 20)
    anchor.show()
    popup = _popup(qapp)
    dismissed = []
    popup.closed.connect(lambda: dismissed.append(True))
    popup.show_persistent(anchor)
    _spin(qapp, 20)
    assert popup.isVisible()

    QApplication.sendEvent(anchor, QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Escape,
        Qt.KeyboardModifier.NoModifier))
    assert not popup.isVisible()
    assert dismissed == [True]

    anchor.hide()
    popup.deleteLater()
    anchor.deleteLater()


# ─── Hover preview ───────────────────────────────────────────────────────────

def _preview(qapp, parent=None):
    from ui.widgets.output_links import OutputLinksPreview
    preview = OutputLinksPreview(parent)
    preview.set_links("http://127.0.0.1:8766/display.html?output=1",
                      "http://192.168.1.42:8766/display.html?output=1")
    return preview


def test_preview_is_an_in_window_child_not_a_tool_window(qapp):
    from PyQt6.QtWidgets import QPushButton, QWidget

    host = QWidget()
    host.resize(700, 500)
    host.show()
    _spin(qapp, 20)
    preview = _preview(qapp, host)

    assert preview.parentWidget() is host
    assert not preview.isWindow(), \
        "the hover card must not become another OS window"
    assert preview.window() is host.window()
    assert "127.0.0.1" in preview.local_value.text()
    assert "192.168.1.42" in preview.network_value.text()
    assert not preview.findChildren(QPushButton), \
        "the hover card is read-only; copy buttons belong to the click card"
    assert preview.testAttribute(
        Qt.WidgetAttribute.WA_TransparentForMouseEvents), \
        "the preview must never sit between the pointer and the button"

    host.hide()
    preview.deleteLater()
    host.deleteLater()


def test_preview_stays_hidden_until_hovered(qapp):
    """Children are shown with their ancestors unless explicitly hidden."""
    from PyQt6.QtWidgets import QWidget

    host = QWidget()
    host.resize(700, 500)
    preview = _preview(qapp, host)
    assert not preview.isVisible()

    host.show()
    _spin(qapp, 20)
    assert not preview.isVisible(), \
        "a child card must not appear just because the panel was shown"

    host.hide()
    preview.deleteLater()
    host.deleteLater()


def test_preview_waits_for_the_hover_delay(qapp):
    from PyQt6.QtWidgets import QWidget

    host = QWidget()
    host.resize(700, 500)
    host.show()
    anchor = QWidget(host)
    anchor.setGeometry(100, 100, 80, 20)
    anchor.show()
    preview = _preview(qapp, host)
    preview.schedule_show(anchor, delay_ms=20)
    assert not preview.isVisible(), "show is deferred, not immediate"
    _spin(qapp, 60)
    assert preview.isVisible()
    preview.hide()
    host.hide()
    preview.deleteLater()
    host.deleteLater()


def test_preview_sits_beside_the_point_inside_its_parent(qapp):
    from PyQt6.QtWidgets import QWidget

    host = QWidget()
    host.resize(700, 500)
    host.show()
    _spin(qapp, 20)
    preview = _preview(qapp, host)
    local = QPoint(140, 120)
    preview.show_at(host.mapToGlobal(local))
    assert preview.isVisible()

    geometry = preview.frameGeometry()
    assert host.rect().contains(geometry), \
        "the card must stay inside the app window"
    assert not geometry.contains(local), "the cursor must stay uncovered"

    preview.hide()
    host.hide()
    preview.deleteLater()
    host.deleteLater()


def test_preview_flips_to_stay_inside_a_small_parent(qapp):
    from PyQt6.QtWidgets import QWidget

    host = QWidget()
    host.resize(700, 500)
    host.show()
    _spin(qapp, 20)
    preview = _preview(qapp, host)
    preview.show_at(host.mapToGlobal(QPoint(680, 480)))
    assert preview.isVisible()

    geometry = preview.frameGeometry()
    assert host.rect().contains(geometry), \
        "a card near the edge must flip, not spill out of the window"

    preview.hide()
    host.hide()
    preview.deleteLater()
    host.deleteLater()


def test_preview_updates_in_place_while_visible(qapp):
    from PyQt6.QtWidgets import QWidget

    host = QWidget()
    host.resize(700, 500)
    host.show()
    _spin(qapp, 20)
    preview = _preview(qapp, host)
    preview.show_at(host.mapToGlobal(QPoint(140, 120)))
    shown_at = preview.pos()
    preview.set_links("http://127.0.0.1:8766/display.html?output=2", None)
    assert "output=2" in preview.local_value.text()
    assert preview.network_value.text() == "Not connected"
    assert preview.pos() == shown_at, \
        "a live update must not re-anchor the card to the pointer"
    preview.hide()
    host.hide()
    preview.deleteLater()
    host.deleteLater()


# ─── Output column integration ──────────────────────────────────────────────

@pytest.fixture
def fake_watcher(monkeypatch):
    import core.network_watcher as nw

    watcher = nw.NetworkAddressWatcher(probe=lambda: "192.168.1.50",
                                       interval_ms=10_000)
    watcher.poll_once()
    monkeypatch.setattr(nw, "_watcher", watcher)
    return watcher


def test_output_column_starts_with_live_links(qapp, fake_watcher):
    from ui.panels.themes_panel import OutputColumn

    column = OutputColumn("1")
    assert column._link_button.toolTip() == ""
    assert column._link_button.text() == "OUTPUT 1"
    assert not column._link_preview.isWindow(), \
        "the hover card lives inside the app window"
    assert column._link_preview.parentWidget() is column
    assert column._network_url == \
        "http://192.168.1.50:8766/display.html?output=1"
    assert column._link_popup.network_row.url == column._network_url
    assert column._link_preview.network_value.text() == column._network_url
    column.deleteLater()


def test_output_column_follows_a_network_change(qapp, fake_watcher):
    from ui.panels.themes_panel import OutputColumn

    column = OutputColumn("1")
    # The hover card may already be on screen when the machine joins a
    # network; it has to re-read the address, not freeze the one it showed.
    column._link_preview.show_at(QPoint(120, 120))
    fake_watcher._probe = lambda: "10.9.8.7"
    fake_watcher.poll_once()          # same GUI thread -> immediate delivery

    assert column._network_url == \
        "http://10.9.8.7:8766/display.html?output=1"
    assert "10.9.8.7" in column._link_popup.network_row.value_label.text()
    assert "10.9.8.7" in column._link_preview.network_value.text()
    column._link_preview.hide()
    column.deleteLater()


def test_output_column_follows_the_watcher_thread(qapp, fake_watcher):
    """End to end: worker-thread probe -> queued signal -> visible URL."""
    from ui.panels.themes_panel import OutputColumn

    state = {"ip": "192.168.1.50"}
    fake_watcher._probe = lambda: state["ip"]
    fake_watcher._interval_s = 0.02
    fake_watcher.start()
    try:
        column = OutputColumn("1")
        state["ip"] = "172.16.5.6"
        expected = "http://172.16.5.6:8766/display.html?output=1"
        assert _wait_for(qapp, lambda: column._network_url == expected), \
            "network change from the worker thread never reached the column"
        assert "172.16.5.6" in \
            column._link_popup.network_row.value_label.text()
        column.deleteLater()
    finally:
        fake_watcher.stop()


def test_output_column_shows_offline_state_when_network_drops(qapp, fake_watcher):
    from ui.panels.themes_panel import OutputColumn

    column = OutputColumn("1")
    fake_watcher._probe = lambda: None
    fake_watcher.poll_once()

    assert column._network_url is None
    assert column._link_popup.network_row.value_label.text() == "Not connected"
    assert column._link_preview.network_value.text() == "Not connected"
    column.deleteLater()


def test_clicking_the_output_name_opens_and_closes_the_card(qapp, fake_watcher):
    from PyQt6.QtTest import QTest
    from ui.panels.themes_panel import OutputColumn

    column = OutputColumn("1")
    column.resize(320, 400)
    column.show()
    _spin(qapp, 20)

    QTest.mouseClick(column._link_button, Qt.MouseButton.LeftButton)
    assert column._link_popup.isVisible(), "a click pins the copy card"
    assert column._link_button.isChecked(), "the open card's trigger stays lit"

    QTest.mouseClick(column._link_button, Qt.MouseButton.LeftButton)
    assert not column._link_popup.isVisible(), "a second click closes it"
    assert not column._link_button.isChecked()

    column.hide()
    column.deleteLater()


def test_hovering_the_output_name_defers_the_preview(qapp, fake_watcher):
    from ui.panels.themes_panel import OutputColumn

    column = OutputColumn("1")
    column.resize(320, 400)
    column.show()
    _spin(qapp, 20)

    QApplication.sendEvent(column._link_button, QEvent(QEvent.Type.Enter))
    assert column._link_preview._show_timer.isActive()
    assert not column._link_popup.isVisible(), \
        "hover previews the addresses; only a click opens the copy card"
    QApplication.sendEvent(column._link_button, QEvent(QEvent.Type.Leave))
    assert not column._link_preview._show_timer.isActive(), \
        "leaving before the delay must cancel the preview"
    assert not column._link_preview.isVisible()

    column.hide()
    column.deleteLater()


def test_hover_preview_is_suppressed_while_the_card_is_open(
        qapp, fake_watcher):
    from ui.panels.themes_panel import OutputColumn

    column = OutputColumn("1")
    column.resize(320, 400)
    column.show()
    _spin(qapp, 20)

    column._link_button.click()
    assert column._link_popup.isVisible()
    QApplication.sendEvent(column._link_button, QEvent(QEvent.Type.Enter))
    assert not column._link_preview._show_timer.isActive(), \
        "the persistent card already shows the links"

    column._link_popup.hide()
    column.hide()
    column.deleteLater()


def test_a_click_outside_dismisses_the_card(qapp, fake_watcher):
    from PyQt6.QtWidgets import QWidget
    from ui.panels.themes_panel import OutputColumn

    host = QWidget()
    host.resize(400, 300)
    column = OutputColumn("1", parent=host)
    host.show()
    _spin(qapp, 20)

    column._link_button.click()
    _spin(qapp, 20)
    popup = column._link_popup
    assert popup.isVisible()

    outside = popup.frameGeometry().bottomRight() + QPoint(40, 40)
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress, QPointF(2, 2), QPointF(outside),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(host, event)
    assert not popup.isVisible(), "a click elsewhere must retire the card"
    assert not column._link_button.isChecked()

    host.hide()
    column.deleteLater()
    host.deleteLater()


def test_only_one_card_is_open_at_a_time(qapp, fake_watcher):
    from PyQt6.QtWidgets import QWidget
    from ui.panels.themes_panel import OutputColumn

    host = QWidget()
    host.resize(600, 600)
    first = OutputColumn("1", parent=host)
    second = OutputColumn("2", parent=host)
    host.show()
    _spin(qapp, 20)

    first._link_button.click()
    assert first._link_popup.isVisible()

    second._link_button.click()
    assert not first._link_popup.isVisible(), \
        "opening another output's card closes the first"
    assert not first._link_button.isChecked()
    assert second._link_popup.isVisible()
    assert second._link_button.isChecked()

    second._link_popup.hide()
    host.hide()
    first.deleteLater()
    second.deleteLater()
    host.deleteLater()

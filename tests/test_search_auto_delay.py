"""Auto-search delay for the Keyword lane (search.auto_delay_ms).

The lane used to hard-code a 100 ms debounce. It is now the operator's
choice: 0 searches on every keystroke, any other slot waits that many ms
after the last character. The panel reads the setting live, so a change
in Settings applies without a restart.
"""

import os

import pytest

import core.database as db


@pytest.fixture
def tmpdb(tmp_path):
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    return db


@pytest.fixture
def panel(tmpdb):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication(["t"])
    from ui.panels import fts_search_panel as mod
    p = mod.FtsSearchPanel()
    try:
        yield p
    finally:
        try:
            p.cleanup()
        except Exception:
            pass
        p.close()
        p.deleteLater()
        _app.processEvents()


def _fired(panel, monkeypatch):
    """Spy on _execute_search; returns the list it appends to."""
    calls = []
    monkeypatch.setattr(panel, "_execute_search",
                        lambda: calls.append(panel.query_input.text()))
    return calls


def test_default_slot_is_100ms(tmpdb, panel):
    from core.constants import SEARCH_AUTO_DELAY_MS_DEFAULT
    assert SEARCH_AUTO_DELAY_MS_DEFAULT == 100
    assert panel._debounce_timer.interval() == 100


def test_every_keystroke_fires_immediately(tmpdb, panel, monkeypatch):
    """delay 0: no wait — textChanged runs the search then and there."""
    db.set_setting("search.auto_delay_ms", "0")
    calls = _fired(panel, monkeypatch)
    panel.query_input.setText("faith")
    assert calls == ["faith"]
    assert not panel._debounce_timer.isActive(), (
        "every-keystroke mode must not arm the debounce timer")


def test_slot_sets_timer_interval(tmpdb, panel, monkeypatch):
    """A slot waits that long after the last keystroke."""
    db.set_setting("search.auto_delay_ms", "350")
    calls = _fired(panel, monkeypatch)
    panel.query_input.setText("faith")
    assert calls == [], "a delay slot must not search mid-typing"
    assert panel._debounce_timer.isActive()
    assert panel._debounce_timer.interval() == 350


def test_delay_is_read_live(tmpdb, panel, monkeypatch):
    """No restart: the next keystroke uses the newly saved value."""
    db.set_setting("search.auto_delay_ms", "500")
    calls = _fired(panel, monkeypatch)
    panel.query_input.setText("ho")
    assert calls == []
    db.set_setting("search.auto_delay_ms", "0")
    panel.query_input.setText("hope")
    assert calls == ["hope"]


def test_bad_value_falls_back(tmpdb, panel, monkeypatch):
    from core.constants import SEARCH_AUTO_DELAY_MS_DEFAULT
    db.set_setting("search.auto_delay_ms", "not-a-number")
    calls = _fired(panel, monkeypatch)
    panel.query_input.setText("grace")
    assert calls == []
    assert panel._debounce_timer.interval() == SEARCH_AUTO_DELAY_MS_DEFAULT


def test_settings_combo_persists(tmpdb):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication(["t"])
    from ui.tabs.settings_tab import SettingsTab

    w = SettingsTab()
    try:
        combo = w._search_auto_delay_combo
        assert combo.itemData(0) == 0, "first option is every keystroke"
        slots = [combo.itemData(i) for i in range(1, combo.count())]
        from core.constants import SEARCH_AUTO_DELAY_MS_SLOTS
        assert slots == list(SEARCH_AUTO_DELAY_MS_SLOTS)
        assert slots[0] == 80 and slots[-1] == 700
        # Default selection reflects the stored value.
        assert combo.currentData() == 100
        # Choosing a slot persists it (the panel reads this key).
        combo.setCurrentIndex(combo.findData(250))
        assert db.get_setting("search.auto_delay_ms") == "250"
        combo.setCurrentIndex(combo.findData(0))
        assert db.get_setting("search.auto_delay_ms") == "0"
    finally:
        w.close()
        w.deleteLater()
        _app.processEvents()

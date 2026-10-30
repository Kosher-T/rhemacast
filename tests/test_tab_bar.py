"""Top-bar tab groups: display tabs lead, core tabs follow, separated by
space (no painted divider).

Display: Scriptures, Decks (internal keys SCRIPTURE/SLIDES stay
UPPER_SNAKE — only labels are user-facing). Core, in order: Library,
History, Theme Designer, Settings.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ui.widgets.display_view  # noqa: F401  (WebEngine pre-import rule)

from PyQt6.QtWidgets import QApplication, QFrame

import pytest

import core.database as db
from ui.tokens import SPACE_16


@pytest.fixture()
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test"])
    return app


@pytest.fixture()
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    db.init_db()
    from ui.main_window import MainWindow
    w = MainWindow()
    w.show()
    w.resize(1600, 900)
    qapp.processEvents()
    qapp.processEvents()
    yield w
    w.close()
    w.deleteLater()
    qapp.processEvents()


def test_tab_order_labels_and_groups(window):
    assert list(window._tabs.keys()) == [
        "SCRIPTURE", "SLIDES", "LIBRARY", "THEME DESIGNER", "SETTINGS",
    ]
    assert [window._tab_buttons[k].text() for k in window._tabs] == [
        "Scriptures", "Decks", "Library", "Theme Designer", "Settings",
    ]
    assert window.stack.count() == 5


def test_group_gap_between_decks_and_library(window):
    lay = window.title_bar.tabs_layout
    # 5 tab containers + 1 gap
    assert lay.count() == 6
    gap = lay.itemAt(2).widget()
    assert gap.findChild(QFrame) is None
    assert gap.width() == SPACE_16


def test_first_tab_active(window):
    assert window._tab_buttons["SCRIPTURE"].isChecked()
    assert window.stack.currentIndex() == 0


def test_tab_names_are_settings_backed(window):
    """Top tab names read the "tabs.names" group and repaint live."""
    from ui.app_theme import notify_interface_font_changed
    btn = window._tab_buttons["SCRIPTURE"]
    assert "font-size: 12px;" in btn.styleSheet()
    assert "font-weight: 600;" in btn.styleSheet()
    db.set_setting("tabs.names.font_size", "16")
    db.set_setting("tabs.names.font_weight", "700")
    notify_interface_font_changed("tabs.names")
    assert "font-size: 16px;" in btn.styleSheet()
    assert "font-weight: 700;" in btn.styleSheet()

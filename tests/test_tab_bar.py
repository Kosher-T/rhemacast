"""Top-bar tab groups: display tabs lead, core tabs follow, separated.

Display: Scriptures, Decks (internal keys SCRIPTURE/SLIDES stay
UPPER_SNAKE — only labels are user-facing). Core, in order: Library,
History, Theme Designer, Settings. A divider sits between the groups.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ui.widgets.display_view  # noqa: F401  (WebEngine pre-import rule)

from PyQt6.QtWidgets import QApplication, QFrame

import pytest

import core.database as db


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
        "SCRIPTURE", "SLIDES", "LIBRARY", "HISTORY", "THEME DESIGNER",
        "SETTINGS",
    ]
    assert [window._tab_buttons[k].text() for k in window._tabs] == [
        "Scriptures", "Decks", "Library", "History", "Theme Designer",
        "Settings",
    ]
    assert window.stack.count() == 6


def test_group_separator_between_decks_and_library(window):
    lay = window.title_bar.tabs_layout
    # 6 tab containers + 1 divider
    assert lay.count() == 7
    divider = lay.itemAt(2).widget()
    assert divider.findChild(QFrame) is not None


def test_first_tab_active(window):
    assert window._tab_buttons["SCRIPTURE"].isChecked()
    assert window.stack.currentIndex() == 0

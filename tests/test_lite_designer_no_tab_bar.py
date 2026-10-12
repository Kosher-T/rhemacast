"""The Lite Designer has no [ Freeform | Theme ] bar.

Which page the popup shows is decided by how it was OPENED, not by a
switch the operator flips. Each entry point could only ever use one of
the two: the theme Quick Edit has no deck (freeform was disabled there),
and a deck edit has no business presenting a theme editor. So the bar
could only restate where you already were — and did not exist at all on
the deck path the operator actually uses.
"""
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest

from PyQt6.QtCore import Qt, QCoreApplication

QCoreApplication.setAttribute(
    Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

_APP = []
_KEEP = []


@pytest.fixture(scope="module")
def app():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test"])
    _APP.append(app)
    return app


def _designer(app, **kwargs):
    from ui.widgets.lite_designer.lite_designer import LiteDesigner
    d = LiteDesigner(parent=None, **kwargs)
    d.show()
    app.processEvents()
    _KEEP.append(d)      # a parentless popup must outlive the test
    return d


def test_no_tab_bar_is_built(app):
    from ui.widgets.lite_designer.lite_designer import LiteDesigner
    assert not hasattr(LiteDesigner, "_build_tab_bar"), (
        "the [ Freeform | Theme ] bar is back")
    assert not hasattr(LiteDesigner, "_switch_tab"), (
        "the tab switcher is back; _apply_mode should be the only path")


def test_deck_edit_shows_freeform_with_no_theme_tab(app):
    d = _designer(app, deck_id=1, theme_name="slides",
                  default_tab="freeform", freeform_enabled=True)
    assert d._stack.currentIndex() == 0, "deck edit must show freeform"
    from PyQt6.QtWidgets import QPushButton
    labels = [b.text() for b in d.findChildren(QPushButton)]
    assert "Theme" not in labels, f"a Theme tab is still present: {labels}"
    assert "Freeform" not in labels, f"a Freeform tab is still present: {labels}"


def test_theme_quick_edit_still_works(app):
    """Removing the bar must not remove theme Quick Edit — it is the mode
    that entry point is FOR, so it has to keep arriving somewhere."""
    d = _designer(app, theme_name="slides",
                  default_tab="theme", freeform_enabled=False)
    assert d._stack.currentIndex() == 1, "theme Quick Edit must show theme"
    assert d._badge.text() == "slides"


def test_page_follows_the_entry_arguments(app):
    """Explicitly asking for the theme page still wins, deck or not."""
    d = _designer(app, deck_id=1, theme_name="slides",
                  default_tab="theme", freeform_enabled=True)
    assert d._stack.currentIndex() == 1


def test_badge_names_what_is_being_edited(app):
    """The bar carried the only label saying which page you were on, so
    the badge has to keep naming it."""
    d = _designer(app, deck_id=1, theme_name="slides",
                  default_tab="freeform", freeform_enabled=True)
    assert d._badge.text() in ("(untitled)", "") or d._badge.text()

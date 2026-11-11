"""Lite Designer previews are item-aware: with a deck open, both the
freeform preview and the Theme-tab preview render the ACTIVE SLIDE
under the governing theme — never a canned sample verse, never a null
theme_data. Without a deck (theme Quick Edit), the sample verse stays.
"""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import ui.widgets.display_view  # noqa: F401

from PyQt6.QtWidgets import QApplication
import pytest

import core.database as db

pytestmark = pytest.mark.webengine

_OPEN_DESIGNERS = []


@pytest.fixture(autouse=True)
def _close_designers():
    yield
    while _OPEN_DESIGNERS:
        w = _OPEN_DESIGNERS.pop()
        try:
            w.close()
            w.deleteLater()
        except RuntimeError:
            pass
    _qt().processEvents()


_app = None


def _qt():
    global _app
    _app = QApplication.instance()
    if _app is None:
        _app = QApplication(["t"])
    return _app


def _designer(tmp_path, **kwargs):
    _qt()
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    from core.slide_service import create_deck
    from ui.widgets.lite_designer.lite_designer import LiteDesigner
    deck = create_deck("# T\n\n\n*1\nFirst slide words\n\n\n*2\nSecond slide words\n")
    kwargs.setdefault("deck_id", deck["id"])
    w = LiteDesigner(**kwargs)
    w.show()
    _qt().processEvents()
    _OPEN_DESIGNERS.append(w)
    return w


def test_freeform_preview_carries_slide_and_theme(tmp_path):
    w = _designer(tmp_path)
    seen = []
    w._preview.display_verse = lambda p: seen.append(p)
    w._refresh_preview()
    assert seen, "freeform preview must render the active slide"
    payload = seen[-1]
    assert payload["content"] == "slide"
    assert "First slide words" in payload["text"]
    assert isinstance(payload.get("theme_data"), dict) and payload["theme_data"]


@pytest.mark.skip(
    reason="Should not run: LiteDesigner._render_theme_preview was removed "
           "when the freeform preview (follows the deck) and the theme "
           "preview (sample verse) were deliberately split. This test still "
           "asserts the old deck-following theme preview. Feature it covered: "
           "the Theme tab preview rendering the active deck slide.")
def test_theme_preview_renders_active_slide_for_deck(tmp_path):
    w = _designer(tmp_path)
    seen = []
    w._theme_preview._view.display_verse = lambda p: seen.append(p)
    w._refresh_preview()
    assert seen, "theme preview must follow the edited deck"
    payload = seen[-1]
    assert payload.get("content") == "slide"
    assert "First slide words" in payload["text"]
    assert isinstance(payload.get("theme_data"), dict) and payload["theme_data"]


def test_bogus_theme_falls_back_to_default(tmp_path):
    w = _designer(tmp_path, theme_name="no-such-theme")
    seen = []
    w._preview.display_verse = lambda p: seen.append(p)
    w._refresh_preview()
    assert seen
    # Per-kind fallback: deck previews fall back to the freeform "slides"
    # theme, never the scripture "default".
    assert seen[-1]["theme"] == "slides"
    assert isinstance(seen[-1].get("theme_data"), dict)


@pytest.mark.skip(
    reason="Should not run: LiteDesigner._render_theme_preview was removed "
           "when the freeform preview (follows the deck) and the theme "
           "preview (sample verse) were deliberately split. This test still "
           "expects a theme change to re-render the deck into the theme "
           "preview. Feature it covered: live theme-change refresh of the "
           "deck-following Theme tab preview.")
def test_working_theme_change_rerenders_slide(tmp_path):
    w = _designer(tmp_path)
    seen = []
    w._theme_preview._view.display_verse = lambda p: seen.append(p)
    w._on_theme_changed(dict(w._working_theme))
    assert seen
    assert seen[-1].get("content") == "slide"
    assert "First slide words" in seen[-1]["text"]


@pytest.mark.skip(
    reason="Should not run: calls the removed "
           "LiteDesigner._render_theme_preview and asserts its old "
           "deck-following behaviour, while the current theme preview "
           "deliberately keeps the sample verse when no deck is open. "
           "Feature it covered: the Theme tab preview without a deck.")
def test_quick_edit_without_deck_keeps_sample_verse(tmp_path):
    _qt()
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    from ui.widgets.lite_designer.lite_designer import LiteDesigner
    w = LiteDesigner(theme_name="default", default_tab="theme",
                     freeform_enabled=False)
    w.show()
    _qt().processEvents()
    _OPEN_DESIGNERS.append(w)
    seen = []
    w._theme_preview._view.display_verse = lambda p: seen.append(p)
    w._render_theme_preview()
    assert seen
    assert seen[-1].get("content", "verse") == "verse"

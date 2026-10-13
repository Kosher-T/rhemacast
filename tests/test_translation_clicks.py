"""Translation click semantics in the scripture browser.

Contract (operator-facing):
  single-click translation -> highlighted (preview) verse, preview only
  double-click translation -> LIVE verse re-rendered in that translation

The double-click path must not reuse the verse double-click handler, which
correctly pushes the highlighted verse: the two gestures share a signal
otherwise, and the reference source would be ambiguous.

No-Qt tests: handlers run unbound on a bare namespace (same pattern as
test_prev_next_semantics.py), with get_verse stubbed.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


class _FakeDisplay:
    def __init__(self):
        self.published_live = []
        self.published_preview = []

    def publish_live(self, payload, verse_dict, *args):
        self.published_live.append((payload, verse_dict))

    def publish_preview(self, payload, verse_dict):
        self.published_preview.append((payload, verse_dict))


def _tab(**overrides):
    from ui.tabs.presentation_tab import PresentationTab

    tab = PresentationTab.__new__(PresentationTab)
    tab._display = _FakeDisplay()
    tab._current_display = None
    tab._current_preview = None
    tab._is_cleared = True
    tab._cloaked = False
    tab.ws_sent = []
    tab._themes_by_output = {}
    for key, value in overrides.items():
        setattr(tab, key, value)

    tab._set_cloak = lambda on: setattr(tab, "_cloaked", on)
    tab._broadcast_to_ws = lambda payload: tab.ws_sent.append(payload)
    return tab


def _live_verse():
    return {
        "text": "In the beginning God created...",
        "book": "Genesis",
        "chapter": "1",
        "verse_num": "1",
        "version": "KJV",
    }


def _stub_get_verse(monkeypatch, text="Am Anfang schuf Gott..."):
    import core.bible_service as bs
    seen = []

    def fake_get_verse(version, book, chapter, verse):
        seen.append((version, book, chapter, verse))
        return {"text": text, "chapter": str(chapter), "verse": str(verse)}

    monkeypatch.setattr(bs, "get_verse", fake_get_verse)
    return seen


def test_translation_double_click_pushes_live_reference(monkeypatch):
    """The live ref (Gen 1:1) is pushed in the new version even though the
    highlight sits on a different verse."""
    from ui.tabs.presentation_tab import PresentationTab

    seen = _stub_get_verse(monkeypatch)
    tab = _tab(_current_display=_live_verse())
    tab.browser_panel = None  # must not be consulted on the live path

    PresentationTab._on_translation_broadcast(tab, "LUT")

    assert seen == [("LUT", "Genesis", 1, 1)], seen
    (payload, verse_dict), = tab._display.published_live
    assert verse_dict["version"] == "LUT"
    assert verse_dict["book"] == "Genesis"
    assert "[LUT] Genesis 1:1" in payload["ref"]
    assert payload["text"] == "Am Anfang schuf Gott..."
    assert tab.ws_sent, "OBS must also receive the re-rendered live verse"


def test_translation_double_click_leaves_preview_alone(monkeypatch):
    """No flash: the double-click path must not write preview state at all.
    Preview keeps whatever it showed (the single-click half of the gesture
    owns preview updates)."""
    from ui.tabs.presentation_tab import PresentationTab

    _stub_get_verse(monkeypatch)
    tab = _tab(_current_display=_live_verse(),
               _current_preview={"text": "preview words"})
    tab.browser_panel = None  # must not be consulted on the live path

    PresentationTab._on_translation_broadcast(tab, "LUT")

    assert tab._display.published_live, "live must update"
    assert tab._display.published_preview == [], "preview must not flash"
    assert tab._current_preview == {"text": "preview words"}


def test_translation_double_click_falls_back_to_highlight(monkeypatch):
    """Nothing live yet: behaves like the old broadcast (highlighted verse)."""
    from ui.tabs.presentation_tab import PresentationTab

    tab = _tab(_current_display=None)
    highlighted = {"text": "highlighted words", "chapter": "3", "verse": "16"}

    class _Browser:
        def get_selected_verse(self):
            return highlighted

        _current_book = "John"

    tab.browser_panel = _Browser()
    PresentationTab._on_translation_broadcast(tab, "KJV")

    (payload, verse_dict), = tab._display.published_live
    assert verse_dict["text"] == "highlighted words"
    assert "[KJV] John 3:16" in payload["ref"]


def test_translation_double_click_missing_verse_falls_back(monkeypatch):
    """Live ref absent from the new translation: highlighted verse instead."""
    import core.bible_service as bs

    from ui.tabs.presentation_tab import PresentationTab

    monkeypatch.setattr(bs, "get_verse", lambda *a: None)
    tab = _tab(_current_display=_live_verse())

    highlighted = {"text": "highlighted words", "chapter": "3", "verse": "16"}

    class _Browser:
        def get_selected_verse(self):
            return highlighted

        _current_book = "John"

    tab.browser_panel = _Browser()
    PresentationTab._on_translation_broadcast(tab, "LUT")

    (payload, verse_dict), = tab._display.published_live
    assert verse_dict["text"] == "highlighted words"

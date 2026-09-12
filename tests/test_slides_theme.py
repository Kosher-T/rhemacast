"""Slides theme: schema values + show_title option.

Pure-logic tests (no Qt): the slides theme must carry the lyric-look
params, scripture themes must declare the new text keys with neutral
values, and slide_title_visible() must default to visible.
"""

import json
from pathlib import Path

from core.theme_loader import get_theme, slide_title_visible, get_theme_kind

THEMES_DIR = Path(__file__).resolve().parent.parent / "themes"


def _load(name: str) -> dict:
    for kind in ("scripture", "freeform"):
        path = THEMES_DIR / kind / f"{name}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    raise AssertionError(f"themes/*/{name}.json missing")


def test_theme_kinds_split():
    assert get_theme_kind("slides") == "freeform"
    for name in ("default", "fullscreen", "fullscreen_2", "reference", "reference_2"):
        assert get_theme_kind(name) == "scripture", name


def test_slides_theme_lookup():
    theme = get_theme("slides")
    assert theme is not None
    assert theme["label"] == "Slides"


def _px(value: str) -> int:
    return int(value.removesuffix("px"))


def test_slides_lyric_params():
    t = _load("slides")["text"]
    # Sizes are the operator's call — assert coherence, not exact values
    assert _px(t["min_size"]) <= _px(t["size"]) <= _px(t["max_size"])
    assert t["text_transform"] == "uppercase"
    assert t["text_align"] == "center"
    # Outline kept, drop shadow removed (no blur layer)
    assert "#000" in t["text_shadow"]
    assert "rgba(" not in t["text_shadow"]


def test_slides_has_no_translation_or_verse_num():
    theme = _load("slides")
    assert "translation" not in theme
    assert "verse_num" not in theme


def test_slides_hides_title():
    assert _load("slides")["slide"]["show_title"] is False
    assert slide_title_visible(get_theme("slides")) is False


def test_scripture_themes_declare_new_keys_neutral():
    for name in ("default", "fullscreen", "fullscreen_2", "reference", "reference_2"):
        t = _load(name)["text"]
        assert t["text_transform"] == "none", name
        assert t["text_align"] == "center", name
        assert slide_title_visible(_load(name)) is True, name


def test_slide_title_visible_defaults():
    assert slide_title_visible(None) is True
    assert slide_title_visible({}) is True
    assert slide_title_visible({"slide": {}}) is True
    assert slide_title_visible({"slide": {"show_title": True}}) is True
    assert slide_title_visible({"slide": {"show_title": False}}) is False

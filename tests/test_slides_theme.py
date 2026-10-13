"""Slides theme: schema values + show_title option.

Pure-logic tests (no Qt): the slides theme must carry the lyric-look
params, scripture themes must declare the new text keys with neutral
values, and slide_title_visible() must default to visible.
"""

import json
from pathlib import Path

from core.theme_loader import (get_theme, slide_title_visible, get_theme_kind,
                                   theme_container)

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


def _text_of(name: str) -> dict:
    """The active container's text block (all themes nest content now)."""
    return theme_container(_load(name)).get("text", {})


def test_single_container_holds_everything():
    """Every shipped theme nests all content blocks in exactly one container
    with explicit stage geometry (x/y/width/height in px)."""
    import glob
    for f in sorted(glob.glob(str(THEMES_DIR / "*" / "*.json"))):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        containers = d.get("containers")
        assert isinstance(containers, dict) and len(containers) == 1, f
        name, cont = next(iter(containers.items()))
        for key in ("x", "y", "width", "height"):
            assert key in cont, (f, key)
        assert 0 <= cont["x"] <= 1920 and 0 <= cont["y"] <= 1080, (f, cont)
        assert theme_container(d) == cont, f


def test_slides_lyric_params():
    t = _text_of("slides")
    # Sizes are the operator's call — assert coherence, not exact values
    assert _px(t["min_size"]) <= _px(t["size"]) <= _px(t["max_size"])
    assert t["text_transform"] == "uppercase"
    assert t["text_align"] == "center"
    # Outline is its own explicit key (off here), and the soft shadow is a
    # separate deliberate setting — never a hand-rolled 8-direction shadow.
    assert t["text_outline"] == "none"
    assert t["text_shadow"] == "0 4px 12px rgba(0, 0, 0, 0.4)"


def test_slides_has_no_translation_or_verse_num():
    cont = theme_container(_load("slides"))
    assert "translation" not in cont
    assert "verse_num" not in cont


def test_slides_hides_title():
    assert _load("slides")["slide"]["show_title"] is False
    assert slide_title_visible(get_theme("slides")) is False


def test_scripture_themes_declare_new_keys_neutral():
    for name in ("default", "fullscreen", "fullscreen_2", "reference", "reference_2"):
        t = _text_of(name)
        assert t["text_transform"] == "none", name
        assert t["text_align"] == "center", name
        assert slide_title_visible(_load(name)) is True, name


def test_slide_title_visible_defaults():
    assert slide_title_visible(None) is True
    assert slide_title_visible({}) is True
    assert slide_title_visible({"slide": {}}) is True
    assert slide_title_visible({"slide": {"show_title": True}}) is True
    assert slide_title_visible({"slide": {"show_title": False}}) is False

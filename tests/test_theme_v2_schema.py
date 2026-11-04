"""
tests/test_theme_v2_schema.py

Schema gate for docs/theme_schema_v2.md:
- documented defaults for canvas, containers, and blocks;
- enum/range repair (clamp first, then fall back);
- unknown keys are dropped from the resolved dict but reported;
- `schema_version` handling (absent = 1, "2" = 2, >2 = SAFE_THEME);
- the safe fallback renders the shipped `fullscreen` look exactly;
- `normalize_theme()` is pure, deterministic, and never hands back the cache.
"""

import copy
import json

import pytest

from core.theme_schema import (
    BUILTIN_ANIMATIONS,
    SAFE_THEME,
    SCHEMA_VERSION,
    normalize_theme,
)


def test_minimal_theme_fills_documented_defaults():
    resolved, report = normalize_theme(
        {"schema_version": 2, "containers": [{"id": "main"}]}, name="probe")

    assert report.ok and report.warnings == []
    assert resolved["schema_version"] == SCHEMA_VERSION == 2
    assert resolved["name"] == "probe"
    assert resolved["label"] == "probe"
    assert resolved["kind"] == "scripture"
    assert resolved["canvas"] == {
        "width": 1920, "height": 1080,
        "background": "transparent", "fit": "contain",
    }

    container = resolved["containers"][0]
    assert container["id"] == "main"
    assert container["label"] == "main"
    assert container["kind"] == "scripture"
    assert container["layer"] == 0
    assert container["visible"] is True
    assert container["position"] == {"anchor": "center"}
    assert container["width"] == "auto"
    assert container["height"] == "auto"
    assert container["min_width"] == 0
    assert container["min_height"] == 0
    assert container["max_width"] is None
    assert container["max_height"] is None
    assert container["background"] == "transparent"
    assert container["border"] == "none"
    assert container["border_radius"] is None
    assert container["box_shadow"] == "none"
    assert container["backdrop_filter"] == "none"
    assert container["opacity"] == 1
    assert container["overflow"] == "hidden"


def test_body_is_synthesized_and_an_absent_block_is_not_rendered():
    resolved, _ = normalize_theme(
        {"schema_version": 2, "containers": [{"id": "main"}]}, name="probe")
    blocks = resolved["containers"][0]["blocks"]

    # The content stack is structural, so it always exists; a content block
    # only exists when the theme declares it (spec §4.7).
    assert list(blocks) == ["body"]
    assert blocks["body"] == {
        "visible": True, "valign": "center", "gap": 0,
        "padding": 0, "padding_top": 0, "padding_right": 0,
        "padding_bottom": 0, "padding_left": 0,
    }


def test_block_default_sets_are_stable():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "containers": [{"id": "main", "blocks": {
            "text": {}, "reference": {}, "translation": {}, "verse_num": {},
        }}],
    }, name="probe")
    assert report.ok and report.warnings == []
    blocks = resolved["containers"][0]["blocks"]

    assert blocks["text"]["size"] == 40
    assert blocks["text"]["min_size"] == 4
    assert blocks["text"]["max_size"] == 300
    assert blocks["text"]["autosize"] is True
    assert blocks["text"]["text_shadow"] == "0 4px 12px rgba(0,0,0,0.4)"

    assert blocks["reference"]["position"] == "below_verse"
    assert blocks["reference"]["color"] == "#94a3b8"
    assert blocks["reference"]["font_family"] == "'DM Sans', sans-serif"
    assert blocks["reference"]["text_transform"] == "uppercase"

    assert blocks["translation"]["position"] == "right_of_reference"
    assert blocks["translation"]["color"] == "#64748b"

    assert blocks["verse_num"]["mode"] == "inline"
    assert blocks["verse_num"]["size"] == "0.6em"
    assert blocks["verse_num"]["color"] == "inherit"


def test_translation_inherits_the_reference_typography():
    resolved, _ = normalize_theme({
        "schema_version": 2,
        "containers": [{"id": "main", "blocks": {
            "reference": {
                "size": 33, "font_family": "'A', sans-serif", "weight": 650,
                "line_height": 1.4, "letter_spacing": "0.2em",
                "text_transform": "lowercase",
            },
            "translation": {},
        }}],
    }, name="probe")
    translation = resolved["containers"][0]["blocks"]["translation"]

    assert translation["size"] == 33
    assert translation["font_family"] == "'A', sans-serif"
    assert translation["weight"] == 650
    assert translation["line_height"] == 1.4
    assert translation["letter_spacing"] == "0.2em"
    assert translation["text_transform"] == "lowercase"
    # Its own defaults survive where the anchor has no opinion.
    assert translation["color"] == "#64748b"
    assert translation["margin_left"] == 8


def test_out_of_range_numbers_clamp_before_falling_back():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "canvas": {"width": 99999, "height": 1, "fit": "nope"},
        "containers": [{
            "id": "main", "layer": 500, "opacity": 5, "overflow": "weird",
            "position": {"anchor": "nope"},
        }],
    }, name="probe")
    container = resolved["containers"][0]

    assert resolved["canvas"]["width"] == 7680   # clamped, not defaulted
    assert resolved["canvas"]["height"] == 240
    assert resolved["canvas"]["fit"] == "contain"
    assert container["layer"] == 100
    assert container["opacity"] == 1
    assert container["overflow"] == "hidden"
    assert container["position"]["anchor"] == "center"
    paths = {entry.split(" path=")[1].split(" ")[0] for entry in report.warnings}
    assert {"canvas.width", "canvas.height", "canvas.fit",
            "containers[0].layer", "containers[0].opacity",
            "containers[0].overflow",
            "containers[0].position.anchor"} <= paths


def test_numeric_strings_are_accepted_for_lengths_and_numbers():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "containers": [{"id": "main", "layer": "20",
                        "position": {"anchor": "top_left", "x": "120px", "y": 40},
                        "width": "600px",
                        "blocks": {"text": {"size": "44px", "weight": "700"}}}],
    }, name="probe")
    container = resolved["containers"][0]

    assert report.warnings == []
    assert container["layer"] == 20
    assert container["position"]["x"] == 120
    assert container["width"] == 600
    assert container["blocks"]["text"]["size"] == 44
    assert container["blocks"]["text"]["weight"] == 700


def test_unknown_keys_are_dropped_from_the_resolved_dict():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "bogus_top": 1,
        "containers": [{
            "id": "main", "bogus_container": 2,
            "position": {"anchor": "center", "bogus_pos": 3},
            "blocks": {"text": {"bogus_block": 4}},
        }],
    }, name="probe")

    assert "bogus_top" not in resolved
    assert "bogus_container" not in resolved["containers"][0]
    assert "bogus_pos" not in resolved["containers"][0]["position"]
    assert "bogus_block" not in resolved["containers"][0]["blocks"]["text"]
    # Unknown keys are repairs, not problems: reported at DEBUG (spec §6.2).
    joined = "\n".join(report.notes)
    for name in ("bogus_top", "bogus_container", "bogus_pos", "bogus_block"):
        assert name in joined
    assert report.warnings == []


def test_absent_schema_version_is_v1_and_migrates():
    raw = {"name": "legacy", "containers": {"main": {
        "text": {"size": "44px", "color": "#ffffff"},
    }}}
    resolved, _ = normalize_theme(copy.deepcopy(raw), kind="scripture",
                                  name="legacy")

    assert resolved["schema_version"] == 2
    assert isinstance(resolved["containers"], list)
    # A raw v1 theme never carried a schema_version; one must not appear on
    # the caller's dict either (purity).
    assert "schema_version" not in raw


def test_string_schema_version_is_coerced():
    resolved, report = normalize_theme(
        {"schema_version": "2", "containers": [{"id": "main"}]}, name="probe")
    assert resolved["schema_version"] == 2
    assert report.ok


def test_future_schema_version_falls_back_to_the_safe_theme():
    resolved, report = normalize_theme(
        {"schema_version": 3, "containers": [{"id": "future"}]}, name="future")

    assert report.errors, "a future schema version must be reported"
    assert resolved == SAFE_THEME
    assert resolved["containers"][0]["id"] == "main"


def test_invalid_schema_version_is_treated_as_v1():
    resolved, report = normalize_theme(
        {"schema_version": "banana", "containers": {"main": {}}}, name="probe")
    assert resolved["schema_version"] == 2
    assert any("schema_version" in entry for entry in report.warnings)


def test_non_object_root_returns_the_safe_theme():
    resolved, report = normalize_theme(["not", "a", "theme"], name="probe")
    assert resolved == SAFE_THEME
    assert report.errors


def test_containers_object_is_repaired_into_an_array():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "containers": {"main": {"blocks": {"text": {"size": 50}}}},
    }, name="probe")

    assert [c["id"] for c in resolved["containers"]] == ["main"]
    assert resolved["containers"][0]["blocks"]["text"]["size"] == 50
    assert any("must be an array" in entry for entry in report.warnings)


def test_empty_containers_synthesizes_main():
    resolved, report = normalize_theme(
        {"schema_version": 2, "containers": []}, name="probe")
    assert [c["id"] for c in resolved["containers"]] == ["main"]
    assert any("no containers" in entry for entry in report.warnings)


def test_container_count_is_capped_at_sixteen():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "containers": [{"id": f"c{i}"} for i in range(20)],
    }, name="probe")

    assert len(resolved["containers"]) == 16
    assert [c["id"] for c in resolved["containers"]] == [f"c{i}" for i in range(16)]
    assert any("more than 16 containers" in e for e in report.warnings)


def test_duplicate_container_ids_are_renamed():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "containers": [{"id": "main"}, {"id": "main"}],
    }, name="probe")

    assert [c["id"] for c in resolved["containers"]] == ["main", "main_1"]
    assert any("duplicate container id" in e for e in report.warnings)


def test_invalid_ids_and_names_fall_back():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "name": "x" * 200,
        "containers": [{"id": "Main Container!"}],
    }, name="probe")

    assert resolved["name"] == "x" * 64
    assert resolved["containers"][0]["id"] == "container0"
    assert resolved["containers"][0]["label"] == "container0"
    assert any("invalid container id" in e for e in report.warnings)


def test_container_kind_is_clamped_to_the_theme_kind_family():
    resolved, _ = normalize_theme({
        "schema_version": 2,
        "containers": [{"id": "a", "kind": "any"}, {"id": "b", "kind": "banana"}],
    }, name="probe")
    assert [c["kind"] for c in resolved["containers"]] == ["any", "scripture"]


def test_theme_kind_disagreeing_with_its_folder_is_overridden():
    resolved, report = normalize_theme({
        "schema_version": 2, "kind": "freeform",
        "containers": [{"id": "main"}],
    }, kind="scripture", name="probe")
    assert resolved["kind"] == "scripture"
    assert any("disagrees with its folder" in e for e in report.warnings)


def test_freeform_aliases_reference_to_title():
    resolved, _ = normalize_theme({
        "schema_version": 2,
        "containers": [{"id": "main", "blocks": {"reference": {"size": 30}}}],
    }, kind="freeform", name="song")
    blocks = resolved["containers"][0]["blocks"]
    assert "reference" not in blocks
    assert blocks["title"]["size"] == 30
    # The title block keeps reference typography defaults.
    assert blocks["title"]["font_family"] == "'DM Sans', sans-serif"


def test_freeform_hides_every_container_after_the_first():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "containers": [{"id": "one"}, {"id": "two", "visible": True}],
    }, kind="freeform", name="song")

    assert resolved["containers"][0]["visible"] is True
    assert resolved["containers"][1]["visible"] is False
    assert any("only the first visible container" in e for e in report.warnings)


def test_scripture_keeps_every_container_visible():
    resolved, _ = normalize_theme({
        "schema_version": 2,
        "containers": [{"id": "one"}, {"id": "two"}],
    }, kind="scripture", name="probe")
    assert [c["visible"] for c in resolved["containers"]] == [True, True]


def test_legacy_flex_keys_and_container_padding_are_rejected():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "containers": [{
            "id": "main", "display": "flex", "flex_direction": "column",
            "justify_content": "center", "align_items": "center",
            "padding": "0", "padding_top": 10,
        }],
    }, name="probe")
    container = resolved["containers"][0]

    for key in ("display", "flex_direction", "justify_content",
                "align_items", "padding", "padding_top"):
        assert key not in container
    joined = "\n".join(report.warnings)
    assert "container padding is not a v2 parameter" in joined
    assert "legacy flex key is ignored" in joined


def test_types_are_coerced_or_defaulted_with_a_warning():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "containers": [{"id": "main", "visible": "false",
                        "opacity": "not a number"}],
    }, name="probe")
    container = resolved["containers"][0]

    assert container["visible"] is False
    assert container["opacity"] == 1
    assert any("boolean written as a string" in e for e in report.warnings)
    assert any("opacity is not numeric" in e for e in report.warnings)


def test_safe_theme_matches_the_shipped_fullscreen_look():
    from core.theme_loader import get_theme, get_theme_kind

    fullscreen, report = normalize_theme(
        get_theme("fullscreen"), kind=get_theme_kind("fullscreen"),
        name="fullscreen")
    assert report.ok
    safe_container = SAFE_THEME["containers"][0]
    shipped = fullscreen["containers"][0]

    assert safe_container["position"] == shipped["position"] == {
        "anchor": "top_left", "x": 60, "y": 40,
    }
    assert (safe_container["width"], safe_container["height"]) == (1800, 1000)
    assert (safe_container["min_width"], safe_container["max_width"]) == (1800, 1800)

    for block_id in ("text", "reference", "translation", "verse_num"):
        assert safe_container["blocks"][block_id] == shipped["blocks"][block_id], block_id
    assert safe_container["blocks"]["body"] == shipped["blocks"]["body"]


def test_safe_theme_is_itself_valid_and_reports_nothing():
    resolved, report = normalize_theme(copy.deepcopy(SAFE_THEME), name="safe")
    assert report.ok and report.warnings == []
    assert resolved["schema_version"] == 2
    assert resolved["containers"][0]["id"] == "main"


def test_normalize_theme_never_mutates_its_input():
    raw = {
        "schema_version": 2,
        "containers": [{"id": "main", "blocks": {
            "text": {"size": 44, "color": "#ffffff"},
        }}],
    }
    snapshot = copy.deepcopy(raw)
    resolved, _ = normalize_theme(raw, name="probe")
    resolved["containers"][0]["blocks"]["text"]["size"] = 999

    assert raw == snapshot
    again, _ = normalize_theme(raw, name="probe")
    assert again["containers"][0]["blocks"]["text"]["size"] == 44


def test_normalize_theme_is_deterministic():
    raw = {
        "schema_version": 2,
        "canvas": {"width": 1920, "height": 1080},
        "containers": [
            {"id": "a", "position": {"anchor": "left", "y": 100},
             "blocks": {"text": {"size": "44px"}}},
            {"id": "b", "layer": 20, "blocks": {"reference": {}}},
        ],
        "animations": {"pop": {"type": "custom", "duration_ms": 400,
                               "keyframes": [{"at": 0, "scale": 0.5},
                                             {"at": 100, "scale": 1}]}},
    }
    first, _ = normalize_theme(copy.deepcopy(raw), name="probe")
    second, _ = normalize_theme(copy.deepcopy(raw), name="probe")
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_builtin_animations_are_complete_definitions():
    assert set(BUILTIN_ANIMATIONS) == {
        "fade_in", "fade_out", "fade_up", "fade_down",
        "scale_up", "scale_down", "slide_up", "slide_down", "typewriter",
    }
    for name, definition in BUILTIN_ANIMATIONS.items():
        assert definition["type"] == name, name
        assert isinstance(definition["duration_ms"], int)
        assert definition["duration_ms"] > 0
    for name in ("fade_in", "fade_up", "scale_up", "slide_up"):
        frames = BUILTIN_ANIMATIONS[name]["keyframes"]
        assert frames[0]["at"] == 0 and frames[-1]["at"] == 100
    assert BUILTIN_ANIMATIONS["typewriter"]["duration_ms"] == 900
    assert BUILTIN_ANIMATIONS["typewriter"]["reveal"] == "char"


@pytest.mark.parametrize("kind", ["scripture", "freeform"])
def test_every_shipped_theme_resolves_without_warnings(kind):
    from core.theme_loader import get_themes_by_kind

    themes = get_themes_by_kind(kind)
    assert themes, f"no shipped {kind} themes"
    for name, raw in themes.items():
        resolved, report = normalize_theme(raw, kind=kind, name=name)
        assert report.warnings == [], (name, report.warnings)
        assert report.errors == [], (name, report.errors)
        assert resolved["kind"] == kind
        assert resolved["containers"], name

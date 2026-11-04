"""
tests/test_theme_v2_migration.py

Migration gate for docs/theme_schema_v2.md §7:
- v1 shape dispatch (nested containers, flat, absolute boxes);
- position synthesis from page flex (top/center/bottom, page padding_bottom);
- form/width defaults, container padding -> body padding;
- flex key conversion (`justify_content` -> `body.valign`,
  `align_items` -> block `text_align` only when absent);
- block defaults and translation inheritance;
- hard shadow ring -> explicit outline, mixed ring stays a shadow;
- v1 animation assignment -> first container only;
- deterministic, pure, and idempotent through `normalize_theme`.
"""

import copy

import pytest

from core.theme_migrate import migrate_v1_to_v2
from core.theme_schema import SCHEMA_VERSION, normalize_theme


def _migrate(raw, kind="scripture"):
    return migrate_v1_to_v2(copy.deepcopy(raw), kind=kind)


def _resolve(raw, kind="scripture", name="probe"):
    return normalize_theme(copy.deepcopy(raw), kind=kind, name=name)


def test_absent_schema_version_becomes_2_with_a_none_fit_canvas():
    migrated = _migrate({"containers": {"main": {"x": 10, "y": 20, "text": {}}}})
    assert migrated["schema_version"] == SCHEMA_VERSION == 2
    assert migrated["canvas"] == {
        "width": 1920, "height": 1080,
        "background": "transparent", "fit": "none",
    }


def test_nested_v1_containers_become_an_ordered_array():
    migrated = _migrate({"containers": {
        "backdrop": {"x": 0, "y": 0, "body": {}, "background": "#000"},
        "verse": {"x": 60, "y": 40, "text": {}},
    }})
    containers = migrated["containers"]
    assert [c["id"] for c in containers] == ["backdrop", "verse"]
    assert [c["layer"] for c in containers] == [0, 10]
    assert [c["visible"] for c in containers] == [True, True]


def test_explicit_x_and_y_become_a_top_left_position():
    resolved, _ = _resolve({"containers": {"main": {
        "x": "38.5px", "y": 39, "width": "1843px", "height": "1002px",
        "text": {},
    }}})
    container = resolved["containers"][0]
    assert container["position"] == {"anchor": "top_left", "x": 38.5, "y": 39}
    assert (container["width"], container["height"]) == (1843, 1002)


@pytest.mark.parametrize("vertical_align, page_padding, anchor, y", [
    ("flex-start", None, "top", 0),
    ("top", "0px", "top", 0),
    ("center", None, "center", -40),
    ("center", "100px", "center", -50),
    (None, None, "bottom", 80),
    ("flex-end", "0px", "bottom", 0),
    ("flex-end", "120px", "bottom", 120),
])
def test_position_is_synthesized_from_v1_page_flex(
        vertical_align, page_padding, anchor, y):
    container = {"text": {}} if vertical_align is None else {
        "text": {}, "body": {"vertical_align": vertical_align},
    }
    if page_padding is not None:
        container["body"] = dict(container.get("body", {}),
                                 padding_bottom=page_padding)
    resolved, report = _resolve({"containers": {"main": container}})
    assert resolved["containers"][0]["position"]["anchor"] == anchor
    assert resolved["containers"][0]["position"]["x"] == 0
    assert resolved["containers"][0]["position"]["y"] == y
    assert any("position synthesized" in w for w in report.warnings)


def test_synthesized_position_keeps_v1_width_defaults():
    resolved, _ = _resolve({"containers": {"main": {"text": {}}}})
    container = resolved["containers"][0]
    assert container["width"] == "auto"
    assert container["min_width"] == "60%"
    assert container["max_width"] == "80%"
    assert container["min_height"] == 0
    assert container["max_height"] is None


def test_container_padding_becomes_body_padding_only():
    resolved, _ = _resolve({"containers": {"main": {
        "padding": "0", "body": {"padding_bottom": "120px"}, "text": {},
    }}})
    body = resolved["containers"][0]["blocks"]["body"]
    # Container padding initializes the content inset ...
    assert body["padding"] == 0
    assert (body["padding_top"], body["padding_right"],
            body["padding_bottom"], body["padding_left"]) == (0, 0, 0, 0)
    # ... while the v1 body padding_bottom is a *page* inset, consumed by the
    # synthesized position and never merged into the content inset.
    assert resolved["containers"][0]["position"]["y"] == 120
    assert body["padding_bottom"] == 0


def test_hand_written_container_padding_is_carried():
    resolved, _ = _resolve({"containers": {"main": {
        "padding": "32px", "x": 0, "y": 0, "text": {},
    }}})
    body = resolved["containers"][0]["blocks"]["body"]
    assert body["padding"] == 32
    assert body["padding_top"] == 32


def test_missing_form_keys_take_the_v1_css_fallbacks():
    migrated = _migrate({"containers": {"main": {"x": 0, "y": 0, "text": {}}}})
    container = migrated["containers"][0]
    assert container["background"] == "rgba(15, 23, 42, 0.6)"
    assert container["border"] == "1px solid rgba(255, 255, 255, 0.1)"
    assert container["border_radius"] == 24
    assert "rgba(255, 255, 255, 0.05) inset" in container["box_shadow"]
    assert container["backdrop_filter"] == "blur(16px)"


@pytest.mark.parametrize("justify, expected", [
    (None, "top"),
    ("flex-start", "top"),
    ("start", "top"),
    ("flex-end", "bottom"),
    ("center", "center"),
    ("space-between", "center"),
])
def test_justify_content_becomes_body_valign(justify, expected):
    container = {"x": 0, "y": 0, "text": {}}
    if justify is not None:
        container["justify_content"] = justify
    migrated = _migrate({"containers": {"main": container}})
    assert migrated["containers"][0]["blocks"]["body"]["valign"] == expected


def test_align_items_sets_text_align_only_when_the_block_has_none():
    migrated = _migrate({"containers": {"main": {
        "x": 0, "y": 0, "align_items": "flex-end",
        "text": {}, "reference": {"text_align": "center"},
    }}})
    blocks = migrated["containers"][0]["blocks"]
    assert blocks["text"]["text_align"] == "right"
    assert blocks["reference"]["text_align"] == "center"


def test_unsupported_flex_values_warn_and_use_documented_fallbacks():
    _, report = _resolve({"containers": {"main": {
        "x": 0, "y": 0, "justify_content": "space-around",
        "align_items": "baseline", "flex_direction": "row", "text": {},
    }}})
    joined = "\n".join(report.warnings)
    assert "unsupported flex value" in joined
    assert "cannot be expressed per block" in joined
    assert "row" in joined


def test_translation_inherits_the_reference_typography():
    migrated = _migrate({"containers": {"main": {
        "x": 0, "y": 0, "text": {},
        "reference": {"size": "48px", "weight": 800, "letter_spacing": "0.2em"},
        "translation": {"color": "#AAFF00"},
    }}})
    translation = migrated["containers"][0]["blocks"]["translation"]
    assert translation["position"] == "right_of_reference"
    assert translation["size"] == "48px"
    assert translation["weight"] == 800
    assert translation["letter_spacing"] == "0.2em"
    assert translation["color"] == "#AAFF00"


def test_translation_without_a_reference_uses_the_v1_css_defaults():
    migrated = _migrate({"containers": {"main": {
        "x": 0, "y": 0, "text": {}, "translation": {},
    }}})
    translation = migrated["containers"][0]["blocks"]["translation"]
    assert translation["font_family"] == "'DM Sans', sans-serif"
    assert translation["size"] == 24
    assert translation["weight"] == 500
    assert translation["text_transform"] == "uppercase"


def test_block_defaults_are_written_down_explicitly():
    migrated = _migrate({"containers": {"main": {
        "x": 0, "y": 0,
        "text": {}, "reference": {}, "translation": {},
        "verse_num": {},
    }}})
    blocks = migrated["containers"][0]["blocks"]
    assert blocks["text"]["autosize"] is True
    assert blocks["reference"]["position"] == "below_verse"
    assert blocks["translation"]["position"] == "right_of_reference"
    assert blocks["verse_num"] == {
        "mode": "inline", "size": "0.6em", "weight": 700, "opacity": 0.7,
        "vertical_align": "top", "margin_right": "0.15em", "line_height": 1,
    }


def test_a_pure_hard_ring_becomes_a_text_outline():
    ring = ", ".join(f"{dx}px {dy}px 0 #000000"
                     for dx, dy in [(-2, -2), (2, -2), (-2, 2), (2, 2),
                                    (-2, 0), (2, 0), (0, -2), (0, 2)])
    migrated = _migrate({"containers": {"main": {
        "x": 0, "y": 0, "text": {"text_shadow": ring},
    }}})
    text = migrated["containers"][0]["blocks"]["text"]
    assert text["text_outline"] == "2px #000000"
    assert text["text_shadow"] == "none"


def test_a_mixed_ring_and_drop_shadow_stays_a_shadow():
    mixed = ("-2px -2px 0 #555, 2px -2px 0 #555, -2px 2px 0 #555, "
             "2px 2px 0 #555, 0 2px 16px rgba(0, 0, 0, 0.6)")
    resolved, _ = _resolve({"containers": {"main": {
        "x": 0, "y": 0, "text": {"text_shadow": mixed},
    }}})
    text = resolved["containers"][0]["blocks"]["text"]
    assert text["text_shadow"] == mixed
    assert text["text_outline"] == "none"


def test_an_explicit_outline_wins_over_the_shadow():
    ring = "-2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000"
    migrated = _migrate({"containers": {"main": {
        "x": 0, "y": 0,
        "text": {"text_shadow": ring, "text_outline": "3px #ff0000"},
    }}})
    text = migrated["containers"][0]["blocks"]["text"]
    assert text["text_outline"] == "3px #ff0000"
    assert text["text_shadow"] == ring


def test_v1_animations_map_onto_the_first_container_only():
    migrated = _migrate({
        "containers": {
            "main": {"x": 0, "y": 0, "text": {}},
            "second": {"x": 0, "y": 0, "text": {}},
        },
        "animations": {
            "display_enter": {"type": "fade_up", "duration_ms": 450},
            "between_slides": {"in_type": "scale_up", "out_type": "fade_down",
                               "duration_ms": 700, "easing": "linear"},
            "display_exit": {"type": "fade_out", "duration_ms": 250},
        },
    })
    first, second = migrated["containers"]
    assert first["animation"]["entry"] == {
        "use": "fade_up", "duration_ms": 450, "easing": "ease-out",
    }
    assert first["animation"]["transition"]["in"] == {
        "use": "scale_up", "duration_ms": 700, "easing": "linear",
    }
    assert first["animation"]["out"] == {
        "use": "fade_out", "duration_ms": 250, "easing": "ease-out",
    }
    # v1 never played `out_type`; it must not invent an exit phase.
    assert "out_type" not in first["animation"]
    assert "animation" not in second


def test_v1_none_and_typewriter():
    migrated = _migrate({
        "containers": {"main": {"x": 0, "y": 0, "text": {}}},
        "animations": {
            "display_enter": {"type": "none"},
            "between_slides": {"in_type": "typewriter"},
        },
    })
    animation = migrated["containers"][0]["animation"]
    assert "entry" not in animation
    assert animation["transition"]["in"]["use"] == "typewriter"


def test_flat_themes_get_one_container_and_a_40px_content_padding():
    resolved, _ = _resolve({
        "container": {"background": "#101010", "padding": "40px"},
        "text": {"size": "44px", "color": "#ffffff"},
        "reference": {"size": "24px"},
    })
    container = resolved["containers"][0]
    assert container["id"] == "main"
    assert container["position"] == {"anchor": "center", "x": 0, "y": 0}
    assert container["background"] == "#101010"
    assert container["blocks"]["body"]["padding"] == 40
    assert container["blocks"]["text"]["size"] == 44
    assert set(container["blocks"]) == {"body", "text", "reference"}


def test_oldest_absolute_boxes_use_center_coordinates():
    resolved, _ = _resolve({"containers": {
        "text": {"x": 960, "y": 540, "width": 800, "height": 200,
                 "size": 50},
        "reference": {"x": 960, "y": 700, "width": 400, "height": 60,
                      "text": "John 3:16"},
        "translation": {"x": 1200, "y": 700, "width": 100, "height": 40},
    }})
    boxes = {c["id"]: c for c in resolved["containers"]}
    assert boxes["text"]["position"] == {
        "anchor": "top_left", "x": 560, "y": 440,
    }
    assert (boxes["text"]["width"], boxes["text"]["height"]) == (800, 200)
    assert boxes["reference"]["position"] == {
        "anchor": "top_left", "x": 760, "y": 670,
    }
    assert boxes["translation"]["position"] == {
        "anchor": "top_left", "x": 1150, "y": 680,
    }
    # The hardcoded v1 per-box defaults are carried into the blocks.
    assert boxes["text"]["blocks"]["body"]["padding"] == 20
    assert boxes["reference"]["blocks"]["reference"]["size"] == 34
    assert boxes["translation"]["blocks"]["translation"]["size"] == 16


def test_freeform_show_title_false_hides_the_title_block():
    migrated = _migrate({
        "slide": {"show_title": False},
        "containers": {"main": {
            "x": 0, "y": 0, "title": {"size": 40}, "text": {},
        }},
    }, kind="freeform")
    assert migrated["containers"][0]["blocks"]["title"]["visible"] is False
    assert migrated["slide"] == {"show_title": False}


def test_migration_is_pure_and_deterministic():
    raw = {
        "containers": {"main": {
            "x": 60, "y": 40, "padding": "0",
            "text": {"size": "80px", "text_shadow": "none"},
            "reference": {"size": "48px"},
        }},
        "animations": {"display_enter": {"type": "fade_in"}},
    }
    snapshot = copy.deepcopy(raw)
    first = _migrate(raw)
    second = _migrate(raw)
    assert raw == snapshot
    assert first == second


def test_v2_documents_are_not_migrated_again():
    v2 = {
        "schema_version": 2,
        "canvas": {"width": 1280, "height": 720, "fit": "contain"},
        "containers": [{"id": "main", "position": {"anchor": "center"}}],
    }
    resolved, report = _resolve(v2)
    assert report.warnings == []
    assert resolved["canvas"] == {
        "width": 1280, "height": 720,
        "background": "transparent", "fit": "contain",
    }
    # Pure pass-through: no v1 defaults (60%/80%/bottom position) appear.
    assert resolved["containers"][0]["width"] == "auto"
    assert resolved["containers"][0]["min_width"] == 0
    assert resolved["containers"][0]["position"] == {"anchor": "center"}


def test_reachable_v2_output_is_stable_under_a_second_migration():
    once = _migrate({"containers": {"main": {
        "x": 0, "y": 0, "padding": "0", "text": {},
    }}})
    twice = migrate_v1_to_v2(copy.deepcopy(once), kind="scripture")
    # Only `schema_version` differs: an already-v2 document is annotated, but
    # the conatiner shape does not grow a second time.
    assert twice["containers"] == once["containers"]


@pytest.mark.parametrize("name", [
    "fullscreen", "default", "reference_2", "reference", "fullscreen_2",
])
def test_shipped_scripture_themes_migrate_without_warnings(name):
    from core.theme_loader import get_theme, get_theme_kind

    raw = get_theme(name)
    assert raw is not None
    _, report = normalize_theme(copy.deepcopy(raw), kind=get_theme_kind(name),
                                name=name)
    assert report.warnings == [], (name, report.warnings)
    assert report.errors == []


def test_shipped_freeform_theme_migrates_without_warnings():
    from core.theme_loader import get_theme, get_theme_kind

    raw = get_theme("slides")
    assert raw is not None
    _, report = normalize_theme(copy.deepcopy(raw), kind=get_theme_kind("slides"),
                                name="slides")
    assert report.warnings == [], report.warnings
    assert report.errors == []


def test_a_future_schema_version_bypasses_migration():
    resolved, report = normalize_theme(
        {"schema_version": 9, "containers": {"main": {"text": {}}}},
        name="future")
    assert report.errors
    assert resolved["schema_version"] == 2
    assert resolved["containers"][0]["id"] == "main"   # safe theme


def test_an_empty_v1_document_still_produces_one_container():
    resolved, report = _resolve({})
    assert [c["id"] for c in resolved["containers"]] == ["main"]
    assert any("position synthesized" in w for w in report.warnings)

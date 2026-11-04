"""
tests/test_theme_v2_animations.py

Animation gate for docs/theme_schema_v2.md §4.9:
- the built-in registry is complete, self-describing (`type` + `duration_ms`),
  and a bare name resolves to exactly the registry definition;
- a definition requires a known `type`; `duration_ms` defaults to 600 for a
  preset and 900 for `typewriter`, with a warning when omitted;
- presets reject author keyframes; `custom` requires 2–8 ordered frames that
  start at 0 and end at 100; `typewriter` takes reveal/cursor instead;
- slot grammar: `"none"`, a name, name+overrides, and inline definitions;
  overrides are only `duration_ms` / `delay_ms` / `easing`;
- unknown names fall back per phase (entry/in -> fade_in, out -> fade_out).

Shared-definition precedence lives in tests/test_theme_v2_shared.py.
"""

import copy
import json

import pytest

from core.theme_schema import (
    BUILTIN_ANIMATIONS,
    PRESET_TYPES,
    normalize_theme,
)


def _resolve(raw, name="probe"):
    return normalize_theme(copy.deepcopy(raw), name=name)


def _theme_with(definition, *, phase="entry", extra=None):
    raw = {
        "schema_version": 2,
        "animations": {"probe": definition},
        "containers": [{"id": "main", "animation": {phase: "probe"}}],
    }
    if extra:
        raw.update(extra)
    return _resolve(raw)


def _definition(definition, *, phase="entry"):
    """Resolve one named definition and return (embedded def, report)."""
    resolved, report = _theme_with(definition, phase=phase)
    return resolved["animations"].get("probe"), report


def _slot(animation, phase="entry", half=None):
    if half is not None:
        return animation["transition"][half]
    return animation[phase]


# ─── Built-in registry ──────────────────────────────────────────────────────


def test_registry_covers_every_preset_plus_typewriter():
    assert set(BUILTIN_ANIMATIONS) == set(PRESET_TYPES) | {"typewriter"}
    assert len(PRESET_TYPES) == 8


def test_every_builtin_is_self_describing():
    for name, definition in BUILTIN_ANIMATIONS.items():
        assert definition["type"] == name, name
        assert isinstance(definition["duration_ms"], int), name
        assert definition["duration_ms"] > 0, name
        assert definition["easing"], name
        if name == "typewriter":
            assert "keyframes" not in definition
            assert definition["reveal"] == "char"
            assert definition["cursor"]["char"] == "\u258c"
        else:
            frames = definition["keyframes"]
            assert frames[0]["at"] == 0, name
            assert frames[-1]["at"] == 100, name


def test_builtin_durations_are_the_documented_values():
    for name, definition in BUILTIN_ANIMATIONS.items():
        expected = 900 if name == "typewriter" else 600
        assert definition["duration_ms"] == expected, name


def test_builtin_keyframes_match_the_documented_shapes():
    assert BUILTIN_ANIMATIONS["fade_in"]["keyframes"] == [
        {"at": 0, "opacity": 0}, {"at": 100, "opacity": "base"},
    ]
    assert BUILTIN_ANIMATIONS["fade_out"]["keyframes"] == [
        {"at": 0, "opacity": "base"}, {"at": 100, "opacity": 0},
    ]
    assert BUILTIN_ANIMATIONS["fade_up"]["keyframes"] == [
        {"at": 0, "opacity": 0, "translate_y": 20},
        {"at": 100, "opacity": "base", "translate_y": 0},
    ]
    assert BUILTIN_ANIMATIONS["scale_up"]["keyframes"] == [
        {"at": 0, "opacity": 0, "scale": 0.85},
        {"at": 100, "opacity": "base", "scale": 1},
    ]
    # slide_* move without touching opacity.
    assert BUILTIN_ANIMATIONS["slide_up"]["keyframes"] == [
        {"at": 0, "translate_y": "100%"}, {"at": 100, "translate_y": 0},
    ]
    assert BUILTIN_ANIMATIONS["slide_down"]["keyframes"] == [
        {"at": 0, "translate_y": 0}, {"at": 100, "translate_y": "100%"},
    ]


@pytest.mark.parametrize("name", sorted(BUILTIN_ANIMATIONS))
def test_a_bare_builtin_name_embeds_the_registry_definition(name):
    resolved, report = _resolve({
        "schema_version": 2,
        "containers": [{"id": "main", "animation": {"entry": name}}],
    })
    assert report.warnings == []
    assert resolved["containers"][0]["animation"]["entry"] == {"use": name}
    assert resolved["animations"][name] == BUILTIN_ANIMATIONS[name]


# ─── Definition validation ──────────────────────────────────────────────────


def test_a_definition_requires_a_known_type():
    definition, report = _definition({"duration_ms": 400})
    assert definition is None
    assert "unknown animation type" in "\n".join(report.warnings)


@pytest.mark.parametrize("bad_type", ["explode", "fade-in", "FADE_IN", None, 3])
def test_unknown_types_are_dropped(bad_type):
    definition, _ = _definition({"type": bad_type, "duration_ms": 400})
    assert definition is None


def test_a_preset_without_duration_warns_and_defaults_to_600():
    definition, report = _definition({"type": "fade_in"})
    assert definition["duration_ms"] == 600
    assert "duration is required" in "\n".join(report.warnings)


def test_duration_is_clamped_and_accepts_numeric_strings():
    definition, _ = _definition({"type": "fade_in", "duration_ms": "800"})
    assert definition["duration_ms"] == 800
    definition, _ = _definition({"type": "fade_in", "duration_ms": 99999})
    assert definition["duration_ms"] == 5000
    definition, report = _definition({"type": "fade_in", "duration_ms": 0})
    assert definition["duration_ms"] == 0     # 0 = instant, still legal
    assert report.warnings == []


def test_delay_is_clamped_to_zero_5000():
    definition, _ = _definition({"type": "fade_in", "duration_ms": 300,
                                 "delay_ms": -50})
    assert definition["delay_ms"] == 0
    definition, _ = _definition({"type": "fade_in", "duration_ms": 300,
                                 "delay_ms": 9000})
    assert definition["delay_ms"] == 5000


@pytest.mark.parametrize("easing", [
    "ease-out", "ease-in", "ease-in-out", "linear", "spring", "smooth",
    "cubic-bezier(0.2, 0, 0.2, 1)",
])
def test_documented_easings_are_accepted(easing):
    definition, report = _definition({"type": "fade_in", "duration_ms": 300,
                                      "easing": easing})
    assert definition["easing"] == easing
    assert report.warnings == []


def test_an_unknown_easing_falls_back_with_a_warning():
    definition, report = _definition({"type": "fade_in", "duration_ms": 300,
                                      "easing": "bouncy"})
    assert definition["easing"] == "ease-out"
    assert "invalid easing" in "\n".join(report.warnings)


def test_typewriter_defaults_to_linear_easing():
    definition, _ = _definition({"type": "typewriter", "duration_ms": 900})
    assert definition["easing"] == "linear"


@pytest.mark.parametrize("origin", [
    "center", "top", "bottom", "left", "right",
    "top left", "top right", "bottom left", "bottom right",
])
def test_documented_origins_are_accepted(origin):
    definition, report = _definition({"type": "fade_in", "duration_ms": 300,
                                      "origin": origin})
    assert definition["origin"] == origin
    assert report.warnings == []


def test_an_unknown_origin_falls_back_to_center():
    definition, report = _definition({"type": "fade_in", "duration_ms": 300,
                                      "origin": "middle"})
    assert definition["origin"] == "center"
    assert "invalid enum value" in "\n".join(report.warnings)


def test_label_defaults_to_the_definition_name_and_is_capped():
    definition, _ = _definition({"type": "fade_in", "duration_ms": 300})
    assert definition["label"] == "probe"
    long = {"type": "fade_in", "duration_ms": 300, "label": "x" * 200}
    definition, report = _definition(long)
    assert len(definition["label"]) == 80
    assert report.warnings


# ─── custom keyframes ───────────────────────────────────────────────────────


def test_custom_requires_keyframes():
    definition, report = _definition({"type": "custom", "duration_ms": 400})
    assert definition is None
    assert "keyframes must be an array" in "\n".join(report.warnings)


@pytest.mark.parametrize("frames", [
    [],                                                     # empty
    [{"at": 0, "opacity": 0}],                              # one frame
    [{"at": 0}] * 9,                                        # nine frames
    "not a list",
])
def test_custom_rejects_non_arrays_and_wrong_frame_counts(frames):
    definition, _ = _definition({"type": "custom", "duration_ms": 400,
                                 "keyframes": frames})
    assert definition is None


@pytest.mark.parametrize("ats", [
    (10, 100),        # does not start at 0
    (0, 90),          # does not end at 100
    (0, 50, 50),      # not strictly increasing
    (0, 120),         # past 100
    (-10, 100),       # below 0
])
def test_custom_rejects_unordered_out_of_range_keyframes(ats):
    frames = [{"at": at, "opacity": 1} for at in ats]
    definition, report = _definition({"type": "custom", "duration_ms": 400,
                                      "keyframes": frames})
    assert definition is None
    assert report.warnings


def test_custom_rejects_non_object_frames():
    definition, _ = _definition({"type": "custom", "duration_ms": 400,
                                 "keyframes": [0, 100]})
    assert definition is None


def test_custom_accepts_two_to_eight_frames():
    two = [{"at": 0, "opacity": 0}, {"at": 100, "opacity": "base"}]
    definition, report = _definition({"type": "custom", "duration_ms": 400,
                                      "keyframes": two})
    assert definition["keyframes"] == two
    assert report.warnings == []

    eight = [{"at": i * 100 / 7} for i in range(8)]
    definition, _ = _definition({"type": "custom", "duration_ms": 400,
                                 "keyframes": eight})
    assert len(definition["keyframes"]) == 8


def test_custom_keeps_base_and_clamps_every_keyframe_value():
    definition, _ = _definition({"type": "custom", "duration_ms": 400,
                                 "keyframes": [
        {"at": 0, "opacity": 2, "translate_x": 5000, "translate_y": -5000,
         "scale": 9, "rotate": 5000, "blur": 999},
        {"at": 100, "opacity": "base", "translate_x": 0, "translate_y": 0,
         "scale": 1, "rotate": 0, "blur": "base"},
    ]})
    first, last = definition["keyframes"]
    assert first == {
        "at": 0, "opacity": 1, "translate_x": 2000, "translate_y": -2000,
        "scale": 4, "rotate": 1080, "blur": 60,
    }
    assert last == {
        "at": 100, "opacity": "base", "translate_x": 0, "translate_y": 0,
        "scale": 1, "rotate": 0, "blur": "base",
    }


def test_keyframes_may_omit_properties():
    definition, report = _definition({"type": "custom", "duration_ms": 400,
                                      "keyframes": [
        {"at": 0, "opacity": 0},
        {"at": 60, "scale": 0.9},
        {"at": 100, "opacity": "base"},
    ]})
    assert definition["keyframes"] == [
        {"at": 0, "opacity": 0},
        {"at": 60, "scale": 0.9},
        {"at": 100, "opacity": "base"},
    ]
    assert report.warnings == []


def test_percentage_translations_are_kept_as_percentages():
    definition, report = _definition({"type": "custom", "duration_ms": 400,
                                      "keyframes": [
        {"at": 0, "translate_x": "-50%", "translate_y": "100%"},
        {"at": 100, "translate_x": "0%", "translate_y": "0%"},
    ]})
    assert definition["keyframes"][0]["translate_x"] == "-50%"
    assert definition["keyframes"][0]["translate_y"] == "100%"
    assert report.warnings == []


def test_preset_with_keyframes_is_dropped():
    # §4.9.4: presets are defined by their type. Authored keyframes on one are
    # a mistake; the definition is dropped so the slot falls back per phase.
    definition, report = _definition({
        "type": "fade_up", "duration_ms": 400,
        "keyframes": [{"at": 0, "scale": 0.5}, {"at": 100, "scale": 1}],
    })
    assert definition is None
    assert "only type=custom accepts keyframes" in "\n".join(report.warnings)


def test_a_preset_supplies_the_builtin_keyframes():
    definition, report = _definition({"type": "fade_up", "duration_ms": 320})
    assert report.warnings == []
    assert definition["keyframes"] == BUILTIN_ANIMATIONS["fade_up"]["keyframes"]
    assert definition["duration_ms"] == 320


# ─── typewriter ─────────────────────────────────────────────────────────────


def test_typewriter_defaults():
    definition, report = _definition({"type": "typewriter", "duration_ms": 900})
    assert report.warnings == []
    assert definition["reveal"] == "char"
    assert definition["easing"] == "linear"
    assert definition["cursor"] == {
        "char": "\u258c", "color": "currentColor",
        "blink_ms": 500, "hide_after_ms": 600,
    }


def test_typewriter_word_reveal():
    definition, _ = _definition({"type": "typewriter", "duration_ms": 900,
                                 "reveal": "word"})
    assert definition["reveal"] == "word"


def test_typewriter_cursor_can_be_disabled():
    definition, report = _definition({"type": "typewriter", "duration_ms": 900,
                                      "cursor": "none"})
    assert definition["cursor"] == "none"
    assert report.warnings == []


def test_typewriter_cursor_is_validated():
    definition, report = _definition({"type": "typewriter", "duration_ms": 900,
                                      "cursor": {
        "char": "abcdef", "color": "#ff0000",
        "blink_ms": 99999, "hide_after_ms": -1,
    }})
    assert definition["cursor"]["char"] == "ab"
    assert definition["cursor"]["color"] == "#ff0000"
    assert definition["cursor"]["blink_ms"] == 2000
    assert definition["cursor"]["hide_after_ms"] == 0
    assert report.warnings


def test_typewriter_cursor_char_cannot_be_empty():
    definition, _ = _definition({"type": "typewriter", "duration_ms": 900,
                                 "cursor": {"char": ""}})
    assert definition["cursor"]["char"] == "\u258c"


def test_typewriter_ignores_keyframes_with_a_warning():
    definition, report = _definition({
        "type": "typewriter", "duration_ms": 900,
        "keyframes": [{"at": 0, "opacity": 0}, {"at": 100, "opacity": 1}],
    })
    assert "keyframes" not in definition
    assert "typewriter takes no keyframes" in "\n".join(report.warnings)


# ─── Slot grammar ───────────────────────────────────────────────────────────


def test_none_and_null_slots_are_silent():
    for value in ("none", None):
        resolved, report = _resolve({
            "schema_version": 2,
            "containers": [{"id": "main", "animation": {"entry": value,
                                                        "out": value}}],
        })
        assert resolved["containers"][0].get("animation") is None
        assert report.warnings == []


def test_a_bare_name_slot_becomes_a_use_reference():
    resolved, report = _resolve({
        "schema_version": 2,
        "containers": [{"id": "main", "animation": {"entry": "fade_up"}}],
    })
    assert resolved["containers"][0]["animation"]["entry"] == {"use": "fade_up"}
    assert report.warnings == []


def test_a_named_slot_carries_only_the_documented_overrides():
    resolved, report = _resolve({
        "schema_version": 2,
        "containers": [{"id": "main", "animation": {"entry": {
            "use": "fade_up",
            "duration_ms": 800,
            "delay_ms": 120,
            "easing": "ease-in-out",
        }}}],
    })
    assert resolved["containers"][0]["animation"]["entry"] == {
        "use": "fade_up", "duration_ms": 800, "delay_ms": 120,
        "easing": "ease-in-out",
    }
    assert report.warnings == []


def test_slot_overrides_are_clamped():
    resolved, _ = _resolve({
        "schema_version": 2,
        "containers": [{"id": "main", "animation": {"entry": {
            "use": "fade_up", "duration_ms": 99999,
        }}}],
    })
    assert resolved["containers"][0]["animation"]["entry"]["duration_ms"] == 5000


def test_a_slot_with_use_cannot_override_type():
    # A `type` on a name slot is not an inline definition; the name wins and
    # the extra key is dropped with a note (not a warning).
    resolved, report = _resolve({
        "schema_version": 2,
        "containers": [{"id": "main", "animation": {"entry": {
            "use": "fade_up", "type": "scale_up",
        }}}],
    })
    assert resolved["containers"][0]["animation"]["entry"] == {"use": "fade_up"}
    assert resolved["animations"]["fade_up"]["type"] == "fade_up"
    assert report.warnings == []
    assert any("ignoring unknown slot keys" in note for note in report.notes)


def test_an_inline_preset_stays_inline():
    resolved, report = _resolve({
        "schema_version": 2,
        "containers": [{"id": "main", "animation": {"entry": {
            "type": "scale_up", "duration_ms": 500,
        }}}],
    })
    slot = resolved["containers"][0]["animation"]["entry"]
    assert slot["type"] == "scale_up"
    assert slot["duration_ms"] == 500
    assert slot["keyframes"] == BUILTIN_ANIMATIONS["scale_up"]["keyframes"]
    # Inline definitions are not registered in the payload's name map.
    assert resolved["animations"] == {}
    assert report.warnings == []


def test_an_inline_custom_slot_keeps_its_frames():
    frames = [{"at": 0, "opacity": 0, "translate_y": 40},
              {"at": 100, "opacity": "base", "translate_y": 0}]
    resolved, report = _resolve({
        "schema_version": 2,
        "containers": [{"id": "main", "animation": {"entry": {
            "type": "custom", "duration_ms": 500, "easing": "ease-out",
            "keyframes": frames,
        }}}],
    })
    slot = resolved["containers"][0]["animation"]["entry"]
    assert slot["type"] == "custom"
    assert slot["keyframes"] == frames
    assert resolved["animations"] == {}
    assert report.warnings == []


def test_an_inline_typewriter_slot():
    resolved, report = _resolve({
        "schema_version": 2,
        "containers": [{"id": "main", "blocks": {"text": {"animation": {
            "entry": {"type": "typewriter", "duration_ms": 1200},
        }}}}],
    })
    slot = resolved["containers"][0]["blocks"]["text"]["animation"]["entry"]
    assert slot["type"] == "typewriter"
    assert slot["duration_ms"] == 1200
    assert slot["cursor"]["char"] == "\u258c"
    assert report.warnings == []


def test_an_invalid_inline_definition_falls_back_per_phase():
    resolved, report = _resolve({
        "schema_version": 2,
        "containers": [{"id": "main", "animation": {
            "entry": {"type": "explode"},
            "out": {"type": "explode"},
        }}],
    })
    animation = resolved["containers"][0]["animation"]
    assert animation["entry"] == {"use": "fade_in"}
    assert animation["out"] == {"use": "fade_out"}
    assert "unknown animation type" in "\n".join(report.warnings)


@pytest.mark.parametrize("bad_name", ["has space", "1fade", "fade_in}", ""])
def test_invalid_slot_names_fall_back_per_phase(bad_name):
    resolved, report = _resolve({
        "schema_version": 2,
        "containers": [{"id": "main", "animation": {
            "entry": bad_name, "out": bad_name,
        }}],
    })
    animation = resolved["containers"][0]["animation"]
    assert animation["entry"] == {"use": "fade_in"}
    assert animation["out"] == {"use": "fade_out"}
    assert "invalid animation name" in "\n".join(report.warnings)


def test_unknown_names_fall_back_per_phase():
    resolved, report = _resolve({
        "schema_version": 2,
        "containers": [{"id": "main", "animation": {
            "entry": "does_not_exist",
            "transition": {"in": "does_not_exist", "out": "does_not_exist"},
            "out": "does_not_exist",
        }}],
    })
    animation = resolved["containers"][0]["animation"]
    assert animation["entry"] == {"use": "fade_in"}
    assert animation["transition"]["in"] == {"use": "fade_in"}
    assert animation["transition"]["out"] == {"use": "fade_out"}
    assert animation["out"] == {"use": "fade_out"}
    assert "\n".join(report.warnings).count("unknown animation name") == 4
    # The fallback definitions are embedded so the renderer never chases names.
    assert resolved["animations"]["fade_in"] == BUILTIN_ANIMATIONS["fade_in"]
    assert resolved["animations"]["fade_out"] == BUILTIN_ANIMATIONS["fade_out"]


def test_transition_shorthand_is_the_in_half():
    resolved, _ = _resolve({
        "schema_version": 2,
        "containers": [{"id": "main", "animation": {
            "transition": "fade_up",
        }}],
    })
    assert resolved["containers"][0]["animation"]["transition"] == {
        "in": {"use": "fade_up"},
    }


def test_transition_out_and_in_are_independent():
    resolved, _ = _resolve({
        "schema_version": 2,
        "containers": [{"id": "main", "animation": {
            "transition": {"out": "fade_down", "in": "fade_up"},
        }}],
    })
    assert resolved["containers"][0]["animation"]["transition"] == {
        "out": {"use": "fade_down"},
        "in": {"use": "fade_up"},
    }


def test_transition_out_only_needs_no_entrance():
    resolved, _ = _resolve({
        "schema_version": 2,
        "containers": [{"id": "main", "animation": {
            "transition": {"out": "fade_down"},
        }}],
    })
    assert resolved["containers"][0]["animation"]["transition"] == {
        "out": {"use": "fade_down"},
    }


def test_unknown_assignment_keys_are_notes_not_warnings():
    resolved, report = _resolve({
        "schema_version": 2,
        "containers": [{"id": "main", "animation": {
            "entry": "fade_in", "hover": "fade_out", "loop": True,
        }}],
    })
    assert resolved["containers"][0]["animation"] == {"entry": {"use": "fade_in"}}
    assert report.warnings == []
    assert any("ignoring unknown animation keys" in note for note in report.notes)


def test_animation_is_legal_on_container_body_and_blocks():
    resolved, report = _resolve({
        "schema_version": 2,
        "containers": [{
            "id": "main",
            "animation": {"entry": "fade_in", "out": "fade_out"},
            "blocks": {
                "body": {"animation": {"entry": "fade_up"}},
                "text": {"animation": {"entry": "scale_up"}},
                "reference": {"animation": {"entry": "slide_up"}},
            },
        }],
    })
    container = resolved["containers"][0]
    assert container["animation"]["entry"] == {"use": "fade_in"}
    assert container["blocks"]["body"]["animation"]["entry"] == {"use": "fade_up"}
    assert container["blocks"]["text"]["animation"]["entry"] == {"use": "scale_up"}
    assert container["blocks"]["reference"]["animation"]["entry"] \
        == {"use": "slide_up"}
    assert set(resolved["animations"]) == {
        "fade_in", "fade_out", "fade_up", "scale_up", "slide_up",
    }
    assert report.warnings == []


def test_a_block_does_not_inherit_its_containers_animation():
    resolved, _ = _resolve({
        "schema_version": 2,
        "containers": [{
            "id": "main",
            "animation": {"entry": "fade_in"},
            "blocks": {"text": {}},
        }],
    })
    assert "animation" not in resolved["containers"][0]["blocks"]["text"]


def test_the_resolved_animation_payload_is_json_safe():
    resolved, _ = _resolve({
        "schema_version": 2,
        "animations": {"probe": {
            "type": "custom", "duration_ms": 400,
            "keyframes": [{"at": 0, "translate_y": "50%", "opacity": "base"},
                          {"at": 100, "translate_y": 0, "opacity": 1}],
        }},
        "containers": [{"id": "main", "animation": {"entry": "probe"}}],
    })
    dumped = json.dumps(resolved["animations"], allow_nan=False)
    assert "NaN" not in dumped and "Infinity" not in dumped
    assert resolved["animations"]["probe"]["keyframes"][0]["translate_y"] == "50%"

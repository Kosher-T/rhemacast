"""Animation registry gate: one source for defaults, ranges and enums."""

import copy
import json
import os
import re
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
from PyQt6.QtWidgets import QApplication

from core import animation_registry as reg
from core.theme_schema import BUILTIN_ANIMATIONS, normalize_theme

ROOT = Path(__file__).resolve().parents[1]
_FORMS = []


_QAPP = None


@pytest.fixture(scope="module")
def qapp():
    global _QAPP
    if _QAPP is None:
        _QAPP = QApplication.instance() or QApplication(["test"])
    return _QAPP


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    for form in _FORMS:
        try:
            form.deleteLater()
        except RuntimeError:
            pass
    _FORMS.clear()


def _resolve(definition, *, type_name):
    raw = {
        "schema_version": 2,
        "animations": {type_name: definition},
        "containers": [{"id": "main", "animation": {"entry": type_name}}],
    }
    return normalize_theme(copy.deepcopy(raw))


def _embedded(definition, *, type_name):
    resolved, report = _resolve(definition, type_name=type_name)
    return resolved["animations"].get(type_name), report


def _form(name):
    from ui.widgets.theme_designer.param_form import ParamForm

    form = ParamForm(name, reg.default_definition(name))
    _FORMS.append(form)
    return form


# ─── registry shape ─────────────────────────────────────────────────────────

def test_registry_covers_every_builtin_plus_custom():
    assert set(reg.ANIMATION_TYPES) == set(BUILTIN_ANIMATIONS) | {"custom"}
    assert set(reg.PRESET_TYPES) == set(BUILTIN_ANIMATIONS) - {"typewriter"}
    assert len(reg.PRESET_TYPES) == 8


def test_every_parameter_is_well_formed():
    for name, spec in reg.ANIMATION_SPECS.items():
        keys = [p.key for p in spec.params]
        assert len(keys) == len(set(keys)), name
        for param in spec.params:
            assert param.label, (name, param.key)
            assert param.type in reg.PARAM_TYPES
            if param.type == "enum":
                assert param.options, (name, param.key)
                assert param.default in param.option_values, (name, param.key)
            if param.type in ("number", "angle", "length"):
                assert param.default is not None, (name, param.key)
                if param.minimum is not None:
                    assert param.default >= param.minimum
                if param.maximum is not None:
                    assert param.default <= param.maximum


def test_default_definitions_match_the_builtin_library():
    assert BUILTIN_ANIMATIONS == reg.default_definitions()


@pytest.mark.parametrize("name", sorted(reg.ANIMATION_SPECS))
def test_every_default_passes_validation(name):
    definition = reg.default_definition(name)
    resolved, report = _embedded(definition, type_name=name)
    assert report.warnings == [], (name, report.warnings)
    spec = reg.ANIMATION_SPECS[name]
    expected = dict(definition)
    if spec.category == "preset":
        # Presets are defined by their type; validation supplies the frames.
        assert "keyframes" not in definition
        expected["keyframes"] = copy.deepcopy(list(spec.keyframes))
    assert resolved == expected, name


# ─── ranges ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["fade_in", "typewriter", "custom"])
def test_duration_bounds_come_from_the_registry(name):
    param = reg.param_for(name, "duration_ms")
    base = reg.default_definition(name)
    low, _ = _embedded({**base, "duration_ms": param.minimum - 10},
                       type_name=name)
    high, _ = _embedded({**base, "duration_ms": param.maximum + 10},
                        type_name=name)
    assert low["duration_ms"] == param.minimum
    assert high["duration_ms"] == param.maximum


def test_delay_and_cursor_bounds_come_from_the_registry():
    base = reg.default_definition("typewriter")
    delay = reg.param_for("typewriter", "delay_ms")
    blink = reg.param_for("typewriter", "cursor.blink_ms")
    hide = reg.param_for("typewriter", "cursor.hide_after_ms")

    low, _ = _embedded({**base, "delay_ms": delay.minimum - 10}, type_name="typewriter")
    assert low["delay_ms"] == delay.minimum

    out, _ = _embedded(
        {**base, "cursor": {**base["cursor"], "blink_ms": blink.maximum + 99,
                            "hide_after_ms": hide.maximum + 99}},
        type_name="typewriter")
    assert out["cursor"]["blink_ms"] == blink.maximum
    assert out["cursor"]["hide_after_ms"] == hide.maximum


def test_cursor_char_respects_the_registry_length():
    base = reg.default_definition("typewriter")
    limit = reg.param_for("typewriter", "cursor.char").max_length
    out, _ = _embedded(
        {**base, "cursor": {**base["cursor"], "char": "ABC"}},
        type_name="typewriter")
    assert len(out["cursor"]["char"]) <= limit


# ─── enums ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value", list(reg.param_for("typewriter", "reveal").option_values))
def test_every_reveal_option_is_accepted(value):
    base = reg.default_definition("typewriter")
    out, _ = _embedded({**base, "reveal": value}, type_name="typewriter")
    assert out["reveal"] == value


def test_invalid_enums_fall_back_to_registry_defaults():
    reveal = reg.param_for("typewriter", "reveal")
    base = reg.default_definition("typewriter")
    out, _ = _embedded({**base, "reveal": "line"}, type_name="typewriter")
    assert out["reveal"] == reveal.default

    preset = reg.default_definition("fade_in")
    out, _ = _embedded({**preset, "easing": "wobble"}, type_name="fade_in")
    assert out["easing"] == reg.param_for("fade_in", "easing").default
    out, _ = _embedded({**base, "easing": "wobble"}, type_name="typewriter")
    assert out["easing"] == reg.param_for("typewriter", "easing").default


def test_origin_options_match_the_registry():
    origin = reg.param_for("fade_in", "origin")
    for value in origin.option_values:
        out, _ = _embedded(
            {**reg.default_definition("fade_in"), "origin": value},
            type_name="fade_in")
        assert out["origin"] == value


def test_slot_overrides_use_the_slot_parameter_bounds():
    duration = reg.SLOT_PARAMS["duration_ms"]
    raw = {
        "schema_version": 2,
        "containers": [{"id": "main",
                        "animation": {"entry": {"use": "fade_in",
                                                "duration_ms": 99999}}}],
    }
    resolved, _ = normalize_theme(copy.deepcopy(raw))
    assert resolved["containers"][0]["animation"]["entry"]["duration_ms"] == duration.maximum


# ─── ParamForm ──────────────────────────────────────────────────────────────

def test_form_builds_every_registered_parameter(qapp):
    for name, spec in reg.ANIMATION_SPECS.items():
        form = _form(name)
        for param in spec.params:
            assert form.row_for(param.key) is not None, (name, param.key)
            assert form.control_for(param.key) is not None, (name, param.key)


def test_form_uses_chips_under_eight_options_and_dropdown_above(qapp):
    from ui.theme_kit import ChipSelect, CompactDropdown

    form = _form("typewriter")
    assert isinstance(form.control_for("reveal"), ChipSelect)
    assert isinstance(form.control_for("cursor.enabled"), ChipSelect) is False

    origin = _form("custom").control_for("origin")
    assert isinstance(origin, CompactDropdown)


def test_form_bounds_are_the_registry_bounds(qapp):
    form = _form("typewriter")
    for key in ("duration_ms", "delay_ms", "cursor.blink_ms",
                "cursor.hide_after_ms"):
        param = form.param(key)
        assert (param.minimum, param.maximum) == (
            reg.param_for("typewriter", key).minimum,
            reg.param_for("typewriter", key).maximum)


def test_form_honours_visible_if(qapp):
    form = _form("typewriter")
    assert not form.row_for("cursor.char").isHidden()
    form.set_value("cursor.enabled", False)
    assert form.row_for("cursor.char").isHidden()
    assert form.row_for("cursor.blink_ms").isHidden()
    form.set_value("cursor.enabled", True)
    assert not form.row_for("cursor.char").isHidden()


def test_form_preserves_unknown_keys(qapp):
    form = _FORMS.pop() if False else None  # keep fixture shape explicit
    from ui.widgets.theme_designer.param_form import ParamForm

    form = ParamForm("fade_in", {"type": "fade_in", "studio_note": "keep"})
    _FORMS.append(form)
    form.set_value("duration_ms", 750)
    values = form.values()
    assert values["duration_ms"] == 750
    assert values["studio_note"] == "keep"
    assert values["type"] == "fade_in"


def test_advanced_parameters_start_hidden(qapp):
    form = _form("custom")
    assert form.row_for("keyframes").isHidden()
    form._on_advanced(True)
    assert not form.row_for("keyframes").isHidden()


def test_form_keeps_cursor_none(qapp):
    form = _form("typewriter")
    form.set_value("cursor.enabled", False)
    assert form.values()["cursor"] == "none"
    form.set_value("cursor.enabled", True)
    assert isinstance(form.values()["cursor"], dict)


# ─── generated renderer defaults ────────────────────────────────────────────

def test_generated_js_matches_the_registry():
    generated = (ROOT / "display" / "animation_defaults.js").read_text()
    assert generated == reg.js_constants()


def test_display_loads_generated_defaults_before_the_engine():
    html = (ROOT / "display" / "display.html").read_text()
    defaults = html.index("animation_defaults.js")
    engine = html.index("display.js")
    assert defaults < engine


def test_renderers_use_the_registry_defaults():
    for path in ("display/display.js", "ui/widgets/display_view.py"):
        source = (ROOT / path).read_text()
        assert "RC_ANIM_DEFAULTS.typewriter_duration_ms" in source, path
        assert re.search(r"def\.duration_ms : 900", source) is None, path
        assert re.search(r"durationMs \|\| 600", source) is None, path


def test_schema_no_longer_owns_animation_defaults():
    source = (ROOT / "core" / "theme_schema.py").read_text()
    assert "_preset_keyframes" not in source
    assert "600, 0, 5000" not in source
    assert "ANIMATION_SPECS" in source

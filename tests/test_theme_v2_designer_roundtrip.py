"""
tests/test_theme_v2_designer_roundtrip.py

Designer round-trip gate: the existing Theme Designer keeps editing v2 themes
without losing what it does not understand.

The designer's v1 path is frozen; the v2 adapter (`_collect_theme_v2`) must:

- start from the loaded source so unknown top-level/container/block keys,
  sibling containers, v2-only fields and animation assignments survive;
- merge managed blocks instead of replacing them;
- write geometry to `position` and padding to `blocks.body`, never to legacy
  container keys (`x`/`y`, `padding*`, `display`/`flex_*`);
- use `"visible": false` for a disabled element and keep the block itself;
- leave structured values (border/shadow objects) intact when untouched;
- produce a dict that resolves again with zero warnings.

`load_theme()` must never mutate the dict it was handed, and a v1 theme must
still round-trip as v1 (no silent schema migration on save).
"""

import copy
import json
import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
from PyQt6.QtWidgets import QApplication

from core.theme_schema import normalize_theme

_PANELS = []


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test"])
    return app


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    for panel in _PANELS:
        try:
            panel.deleteLater()
        except RuntimeError:
            pass
    _PANELS.clear()


def _panel(theme):
    from ui.widgets.theme_properties_panel import ThemePropertiesPanel

    panel = ThemePropertiesPanel()
    _PANELS.append(panel)
    panel.load_theme(theme)
    return panel


def _set_element(panel, key, enabled):
    """Drive the toggle the way a click does (no event loop needed)."""
    toggle = panel._element_toggles[key]
    toggle._toggle.setChecked(enabled)
    toggle._on_toggle(enabled)


def _theme():
    return {
        "name": "probe",
        "label": "Probe",
        "schema_version": 2,
        "kind": "scripture",
        "canvas": {
            "width": 1920, "height": 1080, "background": "#000000",
            "fit": "contain",
        },
        "future_engine_key": {"keep": True},
        "containers": [
            {
                "id": "main",
                "label": "Main",
                "kind": "scripture",
                "layer": 10,
                "position": {"anchor": "center", "x": 0, "y": 20},
                "width": 1400,
                "height": 600,
                "background": "rgba(0,0,0,0.45)",
                "border": {"width": 2, "style": "solid",
                           "color": "#D4AF37", "radius": 12},
                "box_shadow": {"x": 0, "y": 24, "blur": 48, "spread": -12,
                               "color": "rgba(0,0,0,0.55)"},
                "animation": {
                    "entry": "fade_up",
                    "transition": {"in": "fade_in", "out": "fade_out"},
                    "out": "fade_out",
                },
                "blocks": {
                    "body": {"valign": "center", "gap": 10, "padding": 24},
                    "text": {
                        "font_family": "'Nunito', sans-serif",
                        "color": "#ffffff",
                        "size": 48,
                        "weight": 500,
                        "line_height": 1.2,
                        "letter_spacing": 0,
                        "text_shadow": "none",
                        "min_size": 36,
                        "max_size": 64,
                        "visible": True,
                        "glow": {"radius": 4},
                    },
                    "reference": {
                        "font_family": "'Nunito', sans-serif",
                        "color": "#cccccc",
                        "size": 32,
                        "weight": 700,
                        "text_transform": "uppercase",
                        "letter_spacing": "0.1em",
                        "visible": True,
                    },
                    "translation": {
                        "position": "right_of_reference",
                        "color": "#64748b",
                        "margin_left": 8,
                        "visible": True,
                    },
                    "verse_num": {
                        "mode": "inline",
                        "position": "above_verse",
                        "color": "#cccccc",
                        "font_family": "'Nunito', sans-serif",
                        "visible": True,
                    },
                },
                "designer_note": "keep",
            },
            {
                "id": "citation",
                "label": "Citation",
                "kind": "scripture",
                "layer": 30,
                "position": {"anchor": "bottom_right", "x": 40, "y": 40},
                "blocks": {"reference": {"visible": True}},
                "custom_layout": {"column": 2},
            },
        ],
    }


def _collect(panel):
    return panel.get_theme()


# ─── Unknown / v2-only data survives ────────────────────────────────────────


def test_a_v2_theme_keeps_unknown_fields_and_sibling_containers(qapp):
    source = _theme()
    result = _collect(_panel(source))

    assert result["future_engine_key"] == {"keep": True}
    assert result["containers"][0]["designer_note"] == "keep"
    assert result["containers"][0]["blocks"]["text"]["glow"] == {"radius": 4}
    assert result["containers"][1]["custom_layout"] == {"column": 2}

    assert [c["id"] for c in result["containers"]] == ["main", "citation"]
    assert result["schema_version"] == 2
    assert isinstance(result["containers"], list)


def test_structured_border_and_shadow_are_not_stringified(qapp):
    result = _collect(_panel(_theme()))
    container = result["containers"][0]
    assert container["border"] == {
        "width": 2, "style": "solid", "color": "#D4AF37", "radius": 12,
    }
    assert container["box_shadow"] == {
        "x": 0, "y": 24, "blur": 48, "spread": -12,
        "color": "rgba(0,0,0,0.55)",
    }


def test_animation_assignments_survive_the_round_trip(qapp):
    source = _theme()
    result = _collect(_panel(source))
    assert result["containers"][0]["animation"] == source["containers"][0]["animation"]


def test_a_collected_v2_theme_resolves_without_warnings(qapp):
    result = _collect(_panel(_theme()))
    resolved, report = normalize_theme(result, kind="scripture", name="probe")
    assert report.warnings == []
    # Unknown keys are reported at DEBUG into `notes`, not as errors.
    joined = "\n".join(report.notes)
    assert "designer_note" in joined
    assert "custom_layout" in joined
    assert resolved["containers"][0]["blocks"]["text"]["size"] == 48


# ─── Edits write v2, not legacy ─────────────────────────────────────────────


def test_geometry_edits_land_in_position_not_container_x_y(qapp):
    panel = _panel(_theme())
    panel._container_rows["x"].set_value("120")
    panel._container_rows["y"].set_value("80")
    result = _collect(panel)

    container = result["containers"][0]
    assert container["position"] == {"anchor": "center", "x": 120, "y": 80}
    for legacy_key in ("x", "y"):
        assert legacy_key not in container


def test_padding_edits_land_in_blocks_body(qapp):
    panel = _panel(_theme())
    panel._container_rows["padding"].set_value("30")
    result = _collect(panel)

    container = result["containers"][0]
    body = container["blocks"]["body"]
    assert body["padding"] == 30
    assert body["padding_top"] == 30
    assert body["padding_right"] == 30
    assert body["padding_bottom"] == 30
    assert body["padding_left"] == 30
    assert "padding" not in container


def test_the_v2_adapter_never_writes_legacy_flex_keys(qapp):
    panel = _panel(_theme())
    # Loading a blank flex row must not resurrect the v1 defaults.
    panel._container_rows["flex_direction"].set_value("row")
    panel._container_rows["justify_content"].set_value("flex-start")
    panel._container_rows["align_items"].set_value("flex-end")
    result = _collect(panel)

    container = result["containers"][0]
    for legacy_key in ("display", "flex_direction", "justify_content",
                       "align_items"):
        assert legacy_key not in container


def test_managed_blocks_are_merged_not_replaced(qapp):
    panel = _panel(_theme())
    panel._text_size.set_value("52px")
    result = _collect(panel)

    text = result["containers"][0]["blocks"]["text"]
    assert text["size"] == 52
    assert text["glow"] == {"radius": 4}          # untouched unknown key
    assert text["min_size"] == 36                 # untouched managed key


def test_loading_does_not_mutate_the_source_dict(qapp):
    source = _theme()
    snapshot = copy.deepcopy(source)
    panel = _panel(source)
    panel._container_rows["x"].set_value("120")
    panel._text_size.set_value("52px")
    _collect(panel)

    assert source == snapshot
    assert source["containers"][0]["position"] == {"anchor": "center",
                                                   "x": 0, "y": 20}
    assert source["containers"][0]["blocks"]["text"]["size"] == 48


# ─── Toggles ────────────────────────────────────────────────────────────────


def test_disabling_an_element_writes_visible_false_and_keeps_the_block(qapp):
    panel = _panel(_theme())
    _set_element(panel, "reference", False)
    result = _collect(panel)

    reference = result["containers"][0]["blocks"]["reference"]
    assert reference["visible"] is False
    # The block is not deleted, and its typography survives for re-enabling.
    assert reference["color"] == "#cccccc"
    assert reference["size"] == 32


def test_re_enabling_an_element_sets_visible_true(qapp):
    panel = _panel(_theme())
    _set_element(panel, "reference", False)
    _set_element(panel, "reference", True)
    result = _collect(panel)
    assert result["containers"][0]["blocks"]["reference"]["visible"] is True


def test_a_disabled_block_still_resolves_without_warnings(qapp):
    panel = _panel(_theme())
    _set_element(panel, "translation", False)
    resolved, report = normalize_theme(_collect(panel), kind="scripture",
                                       name="probe")
    assert report.warnings == []
    translation = resolved["containers"][0]["blocks"]["translation"]
    assert translation["visible"] is False
    # An invisible block is still validated and defaults are filled.
    assert translation["color"] == "#64748b"


# ─── v1 themes are not silently migrated ────────────────────────────────────


def test_a_v1_theme_round_trips_as_v1(qapp):
    path = Path(__file__).resolve().parent.parent / "themes" / "scripture" / "default.json"
    source = json.loads(path.read_text(encoding="utf-8"))
    panel = _panel(source)
    assert panel._is_v2 is False

    result = _collect(panel)
    assert "schema_version" not in result
    assert isinstance(result["containers"], dict)
    assert set(result["containers"]) == set(source["containers"])
    assert "position" not in next(iter(result["containers"].values()))


def test_loading_a_v1_theme_does_not_mutate_it(qapp):
    source = {
        "name": "legacy",
        "containers": {
            "main": {"x": 100, "y": 50, "width": 1400, "height": 600,
                     "text": {"size": "44px", "color": "#ffffff"}},
        },
    }
    panel = _panel(source)
    panel._container_rows["x"].set_value("200")
    result = _collect(panel)

    assert source["containers"]["main"]["x"] == 100
    assert result["containers"]["main"]["x"] == 200

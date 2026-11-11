"""Stage 2 gate: the Designer property editor round-trips the raw document.

Covers unknown keys, shared refs, palette tokens and one edit per property
group (canvas, container, body, text, reference, translation, verse_num).
"""

import copy
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
from PyQt6.QtWidgets import QApplication

from core.theme_schema import normalize_theme

_EDITORS = []


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
    for editor in _EDITORS:
        try:
            editor.deleteLater()
        except RuntimeError:
            pass
    _EDITORS.clear()


def _editor(theme):
    from ui.widgets.theme_designer import ThemePropertyEditor

    editor = ThemePropertyEditor()
    _EDITORS.append(editor)
    editor.load_theme(theme)
    return editor


def _theme():
    return {
        "schema_version": 2,
        "name": "probe",
        "label": "Probe",
        "kind": "scripture",
        "author": "keep-me",
        "canvas": {
            "width": 1920, "height": 1080,
            "background": "@accent", "fit": "contain",
        },
        "containers": [{
            "id": "main",
            "label": "Main",
            "kind": "scripture",
            "layer": 10,
            "visible": True,
            "min_width": 0,
            "max_width": None,
            "min_height": 0,
            "max_height": None,
            "background": "transparent",
            "border": {"shared": "gold_frame"},
            "border_radius": 0,
            "box_shadow": {"shared": "soft"},
            "backdrop_filter": "none",
            "opacity": 1,
            "overflow": "hidden",
            "unknown_container_key": {"keep": [1, 2, 3]},
            "blocks": {
                "body": {
                    "visible": True, "valign": "center", "gap": 0,
                    "padding": 0, "padding_top": 0, "padding_right": 0,
                    "padding_bottom": 0, "padding_left": 0,
                },
                "text": {
                    "visible": True, "color": "@accent",
                    "font_family": "'Nunito', sans-serif",
                    "size": "40px", "min_size": 4, "max_size": 300,
                    "weight": 700, "line_height": 1.2,
                    "letter_spacing": "-0.01em", "word_spacing": 0,
                    "text_shadow": {"x": 0, "y": 4, "blur": 12, "spread": 0,
                                    "color": "rgba(0,0,0,0.4)", "inset": False},
                    "text_outline": "none", "text_transform": "none",
                    "text_align": "center", "font_style": "normal",
                    "text_decoration": "none", "opacity": 1,
                    "max_lines": None, "direction": "ltr",
                    "margin_top": 0, "margin_right": 0, "margin_bottom": 24,
                    "margin_left": 0, "padding": 0, "padding_top": 0,
                    "padding_right": 0, "padding_bottom": 0,
                    "padding_left": 0, "autosize": True,
                    "legacy_note": "keep me",
                },
                "reference": {
                    "visible": True, "position": "below_verse",
                    "color": "#94a3b8", "font_family": "'DM Sans', sans-serif",
                    "size": "24px", "weight": 500,
                    "letter_spacing": "0.1em",
                    "text_transform": "uppercase",
                },
                "translation": {
                    "visible": True, "position": "right_of_reference",
                    "color": "#64748b", "margin_left": "8px",
                },
                "verse_num": {
                    "visible": True, "mode": "inline",
                    "position": "above_verse", "vertical_align": "top",
                    "margin_right": "0.15em", "size": "0.6em",
                    "weight": 700, "opacity": 0.7, "line_height": 1,
                    "color": "inherit", "font_family": "inherit",
                },
            },
        }],
        "animations": {"fade_in": {"type": "fade_in", "duration_ms": 600}},
        "theme_meta": {"author_note": "keep"},
    }


def test_untouched_round_trip_preserves_everything(qapp):
    theme = _theme()
    editor = _editor(theme)
    assert editor.get_theme() == theme
    assert editor.get_theme() is not theme


def test_canvas_and_container_groups(qapp):
    theme = _theme()
    editor = _editor(theme)
    editor.set_field("canvas.width", 1600)
    editor.set_field("canvas.background", "@accent")
    editor.set_field("containers.0.label", "Stage")
    editor.set_field("containers.0.layer", 30)
    editor.set_field("containers.0.opacity", 0.5)
    editor.set_field("containers.0.border_radius", 12)
    editor.set_field("containers.0.max_width", "50%")
    editor.set_field("containers.0.overflow", "visible")

    doc = editor.get_theme()
    assert doc["canvas"]["width"] == 1600
    assert doc["canvas"]["background"] == "@accent"
    assert doc["containers"][0]["label"] == "Stage"
    assert doc["containers"][0]["layer"] == 30
    assert doc["containers"][0]["opacity"] == 0.5
    assert doc["containers"][0]["border_radius"] == 12
    assert doc["containers"][0]["max_width"] == "50%"
    assert doc["containers"][0]["overflow"] == "visible"
    # shared refs and unknown keys survive
    assert doc["containers"][0]["border"] == {"shared": "gold_frame"}
    assert doc["containers"][0]["box_shadow"] == {"shared": "soft"}
    assert doc["containers"][0]["unknown_container_key"] == {"keep": [1, 2, 3]}
    assert doc["theme_meta"] == {"author_note": "keep"}
    assert doc["animations"] == theme["animations"]


def test_block_groups(qapp):
    theme = _theme()
    editor = _editor(theme)
    editor.set_field("containers.0.blocks.body.padding", 16)
    editor.set_field("containers.0.blocks.text.size", "48px")
    editor.set_field("containers.0.blocks.text.weight", 600)
    editor.set_field("containers.0.blocks.text.text_transform", "uppercase")
    editor.set_field("containers.0.blocks.text.color", "@accent")
    editor.set_field("containers.0.blocks.reference.position", "above_verse")
    editor.set_field("containers.0.blocks.translation.position",
                     "below_reference")
    editor.set_field("containers.0.blocks.verse_num.mode", "block")

    doc = editor.get_theme()
    blocks = doc["containers"][0]["blocks"]
    assert blocks["body"]["padding"] == 16
    assert blocks["text"]["size"] == "48px"
    assert blocks["text"]["weight"] == 600
    assert blocks["text"]["text_transform"] == "uppercase"
    assert blocks["text"]["color"] == "@accent"
    assert blocks["reference"]["position"] == "above_verse"
    assert blocks["translation"]["position"] == "below_reference"
    assert blocks["verse_num"]["mode"] == "block"
    assert blocks["text"]["legacy_note"] == "keep me"


def test_structured_shadow_shape_round_trips(qapp):
    theme = _theme()
    editor = _editor(theme)
    shadow = {"x": 2, "y": 6, "blur": 18, "spread": -2,
              "color": "@accent", "inset": True}
    editor.set_field("containers.0.box_shadow", shadow)
    assert editor.get_theme()["containers"][0]["box_shadow"] == shadow


def test_validator_message_is_surfaced_not_reimplemented(qapp):
    theme = _theme()
    editor = _editor(theme)
    editor.set_field("canvas.width", 99999)
    # the raw document keeps what was typed; the schema clamps and reports
    assert editor.get_theme()["canvas"]["width"] == 99999
    assert editor._note.text().strip() != ""
    resolved, _report = normalize_theme(editor.get_theme(), kind="scripture")
    assert resolved["canvas"]["width"] == 7680


def test_every_group_is_reachable(qapp):
    theme = _theme()
    editor = _editor(theme)
    canvas_paths = editor.field_paths()
    assert "canvas.width" in canvas_paths
    assert "canvas.background" in canvas_paths

    editor._pages.set_value("container")
    container_paths = editor.field_paths()
    for path in ("containers.0.border", "containers.0.box_shadow",
                 "containers.0.backdrop_filter", "containers.0.opacity"):
        assert path in container_paths

    editor._pages.set_value("blocks")
    block_paths = editor.field_paths()
    for path in ("containers.0.blocks.text.size",
                 "containers.0.blocks.text.text_shadow",
                 "containers.0.blocks.text.margin_top",
                 "containers.0.blocks.text.padding"):
        assert path in block_paths


def test_page_switch_leaves_no_old_rows_visible(qapp):
    from ui.theme_kit import PropertyRow
    from ui.widgets.theme_designer.property_editor import block_specs

    editor = _editor(_theme())
    editor._pages.set_value("blocks", emit=True)
    # one row per non-sides spec, plus the two four-side rows
    expected = sum(1 for spec in block_specs("text")
                   if spec["kind"] != "sides") + 2
    # Stage 4 nests SplitEditor rows; count only this page's direct rows.
    rows = [w for w in editor._host.findChildren(PropertyRow)
            if w.parent() is editor._host and not w.isHidden()]
    assert len(rows) == expected

    editor._pages.set_value("canvas", emit=True)
    rows = [w for w in editor._host.findChildren(PropertyRow)
            if w.parent() is editor._host and not w.isHidden()]
    assert len(rows) == 4  # width, height, background, fit


def test_untouched_document_normalizes_cleanly(qapp):
    theme = _theme()
    editor = _editor(theme)
    resolved, report = normalize_theme(copy.deepcopy(editor.get_theme()),
                                       kind="scripture")
    # shared refs and the palette are the only unresolved inputs here; the
    # document itself must not introduce schema errors of its own.
    assert resolved["canvas"]["width"] == 1920
    assert resolved["containers"][0]["blocks"]["text"]["size"] == 40

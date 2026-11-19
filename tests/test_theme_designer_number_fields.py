"""Theme Designer numeric fields: one widget, per-mode limits, live canvas.

These cover the behaviour the shared :class:`NumberField` gained for the
Designer: per-unit ranges, min/max sibling limits, px↔% conversion, the
single-unit label and the live canvas-dependent pixel bounds.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from core import theme_schema as schema  # noqa: E402

_QAPP = None


@pytest.fixture(scope="module")
def qapp():
    global _QAPP
    _QAPP = QApplication.instance() or QApplication(["test"])
    return _QAPP


def _editor(theme):
    from ui.widgets.theme_designer import ThemePropertyEditor

    editor = ThemePropertyEditor()
    editor.load_theme(theme)
    editor._pages.set_value("container")
    editor._on_page("container")
    return editor


def _theme(width=1920, height=1080, **container):
    values = {
        "id": "main",
        "label": "Main",
        "layer": 10,
        "visible": True,
        "position": {"anchor": "center", "x": 0, "y": 0},
        "min_width": "100px",
        "max_width": "1500px",
        "min_height": "100px",
        "max_height": None,
        "border_radius": "12px",
        "opacity": 1.0,
        "overflow": "hidden",
        "blocks": {},
    }
    values.update(container)
    return {"kind": "scripture", "canvas": {"width": width,
                                            "height": height},
            "containers": [values]}


def _field(editor, name):
    return editor._field_widgets[("containers", 0, name)]


# ─── one widget, one set of rules ───────────────────────────────────────────

def test_single_unit_lengths_render_a_label_not_a_dropdown(qapp):
    editor = _editor(_theme())
    radius = _field(editor, "border_radius")

    assert radius._unit_button is None
    assert radius._unit_label is not None
    assert radius._unit_label.text() == "px"


def test_multi_unit_lengths_keep_their_dropdown(qapp):
    editor = _editor(_theme())

    for name in ("min_width", "max_width", "min_height", "max_height"):
        field = _field(editor, name)
        assert field._unit_button is not None
        assert field._unit_label is None


def test_container_id_row_is_gone_but_label_stays(qapp):
    editor = _editor(_theme())
    paths = editor.field_paths()

    assert "containers.0.id" not in paths
    assert "containers.0.label" in paths


# ─── limits ────────────────────────────────────────────────────────────────

def test_pixel_width_stops_at_the_live_canvas_width(qapp):
    editor = _editor(_theme(max_width=None))
    field = _field(editor, "min_width")

    field.scrub_to(10 ** 6)
    assert field.value() == "1920px"
    field.scrub_to(10 ** 6)
    assert field.value() == "1920px"


def test_typed_and_pasted_values_clamp_on_commit(qapp):
    editor = _editor(_theme(max_width=None))
    field = _field(editor, "min_width")

    field._begin_typing()
    field._edit.setText("99999")
    field._commit_typing()

    assert field.value() == "1920px"


def test_percent_width_stays_inside_zero_to_hundred(qapp):
    editor = _editor(_theme())
    field = _field(editor, "max_height")
    field.set_value("40%")

    field.scrub_to(10 ** 6)
    assert field.value() == "100%"


def test_layer_uses_the_schema_integer_range(qapp):
    editor = _editor(_theme())
    field = _field(editor, "layer")

    field.scrub_to(10 ** 6)
    assert field.value() == 100
    field.scrub_to(-10 ** 6)
    assert field.value() == 0


def test_a_drag_that_hits_a_bound_flashes_the_field(qapp):
    editor = _editor(_theme())
    field = _field(editor, "min_width")

    field.scrub_to(10 ** 6)
    assert field._limit_hit is True
    field._clear_limit()
    assert field._limit_hit is False


# ─── min / max relationship ────────────────────────────────────────────────

def test_min_width_cannot_pass_max_width(qapp):
    editor = _editor(_theme())
    low = _field(editor, "min_width")
    high = _field(editor, "max_width")

    low.scrub_to(10 ** 6)
    assert low.value() == "1500px"
    assert high.value() == "1500px"


def test_max_width_cannot_drop_below_min_width(qapp):
    editor = _editor(_theme())
    low = _field(editor, "min_width")
    high = _field(editor, "max_width")
    low.set_value("400px")

    high.scrub_to(-10 ** 6)
    assert high.value() == "400px"


def test_clearing_max_releases_the_min_width_limit(qapp):
    editor = _editor(_theme())
    low = _field(editor, "min_width")
    high = _field(editor, "max_width")

    high._clear_value()
    assert high.value() is None
    low.scrub_to(10 ** 6)
    assert low.value() == "1920px"


# ─── units ─────────────────────────────────────────────────────────────────

def test_switching_px_to_percent_keeps_the_rendered_size(qapp):
    editor = _editor(_theme())
    field = _field(editor, "min_width")
    field.set_value("960px")

    field._on_unit_changed("%")
    assert field.value() == "50%"
    field._on_unit_changed("px")
    assert field.value() == "960px"


def test_switching_units_does_not_dirty_a_zero_value(qapp):
    editor = _editor(_theme(min_width=0, max_width=0))
    field = _field(editor, "max_width")
    document = editor._document
    before = document.revision

    field._on_unit_changed("%")

    assert document.revision == before
    assert document.snapshot()["containers"][0]["max_width"] == 0


# ─── live canvas and out-of-range loads ────────────────────────────────────

@pytest.mark.parametrize("width,height", [(1920, 1080), (4270, 1080),
                                          (1080, 1920)])
def test_pixel_limits_follow_the_canvas(qapp, width, height):
    editor = _editor(_theme(width=width, height=height))
    field = _field(editor, "min_width")
    vertical = _field(editor, "min_height")

    assert field._unit_ranges["px"][1] == float(width)
    assert vertical._unit_ranges["px"][1] == float(height)


def test_a_canvas_resize_updates_the_pixel_limits(qapp):
    editor = _editor(_theme())
    field = _field(editor, "min_width")
    assert field._unit_ranges["px"][1] == 1920.0

    editor._document.set(("canvas", "width"), 1080)
    editor._on_document_changed(None, None)
    field = _field(editor, "min_width")

    assert field._unit_ranges["px"][1] == 1080.0


def test_an_out_of_range_value_loads_without_clamping_or_dirtying(qapp):
    editor = _editor(_theme(max_height="3955%"))
    field = _field(editor, "max_height")
    document = editor._document

    assert field.value() == "3955%"
    assert document.snapshot()["containers"][0]["max_height"] == "3955%"

    field._step_by(1)
    assert field.value() == "100%"

"""Theme Designer panel tiers: parameters, subparameters and saved open state.

The rules live in ``docs/PANEL_ORGANIZATION.md``. These tests pin the finished
Container panel: Tier-1 headings, Tier-2 parameter rows, Tier-3 subparameters
and the state that remembers which of them is open.
"""

from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from ui.theme_kit import panel_state  # noqa: E402
from ui.theme_kit.param_group import SUB_INDENT, ParamGroup  # noqa: E402
from ui.theme_kit.property_row import PropertyRow, PropertySection  # noqa: E402

_QAPP = None


@pytest.fixture(scope="module")
def qapp():
    global _QAPP
    _QAPP = QApplication.instance() or QApplication(["test"])
    return _QAPP


@pytest.fixture(autouse=True)
def saved_state(monkeypatch):
    """In-memory settings store, so tests never touch the app database."""
    panel_state.reset_cache()
    store: dict[str, dict[str, bool]] = {}
    monkeypatch.setattr(panel_state, "_read",
                        lambda panel: dict(store.get(panel, {})))
    monkeypatch.setattr(panel_state, "_write",
                        lambda panel, state: store.__setitem__(panel,
                                                               dict(state)))
    yield store
    panel_state.reset_cache()


def _theme(**container):
    values = {
        "id": "main",
        "label": "Main",
        "visible": True,
        "layer": 2,
        "width": "100%",
        "height": 600,
        "border": "none",
        "border_padding": 40,
        "border_radius": 12,
        "blocks": {},
    }
    values.update(container)
    return {"kind": "scripture",
            "canvas": {"width": 1920, "height": 1080},
            "containers": [values]}


def _editor(qapp, theme=None):
    from ui.widgets.theme_designer import ThemePropertyEditor

    editor = ThemePropertyEditor()
    editor.resize(240, 900)
    editor.load_theme(theme if theme is not None else _theme())
    editor._pages.set_value("container")
    editor._on_page("container")
    qapp.processEvents()
    return editor


def _sections(editor):
    return [w for w in editor._host.findChildren(PropertySection)
            if w.parent() is editor._host]


def _groups(editor):
    return {group.state_key: group
            for group in editor._host.findChildren(ParamGroup)}


def _rows(editor):
    return editor._host.findChildren(PropertyRow)


def _row(editor, label, index=0):
    return [row for row in _rows(editor) if row.label() == label][index]


def _sub_row_ids(editor):
    return {id(row) for group in _groups(editor).values()
            for row in group.sub_rows()}


def _inside_heading(row, editor):
    widget = row.parentWidget()
    while widget is not None and widget is not editor:
        if isinstance(widget, PropertySection):
            return True
        widget = widget.parentWidget()
    return False


# ── tier 1: headings ────────────────────────────────────────────────────────
def test_container_page_opens_with_seven_group_headings(qapp):
    editor = _editor(qapp)
    sections = _sections(editor)
    # Shape is gone: Radius shapes the border layer, so it is a Border
    # subparameter now (round 3, decision 2). Position is new in round 4 and
    # sits between Size and Fill.
    assert [section.header._title for section in sections] == [
        "Identity", "Visibility", "Size", "Position", "Fill", "Border",
        "Effects",
    ]
    assert [section.state_key for section in sections] == [
        "identity", "visibility", "size", "position", "fill", "border",
        "effects",
    ]
    assert all(not section.body.isHidden() for section in sections)
    editor.close()


def test_headings_are_collapsible(qapp):
    editor = _editor(qapp)
    size = next(s for s in _sections(editor) if s.state_key == "size")
    assert not size.body.isHidden()
    size.header.toggled_expanded.emit(False)
    assert size.body.isHidden()
    editor.close()


# ── tier 2 / tier 3: parameters and their subparameters ─────────────────────
def test_only_refining_controls_are_nested(qapp):
    editor = _editor(qapp)
    groups = _groups(editor)
    assert set(groups) == {"size.width", "size.height", "border.options"}

    assert groups["size.width"].param().label() == "Width"
    assert [row.label() for row in groups["size.width"].sub_rows()] == [
        "Min", "Max"]
    assert groups["size.height"].param().label() == "Height"
    assert [row.label() for row in groups["size.height"].sub_rows()] == [
        "Min", "Max"]
    assert groups["border.options"].param().label() == "Border"
    assert [row.label() for row in groups["border.options"].sub_rows()] == [
        "Fill", "Pad", "Radius", "Border shadow"]
    editor.close()


def test_parameters_without_subparameters_have_no_arrow(qapp):
    editor = _editor(qapp)
    with_arrow = [row.label() for row in _rows(editor) if row.has_disclosure()]
    assert with_arrow == ["Width", "Height", "Border"]
    # `Label` is gone: it only echoed the container id, and the selector's
    # Rename action owns that now (docs/PANEL_ORGANIZATION.md §3).
    for label in ("Container", "Visible", "Layer", "Opacity",
                  "Overflow", "Radius", "Container bg", "Shadow", "Backdrop"):
        row = _row(editor, label)
        assert not row.has_disclosure()
        # The empty gutter still keeps every parameter label on one grid.
        assert row._disclosure_reserved
    editor.close()


def test_subparameters_are_indented_one_step(qapp):
    editor = _editor(qapp)
    group = _groups(editor)["size.width"]
    assert group.body.layout().contentsMargins().left() == SUB_INDENT
    assert group.body.layout().contentsMargins().right() == 0
    editor.close()


def test_parameter_labels_share_one_grid(qapp):
    editor = _editor(qapp)
    for group in _groups(editor).values():
        group.set_expanded(True)
    editor.show()
    qapp.processEvents()

    sub_ids = _sub_row_ids(editor)
    # Only the rows the operator can see: the Position section swaps its
    # canvas rows for its edge rows, and a hidden row has no geometry.
    visible = [row for row in _rows(editor) if row.isVisibleTo(editor)]
    parameter_x = {
        row._label.mapTo(editor._host, row._label.rect().topLeft()).x()
        for row in visible
        if not row._full_width and id(row) not in sub_ids
    }
    sub_x = {
        row._label.mapTo(editor._host, row._label.rect().topLeft()).x()
        for row in visible
        if not row._full_width and id(row) in sub_ids
    }
    assert len(parameter_x) == 1
    assert len(sub_x) == 1
    assert sub_x.pop() > parameter_x.pop()

    # Every row the page aligned shares one label column, nesting included.
    widths = {row._effective_label_width for row in editor._page_rows
              if not row._full_width}
    assert len(widths) == 1
    editor.close()


# ── open state ─────────────────────────────────────────────────────────────
def test_subparameters_default_collapsed_except_border_options(qapp):
    editor = _editor(qapp)
    groups = _groups(editor)
    assert not groups["size.width"].is_expanded()
    assert not groups["size.height"].is_expanded()
    assert groups["size.width"].body.isHidden()
    assert groups["border.options"].is_expanded()
    assert not groups["border.options"].body.isHidden()
    editor.close()


def test_toggling_subparameters_is_remembered(qapp, saved_state):
    editor = _editor(qapp)
    group = _groups(editor)["size.width"]
    group.set_expanded(True, notify=True)
    assert saved_state["container"]["size.width"] is True

    panel_state.reset_cache()  # prove the value came back from the store
    fresh = _editor(qapp)
    assert _groups(fresh)["size.width"].is_expanded()
    editor.close()
    fresh.close()


def test_toggling_a_heading_is_remembered(qapp, saved_state):
    editor = _editor(qapp)
    section = next(s for s in _sections(editor) if s.state_key == "effects")
    section.header.toggled_expanded.emit(False)
    assert saved_state["container"]["effects"] is False

    panel_state.reset_cache()
    fresh = _editor(qapp)
    reopened = next(s for s in _sections(fresh) if s.state_key == "effects")
    assert reopened.body.isHidden()
    editor.close()
    fresh.close()


def test_open_state_survives_a_page_switch(qapp, saved_state):
    editor = _editor(qapp)
    _groups(editor)["size.height"].set_expanded(True, notify=True)
    editor._pages.set_value("canvas")
    editor._on_page("canvas")
    editor._pages.set_value("container")
    editor._on_page("container")
    qapp.processEvents()
    assert _groups(editor)["size.height"].is_expanded()
    editor.close()


# ── behaviour: nothing lost, nothing re-valued ─────────────────────────────
def test_every_control_is_still_reachable(qapp):
    editor = _editor(qapp)
    # `containers.0.label` is no longer a row: it was a second name for the
    # id. The stored field survives untouched (see
    # test_the_removed_label_row_does_not_touch_the_stored_field).
    assert set(editor.field_paths()) == {
        "containers.0.visible",
        "containers.0.layer",
        "containers.0.opacity",
        "containers.0.width",
        "containers.0.height",
        "containers.0.min_width",
        "containers.0.max_width",
        "containers.0.min_height",
        "containers.0.max_height",
        "containers.0.overflow",
        "containers.0.container_background",
        "containers.0.background",
        "containers.0.border",
        "containers.0.border_padding",
        "containers.0.border_radius",
        "containers.0.border_shadow",
        "containers.0.box_shadow",
        "containers.0.backdrop_filter",
        "containers.0.position.mode",
        "containers.0.position.canvas",
        "containers.0.position.edge",
    }
    editor.close()


def test_size_parameters_are_editable_and_keep_their_limits(qapp):
    editor = _editor(qapp)
    for leaf in ("width", "height", "min_width", "max_width",
                 "min_height", "max_height"):
        assert ("containers", 0, leaf) in editor._field_widgets

    # Min and Max bound each other, but a raised Min moves Max out of its way
    # instead of being clamped back (docs §2, size semantics).
    high = editor._field_widgets[("containers", 0, "max_width")]
    high.set_value("1500px", emit=True)
    low = editor._field_widgets[("containers", 0, "min_width")]
    low.set_value("1800px", emit=True)
    assert editor.get_theme()["containers"][0]["max_width"] == 1800

    editor.set_field("containers.0.width", "50%")
    assert editor.get_theme()["containers"][0]["width"] == "50%"
    editor.close()


def test_nothing_is_orphaned_outside_a_heading(qapp):
    editor = _editor(qapp)
    for row in _rows(editor):
        assert _inside_heading(row, editor), \
            f"{row.label()} is not inside a heading"
    editor.close()


def test_load_and_snapshot_are_byte_identical(qapp):
    theme = _theme()
    editor = _editor(qapp, theme)
    assert json.dumps(editor.get_theme(), sort_keys=True) == \
        json.dumps(theme, sort_keys=True)
    editor.close()


def test_absent_values_still_show_their_semantics(qapp):
    theme = _theme()
    for key in ("opacity", "border_padding", "border_radius"):
        theme["containers"][0].pop(key, None)
    editor = _editor(qapp, theme)
    assert _row(editor, "Opacity").control().value() == 1.0
    assert _row(editor, "Pad").control().value() is None
    assert _row(editor, "Radius").control().value() is None
    assert _row(editor, "Min").control()._edit.placeholderText() == "Unset"
    editor.close()


# ── the three decisions ────────────────────────────────────────────────────
def test_radius_moved_under_border_after_pad(qapp):
    """Radius shapes the border layer, so it belongs to Border (round 3)."""
    editor = _editor(qapp)
    border = next(s for s in _sections(editor) if s.state_key == "border")
    labels = [row.label() for row in border.findChildren(PropertyRow)]
    assert labels == ["Border", "Fill", "Pad", "Radius", "Border shadow"]
    assert "Shape" not in [s.header._title for s in _sections(editor)]
    editor.close()


def test_border_none_never_disables_a_control_that_still_renders(qapp):
    """The border layer always exists; Border = none only drops the stroke."""
    editor = _editor(qapp)
    editor.set_field("containers.0.border", "none")
    for label in ("Fill", "Pad", "Radius", "Border shadow"):
        row = _row(editor, label)
        assert row.disabled_reason() == "", f"{label} carries a reason"
        assert row.control().isEnabled(), f"{label} is disabled"
    editor.close()


def test_old_names_are_gone_and_nested_names_drop_redundancy(qapp):
    editor = _editor(qapp)
    labels = {row.label() for row in _rows(editor)}
    assert {"Min", "Max", "Fill", "Pad"} <= labels
    for old in ("Min width", "Max width", "Min height", "Max height",
                "Border fill", "Border pad"):
        assert old not in labels
    for kept in ("Container bg", "Radius", "Layer", "Visible", "Opacity",
                 "Overflow", "Shadow", "Backdrop", "Border"):
        assert kept in labels
    assert "Label" not in labels
    editor.close()

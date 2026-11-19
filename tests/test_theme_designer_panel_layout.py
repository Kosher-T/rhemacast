"""Theme Designer panel round 2: one grid, stacked controls, size semantics,
container identity.

The rules live in ``docs/PANEL_ORGANIZATION.md``. These tests pin the parts a
refactor could silently break: the three constants are the only geometry
source, a stacked control starts at its label's left edge, Width is preferred
and Min/Max bound it, and a container id can be renamed without leaving a
dangling reference.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from ui.theme_kit import panel_state  # noqa: E402
from ui.theme_kit import panel_layout  # noqa: E402
from ui.theme_kit.panel_layout import (  # noqa: E402
    GUTTER,
    PANEL_PAD,
    TIER_STEP,
    edge,
    label_x,
)
from ui.theme_kit.param_group import SUB_INDENT  # noqa: E402
from ui.theme_kit.property_row import PropertyRow, PropertySection  # noqa: E402
from ui.widgets.theme_designer.document import (  # noqa: E402
    ThemeDocument,
    container_id_from_name,
)

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


# ── fixtures ────────────────────────────────────────────────────────────────
def _theme(**container):
    values = {
        "id": "main",
        "label": "Main",
        "visible": True,
        "layer": 2,
        "width": 600,
        "height": 600,
        "border": "none",
        "blocks": {},
    }
    values.update(container)
    return {"kind": "scripture",
            "canvas": {"width": 1920, "height": 1080},
            "containers": [values]}


def _editor(qapp, theme=None):
    from ui.widgets.theme_designer import ThemePropertyEditor

    editor = ThemePropertyEditor()
    editor.resize(240, 1000)
    editor.load_theme(theme if theme is not None else _theme())
    editor._pages.set_value("container")
    editor._on_page("container")
    editor.show()
    qapp.processEvents()
    return editor


def _rows(editor):
    return editor._host.findChildren(PropertyRow)


def _row(editor, label):
    return next(row for row in _rows(editor) if row.label() == label)


def _x(editor, widget):
    return widget.mapTo(editor, widget.rect().topLeft()).x()


def _sub_rows(editor):
    from ui.theme_kit.param_group import ParamGroup

    return {id(row) for group in editor._host.findChildren(ParamGroup)
            for row in group.sub_rows()}


def _expand_all(editor, qapp):
    """Open every subparameter group so hidden rows have real geometry."""
    from ui.theme_kit.param_group import ParamGroup

    for group in editor._host.findChildren(ParamGroup):
        group.set_expanded(True)
    editor._layout.activate()
    qapp.processEvents()


def _tier_columns(editor):
    """{tier: set of control x} for the rows that keep the inline column."""
    subs = _sub_rows(editor)
    columns: dict[int, set[int]] = {2: set(), 3: set()}
    for row in _rows(editor):
        if row._full_width:
            continue
        tier = 3 if id(row) in subs else 2
        columns[tier].add(_x(editor, row.control()))
    return columns


# ── one grid, defined once ─────────────────────────────────────────────────
def test_the_three_constants_are_the_only_geometry_source(qapp):
    from ui.theme_kit import property_row
    from ui.widgets.theme_designer import property_editor

    assert (PANEL_PAD, TIER_STEP, GUTTER) == (8, 12, 12)
    # Everything that draws the grid reads the same three values.
    assert property_editor.PANEL_PAD == PANEL_PAD
    assert property_row.GUTTER == GUTTER
    assert property_row.TIER_STEP == TIER_STEP
    assert SUB_INDENT == TIER_STEP
    assert panel_layout.edge(1) == PANEL_PAD
    assert panel_layout.label_x(1) == PANEL_PAD + GUTTER


def test_label_x_strictly_increases_with_the_tier():
    positions = [label_x(tier) for tier in (1, 2, 3, 4)]
    assert positions == [20, 32, 44, 56]
    assert all(right - left == TIER_STEP
               for left, right in zip(positions, positions[1:]))
    # The row edge steps by the same amount, so the gutter is constant.
    assert all(edge(tier) + GUTTER == label_x(tier) for tier in (1, 2, 3, 4))


def test_the_measured_columns_match_the_formula(qapp):
    editor = _editor(qapp)
    _expand_all(editor, qapp)
    sections = [w for w in editor._host.findChildren(PropertySection)
                if w.parent() is editor._host]
    assert sections, "the container page must have headings"

    # Tier 1 heading text, Tier 2 parameter label, Tier 3 subparameter label.
    heading_x = {_x(editor, section.header) + GUTTER for section in sections}
    assert heading_x == {label_x(1)}, "heading text must start on the grid"

    subs = _sub_rows(editor)
    parameter_x = {_x(editor, row._label) for row in _rows(editor)
                   if not row._full_width and id(row) not in subs}
    sub_x = {_x(editor, row._label) for row in _rows(editor)
             if not row._full_width and id(row) in subs}
    assert parameter_x == {label_x(2)}
    assert sub_x == {label_x(3)}
    editor.close()


def test_a_tier_three_row_reserves_the_gutter_without_an_arrow(qapp):
    editor = _editor(qapp)
    group = next(group for group in editor._host.findChildren(
        __import__("ui.theme_kit.param_group", fromlist=["ParamGroup"]).
        ParamGroup) if group.state_key == "size.width")
    group.set_expanded(True)
    qapp.processEvents()
    for row in group.sub_rows():
        assert not row.has_disclosure()
        assert row._disclosure_reserved
    editor.close()


# ── stacked controls ───────────────────────────────────────────────────────
def test_stacked_controls_start_at_their_label_left_edge(qapp):
    editor = _editor(qapp)
    stacked = [row for row in _rows(editor) if row._full_width]
    assert stacked, "the container page has full-width controls"
    for row in stacked:
        assert _x(editor, row.control()) == _x(editor, row._label), \
            f"{row.label()} must start under its label"
    editor.close()


def test_the_stacked_set_is_the_wide_controls(qapp):
    editor = _editor(qapp)
    stacked = {row.label() for row in _rows(editor) if row._full_width}
    # Dropdowns, paint boxes and compound editors need the whole width.
    assert stacked == {"Container", "Overflow", "Container bg", "Border",
                       "Fill", "Shadow", "Border shadow", "Backdrop"}
    editor.close()


def test_inline_controls_share_the_value_column_and_step_with_the_tier(qapp):
    editor = _editor(qapp)
    _expand_all(editor, qapp)
    columns = _tier_columns(editor)
    assert len(columns[2]) == 1, f"Tier 2 controls drift: {columns[2]}"
    assert len(columns[3]) == 1, f"Tier 3 controls drift: {columns[3]}"
    (parameter_x,) = columns[2]
    (sub_x,) = columns[3]
    assert sub_x == parameter_x + TIER_STEP
    editor.close()


# ── size semantics ─────────────────────────────────────────────────────────
def _size_row(editor, label):
    return _row(editor, label)


def test_load_marks_a_clamped_preferred_size_without_rewriting_it(qapp):
    editor = _editor(qapp, _theme(width=600, min_width=100, max_width=400))
    assert editor.get_theme()["containers"][0]["width"] == 600
    assert _size_row(editor, "Width").warning() == "Renders as 400px"
    assert _size_row(editor, "Height").warning() == ""
    editor.close()


def test_the_marker_clears_when_the_value_already_fits(qapp):
    editor = _editor(qapp, _theme(width=300, min_width=100, max_width=400))
    assert _size_row(editor, "Width").warning() == ""

    # Raising Min above the preferred size moves the render, not the value.
    editor._field_widgets[("containers", 0, "min_width")].set_value(
        "350px", emit=True)
    assert _size_row(editor, "Width").warning() == "Renders as 350px"
    editor.close()


def test_editing_the_preferred_size_keeps_it_between_min_and_max(qapp):
    editor = _editor(qapp, _theme(width=300, min_width=100, max_width=400))
    width = editor._field_widgets[("containers", 0, "width")]

    width.set_value("900px", emit=True)
    assert editor.get_theme()["containers"][0]["width"] == 400
    assert width.value() == "400px"

    width.set_value("10px", emit=True)
    assert editor.get_theme()["containers"][0]["width"] == 100
    assert width.value() == "100px"
    editor.close()


def test_only_same_unit_values_are_compared(qapp):
    # A percent Max says nothing about a pixel Min.
    editor = _editor(qapp, _theme(width=300, min_width=100, max_width="50%"))
    editor._field_widgets[("containers", 0, "min_width")].set_value(
        "1200px", emit=True)
    assert editor.get_theme()["containers"][0]["max_width"] == "50%"
    assert editor.get_theme()["containers"][0]["min_width"] == 1200
    editor.close()


def test_auto_and_unset_preferred_sizes_are_never_marked(qapp):
    editor = _editor(qapp, _theme(width="auto", max_width=400,
                                  height=None, max_height=400))
    assert _size_row(editor, "Width").warning() == ""
    assert _size_row(editor, "Height").warning() == ""
    editor.close()


def test_an_unset_max_does_not_bound_the_preferred_size(qapp):
    editor = _editor(qapp, _theme(width=900, min_width=100))
    assert _size_row(editor, "Width").warning() == ""
    width = editor._field_widgets[("containers", 0, "width")]
    width.set_value("1200px", emit=True)
    assert editor.get_theme()["containers"][0]["width"] == 1200
    editor.close()


# ── identity: the removed Label row ────────────────────────────────────────
def test_the_removed_label_row_does_not_touch_the_stored_field(qapp):
    editor = _editor(qapp, _theme(label="Hero banner"))
    labels = {row.label() for row in _rows(editor)}
    assert "Label" not in labels
    assert editor.get_theme()["containers"][0]["label"] == "Hero banner"

    editor._identity.rename_requested.emit("hero")
    theme = editor.get_theme()["containers"][0]
    assert theme["id"] == "hero"
    # A custom label is the operator's, not a second copy of the id.
    assert theme["label"] == "Hero banner"
    editor.close()


def test_rename_updates_a_label_that_only_echoed_the_id(qapp):
    editor = _editor(qapp, _theme(label="main"))
    editor._identity.rename_requested.emit("hero")
    assert editor.get_theme()["containers"][0]["label"] == "hero"
    editor.close()


def test_rename_rewrites_every_nested_reference(qapp):
    theme = _theme()
    theme["slide"] = {"container": "main"}
    theme["presentation"] = {"targets": [{"container_id": "main"},
                                         {"containerId": "main"}],
                             "deep": [{"container": "main"}]}
    document = ThemeDocument(theme)
    emissions = []
    document.changed.connect(lambda paths, source: emissions.append(paths))

    renamed = document.rename_container("main", "hero")

    assert renamed == "hero"
    assert emissions == [(("containers", 0),)]
    assert document.revision == 1
    snapshot = document.snapshot()
    assert snapshot["containers"][0]["id"] == "hero"
    assert snapshot["slide"]["container"] == "hero"
    assert snapshot["presentation"]["targets"] == [{"container_id": "hero"},
                                                   {"containerId": "hero"}]
    assert snapshot["presentation"]["deep"] == [{"container": "hero"}]


def test_duplicate_and_invalid_ids_are_refused(qapp):
    theme = _theme()
    theme["containers"].append({"id": "second", "label": "Second",
                                "blocks": {}})
    document = ThemeDocument(theme)

    ok, reason = document.validate_container_id("second")
    assert not ok and "already used" in reason
    ok, reason = document.validate_container_id("")
    assert not ok and reason
    ok, reason = document.validate_container_id("Not An Id")
    assert not ok and "lowercase" in reason
    # The id being edited is not its own duplicate.
    assert document.validate_container_id("main", ignore="main")[0]

    assert document.rename_container("main", "second") is None
    assert document.rename_container("main", "Bad Id") is None
    assert [c["id"] for c in document.containers()] == ["main", "second"]


def test_the_editor_reports_a_refused_rename_inline(qapp):
    editor = _editor(qapp)
    editor._identity.rename_requested.emit("Bad Id")

    assert editor.container_id() == "main"
    assert editor._identity._message.isHidden() is False
    assert "lowercase" in editor._identity._message.text()
    # Editing stays open so the operator can correct it.
    assert editor._identity.is_editing() or not editor._identity._message.isHidden()
    editor.close()


def test_a_successful_rename_rebuilds_the_page_and_announces_it(qapp):
    editor = _editor(qapp)
    seen = []
    editor.container_selected.connect(seen.append)

    editor._identity.rename_requested.emit("hero")

    assert editor.container_id() == "hero"
    assert editor._identity.picker.value() == "hero"
    assert seen == ["hero"]
    editor.close()


def test_main_is_not_a_reserved_id(qapp):
    document = ThemeDocument(_theme())
    assert document.rename_container("main", "hero") == "hero"
    assert document.rename_container("hero", "main") == "main"


# ── identity: adding a container by name ───────────────────────────────────
@pytest.mark.parametrize("name,expected", [
    ("Hero Banner", "hero-banner"),
    ("  Lower third  ", "lower-third"),
    ("2 col", "c-2-col"),
    ("Already_snake", "already_snake"),
    ("!!!", ""),
    ("", ""),
    ("A" * 40, "a" * 32),
])
def test_container_id_from_name(name, expected):
    assert container_id_from_name(name) == expected


def test_adding_a_container_takes_the_name_it_was_given():
    document = ThemeDocument(_theme())
    assert document.add_container("Lower third") == "lower-third"
    added = document.containers()[-1]
    assert added["id"] == "lower-third"
    assert added["label"] == "Lower third"
    # Same name twice is refused instead of silently renamed.
    assert document.add_container("Lower third") is None
    assert document.add_container("!!!") is None


def test_the_workspace_asks_before_adding(qapp, monkeypatch):
    from ui.widgets.theme_designer.container_workspace import ContainerWorkspace

    workspace = ContainerWorkspace()
    workspace.load_theme(_theme())
    asked = []

    def fake_get_validated_text(parent, title, label, **kwargs):
        asked.append((title, kwargs.get("placeholder")))
        return "Lower third", True

    monkeypatch.setattr(
        "ui.dialogs.get_validated_text", fake_get_validated_text)
    workspace.prompt_add_container()

    assert asked, "adding must ask for a name first"
    assert workspace.selected_id() == "lower-third"
    assert workspace.theme()["containers"][-1]["label"] == "Lower third"


def test_the_workspace_does_nothing_when_the_prompt_is_cancelled(qapp,
                                                               monkeypatch):
    from ui.widgets.theme_designer.container_workspace import ContainerWorkspace

    workspace = ContainerWorkspace()
    workspace.load_theme(_theme())
    before = workspace.theme()

    monkeypatch.setattr("ui.dialogs.get_validated_text",
                        lambda *a, **k: ("", False))
    workspace.prompt_add_container()

    assert workspace.theme() == before


def test_the_add_reason_explains_a_collision(qapp):
    from ui.widgets.theme_designer.container_workspace import ContainerWorkspace

    workspace = ContainerWorkspace()
    workspace.load_theme(_theme())
    reason = workspace._new_container_reason("Main")
    assert reason, "a duplicate name must be refused"
    assert "main" in reason


# ── the input dialog refuses what the document refuses ─────────────────────
def test_the_validated_dialog_keeps_ok_disabled_while_invalid(qapp):
    from ui.dialogs import ValidatedTextDialog

    def validator(text):
        return "" if text.strip().lower().startswith("h") else "Start with h"

    dialog = ValidatedTextDialog(None, "Add container", "Name",
                                 validator=validator)
    dialog._edit.setText("lower")
    assert dialog.reason() == "Start with h"
    assert not dialog._ok.isEnabled()
    assert not dialog._message.isHidden()

    dialog.accept()
    assert dialog.result() == 0, "accept must not close on an invalid value"

    dialog._edit.setText("hero")
    assert dialog.reason() == ""
    assert dialog._ok.isEnabled()
    dialog.accept()
    assert dialog.result() == 1
    assert dialog.value() == "hero"
    dialog.deleteLater()

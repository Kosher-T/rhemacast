"""M1 reconciliation: inline numeric labels and 240 px animation cards."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtCore import QEvent, QPoint  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QApplication, QHBoxLayout, QLineEdit, QWidget,
)

from ui.theme_kit import (  # noqa: E402
    BorderEditor, IconButton, NumberField, PropertyRow, ShadowEditor,
)
from ui.widgets.theme_designer import container_geometry as geometry  # noqa: E402
from ui.widgets.theme_designer.animation_panel import AnimationPanel  # noqa: E402
from ui.widgets.theme_designer.container_workspace import ContainerWorkspace  # noqa: E402
from ui.widgets.theme_designer.document import ThemeDocument  # noqa: E402
from ui.widgets.theme_designer.param_form import ParamForm  # noqa: E402
from ui.widgets.theme_designer.property_editor import ThemePropertyEditor  # noqa: E402

_QAPP = None


@pytest.fixture(scope="module")
def qapp():
    global _QAPP
    _QAPP = QApplication.instance() or QApplication([])
    return _QAPP


def _show(widget: QWidget, width: int, height: int, qapp) -> QWidget:
    widget.resize(width, height)
    widget.show()
    qapp.processEvents()
    return widget


def _ancestors(widget: QWidget):
    parent = widget.parentWidget()
    while parent is not None:
        yield parent
        parent = parent.parentWidget()


def _assert_inside(field: NumberField, width: int) -> None:
    label = field._inline_label
    assert label is not None and label.isVisible(), field.inline_label()
    assert label.text() == field.inline_label()
    assert label.geometry().left() >= 0
    assert label.geometry().right() < width
    assert field._edit.geometry().right() < width
    assert field._edit.width() >= 24


# ─── NumberField inline label ───────────────────────────────────────────────

def test_inline_label_is_visible_inside_a_240px_field(qapp):
    host = QWidget()
    layout = QHBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    field = NumberField(4, minimum=-500, maximum=500, step=1,
                        label="Shadow spread", inline_label="Spread")
    layout.addWidget(field, 1)
    _show(host, 240, 30, qapp)

    assert field.inline_label() == "Spread"
    assert field.accessibleName() == "Shadow spread"
    _assert_inside(field, 240)
    assert field.width() == 240


def test_a_field_without_an_inline_label_draws_no_label(qapp):
    field = _show(NumberField(4, label="Shadow spread"), 180, 30, qapp)

    assert field.inline_label() == ""
    assert field._inline_label is None
    assert field.findChild(QLineEdit) is not None


def test_a_row_labelled_field_is_not_double_labelled(qapp):
    field = NumberField(4, label="Corner radius")
    row = _show(PropertyRow("Radius", field, label_width=52), 240, 30, qapp)

    assert field.inline_label() == ""
    assert row.label() == "Radius"


# ─── Shadow editor ──────────────────────────────────────────────────────────

def test_shadow_x_y_blur_spread_carry_inline_labels_at_240px(qapp):
    editor = ShadowEditor("0 4px 12px rgba(0, 0, 0, 0.4)")
    _show(editor, 240, 360, qapp)
    row = editor._rows[0]

    expected = {"X": row.x, "Y": row.y, "Blur": row.blur,
                "Spread": row.spread}
    for text, field in expected.items():
        assert field.inline_label() == text
        _assert_inside(field, row.width())
        # The old PropertyRow wrapper is gone: no label column eats width.
        assert field.parent() is row
        assert not any(isinstance(parent, PropertyRow)
                       for parent in _ancestors(field))
        assert field.width() >= 100


def test_multi_layer_shadow_keeps_inline_labels_at_240px(qapp):
    editor = ShadowEditor("0 4px 12px rgba(0, 0, 0, 0.4), "
                          "0 0 2px rgba(255, 255, 255, 0.2)")
    _show(editor, 240, 500, qapp)

    assert len(editor._rows) == 2
    for row in editor._rows:
        for field in (row.x, row.y, row.blur, row.spread):
            _assert_inside(field, row.width())


# ─── Border editor ──────────────────────────────────────────────────────────

def test_border_radius_fields_carry_inline_labels_at_240px(qapp):
    editor = BorderEditor({"width": 2, "style": "solid", "color": "#ffffff",
                           "radius": 8})
    _show(editor, 240, 520, qapp)

    assert editor.radius_field.inline_label() == "Radius"
    _assert_inside(editor.radius_field, editor.width())

    editor._on_side_selected("top")
    qapp.processEvents()
    assert editor.side_radius.inline_label() == "Radius"
    assert editor.side_radius.isVisible()
    _assert_inside(editor.side_radius, editor.width())


# ─── Animation panel at 240 px ──────────────────────────────────────────────

def _theme() -> dict:
    return {
        "schema_version": 2,
        "kind": "scripture",
        "name": "m1",
        "unknown_top": {"keep": True},
        "containers": [{
            "id": "c1",
            "animation": {
                "entry": "fade_up",
                "out": {"type": "fade_in", "duration_ms": 400},
            },
        }],
    }


def _panel(qapp, width: int = 240) -> AnimationPanel:
    panel = AnimationPanel()
    panel.load_theme(_theme())
    _show(panel, width, 1400, qapp)
    for card in panel._cards.values():
        card.set_expanded(True)
    qapp.processEvents()
    return panel


def _bleeding_children(card: QWidget) -> list[tuple[str, int, int]]:
    bad = []
    for child in card.findChildren(QWidget):
        if not child.isVisible() or child.window() is not card.window():
            continue
        top_left = child.mapTo(card, QPoint(0, 0))
        if top_left.x() < -1 or top_left.x() + child.width() > card.width() + 1:
            bad.append((type(child).__name__, top_left.x(), child.width()))
    return bad


def test_animation_cards_fit_a_240px_column(qapp):
    panel = _panel(qapp)

    assert panel._host.width() <= 240
    for phase, card in panel._cards.items():
        assert card.width() <= panel._host.width(), phase
        assert _bleeding_children(card) == [], phase


def test_builtin_animation_copies_into_theme_at_240px(qapp):
    panel = _panel(qapp)
    card = panel.card("entry")
    copy = next(button for button in card.findChildren(IconButton)
                if button.text() == "Copy into theme")
    assert copy.isVisible()
    top_left = copy.mapTo(card, QPoint(0, 0))
    assert top_left.x() + copy.width() <= card.width() + 1

    copy.click()
    qapp.processEvents()
    copied = panel.theme()
    assert copied["animations"]["fade_up"]["type"] == "fade_up"
    assert copied["containers"][0]["animation"]["entry"] == "fade_up"


def test_switching_slot_types_leaves_no_stale_editor_at_240px(qapp):
    panel = _panel(qapp)
    card = panel.card("entry")
    sequence = [
        "fade_up",
        {"type": "typewriter", "duration_ms": 500, "reveal": "char"},
        {"type": "custom", "duration_ms": 500,
         "keyframes": [{"at": 0, "opacity": 0}, {"at": 1, "opacity": 1}]},
        "fade_up",
        {"type": "fade_in", "duration_ms": 400},
        "none",
    ]
    for value in sequence:
        card.set_value(value)
        card.changed.emit(card.value())
        qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qapp.processEvents()
        card = panel.card("entry")
        assert len(card.findChildren(ParamForm)) <= 1
        assert len([form for form in card.findChildren(ParamForm)
                    if form.isVisible()]) <= 1
        assert _bleeding_children(card) == []


# ─── Single-owner document (panels request edits, never merge copies) ───────


def _animated_document() -> dict:
    return {
        "schema_version": 2,
        "kind": "scripture",
        "name": "m1",
        "unknown_top": {"keep": True},
        "canvas": {"width": 1920, "height": 1080},
        "animations": {"fade_up": {"type": "fade_up", "duration_ms": 700}},
        "containers": [{
            "id": "main",
            "layer": 0,
            "animation": {"out": {"type": "fade_in", "duration_ms": 400}},
            "blocks": {"text": {"size": "44px"}},
        }],
    }


def test_properties_and_animation_views_share_one_document(qapp):
    """A border edit and an animation edit survive without a merge step."""
    document = ThemeDocument(_animated_document())
    properties = ThemePropertyEditor()
    animations = AnimationPanel()
    properties.bind_document(document)
    animations.bind_document(document)

    properties.set_field("containers.0.border.radius", 8)
    animations._write_slot("entry", "fade_up")

    snapshot = document.snapshot()
    assert snapshot["containers"][0]["border"]["radius"] == 8
    assert snapshot["containers"][0]["animation"]["entry"] == "fade_up"
    # Both views render the one document, including the other panel's edit.
    assert properties.get_theme()["containers"][0]["animation"]["entry"] == (
        "fade_up")
    assert animations.theme()["containers"][0]["border"]["radius"] == 8
    assert snapshot["unknown_top"] == {"keep": True}


def test_an_animation_edit_does_not_revert_workspace_geometry(qapp):
    """Workspace geometry and animation slots write to the same document."""
    document = ThemeDocument(_animated_document())
    workspace = ContainerWorkspace()
    animations = AnimationPanel()
    workspace.bind_document(document, "main")
    animations.bind_document(document)

    workspace._write("position.x", 120)
    animations._write_slot("entry",
                           {"type": "fade_up", "duration_ms": 500})

    snapshot = document.snapshot()
    assert snapshot["containers"][0]["position"]["x"] == 120
    assert snapshot["containers"][0]["animation"]["entry"][
        "duration_ms"] == 500
    assert workspace.theme()["containers"][0]["animation"]["entry"][
        "duration_ms"] == 500


def test_a_removed_animation_library_does_not_leave_a_stale_key():
    document = ThemeDocument(_animated_document())
    before = document.snapshot()
    assert document.set(("canvas", "background"), None) is False
    assert document.snapshot() == before

    document.set(("animations",), None)
    document.set(("containers", 0, "animation"), None)

    snapshot = document.snapshot()
    assert "animations" not in snapshot
    assert "animation" not in snapshot["containers"][0]


def test_containers_are_matched_by_id_not_index():
    document = ThemeDocument({
        "containers": [
            {"id": "second", "layer": 1},
            {"id": "first", "layer": 0},
        ],
    })

    assert document.container_index("first") == 1
    selected = document.delete_container("second")

    assert selected == "first"
    assert [c["id"] for c in document.snapshot()["containers"]] == ["first"]
    assert document.container("second") is None


def test_canvas_drag_preview_does_not_write_the_document(qapp):
    document = ThemeDocument(_animated_document())
    workspace = ContainerWorkspace()
    workspace.bind_document(document, "main")
    previews: list[dict] = []
    workspace.preview_changed.connect(previews.append)
    before = document.snapshot()
    container = document.get(("containers", 0))
    rect = geometry.container_rect(container, (1920.0, 1080.0))
    moved = dict(rect, x=rect["x"] + 24)

    workspace._on_canvas_preview("main", moved)

    assert document.snapshot() == before
    assert previews
    preview = geometry.container_rect(previews[-1]["containers"][0],
                                      (1920.0, 1080.0))
    assert round(preview["x"]) == round(moved["x"])

"""Stage 4: container canvas workspace, single selection, split editor."""

from __future__ import annotations

import copy
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtCore import QPointF  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from core import theme_schema as schema  # noqa: E402
from ui.theme_kit import ContainerCanvas, PropertyRow, SplitEditor  # noqa: E402
from ui.widgets.theme_designer import container_geometry as geometry  # noqa: E402
from ui.widgets.theme_designer.container_workspace import (  # noqa: E402
    ContainerWorkspace,
)
from ui.widgets.theme_designer.property_editor import ThemePropertyEditor  # noqa: E402

_QAPP = None


@pytest.fixture(scope="module")
def qapp():
    global _QAPP
    _QAPP = QApplication.instance() or QApplication([])
    return _QAPP


def _containers(count: int) -> list[dict]:
    values = []
    for index in range(count):
        anchor = ("top_left", "center", "bottom_right", "left",
                  "top", "right", "bottom", "top_right")[index % 8]
        values.append({
            "id": f"c{index + 1}",
            "label": f"Layer {index + 1}",
            "layer": index * 6,
            "visible": True,
            "position": {"anchor": anchor, "x": index * 12, "y": index * 8,
                         "future_position": {"keep": index}},
            "width": 300 + index * 10,
            "height": 200 + index * 5,
            "unknown_container_key": {"keep": index},
        })
    return values


def _theme(count: int = 2) -> dict:
    containers = _containers(count)
    containers[0].update({
        "blocks": {
            "body": {"padding": 4, "unknown_body_key": "keep"},
            "text": {
                "size": 40,
                "unknown_block_key": {"keep": True},
                "animation": {
                    "entry": "fade_in",
                    "split": {"by": "line", "stagger_ms": 70,
                              "future_split": {"keep": 1}},
                },
            },
            "reference": {"position": "below_verse"},
            "translation": {"position": "right_of_reference"},
            "verse_num": {"visible": True},
        },
    })
    return {
        "schema_version": 2,
        "name": "stage4",
        "label": "Stage 4",
        "kind": "scripture",
        "canvas": {"width": 1920, "height": 1080,
                   "background": "#101010", "fit": "contain"},
        "unknown_theme_key": {"keep": True},
        "containers": containers,
    }


def _workspace(qapp, count=2) -> ContainerWorkspace:
    workspace = ContainerWorkspace()
    workspace.resize(760, 700)
    workspace.load_theme(_theme(count))
    workspace.show()
    qapp.processEvents()
    return workspace


# ── geometry mapping ────────────────────────────────────────────────────────
@pytest.mark.parametrize("anchor", schema.ANCHORS)
def test_anchor_rect_round_trip(anchor):
    container = {
        "id": "c", "position": {"anchor": anchor, "x": 24, "y": -16,
                                "future": "keep"},
        "width": "50%", "height": 240,
    }
    size = (1920.0, 1080.0)
    rect = geometry.container_rect(container, size)
    geometry.apply_rect(container, rect, size)
    again = geometry.container_rect(container, size)
    for key in ("x", "y", "width", "height"):
        assert round(again[key], 2) == round(rect[key], 2), (anchor, key)
    assert container["position"]["future"] == "keep"


def test_fill_ignores_rect_and_auto_uses_canvas_fallback():
    size = (1000.0, 500.0)
    fill = {"position": {"anchor": "fill"}, "width": 12, "height": 12}
    rect = geometry.container_rect(fill, size)
    assert (rect["x"], rect["y"], rect["width"], rect["height"]) == (
        0.0, 0.0, 1000.0, 500.0)
    geometry.apply_rect(fill, rect, size)
    assert fill["width"] == 12 and fill["height"] == 12

    auto = {"position": {"anchor": "center"}, "width": "auto",
            "height": "auto"}
    rect = geometry.container_rect(auto, size)
    assert rect["width"] == 600.0 and rect["height"] == 200.0


def test_percentage_offset_and_size_resolve_against_canvas():
    container = {"position": {"anchor": "top_left", "x": "10%", "y": 20},
                 "width": "25%", "height": "50%"}
    rect = geometry.container_rect(container, (1000.0, 800.0))
    assert rect == {"x": 100.0, "y": 20.0, "width": 250.0,
                    "height": 400.0, "fill": False}


def test_pure_move_keeps_authored_size_forms_and_untouched_offset():
    container = {"position": {"anchor": "top_left", "x": "10%", "y": "25%"},
                 "width": "auto", "height": "50%"}
    size = (1920.0, 1080.0)
    rect = geometry.container_rect(container, size)
    geometry.apply_rect(container, dict(rect, x=rect["x"] + 40), size)
    assert container["width"] == "auto"
    assert container["height"] == "50%"
    assert container["position"]["y"] == "25%"
    assert container["position"]["x"] == 232


def test_pure_vertical_move_keeps_percentage_x_offset():
    container = {"position": {"anchor": "top_left", "x": "10%", "y": 20},
                 "width": 300, "height": 200}
    size = (1000.0, 800.0)
    rect = geometry.container_rect(container, size)
    geometry.apply_rect(container, dict(rect, y=rect["y"] + 40), size)
    assert container["position"]["x"] == "10%"
    assert container["position"]["y"] == 60
    assert container["width"] == 300


def test_resize_rebases_offset_only_when_size_drives_it():
    size = (1000.0, 800.0)
    centered = {"position": {"anchor": "center"}, "width": 600, "height": 400}
    rect = geometry.container_rect(centered, size)
    rect["width"] = 500
    geometry.apply_rect(centered, rect, size)
    again = geometry.container_rect(centered, size)
    assert (again["x"], again["width"]) == (200.0, 500.0)

    cornered = {"position": {"anchor": "top_left", "x": "10%", "y": 24},
                "width": 300, "height": 200}
    rect = geometry.container_rect(cornered, size)
    rect["width"] = 400
    geometry.apply_rect(cornered, rect, size)
    assert cornered["position"]["x"] == "10%"
    assert cornered["position"]["y"] == 24
    assert cornered["width"] == 400


# ── workspace ───────────────────────────────────────────────────────────────
def test_workspace_loads_1_8_16_and_enforces_limit(qapp):
    for count in (1, 8, 16):
        workspace = _workspace(qapp, count)
        assert len(workspace.canvas.surface._boxes) == count
        assert len(workspace.container_ids()) == count
        assert workspace.strip.add_button.isEnabled() == (count < 16)
        workspace.close()

    workspace = _workspace(qapp, 15)
    workspace.add_container()
    assert len(workspace.container_ids()) == 16
    workspace.add_container()
    assert len(workspace.container_ids()) == 16
    workspace.close()


def test_canvas_edit_preserves_unknown_keys_and_reaches_document(qapp):
    workspace = _workspace(qapp)
    emitted: list[dict] = []
    workspace.theme_changed.connect(emitted.append)
    workspace.set_selected("c1")
    workspace.canvas.changed.emit("c1", {
        "x": 40, "y": 30, "width": 500, "height": 260})
    qapp.processEvents()

    container = workspace.theme()["containers"][0]
    assert container["unknown_container_key"] == {"keep": 0}
    assert container["position"]["future_position"] == {"keep": 0}
    assert container["width"] == 500
    assert container["height"] == 260
    rect = geometry.container_rect(container, (1920.0, 1080.0))
    assert (round(rect["x"]), round(rect["y"])) == (40, 30)
    assert emitted and emitted[-1]["unknown_theme_key"] == {"keep": True}
    workspace.close()


def test_save_and_reload_keeps_unknown_keys(tmp_path, monkeypatch):
    from core import theme_loader

    for name in ("_cache", "_paths", "_file_mtimes", "_resolved_cache"):
        monkeypatch.setattr(theme_loader, name, {})
    monkeypatch.setattr(theme_loader, "_THEMES_DIR", tmp_path)
    monkeypatch.setattr(theme_loader, "_loaded", False)

    document = _theme()
    document["name"] = "stage4_roundtrip"
    theme_loader.save_theme("stage4_roundtrip", document)
    assert (tmp_path / "scripture" / "stage4_roundtrip.json").is_file()

    # Drop every cache and re-scan, so this must read the JSON from disk.
    for cache in (theme_loader._cache, theme_loader._paths,
                  theme_loader._file_mtimes, theme_loader._resolved_cache):
        cache.clear()
    theme_loader._loaded = False
    loaded = theme_loader.get_theme("stage4_roundtrip")

    assert loaded["unknown_theme_key"] == {"keep": True}
    assert loaded["containers"][0]["unknown_container_key"] == {"keep": 0}
    assert loaded["containers"][0]["position"]["future_position"] == {
        "keep": 0}
    text = loaded["containers"][0]["blocks"]["text"]
    assert text["unknown_block_key"] == {"keep": True}


def test_exact_fields_show_the_document_unit_after_load(qapp):
    def document(x, width):
        return {
            "schema_version": 2,
            "kind": "scripture",
            "canvas": {"width": 1920, "height": 1080},
            "containers": [{
                "id": "c1", "position": {"anchor": "top_left", "x": x,
                                         "y": 0},
                "width": width, "height": 200,
            }],
        }

    workspace = ContainerWorkspace()
    workspace.resize(760, 700)
    workspace.load_theme(document("10%", "50%"), "c1")
    assert workspace.x_field.value() == "10%"
    assert workspace.width_field.value() == "50%"
    workspace.load_theme(document(24, 300), "c1")
    assert workspace.x_field.value() == "24px"
    assert workspace.width_field.value() == "300px"
    workspace.load_theme(document(24, "auto"), "c1")
    assert workspace.width_field.value() == "auto"
    assert workspace.width_field._unit_button.value() == "auto"
    workspace.close()


def test_canvas_move_keeps_auto_and_percent_forms(qapp):
    theme = _theme(1)
    theme["containers"][0].update({
        "position": {"anchor": "top_left", "x": "10%", "y": 20,
                     "future_position": "keep"},
        "width": "auto", "height": "50%",
    })
    workspace = ContainerWorkspace()
    workspace.resize(760, 700)
    workspace.load_theme(theme)
    workspace.show()
    qapp.processEvents()
    rect = geometry.container_rect(theme["containers"][0], (1920.0, 1080.0))
    workspace.canvas.changed.emit("c1", dict(rect, x=rect["x"] + 16))
    qapp.processEvents()
    container = workspace.theme()["containers"][0]
    assert container["width"] == "auto"
    assert container["height"] == "50%"
    assert container["position"]["y"] == 20
    assert container["position"]["x"] == round(rect["x"] + 16)
    assert container["position"]["future_position"] == "keep"
    workspace.close()


def test_selection_is_shared_and_fields_follow_it(qapp):
    workspace = _workspace(qapp)
    seen: list[str] = []
    workspace.container_selected.connect(seen.append)
    workspace.set_selected("c2", emit=True)
    assert seen == ["c2"]
    assert workspace.selected_id() == "c2"
    assert workspace.x_field.value() == "12px"
    assert workspace.width_field.value() == "310px"
    assert workspace.strip.selected_id() == "c2"
    assert workspace.canvas.selected_id() == "c2"
    workspace.close()


def test_structural_selection_is_announced(qapp):
    workspace = _workspace(qapp, 2)
    seen: list[str] = []
    workspace.container_selected.connect(seen.append)
    workspace.add_container()
    assert seen[-1] == workspace.selected_id()
    workspace.duplicate_container(workspace.selected_id())
    assert seen[-1] == workspace.selected_id()
    workspace.delete_container(workspace.selected_id())
    assert seen[-1] == workspace.selected_id()


def test_reorder_sets_top_first_layers_and_keeps_ids(qapp):
    workspace = _workspace(qapp, 3)
    workspace._reorder(["c3", "c1", "c2"])
    layers = {c["id"]: c["layer"] for c in workspace.theme()["containers"]}
    assert layers["c3"] > layers["c1"] > layers["c2"]
    assert set(layers) == {"c1", "c2", "c3"}
    workspace.close()


def test_overlap_selects_topmost_and_edge_small_rects_stay(qapp):
    theme = _theme(2)
    theme["containers"][0].update({"position": {"anchor": "top_left",
                                                "x": 0, "y": 0},
                                   "width": 300, "height": 200,
                                   "layer": 10})
    theme["containers"][1].update({"position": {"anchor": "top_left",
                                                "x": 0, "y": 0},
                                   "width": 300, "height": 200,
                                   "layer": 20})
    workspace = ContainerWorkspace()
    workspace.resize(700, 600)
    workspace.load_theme(theme)
    workspace.show()
    qapp.processEvents()
    surface = workspace.canvas.surface
    top = surface._boxes[-1]
    point = surface._box_rect(top).center()
    assert surface._box_at(point).id == "c2"

    workspace.canvas.changed.emit("c2", {
        "x": 0, "y": 0, "width": 12, "height": 12})
    rect = geometry.container_rect(workspace.theme()["containers"][1],
                                   (1920.0, 1080.0))
    assert (rect["x"], rect["y"], rect["width"], rect["height"]) == (
        0.0, 0.0, 12.0, 12.0)
    workspace.close()


def test_duplicate_and_delete_round_trip_unknowns(qapp):
    workspace = _workspace(qapp, 2)
    workspace.duplicate_container("c1")
    ids = workspace.container_ids()
    assert len(ids) == 3 and ids[-1] not in ("c1", "c2")
    duplicate = workspace.theme()["containers"][-1]
    assert duplicate["unknown_container_key"] == {"keep": 0}
    assert duplicate["blocks"]["text"]["unknown_block_key"] == {"keep": True}
    workspace.delete_container(ids[-1])
    assert len(workspace.container_ids()) == 2
    workspace.close()


# ── split editor ────────────────────────────────────────────────────────────
def _property(qapp, block="text"):
    editor = ThemePropertyEditor()
    editor.resize(260, 800)
    editor.load_theme(_theme())
    editor.show()
    editor._pages.set_value("blocks", emit=True)
    editor._on_block(block)
    qapp.processEvents()
    return editor


def test_absent_float_rows_show_schema_defaults(qapp):
    editor = _property(qapp, "text")
    rows = {row._label_text: row.control()
            for row in editor.findChildren(PropertyRow)}
    assert rows["Opacity"].value() == 1.0
    assert rows["Line height"].value() == 1.2
    editor.close()


def test_split_editor_only_mounts_for_text_blocks(qapp):
    for block in ("text", "reference", "translation"):
        editor = _property(qapp, block)
        assert editor.findChildren(SplitEditor)
        editor.close()
    for block in ("body", "verse_num"):
        editor = _property(qapp, block)
        assert not editor.findChildren(SplitEditor)
        editor.close()


def test_split_write_preserves_entry_and_unknown_keys(qapp):
    editor = _property(qapp, "text")
    split = editor.findChild(SplitEditor)
    assert split.value()["by"] == "line"
    split.enabled_switch.set_value(True)
    split._on_enabled(True)
    split._set_key("by", "word")
    qapp.processEvents()

    block = editor.get_theme()["containers"][0]["blocks"]["text"]
    assert block["unknown_block_key"] == {"keep": True}
    animation = block["animation"]
    assert animation["entry"] == "fade_in"
    assert animation["split"]["by"] == "word"
    assert animation["split"]["future_split"] == {"keep": 1}
    editor.close()


def test_split_disable_removes_only_split(qapp):
    editor = _property(qapp, "text")
    split = editor.findChild(SplitEditor)
    split.enabled_switch.set_value(False)
    split._on_enabled(False)
    qapp.processEvents()
    animation = editor.get_theme()["containers"][0]["blocks"]["text"][
        "animation"]
    assert "split" not in animation
    assert animation["entry"] == "fade_in"
    editor.close()


def test_property_container_selection_is_a_request_not_a_second_model(qapp):
    editor = _property(qapp, "text")
    seen: list[str] = []
    editor.container_selected.connect(seen.append)
    editor._on_container_pick("c2")
    assert seen == ["c2"]
    assert editor.container_id() == "c1"  # only the tab commits selection
    editor.set_selected_container("c2")
    assert editor.container_id() == "c2"
    assert editor._prefix()[:2] == ("containers", 1)
    editor.close()

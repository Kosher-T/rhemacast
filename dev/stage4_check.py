"""Stage 4 real-display harness (Linux/X11; re-run after UI changes).

Drives the real ThemeDesignerTab with real mouse events and writes screenshots
to dev/stage4_shots/. Not part of the app; safe to delete.
"""
import copy
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from PyQt6 import QtWebEngineWidgets  # noqa: F401,E402

app = QApplication(sys.argv)
from ui.tabs.theme_designer_tab import ThemeDesignerTab  # noqa: E402
from ui.theme_kit import SplitEditor  # noqa: E402

SHOTS = Path("dev/stage4_shots")
BASE = json.loads(Path("themes/scripture/default.json").read_text())


def settle(ms=350):
    app.processEvents()
    QTest.qWait(ms)
    app.processEvents()


def shot(name):
    settle(200)
    path = SHOTS / f"{name}.png"
    ok = tab.grab().save(str(path))
    print("SHOT", path, ok)


def load_document(document, selected=""):
    tab._working_theme = document
    tab._theme_name = document.get("name", "stage4")
    tab._original_theme = copy.deepcopy(document)
    ids = [str(c.get("id", "")) for c in document.get("containers", [])]
    tab._selected_container_id = selected if selected in ids else (
        ids[0] if ids else "")
    tab._properties_panel.load_theme(document, tab._selected_container_id)
    tab._animations_panel.load_theme(document)
    tab._workspace.load_theme(document, tab._selected_container_id)
    tab._apply_to_previews()
    tab._update_json_display()
    settle()


def synthetic(count, overlap=False):
    document = copy.deepcopy(BASE)
    document["name"] = f"stage4_{count}"
    document["label"] = f"Stage 4 — {count} containers"
    first = document["containers"][0]
    containers = []
    anchors = ("top_left", "top_right", "bottom_left", "bottom_right",
               "left", "right", "top", "bottom")
    for index in range(count):
        container = copy.deepcopy(first)
        container["id"] = f"check{index + 1}"
        container["label"] = f"Container {index + 1}"
        container["layer"] = (index + 1) * 4
        if overlap:
            container["position"] = {"anchor": "top_left", "x": 180,
                                     "y": 120}
            container["width"] = 760
            container["height"] = 360
        else:
            anchor = anchors[index % len(anchors)]
            container["position"] = {
                "anchor": anchor, "x": 24, "y": 18}
            container["width"] = 360
            container["height"] = 190
        containers.append(container)
    document["containers"] = containers
    return document


tab = ThemeDesignerTab()
tab.resize(1400, 900)
tab.show()
settle(500)
tab.setFixedSize(1400, 900)
settle(900)
tab._switch_center_view("editor")
tab.set_theme("default_typewriter")
settle(700)
print("tab", tab.width(), tab.height(), "workspace side",
      tab._workspace.width(), "canvas", tab._workspace.canvas.width(),
      tab._workspace.canvas.height())
shot("01_one_container")

load_document(synthetic(8))
shot("02_eight_containers")

load_document(synthetic(16))
print("16 boxes", len(tab._workspace.canvas.surface._boxes),
      "add enabled", tab._workspace.strip.add_button.isEnabled())
shot("03_sixteen_containers")

load_document(synthetic(3, overlap=True))
surface = tab._workspace.canvas.surface
top = surface._boxes[-1]
QTest.mouseClick(surface, Qt.MouseButton.LeftButton,
                 pos=surface._box_rect(top).center().toPoint())
settle()
print("overlap click selected", tab._selected_container_id)
shot("04_overlap_topmost")

load_document(synthetic(2))
workspace = tab._workspace
workspace.set_selected("check1")
settle()
surface = workspace.canvas.surface
box = next(b for b in surface._boxes if b.id == "check1")
rect = surface._box_rect(box)
print("before drag", rect)
QTest.mousePress(surface, Qt.MouseButton.LeftButton,
                 pos=rect.center().toPoint())
QTest.mouseMove(surface, rect.center().toPoint() + QPoint(70, 40))
settle(120)
QTest.mouseRelease(surface, Qt.MouseButton.LeftButton,
                   pos=rect.center().toPoint() + QPoint(70, 40))
settle()
after = next(b for b in surface._boxes if b.id == "check1")
print("after drag", surface._box_rect(after))
print("drag doc position", workspace.theme()["containers"][0]["position"])

rect = surface._box_rect(after)
corner = rect.bottomRight().toPoint() - QPoint(2, 2)
QTest.mousePress(surface, Qt.MouseButton.LeftButton, pos=corner)
QTest.mouseMove(surface, corner + QPoint(45, 30))
settle(120)
QTest.mouseRelease(surface, Qt.MouseButton.LeftButton,
                   pos=corner + QPoint(45, 30))
settle()
resized = next(b for b in surface._boxes if b.id == "check1")
print("after resize", surface._box_rect(resized))
print("resize doc size", workspace.theme()["containers"][0]["width"],
      workspace.theme()["containers"][0]["height"])
shot("05_drag_resize")

# A pure move must keep authored auto/% forms and untouched offsets.
preserved = synthetic(2)
preserved["containers"][0].update({
    "position": {"anchor": "top_left", "x": "10%", "y": "25%",
                 "future_position": {"keep": True}},
    "width": "auto", "height": "50%",
})
load_document(preserved, "check1")
surface = tab._workspace.canvas.surface
box = next(b for b in surface._boxes if b.id == "check1")
rect = surface._box_rect(box)
QTest.mousePress(surface, Qt.MouseButton.LeftButton,
                 pos=rect.center().toPoint())
QTest.mouseMove(surface, rect.center().toPoint() + QPoint(60, 0))
settle(120)
QTest.mouseRelease(surface, Qt.MouseButton.LeftButton,
                   pos=rect.center().toPoint() + QPoint(60, 0))
settle()
kept = tab._workspace.theme()["containers"][0]
print("move preserves", kept["width"], kept["height"],
      kept["position"], "fields", tab._workspace.width_field.value(),
      tab._workspace.height_field.value())
shot("06_move_preserves_forms")

small = synthetic(2)
small["containers"][0].update({
    "position": {"anchor": "top_left", "x": 0, "y": 0},
    "width": 12, "height": 12, "layer": 90})
small["containers"][1].update({
    "position": {"anchor": "bottom_right", "x": 0, "y": 0},
    "width": 180, "height": 100, "layer": 10})
load_document(small, "check1")
shot("07_edge_small")

json_doc = synthetic(2)
json_doc["unknown_stage4_key"] = {"keep": True}
json_doc["containers"][0]["unknown_container_key"] = {"keep": 1}
json_doc["containers"][0].setdefault("blocks", {}).setdefault(
    "text", {})["unknown_block_key"] = {"keep": 2}
json_doc["containers"][0]["blocks"]["text"]["animation"] = {
    "entry": "fade_in",
    "split": {"by": "line", "stagger_ms": 70,
              "future_split": {"keep": 3}},
}
tab._switch_right_tab("json")
tab._json_editor.setPlainText(json.dumps(json_doc, indent=2))
settle(200)
QTest.mouseClick(tab._btn_apply, Qt.MouseButton.LeftButton)
settle(500)
print("json apply boxes", len(tab._workspace.canvas.surface._boxes),
      "unknown", tab._working_theme.get("unknown_stage4_key"),
      tab._working_theme["containers"][0].get("unknown_container_key"))
shot("08_json_apply")

# Split editor: left properties panel, Blocks page, text block, scrolled down.
tab._properties_panel._pages.set_value("blocks", emit=True)
tab._properties_panel._on_block("text")
settle()
split = tab._properties_panel.findChild(SplitEditor)
tab._properties_panel._scroll.verticalScrollBar().setValue(
    tab._properties_panel._scroll.verticalScrollBar().maximum())
settle(300)
print("split mounted", split is not None,
      "split value", split.value() if split else None,
      "scroll max", tab._properties_panel._scroll.verticalScrollBar().maximum())
shot("09_split_editor")

QTest.mouseClick(split.enabled_switch, Qt.MouseButton.LeftButton,
                 pos=split.enabled_switch.rect().center())
settle(400)
off_doc = tab._working_theme["containers"][0]["blocks"]["text"]["animation"]
print("split off", "split" in off_doc, "entry", off_doc.get("entry"))
QTest.mouseClick(split.enabled_switch, Qt.MouseButton.LeftButton,
                 pos=split.enabled_switch.rect().center())
settle(400)
on_doc = tab._working_theme["containers"][0]["blocks"]["text"]["animation"]
print("split on", on_doc.get("split"), "entry", on_doc.get("entry"))
split.by.set_value("word", emit=True)
settle(400)
changed = tab._working_theme["containers"][0]["blocks"]["text"]["animation"]
print("split word", changed["split"], "unknown block",
      tab._working_theme["containers"][0]["blocks"]["text"].get(
          "unknown_block_key"))
tab._properties_panel._scroll.verticalScrollBar().setValue(
    tab._properties_panel._scroll.verticalScrollBar().maximum())
settle(400)
shot("10_split_expanded")

# Exact field edits and structural selection through the real tab.
tab._workspace.x_field.set_value(300, emit=True)
settle(400)
print("field x doc", tab._working_theme["containers"][0]["position"]["x"],
      "box", [(b.id, round(b.x)) for b in
              tab._workspace.canvas.surface._boxes[:2]])
tab._workspace.add_container()
settle(500)
print("add selection tab", tab._selected_container_id,
      "workspace", tab._workspace.selected_id(),
      "properties", tab._properties_panel.container_id())

# Force the left properties column to ~240 px (Stage 2's stated tolerance).
tab._properties_panel.parentWidget().setFixedWidth(240)
tab._workspace.set_selected("check1", emit=True)
settle(400)
tab._properties_panel._pages.set_value("blocks", emit=True)
tab._properties_panel._on_block("text")
settle(300)
split = tab._properties_panel.findChild(SplitEditor)
tab._properties_panel._scroll.verticalScrollBar().setValue(
    tab._properties_panel._scroll.verticalScrollBar().maximum())
settle(400)
visible_splits = [widget for widget in
                  tab._properties_panel.findChildren(SplitEditor)
                  if widget.isVisible()]
print("left panel 240 width", tab._properties_panel.width(),
      "visible split widths", [widget.width() for widget in visible_splits],
      "split value", visible_splits[0].value() if visible_splits else None,
      "hscroll", tab._properties_panel._scroll.horizontalScrollBar().maximum())
from ui.theme_kit import BlockTabBar, FourSideField  # noqa: E402
scroll = tab._properties_panel._scroll
viewport = scroll.viewport()
for bar in tab._properties_panel.findChildren(BlockTabBar):
    if bar.isVisible():
        rows = bar._layout_rows()
        top = bar.mapTo(viewport, QPoint(0, 0)).y()
        next_row = tab._properties_panel._layout.itemAt(1)
        print("block tabs", bar.geometry(), "rows", len(rows),
              "next item", next_row.widget().geometry() if next_row else None,
              "viewport top", top, "bottom", top + bar.height(),
              "viewport h", viewport.height(),
              "scroll", scroll.verticalScrollBar().value(), "/",
              scroll.verticalScrollBar().maximum())
for field in tab._properties_panel.findChildren(FourSideField):
    if not field.isVisible():
        continue
    edit = field._fields["top"]._edit
    print("side placeholder", edit.placeholderText(),
          "text px", edit.fontMetrics().horizontalAdvance(
              edit.placeholderText()), "edit width", edit.width())
probe = viewport.childAt(QPoint(100, 40))
chain = []
while probe is not None and probe is not viewport:
    chain.append(f"{type(probe).__name__}:{probe.geometry().getRect()}")
    probe = probe.parentWidget()
print("widget at viewport (100,40)", chain)
shot("11_split_240")

# Scroll back to the top: the block tabs themselves must be legible at 240 px.
scroll.verticalScrollBar().setValue(0)
settle(300)
top_bar = next((bar for bar in tab._properties_panel.findChildren(BlockTabBar)
                if bar.isVisible()), None)
print("240 top bar rows", len(top_bar._layout_rows()) if top_bar else None,
      "viewport top", (top_bar.mapTo(viewport, QPoint(0, 0)).y()
                       if top_bar else None))
shot("12_blocks_240_top")

print("DONE")
app.quit()

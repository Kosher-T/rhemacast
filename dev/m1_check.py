"""M1 real-display harness (Linux/X11; re-run after UI changes).

Verifies, with real widgets and real mouse events:

* the animation panel's "Copy into theme" for a built-in definition,
* animation cards at a 240 px column, with no stale editors after switching
  slot types,
* inline labels inside shadow X/Y/blur/spread and border radius fields,
* the real toolbar Save / Export / Import once, with unknown keys surviving.

Saves screenshots to dev/m1_shots/. Not part of the app; safe to delete.
"""

import copy
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
from PyQt6.QtCore import QEvent, QPoint, Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from PyQt6 import QtWebEngineWidgets  # noqa: F401,E402

app = QApplication(sys.argv)
from core import theme_loader  # noqa: E402
from ui.theme_kit import BorderField, IconButton, ShadowField  # noqa: E402
from ui.widgets.theme_designer.param_form import ParamForm  # noqa: E402
from ui.tabs.theme_designer_tab import ThemeDesignerTab  # noqa: E402

SHOTS = Path("dev/m1_shots")
SHOTS.mkdir(parents=True, exist_ok=True)
REPO_THEMES = Path("themes")


def settle(ms=300):
    app.processEvents()
    QTest.qWait(ms)
    app.processEvents()


def shot(widget, name):
    settle(150)
    path = SHOTS / f"{name}.png"
    ok = widget.grab().save(str(path))
    print("SHOT", path, ok)
    return ok


def flush_deletes():
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def bleeding_children(card: QWidget):
    bad = []
    for child in card.findChildren(QWidget):
        if not child.isVisible() or child.window() is not card.window():
            continue
        top_left = child.mapTo(card, QPoint(0, 0))
        if top_left.x() < -1 or top_left.x() + child.width() > card.width() + 1:
            bad.append((type(child).__name__, top_left.x(), child.width(),
                        card.width()))
    return bad


def assert_inline(field, editor, text):
    assert field.inline_label() == text, (field.inline_label(), text)
    label = field._inline_label
    assert label is not None and label.isVisible(), text
    origin = label.mapTo(editor, QPoint(0, 0))
    assert origin.x() >= 0, (text, origin.x())
    assert origin.x() + label.width() <= editor.width(), (
        text, origin.x(), label.width(), editor.width())
    edit_origin = field._edit.mapTo(editor, QPoint(0, 0))
    assert edit_origin.x() + field._edit.width() <= editor.width(), (
        text, edit_origin.x(), field._edit.width(), editor.width())
    assert field._edit.width() >= 24, (text, field._edit.width())
    print("INLINE", text, "field", field.width(), "label",
          label.width(), "editor", editor.width())


# ─── Isolated themes dir: Save writes here, never into the repo ─────────────

workdir = Path(tempfile.mkdtemp(prefix="rhemacast-m1-themes-"))
shutil.copytree(REPO_THEMES, workdir / "themes")
themes_dir = workdir / "themes"
base = json.loads((themes_dir / "scripture" / "default.json").read_text())
document = copy.deepcopy(base)
document["name"] = "m1_live"
document["label"] = "M1 live check"
document["unknown_top"] = {"keep": True}
container = document["containers"][0]
container["unknown_container_key"] = {"keep": 1}
container["box_shadow"] = "0 4px 12px rgba(0, 0, 0, 0.4)"
container["border"] = {"width": 2, "style": "solid",
                       "color": "#ffffff", "radius": 8}
container["animation"] = {
    "entry": "fade_up",
    "out": {"type": "fade_in", "duration_ms": 400},
}
container.setdefault("blocks", {}).setdefault("text", {})[
    "unknown_block_key"] = {"keep": 2}
(themes_dir / "scripture" / "m1_live.json").write_text(
    json.dumps(document, indent=4))

theme_loader._THEMES_DIR = themes_dir
theme_loader.reload_themes()
assert theme_loader.get_theme("m1_live") is not None

# ─── Real tab ───────────────────────────────────────────────────────────────

tab = ThemeDesignerTab()
tab.resize(1400, 900)
tab.show()
settle(500)
tab.setFixedSize(1400, 900)
tab.set_theme("m1_live")
settle(700)
print("tab", tab.width(), tab.height(), "theme", tab._theme_name)

# Force the animation column to 240 px (300 px is the shipping width).
right_col = tab._animations_panel.parentWidget().parentWidget()
right_col.setFixedWidth(240)
settle(500)
panel = tab._animations_panel
print("animation panel", panel.width(), "host", panel._host.width())
shot(tab, "01_animation_240")

# Cards fit, every phase.
for card in panel._cards.values():
    card.set_expanded(True)
settle(400)
for phase, card in panel._cards.items():
    bad = bleeding_children(card)
    assert card.width() <= panel._host.width(), (phase, card.width(),
                                                 panel._host.width())
    assert not bad, (phase, bad)
    print("CARD", phase, card.width(), "no overflow")
shot(tab, "02_animation_cards_240")

# Built-in entry -> the real Copy into theme button.
entry = panel.card("entry")
copy_button = next(button for button in entry.findChildren(IconButton)
                   if button.text() == "Copy into theme" and button.isVisible())
assert copy_button.width() > 0
QTest.mouseClick(copy_button, Qt.MouseButton.LeftButton,
                 pos=copy_button.rect().center())
settle(500)
copied = tab._working_theme
assert copied["animations"]["fade_up"]["type"] == "fade_up", copied.keys()
assert copied["containers"][0]["animation"]["entry"] == "fade_up"
print("COPY built-in fade_up ->", copied["containers"][0]["animation"]["entry"])
shot(tab, "03_animation_copy")

# Slot-type switches: one visible editor at most, no stale geometry.
entry = panel.card("entry")
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
    entry.set_value(value)
    entry.changed.emit(entry.value())
    flush_deletes()
    settle(180)
    entry = panel.card("entry")
    forms = entry.findChildren(ParamForm)
    visible = [form for form in forms if form.isVisible()]
    assert len(forms) <= 1, (value, len(forms))
    assert len(visible) <= 1, (value, len(visible))
    assert not bleeding_children(entry), (value, bleeding_children(entry))
    print("SWITCH", str(value)[:48], "forms", len(forms),
          "visible", len(visible))
shot(tab, "04_animation_switches")
print("AFTER SWITCHES animations", list(
    (tab._working_theme.get("animations") or {}).keys()))
print("AFTER SWITCHES panel animations", list(
    (panel.theme().get("animations") or {}).keys()))

# ─── Shadow inline labels in the real container page ────────────────────────

props = tab._properties_panel
props._pages.set_value("container", emit=True)
settle(400)
shadow = next(widget for widget in props.findChildren(ShadowField)
              if widget.isVisible())
props._scroll.ensureWidgetVisible(shadow)
settle(300)
QTest.mouseClick(shadow, Qt.MouseButton.LeftButton,
                 pos=shadow.rect().center())
settle(500)
popover = shadow._popover
assert popover is not None and popover.isVisible(), "shadow popover"
popover.setFixedWidth(240)
popover.resize(240, 460)
settle(400)
editor = popover.editor
assert editor.width() <= 240, editor.width()
row = editor._rows[0]
for text, field in (("X", row.x), ("Y", row.y),
                    ("Blur", row.blur), ("Spread", row.spread)):
    assert_inline(field, editor, text)
print("SHADOW editor", editor.width(), "popover", popover.width())
print("AFTER SHADOW animations", list(
    (tab._working_theme.get("animations") or {}).keys()))
print("AFTER SHADOW props animations", list(
    (props.get_theme().get("animations") or {}).keys()))
shot(popover, "05_shadow_inline_240")
popover.close()
settle(300)

# ─── Border radius inline labels ────────────────────────────────────────────

border = next(widget for widget in props.findChildren(BorderField)
              if widget.isVisible())
props._scroll.ensureWidgetVisible(border)
settle(300)
QTest.mouseClick(border, Qt.MouseButton.LeftButton,
                 pos=border.rect().center())
settle(500)
popover = border._popover
assert popover is not None and popover.isVisible(), "border popover"
popover.setFixedWidth(240)
popover.resize(240, 460)
settle(400)
editor = popover.editor
assert editor.width() <= 240, editor.width()
assert not hasattr(editor, "radius_field"), "radius lives under Border only"
editor._on_side_selected("top")
settle(300)
assert not hasattr(editor, "side_radius")
print("BORDER editor", editor.width(), "popover", popover.width())
print("AFTER BORDER animations", list(
    (tab._working_theme.get("animations") or {}).keys()))
print("AFTER BORDER props animations", list(
    (props.get_theme().get("animations") or {}).keys()))
# The stale properties document must not have reverted the slot the
# animation panel last wrote (entry was set to "none" in the switch run),
# nor the inline "out" definition.
animation_state = tab._working_theme["containers"][0].get("animation") or {}
assert "entry" not in animation_state, animation_state
assert animation_state.get("out", {}).get("type") == "fade_in", animation_state
print("AFTER BORDER slots", animation_state)
shot(popover, "06_border_inline_240")
popover.close()
settle(300)

# ─── Real Save / Export / Import ───────────────────────────────────────────

saved_path = Path(theme_loader._paths["m1_live"])
assert themes_dir in saved_path.parents, saved_path
print("BEFORE SAVE animations", list(
    (tab._working_theme.get("animations") or {}).keys()))
print("BEFORE SAVE props animations", list(
    (tab._properties_panel.get_theme().get("animations") or {}).keys()))

QTest.mouseClick(tab._btn_save, Qt.MouseButton.LeftButton,
                 pos=tab._btn_save.rect().center())
settle(400)
assert not tab.is_dirty(), "Save left the tab dirty"
assert saved_path.exists(), saved_path

# Cold reload: drop every cache and read the file the button wrote.
theme_loader.reload_themes()
saved = json.loads(saved_path.read_text())
assert saved["unknown_top"] == {"keep": True}, saved.get("unknown_top")
assert saved["containers"][0]["unknown_container_key"] == {"keep": 1}
assert saved["containers"][0]["blocks"]["text"]["unknown_block_key"] == {
    "keep": 2}
assert saved["animations"]["fade_up"]["type"] == "fade_up"
print("SAVE", saved_path, "unknown keys survived", saved["name"])

QTest.mouseClick(tab._btn_export, Qt.MouseButton.LeftButton,
                 pos=tab._btn_export.rect().center())
settle(300)
exported_text = QApplication.clipboard().text()
exported = json.loads(exported_text)
assert exported["unknown_top"] == {"keep": True}
assert exported["containers"][0]["unknown_container_key"] == {"keep": 1}
assert exported["containers"][0]["blocks"]["text"]["unknown_block_key"] == {
    "keep": 2}
print("EXPORT", len(exported_text), "bytes; unknown keys present")

imported = copy.deepcopy(exported)
imported["unknown_imported"] = {"keep": 3}
imported["containers"][0]["unknown_container_key"] = {"keep": 4}
QApplication.clipboard().setText(json.dumps(imported, indent=4))
settle(200)
QTest.mouseClick(tab._btn_import, Qt.MouseButton.LeftButton,
                 pos=tab._btn_import.rect().center())
settle(500)
assert tab._working_theme["unknown_imported"] == {"keep": 3}
assert tab._working_theme["unknown_top"] == {"keep": True}
assert tab._working_theme["containers"][0]["unknown_container_key"] == {
    "keep": 4}
assert tab._working_theme["containers"][0]["blocks"]["text"][
    "unknown_block_key"] == {"keep": 2}
print("IMPORT unknown keys", tab._working_theme["unknown_imported"],
      tab._working_theme["containers"][0]["unknown_container_key"])

tab._switch_right_tab("json")
settle(400)
shot(tab, "07_toolbar_import")

print("M1 CHECK PASS")
app.quit()

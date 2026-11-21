"""Container panel, round 3: live controls, Radius under Border, shadows, Backdrop.

The Container panel used to disable Border ▸ Fill / Pad whenever Border was
``none`` (docs/PANEL_ORGANIZATION.md decision 2 in round 2). That gate was
wrong: the border layer always exists, so Fill, Pad and Radius still change the
render when no outline is stroked. These tests drive real mouse sequences on
those rows and pin the corrected model:

* a control that still changes the render is never disabled;
* Radius is a Tier-3 subparameter of Border, after Pad;
* exactly one of the two shadows is painted, mirroring which row is visible;
* the border shadow paints on the canvas and is not clipped by the container;
* Backdrop is edited as a blur radius in px while the stored value stays valid.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QMouseEvent  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

from ui.theme_kit import panel_state  # noqa: E402
from ui.theme_kit.border_editor import BorderField  # noqa: E402
from ui.theme_kit.param_group import ParamGroup  # noqa: E402
from ui.theme_kit.property_row import PropertyRow, PropertySection  # noqa: E402

_QAPP = None

ROOT = Path(__file__).resolve().parents[1]
CHROME = (shutil.which("google-chrome-stable")
          or shutil.which("google-chrome")
          or shutil.which("chromium")
          or shutil.which("chromium-browser"))
RENDERERS = ["display/display.js", "ui/widgets/display_view.py"]


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


# ─── fixtures ───────────────────────────────────────────────────────────────

def _theme(**container):
    values = {
        "id": "main",
        "label": "Main",
        "visible": True,
        "layer": 2,
        "width": "100%",
        "height": 600,
        "container_background": "transparent",
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
    editor.show()
    qapp.processEvents()
    return editor


def _rows(editor):
    return editor._host.findChildren(PropertyRow)


def _row(editor, label, index=0):
    return [row for row in _rows(editor) if row.label() == label][index]


def _sections(editor):
    return [w for w in editor._host.findChildren(PropertySection)
            if w.parent() is editor._host]


def _groups(editor):
    return {group.state_key: group for group in editor._host.findChildren(
        ParamGroup)}


def _send_move(widget, pos: QPoint) -> None:
    event = QMouseEvent(
        QEvent.Type.MouseMove, QPointF(pos),
        QPointF(widget.mapToGlobal(pos)),
        Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, event)


def _drag_label(qapp, row: PropertyRow, dx: int = 24) -> None:
    """One real press → move → release scrub on a row's label."""
    label = row._label
    start = QPoint(4, max(1, label.height() // 2))
    QTest.mousePress(label, Qt.MouseButton.LeftButton, pos=start)
    qapp.processEvents()
    _send_move(label, start + QPoint(dx, 0))
    qapp.processEvents()
    QTest.mouseRelease(label, Qt.MouseButton.LeftButton,
                       pos=start + QPoint(dx, 0))
    qapp.processEvents()


def _state(row: PropertyRow) -> str:
    control = row.control()
    grabber = QWidget.mouseGrabber()
    return (f"label={row.label()!r} enabled={control.isEnabled()} "
            f"grabber={'self' if grabber is control else grabber} "
            f"control={id(control)} value={control.value()!r}")


# ─── 1. dead Pad / Fill controls: the mouse sequence ────────────────────────

@pytest.mark.parametrize("label", ["Pad", "Radius"])
def test_pad_and_radius_scrub_three_times_with_border_none(qapp, label,
                                                           capsys):
    """Three consecutive scrubs commit, stay enabled and keep the same widget.

    Root cause pinned by this test: with Border = None the border gate
    (``_refresh_container_border_state``) called ``set_disabled_reason`` on
    Fill/Pad, which disables the mounted control after the first commit while
    the label keeps its scrub cursor — a drag on an enabled-looking label that
    silently returns early (``_begin_label_scrub`` refuses a disabled control).
    """
    editor = _editor(qapp, _theme(border="none"))
    row = _row(editor, label)
    control = row.control()
    identity = id(control)
    seen = []
    for _ in range(3):
        _drag_label(qapp, row)
        with capsys.disabled():
            print(_state(row))
        seen.append(editor.get_theme()["containers"][0].get(
            "border_padding" if label == "Pad" else "border_radius"))
        assert row.control().isEnabled(), f"{label} was disabled after a commit"
        assert id(row.control()) == identity, (
            f"{label} was rebuilt mid-sequence; the live widget was replaced")
        assert QWidget.mouseGrabber() is None, "scrub left a mouse grab behind"
    numbers = [float(str(value).rstrip("px")) for value in seen]
    assert all(n != 0 for n in numbers)
    assert numbers[1] > numbers[0] and numbers[2] > numbers[1]
    editor.close()


def test_fill_edits_three_times_with_border_none(qapp, capsys):
    """Fill is a paint field (no scrub handle): press it, commit, three times."""
    editor = _editor(qapp, _theme(border="none"))
    row = _row(editor, "Fill")
    control = row.control()
    identity = id(control)
    values = []
    for index in range(3):
        assert control.isEnabled(), "Fill was disabled with Border = none"
        QTest.mousePress(control, Qt.MouseButton.LeftButton,
                         pos=QPoint(6, control.height() // 2))
        popover = control._popover
        assert popover is not None and popover.isVisible(), (
            "pressing Fill did not open its editor")
        popover.editor.committed.emit(f"#8b5cf{index}")
        popover.close()  # dismiss, then press again for the next round
        qapp.processEvents()
        with capsys.disabled():
            print(_state(row))
        values.append(editor.get_theme()["containers"][0].get("background"))
        assert row.control().isEnabled(), "Fill was disabled after a commit"
        assert id(row.control()) == identity
    assert values == ["#8b5cf0", "#8b5cf1", "#8b5cf2"]
    editor.close()


def test_border_none_never_disables_border_subparameters(qapp):
    """A control that still changes the render is never disabled."""
    editor = _editor(qapp, _theme(border="none"))
    for label in ("Fill", "Pad", "Radius", "Border shadow"):
        row = _row(editor, label)
        assert row.control().isEnabled(), f"{label} is disabled with Border=none"
        assert row.disabled_reason() == ""
    editor.close()


# ─── 2. Radius moves under Border ───────────────────────────────────────────

def test_radius_is_a_border_subparameter_after_pad(qapp):
    editor = _editor(qapp)
    headings = [section.header._title for section in _sections(editor)]
    assert "Shape" not in headings
    assert headings == ["Identity", "Visibility", "Size", "Position", "Fill",
                        "Border", "Effects"]
    assert [row.label() for row in _groups(editor)["border.options"].sub_rows()] \
        == ["Fill", "Pad", "Radius", "Border shadow"]
    editor.close()


def test_radius_keeps_its_path_value_and_px_unit(qapp):
    editor = _editor(qapp, _theme(border_radius=14))
    row = _row(editor, "Radius")
    control = row.control()
    assert control.unit() == "px"
    assert control.value() == "14px"
    assert ("containers", 0, "border_radius") in editor._field_widgets
    control.set_value("22px", emit=True)
    assert editor.get_theme()["containers"][0]["border_radius"] == 22
    editor.close()


def test_radius_mapping_old_to_new_has_no_stored_change(qapp):
    """Radius moved between headings only: the stored key is untouched."""
    theme = _theme(border_radius=18)
    editor = _editor(qapp, theme)
    assert json.dumps(editor.get_theme(), sort_keys=True) == \
        json.dumps(theme, sort_keys=True)
    editor.close()


# ─── 1b. Border dropdown commits what was chosen ────────────────────────────

def test_border_choice_commits_and_stays_in_the_dropdown(qapp):
    """Choosing Custom writes the border and keeps the surface open.

    Root cause: the popover emitted ``committed`` and then closed, and
    ``closeEvent`` emitted ``cancelled``, which rewound the field to the value
    it opened with and previewed that back into the document — the row showed
    "None" again. The switch itself was a preview, so turning the border off
    was undone by the dismiss as well.
    """
    field = BorderField("none")
    field.resize(180, 28)
    field.show()
    seen = []
    field.changed.connect(seen.append)
    field._open_popover()
    popover = field._popover
    assert popover is not None
    # No event-loop turn while the popup is open: the offscreen platform
    # deactivates a Qt.Popup on the first pass, which is not this behaviour.
    popover.editor.mode.set_value("custom", emit=True)
    assert seen, "choosing Custom did not commit a border"
    committed = seen[-1]
    assert isinstance(committed, dict), committed
    assert field.value() == committed, "the field did not adopt the commit"
    # The commit writes through and leaves the surface open for the rest of
    # the fields; dismissing it afterwards must not be a cancel.
    assert popover.isVisible() and popover._committed

    popover.editor.width_field.set_value("3", emit=True)
    assert seen[-1]["width"] == 3, seen[-1]
    assert popover.isVisible(), "the width edit closed the surface"
    popover.close()
    assert field.value() == seen[-1], "closing reverted the commit to None"
    assert "none" not in [value for value in seen]
    field.close()
    field.deleteLater()


def test_border_tooltip_does_not_cover_its_own_control(qapp):
    from ui.theme_kit.popup import tooltip_position

    anchor = (0, 400, 224, 28)  # a full-width row in a 240 px panel
    position = tooltip_position(anchor, (270, 54), (0, 0, 1920, 1080))
    tip = (position.x(), position.y(), 270, 54)
    assert not _intersects(tip, anchor)
    # Above the anchor when the panel sits near the bottom of the screen.
    low = (0, 1000, 224, 28)
    above = tooltip_position(low, (270, 54), (0, 0, 1920, 1080))
    assert not _intersects((above.x(), above.y(), 270, 54), low)


def _intersects(a, b) -> bool:
    return not (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0]
                or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1])


# ─── 3. shadows follow what is visible ──────────────────────────────────────

def test_shadow_rows_swap_with_the_container_background(qapp):
    editor = _editor(qapp, _theme(box_shadow="0 8px 24px #00000080",
                                  border_shadow="0 10px 30px #00000080"))
    container_row = _row(editor, "Shadow")
    border_row = _row(editor, "Border shadow")

    def visible(row):
        return not row.isHidden()

    assert not visible(container_row), "container shadow shown with bg none"
    assert visible(border_row)

    editor.set_field("containers.0.container_background", "#112233")
    assert visible(container_row)
    assert not visible(border_row), "border shadow shown with a container bg"

    editor.set_field("containers.0.container_background", "none")
    assert not visible(container_row)
    assert visible(border_row)
    # Hiding keeps the stored value.
    stored = editor.get_theme()["containers"][0]
    assert stored["box_shadow"] == "0 8px 24px #00000080"
    assert stored["border_shadow"] == "0 10px 30px #00000080"
    editor.close()


def test_border_shadow_round_trips_and_defaults_to_none(qapp):
    theme = _theme()
    theme["containers"][0].pop("border_shadow", None)
    editor = _editor(qapp, theme)
    assert _row(editor, "Border shadow").control().value() == "none"
    assert json.dumps(editor.get_theme(), sort_keys=True) == \
        json.dumps(theme, sort_keys=True)
    editor.close()


# ─── 4. Backdrop ────────────────────────────────────────────────────────────

def test_backdrop_edits_as_a_blur_radius_and_stays_valid(qapp):
    editor = _editor(qapp, _theme(backdrop_filter="blur(12px) saturate(1.2)"))
    row = _row(editor, "Backdrop")
    control = row.control()
    assert control.blur() == 12
    assert "behind this container" in control.toolTip().lower() or \
        "behind this container" in control._hint.lower()

    control.set_blur(20, emit=True)
    qapp.processEvents()
    stored = editor.get_theme()["containers"][0]["backdrop_filter"]
    assert stored == "blur(20px) saturate(1.2)"

    from core import theme_schema
    _, report = theme_schema.normalize_theme(editor.get_theme(),
                                             kind="scripture")
    messages = report.warnings + report.errors + report.notes
    assert not [item for item in messages if "backdrop" in item]

    # Clearing the blur keeps the other functions rather than dropping them.
    control.set_blur(None, emit=True)
    qapp.processEvents()
    assert editor.get_theme()["containers"][0]["backdrop_filter"] == \
        "saturate(1.2)"
    editor.close()


def test_backdrop_clears_to_none(qapp):
    editor = _editor(qapp, _theme(backdrop_filter="blur(9px)"))
    control = _row(editor, "Backdrop").control()
    control.set_blur(None, emit=True)
    qapp.processEvents()
    assert editor.get_theme()["containers"][0]["backdrop_filter"] in (
        "none", "off")
    editor.close()


def test_backdrop_accepts_a_typed_blur(qapp):
    editor = _editor(qapp, _theme(backdrop_filter="none"))
    field = _row(editor, "Backdrop").control()._blur
    QTest.mouseDClick(field._edit, Qt.MouseButton.LeftButton,
                      pos=QPoint(8, field._edit.height() // 2))
    qapp.processEvents()
    QTest.keyClicks(field._edit, "25")
    QTest.keyPress(field._edit, Qt.Key.Key_Return)
    qapp.processEvents()
    assert editor.get_theme()["containers"][0]["backdrop_filter"] == \
        "blur(25px)"
    editor.close()


# ─── renderer ───────────────────────────────────────────────────────────────

SHADOW_DRIVER = r"""
window.__log = [];
window.__errs = [];
window.addEventListener("error", function (e) {
  window.__errs.push(String(e.message) + " @" + e.lineno + ":" + e.colno);
});
window.__wait = function (ms) { return new Promise(r => setTimeout(r, ms)); };
window.__payload = function (p) {
  return {action: "display", theme_data: window.__theme, ...p};
};
window.__snap = function (label) {
  const ct = document.getElementById("container");
  const layer = ct ? ct.querySelector(".rc-border-layer") : null;
  const hosts = Array.prototype.map.call(
    document.querySelectorAll(".rc-border-shadow"),
    function (el) {
      const box = el.getBoundingClientRect();
      return {
        shadow: getComputedStyle(el).boxShadow,
        radius: getComputedStyle(el).borderRadius,
        parent: el.parentElement ? (el.parentElement.id || el.parentElement.tagName) : "",
        insideContainer: !!el.closest(".rc-container"),
        visible: getComputedStyle(el).visibility,
        top: box.top, bottom: box.bottom, left: box.left, right: box.right,
      };
    });
  const cbox = ct ? ct.getBoundingClientRect() : null;
  window.__log.push({
    label: label,
    containerShadow: ct ? getComputedStyle(ct).boxShadow : "",
    containerRadius: ct ? getComputedStyle(ct).borderRadius : "",
    layerRadius: layer ? getComputedStyle(layer).borderRadius : "",
    layerShadow: layer ? getComputedStyle(layer).boxShadow : "",
    containerBox: cbox ? {top: cbox.top, bottom: cbox.bottom,
                          left: cbox.left, right: cbox.right} : null,
    containerOverflow: ct ? getComputedStyle(ct).overflow : "",
    globals: {
      backdrop: getComputedStyle(document.documentElement)
        .getPropertyValue("--rc-backdrop-filter").trim(),
      containerBackdrop: ct ? getComputedStyle(ct).backdropFilter : "",
    },
    hosts: hosts,
  });
};
window.__run = async function () {
  handlePayload(window.__payload({text: "Jesus wept.",
                                  reference: "John 11:35"}));
  await window.__wait(400);
  window.__snap("none-bg");
  applyTheme(Object.assign({}, window.__theme, {containers: [
    Object.assign({}, window.__theme.containers[0], {
      container_background: "#112233",
    })]}));
  await window.__wait(250);
  window.__snap("filled-bg");
  window.__log.push({label: "errors", errs: window.__errs});
  const tag = document.createElement("script");
  tag.type = "text/plain";
  tag.setAttribute("data-rc", "log");
  tag.textContent = JSON.stringify(window.__log);
  document.body.appendChild(tag);
};
"""

SHADOW_THEME = {
    "schema_version": 2,
    "name": "round3_shadow",
    "kind": "scripture",
    "canvas": {"width": 1920, "height": 1080},
    "containers": [{
        "id": "main", "visible": True, "layer": 1,
        "position": {"anchor": "top_left", "x": 400, "y": 300},
        "width": 600, "height": 300,
        "container_background": "none",
        "background": "rgba(15, 23, 42, 0.6)",
        "border": "none",
        "border_padding": 0,
        "border_radius": 24,
        "box_shadow": "0 8px 24px #00000080",
        "border_shadow": "0 40px 0 #ff0000",
        "backdrop_filter": "blur(16px)",
        "opacity": 1,
        "overflow": "hidden",
        "blocks": {
            "body": {"visible": True, "valign": "center", "gap": 8,
                     "padding": 0},
            "text": {"visible": True, "size": 48, "color": "#ffffff"},
            "reference": {"visible": True, "size": 24, "color": "#dddddd"},
        },
    }],
    "animations": {},
}


def _script_text(rel_path: str) -> str:
    src = (ROOT / rel_path).read_text()
    if rel_path.endswith(".py"):
        html = src.split('_DISPLAY_HTML = r"""', 1)[1].split('"""', 1)[0]
        src = "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))
    return src


def _drive_shadows(script_path: str) -> dict:
    from tests.test_theme_v2_animation_runtime import _build_page

    page_html = _build_page(script_path, theme=SHADOW_THEME,
                            driver=SHADOW_DRIVER)
    tmp = Path(tempfile.mkdtemp(prefix="rc-round3-"))
    try:
        page = tmp / "page.html"
        page.write_text(page_html)
        out = subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--window-size=1920,1080", "--force-device-scale-factor=1",
             f"--user-data-dir={tmp / 'profile'}", "--no-first-run",
             "--virtual-time-budget=8000", "--dump-dom", page.as_uri()],
            capture_output=True, text=True, timeout=120).stdout
        found = re.findall(r'<script[^>]*data-rc="log"[^>]*>(.*?)</script>',
                           out, re.S)
        assert found, f"renderer produced no log: {out[:800]}"
        return {entry["label"]: entry for entry in json.loads(found[-1])
                if "label" in entry}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_only_the_visible_shadow_paints(renderer):
    log = _drive_shadows(renderer)
    border_first = log["none-bg"]
    # Container bg is None: no container shadow, the border shadow paints.
    assert border_first["containerShadow"] in ("none", "")
    hosts = border_first["hosts"]
    assert len(hosts) == 1, f"expected one border shadow host, got {hosts}"
    assert "40px" in hosts[0]["shadow"], hosts[0]["shadow"]

    filled = log["filled-bg"]
    assert "8px" in filled["containerShadow"] or \
        "24px" in filled["containerShadow"], filled["containerShadow"]
    assert filled["hosts"][0]["shadow"] in ("none", ""), \
        "a hidden border shadow still painted"


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_border_shadow_is_not_clipped_by_the_container(renderer):
    log = _drive_shadows(renderer)
    entry = log["none-bg"]
    assert entry["containerOverflow"] == "hidden"
    host = entry["hosts"][0]
    box = entry["containerBox"]
    assert host["insideContainer"] is False, (
        "the border shadow is a descendant of the container, so overflow "
        "clips it")
    assert host["parent"] in ("stage", "STAGE"), host["parent"]
    # A 40 px downward offset paints below the container's own bounds.
    assert host["bottom"] + 40 > box["bottom"], (host, box)


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_radius_shapes_the_border_layer_only(renderer):
    log = _drive_shadows(renderer)
    entry = log["none-bg"]
    assert entry["containerRadius"] in ("0px", "0"), entry["containerRadius"]
    assert entry["layerRadius"] == "24px", entry["layerRadius"]
    assert entry["hosts"][0]["radius"] == "24px", entry["hosts"][0]["radius"]

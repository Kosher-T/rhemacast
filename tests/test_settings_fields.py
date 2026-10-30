"""Settings field chrome: generated chevrons, geometry and state behaviour.

The previous attempt passed a "a chevron is visible" check while painting
two of them (one at the widget centre, one in the drop-down). These tests
therefore render a *textless* field, exclude the border ring, count
connected components, and assert their bounding boxes. Every test also
fails on a Qt stylesheet parse/load message.

Run offscreen::

    QT_QPA_PLATFORM=offscreen python -m pytest tests/test_settings_fields.py -v
"""

import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PyQt6.QtCore import QPoint, QPointF, Qt, qInstallMessageHandler
from PyQt6.QtGui import QColor, QImage, QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QSpinBox, QStyle, QStyleOptionComboBox,
    QStyleOptionSpinBox, QVBoxLayout, QWidget,
)

from tests.harness import field_chrome as probe
from ui import field_chrome, tokens

FORBIDDEN_MESSAGES = (
    "Could not parse stylesheet",
    "Unknown property",
    "Could not load",
)

EXPECTED_COMPONENTS = {"combo": 1, "font": 1, "spin": 2}


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def qapp():
    return probe.install_test_app()


@pytest.fixture(scope="module")
def park(qapp):
    widget = probe.park_widget()
    yield widget
    widget.close()


@pytest.fixture(autouse=True)
def _fail_on_qt_stylesheet_messages():
    """Any warning about parsing or loading a stylesheet fails the test."""
    captured: list[str] = []
    previous = qInstallMessageHandler(
        lambda mode, context, message: captured.append(str(message)))
    try:
        yield
    finally:
        qInstallMessageHandler(previous)
    offenders = [message for message in captured
                 if any(text in message for text in FORBIDDEN_MESSAGES)]
    assert offenders == [], offenders


# ─── Arrow count (the check the failed attempt lacked) ──────────────────────

@pytest.mark.parametrize("kind", probe.CONTROLS)
@pytest.mark.parametrize("state", probe.STATES)
def test_arrow_component_count(kind, state, qapp, park):
    widget = probe.make_control(kind)
    try:
        probe.apply_state(widget, state, park)
        components, image = probe.grab_components(widget)

        print(f"\n{kind:5} {state:8} height={widget.height()} "
              f"components={len(components)}")
        for component in components:
            print(f"    {component}")

        assert widget.height() == tokens.COMBO_HEIGHT
        assert len(components) == EXPECTED_COMPONENTS[kind], (
            kind, state, [str(component) for component in components])

        # Every mark must sit in the right-hand button column, not in the
        # text area (the old bug's centre copy) and not on the border.
        column_width = (tokens.SPIN_BUTTON_WIDTH if kind == "spin"
                        else tokens.COMBO_BUTTON_WIDTH)
        column_left = widget.width() - column_width - 2
        for component in components:
            assert component.center_x >= column_left, (kind, state, component)
            assert component.right < widget.width(), (kind, state, component)
            assert component.bottom < widget.height(), (kind, state, component)
            assert component.width <= 14, (kind, state, component)
            assert component.height <= 8, (kind, state, component)
    finally:
        widget.close()


def test_arrow_files_are_distinct_per_state_and_scale(qapp):
    paths = field_chrome.ensure_arrow_images()
    assert len(paths) == 12

    import hashlib

    digests = {}
    for name, path in paths.items():
        image = QImage(path)
        assert not image.isNull(), (name, path)
        expected = 24 if name.endswith("@2x") else 12
        assert (image.width(), image.height()) == (expected, expected), name
        assert os.path.getsize(path) > 0, name
        digests[name] = hashlib.sha256(open(path, "rb").read()).hexdigest()

    assert digests["down-normal"] != digests["down-hover"]
    assert digests["down-hover"] != digests["down-disabled"]
    assert digests["up-normal"] != digests["down-normal"]
    assert digests["down-normal@2x"] != digests["down-normal"]


# ─── Geometry ───────────────────────────────────────────────────────────────

def _spin_rects(widget):
    option = QStyleOptionSpinBox()
    option.initFrom(widget)
    style = widget.style()
    return {
        "up": style.subControlRect(
            QStyle.ComplexControl.CC_SpinBox, option,
            QStyle.SubControl.SC_SpinBoxUp, widget),
        "down": style.subControlRect(
            QStyle.ComplexControl.CC_SpinBox, option,
            QStyle.SubControl.SC_SpinBoxDown, widget),
        "edit": style.subControlRect(
            QStyle.ComplexControl.CC_SpinBox, option,
            QStyle.SubControl.SC_SpinBoxEditField, widget),
    }


def _combo_rects(widget):
    option = QStyleOptionComboBox()
    option.initFrom(widget)
    option.editable = widget.isEditable()
    style = widget.style()
    return {
        "arrow": style.subControlRect(
            QStyle.ComplexControl.CC_ComboBox, option,
            QStyle.SubControl.SC_ComboBoxArrow, widget),
        "edit": style.subControlRect(
            QStyle.ComplexControl.CC_ComboBox, option,
            QStyle.SubControl.SC_ComboBoxEditField, widget),
    }


def test_spin_buttons_fill_the_inner_rect(qapp, park):
    spin = probe.make_control("spin")
    try:
        probe.apply_state(spin, "normal", park)
        rects = _spin_rects(spin)
        up, down = rects["up"], rects["down"]
        inner = spin.rect().adjusted(
            tokens.FIELD_BORDER_WIDTH, tokens.FIELD_BORDER_WIDTH,
            -tokens.FIELD_BORDER_WIDTH, -tokens.FIELD_BORDER_WIDTH)

        print(f"\nspin height={spin.height()} inner={inner}")
        for name, rect in rects.items():
            print(f"    {name}: {rect}")

        assert spin.height() == tokens.COMBO_HEIGHT
        assert up.width() == tokens.SPIN_BUTTON_WIDTH
        assert down.width() == tokens.SPIN_BUTTON_WIDTH
        assert up.left() == down.left()
        assert up.top() == inner.top()
        assert down.bottom() == inner.bottom()
        assert up.bottom() + 1 == down.top(), "gap or overlap between buttons"
        assert up.height() + down.height() == inner.height()
        assert inner.contains(up) and inner.contains(down)
        assert rects["edit"].right() < up.left(), "text runs under buttons"
    finally:
        spin.close()


def test_combo_arrow_sits_in_the_dropdown_column(qapp, park):
    for kind in ("combo", "font"):
        combo = probe.make_control(kind)
        try:
            probe.apply_state(combo, "normal", park)
            rects = _combo_rects(combo)
            arrow = rects["arrow"]
            inner_column = (combo.width() - tokens.COMBO_BUTTON_WIDTH - 2,
                            combo.width() - 2)

            print(f"\n{kind} height={combo.height()} arrow={arrow} "
                  f"edit={rects['edit']}")

            assert combo.height() == tokens.COMBO_HEIGHT
            assert arrow.width() == tokens.COMBO_BUTTON_WIDTH
            assert inner_column[0] <= arrow.center().x() <= inner_column[1]
            assert rects["edit"].right() < arrow.left()
        finally:
            combo.close()


def test_layout_height_is_the_token_height(qapp):
    host = QWidget()
    layout = QVBoxLayout(host)
    controls = [probe.make_control(kind) for kind in probe.CONTROLS]
    for control in controls:
        layout.addWidget(control)
    host.show()
    qapp.processEvents()
    try:
        print("\nlayout heights:",
              [(control.objectName(), control.height())
               for control in controls])
        for control in controls:
            assert control.height() == tokens.COMBO_HEIGHT
    finally:
        host.close()


# ─── State isolation ────────────────────────────────────────────────────────

def test_focus_keeps_the_arrow_normal_and_paints_the_accent_border(
        qapp, park):
    readings = {}
    for state in ("normal", "hover", "focus", "disabled"):
        widget = probe.make_control("combo")
        try:
            probe.apply_state(widget, state, park)
            components, image = probe.grab_components(widget)
            readings[state] = {
                "brightness": probe.arrow_brightness(components, image),
                "border": probe.border_colour(widget).name(),
                "count": len(components),
            }
        finally:
            widget.close()

    print("\ncombo state readings:", readings)

    assert readings["focus"]["border"] != readings["normal"]["border"]
    focus_border = QColor(readings["focus"]["border"])
    assert focus_border.blue() > focus_border.red(), readings["focus"]
    assert readings["focus"]["brightness"] == readings["normal"]["brightness"]
    assert readings["hover"]["brightness"] > readings["normal"]["brightness"]
    assert readings["disabled"]["brightness"] < readings["normal"]["brightness"]
    assert all(reading["count"] == 1 for reading in readings.values())


def test_spin_hover_brightens_both_chevrons(qapp, park):
    brightness = {}
    for state in ("normal", "hover"):
        widget = probe.make_control("spin")
        try:
            probe.apply_state(widget, state, park)
            components, image = probe.grab_components(widget)
            assert len(components) == 2
            brightness[state] = probe.arrow_brightness(components, image)
        finally:
            widget.close()
    print("\nspin arrow brightness:", brightness)
    assert brightness["hover"] > brightness["normal"]


# ─── Scoping / no leak ──────────────────────────────────────────────────────

def _blocks(qss: str):
    return re.findall(r"([^{}]+)\{([^{}]*)\}", qss)


@pytest.mark.parametrize("helper,prefix", [
    (field_chrome.combo_qss, "QComboBox"),
    (field_chrome.spin_qss, "QSpinBox"),
])
def test_qss_is_scoped_and_every_arrow_rule_is_positioned(helper, prefix):
    name = "scopeProbe"
    qss = helper(name)

    assert f"{prefix}#{name}" in qss
    assert not re.search(rf"(?m)^\s*{prefix}\s*\{{", qss), "unscoped rule"

    arrow_rules = 0
    for selector, body in _blocks(qss):
        if "-arrow" not in selector:
            continue
        arrow_rules += 1
        assert "subcontrol-origin" in body, selector
        assert "subcontrol-position" in body, selector
        assert "image:" in body, selector
    assert arrow_rules >= 1

    if prefix == "QSpinBox":
        assert "up-arrow:hover" in qss
        assert "down-arrow:hover" in qss
        # Separate images for the two directions, never one shared hover.
        up = re.search(r"::up-arrow:hover\s*\{([^}]*)\}", qss).group(1)
        down = re.search(r"::down-arrow:hover\s*\{([^}]*)\}", qss).group(1)
        up_image = re.search(r"url\(([^)]+)\)", up).group(1)
        down_image = re.search(r"url\(([^)]+)\)", down).group(1)
        assert up_image != down_image


def test_qt_stylesheet_uses_plain_absolute_paths():
    paths = field_chrome.ensure_arrow_images()
    for path in paths.values():
        assert os.path.isabs(path), path
        assert "\\" not in path, path
        assert not path.startswith("file://"), path
        assert not path.startswith("data:"), path


def test_arrow_urls_survive_a_directory_with_a_space(qapp, tmp_path):
    base = tmp_path / "arrow cache with spaces"
    assert " " in str(base)
    paths = field_chrome.ensure_arrow_images(base_dir=base)
    assert len(paths) == 12
    assert any(" " in path for path in paths.values())

    combo = QComboBox()
    combo.addItem("")
    combo.setObjectName("spaceCombo")
    combo.setStyleSheet(field_chrome.combo_qss("spaceCombo", paths))
    combo.resize(220, tokens.COMBO_HEIGHT)
    combo.show()
    qapp.processEvents()
    try:
        components, _ = probe.grab_components(combo)
        print("\nspace-path combo components:", [str(c) for c in components])
        assert len(components) == 1
        assert combo.height() == tokens.COMBO_HEIGHT
    finally:
        combo.close()

    spin = QSpinBox()
    spin.setRange(8, 16)
    spin.setValue(8)
    spin.setSpecialValueText(" ")
    spin.setSuffix("")
    spin.setReadOnly(True)
    spin.setObjectName("spaceSpin")
    spin.setStyleSheet(field_chrome.spin_qss("spaceSpin", paths))
    spin.resize(220, tokens.COMBO_HEIGHT)
    spin.show()
    qapp.processEvents()
    try:
        components, _ = probe.grab_components(spin)
        print("space-path spin components:", [str(c) for c in components])
        assert len(components) == 2
    finally:
        spin.close()


# ─── Settings tab wiring ────────────────────────────────────────────────────

def test_settings_font_row_uses_the_scoped_helpers(qapp):
    from types import SimpleNamespace

    from ui.tabs.settings_tab import SettingsTab

    host = QWidget()
    layout = QVBoxLayout(host)
    holder = SimpleNamespace(_font_groups={})
    SettingsTab._add_font_group(
        holder, layout, prefix="test.fontrow", title="Font row",
        subtitle="Test-only", size_min=8, size_max=16, size_default=13,
        weight_default=400, preview_text="Preview",
        family_key="test.font_family", weight_key="test.font_weight",
        size_key="test.font_size")
    controls = holder._font_groups["test.fontrow"]
    host.show()
    qapp.processEvents()
    try:
        expected = {
            "family": field_chrome.SETTINGS_FONT_FAMILY_COMBO,
            "weight": field_chrome.SETTINGS_FONT_WEIGHT_COMBO,
            "size": field_chrome.SETTINGS_FONT_SIZE_SPIN,
        }
        for key, object_name in expected.items():
            widget = controls[key]
            assert widget.objectName() == object_name
            assert f"#{object_name}" in widget.styleSheet()
            assert widget.height() == tokens.COMBO_HEIGHT
            assert widget.font().family() == qapp.font().family()
        assert controls["size"].suffix() == " px"
        assert controls["size"].value() == 13
    finally:
        host.close()


# ─── Behaviour is unchanged ────────────────────────────────────────────────

def test_spin_behavior_is_unchanged(qapp):
    spin = probe.make_control("spin", textless=False)
    spin.setRange(8, 16)
    spin.setValue(13)
    spin.show()
    spin.activateWindow()
    spin.setFocus()
    qapp.processEvents()

    changed = []
    spin.valueChanged.connect(changed.append)

    def wheel(delta: int) -> None:
        local = QPointF(10, 10)
        event = QWheelEvent(
            local, QPointF(spin.mapToGlobal(QPoint(10, 10))),
            QPoint(0, 0), QPoint(0, delta),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(spin, event)
        qapp.processEvents()

    try:
        assert spin.suffix() == " px"
        assert (spin.minimum(), spin.maximum()) == (8, 16)

        spin.stepBy(1)
        assert spin.value() == 14

        QTest.keyClick(spin, Qt.Key.Key_Up)
        assert spin.value() == 15
        QTest.keyClick(spin, Qt.Key.Key_Down)
        assert spin.value() == 14
        QTest.keyClick(spin, Qt.Key.Key_PageUp)
        page_up = spin.value()
        assert page_up > 14, "PageUp must step up"
        QTest.keyClick(spin, Qt.Key.Key_PageDown)
        assert spin.value() < page_up, "PageDown must step down"

        spin.setValue(10)
        wheel(120)
        assert spin.value() == 11, "wheel up steps once"
        wheel(-120)
        assert spin.value() == 10, "wheel down steps once"

        assert changed, "valueChanged must still fire"
        assert spin.suffix() == " px"
        assert (spin.minimum(), spin.maximum()) == (8, 16)
    finally:
        spin.close()


# ─── Raw dumps for the report ──────────────────────────────────────────────

def test_print_font_row_ascii_dumps(qapp, park):
    for kind, state in (("font", "normal"), ("font", "hover"),
                        ("spin", "normal"), ("spin", "hover")):
        widget = probe.make_control(kind)
        try:
            probe.apply_state(widget, state, park)
            print(f"\n=== {kind} {state} {widget.width()}x"
                  f"{widget.height()} ===")
            print(probe.ascii_dump(widget))
        finally:
            widget.close()


# ─── Phase 2: the standard-size Settings fields ─────────────────────────────

STANDARD_FIELDS = (
    (field_chrome.SETTINGS_FIELD_COMBO, "combo", 1),
    (field_chrome.SETTINGS_FIELD_SPIN, "spin", 2),
)


@pytest.mark.parametrize("state", probe.STATES)
@pytest.mark.parametrize("object_name,kind,expected", STANDARD_FIELDS)
def test_standard_field_component_count(object_name, kind, expected, state,
                                        qapp, park):
    widget = probe.make_control(kind, object_name=object_name)
    try:
        probe.apply_state(widget, state, park)
        components, _ = probe.grab_components(widget)
        print(f"\n{object_name} {state} height={widget.height()} "
              f"components={len(components)}")
        for component in components:
            print(f"    {component}")
        assert widget.objectName() == object_name
        assert widget.height() == tokens.COMBO_HEIGHT
        assert len(components) == expected, (
            object_name, state, [str(c) for c in components])
    finally:
        widget.close()


def test_settings_tab_no_longer_applies_the_legacy_field_styles():
    """Two matching arrow rules paint two chevrons; the tab must use the
    scoped generated-arrow helpers for every Settings field."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1]
              / "ui" / "tabs" / "settings_tab.py").read_text(encoding="utf-8")
    assert "setStyleSheet(COMBO_STYLE)" not in source
    assert "setStyleSheet(SPIN_STYLE)" not in source


# ─── Phase 3: the compact Database / Keywords combos ────────────────────────

@pytest.mark.parametrize("state", probe.STATES)
def test_compact_combo_keeps_27px_and_one_arrow(state, qapp, park):
    widget = probe.make_control(
        "combo", object_name=field_chrome.SETTINGS_COMPACT_COMBO,
        compact=True)
    try:
        probe.apply_state(
            widget, state, park, height=tokens.COMPACT_COMBO_HEIGHT)
        components, _ = probe.grab_components(widget)
        print(f"\ncompact combo {state} height={widget.height()} "
              f"components={len(components)}")
        for component in components:
            print(f"    {component}")

        assert widget.objectName() == field_chrome.SETTINGS_COMPACT_COMBO
        assert widget.height() == tokens.COMPACT_COMBO_HEIGHT
        assert len(components) == 1, [str(c) for c in components]
        column_left = (widget.width()
                       - tokens.COMPACT_COMBO_BUTTON_WIDTH - 2)
        for component in components:
            assert component.center_x >= column_left
            assert component.width <= 14
            assert component.height <= 8

        option = QStyleOptionComboBox()
        option.initFrom(widget)
        option.editable = False
        arrow = widget.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox, option,
            QStyle.SubControl.SC_ComboBoxArrow, widget)
        assert arrow.width() == tokens.COMPACT_COMBO_BUTTON_WIDTH
        assert widget.height() == tokens.COMPACT_COMBO_HEIGHT
    finally:
        widget.close()


def test_compact_combo_has_no_max_width_and_keeps_dense_text():
    qss = field_chrome.combo_qss(
        field_chrome.SETTINGS_COMPACT_COMBO, compact=True)
    assert "max-width" not in qss, "compact combos must keep growing"
    assert f"min-width: {tokens.COMPACT_COMBO_MIN_WIDTH}px" in qss
    assert f"font-size: {tokens.TYPE_CAPTION}px" in qss
    assert f"padding: {tokens.COMPACT_COMBO_PADDING_Y}px" in qss
    assert f"width: {tokens.COMPACT_COMBO_BUTTON_WIDTH}px" in qss

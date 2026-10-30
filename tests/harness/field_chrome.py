"""
Reusable offscreen probes for the Settings field chrome tests.

The point of these helpers is that "a chevron is visible" is not enough:
the failure this guards against painted *two* chevrons (one at the widget
centre, one in the drop-down) and still passed a visibility check. So the
probe renders a textless field, excludes the border, counts connected
components, and reports each component's bounding box.

Not product code.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import dataclass

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFontComboBox, QSpinBox, QWidget,
)

from ui import field_chrome, tokens

CONTROLS = ("combo", "font", "spin")
STATES = ("normal", "hover", "focus", "disabled")


@dataclass(frozen=True)
class Component:
    """One connected mark in the rendered field."""

    area: int
    left: int
    top: int
    right: int
    bottom: int

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2.0

    @property
    def width(self) -> int:
        return self.right - self.left + 1

    @property
    def height(self) -> int:
        return self.bottom - self.top + 1

    def __str__(self) -> str:       # compact table cell
        return (f"area={self.area} bbox=({self.left},{self.top})-"
                f"({self.right},{self.bottom})")


def install_test_app() -> QApplication:
    """Mirror ``core/ui.py``'s order: Fusion, sheet, font, palette.

    The order matters: a stylesheet installed after the bundled Inter font
    makes new widgets resolve their family from the platform theme. The
    tests assert the controls still use the app font.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(["rhemacast-field-chrome-tests"])

    from ui.app_style import install as install_app_style
    assert install_app_style(app) is True

    from ui.popups import tooltip_qss
    app.setStyleSheet(tokens.scrollbar_qss() + "\n" + tooltip_qss())

    from ui.typography import install as install_typography
    install_typography(app)

    from ui.app_theme import apply_palette
    apply_palette(app)
    return app


def park_widget() -> QWidget:
    """A window used only as a mouse/focus parking spot."""
    park = QWidget()
    park.setGeometry(900, 900, 40, 40)
    park.show()
    QApplication.processEvents()
    return park


def move_mouse_away(park: QWidget) -> None:
    QTest.mouseMove(park, QPoint(5, 5))
    QApplication.processEvents()


def make_control(kind: str, *, textless: bool = True,
                 object_name: str | None = None,
                 compact: bool = False) -> QWidget:
    """Build one Settings-styled control, textless by default.

    ``combo``       plain QComboBox with one empty item
    ``font``        QFontComboBox with an empty item, non-editable so a
                    focus caret cannot be mistaken for an arrow
    ``spin``        QSpinBox at its minimum with an empty special value,
                    read-only so a caret cannot be mistaken for an arrow
    """
    if kind == "spin":
        spin = QSpinBox()
        spin.setRange(8, 16)
        spin.setValue(8)
        if textless:
            spin.setSpecialValueText(" ")
            spin.setSuffix("")
            spin.setReadOnly(True)
        else:
            spin.setSuffix(" px")
            spin.setValue(13)
        field_chrome.apply_spin(
            spin, object_name or field_chrome.SETTINGS_FONT_SIZE_SPIN)
        widget = spin
    elif kind == "font":
        combo = QFontComboBox()
        if textless:
            combo.clear()
            combo.addItem("")
            combo.setEditable(False)
        field_chrome.apply_combo(
            combo, field_chrome.SETTINGS_FONT_FAMILY_COMBO)
        widget = combo
    elif kind == "combo":
        combo = QComboBox()
        combo.addItem("")
        field_chrome.apply_combo(
            combo, object_name or field_chrome.SETTINGS_FONT_WEIGHT_COMBO,
            compact=compact)
        widget = combo
    else:
        raise ValueError(f"unknown control kind: {kind!r}")

    widget.resize(220, tokens.COMBO_HEIGHT)
    return widget


def apply_state(widget: QWidget, state: str, park: QWidget,
                *, height: int | None = None) -> QWidget:
    """Show a fresh widget and apply exactly one state.

    Offscreen Qt activates a freshly shown top-level widget, which would
    paint the focus border in every state. Non-focus states therefore opt
    out of focus first; the focus state uses the real (StrongFocus)
    policy.
    """
    widget.setFocusPolicy(
        Qt.FocusPolicy.StrongFocus if state == "focus"
        else Qt.FocusPolicy.NoFocus)
    move_mouse_away(park)
    widget.show()
    widget.resize(220, height or tokens.COMBO_HEIGHT)
    widget.clearFocus()
    QApplication.processEvents()

    if state == "hover":
        y = 7 if isinstance(widget, QSpinBox) else widget.height() // 2
        QTest.mouseMove(widget, QPoint(widget.width() - 12, y))
        QApplication.processEvents()
        assert widget.underMouse(), "hover did not reach the widget offscreen"
    elif state == "focus":
        widget.activateWindow()
        widget.setFocus(Qt.FocusReason.OtherFocusReason)
        QApplication.processEvents()
        assert widget.hasFocus(), "focus did not reach the widget offscreen"
    elif state == "disabled":
        widget.setEnabled(False)
        QApplication.processEvents()
    elif state != "normal":
        raise ValueError(f"unknown state: {state!r}")
    return widget


def _difference(first: QColor, second: QColor) -> int:
    return max(abs(first.red() - second.red()),
               abs(first.green() - second.green()),
               abs(first.blue() - second.blue()))


def grab_components(widget: QWidget, *, ring: int = 3,
                    threshold: int = 24,
                    min_area: int = 3) -> tuple[list[Component], QImage]:
    """Return connected marks, excluding the border ring.

    A component is a 4-connected run of pixels that differ from
    ``BG_FIELD`` by more than ``threshold`` and are opaque enough to be
    painted. Antialiased edge pixels are included; the border and the
    rounded corners are not.
    """
    image = widget.grab().toImage().convertToFormat(
        QImage.Format.Format_ARGB32)
    background = QColor(tokens.BG_FIELD)
    width, height = image.width(), image.height()
    seen: set[tuple[int, int]] = set()
    components: list[Component] = []

    def painted(x: int, y: int) -> bool:
        colour = image.pixelColor(x, y)
        return (colour.alpha() >= 40
                and _difference(background, colour) > threshold)

    for y in range(ring, height - ring):
        for x in range(ring, width - ring):
            if (x, y) in seen or not painted(x, y):
                continue
            stack = [(x, y)]
            seen.add((x, y))
            pixels: list[tuple[int, int]] = []
            while stack:
                px, py = stack.pop()
                pixels.append((px, py))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = px + dx, py + dy
                    if (ring <= nx < width - ring
                            and ring <= ny < height - ring
                            and (nx, ny) not in seen
                            and painted(nx, ny)):
                        seen.add((nx, ny))
                        stack.append((nx, ny))
            if len(pixels) >= min_area:
                xs = [point[0] for point in pixels]
                ys = [point[1] for point in pixels]
                components.append(Component(
                    area=len(pixels), left=min(xs), top=min(ys),
                    right=max(xs), bottom=max(ys)))

    components.sort(key=lambda part: part.left)
    return components, image


def arrow_brightness(components: list[Component], image: QImage) -> int:
    """Brightest RGB sum inside the components (state colour probe)."""
    best = 0
    for component in components:
        for y in range(component.top, component.bottom + 1):
            for x in range(component.left, component.right + 1):
                colour = image.pixelColor(x, y)
                if colour.alpha() >= 40:
                    best = max(best, colour.red() + colour.green()
                               + colour.blue())
    return best


def border_colour(widget: QWidget) -> QColor:
    """One border pixel at mid-height (x=0 is the 1px field border)."""
    image = widget.grab().toImage().convertToFormat(
        QImage.Format.Format_ARGB32)
    return image.pixelColor(0, widget.height() // 2)


def ascii_dump(widget: QWidget) -> str:
    """Full-width, one character per pixel.

    ' ' equal to the field background, '.' slight, '+' medium, '#' strong.
    """
    image = widget.grab().toImage().convertToFormat(
        QImage.Format.Format_ARGB32)
    background = QColor(tokens.BG_FIELD)
    rows = []
    for y in range(image.height()):
        row = []
        for x in range(image.width()):
            colour = image.pixelColor(x, y)
            if colour.alpha() <= 20:
                delta = 0
            else:
                delta = _difference(background, colour)
            row.append(" " if delta <= 6 else
                       "." if delta <= 24 else
                       "+" if delta <= 64 else "#")
        rows.append("".join(row))
    return "\n".join(rows)

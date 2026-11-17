"""SegmentedToggle focus painting: ring the segment, never the whole row.

A click selects a segment — that is already visible — so it must not outline
the entire switch. Keyboard focus still paints a ring, but only around the
current segment.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtCore import QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QImage, QKeyEvent, QMouseEvent, QPainter  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from ui.theme_kit.segmented import ChoiceOption, SegmentedToggle  # noqa: E402

_QAPP = None
OPTIONS = [ChoiceOption("canvas", "Canvas"),
           ChoiceOption("container", "Container"),
           ChoiceOption("blocks", "Blocks")]


@pytest.fixture(scope="module")
def qapp():
    global _QAPP
    _QAPP = QApplication.instance() or QApplication([])
    return _QAPP


def _toggle() -> SegmentedToggle:
    toggle = SegmentedToggle(OPTIONS, "canvas")
    toggle.resize(320, 28)
    toggle.show()
    return toggle


def _click(toggle: SegmentedToggle, index: int) -> None:
    centre = toggle._segment_rect(index).center()
    for event_type, buttons in (
            (QMouseEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
            (QMouseEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
        QApplication.sendEvent(toggle, QMouseEvent(
            event_type, QPointF(centre), QPointF(centre),
            Qt.MouseButton.LeftButton, buttons,
            Qt.KeyboardModifier.NoModifier))


def _key(toggle: SegmentedToggle, key) -> None:
    QApplication.sendEvent(toggle, QKeyEvent(
        QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))


def _image(toggle: SegmentedToggle) -> QImage:
    toggle.update()
    QApplication.processEvents()
    image = QImage(toggle.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    try:
        toggle.render(painter)
    finally:
        painter.end()
    return image


def test_a_click_paints_no_focus_ring_at_all(qapp):
    toggle = _toggle()
    toggle.setFocus(Qt.FocusReason.TabFocusReason)
    assert _image(toggle) != _image_of(toggle, focused=False), (
        "the keyboard ring must be visible to compare against")

    _click(toggle, 1)

    assert toggle.hasFocus(), "the click should still take focus"
    assert not toggle._keyboard_focus
    # Same selection, focused vs unfocused: identical pixels means the click
    # added no ring around the row.
    focused_image = _image(toggle)
    toggle.clearFocus()
    assert _image(toggle) == focused_image


def test_keyboard_focus_still_paints_a_ring(qapp):
    toggle = _toggle()
    toggle.setFocus(Qt.FocusReason.TabFocusReason)
    assert toggle._keyboard_focus
    assert _image(toggle) != _image_of(toggle, focused=False)


def test_arrow_keys_restore_the_ring_after_a_click(qapp):
    toggle = _toggle()
    toggle.setFocus(Qt.FocusReason.TabFocusReason)
    _click(toggle, 1)
    assert not toggle._keyboard_focus

    _key(toggle, Qt.Key.Key_Right)
    assert toggle._keyboard_focus


def _image_of(toggle: SegmentedToggle, *, focused: bool) -> QImage:
    """The same widget painted with the ring forced on or off."""
    previous = toggle._keyboard_focus
    toggle._keyboard_focus = focused
    try:
        return _image(toggle)
    finally:
        toggle._keyboard_focus = previous

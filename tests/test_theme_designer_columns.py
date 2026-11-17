"""Offscreen tests for the Theme Designer's resizable side columns.

Covers the shipped defaults, min/max clamping while dragging, the preview
width floor, persistence in the local settings store, double-click reset,
saved widths that no longer fit, the content reflow floor (no horizontal
scrollbars at the minimum side widths), and the handle's paint states.

The QtWebEngine preview is stubbed exactly as ``test_theme_designer_m1_batch1``
does: these tests own the column geometry, not the display renderer.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtCore import QPoint, Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QScrollArea, QWidget  # noqa: E402

# Import WebEngine before QApplication exists; the module import is enough for
# the real preview import chain, while these tests construct a stub instead.
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from PyQt6 import QtWebEngineWidgets  # noqa: F401,E402

from core import theme_schema as schema  # noqa: E402
from core.constants import (  # noqa: E402
    DESIGNER_HANDLE_WIDTH,
    DESIGNER_LEFT_DEFAULT_WIDTH,
    DESIGNER_LEFT_MAX_WIDTH,
    DESIGNER_LEFT_MIN_WIDTH,
    DESIGNER_PREVIEW_MIN_WIDTH,
    DESIGNER_RIGHT_DEFAULT_WIDTH,
    DESIGNER_RIGHT_MAX_WIDTH,
    DESIGNER_RIGHT_MIN_WIDTH,
)
from core.database import delete_setting, get_setting, set_setting  # noqa: E402
from ui.widgets.theme_designer.column_handle import ColumnHandle  # noqa: E402

LEFT_KEY = "layout.designer.left_width"
RIGHT_KEY = "layout.designer.right_width"
TAB_MIN_WIDTH = (DESIGNER_LEFT_MIN_WIDTH + DESIGNER_RIGHT_MIN_WIDTH
                 + DESIGNER_PREVIEW_MIN_WIDTH + 2 * DESIGNER_HANDLE_WIDTH)

_QAPP = None
_TAB_MODULE = None
_REAL_PREVIEW = None


class _PreviewStub(QWidget):
    """Stand-in for the QtWebEngine preview; owns no rendering."""

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.theme = {}
        self.sample = ""

    def apply_theme(self, theme):
        self.theme = dict(theme)

    def set_verse(self, sample_id):
        self.sample = str(sample_id)


def _tab_module():
    global _TAB_MODULE, _REAL_PREVIEW
    if _TAB_MODULE is None:
        from ui.tabs import theme_designer_tab as module
        _TAB_MODULE = module
        _REAL_PREVIEW = module.ThemePreview
    return _TAB_MODULE


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def qapp():
    global _QAPP
    _QAPP = QApplication.instance() or QApplication([])
    return _QAPP


@pytest.fixture(autouse=True)
def clean_width_settings(_isolated_app_db):
    """Every test starts and ends with no saved Designer widths."""
    delete_setting(LEFT_KEY)
    delete_setting(RIGHT_KEY)
    yield
    delete_setting(LEFT_KEY)
    delete_setting(RIGHT_KEY)


@pytest.fixture
def tab(qapp, monkeypatch):
    """A real ThemeDesignerTab with only the QtWebEngine preview stubbed."""
    module = _tab_module()
    monkeypatch.setattr(module, "ThemePreview", _PreviewStub)
    widget = module.ThemeDesignerTab()
    widget.resize(1400, 900)
    widget.show()
    _settle(qapp)
    yield widget
    widget.close()
    widget.deleteLater()
    _settle(qapp)


def _settle(qapp, rounds: int = 4) -> None:
    for _ in range(rounds):
        qapp.processEvents()


def _make_tab(qapp, width: int = 1400, height: int = 900):
    """Build a tab with the preview stubbed, with no fixture required."""
    module = _tab_module()
    previous = module.ThemePreview
    module.ThemePreview = _PreviewStub
    try:
        widget = module.ThemeDesignerTab()
    finally:
        module.ThemePreview = previous
    widget.resize(width, height)
    widget.show()
    _settle(qapp)
    return widget


def _close(tab, qapp) -> None:
    tab.close()
    tab.deleteLater()
    _settle(qapp)


def _widths(tab):
    return tab._left_col.width(), tab._center_col.width(), tab._right_col.width()


def _assert_columns_fill(tab):
    """Geometry invariant: two handles plus three columns fill the body."""
    body = tab._body
    left, preview, right = _widths(tab)
    handles = 2 * DESIGNER_HANDLE_WIDTH
    assert left + preview + right + handles == body.width()
    assert preview >= DESIGNER_PREVIEW_MIN_WIDTH
    assert tab._left_handle.x() == left
    assert tab._left_handle.width() == DESIGNER_HANDLE_WIDTH
    assert tab._center_col.x() == left + DESIGNER_HANDLE_WIDTH
    assert tab._right_handle.x() == left + DESIGNER_HANDLE_WIDTH + preview
    assert tab._right_handle.width() == DESIGNER_HANDLE_WIDTH
    assert tab._right_col.x() == (
        left + 2 * DESIGNER_HANDLE_WIDTH + preview)
    assert tab._right_col.x() + right == body.width()
    assert left >= DESIGNER_LEFT_MIN_WIDTH
    assert right >= DESIGNER_RIGHT_MIN_WIDTH
    assert left <= DESIGNER_LEFT_MAX_WIDTH
    assert right <= DESIGNER_RIGHT_MAX_WIDTH


def _drag(tab, side: str, delta: int) -> None:
    tab._on_handle_drag_started()
    tab._on_handle_dragged(side, delta)
    tab._on_handle_drag_finished()


def _visible_horizontal_scrollbars(widget):
    found = []
    for area in widget.findChildren(QScrollArea):
        if not area.isVisible():
            continue
        bar = area.horizontalScrollBar()
        if bar.maximum() > 0:
            found.append((bar.maximum(), area.viewport().width()))
    return found


# ── defaults and helper maths ───────────────────────────────────────────────

def test_shipped_default_widths(tab):
    assert _widths(tab) == (
        DESIGNER_LEFT_DEFAULT_WIDTH,
        tab._body.width() - 2 * DESIGNER_HANDLE_WIDTH
        - DESIGNER_LEFT_DEFAULT_WIDTH - DESIGNER_RIGHT_DEFAULT_WIDTH,
        DESIGNER_RIGHT_DEFAULT_WIDTH,
    )
    assert tab._left_col.width() == 260
    assert tab._right_col.width() == 300
    _assert_columns_fill(tab)


def test_tab_minimum_keeps_the_preview_alive(tab):
    assert tab.minimumWidth() == TAB_MIN_WIDTH == 880


@pytest.mark.parametrize("value,expected", [
    (-500, DESIGNER_LEFT_MIN_WIDTH),
    (0, DESIGNER_LEFT_MIN_WIDTH),
    (DESIGNER_LEFT_MIN_WIDTH, DESIGNER_LEFT_MIN_WIDTH),
    (333, 333),
    (DESIGNER_LEFT_MAX_WIDTH, DESIGNER_LEFT_MAX_WIDTH),
    (9999, DESIGNER_LEFT_MAX_WIDTH),
])
def test_clamp_column_width(value, expected):
    assert _tab_module().clamp_column_width(
        value, DESIGNER_LEFT_MIN_WIDTH,
        DESIGNER_LEFT_MAX_WIDTH) == expected


@pytest.mark.parametrize("available,left,right,expected", [
    # Both columns fit: nothing moves.
    (900, 260, 300, (260, 300)),
    # 20 px short: split 20 in proportion to each column's slack (20 / 40).
    (540, 260, 300, (254, 286)),
    # Exactly the combined slack: both land on their minimum.
    (500, 260, 300, (240, 260)),
    # Far beyond the combined slack: minimums are the floor.
    (300, 400, 400, (240, 260)),
    # Wide saved widths trimmed proportionally over their slack (240 / 260).
    (550, 480, 520, (264, 286)),
    # Already at minimum: no negative room to take.
    (400, 240, 260, (240, 260)),
])
def test_fit_side_widths(available, left, right, expected):
    assert _tab_module().fit_side_widths(available, left, right) == expected


# ── dragging ────────────────────────────────────────────────────────────────

def test_left_drag_clamps_to_min_and_max(qapp, tab):
    tab.resize(2000, 900)
    _settle(qapp)

    _drag(tab, "left", -1000)
    assert tab._left_col.width() == DESIGNER_LEFT_MIN_WIDTH

    _drag(tab, "left", 2000)
    assert tab._left_col.width() == DESIGNER_LEFT_MAX_WIDTH
    _assert_columns_fill(tab)


def test_right_drag_clamps_to_min_and_max(qapp, tab):
    tab.resize(2000, 900)
    _settle(qapp)

    # The right column's left edge follows the pointer, so a rightward drag
    # gives width back to the preview and a leftward drag adds width.
    _drag(tab, "right", 2000)
    assert tab._right_col.width() == DESIGNER_RIGHT_MIN_WIDTH

    _drag(tab, "right", -2000)
    assert tab._right_col.width() == DESIGNER_RIGHT_MAX_WIDTH
    _assert_columns_fill(tab)


def test_drag_stops_when_the_preview_reaches_its_minimum(qapp, tab):
    tab.resize(1000, 900)
    _settle(qapp)
    assert _widths(tab) == (260, 420, 300)

    _drag(tab, "left", 1000)
    assert _widths(tab) == (320, DESIGNER_PREVIEW_MIN_WIDTH, 300)

    # More pointer movement in the same direction cannot take the preview.
    _drag(tab, "left", 500)
    assert _widths(tab) == (320, DESIGNER_PREVIEW_MIN_WIDTH, 300)

    _drag(tab, "right", -1000)
    assert _widths(tab) == (320, DESIGNER_PREVIEW_MIN_WIDTH, 300)


def test_right_drag_stops_at_preview_minimum(qapp, tab):
    tab.resize(1000, 900)
    _settle(qapp)

    _drag(tab, "right", -1000)
    assert tab._right_col.width() == 360
    assert tab._center_col.width() == DESIGNER_PREVIEW_MIN_WIDTH
    _assert_columns_fill(tab)


def test_shrink_to_minimum_gives_way_before_the_preview(qapp, tab):
    tab.resize(700, 900)
    _settle(qapp)
    assert tab.width() == TAB_MIN_WIDTH
    assert _widths(tab) == (
        DESIGNER_LEFT_MIN_WIDTH,
        DESIGNER_PREVIEW_MIN_WIDTH,
        DESIGNER_RIGHT_MIN_WIDTH,
    )
    _assert_columns_fill(tab)


def test_click_without_motion_keeps_the_saved_widths(qapp, tab):
    set_setting(LEFT_KEY, str(DESIGNER_LEFT_MAX_WIDTH))
    set_setting(RIGHT_KEY, str(DESIGNER_RIGHT_MAX_WIDTH))
    _close(tab, qapp)
    widget = _make_tab(qapp, 1000, 900)
    try:
        # The window trims both columns, but the preference is still 480/520.
        assert widget._left_width == DESIGNER_LEFT_MAX_WIDTH
        assert widget._right_width == DESIGNER_RIGHT_MAX_WIDTH
        assert widget._left_col.width() < widget._left_width

        widget._on_handle_drag_started()
        widget._on_handle_drag_finished()

        assert get_setting(LEFT_KEY) == str(DESIGNER_LEFT_MAX_WIDTH)
        assert get_setting(RIGHT_KEY) == str(DESIGNER_RIGHT_MAX_WIDTH)
    finally:
        _close(widget, qapp)


# ── reset ───────────────────────────────────────────────────────────────────

def test_double_click_reset_restores_default_and_saves(qapp, tab):
    _drag(tab, "left", 80)
    assert tab._left_col.width() == 340
    assert get_setting(LEFT_KEY) == "340"

    tab._left_handle.reset_requested.emit()
    _settle(qapp)
    assert tab._left_col.width() == DESIGNER_LEFT_DEFAULT_WIDTH
    assert get_setting(LEFT_KEY) == str(DESIGNER_LEFT_DEFAULT_WIDTH)
    _assert_columns_fill(tab)

    _drag(tab, "right", -120)
    assert tab._right_col.width() == 420
    tab._right_handle.reset_requested.emit()
    _settle(qapp)
    assert tab._right_col.width() == DESIGNER_RIGHT_DEFAULT_WIDTH
    assert get_setting(RIGHT_KEY) == str(DESIGNER_RIGHT_DEFAULT_WIDTH)


# ── persistence ─────────────────────────────────────────────────────────────

def test_widths_persist_across_tab_instances(qapp, tab):
    _drag(tab, "left", 60)
    _drag(tab, "right", -40)
    assert (tab._left_width, tab._right_width) == (320, 340)
    assert get_setting(LEFT_KEY) == "320"
    assert get_setting(RIGHT_KEY) == "340"

    _close(tab, qapp)
    widget = _make_tab(qapp, 1400, 900)
    try:
        assert (widget._left_col.width(),
                widget._right_col.width()) == (320, 340)
    finally:
        _close(widget, qapp)


def test_bad_saved_widths_fall_back_or_clamp(qapp):
    set_setting(LEFT_KEY, "9999")
    set_setting(RIGHT_KEY, "not-a-number")
    widget = _make_tab(qapp, 1400, 900)
    try:
        assert widget._left_col.width() == DESIGNER_LEFT_MAX_WIDTH
        assert widget._right_col.width() == DESIGNER_RIGHT_DEFAULT_WIDTH
    finally:
        _close(widget, qapp)

    set_setting(LEFT_KEY, "-20")
    set_setting(RIGHT_KEY, "")
    widget = _make_tab(qapp, 1400, 900)
    try:
        assert widget._left_col.width() == DESIGNER_LEFT_MIN_WIDTH
        assert widget._right_col.width() == DESIGNER_RIGHT_DEFAULT_WIDTH
    finally:
        _close(widget, qapp)


def test_saved_widths_that_no_longer_fit_are_trimmed(qapp):
    set_setting(LEFT_KEY, str(DESIGNER_LEFT_MAX_WIDTH))
    set_setting(RIGHT_KEY, str(DESIGNER_RIGHT_MAX_WIDTH))
    widget = _make_tab(qapp, 1000, 900)
    try:
        left, preview, right = _widths(widget)
        assert preview == DESIGNER_PREVIEW_MIN_WIDTH
        assert left >= DESIGNER_LEFT_MIN_WIDTH
        assert right >= DESIGNER_RIGHT_MIN_WIDTH
        assert left + right == (1000 - 2 * DESIGNER_HANDLE_WIDTH
                                - DESIGNER_PREVIEW_MIN_WIDTH)
        # The preference is kept, not rewritten by the trim.
        assert (widget._left_width, widget._right_width) == (480, 520)
        _assert_columns_fill(widget)
    finally:
        _close(widget, qapp)


# ── content reflow ──────────────────────────────────────────────────────────

def test_no_horizontal_scrollbars_at_minimum_widths(qapp, tab):
    """Every page and block reflows at 240 / 260 without a horizontal bar."""
    tab.resize(1400, 1000)
    tab._left_width = DESIGNER_LEFT_MIN_WIDTH
    tab._right_width = DESIGNER_RIGHT_MIN_WIDTH
    tab._layout_columns()
    _settle(qapp)

    panel = tab._properties_panel
    checked = []

    def check(tag):
        _settle(qapp, 6)
        assert _visible_horizontal_scrollbars(panel) == [], tag
        assert _visible_horizontal_scrollbars(tab._right_col) == [], tag
        assert _visible_horizontal_scrollbars(tab._center_col) == [], tag
        checked.append(tag)

    for page in ("canvas", "container"):
        panel._pages.set_value(page, emit=True)
        check(f"scripture {page}")

    panel._pages.set_value("blocks", emit=True)
    for block in schema.BLOCK_IDS[schema.SCRIPTURE]:
        panel._on_block(block)
        check(f"scripture blocks/{block}")

    tab.set_theme("slides")
    _settle(qapp, 6)
    for page in ("canvas", "container"):
        panel._pages.set_value(page, emit=True)
        check(f"freeform {page}")
    panel._pages.set_value("blocks", emit=True)
    for block in schema.BLOCK_IDS[schema.FREEFORM]:
        panel._on_block(block)
        check(f"freeform blocks/{block}")

    tab._switch_right_tab("animations")
    check("right animations")
    tab._switch_right_tab("json")
    check("right json")

    # The loop really walked both theme kinds and every block.
    assert len(checked) == 2 + 5 + 2 + 5 + 2


def test_json_header_reflows_at_minimum_width(qapp, tab):
    """The decorative JSON label hides before its text clips at 260."""
    tab._right_width = DESIGNER_RIGHT_MIN_WIDTH
    tab._layout_columns()
    tab._switch_right_tab("json")
    _settle(qapp, 6)

    label = tab._json_header_label
    assert not label.isVisible()
    for button in (tab._btn_format, tab._btn_copy, tab._btn_apply):
        assert button.isVisible()
        assert button.width() >= button.minimumSizeHint().width()

    tab._right_width = DESIGNER_RIGHT_DEFAULT_WIDTH
    tab._layout_columns()
    _settle(qapp, 6)

    assert label.isVisible()
    assert label.width() >= label.minimumSizeHint().width()


# ── handle widget ───────────────────────────────────────────────────────────

def test_handle_contract(qapp):
    handle = ColumnHandle("right")
    handle.resize(DESIGNER_HANDLE_WIDTH, 300)
    handle.show()
    _settle(qapp)
    try:
        assert handle.side() == "right"
        assert handle.width() == DESIGNER_HANDLE_WIDTH
        assert handle.cursor().shape() == Qt.CursorShape.SplitHCursor
        assert handle.focusPolicy() == Qt.FocusPolicy.NoFocus
        assert handle.toolTip()
        assert handle.accessibleName()
    finally:
        handle.close()
        handle.deleteLater()
        _settle(qapp)


def test_handle_paint_states_differ(qapp):
    def signature(image):
        # The line runs down the centre, so a column of samples plus the grip
        # row is enough to distinguish idle, hover and dragging.
        xs = range(image.width())
        ys = (2, image.height() // 2, image.height() - 3)
        return tuple(image.pixelColor(x, y).rgba()
                     for y in ys for x in xs)

    handle = ColumnHandle("left")
    handle.resize(DESIGNER_HANDLE_WIDTH, 300)
    handle.show()
    _settle(qapp)
    try:
        # grab() paints synchronously from the current flags. Do not process
        # events between grabs: a synthetic enter/leave event would rewrite
        # the hover flag. Force idle first, since the offscreen cursor may
        # already sit inside the freshly shown handle.
        handle._hovered = False
        handle._dragging = False
        idle = signature(handle.grab().toImage())
        handle._hovered = True
        hovered = signature(handle.grab().toImage())
        handle._dragging = True
        dragging = signature(handle.grab().toImage())

        assert idle
        assert idle != hovered
        assert hovered != dragging
        assert idle != dragging
    finally:
        handle.close()
        handle.deleteLater()
        _settle(qapp)


# ── real mouse events ───────────────────────────────────────────────────────

def test_real_mouse_drag_and_double_click(qapp, tab):
    from PyQt6.QtTest import QTest

    handle = tab._left_handle
    centre = handle.rect().center()

    QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=centre)
    QTest.mouseMove(handle, centre + QPoint(40, 0), delay=5)
    QTest.mouseRelease(handle, Qt.MouseButton.LeftButton,
                       pos=centre + QPoint(40, 0))
    _settle(qapp)
    assert tab._left_col.width() == 300
    assert get_setting(LEFT_KEY) == "300"

    QTest.mouseDClick(handle, Qt.MouseButton.LeftButton,
                      pos=handle.rect().center())
    _settle(qapp)
    assert tab._left_col.width() == DESIGNER_LEFT_DEFAULT_WIDTH
    assert get_setting(LEFT_KEY) == str(DESIGNER_LEFT_DEFAULT_WIDTH)
    _assert_columns_fill(tab)


def test_handles_sit_between_columns_at_every_width(qapp, tab):
    for width in (880, 1000, 1400, 2000):
        tab.resize(width, 900)
        _settle(qapp)
        _assert_columns_fill(tab)

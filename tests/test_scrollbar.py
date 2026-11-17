"""
tests/test_scrollbar.py

Shared minimal scrollbar (ui.tokens spec): permanently reserved lane,
flat thumb, no arrows — identical behaviour on every scroll area.
"""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import (
    QApplication, QFrame, QLabel, QListWidget, QScrollArea, QTextEdit,
    QVBoxLayout, QWidget,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
import pytest

from ui import tokens
from ui.scrollbars import (
    reserve_scrollbar_lane, install as install_scrollbar_lanes,
)
from ui.styles import apply_minimal_scrollbar, MINIMAL_SCROLLBAR_CSS
from ui.widgets.scrollable import scrollable


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test"])
    return app


def test_policies_and_rules(qapp):
    area = QScrollArea()
    area.setStyleSheet("QScrollArea { background: transparent; }")
    apply_minimal_scrollbar(area)
    assert area.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOn
    assert area.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    sheet = area.styleSheet()
    assert "QScrollArea { background: transparent; }" in sheet
    assert "QScrollBar:vertical" in sheet
    assert f"width: {tokens.SCROLLBAR_THICKNESS}px" in sheet


def test_idempotent_and_widget_generic(qapp):
    lst = QListWidget()
    apply_minimal_scrollbar(lst)
    apply_minimal_scrollbar(lst)
    assert lst.styleSheet().count("QScrollBar:vertical {") == 1
    lst.show()
    qapp.processEvents()
    assert lst.verticalScrollBar().isVisibleTo(lst)


# ── reserved lane: content width must not change ──────────────────────────

def _tall_rows(count: int = 80) -> QWidget:
    inner = QWidget()
    layout = QVBoxLayout(inner)
    layout.setContentsMargins(0, 0, 0, 0)
    for index in range(count):
        layout.addWidget(QLabel(f"row {index}"))
    return inner


def _prepared(area, width: int, height: int, *, horizontal: bool = True):
    area.setStyleSheet(tokens.scrollbar_qss())
    reserve_scrollbar_lane(area, horizontal=horizontal)
    area.resize(width, height)
    area.show()
    return area


def test_scroll_area_width_is_stable_across_overflow(qapp):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(QWidget())
    _prepared(area, 260, 220)
    qapp.processEvents()
    assert area.verticalScrollBar().maximum() == 0
    short_width = area.viewport().width()

    area.setWidget(_tall_rows())
    qapp.processEvents()
    assert area.verticalScrollBar().maximum() > 0
    assert area.verticalScrollBar().isVisibleTo(area)
    assert area.viewport().width() == short_width
    area.close()


def test_list_viewport_width_is_stable_across_overflow(qapp):
    lst = QListWidget()
    _prepared(lst, 240, 200)
    qapp.processEvents()
    assert lst.verticalScrollBar().maximum() == 0
    short_width = lst.viewport().width()

    for index in range(80):
        lst.addItem(f"item {index}")
    qapp.processEvents()
    assert lst.verticalScrollBar().maximum() > 0
    assert lst.viewport().width() == short_width
    lst.close()


def test_text_editor_width_is_stable_across_overflow(qapp):
    edit = QTextEdit()
    _prepared(edit, 300, 200)
    qapp.processEvents()
    assert edit.verticalScrollBar().maximum() == 0
    short_width = edit.viewport().width()

    edit.setPlainText("\n".join(f"line {index}" for index in range(200)))
    qapp.processEvents()
    assert edit.verticalScrollBar().maximum() > 0
    assert edit.viewport().width() == short_width
    edit.close()


def test_both_axes_keep_the_viewport_size(qapp):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(QWidget())
    _prepared(area, 260, 220)
    qapp.processEvents()
    base = (area.viewport().width(), area.viewport().height())

    inner = QWidget()
    inner.setMinimumSize(700, 700)
    area.setWidget(inner)
    qapp.processEvents()
    assert area.verticalScrollBar().maximum() > 0
    assert area.horizontalScrollBar().maximum() > 0
    assert (area.viewport().width(), area.viewport().height()) == base
    area.close()


def test_scrollable_wrapper_reserves_the_vertical_lane(qapp):
    area = scrollable(_tall_rows())
    assert area.verticalScrollBarPolicy() == \
        Qt.ScrollBarPolicy.ScrollBarAlwaysOn
    assert area.horizontalScrollBarPolicy() == \
        Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    area.close()


def test_always_off_is_left_alone(qapp):
    area = QScrollArea()
    area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    assert reserve_scrollbar_lane(area) is False
    assert area.verticalScrollBarPolicy() == \
        Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert area.horizontalScrollBarPolicy() == \
        Qt.ScrollBarPolicy.ScrollBarAlwaysOff


def test_horizontal_opt_out_leaves_the_bottom_lane(qapp):
    area = QScrollArea()
    assert reserve_scrollbar_lane(area, horizontal=False) is True
    assert area.verticalScrollBarPolicy() == \
        Qt.ScrollBarPolicy.ScrollBarAlwaysOn
    assert area.horizontalScrollBarPolicy() == \
        Qt.ScrollBarPolicy.ScrollBarAsNeeded


def test_app_filter_covers_widgets_created_later(qapp):
    flt = install_scrollbar_lanes(qapp)
    try:
        edit = QTextEdit()
        assert edit.verticalScrollBarPolicy() == \
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        edit.show()
        qapp.processEvents()
        assert edit.verticalScrollBarPolicy() == \
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        assert edit.horizontalScrollBarPolicy() == \
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        edit.close()
    finally:
        qapp.removeEventFilter(flt)
        del qapp._rc_scrollbar_lane_filter
        flt.deleteLater()
        qapp.processEvents()


def test_scrollbar_theme_has_hover_drag_and_minimum_handle(qapp):
    qss = tokens.scrollbar_qss()
    for orientation in ("vertical", "horizontal"):
        assert f"QScrollBar::handle:{orientation}:hover" in qss
        assert f"QScrollBar::handle:{orientation}:pressed" in qss
        assert (f'QScrollBar[rcLaneEmpty="true"]::handle:{orientation}'
                in qss)
    assert tokens.ACCENT in qss
    assert f"min-height: {tokens.SCROLLBAR_MIN_HANDLE}px" in qss
    assert f"min-width: {tokens.SCROLLBAR_MIN_HANDLE}px" in qss


def _handle_pixels(bar) -> int:
    target = QColor(tokens.BG_CARD_HOVER).getRgb()[:3]
    image = bar.grab().toImage()
    hits = 0
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.alpha() == 0:
                continue
            rgb = (color.red(), color.green(), color.blue())
            if all(abs(rgb[i] - target[i]) <= 6 for i in range(3)):
                hits += 1
    return hits


def test_empty_lane_paints_no_handle(qapp):
    """A reserved lane with nothing to scroll must stay visually blank."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(_tall_rows(2))
    _prepared(area, 220, 160)
    qapp.processEvents()
    assert area.verticalScrollBar().maximum() == 0
    assert _handle_pixels(area.verticalScrollBar()) == 0

    area.setWidget(_tall_rows(40))
    qapp.processEvents()
    assert area.verticalScrollBar().maximum() > 0
    assert _handle_pixels(area.verticalScrollBar()) > 0

    area.setWidget(_tall_rows(2))
    qapp.processEvents()
    assert _handle_pixels(area.verticalScrollBar()) == 0
    area.close()

"""
tests/test_slide_strips.py

Preview/live strip cards: flat 2D look only (behavior untouched).
Idle = dark fill, no border. Highlighted = vibrant wash + orange edge,
same highlight language as the lite-designer slide cards.
"""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication
import pytest

from ui.panels.slide_grid_panel import SlideCard
from ui.styles import SLATE_900
from PyQt6.QtGui import QColor

_IDLE_RGB = (lambda c: (c.red(), c.green(), c.blue()))(QColor(SLATE_900))


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test"])
    return app


def _card(qapp, selected):
    card = SlideCard(0, "Line one\nLine two", {}, parent=None)
    card.resize(300, 80)
    card.set_selected(selected)
    card.show()
    qapp.processEvents()
    return card


def _px(img, x, y):
    c = img.pixelColor(x, y)
    return (c.red(), c.green(), c.blue())


def test_idle_flat_dark_no_border(qapp):
    card = _card(qapp, False)
    img = card.grab().toImage()
    w, h = card.width(), card.height()
    interior = _px(img, w // 2, h // 2)
    assert interior == _IDLE_RGB, interior  # SLATE_900
    edge = _px(img, w // 2, 1)
    assert all(abs(a - b) <= 10 for a, b in zip(edge, interior)), \
        f"border visible: edge={edge} interior={interior}"
    card.close()


def test_highlighted_vibrant_wash_orange_edge(qapp):
    card = _card(qapp, True)
    img = card.grab().toImage()
    w, h = card.width(), card.height()
    edge = _px(img, w // 2, 0)
    # Orange edge: red-dominant hue regardless of wash brightness.
    assert edge[0] - edge[2] > 40 and edge[0] > edge[1], edge
    interior = _px(img, w // 2, h // 2)
    assert interior != _IDLE_RGB, interior
    card.close()


def test_thumb_geometry_math(qapp):
    from ui.panels.slide_grid_panel import _FadeScrollBar as F
    assert F.thumb_geometry(400, 0, 400, 0) is None
    h, y = F.thumb_geometry(400, 400, 400, 0)
    assert h == 200 and y == 0
    h, y = F.thumb_geometry(400, 400, 400, 400)
    assert h == 200 and y == 200
    h, _ = F.thumb_geometry(400, 7600, 400, 0)
    assert h == F.MIN_THUMB


def _tall_scroll(qapp):
    from PyQt6.QtWidgets import QScrollArea, QWidget, QVBoxLayout, QLabel
    from ui.panels.slide_grid_panel import _FadeScrollBar
    host = QScrollArea()
    host.setWidgetResizable(True)
    inner = QWidget()
    lay = QVBoxLayout(inner)
    for i in range(30):
        lay.addWidget(QLabel(f"row {i}"))
    host.setWidget(inner)
    bar = _FadeScrollBar(host)
    host.resize(200, 200)
    host.show()
    qapp.processEvents()
    return host, bar


def test_fade_bar_shows_on_scroll_hides_on_idle(qapp):
    from PyQt6.QtCore import QPropertyAnimation
    host, bar = _tall_scroll(qapp)
    bar.hide()
    bar._effect.setOpacity(0.0)
    bar._on_fade_done()
    assert not bar._lane.isVisibleTo(host)
    host.verticalScrollBar().setValue(100)
    qapp.processEvents()
    assert bar._lane.isVisibleTo(host)
    assert bar._effect.opacity() == 1.0
    bar.hide()
    assert bar._fade.state() == QPropertyAnimation.State.Running
    bar._effect.setOpacity(0.0)
    bar._on_fade_done()
    assert not bar._lane.isVisibleTo(host)
    host.close()


def test_fade_bar_never_shows_without_overflow(qapp):
    host, bar = _tall_scroll(qapp)
    host.verticalScrollBar().setValue(0)
    qapp.processEvents()
    host.resize(200, 2000)
    qapp.processEvents()
    assert not bar._lane.isVisibleTo(host)
    host.close()


def test_strip_panels_use_overlay_not_lane(qapp):
    from PyQt6.QtCore import Qt
    from ui.panels.slide_grid_panel import SlideGridPanel, _FadeScrollBar
    for panel in (SlideGridPanel("Preview"), SlideGridPanel("Live")):
        panel.show()
        qapp.processEvents()
        assert panel._scroll.verticalScrollBarPolicy() == \
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        assert isinstance(panel._fade_bar, _FadeScrollBar)
        panel.close()

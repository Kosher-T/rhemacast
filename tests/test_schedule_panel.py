"""
tests/test_schedule_panel.py

Schedule list: Alt+click inside it must not re-add (no duplicates),
and adds must not throw the viewport back to the top.
"""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import ui.widgets.display_view  # noqa: F401  (WebEngine pre-import first)

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt
import pytest

from ui.main_window import MainWindow
from ui.panels.schedule_panel import SchedulePanel
from core.schedule_model import ScheduleModel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test"])
    return app


_OPEN_PANELS = []


@pytest.fixture(autouse=True)
def _close_panels():
    """Panels hold model signal connections; deterministic teardown
    keeps native state clean for later files (designer-file precedent)."""
    yield
    while _OPEN_PANELS:
        w = _OPEN_PANELS.pop()
        try:
            w.close()
            w.deleteLater()
        except RuntimeError:
            pass
    QApplication.instance().processEvents()


def _panel(qapp, n=30):
    model = ScheduleModel()
    panel = SchedulePanel(model=model)
    for i in range(n):
        model.add_item({"ref": f"GEN 1:{i + 1}", "_sched_uid": f"u{i}"})
    panel.resize(300, 300)
    panel.show()
    qapp.processEvents()
    _OPEN_PANELS.append(panel)
    return panel, model


def test_alt_click_guard_inside_schedule(qapp):
    panel, _ = _panel(qapp, n=3)
    assert MainWindow._press_in_schedule(
        panel.list_widget.viewport()) is True
    assert MainWindow._press_in_schedule(QWidget()) is False


def test_cursor_in_schedule_veto(qapp):
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QCursor
    panel, _ = _panel(qapp, n=3)
    vp = panel.list_widget.viewport()
    QCursor.setPos(vp.mapToGlobal(vp.rect().center()))
    qapp.processEvents()
    assert MainWindow._cursor_in_schedule() is True
    QCursor.setPos(vp.mapToGlobal(vp.rect().bottomRight() + QPoint(60, 60)))
    qapp.processEvents()
    assert MainWindow._cursor_in_schedule() is False
    # Park the virtual cursor somewhere inert and flush: a stale
    # position over torn-down widgets synthesizes enter events into
    # later tests' construction (native-state contamination).
    QCursor.setPos(QPoint(0, 0))
    qapp.processEvents()


def test_add_preserves_scroll_position(qapp):
    panel, model = _panel(qapp)
    bar = panel.list_widget.verticalScrollBar()
    assert bar.maximum() > 0
    mid = bar.maximum() // 2
    bar.setValue(mid)
    model.add_item({"ref": "GEN 1:31", "_sched_uid": "u30"})
    qapp.processEvents()
    assert panel.list_widget.count() == 31
    assert bar.value() == mid
    # At the bottom: stays pinned to the new bottom (new item visible).
    bar.setValue(bar.maximum())
    model.add_item({"ref": "GEN 1:32", "_sched_uid": "u31"})
    qapp.processEvents()
    assert bar.value() == bar.maximum()


def test_alt_drag_never_copies(qapp):
    """Alt held during a schedule drag must not flip the drop into a
    copy that clones the row: the action is forced back to Move.

    NOTE: only the session-establishing DragEnter is exercisable —
    Qt drops synthetic DragMove events with no live drag session, so
    moves are covered by code review (same branch handles them live).
    """
    from PyQt6.QtCore import QPoint, QMimeData
    from PyQt6.QtGui import QDragEnterEvent
    from PyQt6.QtWidgets import QApplication
    panel, _ = _panel(qapp, n=5)
    mime = QMimeData()
    mime.setText("x")
    ev = QDragEnterEvent(
        QPoint(10, 10),
        Qt.DropAction.CopyAction | Qt.DropAction.MoveAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.AltModifier)
    QApplication.sendEvent(panel.list_widget.viewport(), ev)
    assert ev.dropAction() == Qt.DropAction.MoveAction

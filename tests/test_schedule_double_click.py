"""Schedule double-click delivery must not depend on the platform."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import time
import pytest
from PyQt6.QtCore import Qt, QCoreApplication
from PyQt6.QtWidgets import QApplication

QCoreApplication.setAttribute(
    Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

# Module-global: if the last Python handle to the QApplication wrapper
# dies, PyQt tears down the C++ app with it and every later QWidget()
# aborts the process. (Same pattern as test_schedule_panel.py.)
_APP = []
_PANELS = []


@pytest.fixture(scope="module", autouse=True)
def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test"])
    _APP.append(app)
    return app


def _panel(tmp_path, monkeypatch):
    import core.database as db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    db.init_db()
    from core.schedule_model import ScheduleModel
    from ui.panels.schedule_panel import SchedulePanel
    model = ScheduleModel()
    panel = SchedulePanel(model=model)
    for ref, verse in (("Psalms 23:1", "1"), ("Psalms 23:2", "2")):
        model.add_item({"ref": ref, "book": "Psalms", "chapter": "23",
                        "verse": verse, "text": "x", "translation": "KJV"})
    panel.resize(360, 240)
    panel.show()
    QApplication.instance().processEvents()
    _PANELS.append(panel)
    return panel


def _fired(panel):
    seen = []
    panel.item_double_clicked.connect(lambda d: seen.append(d.get("ref")))
    return seen


def _rows(panel):
    return [panel.list_widget.item(i)
            for i in range(panel.list_widget.count())]


def test_double_click_via_the_view_signal_alone(panel_style):
    """The route Windows takes: the widget's own mouseDoubleClickEvent is
    never reached, only the view's itemDoubleClicked."""
    panel, seen = panel_style
    row = _rows(panel)[1]
    panel.list_widget.itemDoubleClicked.emit(row)
    assert seen == ["Psalms 23:2"], seen


def test_double_click_via_the_row_widget_alone(panel_style):
    """The route Linux takes: only the row widget's signal fires."""
    panel, seen = panel_style
    widget = _rows(panel)[1].data(Qt.ItemDataRole.UserRole + 1)
    widget.double_clicked.emit()
    assert seen == ["Psalms 23:2"], seen


def test_both_routes_fire_exactly_once(panel_style):
    """Where both fire, the handler must still run ONCE — twice would push
    the verse to live twice."""
    panel, seen = panel_style
    row = _rows(panel)[1]
    widget = row.data(Qt.ItemDataRole.UserRole + 1)
    widget.double_clicked.emit()
    panel.list_widget.itemDoubleClicked.emit(row)
    assert seen == ["Psalms 23:2"], f"emitted {len(seen)} times: {seen}"


def test_a_later_double_click_still_works(panel_style):
    """The once-only guard must not swallow the NEXT double-click."""
    panel, seen = panel_style
    for _ in range(2):
        widget = _rows(panel)[1].data(Qt.ItemDataRole.UserRole + 1)
        widget.double_clicked.emit()
        time.sleep(0.5)          # past doubleClickInterval
    assert seen == ["Psalms 23:2", "Psalms 23:2"], seen


def test_the_widget_really_does_ignore_the_press(panel_style):
    """Why the widget route is untrustworthy: the press is ignored so the
    view owns selection, which leaves the double-click's delivery up to
    event propagation."""
    from PyQt6.QtCore import QEvent, QPointF
    from PyQt6.QtGui import QMouseEvent
    panel, _seen = panel_style
    widget = _rows(panel)[0].data(Qt.ItemDataRole.UserRole + 1)
    p = QPointF(5.0, 5.0)
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, p, p,
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    widget.mousePressEvent(ev)
    assert ev.isAccepted() is False, (
        "press is accepted now — the fragile path is gone, update this test")


@pytest.fixture
def panel_style(tmp_path, monkeypatch):
    panel = _panel(tmp_path, monkeypatch)
    return panel, _fired(panel)

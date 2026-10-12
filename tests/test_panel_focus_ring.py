"""Panel focus rings: the Bible (BrowserPanel) and Schedule panels show a
themed outline while they — or any child — hold focus, lose it cleanly,
never reflow the panel's contents, and never swallow mouse events.

Note on baselines: Qt auto-focuses a panel's first focusable child on
show(), so "unfocused" must be established by moving focus to a widget
OUTSIDE the panel, not by sampling it right after show().
"""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel, QSplitter
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt
import pytest

import core.database as db

_app = None


def _qt():
    global _app
    _app = QApplication.instance()
    if _app is None:
        _app = QApplication(["t"])
    return _app


_HOSTS = []


def _host(*panels):
    """Put panels in a host with a focusable outside widget.

    Kept alive for the whole module: a top-level widget that is garbage
    collected takes its children (and the panels under test) with it.
    """
    _qt()
    host = QWidget()
    lay = QVBoxLayout(host)
    for p in panels:
        lay.addWidget(p)
    outside = QLineEdit()
    outside.setObjectName("outside")
    lay.addWidget(outside)
    host.resize(400, 300)
    host.show()
    _qt().processEvents()
    _HOSTS.append(host)
    return host, outside


def _focusable_child(panel):
    """Any focusable descendant (QLineEdit or QAbstractButton)."""
    from PyQt6.QtWidgets import QAbstractButton, QAbstractSpinBox
    for cls in (QLineEdit, QAbstractButton, QAbstractSpinBox):
        child = panel.findChild(cls)
        if child is not None:
            return child
    return None


def _blink_panel():
    _qt()
    db.DB_PATH = "/tmp/test_focus_ring_app.db"
    db.init_db()
    from ui.panels.browser_panel import BrowserPanel
    return BrowserPanel(translations=["KJV"])


def _schedule_panel():
    _qt()
    db.DB_PATH = "/tmp/test_focus_ring_app.db"
    db.init_db()
    # The ScheduleModel is a module-level singleton: another test that
    # tore the app down may have left it deleted, and a fresh C++ instance
    # is the only way to get a usable panel.
    from core import schedule_model as sm
    from PyQt6.QtCore import QObject
    if isinstance(sm.schedule_model, QObject) \
            and not _alive(sm.schedule_model):
        sm.schedule_model = sm.ScheduleModel()
    from ui.panels.schedule_panel import SchedulePanel
    return SchedulePanel()


def _alive(obj):
    try:
        obj.objectName()
        return True
    except RuntimeError:
        return False


def _edge(img):
    """Leftmost columns at mid-height, for ring-presence assertions."""
    mid = img.height() // 2
    return [img.pixelColor(x, mid).getRgb()[:3] for x in range(3)]


def _accent_columns(img):
    """Which of the leftmost 3 columns carry the accent hue."""
    return [x for x, rgb in enumerate(_edge(img)) if _is_accent(rgb)]


def _is_accent(rgb) -> bool:
    """Does this pixel read as the accent (hue-carrying) rather than panel bg?"""
    from ui import app_theme
    r, g, b = rgb[:3]
    accent = QColor(app_theme.color("accent")).getRgb()[:3]
    return r > 90 and b > 90 and g < min(r, b)


# ─── the helper ────────────────────────────────────────────────────────────

def test_ring_follows_child_focus():
    from ui.focus_ring import install_focus_ring, remove_focus_ring
    _qt()
    panel = QWidget()
    lay = QVBoxLayout(panel)
    inner = QLineEdit()
    lay.addWidget(inner)
    _host_outside, outside = _host(panel)
    install_focus_ring(panel)
    overlay = panel._focus_ring_overlay

    # Qt auto-focuses the first focusable child on show(); move focus out
    # of the panel first so the baseline is genuinely unfocused.
    outside.setFocus()
    _qt().processEvents()
    assert overlay.isVisible() is False, "ring off when focus is outside"

    inner.setFocus()
    _qt().processEvents()
    assert overlay.isVisible() is True, "child focus must light the ring"

    outside.setFocus()
    _qt().processEvents()
    assert overlay.isVisible() is False, "focus leaving must clear it"
    remove_focus_ring(panel)


def test_ring_is_mouse_transparent():
    """The ring must never intercept clicks meant for the panel."""
    _qt()
    from ui.focus_ring import install_focus_ring, remove_focus_ring, sync_focus_ring
    panel = QWidget()
    lay = QVBoxLayout(panel)
    edit = QLineEdit()
    lay.addWidget(edit)
    _host(panel)
    install_focus_ring(panel)
    overlay = panel._focus_ring_overlay
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert overlay.focusPolicy() == Qt.FocusPolicy.NoFocus
    # WA_TransparentForMouseEvents means hit-testing falls THROUGH the
    # overlay to whatever is beneath — the panel's own content.
    panel.resize(300, 200)
    _qt().processEvents()
    sync_focus_ring(panel)
    assert overlay.geometry() == panel.rect()
    remove_focus_ring(panel)


def test_ring_install_is_idempotent_and_removable():
    from ui.focus_ring import install_focus_ring, remove_focus_ring
    _qt()
    panel = QWidget()
    _host(panel)
    install_focus_ring(panel)
    first = panel._focus_ring_overlay
    install_focus_ring(panel)  # second call must be a no-op
    assert panel._focus_ring_overlay is first
    remove_focus_ring(panel)
    assert panel._focus_ring_installed is False


def test_ring_survives_panel_teardown():
    """A destroyed panel must not raise when focus moves afterwards."""
    from ui.focus_ring import install_focus_ring
    _qt()
    host, outside = _host()
    panel = QWidget()
    lay = QVBoxLayout(host)
    edit = QLineEdit()
    lay.addWidget(panel)
    lay.addWidget(edit)
    _qt().processEvents()
    install_focus_ring(panel)
    panel.setParent(None)   # detach so the host can outlive it
    panel.deleteLater()
    _qt().processEvents()
    edit.setFocus()
    _qt().processEvents()  # must not raise


# ─── both real panels carry a ring ──────────────────────────────────────────

@pytest.mark.parametrize("factory", [_blink_panel, _schedule_panel])
def test_real_panels_do_not_self_install_ring(factory):
    """The real panels no longer install their own ring.

    Ring ownership moved to PresentationTab's FocusRingStateMachine: the
    work-area ring wraps browser+queue together, and the schedule ring
    wraps the schedule wrapper so the two can light up as one composite.
    Self-installing here would double-ring the browser and show a third,
    unrelated schedule outline.
    """
    panel = factory()
    try:
        assert getattr(panel, "_focus_ring_installed", False) is False, factory.__name__
        assert getattr(panel, "_focus_ring_overlay", None) is None, factory.__name__
    finally:
        panel.deleteLater()


class _StubState:
    """Minimal stand-in for the live-display payload the state reads."""

    def __init__(self, item_type=None):
        self.item_type = item_type


def _ring_fixture():
    """Build the two ring regions with a controllable 'what is on live'.

    The work region mirrors the real layout: a plain container holding a
    QSplitter. Parenting the ring overlay straight to a QSplitter does not
    work — its layout engine repositions children, so the overlay drifts
    off the edge. The container is what makes the ring track reliably.
    """
    from ui.focus_ring import FocusRingStateMachine

    schedule = QWidget()
    sched_layout = QVBoxLayout(schedule)
    sched_edit = QLineEdit()
    sched_layout.addWidget(sched_edit)

    work_box = QWidget()
    box_layout = QVBoxLayout(work_box)
    box_layout.setContentsMargins(0, 0, 0, 0)
    work = QSplitter(Qt.Orientation.Horizontal)
    browser = QWidget()
    browser_layout = QVBoxLayout(browser)
    search_edit = QLineEdit()          # stands in for FTS / fuzzy query
    browser_layout.addWidget(search_edit)
    work.addWidget(browser)
    box_layout.addWidget(work)

    host, outside = _host(schedule, work_box)
    state = _StubState()
    machine = FocusRingStateMachine(
        work_box, schedule,
        work_area_of_schedule=lambda: state.item_type != "slide",
    )
    # Qt auto-focuses the first focusable child on show(), which would land
    # on the schedule edit. Park focus outside both regions so "resting"
    # means genuinely unfocused-by-schedule.
    outside.setFocus()
    _qt().processEvents()
    return {
        "machine": machine, "state": state, "host": host,
        "work": work_box, "schedule": schedule, "outside": outside,
        "sched_edit": sched_edit, "search_edit": search_edit,
    }


def _ring_on(widget) -> bool:
    """Overlay visibility, independent of whether the host is on screen."""
    return not widget._focus_ring_overlay.isHidden()


def test_work_ring_lights_on_resting_scripture_state():
    """Scripture on live is the resting state: the work area is lit."""
    fx = _ring_fixture()
    try:
        assert _ring_on(fx["work"]) is True
        assert _ring_on(fx["schedule"]) is False
    finally:
        fx["machine"].dispose()
        fx["host"].close()


def test_schedule_focus_lights_both_regions_as_one_context():
    """Schedule focus lights schedule AND work area — the composite."""
    fx = _ring_fixture()
    try:
        fx["sched_edit"].setFocus()
        _qt().processEvents()
        assert _ring_on(fx["schedule"]) is True
        assert _ring_on(fx["work"]) is True
    finally:
        fx["machine"].dispose()
        fx["host"].close()


def test_work_ring_hides_while_search_box_focused():
    """Typing in a search box: the box is the target, so no work ring."""
    fx = _ring_fixture()
    try:
        fx["search_edit"].setFocus()
        _qt().processEvents()
        assert _ring_on(fx["work"]) is False
        assert _ring_on(fx["schedule"]) is False
    finally:
        fx["machine"].dispose()
        fx["host"].close()


def test_work_ring_hides_when_deck_is_on_live():
    """A deck on live means slide work: the scripture work ring steps aside."""
    fx = _ring_fixture()
    try:
        fx["state"].item_type = "slide"
        fx["machine"].update()
        assert _ring_on(fx["work"]) is False
        # Back to scripture and the ring returns.
        fx["state"].item_type = None
        fx["machine"].update()
        assert _ring_on(fx["work"]) is True
    finally:
        fx["machine"].dispose()
        fx["host"].close()


def test_work_ring_paints_accent_on_its_edge():
    """The work-area outline paints the accent on exactly ONE pixel column.

    Spec: the ring is 1px. At 1px with a half-pixel inset the stroke lands on
    column 0, so the assertion counts accent columns rather than sampling a
    fixed one — it pins both "it is there" and "it is not 2px fat".
    """
    fx = _ring_fixture()
    try:
        # Grab with the ring OFF (deck on live), then with it ON (scripture).
        fx["state"].item_type = "slide"
        fx["machine"].update()
        _qt().processEvents()
        off_img = fx["work"].grab().toImage()
        assert _accent_columns(off_img) == [], _edge(off_img)

        fx["state"].item_type = None
        fx["machine"].update()
        _qt().processEvents()
        on_img = fx["work"].grab().toImage()
        columns = _accent_columns(on_img)
        assert columns, _edge(on_img)
        assert len(columns) == 1, (
            f"ring must be exactly 1px, accent spans columns {columns}: "
            f"{_edge(on_img)}"
        )
        from ui import app_theme
        r, g, b = _edge(on_img)[columns[0]]
        accent = QColor(app_theme.color("accent")).getRgb()[:3]
        assert r > 90 and b > 90 and g < min(r, b), ((r, g, b), accent)
    finally:
        fx["machine"].dispose()
        fx["host"].close()


@pytest.mark.parametrize("factory", [_blink_panel, _schedule_panel])
def test_ring_toggle_does_not_reflow(factory):
    """Focus toggling must not change the panel's size (an overlay can
    never push content around)."""
    from ui.focus_ring import refresh_focus_ring, remove_focus_ring
    panel = factory()
    host, outside = _host(panel)
    try:
        before = panel.size()
        outside.setFocus()
        _qt().processEvents()
        refresh_focus_ring(panel)
        child = _focusable_child(panel)
        assert child is not None, factory.__name__
        child.setFocus()
        _qt().processEvents()
        refresh_focus_ring(panel)
        assert panel.size() == before, (before, panel.size())
    finally:
        remove_focus_ring(panel)
        host.close()


def test_ring_follows_resize():
    from ui.focus_ring import install_focus_ring, remove_focus_ring, sync_focus_ring
    _qt()
    panel = QWidget()
    lay = QVBoxLayout(panel)
    edit = QLineEdit()
    lay.addWidget(edit)
    _host(panel)
    install_focus_ring(panel)
    edit.setFocus()
    _qt().processEvents()
    panel.resize(333, 222)
    _qt().processEvents()
    sync_focus_ring(panel)
    assert panel._focus_ring_overlay.geometry() == panel.rect()
    remove_focus_ring(panel)


def test_ring_tracks_window_resize_automatically():
    """The ring must follow the panel through a window resize with NO
    manual sync call.

    Regression: the resize hook was a plain module-level function, which
    PyQt6's installEventFilter rejects with TypeError — so every install
    silently aborted halfway. The overlay was created (and lit on focus),
    but nothing ever re-synced it, freezing the ring at its first-paint
    size while the window kept growing. Resizing the host window here must
    move the overlay on its own.
    """
    from ui.focus_ring import install_focus_ring, remove_focus_ring
    _qt()
    panel = QWidget()
    lay = QVBoxLayout(panel)
    edit = QLineEdit()
    lay.addWidget(edit)
    host, outside = _host(panel)
    install_focus_ring(panel)

    outside.setFocus()
    _qt().processEvents()
    edit.setFocus()
    _qt().processEvents()
    overlay = panel._focus_ring_overlay
    assert overlay.isVisible() is True, "precondition: ring is lit"
    assert overlay.geometry() == panel.rect(), (
        "precondition: ring matches panel before resize",
        overlay.geometry(), panel.rect())

    host.resize(host.width() + 200, host.height() + 150)
    _qt().processEvents()
    assert overlay.geometry() == panel.rect(), (
        "ring did not track the window resize",
        overlay.geometry(), panel.rect())
    remove_focus_ring(panel)

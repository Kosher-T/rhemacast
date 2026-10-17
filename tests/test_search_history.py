"""Search-box history (FTS / Fuzzy / deck search) and focus-select-all.

Two operator-facing contracts:

1. SESSION-ONLY HISTORY. Up/Down walk qualifying queries and overwrite the
   box, like a shell. Nothing is persisted — the entries live on a Python
   list, so closing the app wipes them. A query only qualifies when the
   operator shows they meant it: 2s idle, or they clicked a hit, or they
   scrolled the results (render-time scrolling must not count).

2. FOCUS SELECT-ALL. Focusing a search box highlights everything in it, so
   typing starts a new query with no manual highlight first.
"""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import Qt, QCoreApplication
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

import pytest

_app = None


def _qt():
    # Module-global: if the last Python handle to the QApplication wrapper
    # dies, PyQt tears down the C++ app and later QWidget() aborts.
    global _app
    _app = QApplication.instance()
    if _app is None:
        _app = QApplication(["t"])
    return _app


_HOSTS = []


def _field():
    """A search box, as the panels now have one: a plain QLineEdit."""
    from PyQt6.QtWidgets import QLineEdit
    _qt()
    host = QWidget()
    lay = QVBoxLayout(host)
    field = QLineEdit()
    lay.addWidget(field)
    host.resize(400, 80)
    host.show()
    _qt().setActiveWindow(host)
    _qt().processEvents()
    _HOSTS.append(host)
    return field


def _history(**kwargs):
    from ui.widgets.search_history import SearchHistory
    field = _field()
    return SearchHistory(field, **kwargs), field


# ─── qualifying: idle ───────────────────────────────────────────────────────

def test_typing_then_idle_qualifies_the_query():
    hist, field = _history(idle_ms=40)
    field.setText("rapture")
    _qt().processEvents()
    assert hist.entries == []          # not yet: typing just started
    assert hist._idle_timer.isActive()
    assert hist._idle_timer.interval() == 40
    hist._on_idle()
    assert hist.entries == ["rapture"]


def test_every_keystroke_alone_never_qualifies():
    """The whole point: keystrokes are searches, so only the settled query
    counts — not each prefix on the way there."""
    hist, field = _history(idle_ms=40)
    for ch in "rapture":
        field.setText(field.text() + ch)
        _qt().processEvents()
        hist._idle_timer.stop()        # keep typing (never idle)
    assert hist.entries == []


def test_blank_box_never_arms_idle():
    hist, field = _history(idle_ms=40)
    field.setText("x")
    _qt().processEvents()
    assert hist._idle_timer.isActive()
    field.setText("   ")
    _qt().processEvents()
    assert not hist._idle_timer.isActive()


def test_whitespace_only_query_is_not_added():
    hist, _field_obj = _history()
    assert hist.add("   ") is False
    assert hist.entries == []


# ─── qualifying: click / scroll ─────────────────────────────────────────────

def test_note_used_qualifies_immediately():
    hist, field = _history(idle_ms=10000)
    field.setText("two thrones")
    _qt().processEvents()
    assert hist.note_used() is True
    assert hist.entries == ["two thrones"]
    # and it cancelled the pending idle wait
    assert not hist._idle_timer.isActive()


def test_scroll_before_settle_is_not_a_user_scroll():
    """Rendering scrolls the list itself; that must not qualify anything."""
    from PyQt6.QtWidgets import QScrollBar
    hist, field = _history()
    bar = QScrollBar()
    hist.bind_scroll(bar)
    field.setText("no results here")
    hist.arm_scroll()                  # render just happened
    bar.setValue(40)                   # render-time movement
    _qt().processEvents()
    assert hist.entries == []
    hist._on_scroll_settled()          # settle window elapses
    bar.setValue(90)                   # now the operator scrolls
    _qt().processEvents()
    assert hist.entries == ["no results here"]


def test_scroll_without_arm_never_qualifies():
    from PyQt6.QtWidgets import QScrollBar
    hist, field = _history()
    bar = QScrollBar()
    hist.bind_scroll(bar)
    field.setText("never armed")
    _qt().processEvents()
    bar.setValue(30)
    _qt().processEvents()
    assert hist.entries == []


# ─── recall semantics ───────────────────────────────────────────────────────

def test_up_overwrites_with_previous_entry():
    hist, field = _history()
    hist.add("first")
    hist.add("second")           # newest first
    field.setText("draft")
    assert hist.previous() == "second"
    assert hist.previous() == "first"
    assert hist.previous() == "first"   # clamps at oldest


def test_down_returns_then_restores_draft():
    hist, field = _history()
    hist.add("first")
    hist.add("second")
    field.setText("draft")
    hist.previous()
    hist.previous()
    assert hist.next() == "second"
    assert hist.next() == "draft"      # what was there before navigating


def test_recall_writes_the_box_and_does_not_requalify():
    hist, field = _history(idle_ms=40)
    hist.add("alpha")
    hist.add("beta")
    hist.previous()
    _qt().processEvents()
    assert field.text() == "beta"
    # The recall write must not re-arm idle or re-add the entry.
    assert not hist._idle_timer.isActive()
    hist._on_idle()
    assert hist.entries == ["beta", "alpha"]


def test_up_key_overwrites_box_contents():
    """Up in the box itself (not just the API) replaces the text."""
    from PyQt6.QtTest import QTest
    hist, field = _history()
    hist.add("only")
    field.setFocus()
    _qt().processEvents()
    QTest.keyClick(field, Qt.Key.Key_Up)
    _qt().processEvents()
    assert field.text() == "only"


def test_typing_abandons_recall_walk():
    hist, field = _history()
    hist.add("one")
    hist.add("two")
    hist.previous()
    assert hist._nav_index is not None
    field.setText("two edited")
    _qt().processEvents()
    assert hist._nav_index is None
    # A fresh walk starts from the newest entry again
    assert hist.previous() == "two"


def test_new_query_resets_nav_position():
    hist, _f = _history()
    hist.add("a")
    hist.add("b")
    hist.previous()
    hist.previous()
    hist.add("c")                  # a fresh qualifying search
    assert hist.previous() == "c"


def test_duplicate_consecutive_query_is_not_repeated():
    hist, field = _history()
    field.setText("same")
    assert hist.add("same") is True
    assert hist.add("same") is False
    assert hist.entries == ["same"]


def test_history_is_capped_and_newest_first():
    hist, _f = _history(max_entries=3)
    for q in ("q1", "q2", "q3", "q4"):
        hist.add(q)
    assert hist.entries == ["q4", "q3", "q2"]


def test_clear_wipes_session_history():
    hist, _f = _history()
    hist.add("gone")
    hist.clear()
    assert hist.entries == []


# ─── focus select-all ───────────────────────────────────────────────────────




def _click(widget, pos=None, settle_ms=500):
    """Deliver a real left click to the widget.

    Handed straight to the handlers instead of via QTest: under the
    offscreen platform QTest DROPS clicks aimed at a widget that already
    has focus (the auto-focused search box is exactly that case), so the
    real-app scenario would silently test nothing.

    `settle_ms` defaults BEYOND the double-click interval so consecutive
    calls are independent clicks; pass a small value only when the test is
    deliberately building a double/triple-click.
    """
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    point = pos or QPointF(widget.rect().center())
    widget.mousePressEvent(QMouseEvent(
        QEvent.Type.MouseButtonPress, point,
        QPointF(widget.mapToGlobal(point.toPoint())),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier))
    _qt().processEvents()
    from PyQt6.QtTest import QTest
    QTest.qWait(settle_ms)




def _focus(widget):
    """Give the widget keyboard focus and let the focus watcher run."""
    widget.setFocus()
    _qt().processEvents()
    from PyQt6.QtTest import QTest
    QTest.qWait(40)


def _dark_area(field):
    """A point inside the box but past the end of its text."""
    from PyQt6.QtCore import QPointF
    return QPointF(field.rect().right() - 4, field.rect().center().y())



# ─── panel wiring ───────────────────────────────────────────────────────────

def test_fts_panel_has_history_wired_to_its_box(monkeypatch, tmp_path):
    import core.database as db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    db.init_db()
    from ui.panels.fts_search_panel import FtsSearchPanel
    panel = FtsSearchPanel()
    hist = panel._search_history
    assert hist is not None
    # The history watches the panel's own query box.
    assert hist._field is panel.query_input
    hist.add("wisdom")
    assert hist.entries == ["wisdom"]


def test_deck_panel_history_wired_to_search_box(monkeypatch, tmp_path):
    import core.database as db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    db.init_db()
    from ui.panels.deck_list_panel import DeckListPanel
    panel = DeckListPanel()
    hist = panel._search_history
    assert hist is not None
    assert hist._field is panel.search_box
    hist.add("grace")
    assert "grace" in hist.entries


def test_up_does_not_rewrite_the_box_with_its_own_current_query():
    """Regression: the current query qualifies for history like any other,
    so a naive entries[0] recall rewrote the box with ITSELF — wasting the
    press and re-running the same search. The first Up must land on the
    query BEFORE the current one."""
    hist, field = _history()
    hist.add("alpha")
    hist.add("beta")            # beta is newest AND currently in the box
    field.setText("beta")
    _qt().processEvents()
    assert hist.previous() == "alpha"
    assert field.text() == "alpha"


def test_up_with_only_the_current_query_does_nothing():
    """Nothing older than the current query: Up is a no-op, not a self-
    rewrite (which would re-run the same search)."""
    hist, field = _history()
    hist.add("solo")
    field.setText("solo")
    _qt().processEvents()
    assert hist.previous() is None
    assert field.text() == "solo"


def test_recall_never_rewrites_identical_text():
    """No needless textChanged -> no needless re-search."""
    hist, field = _history()
    hist.add("x")
    hist.add("y")
    field.setText("y")
    _qt().processEvents()
    hist.previous()            # -> "x"
    hist.next()                # back to "y", which IS what the box holds
    _qt().processEvents()
    assert field.text() == "y"


def test_history_constants_match_spec():
    from core.constants import SEARCH_HISTORY_IDLE_MS, SEARCH_HISTORY_MAX_ENTRIES
    assert SEARCH_HISTORY_IDLE_MS == 2000
    assert SEARCH_HISTORY_MAX_ENTRIES > 0

def test_switching_to_search_tab_by_click_focuses_and_selects(monkeypatch, tmp_path):
    """Clicking the Keyword tab is as much "go search" as the hotkey is.

    Regression: _switch_tab() only set the stack index, so a tab CLICK left
    the query box unfocused and unselected — the operator clicked a search
    tab and still had to click into the box and highlight it by hand.
    """
    import core.database as db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    db.init_db()
    from PyQt6.QtWidgets import QWidget, QVBoxLayout
    from ui.panels.queue_panel import QueuePanel

    _qt()
    panel = QueuePanel()
    host = QWidget()
    QVBoxLayout(host).addWidget(panel)
    host.resize(1000, 500)
    host.show()
    _qt().setActiveWindow(host)
    _qt().processEvents()
    _HOSTS.append(host)

    panel._ensure_fts_search_loaded()
    _qt().processEvents()
    field = panel._fts_search_panel.query_input
    field.setText("previous query")
    _qt().processEvents()

    panel._switch_tab("queue")
    _qt().processEvents()
    panel._switch_tab("keyword")
    _qt().processEvents()
    from PyQt6.QtTest import QTest
    QTest.qWait(40)

    assert field.hasFocus(), "tab click must hand the operator the box"
    assert field.selectedText() == "previous query", (
        "tab click must also highlight what is in the box")

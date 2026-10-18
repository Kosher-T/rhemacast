"""Prev/Next navigation semantics, and the separate schedule-item hotkeys.

Contract under test (an operator-facing decision, not an implementation
detail):

  Left / Right  ("Next"/"Previous Verse")
      scripture on live  -> step to the adjacent VERSE
      deck on live       -> step through that deck's SLIDES
      at a boundary      -> do nothing (never fall through to the schedule)

  Alt+Left / Alt+Right ("Prev Item"/"Next Item")
      -> step through SCHEDULE items, decks included

The point of the split: a schedule item pushed to live is a *starting
point*. Stepping onward must walk what is displayed (neighbouring verses,
the deck's own slides) and stop there — an exhausted deck or a boundary
verse must not silently jump to the next schedule item. Schedule traversal
is its own explicit hotkey.

These are no-Qt tests: the handlers are unbound and the instance is a bare
namespace, so this needs no DB, no WebEngine, and no event loop.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt, QCoreApplication
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel

# main_window transitively imports QtWebEngine, which raises unless this is
# set BEFORE any QApplication is constructed. Done at import time so test
# order within the module cannot change the outcome.
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

import pytest

# Top-level windows are kept alive for the whole module: creating one after
# closing another aborts the offscreen QApplication, and focusWidget() only
# ever reports the active window's focus.
_KEEP_ALIVE = []


class _FakeDisplay:
    """Stand-in for DisplayState.

    Needed because `_current_display` / `_current_from_schedule` are
    properties that read and write `self._display`; bypassing __init__ means
    providing that one collaborator by hand.
    """

    # Step routing / preview replay: this stub steps locally and has no
    # stored preview payload (the real DisplayState routes by content owner
    # and replays preview pushes — see core/display_state.py).
    def dispatch_step(self, delta):
        return False

    def matching_preview_payload(self):
        return None
    def __init__(self):
        self.live_data = None
        self.live_sched_uid = None
        self.live_from_schedule = False


def _tab(**overrides):
    """A bare PresentationTab stand-in carrying only the nav state.

    `_step_schedule` is recorded, not run, so any bleed from prev/next
    into the schedule is directly observable.
    """
    from ui.tabs.presentation_tab import PresentationTab

    tab = PresentationTab.__new__(PresentationTab)
    tab.steps = []
    tab._display = _FakeDisplay()
    tab._current_sched_data = None
    tab._prev_verse_data = None
    tab._next_verse_data = None
    tab.navigated = []
    tab.applied_slides = []
    for key, value in overrides.items():
        setattr(tab, key, value)

    def _record_step(delta):
        tab.steps.append(delta)

    def _navigate(verse_data, version, skip_navigator=False):
        tab.navigated.append((verse_data, version, skip_navigator))

    def _apply_slide_display(sched_data, deck_title, slides, index, uncloak=False):
        tab.applied_slides.append(index)

    tab._step_schedule = _record_step
    tab._navigate_to_bible_verse = _navigate
    tab._apply_slide_display = _apply_slide_display
    return tab


def _scripture(verse="1", chapter="1", book="Genesis"):
    return {
        "text": f"verse {chapter}:{verse}",
        "book": book,
        "chapter": chapter,
        "verse_num": verse,
        "version": "KJV",
    }


def _deck(index, count=3, uid="deck-1"):
    return {
        "item_type": "slide",
        "text": f"slide {index}",
        "slides": [{"text": f"slide {i}"} for i in range(count)],
        "slide_index": index,
        "deck_title": "Sermon",
        "slides_count": count,
    }, {"_sched_uid": uid}


# ─── scripture: adjacent verses, never the schedule ────────────────────────

def test_next_verse_navigates_to_adjacent_verse():
    tab = _tab(_current_display=_scripture("1"),
               _next_verse_data={"book": "Genesis", "chapter": 1, "verse": 2,
                                 "text": "The earth was without form"})
    tab._on_next_verse()
    assert len(tab.navigated) == 1
    assert tab.navigated[0][0]["verse"] == 2
    assert tab.steps == [], "next must not touch the schedule"


def test_prev_verse_navigates_to_adjacent_verse():
    tab = _tab(_current_display=_scripture("2"),
               _prev_verse_data={"book": "Genesis", "chapter": 1, "verse": 1,
                                 "text": "In the beginning"})
    tab._on_prev_verse()
    assert tab.navigated[0][0]["verse"] == 1
    assert tab.steps == []


def test_scripture_from_schedule_does_not_step_schedule():
    """The regression this whole split exists for: a schedule verse on live
    must step to the NEIGHBOURING VERSE, not the next schedule item."""
    tab = _tab(_current_display=_scripture("12"),
               _current_sched_data={"_sched_uid": "s1"},
               _current_from_schedule=True,
               _next_verse_data={"book": "Genesis", "chapter": 1, "verse": 13,
                                 "text": "next verse"})
    tab._on_next_verse()
    assert tab.steps == [], "schedule bleed: prev/next must not step the schedule"
    assert tab.navigated[0][0]["verse"] == 13, "expected the adjacent verse"


def test_scripture_at_a_bible_boundary_does_nothing():
    """Genesis 1:1 has no PREVIOUS verse — stay put, do not wrap.

    Only "previous" is a boundary here: the next verse is Genesis 1:2, and
    walking to it is the whole point of prev/next. What must never happen
    at either boundary is a fall-through into the schedule.
    """
    tab = _tab(_current_display=_scripture("1"),
               _current_sched_data={"_sched_uid": "s1"},
               _current_from_schedule=True,
               _prev_verse_data=None, _next_verse_data=None)
    tab._on_prev_verse()
    assert tab.navigated == [], "walked past the first verse"
    assert tab.steps == [], "fell through to the schedule at a boundary"


def test_next_at_genesis_1_1_walks_to_the_adjacent_verse():
    """The other half of the boundary case: next is NOT a boundary.

    Regression guard for the self-healing neighbour lookup — with an empty
    queue it recomputes, and must land on the adjacent VERSE rather than
    doing nothing or reaching for a schedule item.
    """
    tab = _tab(_current_display=_scripture("1"),
               _current_sched_data={"_sched_uid": "s1"},
               _current_from_schedule=True,
               _prev_verse_data=None, _next_verse_data=None)
    tab._on_next_verse()
    assert tab.steps == [], "fell through to the schedule"
    assert len(tab.navigated) == 1, "next did nothing at a non-boundary"
    verse, _version, _skip = tab.navigated[0]
    assert verse["book"] == "Genesis" and verse["chapter"] == 1 \
        and verse["verse"] == 2


def test_neighbours_are_recomputed_when_the_queue_is_stale():
    """prev/next must not depend on the live_data hook having fired.

    A schedule verse pushed by any path that skipped the hook would
    otherwise leave the operator pressing a button that silently does
    nothing — which is exactly the symptom of the bug this guards.
    """
    tab = _tab(_current_display=_scripture("22", "7", "Matthew"),
               _current_sched_data={"_sched_uid": "s1"},
               _current_from_schedule=True,
               _prev_verse_data=None, _next_verse_data=None)
    tab._on_next_verse()
    assert tab.steps == []
    assert len(tab.navigated) == 1
    verse, _v, _s = tab.navigated[0]
    assert verse["verse"] == 23, verse
    assert tab._next_verse_data is not None, "queue not repopulated"


def test_a_display_with_no_verse_neighbours_stays_put():
    """Nothing to walk to and nothing to fall back on: do nothing."""
    tab = _tab(_current_display={"item_type": "verse"},
               _current_sched_data={"_sched_uid": "s1"},
               _current_from_schedule=True,
               _prev_verse_data=None, _next_verse_data=None)
    tab._on_prev_verse()
    tab._on_next_verse()
    assert tab.steps == []
    assert tab.navigated == []


# ─── decks: own slides only, boundaries are a dead stop ────────────────────

def test_next_steps_through_deck_slides():
    display, sched = _deck(index=0, count=3)
    tab = _tab(_current_display=display, _current_sched_data=sched,
               _current_from_schedule=True)
    tab._on_next_verse()
    assert tab.applied_slides == [1]
    assert tab.steps == []


def test_prev_steps_through_deck_slides():
    display, sched = _deck(index=2, count=3)
    tab = _tab(_current_display=display, _current_sched_data=sched,
               _current_from_schedule=True)
    tab._on_prev_verse()
    assert tab.applied_slides == [1]
    assert tab.steps == []


def test_last_slide_next_does_nothing():
    """The bug this fixes: an exhausted deck fell through to the next
    schedule item, so Right at the last slide jumped items."""
    display, sched = _deck(index=2, count=3)
    tab = _tab(_current_display=display, _current_sched_data=sched,
               _current_from_schedule=True)
    tab._on_next_verse()
    assert tab.steps == [], "exhausted deck must not step the schedule"
    assert tab.applied_slides == []


def test_first_slide_prev_does_nothing():
    display, sched = _deck(index=0, count=3)
    tab = _tab(_current_display=display, _current_sched_data=sched,
               _current_from_schedule=True)
    tab._on_prev_verse()
    assert tab.steps == []
    assert tab.applied_slides == []


def test_single_slide_deck_does_nothing():
    display, sched = _deck(index=0, count=1)
    tab = _tab(_current_display=display, _current_sched_data=sched,
               _current_from_schedule=True)
    tab._on_next_verse()
    tab._on_prev_verse()
    assert tab.steps == []
    assert tab.applied_slides == []


def test_deck_with_nothing_on_live_does_nothing():
    tab = _tab(_current_display=None, _current_sched_data=None)
    tab._on_next_verse()
    tab._on_prev_verse()
    assert tab.steps == []
    assert tab.navigated == []


# ─── Alt+Left / Alt+Right: the only path into the schedule ─────────────────

def test_schedule_item_hotkeys_step_the_schedule():
    tab = _tab()
    tab._on_next_schedule_item()
    tab._on_prev_schedule_item()
    assert tab.steps == [1, -1]


def test_slides_tab_deck_boundary_does_not_step_schedule():
    """slides_tab has its own stepper with the same fallthrough bug."""
    from ui.tabs.slides_tab import SlidesTab

    tab = SlidesTab.__new__(SlidesTab)
    tab.steps = []
    tab._display = _FakeDisplay()
    tab._current_display = {
        "item_type": "slide",
        "slides": [{"text": "a"}, {"text": "b"}],
        "slide_index": 1,
        "deck_title": "Sermon",
    }
    tab._live_sched_uid = "u1"
    tab._live_from_schedule = True
    tab._step_schedule = lambda d: tab.steps.append(d)
    tab._show_slide = lambda *a, **k: None
    tab._step_live(1)
    assert tab.steps == [], "exhausted deck must not step the schedule"


# ─── hotkey table: arrows are verse/slide, Alt+arrows are schedule items ───

def test_hotkey_defaults_separate_verse_from_schedule_navigation():
    """The defaults must not collide, or the split is unreachable."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QKeySequence

    QApplication.instance() or QApplication(["t"])
    from ui.widgets.hotkey_editor import DEFAULT_BINDINGS as defaults

    def binding(action_id):
        return defaults[action_id][2]

    pairs = {
        "next_verse": "Right",
        "prev_verse": "Left",
        "next_schedule_item": "Alt+Right",
        "prev_schedule_item": "Alt+Left",
    }
    for action_id, expected in pairs.items():
        assert binding(action_id) == expected, action_id
    # Distinct key sequences — Alt+Right must not resolve to plain Right.
    assert QKeySequence("Alt+Right") != QKeySequence("Right")
    assert QKeySequence("Alt+Left") != QKeySequence("Left")


def test_main_window_maps_schedule_item_actions():
    """The action ids must be dispatched by the main window or Alt+arrows
    would fall through to nothing."""
    import inspect
    from ui.main_window import MainWindow

    source = inspect.getsource(MainWindow)
    for action_id in ("next_schedule_item", "prev_schedule_item"):
        assert f'"{action_id}": self._hotkey_' in source, action_id


def test_focusable_ancestor_picks_nearest_focusable_widget():
    """The double-click hotkey focuses the nearest focusable ancestor of the
    widget under the cursor — that is what moves the ring to the panel the
    operator deployed into."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
    from PyQt6.QtCore import Qt
    from ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(["t"])
    root = QWidget()
    layout = QVBoxLayout(root)
    focusable = QWidget()
    focusable.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
    inner = QLabel("leaf (NoFocus)")
    layout.addWidget(focusable)
    layout.addWidget(inner)
    inner_layout = QVBoxLayout(focusable)
    inner_layout.addWidget(inner)
    root.show()
    app.processEvents()

    # A non-focusable leaf resolves up to its focusable ancestor.
    assert MainWindow._focusable_ancestor(inner) is focusable
    # A focusable widget resolves to itself.
    assert MainWindow._focusable_ancestor(focusable) is focusable


# ─── F1 double-click moves focus to the deployment target ──────────────────

def test_focusable_ancestor_resolves_non_focusable_child():
    """A click target is often a non-focusable child (a schedule row is a
    NoFocus QFrame, and the click lands on a label inside it). The ancestor
    walk must climb to the nearest widget that can take focus."""
    app = QApplication.instance() or QApplication(["t"])
    root = QWidget()
    layout = QVBoxLayout(root)
    holder = QWidget()
    holder.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
    inner_layout = QVBoxLayout(holder)
    inner = QLabel("leaf")
    inner_layout.addWidget(inner)
    layout.addWidget(holder)
    root.show()
    app.processEvents()
    _KEEP_ALIVE.append(root)

    from ui.main_window import MainWindow

    assert inner.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert MainWindow._focusable_ancestor(inner) is holder
    assert MainWindow._focusable_ancestor(holder) is holder


def test_double_click_hotkey_focuses_the_target_ancestor(monkeypatch):
    """F1 must move focus to the deployment target.

    This is what makes the focus ring follow the deployment: the nearest
    focusable ancestor of the widget under the cursor takes focus, so
    double-clicking a schedule row lights the schedule ring instead of
    leaving it wherever the caret happened to be. Previously the handler
    called `self.setFocus()` on the main window, which parked focus on
    nothing and left the ring stranded.

    widgetAt is stubbed rather than driven by a real cursor position: under
    the offscreen platform the hit-test target depends on layout timing,
    and the behaviour under test is what the handler DOES with that target.
    """
    from types import MethodType
    from PyQt6.QtCore import QPoint
    from PyQt6.QtWidgets import QApplication
    from ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(["t"])

    class _Target:
        """A non-focusable click target that records the focus it grants."""

        def __init__(self):
            self.granted_to = None

        def parentWidget(self):
            return None

    class _RecordingWidget(QWidget):
        """A real QWidget (sendEvent needs one) that records focus reasons."""

        def __init__(self):
            super().__init__()
            self.focus_calls = []
            self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            self.show()

        def setFocus(self, reason=None):
            self.focus_calls.append(reason)
            super().setFocus(reason)

    focusable = _RecordingWidget()
    _KEEP_ALIVE.append(focusable)
    app.processEvents()

    # The widget under the cursor is focusable itself, so it is the answer.
    monkeypatch.setattr(QApplication, "widgetAt",
                        staticmethod(lambda point: focusable))
    # Focus currently sits elsewhere, so the handler must act.
    elsewhere = QWidget()
    elsewhere.show()
    _KEEP_ALIVE.append(elsewhere)
    elsewhere.setFocus()
    app.processEvents()

    class _Host:
        pass

    host = _Host()
    host._focusable_ancestor = MainWindow._focusable_ancestor
    host._hotkey_double_click = MethodType(MainWindow._hotkey_double_click, host)
    host._hotkey_double_click()

    assert focusable.focus_calls, "double-click must move focus to the target"
    # MouseFocusReason, like a real click.
    assert focusable.focus_calls[0] == Qt.FocusReason.MouseFocusReason


# ─── regression: Qt enum namespace in the double-click handler ─────────────

def test_no_qualified_qt_enum_namespace_anywhere():
    """Guard against `QtCore.Qt.<Enum>` (or any doubled namespace).

    Regression, not lint taste. `_hotkey_double_click` once read
    `QtCore.Qt.FocusReason.MouseFocusReason` where `QtCore` was already an
    alias *for* `Qt`, so the doubled lookup raised
    `AttributeError: type object 'Qt' has no attribute 'Qt'` at the moment
    an operator pressed F1 — during a service, not in CI. The crash needs a
    live cursor hit-test to reach, so nothing else caught it.

    Qt's enums are nested under `Qt` itself (`Qt.FocusReason`,
    `Qt.FocusPolicy`); a module alias plus a class name is always wrong.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    # A Qt class followed by an attribute that is itself a Qt class:
    # `Qt.FocusReason`, `QtCore.Qt.FocusReason`, `Qt.Qt.FocusPolicy`.
    # Restricted to known Qt types so IP literals ("0.0.0.0") and dotted
    # __file__ chains do not match.
    qt_types = frozenset((
        "Qt", "QtCore", "QRect", "QRectF", "QPoint", "QPointF",
        "QEvent", "QTimer", "QObject", "QSize", "QMargins",
    ))
    # Parse rather than regex over raw text, so the example of the very
    # mistake being guarded against (written in this docstring) is not itself
    # a hit. Also skips comments and string literals for free.
    import ast

    offenders = []
    for path in root.rglob("*.py"):
        if "venv" in path.parts or ".git" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            parts = []
            cur = node
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if not isinstance(cur, ast.Name):
                continue
            parts.append(cur.id)
            parts.reverse()  # outermost first
            if len(parts) >= 3 and parts[0] in qt_types and parts[1] in qt_types:
                offenders.append(
                    f"{path.relative_to(root)}:{node.lineno}: {'.'.join(parts)}")
    assert not offenders, "doubled Qt namespace:\n" + "\n".join(offenders)


def test_double_click_handler_uses_real_focus_reason_enum():
    """Pins the actual attribute the handler passes to setFocus().

    Companion to the source scan above: if this ever regresses to a bad
    namespace, the handler raises the moment focus needs to move.
    """
    app = QApplication.instance() or QApplication(["t"])
    from types import MethodType
    from PyQt6.QtWidgets import QApplication as QA
    from ui.main_window import MainWindow

    class _Target(QWidget):
        def __init__(self):
            super().__init__()
            self.reasons = []
            self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        def setFocus(self, reason=None):
            self.reasons.append(reason)
            super().setFocus(reason)

    target = _Target()
    target.show()
    app.processEvents()
    _KEEP_ALIVE.append(target)

    other = QWidget()
    other.show()
    other.setFocus()
    app.processEvents()
    _KEEP_ALIVE.append(other)

    # Focus is elsewhere, so the handler must move it.
    original_widget_at = QA.widgetAt
    original_focus_widget = QA.focusWidget
    try:
        QA.widgetAt = staticmethod(lambda point: target)
        QA.focusWidget = staticmethod(lambda: other)

        class _Host:
            pass

        host = _Host()
        host._focusable_ancestor = MainWindow._focusable_ancestor
        host._hotkey_double_click = MethodType(MainWindow._hotkey_double_click, host)
        host._hotkey_double_click()  # must not raise
    finally:
        QA.widgetAt = original_widget_at
        QA.focusWidget = original_focus_widget

    assert target.reasons, "focus should have moved to the target"
    assert target.reasons[0] == Qt.FocusReason.MouseFocusReason


# ─── the prev/next queue tracks whatever is displayed ────────────────────
#
# Regression: the queue used to be refreshed by hand at each of ten display
# call sites, and the one path that did not — a preview-only search-result
# click — left the neighbours of the PREVIOUSLY displayed verse in place.
# Observed as: display Matt 6:25, click a search result for Matt 7:22, press
# Next, and get 6:26.

def _queue_tab():
    """A tab wired to a real DisplayState so the live_data hook is live."""
    from core.display_state import DisplayState
    from ui.tabs.presentation_tab import PresentationTab
    tab = PresentationTab.__new__(PresentationTab)
    tab._display = DisplayState()
    tab._prev_verse_data = None
    tab._next_verse_data = None
    tab._display.add_live_data_hook(tab._on_live_data_changed)
    return tab


def _ref(verse):
    if not verse:
        return None
    return f"{verse['book']} {verse['chapter']}:" \
           f"{verse.get('verse_num', verse.get('verse'))}"


def test_queue_follows_a_displayed_verse_from_any_source(monkeypatch):
    """Whatever is displayed, the queue brackets THAT verse."""
    import ui.tabs.presentation_tab as pt
    monkeypatch.setattr(pt.PresentationTab, "_update_verse_neighbors",
                        lambda self, v, b, c, n: (
                            setattr(self, "_prev_verse_data",
                                    {"book": b, "chapter": c, "verse": n - 1}),
                            setattr(self, "_next_verse_data",
                                    {"book": b, "chapter": c, "verse": n + 1})))
    tab = _queue_tab()

    # live_data is THE record of what is displayed — one assignment covers
    # navigator, browser, schedule, search-live and prev/next itself.
    tab._display.live_data = _scripture("25", "6", "Matthew")
    assert _ref(tab._prev_verse_data) == "Matthew 6:24"
    assert _ref(tab._next_verse_data) == "Matthew 6:26"

    tab._display.live_data = _scripture("22", "7", "Matthew")
    assert _ref(tab._prev_verse_data) == "Matthew 7:21"
    assert _ref(tab._next_verse_data) == "Matthew 7:23"


def test_preview_only_navigation_moves_the_queue(monkeypatch):
    """A search-result click is preview-only, so live_data never changes
    and the hook cannot fire — but the operator HAS moved, so the queue
    must follow them rather than the stale live verse."""
    import ui.tabs.presentation_tab as pt
    monkeypatch.setattr(pt.PresentationTab, "_update_verse_neighbors",
                        lambda self, v, b, c, n: (
                            setattr(self, "_prev_verse_data",
                                    {"book": b, "chapter": c, "verse": n - 1}),
                            setattr(self, "_next_verse_data",
                                    {"book": b, "chapter": c, "verse": n + 1})))
    tab = _queue_tab()
    tab._display.live_data = _scripture("25", "6", "Matthew")
    assert _ref(tab._next_verse_data) == "Matthew 6:26"

    tab._set_verse_position("KJV", "Matthew", "7", "22")
    assert _ref(tab._prev_verse_data) == "Matthew 7:21"
    assert _ref(tab._next_verse_data) == "Matthew 7:23"


def test_queue_is_emptied_by_a_deck_and_by_a_clear(monkeypatch):
    """A deck steps through its own slides, so the verse queue must be
    empty rather than stale; a clear leaves nothing to step from."""
    tab = _queue_tab()
    tab._display.live_data = _scripture("25", "6", "Matthew")
    assert tab._next_verse_data is not None

    tab._display.live_data = _deck(0)[0]
    assert tab._prev_verse_data is None
    assert tab._next_verse_data is None

    tab._display.live_data = _scripture("25", "6", "Matthew")
    assert tab._next_verse_data is not None
    tab._display.publish_clear()
    assert tab._prev_verse_data is None
    assert tab._next_verse_data is None


def test_clicking_a_search_result_moves_the_queue(monkeypatch):
    """End to end through the handler the operator actually clicks.

    This is the path that was missed: it publishes a preview and returns,
    so live_data is untouched and the display hook never fires.
    """
    import core.bible_service as bible_service
    import ui.tabs.presentation_tab as pt
    from core.display_state import DisplayState
    from ui.tabs.presentation_tab import PresentationTab

    monkeypatch.setattr(bible_service, "get_verse",
                        lambda v, b, c, n: {"text": "text",
                                            "book": b, "chapter": c,
                                            "verse": n})
    monkeypatch.setattr(PresentationTab, "_update_verse_neighbors",
                        lambda self, v, b, c, n: (
                            setattr(self, "_prev_verse_data",
                                    {"book": b, "chapter": c, "verse": n - 1}),
                            setattr(self, "_next_verse_data",
                                    {"book": b, "chapter": c, "verse": n + 1})))

    tab = PresentationTab.__new__(PresentationTab)
    tab._display = DisplayState()
    tab._prev_verse_data = None
    tab._next_verse_data = None
    tab._display.add_live_data_hook(tab._on_live_data_changed)

    class _Browser:
        _current_translation = "KJV"

        def navigate_to_reference(self, *a, **k):
            pass
    tab.browser_panel = _Browser()
    # _build_payload reaches for widget state we deliberately do not have.
    tab._build_payload = lambda text, ref, version, book, chapter, verse: {
        "action": "display", "content": "verse", "text": text, "ref": ref}

    # Something else is on live first.
    tab._display.live_data = _scripture("25", "6", "Matthew")
    assert _ref(tab._next_verse_data) == "Matthew 6:26"

    tab._on_search_to_navigator({"book": "Matthew", "chapter": "7",
                                 "verse_num": "22"})

    assert _ref(tab._prev_verse_data) == "Matthew 7:21", (
        "prev/next still bracket the previously displayed verse")
    assert _ref(tab._next_verse_data) == "Matthew 7:23"


def test_the_real_tab_registers_the_queue_hook():
    """The queue must be wired in PresentationTab.__init__, not only in the
    tests that exercise the mechanism.

    Deliberately a source-level guard: booting a real tab needs the DB,
    the models and an event loop, and what is being asserted here is a
    wiring fact ("this registration exists in __init__") rather than
    behaviour. The behaviour itself is covered by the tests above; this
    is here so that deleting the one line that connects them fails loudly
    instead of silently leaving every display path unrefreshed.
    """
    import inspect
    from ui.tabs.presentation_tab import PresentationTab
    src = inspect.getsource(PresentationTab.__init__)
    assert "add_live_data_hook" in src, (
        "PresentationTab.__init__ no longer registers the live_data hook — "
        "prev/next will bracket whichever verse was displayed last among "
        "the paths that still refresh it by hand")

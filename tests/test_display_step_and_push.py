"""
tests/test_display_step_and_push.py

The display queue belongs to the DISPLAYED content, not to the tab the
operator happens to be standing in, and preview -> live is a replay of the
stored payload rather than a rebuild from a navigation dict.

Both rules exist because of reported failures:
  - a deck slide stepped from the Scripture tab came back rebuilt through
    the scripture code path, wearing the scripture theme;
  - a scripture previewed in Scriptures and pushed from the Decks tab lost
    its inline verse number and scripture reference, leaving bare text and
    a translation on the OBS screen.

These use real DisplayState scopes and `__new__`-built tabs (no widgets):
the behaviour under test is state routing, not layout.
"""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

# No WebEngine here: these tests exercise state routing with plain widgets,
# and pulling the WebEngine stack in for nothing adds teardown risk to the
# suite.

import logging

import pytest

import core.database as db
from core.outputs import MODE_PRIORITIZED, MODE_SIMULTANEOUS, set_output_mode

logging.disable(logging.CRITICAL)


@pytest.fixture(autouse=True)
def _clean_display_state():
    """Display scopes are module-global singletons. These tests publish
    into the SHARED scope, so both ends of the test clear it — otherwise the
    next file inherits a live payload and steps from the wrong content."""
    from core.display_state import reset_display_states
    reset_display_states()
    yield
    reset_display_states()


@pytest.fixture()
def tmpdb(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    db.init_db()
    return tmp_path


@pytest.fixture()
def prioritized(tmpdb):
    set_output_mode(MODE_PRIORITIZED)
    return MODE_PRIORITIZED


@pytest.fixture()
def simultaneous(tmpdb):
    set_output_mode(MODE_SIMULTANEOUS)
    return MODE_SIMULTANEOUS


def _handles(prioritized):
    """Real handles for both display tabs (no widgets)."""
    from core.display_state import display_state_for, follow_output_mode, reset_display_states
    reset_display_states()
    follow_output_mode()
    return display_state_for("SCRIPTURE"), display_state_for("SLIDES")


def _slide_data(text="I can't escape", index=0):
    return {"item_type": "slide", "text": text, "deck_title": "My World Needs You",
            "slides": [{"text": "I can't escape", "section": "Verse"},
                       {"text": "Show me your face", "section": "Chorus"}],
            "slide_index": index, "deck_id": 1}


def _verse_data(text="And God saw the light, that it was good;"):
    return {"item_type": "verse", "text": text, "book": "Genesis",
            "chapter": "1", "verse_num": "4", "version": "NKJV"}


# ── who owns the displayed content ───────────────────────────────────────────

def test_owner_follows_the_live_content_not_the_asking_tab(prioritized):
    """The handle that is asked must not decide who owns the content."""
    pres, slides = _handles(prioritized)
    from core.display_state import display_state
    assert pres.scope is slides.scope is display_state

    pres.publish_live({"action": "display", "text": "l1", "content": "slide",
                       "theme": "slides", "theme_data": {}}, _slide_data())
    # Asked of the Scripture tab: the DECK owns a live slide.
    assert pres.content_owner_key() == "SLIDES"
    assert slides.content_owner_key() == "SLIDES"

    pres.publish_live({"action": "display", "text": "a verse", "content": "verse",
                       "theme": "default", "theme_data": {}}, _verse_data())
    assert pres.content_owner_key() == "SCRIPTURE"
    assert slides.content_owner_key() == "SCRIPTURE"


def test_simultaneous_mode_keeps_ownership_local(simultaneous):
    pres, slides = _handles(simultaneous)
    assert pres.scope is not slides.scope
    pres.publish_live({"action": "display", "text": "a verse", "content": "verse",
                       "theme": "default", "theme_data": {}}, _verse_data())
    # Each tab screens for itself, so stepping never crosses tabs.
    assert pres.content_owner_key() == "SCRIPTURE"
    assert slides.content_owner_key() == "SLIDES"


def test_no_live_content_leaves_the_owner_to_the_asking_tab(prioritized):
    pres, _slides = _handles(prioritized)
    assert pres.scope.live_data is None
    assert pres.content_owner_key() == "SCRIPTURE"


# ── dispatch ─────────────────────────────────────────────────────────────────

def test_dispatch_runs_the_owners_stepper(prioritized):
    pres, slides = _handles(prioritized)
    seen = []
    pres.register_owner_op("SCRIPTURE", "step", lambda d: seen.append(("SCRIPTURE", d)))
    slides.register_owner_op("SLIDES", "step", lambda d: seen.append(("SLIDES", d)))
    pres.publish_live({"action": "display", "text": "l1", "content": "slide",
                       "theme": "slides", "theme_data": {}}, _slide_data())

    assert pres.dispatch_step(1) is True
    assert seen == [("SLIDES", 1)], "a live slide steps with the deck's code"
    pres.dispatch_step(-1)
    assert seen[-1] == ("SLIDES", -1)

    pres.publish_live({"action": "display", "text": "v", "content": "verse",
                       "theme": "default", "theme_data": {}}, _verse_data())
    pres.dispatch_step(1)
    assert seen[-1] == ("SCRIPTURE", 1), "a live verse steps the scripture queue"


def test_dispatch_returns_false_without_an_owner(prioritized):
    pres, _slides = _handles(prioritized)
    pres.publish_live({"action": "display", "text": "l1", "content": "slide",
                       "theme": "slides", "theme_data": {}}, _slide_data())
    # Nothing registered (a bare scope): the caller steps locally.
    assert pres.dispatch_step(1) is False


def test_dead_stepper_is_dropped_not_called(prioritized):
    """A stepper must never outlive its tab: routing into a closed window
    is how a dead tab silently swallowed the keystroke."""
    pres, _slides = _handles(prioritized)
    pres.publish_live({"action": "display", "text": "l1", "content": "slide",
                       "theme": "slides", "theme_data": {}}, _slide_data())

    class Tab:
        def __init__(self):
            self.calls = 0

        def step(self, delta):
            self.calls += 1

    tab = Tab()
    pres.register_owner_op("SLIDES", "step", tab.step)
    assert pres.dispatch_step(1) is True and tab.calls == 1

    # No gc.collect(): forcing a global collection here sweeps up unrelated
    # pending Qt objects and crashes WebEngine teardown. Dropping the last
    # reference is enough — the registry holds it weakly.
    del tab
    assert pres.dispatch_step(1) is False, "dead stepper must not be invoked"


def test_registration_is_overwritten_by_the_newest_tab(prioritized):
    pres, _slides = _handles(prioritized)
    pres.publish_live({"action": "display", "text": "l1", "content": "slide",
                       "theme": "slides", "theme_data": {}}, _slide_data())
    seen = []
    pres.register_owner_op("SLIDES", "step", lambda d: seen.append("first"))
    pres.register_owner_op("SLIDES", "step", lambda d: seen.append("second"))
    pres.dispatch_step(1)
    assert seen == ["second"]


# ── tabs hand stepping to the state ──────────────────────────────────────────

class _RoutingDisplay:
    """Display stub that records the routing decision."""

    cloaked = False

    def __init__(self, handled=True):
        self.dispatched = []
        self._handled = handled
        self.live_data = None
        self.scope = None

    def dispatch_step(self, delta):
        self.dispatched.append(delta)
        return self._handled

    def dispatch_to_owner(self, op, *args):
        self.dispatched.append(op)
        return self._handled

    def register_owner_op(self, *a):
        pass


def test_scripture_tab_entry_points_route(prioritized):
    from ui.tabs.presentation_tab import PresentationTab
    tab = PresentationTab.__new__(PresentationTab)
    tab._display = _RoutingDisplay(handled=True)
    tab._on_next_verse()
    tab._on_prev_verse()
    assert tab._display.dispatched == [1, -1]


def test_deck_tab_entry_points_route(prioritized):
    from ui.tabs.slides_tab import SlidesTab
    tab = SlidesTab.__new__(SlidesTab)
    tab._display = _RoutingDisplay(handled=True)
    tab._on_next()
    tab._on_prev()
    assert tab._display.dispatched == [1, -1]


def test_unrouted_step_falls_back_to_the_tabs_own_step(prioritized):
    """Nothing registered (simultaneous-style stub): the tab steps itself."""
    from ui.tabs.slides_tab import SlidesTab
    tab = SlidesTab.__new__(SlidesTab)
    tab._display = _RoutingDisplay(handled=False)
    seen = []
    tab._step_live = lambda delta: seen.append(delta)
    tab._on_next()
    tab._on_prev()
    assert tab._display.dispatched == [1, -1]
    assert seen == [1, -1], "the tab's own step must still run"


# ── preview push replays instead of rebuilding ───────────────────────────────

def test_matching_preview_payload_requires_current_content(tmpdb):
    from core.display_state import DisplayState
    state = DisplayState()
    data = _verse_data()
    payload = {"action": "display", "content": "verse", "text": data["text"],
               "theme": "default", "theme_data": {}}
    state.publish_preview(payload, data)
    replayed = state.matching_preview_payload()
    assert replayed is not None and replayed["text"] == data["text"]

    # Preview moved on without a new payload: the stored one is stale.
    state.preview_data = {**data, "text": "something else"}
    assert state.matching_preview_payload() is None


def test_deck_tab_verse_payload_keeps_scripture_parts():
    """The renderer draws the inline verse number and full reference from
    book/chapter/verse; blanking them left bare text + translation."""
    from ui.tabs.slides_tab import SlidesTab
    tab = SlidesTab.__new__(SlidesTab)
    tab._themes_by_output = {"4": "slides"}
    tab._verse_themes_by_output = {"4": "default"}
    tab._main_output = "4"
    payload = tab._build_payload("And God saw the light;", "[NKJV] Genesis 1:4",
                                 "NKJV", output_id="4", is_slide=False,
                                 book="Genesis", chapter="1", verse="4")
    assert payload["book"] == "Genesis"
    assert payload["chapter"] == "1"
    assert payload["verse"] == "4"
    assert payload["translation"] == "NKJV"
    assert payload["content"] == "verse"


def test_payload_for_display_passes_scripture_parts_through():
    from ui.tabs.slides_tab import SlidesTab
    tab = SlidesTab.__new__(SlidesTab)
    tab._themes_by_output = {"4": "slides"}
    tab._verse_themes_by_output = {"4": "default"}
    tab._main_output = "4"
    payload = tab._payload_for_display(_verse_data())
    assert (payload["book"], payload["chapter"], payload["verse"]) == \
        ("Genesis", "1", "4")


def test_broadcast_carries_scripture_parts_to_every_output(monkeypatch):
    """Per-output payloads must keep the parts too, or OBS loses them."""
    from ui.tabs.slides_tab import SlidesTab
    tab = SlidesTab.__new__(SlidesTab)
    tab._themes_by_output = {"4": "default", "5": "default", "6": "default"}
    tab._verse_themes_by_output = {"4": "default", "5": "default", "6": "default"}
    tab._main_output = "4"

    class _Display:
        cloaked = False

        def matching_live_output_payloads(self):
            return {}

        def remember_live_output_payloads(self, payloads):
            pass

    tab._display = _Display()
    sent = []

    class _Loop:
        def is_closed(self):
            return False

    import core.websocket_server as ws
    import core.output_router as router

    def fake_broadcast(payload, target=None):
        sent.append((payload, target))

        async def _done():
            return None
        return _done()

    # monkeypatch, not plain assignment: a fake loop left behind would make
    # every later "router is quiet with no server" assertion fail.
    monkeypatch.setattr(ws, "_server_loop", _Loop())
    monkeypatch.setattr(ws, "broadcast_display", fake_broadcast)
    monkeypatch.setattr(router.asyncio, "run_coroutine_threadsafe",
                        lambda coro, loop: coro.close())
    set_output_mode(MODE_SIMULTANEOUS)

    payload = tab._build_payload("And God saw the light;", "[NKJV] Genesis 1:4",
                                 "NKJV", is_slide=False, book="Genesis",
                                 chapter="1", verse="4")
    tab._broadcast_to_ws(payload, None)
    assert sent, "expected a fan-out"
    for out_payload, _target in sent:
        assert out_payload["book"] == "Genesis"
        assert out_payload["verse"] == "4"


# ── double-tap Ctrl releases the keyboard ───────────────────────────────────

def test_double_ctrl_releases_textbox_focus(tmpdb):
    """A focused search box eats Left/Right; two Ctrl taps give the keys
    back so prev/next work again."""
    import time
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QLineEdit, QWidget, QVBoxLayout
    import ui.main_window as mw

    # Never create the QApplication here: this file runs early, and
    # building one before ui.widgets.display_view has been imported leaves
    # WebEngine initializing after the app exists — the documented
    # headless crash. Use whatever app the suite already owns.
    app = QApplication.instance()
    if app is None:
        pytest.skip("no QApplication yet (WebEngine pre-import order)")
    host = QWidget()
    line = QLineEdit(host)
    QVBoxLayout(host).addWidget(line)
    host.show()
    app.processEvents()
    host.activateWindow()
    app.processEvents()
    line.setFocus(Qt.FocusReason.OtherFocusReason)
    app.processEvents()
    if not line.hasFocus():
        pytest.skip("no window focus in this environment")

    class _Stub:
        _last_ctrl_release_at = 0.0

        def setFocus(self, *args, **kwargs):
            pass

        def _active_workspace_tab(self):
            return host

    stub = _Stub()
    stub._maybe_release_focus_from_textbox = (
        mw.MainWindow._maybe_release_focus_from_textbox.__get__(stub))

    # Ctrl+A then Ctrl+C: both taps carry a combo, so neither counts.
    stub._ctrl_tap_clean = False
    stub._last_ctrl_release_at = time.monotonic() - 0.05
    stub._maybe_release_focus_from_textbox()
    app.processEvents()
    assert line.hasFocus(), "Ctrl combos must not count as taps"

    stub._ctrl_tap_clean = True
    stub._last_ctrl_release_at = 0.0
    stub._maybe_release_focus_from_textbox()      # one tap: nothing yet
    app.processEvents()
    assert line.hasFocus(), "a single Ctrl tap must not steal the keyboard"

    stub._ctrl_tap_clean = True
    stub._last_ctrl_release_at = time.monotonic() - 0.05
    stub._maybe_release_focus_from_textbox()      # second tap inside the window
    app.processEvents()
    assert not line.hasFocus(), "double Ctrl must drop the textbox focus"

    # Two slow taps are two taps, not a double.
    line.setFocus(Qt.FocusReason.OtherFocusReason)
    app.processEvents()
    stub._ctrl_tap_clean = True
    stub._last_ctrl_release_at = time.monotonic() - 5.0
    stub._maybe_release_focus_from_textbox()
    app.processEvents()
    assert line.hasFocus()

# ── cloak / uncloak across tabs ──────────────────────────────────────────────

def test_uncloak_runs_on_the_tab_that_owns_the_content(prioritized):
    """Regression: uncloaking from the "wrong" tab rebuilt the live screen
    through that tab's code and theme."""
    pres, slides = _handles(prioritized)
    pres.publish_live({"action": "display", "text": "l1", "content": "slide",
                       "theme": "slides", "theme_data": {}}, _slide_data())
    seen = []
    pres.register_owner_op("SCRIPTURE", "uncloak", lambda: seen.append("scripture"))
    slides.register_owner_op("SLIDES", "uncloak", lambda: seen.append("slides"))

    pres.dispatch_to_owner("uncloak")      # asked of the scripture tab
    assert seen == ["slides"], "a live slide uncloaks in the DECKS tab"


def test_uncloak_route_falls_back_when_unregistered(prioritized):
    pres, _slides = _handles(prioritized)
    assert pres.dispatch_to_owner("uncloak") is False


def test_clearing_recall_routes_uncloak_to_the_owner(prioritized):
    """The public cloak/recall toggle must delegate before acting locally,
    or the local branch would blank/rebuild its own way."""
    from ui.tabs.slides_tab import SlidesTab
    tab = SlidesTab.__new__(SlidesTab)
    tab._display = _RoutingDisplay(handled=True)
    tab._display.cloaked = True           # currently cloaked -> uncloak path
    tab._uncloak_now = lambda: seen.append("local")
    seen = []
    tab._on_clear_recall()
    assert tab._display.dispatched == ["uncloak"]
    assert seen == [], "the owner must act, not this tab"


def test_a_shared_cloak_blanks_every_output(monkeypatch, prioritized):
    """One live screen means one cover: leaving another tab's output on
    air behind a cloak is what made the restore look wrong."""
    from core.outputs import active_outputs, outputs_for_tab
    import core.websocket_server as ws
    import core.output_router as router

    sent = []

    class _Loop:
        def is_closed(self):
            return False

    def fake_broadcast(payload, target=None):
        sent.append((payload, target))

        async def _done():
            return None
        return _done()

    monkeypatch.setattr(ws, "_server_loop", _Loop())
    monkeypatch.setattr(ws, "broadcast_display", fake_broadcast)
    monkeypatch.setattr(router.asyncio, "run_coroutine_threadsafe",
                        lambda coro, loop: coro.close())
    router.clear_all_outputs()
    expected = {oid for key in outputs_for_tab("SCRIPTURE") and
                ("SCRIPTURE", "SLIDES", "MEDIA", "PRESENTATION")
                for oid in active_outputs(key)}
    assert {t for _p, t in sent} == expected
    assert all(p.get("action") == "clear" for p, _t in sent)


def test_router_scopes_a_tab_to_its_own_outputs(monkeypatch, prioritized):
    """A tab may only write to its own set, whatever the payload map says.

    Regression: a restore rebuilds the map from stored per-output
    snapshots, and those keys follow whoever produced the content — so a
    Decks uncloak pushed a scripture back out to scripture's screens.
    """
    from core.outputs import active_outputs
    import core.websocket_server as ws
    import core.output_router as router

    sent = []

    class _Loop:
        def is_closed(self):
            return False

    def fake_broadcast(payload, target=None):
        sent.append((payload, target))

        async def _done():
            return None
        return _done()

    monkeypatch.setattr(ws, "_server_loop", _Loop())
    monkeypatch.setattr(ws, "broadcast_display", fake_broadcast)
    monkeypatch.setattr(router.asyncio, "run_coroutine_threadsafe",
                        lambda coro, loop: coro.close())

    stray = {"action": "display", "text": "stolen"}
    router.broadcast_tab_payload("SLIDES", {"4": stray, "1": stray})
    # Prioritized mode also cloaks the other tabs — those are clears, and
    # they are the point. Only CONTENT must stay on the acting tab's set.
    content = [t for payload, t in sent if payload.get("action") != "clear"]
    assert content == ["4"], content
    assert set(active_outputs("SLIDES")) == {"4", "5", "6"}


def test_deck_verse_citation_line_has_no_translation(prioritized):
    """Regression: the deck tab sent reference="[NKJV] Genesis 1:9" AND
    translation="NKJV", so the screen read "[NKJV] Genesis 1:9 NKJV"."""
    from ui.tabs.slides_tab import SlidesTab
    tab = SlidesTab.__new__(SlidesTab)
    tab._themes_by_output = {"4": "slides"}
    tab._verse_themes_by_output = {"4": "default"}
    tab._main_output = "4"
    payload = tab._build_payload("Then God said", "[NKJV] Genesis 1:9", "NKJV",
                                 is_slide=False, book="Genesis", chapter="1",
                                 verse="9")
    assert payload["reference"] == "Genesis 1:9"
    assert payload["translation"] == "NKJV"
    assert "NKJV" not in payload["reference"]


# ── display-tab cycling chord (built-in, not editable) ──────────────────────

class _FakeEvent:
    def __init__(self, key, mods=(), auto_repeat=False):
        self._key = key
        self._mods = mods
        self._repeat = auto_repeat

    def key(self):
        return self._key

    def modifiers(self):
        return self._mods

    def isAutoRepeat(self):
        return self._repeat


def _cycler_stub(display_keys=("SCRIPTURE", "SLIDES")):
    """Minimal MainWindow stand-in for the cycling chord."""
    from PyQt6.QtCore import Qt
    import ui.main_window as mw

    class _Stub:
        def __init__(self):
            self._tabs = {k: object() for k in display_keys}
            self._tabs["SETTINGS"] = object()
            self._tabs["HISTORY"] = object()
            self.stack = _Stack()
            self.cycled = []

        def isActiveWindow(self):
            return True

        def _switch_tab(self, index, name):
            self.stack.current = index
            self.cycled.append(name)

        def _cycle_display_tab(self, step):
            return mw.MainWindow._cycle_display_tab(self, step)

        def _maybe_display_tab_chord(self, event):
            return mw.MainWindow._maybe_display_tab_chord(self, event)

    class _Stack:
        current = 0
        currentIndex = lambda self: self.current

    return _Stub(), Qt


def _names_for(stub):
    return list(stub._tabs.keys())


def test_ctrl_alt_arrows_cycle_display_tabs_and_wrap():
    stub, Qt = _cycler_stub()
    names = _names_for(stub)
    ctrl_alt = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier

    # From Scriptures, Right -> Decks, then wrap back to Scriptures.
    assert stub._maybe_display_tab_chord(
        _FakeEvent(Qt.Key.Key_Right, ctrl_alt)) is True
    assert stub.cycled[-1] == "SLIDES"
    assert stub._maybe_display_tab_chord(
        _FakeEvent(Qt.Key.Key_Right, ctrl_alt)) is True
    assert stub.cycled[-1] == "SCRIPTURE", "must wrap, not stop at the end"
    # And the other direction wraps too.
    assert stub._maybe_display_tab_chord(
        _FakeEvent(Qt.Key.Key_Left, ctrl_alt)) is True
    assert stub.cycled[-1] == "SLIDES"


def test_cycle_skips_non_display_tabs():
    """Settings/History/Library are not display tabs and stay off the path."""
    stub, Qt = _cycler_stub()
    stub.stack.current = _names_for(stub).index("SETTINGS")
    stub.cycled.clear()
    ctrl_alt = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
    # Right from Settings continues forward: Scriptures, then Decks.
    stub._maybe_display_tab_chord(_FakeEvent(Qt.Key.Key_Right, ctrl_alt))
    stub._maybe_display_tab_chord(_FakeEvent(Qt.Key.Key_Right, ctrl_alt))
    assert stub.cycled == ["SCRIPTURE", "SLIDES"]
    # Left from a core tab continues backward to the nearest display tab.
    stub.stack.current = _names_for(stub).index("HISTORY")
    stub.cycled.clear()
    stub._maybe_display_tab_chord(_FakeEvent(Qt.Key.Key_Left, ctrl_alt))
    assert stub.cycled == ["SLIDES"]


def test_chord_needs_ctrl_and_alt():
    stub, Qt = _cycler_stub()
    ctrl = Qt.KeyboardModifier.ControlModifier
    alt = Qt.KeyboardModifier.AltModifier
    # Neither modifier alone, nor Ctrl without Alt, is the chord.
    assert stub._maybe_display_tab_chord(
        _FakeEvent(Qt.Key.Key_Right, ctrl)) is False
    assert stub._maybe_display_tab_chord(
        _FakeEvent(Qt.Key.Key_Right, alt)) is False
    assert stub._maybe_display_tab_chord(
        _FakeEvent(Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)) is False
    # Plain arrows stay with prev/next.
    assert stub._maybe_display_tab_chord(
        _FakeEvent(Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)) is False
    assert stub.cycled == []


def test_auto_repeat_does_not_double_cycle():
    """Holding the key must not fly through the tabs."""
    stub, Qt = _cycler_stub()
    ctrl_alt = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
    assert stub._maybe_display_tab_chord(
        _FakeEvent(Qt.Key.Key_Right, ctrl_alt, auto_repeat=True)) is True
    assert stub.cycled == []


def test_cycling_includes_future_display_tabs():
    stub, Qt = _cycler_stub(
        display_keys=("SCRIPTURE", "SLIDES", "MEDIA", "PRESENTATION"))
    ctrl_alt = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
    seen = []
    for _ in range(5):
        stub._maybe_display_tab_chord(_FakeEvent(Qt.Key.Key_Right, ctrl_alt))
        seen.append(stub.cycled[-1])
    assert seen == ["SLIDES", "MEDIA", "PRESENTATION", "SCRIPTURE", "SLIDES"]


def test_built_in_chords_are_listed_but_not_editable(tmpdb):
    """Settings shows them for reference; they must not be capturable."""
    from ui.widgets.hotkey_editor import (BUILT_IN_BINDINGS, BuiltInHotkeyRow,
                                         DEFAULT_BINDINGS)
    keys = [spec[2] for spec in BUILT_IN_BINDINGS.values()]
    assert any("Ctrl+Alt" in k for k in keys), "display-tab chord must be listed"
    assert any("Ctrl, Ctrl" in k for k in keys), "focus-release chord must be listed"
    # None of them leak into the editable set.
    for action_id in BUILT_IN_BINDINGS:
        assert action_id not in DEFAULT_BINDINGS
    # No capture/clear affordances: the class cannot offer a rebind path.
    for attr in ("capture_btn", "clear_btn"):
        assert not hasattr(BuiltInHotkeyRow, attr), attr


def test_deck_search_hotkey_is_editable():
    from ui.widgets.hotkey_editor import DEFAULT_BINDINGS
    name, desc, default, scope = DEFAULT_BINDINGS["deck_search"]
    assert default == "Ctrl+G"
    assert scope == "slides"


def test_deck_search_hotkey_switches_tab_and_focuses_the_box():
    """Ctrl+G: like Ctrl+F / Ctrl+Shift+F, but for the Decks library."""
    import ui.main_window as mw

    class _Box:
        def __init__(self):
            self.focused = False
            self.selected = False

        def setFocus(self):
            self.focused = True

        def selectAll(self):
            self.selected = True

    class _DeckPanel:
        def __init__(self):
            self.search_box = _Box()

    class _DeckTab:
        def __init__(self):
            self.deck_panel = _DeckPanel()

    class _Stack:
        def __init__(self):
            self.current = 1
            self.currentIndex = lambda: self.current

    class _Stub:
        def __init__(self):
            self._tabs = {"SCRIPTURE": object(), "SLIDES": _DeckTab()}
            self.stack = _Stack()
            self.switched = None

        def _switch_tab(self, index, name):
            self.stack.current = index
            self.switched = name

        def _hotkey_deck_search(self):
            return mw.MainWindow._hotkey_deck_search(self)

    stub = _Stub()
    stub._hotkey_deck_search()
    assert stub.switched == "SLIDES", "must open the Decks tab"
    box = stub._tabs["SLIDES"].deck_panel.search_box
    assert box.focused and box.selected, "cursor in the box, text selected"


def test_deck_search_hotkey_default_is_registered():
    from ui.main_window import MainWindow
    assert MainWindow._HOTKEY_DEFAULTS["deck_search"] == "Ctrl+G"

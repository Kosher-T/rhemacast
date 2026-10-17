"""Per-tab output sets: registry, router, theme columns, deck tabs."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ui.widgets.display_view  # noqa: F401  (WebEngine pre-import rule)

from PyQt6.QtWidgets import QApplication

import pytest

import core.database as db


_app = None


@pytest.fixture()
def qapp():
    # Module-global ref: without it CPython collects the QApplication
    # wrapper between tests, tearing down the C++ app — and every
    # parentless QObject (like the scoped DisplayStates) — with it.
    # Suite convention (see the tier-format harness).
    global _app
    _app = QApplication.instance()
    if _app is None:
        _app = QApplication(["test"])
    return _app


@pytest.fixture()
def tmpdb(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    db.init_db()
    return tmp_path


_OPEN = []


@pytest.fixture(autouse=True)
def _close():
    yield
    while _OPEN:
        w = _OPEN.pop()
        try:
            w.close()
            w.deleteLater()
        except RuntimeError:
            pass
    app = QApplication.instance()
    if app is not None:
        app.processEvents()


def test_registry_maps_and_validates():
    from core.outputs import (
        ALL_OUTPUTS, DECK_OUTPUTS, SCRIPTURE_OUTPUTS,
        outputs_for_tab, tab_for_output, is_valid_output,
    )
    assert SCRIPTURE_OUTPUTS == ("1", "2", "3")
    assert DECK_OUTPUTS == ("4", "5", "6")
    assert len(ALL_OUTPUTS) == 10 and len(set(ALL_OUTPUTS)) == 10
    assert outputs_for_tab("SCRIPTURE") == SCRIPTURE_OUTPUTS
    assert outputs_for_tab("SLIDES") == DECK_OUTPUTS
    assert outputs_for_tab("SETTINGS") == ()
    assert tab_for_output("5") == "SLIDES"
    assert tab_for_output("1") == "SCRIPTURE"
    assert tab_for_output("9") == "PRESENTATION"
    assert tab_for_output("99") is None
    assert is_valid_output("4") and not is_valid_output("11")


def test_mode_round_trip_and_derivation(tmpdb):
    from core.outputs import (
        get_output_mode, set_output_mode, shared_display_enabled,
        MODE_SIMULTANEOUS, MODE_PRIORITIZED, DEFAULT_MODE,
    )
    assert get_output_mode() == DEFAULT_MODE
    assert set_output_mode(MODE_SIMULTANEOUS) is True
    assert get_output_mode() == MODE_SIMULTANEOUS
    assert shared_display_enabled() is False
    assert set_output_mode(MODE_PRIORITIZED) is True
    assert shared_display_enabled() is True
    assert set_output_mode("bogus") is False
    assert get_output_mode() == MODE_PRIORITIZED


def test_ws_state_sized_by_registry():
    from core import websocket_server as ws
    from core.outputs import ALL_OUTPUTS
    assert set(ws.connected_clients) == set(ALL_OUTPUTS)
    assert set(ws.current_display_state) == set(ALL_OUTPUTS)


def test_router_cloak_other_sets_prioritized(tmpdb):
    from core.display_state import display_state
    from core.outputs import set_output_mode, MODE_PRIORITIZED
    from core.output_router import cloak_other_tabs, fan_out
    assert set_output_mode(MODE_PRIORITIZED) is True
    display_state.live_output_payloads = {
        "1": {"action": "display"}, "4": {"action": "display"},
        "7": {"action": "display"},
    }
    cloak_other_tabs("SCRIPTURE")
    assert "1" in display_state.live_output_payloads
    assert "4" not in display_state.live_output_payloads
    assert "7" not in display_state.live_output_payloads
    display_state.live_output_payloads = {}


def test_router_quiet_without_server(tmpdb):
    from core.outputs import set_output_mode, MODE_SIMULTANEOUS
    from core.output_router import (
        broadcast_tab_payload, clear_tab_outputs, cloak_other_tabs, fan_out)
    assert set_output_mode(MODE_SIMULTANEOUS) is True
    assert fan_out({"4": {"action": "display"}}) is False
    assert clear_tab_outputs("SLIDES") is False
    assert cloak_other_tabs("SLIDES") is False
    assert broadcast_tab_payload("SLIDES", {"4": {"action": "display"}}) is False


def test_display_state_scoping_follows_mode(tmpdb, monkeypatch):
    """Handles are stable per tab; the MODE re-points them (no restart)."""
    from core.display_state import (display_state, display_state_for,
                                    follow_output_mode)
    from core.outputs import set_output_mode, MODE_SIMULTANEOUS, MODE_PRIORITIZED
    assert set_output_mode(MODE_PRIORITIZED) is True
    s1, s2 = display_state_for("SCRIPTURE"), display_state_for("SLIDES")
    # Handles are per tab and never replaced; prioritized points both at
    # the shared scope.
    assert s1 is display_state_for("SCRIPTURE")  # stable
    assert s1.scope is display_state
    assert s2.scope is display_state
    assert s1.scope is s2.scope
    assert set_output_mode(MODE_SIMULTANEOUS) is True
    assert follow_output_mode() is True
    assert display_state_for("SCRIPTURE") is s1  # same handle, new scope
    assert s1.scope is not display_state and s2.scope is not display_state
    assert s1.scope is not s2.scope
    # Switching back re-shares, live.
    assert set_output_mode(MODE_PRIORITIZED) is True
    assert follow_output_mode() is True
    assert s1.scope is display_state and s2.scope is display_state


def test_mode_switch_carries_the_live_screen_across(tmpdb):
    """The switch must not blank the screens, and prioritized must make
    both tabs show the SAME content again (the operator's complaint)."""
    from core.display_state import (display_state, display_state_for,
                                    follow_output_mode)
    from core.outputs import set_output_mode, MODE_PRIORITIZED, MODE_SIMULTANEOUS
    set_output_mode(MODE_PRIORITIZED)
    scripture, decks = display_state_for("SCRIPTURE"), display_state_for("SLIDES")
    scripture.publish_live({"action": "display", "text": "In the beginning"},
                           {"item_type": "verse", "text": "In the beginning"})
    assert decks.scope.live_payload["text"] == "In the beginning"

    set_output_mode(MODE_SIMULTANEOUS)
    follow_output_mode()
    # Each tab keeps its own scope but the screen carried over.
    assert scripture.scope.live_payload["text"] == "In the beginning"
    assert decks.scope.live_payload["text"] == "In the beginning"
    assert scripture.scope is not decks.scope

    # Decks now pushes its own content; Scriptures must not follow.
    decks.publish_live({"action": "display", "text": "Deep calls to deep"},
                       {"item_type": "slide", "text": "Deep calls to deep"})
    assert decks.scope.live_payload["text"] == "Deep calls to deep"
    assert scripture.scope.live_payload["text"] == "In the beginning"

    # Back to prioritized: ONE screen again, converged on what was live.
    set_output_mode(MODE_PRIORITIZED)
    follow_output_mode()
    assert scripture.scope is decks.scope
    assert scripture.scope.live_payload["text"] == "Deep calls to deep"


def test_themes_panel_deck_scoped(qapp, tmpdb):
    from ui.panels.themes_panel import ThemesPanel
    from core.theme_loader import FREEFORM
    db.set_setting("display.slides_output_5_theme", "slides")
    panel = ThemesPanel(output_ids=("4", "5", "6"), theme_kind=FREEFORM,
                        setting_prefix="display.slides_output",
                        default_theme="slides", main_label="Main")
    _OPEN.append(panel)
    try:
        assert sorted(panel._columns) == ["4", "5", "6"]
        assert panel._columns["4"].output_id == "4"
        names = {c.current_theme for c in panel._columns.values()}
        assert "slides" in names
    finally:
        pass


def test_deck_panel_tabbed_pages(qapp, tmpdb):
    from ui.panels.deck_list_panel import DeckListPanel
    panel = DeckListPanel()
    _OPEN.append(panel)
    try:
        assert panel._pages.count() == 2
        assert panel._decks_tab_btn.isChecked()
        assert not panel._outputs_tab_btn.isChecked()
        assert panel._outputs_themes._output_ids == ("4", "5", "6")
        panel._outputs_tab_btn.click()
        assert panel._pages.currentIndex() == 1
        assert panel._outputs_tab_btn.isChecked()
        panel._decks_tab_btn.click()
        assert panel._pages.currentIndex() == 0
    finally:
        pass


def test_deck_panel_reemits_output_theme(qapp, tmpdb):
    from ui.panels.deck_list_panel import DeckListPanel
    panel = DeckListPanel()
    _OPEN.append(panel)
    try:
        seen = []
        panel.output_theme_changed.connect(lambda o, n: seen.append((o, n)))
        panel.output_theme_double_clicked.connect(
            lambda o, n: seen.append(("double", o, n)))
        col = panel._outputs_themes._columns["4"]
        col.theme_changed.emit("4", "slides")
        col.theme_double_clicked.emit("4", "slides")
        assert ("4", "slides") in seen
        assert ("double", "4", "slides") in seen
    finally:
        pass


def test_slides_tab_theme_maps_deck_outputs(qapp, tmpdb):
    from core.schedule_model import ScheduleModel
    from core.slide_service import create_deck
    from ui.tabs.slides_tab import SlidesTab
    db.set_setting("display.slides_output_4_theme", "slides")
    db.set_setting("display.output_1_theme", "default")
    create_deck("# T\n\n\nl1")
    tab = SlidesTab(schedule_model=ScheduleModel())
    _OPEN.append(tab)
    try:
        qapp.processEvents()
        assert sorted(tab._themes_by_output) == ["4", "5", "6"]
        assert tab._themes_by_output["4"] == "slides"
        assert sorted(tab._verse_themes_by_output) == ["4", "5", "6"]
        assert tab._verse_themes_by_output["4"] == "default"
    finally:
        pass


def test_settings_display_output_section(qapp, tmpdb):
    from core.outputs import (
        get_output_mode, MODE_SIMULTANEOUS, MODE_PRIORITIZED)
    from ui.tabs.settings_tab import SettingsTab
    w = SettingsTab()
    _OPEN.append(w)
    try:
        qapp.processEvents()
        assert w._output_mode_combo.currentData() == MODE_PRIORITIZED
        assert "Shared display: ON" in w._shared_display_label.text()
        w._output_mode_combo.setCurrentIndex(
            w._output_mode_combo.findData(MODE_SIMULTANEOUS))
        assert get_output_mode() == MODE_SIMULTANEOUS
        assert "Shared display: OFF" in w._shared_display_label.text()
        w._output_mode_combo.setCurrentIndex(
            w._output_mode_combo.findData("bogus"))
        # unknown value: not selectable, mode untouched
        assert get_output_mode() == MODE_SIMULTANEOUS
    finally:
        pass


# ── Active outputs: add / remove / broadcast set ──────────────────────────

def test_active_outputs_default_to_the_whole_pool(tmpdb):
    from core.outputs import active_outputs, DECK_OUTPUTS, can_add_output
    assert active_outputs("SLIDES") == DECK_OUTPUTS
    assert can_add_output("SLIDES") is False
    # Unknown/core tabs have no outputs at all.
    assert active_outputs("SETTINGS") == ()


def test_active_outputs_add_and_remove_persist(tmpdb):
    from core.outputs import (active_outputs, add_active_output, can_add_output,
                              main_output_for_tab, remove_active_output,
                              set_active_outputs)
    assert add_active_output("SLIDES") == ("4", "5", "6")
    assert set_active_outputs("SLIDES", ["5"]) == ("5",)
    assert active_outputs("SLIDES") == ("5",)
    assert main_output_for_tab("SLIDES") == "5"
    # A hole is legal (ids are the operator's OBS scenes): survivors keep
    # their own ids and order.
    assert set_active_outputs("SLIDES", ["6", "4"]) == ("6", "4")
    assert add_active_output("SLIDES") == ("6", "4", "5")
    assert can_add_output("SLIDES") is False
    assert remove_active_output("SLIDES", "4") == ("6", "5")
    # Never empty, never outside the pool.
    assert remove_active_output("SLIDES", "6") == ("5",)
    assert remove_active_output("SLIDES", "5") == ("5",)
    assert set_active_outputs("SLIDES", ["1", "9", "7"]) == ("5",)
    assert set_active_outputs("SETTINGS", ["1"]) == ()


def test_router_clears_and_cloaks_only_active_outputs(tmpdb, monkeypatch):
    from core.outputs import (MODE_PRIORITIZED, set_active_outputs,
                              set_output_mode)
    from core import output_router
    sent = []

    class FakeLoop:
        def is_closed(self):
            return False

    import core.websocket_server as ws

    def fake_broadcast(payload, target=None):
        sent.append((payload, target))
        async def _done():
            return None
        return _done()

    monkeypatch.setattr(ws, "_server_loop", FakeLoop())
    monkeypatch.setattr(ws, "broadcast_display", fake_broadcast)
    monkeypatch.setattr(output_router.asyncio, "run_coroutine_threadsafe",
                        lambda coro, loop: coro.close())
    set_output_mode(MODE_PRIORITIZED)
    set_active_outputs("SLIDES", ["4"])
    set_active_outputs("SCRIPTURE", ["1", "2"])

    output_router.clear_tab_outputs("SLIDES")
    assert [t for _p, t in sent] == ["4"]

    sent.clear()
    output_router.cloak_other_tabs("SLIDES")
    # Only the OTHER tabs' ACTIVE outputs are cloaked — a deleted output
    # is never touched, and a tab never cloaks itself.
    assert sorted(t for _p, t in sent) == ["1", "10", "2", "7", "8", "9"]


def test_deck_uncloak_never_touches_scripture_outputs(tmpdb, monkeypatch):
    """Regression: a deck cloak → uncloak used to send ONE wayward deck
    payload to output 1 (scripture's screen) because the restore path
    looked up a hardcoded "1" and the stored snapshot was seeded under it.
    """
    import asyncio as _asyncio
    from core.display_state import display_state_for, reset_display_states
    from core.outputs import MODE_SIMULTANEOUS, set_output_mode, active_outputs
    reset_display_states()
    set_output_mode(MODE_SIMULTANEOUS)

    import core.websocket_server as ws
    sent = []

    class FakeLoop:
        def is_closed(self):
            return False

    def fake_broadcast(payload, target=None):
        sent.append((payload, target))
        async def _done():
            return None
        return _done()

    monkeypatch.setattr(ws, "_server_loop", FakeLoop())
    monkeypatch.setattr(ws, "broadcast_display", fake_broadcast)
    monkeypatch.setattr(_asyncio, "run_coroutine_threadsafe",
                        lambda coro, loop: coro.close())

    from ui.tabs.slides_tab import SlidesTab
    slides = SlidesTab.__new__(SlidesTab)
    slides._display = display_state_for("SLIDES")
    slides._themes_by_output = {"4": "slides", "5": "slides", "6": "slides"}
    slides._verse_themes_by_output = {"4": "default", "5": "default",
                                      "6": "default"}
    slides._main_output = "4"
    slides._cloak = False
    slides._current_theme = "slides"
    slides._current_preview = None
    slides._is_cleared = False
    data = {
        "item_type": "slide",
        "text": "I am overwhelmed by this deep longing",
        "deck_title": "Deep Calls to Deep",
        "slides": [{"text": "I am overwhelmed by this deep longing",
                    "section": ""}],
        "slide_index": 0,
        "deck_id": 1,
    }
    slides._current_display = data
    deck_outputs = set(active_outputs("SLIDES"))

    # Cloak, then uncloak: the restore path replays stored snapshots.
    slides._on_clear_recall()
    sent.clear()
    slides._on_clear_recall()

    targets = {t for _p, t in sent}
    assert targets, "uncloak must rebroadcast the deck screen"
    assert targets <= deck_outputs, (
        f"deck restore leaked to {targets - deck_outputs}")
    # The first broadcast after a restore must not be the only clean one:
    # every own-set output is targeted, and nothing outside the set.
    assert targets == deck_outputs
    # And nothing was stored under a scripture output id.
    stored = set(slides._display.live_output_payloads)
    assert stored and stored <= deck_outputs, stored
    reset_display_states()


def test_themes_panel_adds_and_removes_outputs(tmpdb):
    from core.outputs import active_outputs
    from ui.panels.themes_panel import ThemesPanel
    panel = ThemesPanel(output_ids=active_outputs("SLIDES"), tab_key="SLIDES",
                        allow_add_remove=True)
    _OPEN.append(panel)
    seen = []
    panel.outputs_changed.connect(seen.append)

    # Full pool: no add row, and every X is live.
    assert sorted(panel._columns) == ["4", "5", "6"]
    assert panel._add_btn.isHidden()

    panel._on_remove_output("5")
    assert sorted(panel._columns) == ["4", "6"]
    assert seen[-1] == ["4", "6"]
    assert active_outputs("SLIDES") == ("4", "6")
    # A hole in the set, not a renumber: output 5 is gone, 6 stays 6.
    assert panel._add_btn.isHidden() is False

    panel._on_add_output()
    assert sorted(panel._columns) == ["4", "5", "6"]
    assert active_outputs("SLIDES") == ("4", "6", "5")
    assert panel._add_btn.isHidden()
    # Panels with no tab (fixed usage, e.g. tests) show no add row.
    plain = ThemesPanel(output_ids=("4",), tab_key=None)
    _OPEN.append(plain)
    assert plain._add_btn.isHidden()


def test_last_output_cannot_be_removed(tmpdb):
    from core.outputs import active_outputs, set_active_outputs
    from ui.panels.themes_panel import ThemesPanel
    set_active_outputs("SLIDES", ["5"])
    panel = ThemesPanel(output_ids=active_outputs("SLIDES"), tab_key="SLIDES",
                        allow_add_remove=True)
    _OPEN.append(panel)
    panel._on_remove_output("5")
    assert active_outputs("SLIDES") == ("5",)
    # The X is disabled rather than hidden: the operator can see the
    # control and learn a tab must keep one output.
    assert panel._columns["5"]._remove_btn.isEnabled() is False


def test_mode_switch_reaches_the_tab_screens(tmpdb):
    """The switch is operator-visible: subscribers must re-render, not
    keep showing their old tab's screen."""
    from core.display_state import (display_state_for, follow_output_mode,
                                    reset_display_states)
    from core.outputs import (MODE_PRIORITIZED, MODE_SIMULTANEOUS,
                              set_output_mode)
    reset_display_states()
    set_output_mode(MODE_SIMULTANEOUS)
    scripture, decks = display_state_for("SCRIPTURE"), display_state_for("SLIDES")
    seen_scripture, seen_decks = [], []
    scripture.live_changed.connect(lambda p: seen_scripture.append(p["text"]))
    decks.live_changed.connect(lambda p: seen_decks.append(p["text"]))

    decks.publish_live({"action": "display", "text": "deck screen"},
                       {"item_type": "slide", "text": "deck screen"})
    assert seen_decks == ["deck screen"] and seen_scripture == []

    set_output_mode(MODE_PRIORITIZED)
    follow_output_mode()
    # Both tabs' screens now show the one shared content.
    assert seen_scripture == ["deck screen"], seen_scripture
    assert seen_decks[-1] == "deck screen"
    # And a later push from either tab reaches both.
    scripture.publish_live({"action": "display", "text": "verse screen"},
                           {"item_type": "verse", "text": "verse screen"})
    assert seen_decks[-1] == "verse screen"
    reset_display_states()


def test_removing_an_output_blanks_its_scene(tmpdb, monkeypatch):
    """A deleted output gets nothing new written to it — so its still-open
    OBS scene must be blanked, not left frozen on the last frame."""
    from ui.panels.themes_panel import ThemesPanel
    from core import output_router
    import core.websocket_server as ws
    sent = []

    class FakeLoop:
        def is_closed(self):
            return False

    def fake_broadcast(payload, target=None):
        sent.append((payload, target))
        async def _done():
            return None
        return _done()

    monkeypatch.setattr(ws, "_server_loop", FakeLoop())
    monkeypatch.setattr(ws, "broadcast_display", fake_broadcast)
    monkeypatch.setattr(output_router.asyncio, "run_coroutine_threadsafe",
                        lambda coro, loop: coro.close())
    panel = ThemesPanel(output_ids=("4", "5", "6"), tab_key="SLIDES",
                        allow_add_remove=True)
    _OPEN.append(panel)
    panel._on_remove_output("5")
    assert sent == [({"action": "clear"}, "5")]
    # Adding one back does not blank anything.
    sent.clear()
    panel._on_add_output()
    assert sent == []


# ── Bible panel sub-page tabs: text, and named for the operator ────────────

def test_bible_panel_uses_named_text_tabs(qapp, tmpdb):
    """No icon rail: the three sub-pages are TEXT tabs, named after what
    they do — Outputs / Keyword / Semantic."""
    from ui.panels.queue_panel import QueuePanel
    panel = QueuePanel()
    _OPEN.append(panel)
    labels = [panel._tab_buttons[k].text()
              for k in ("outputs", "keyword", "semantic")]
    assert labels == ["Outputs", "Keyword", "Semantic"]
    # Text on the buttons (no pictographs), each with a real tooltip.
    for key in ("outputs", "keyword", "semantic"):
        btn = panel._tab_buttons[key]
        assert btn.toolTip(), f"{key} needs a tooltip"
        assert btn.accessibleName() == btn.text()
    # The old icon rail is gone.
    assert not hasattr(panel, "_tab_style")
    # Outputs opens by default, and the pages switch.
    assert panel._active_tab == "outputs"
    panel._switch_tab("semantic")
    assert panel._tab_buttons["semantic"].isChecked()
    assert not panel._tab_buttons["outputs"].isChecked()


def test_bible_panel_tab_clicks_switch_the_page(qapp, tmpdb):
    """A CLICK must switch the page, not just light the button.

    Regression: the text row's buttons are checkable and exclusive, so the
    row highlighted itself while nothing was wired to _switch_tab — the
    click looked alive and did nothing. Assert the stack page, not the
    highlight.
    """
    from PyQt6.QtWidgets import QWidget, QVBoxLayout
    from ui.panels.queue_panel import QueuePanel
    host = QWidget()
    panel = QueuePanel()
    QVBoxLayout(host).addWidget(panel)
    host.resize(900, 500)
    host.show()
    _OPEN.append(host)
    qapp.processEvents()

    outputs_page = panel._stack.currentIndex()

    panel._tab_buttons["keyword"].click()
    qapp.processEvents()
    assert panel._active_tab == "keyword"
    assert panel._stack.currentIndex() == panel._fts_search_index
    assert panel._stack.currentIndex() != outputs_page

    panel._tab_buttons["semantic"].click()
    qapp.processEvents()
    assert panel._active_tab == "semantic"
    assert panel._stack.currentIndex() == panel._fuzzy_search_index

    panel._tab_buttons["outputs"].click()
    qapp.processEvents()
    assert panel._active_tab == "outputs"
    assert panel._stack.currentIndex() == outputs_page


def test_hotkey_switch_then_click_still_switches(qapp, tmpdb):
    """After a hotkey moves the page, a click on another tab still works.

    (The reported shape: hotkey → page moved; clicking a tab did nothing.)
    """
    from ui.panels.queue_panel import QueuePanel
    panel = QueuePanel()
    _OPEN.append(panel)
    panel.switch_to_keyword_search = getattr(panel, "switch_to_fts_search")
    panel.switch_to_fts_search()
    assert panel._active_tab == "keyword"
    panel._tab_buttons["semantic"].click()
    assert panel._active_tab == "semantic"
    panel.switch_to_fts_search()
    assert panel._active_tab == "keyword"
    panel._tab_buttons["outputs"].click()
    assert panel._active_tab == "outputs"


def test_deck_panel_tabs_match_the_bible_panel_row(qapp, tmpdb):
    """One text-tab row implementation, so the two panels read the same."""
    from ui.panels.deck_list_panel import DeckListPanel
    from ui.panels.text_tabs import TEXT_TAB_QSS
    deck = DeckListPanel()
    bible_panel = None
    _OPEN.append(deck)
    assert deck._decks_tab_btn.text() == "Decks"
    assert deck._outputs_tab_btn.text() == "Outputs"
    # Same stylesheet in both panels — a design change lands in one place.
    assert deck._outputs_tab_btn.styleSheet() == TEXT_TAB_QSS


def test_search_pages_drop_their_duplicate_heading(qapp, tmpdb):
    """The tab names the page; a repeated in-panel title only ate height."""
    from ui.panels.queue_panel import QueuePanel
    panel = QueuePanel()
    _OPEN.append(panel)
    panel._switch_tab("keyword")
    panel._switch_tab("semantic")
    keyword_labels = [w.text() for w in panel._fts_search_panel.findChildren(
        type(panel._fts_search_panel.status_label))]
    assert "Keyword Search" not in keyword_labels
    semantic_labels = [w.text() for w in panel._fuzzy_search_panel.findChildren(
        type(panel._fuzzy_search_panel.status_label))]
    assert "Semantic Search" not in semantic_labels

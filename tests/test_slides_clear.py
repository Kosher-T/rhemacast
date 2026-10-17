"""
tests/test_slides_clear.py

Clear screen is an invisibility cloak over OBS output in the Slides
tab: while cloaked, pushes update the model/operator screens normally
but nothing is broadcast; double-click or the clear toggle removes it.
"""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import ui.widgets.display_view  # noqa: F401  (WebEngine pre-import first)

from PyQt6.QtWidgets import QApplication
import pytest


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test"])
    return app


_OPEN_TABS = []


@pytest.fixture(autouse=True)
def _close_tabs():
    """Tabs hold WebEngine views and singleton signal connections;
    leaving them shown across tests corrupts native state for later
    files (same rationale as the designer fixture)."""
    yield
    while _OPEN_TABS:
        w = _OPEN_TABS.pop()
        try:
            w.close()
            w.deleteLater()
        except RuntimeError:
            pass
    QApplication.instance().processEvents()


def _tab(qapp, tmp_path, raw="# T\n\n\nl1\n\n\nl2\n\n\nl3"):
    import core.database as db
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    from core.slide_service import create_deck, get_deck
    from core.schedule_model import ScheduleModel
    from ui.tabs.slides_tab import SlidesTab
    create_deck(raw)
    # Fresh model per test: hermetic regardless of ambient native state
    # elsewhere in the suite (production passes nothing → shared one).
    tab = SlidesTab(schedule_model=ScheduleModel())
    tab.show()
    qapp.processEvents()
    deck = get_deck(1)
    tab.live_grid.set_deck(deck, select_index=0)
    qapp.processEvents()
    _OPEN_TABS.append(tab)
    return tab


def _spy_publish(tab):
    published = []
    orig = tab._display.publish_live
    tab._display.publish_live = lambda *a, **k: published.append(True)
    return published, orig


def test_gate_matrix(qapp, tmp_path):
    tab = _tab(qapp, tmp_path)
    content = {"action": "display"}
    blank = {"action": "clear"}
    assert tab._obs_gated(content) is False
    assert tab._obs_gated(blank) is False
    tab._cloak = True
    assert tab._obs_gated(content) is True
    assert tab._obs_gated(blank) is False


def test_single_click_pushes_behind_cloak(qapp, tmp_path):
    tab = _tab(qapp, tmp_path)
    published, orig = _spy_publish(tab)
    try:
        tab._on_live_slide_double_clicked(0)
        published.clear()
        tab._on_clear_recall()
        assert tab._cloak is True
        tab._on_live_slide_clicked(2)
        assert published == [True]
        assert tab._cloak is True
        assert tab._obs_gated({"action": "display"}) is True
    finally:
        tab._display.publish_live = orig


def test_double_click_exits_cloak(qapp, tmp_path):
    tab = _tab(qapp, tmp_path)
    published, orig = _spy_publish(tab)
    try:
        tab._on_live_slide_double_clicked(0)
        published.clear()
        tab._on_clear_recall()
        assert tab._cloak is True
        tab._on_live_slide_double_clicked(1)
        assert published == [True]
        assert tab._cloak is False
        assert tab.live_preview.btn_clear.property("cloaked") is False
        assert tab._obs_gated({"action": "display"}) is False
    finally:
        tab._display.publish_live = orig


def test_toggle_off_shows_current(qapp, tmp_path):
    tab = _tab(qapp, tmp_path)
    published, orig = _spy_publish(tab)
    try:
        tab._on_live_slide_double_clicked(0)
        tab._on_clear_recall()
        tab._on_live_slide_clicked(2)  # advance behind the cloak
        assert tab._current_display["slide_index"] == 2
        tab._on_clear_recall()  # toggle off
        assert tab._cloak is False
        # Showing now-current (2), never stale recall.
        assert tab._current_display["slide_index"] == 2
        assert tab._obs_gated({"action": "display"}) is False
        assert tab.live_preview.btn_clear.property("cloaked") is False
    finally:
        tab._display.publish_live = orig


def test_button_indicates_cloak(qapp, tmp_path):
    tab = _tab(qapp, tmp_path)
    tab._on_clear_recall()
    assert tab._cloak is True
    assert tab.live_preview.btn_clear.property("cloaked") is True
    tab._on_clear_recall()
    assert tab._cloak is False
    assert tab.live_preview.btn_clear.property("cloaked") is False


def test_operator_mirrors_obs_blank(qapp, tmp_path):
    """Live screen taps the OBS feed: cloaking blanks operator views;
    pushes behind the cloak render nothing anywhere (no flash possible);
    uncloak re-renders current."""
    tab = _tab(qapp, tmp_path)
    blanks = []
    renders = []
    slot = lambda: blanks.append(True)
    render_slot = lambda _p: renders.append(True)
    tab._display.cleared.connect(slot)
    tab._display.live_changed.connect(render_slot)
    try:
        tab._on_live_slide_double_clicked(0)
        assert renders == [True]
        blanks.clear()
        renders.clear()
        tab._on_clear_recall()
        assert blanks == [True]
        assert renders == []
        tab._on_live_slide_clicked(2)  # push behind the cloak
        assert renders == []
        assert blanks == [True]
        assert tab._cloak is True
        tab._on_clear_recall()  # toggle off re-renders operator views
        assert renders == [True]
        assert blanks == [True]
        assert tab._cloak is False
    finally:
        try:
            tab._display.cleared.disconnect(slot)
        except Exception:
            pass
        try:
            tab._display.live_changed.disconnect(render_slot)
        except Exception:
            pass


def test_arrows_push_behind_cloak(qapp, tmp_path):
    tab = _tab(qapp, tmp_path)
    published, orig = _spy_publish(tab)
    try:
        tab._on_live_slide_double_clicked(0)
        published.clear()
        tab._on_clear_recall()
        tab._on_next()
        assert tab._cloak is True
        assert published == [True]
        assert tab._current_display["slide_index"] == 1
        assert tab._obs_gated({"action": "display"}) is True
        tab._on_prev()
        assert tab._current_display["slide_index"] == 0
    finally:
        tab._display.publish_live = orig


def test_song_nav_pushes_behind_cloak(qapp, tmp_path):
    tab = _tab(qapp, tmp_path,
               raw="# T\n\n\n*V1\na\n\n\nb\n\n\n*V2\nc\n")
    published, orig = _spy_publish(tab)
    try:
        tab._on_live_slide_double_clicked(0)
        published.clear()
        tab._on_clear_recall()
        tab.song_nav_step(+1)
        assert tab._cloak is True
        assert tab.live_grid._selected_index == 2
        assert published == []
        tab._end_song_nav()
        assert tab._cloak is True
        assert tab._current_display["slide_index"] == 2
        assert published == [True]
    finally:
        tab._display.publish_live = orig


def test_strip_refreshes_when_preview_screen_elsewhere(qapp, tmp_path):
    """Single-slide edits patch the preview strip even while the
    preview screen shows something else (verse / nothing)."""
    from core.slide_service import update_slide, get_deck
    tab = _tab(qapp, tmp_path)
    deck_id = 1
    tab.preview_grid.set_deck(get_deck(deck_id), select_index=0)
    qapp.processEvents()
    tab._current_preview = {
        "item_type": "verse", "text": "In the beginning",
        "ref": "GEN 1:1", "version": "",
    }
    update_slide(deck_id, 1, "CHANGED")
    tab._on_deck_slide_updated(deck_id, 1)
    card = tab.preview_grid._card_at(1)
    assert card is not None
    assert "CHANGED" in card._body.text()


def _presentation_tab(qapp):
    """SCRIPTURE tab sharing the same DisplayState singleton."""
    from core import schedule_model as sm
    from core.schedule_model import ScheduleModel
    try:
        sm.schedule_model.objectName()
    except RuntimeError:
        sm.schedule_model = ScheduleModel()
    from ui.tabs.presentation_tab import PresentationTab
    pres = PresentationTab()
    pres.show()
    _OPEN_TABS.append(pres)
    qapp.processEvents()
    return pres


def test_cloak_persists_across_tabs(qapp, tmp_path):
    """Cloak is shared live-screen state: cloaking in SLIDES cloaks
    SCRIPTURE too — its pushes stay behind the cloak everywhere."""
    tab = _tab(qapp, tmp_path)
    tab._display.set_cloaked(False)
    pres = _presentation_tab(qapp)
    renders = []
    slot = lambda _p: renders.append(True)
    tab._display.live_changed.connect(slot)
    try:
        tab._on_clear_recall()
        assert tab._cloak is True
        assert pres._cloak is True
        assert pres.live_preview.btn_clear.property("cloaked") is True
        # SCRIPTURE live push advances the model but renders nothing
        # and stays gated from OBS.
        pres._on_display_verse({
            "text": "In the beginning", "book": "GEN", "chapter": "1",
            "verse_num": "1", "version": "KJV",
        })
        assert renders == []
        assert pres._cloak is True
        assert pres._obs_gated({"action": "display"}) is True
        assert tab._obs_gated({"action": "display"}) is True
    finally:
        try:
            tab._display.live_changed.disconnect(slot)
        except Exception:
            pass
        tab._display.set_cloaked(False)


def test_presentation_toggle_uncloaks_everywhere(qapp, tmp_path):
    tab = _tab(qapp, tmp_path)
    tab._display.set_cloaked(False)
    pres = _presentation_tab(qapp)
    tab._on_clear_recall()
    assert tab._cloak is True and pres._cloak is True
    pres._on_clear_recall()
    assert tab._cloak is False and pres._cloak is False
    assert tab.live_preview.btn_clear.property("cloaked") is False
    assert pres.live_preview.btn_clear.property("cloaked") is False
    assert pres._obs_gated({"action": "display"}) is False


def test_presentation_double_click_exits_cloak(qapp, tmp_path):
    tab = _tab(qapp, tmp_path)
    tab._display.set_cloaked(False)
    pres = _presentation_tab(qapp)
    tab._on_clear_recall()
    assert pres._cloak is True
    pres._current_preview = {
        "text": "In the beginning", "book": "GEN", "chapter": 1,
        "verse_num": 1, "version": "KJV",
    }
    pres._on_preview_double_click()
    assert pres._cloak is False
    assert tab._cloak is False
    tab._display.set_cloaked(False)


def _spy_panel(tab):
    calls = []
    tab.live_preview.set_live_payload = lambda p: calls.append(("live", p))
    tab.live_preview.set_preview_payload = lambda p: calls.append(("preview", p))
    tab.live_preview.clear_live = lambda: calls.append(("clear", None))
    return calls


def test_resync_delegates_shared_state(qapp, tmp_path, monkeypatch):
    """Arriving on a tab cover-refreshes with shared payloads and arms
    the reveal fallback — stale committed frames never surface."""
    from PyQt6.QtCore import QTimer
    tab = _tab(qapp, tmp_path)
    tab._display.set_cloaked(False)
    verse = {"action": "display", "text": "V2", "ref": "EXO 1:1"}
    tab._display.publish_live(verse, {"item_type": "verse"})
    tab._display.publish_preview(verse, {"item_type": "verse"})
    refreshed = []
    tab.live_preview.refresh_views = lambda live, preview, done=None: refreshed.append((live, preview))
    timers = []
    monkeypatch.setattr(QTimer, "singleShot",
                        staticmethod(lambda ms, fn: timers.append((ms, fn))))
    tab.resync_screens()
    assert refreshed == [(verse, verse)]
    assert len(timers) == 1 and timers[0][0] == 500
    # Fallback reveals (idempotent — safe even after ack reveal).
    timers[0][1]()
    assert not tab.live_preview._live_cover.isVisible()
    assert not tab.live_preview._preview_cover.isVisible()
    tab._display.set_cloaked(False)


def test_resync_respects_cloak(qapp, tmp_path, monkeypatch):
    """Resync while cloaked re-blanks instead of re-pushing — a stale
    pre-cloak frame must never surface on arrival."""
    from PyQt6.QtCore import QTimer
    tab = _tab(qapp, tmp_path)
    tab._display.publish_live({"action": "display", "text": "V"},
                              {"item_type": "verse"})
    tab._display.set_cloaked(True)
    refreshed = []
    tab.live_preview.refresh_views = lambda live, preview, done=None: refreshed.append((live, preview))
    monkeypatch.setattr(QTimer, "singleShot",
                        staticmethod(lambda ms, fn: None))
    tab.resync_screens()
    assert refreshed and refreshed[0][0] == "clear"
    assert not [c for c in refreshed if isinstance(c[0], dict) and c[0].get("text") == "V"]
    tab._display.set_cloaked(False)


def test_resync_handles_empty_state(qapp, tmp_path, monkeypatch):
    from PyQt6.QtCore import QTimer
    tab = _tab(qapp, tmp_path)
    tab._display.set_cloaked(False)
    tab._display.live_payload = None
    tab._display.preview_payload = None
    refreshed = []
    tab.live_preview.refresh_views = lambda live, preview, done=None: refreshed.append((live, preview))
    monkeypatch.setattr(QTimer, "singleShot",
                        staticmethod(lambda ms, fn: None))
    tab.resync_screens()  # must not crash; nothing to show
    assert refreshed == [(None, None)]


def test_presentation_resync_delegates_shared_state(qapp, tmp_path, monkeypatch):
    from PyQt6.QtCore import QTimer
    _tab(qapp, tmp_path)
    pres = _presentation_tab(qapp)
    pres._display.set_cloaked(False)
    verse = {"action": "display", "text": "V3", "ref": "LEV 1:1"}
    pres._display.publish_live(verse, {"item_type": "verse"})
    refreshed = []
    pres.live_preview.refresh_views = lambda live, preview, done=None: refreshed.append((live, preview))
    monkeypatch.setattr(QTimer, "singleShot",
                        staticmethod(lambda ms, fn: None))
    pres.resync_screens()
    assert refreshed == [(verse, pres._display.preview_payload)]
    pres._display.set_cloaked(False)


def test_cloak_uncloak_never_broadcasts_off_set(qapp, tmp_path, monkeypatch):
    """A deck cloak → uncloak must touch ONLY the deck output set.

    Regression: the restore path looked up a hardcoded "1", so the first
    payload after an uncloak also went to scripture's output 1 — the
    operator had to re-send from Scriptures to get their screen back.
    """
    import asyncio as _asyncio
    import core.websocket_server as ws
    from core.outputs import (MODE_SIMULTANEOUS, active_outputs,
                              set_output_mode)
    from core.display_state import follow_output_mode
    set_output_mode(MODE_SIMULTANEOUS)
    follow_output_mode()

    sent = []

    class FakeLoop:
        def is_closed(self):
            return False

    def fake_broadcast(payload, target=None):
        sent.append((payload.get("action", "display"), target))
        async def _done():
            return None
        return _done()

    monkeypatch.setattr(ws, "_server_loop", FakeLoop())
    monkeypatch.setattr(ws, "broadcast_display", fake_broadcast)
    monkeypatch.setattr(_asyncio, "run_coroutine_threadsafe",
                        lambda coro, loop: coro.close())

    tab = _tab(qapp, tmp_path)
    deck = {"id": 1, "title": "# T",
            "slides": [{"text": "l1", "section": ""}], "format": None}
    tab._show_slide(deck, 0, live=True)

    sent.clear()
    tab._on_clear_recall()   # cloak
    cloak_targets = {t for _a, t in sent}
    tab._on_clear_recall()   # uncloak
    sent.clear()
    tab._on_clear_recall()   # uncloak again (restore replays snapshots)
    targets = {t for _a, t in sent}

    deck_set = set(active_outputs("SLIDES"))
    assert deck_set == {"4", "5", "6"}
    assert cloak_targets == deck_set, cloak_targets
    assert targets == deck_set, f"deck restore leaked: {targets - deck_set}"
    assert set(tab._display.live_output_payloads) <= deck_set

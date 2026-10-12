"""
tests/test_theme_switch.py

Theme-switch contract (docs/theme-switch-contract.md):
- switch payloads always carry a complete, non-null theme_data —
  even when per-machine settings name a theme missing on this machine
  (the deck→scripture carryover class);
- re-theming preserves content identity (slide stays slide);
- renderer resetTheme() covers every --rc-* variable applyTheme() sets,
  in both renderer copies (display.js + embedded DisplayView copy).
"""

import asyncio
import os
import re

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


_OPEN = []


@pytest.fixture(autouse=True)
def _close_tabs():
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


def _init_db(tmp_path):
    import core.database as db
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    return db


def _ensure_schedule_singleton():
    """SchedulePanel() with no model uses the global schedule_model
    singleton — which earlier suite files may have deleted with their
    panels. Resurrect it; production never deletes singletons."""
    from core import schedule_model as sm
    from core.schedule_model import ScheduleModel
    try:
        sm.schedule_model.objectName()
    except RuntimeError:
        sm.schedule_model = ScheduleModel()


# ── resolve_theme ─────────────────────────────────────────────────────

def test_resolve_unknown_theme_falls_back_to_default(tmp_path):
    _init_db(tmp_path)
    from core.theme_loader import resolve_theme
    name, data = resolve_theme("no-such-theme-anywhere")
    assert name == "default"
    assert isinstance(data, dict) and data


def test_resolve_empty_theme_falls_back_to_default(tmp_path):
    _init_db(tmp_path)
    from core.theme_loader import resolve_theme
    name, data = resolve_theme("")
    assert name == "default"
    assert isinstance(data, dict) and data


def test_resolve_known_theme_returns_isolated_copy(tmp_path):
    _init_db(tmp_path)
    from core.theme_loader import get_theme, resolve_theme
    name, data = resolve_theme("default")
    assert name == "default"
    assert data == get_theme("default")
    assert data is not get_theme("default")
    data["text"] = "MUTATED"
    assert get_theme("default").get("text") != "MUTATED"


# ── payload completeness (both tabs, bogus configured themes) ─────────

def _slides_tab(qapp, tmp_path, slides_theme="bogus-theme", verse_theme="bogus-theme"):
    db = _init_db(tmp_path)
    db.set_setting("display.slides_output_1_theme", slides_theme)
    db.set_setting("display.output_1_theme", verse_theme)
    from core.schedule_model import ScheduleModel
    from core.slide_service import create_deck, get_deck
    from ui.tabs.slides_tab import SlidesTab
    create_deck("# T\n\n\nl1\n\n\nl2\n\n\nl3")
    tab = SlidesTab(schedule_model=ScheduleModel())
    tab.show()
    _OPEN.append(tab)
    qapp.processEvents()
    tab.live_grid.set_deck(get_deck(1), select_index=0)
    qapp.processEvents()
    return tab


def test_slides_tab_payload_never_null_theme_data(qapp, tmp_path):
    tab = _slides_tab(qapp, tmp_path)
    slide = tab._build_payload("line", "Title", is_slide=True)
    verse = tab._build_payload("text", "GEN 1:1", is_slide=False)
    # Per-kind fallbacks (not app-wide): slides -> "slides", verses -> "default".
    assert slide["theme"] == "slides" and isinstance(slide["theme_data"], dict)
    assert verse["theme"] == "default" and isinstance(verse["theme_data"], dict)
    assert verse["content"] == "verse"
    assert "slide_format" not in verse


def test_presentation_tab_payload_never_null_theme_data(qapp, tmp_path):
    db = _init_db(tmp_path)
    db.set_setting("display.output_1_theme", "bogus-theme")
    from ui.tabs.presentation_tab import PresentationTab
    _ensure_schedule_singleton()
    tab = PresentationTab()
    tab.show()
    _OPEN.append(tab)
    qapp.processEvents()
    payload = tab._build_payload("In the beginning", "[KJV] GEN 1:1", "KJV",
                                 "GEN", "1", "1")
    assert payload["theme"] == "default"
    assert isinstance(payload["theme_data"], dict) and payload["theme_data"]
    assert payload["content"] == "verse"
    assert "slide_format" not in payload


def _capture_broadcasts(monkeypatch):
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

    def fake_rc(coro, loop):
        coro.close()
        return None

    monkeypatch.setattr(ws, "_server_loop", FakeLoop())
    monkeypatch.setattr(ws, "broadcast_display", fake_broadcast)
    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", fake_rc)
    return sent


def test_presentation_rebroadcast_preserves_slide_identity(qapp, tmp_path, monkeypatch):
    db = _init_db(tmp_path)
    db.set_setting("display.output_1_theme", "default")
    from ui.tabs.presentation_tab import PresentationTab
    _ensure_schedule_singleton()
    tab = PresentationTab()
    tab.show()
    _OPEN.append(tab)
    qapp.processEvents()
    sent = _capture_broadcasts(monkeypatch)
    original = tab._build_payload("lyric", "Song", "", content="slide",
                                  slide_format={"case": "upper"}, deck_id=7)
    tab._broadcast_to_ws(original)
    assert sent, "expected per-output rebroadcasts"
    for themed, _oid in sent:
        assert themed["content"] == "slide"
        assert themed["deck_id"] == 7
        assert themed["slide_format"] == {"case": "upper"}
        assert isinstance(themed["theme_data"], dict) and themed["theme_data"]


def test_presentation_rebroadcast_verse_stays_clean(qapp, tmp_path, monkeypatch):
    db = _init_db(tmp_path)
    db.set_setting("display.output_1_theme", "default")
    from ui.tabs.presentation_tab import PresentationTab
    _ensure_schedule_singleton()
    tab = PresentationTab()
    tab.show()
    _OPEN.append(tab)
    qapp.processEvents()
    sent = _capture_broadcasts(monkeypatch)
    verse = tab._build_payload("In the beginning", "[KJV] GEN 1:1", "KJV",
                               "GEN", "1", "1")
    # Verse shown right after a deck: no deck overrides may hitchhike.
    tab._broadcast_to_ws(verse)
    assert sent
    for themed, _oid in sent:
        assert themed["content"] == "verse"
        assert "slide_format" not in themed
        assert isinstance(themed["theme_data"], dict) and themed["theme_data"]


# ── renderer reset coverage (both copies) ─────────────────────────────

def _theme_vars(path):
    src = open(path).read()
    all_vars = set(re.findall(r"--rc-[a-z-]+", src))
    m = re.search(r"function resetTheme\(\) \{(.*?)\n\}", src, re.S)
    assert m, f"resetTheme not found in {path}"
    reset_vars = set(re.findall(r"--rc-[a-z-]+", m.group(1)))
    return all_vars, reset_vars


@pytest.mark.parametrize("path", [
    "display/display.js",
    "ui/widgets/display_view.py",
])
def test_reset_covers_every_theme_variable(path):
    all_vars, reset_vars = _theme_vars(path)
    assert all_vars, f"no theme vars found in {path}"
    assert all_vars <= reset_vars, (
        f"stale-carryover risk in {path}: {sorted(all_vars - reset_vars)}"
    )


def test_renderer_copies_agree_on_reset_list():
    _, reset_js = _theme_vars("display/display.js")
    _, reset_embedded = _theme_vars("ui/widgets/display_view.py")
    assert reset_js == reset_embedded


def test_cross_tab_uncloak_keeps_originating_verse_theme(qapp, tmp_path, monkeypatch):
    """The same authority rule applies in the other direction.

    A verse displayed with the SCRIPTURE output theme, cloaked in SCRIPTURE,
    then uncloaked from SLIDES must not come back wearing the SLIDES verse
    map. Stored payloads are tab-agnostic; local maps are not.
    """
    db = _init_db(tmp_path)
    db.set_setting("display.slides_output_1_theme", "slides")
    db.set_setting("display.output_1_theme", "fullscreen")

    from core.display_state import DisplayState
    from ui.tabs.presentation_tab import PresentationTab
    from ui.tabs.slides_tab import SlidesTab

    scripture = PresentationTab.__new__(PresentationTab)
    scripture._themes_by_output = {"1": "fullscreen"}
    scripture._current_theme = "fullscreen"
    original = scripture._build_payload(
        "In the beginning", "[KJV] Genesis 1:1", "KJV",
        "Genesis", "1", "1", output_id="1",
    )
    assert original["content"] == "verse"
    assert original["theme"] == "fullscreen"

    live_data = {
        "text": original["text"],
        "book": "Genesis",
        "chapter": "1",
        "verse_num": "1",
        "version": "KJV",
    }
    state = DisplayState()
    state.publish_live(original, live_data, None, False)
    state.set_cloaked(True)

    slides = SlidesTab.__new__(SlidesTab)
    slides._display = state
    slides._themes_by_output = {"1": "slides"}
    slides._verse_themes_by_output = {"1": "default"}

    sent = _capture_broadcasts(monkeypatch)
    renders = []
    slot = lambda payload: renders.append(dict(payload))
    state.live_changed.connect(slot)
    try:
        slides._on_clear_recall()
    finally:
        try:
            state.live_changed.disconnect(slot)
        except Exception:
            pass
        state.set_cloaked(False)

    assert state.cloaked is False
    assert renders, "uncloak must re-render live"
    restored = state.live_payload
    assert restored["content"] == "verse"
    assert renders[-1]["theme"] == "fullscreen"
    assert restored["theme"] == "fullscreen"
    assert sent, "uncloak must rebroadcast live"
    assert all(payload["theme"] == "fullscreen" for payload, _target in sent)


def test_cross_tab_uncloak_keeps_originating_slide_theme(qapp, tmp_path, monkeypatch):
    """A Slides deck push must survive cloak -> SCRIPTURE -> uncloak.

    Regression for a live-service failure: a slide displayed with the Slides
    output theme, cloaked in SLIDES, then uncloaked from SCRIPTURE came back
    wearing the SCRIPTURE output theme instead. The stored live payload —
    including the theme chosen by the originating push — is authoritative,
    so uncloak must reuse it rather than rebuild from the active tab.
    """
    db = _init_db(tmp_path)
    db.set_setting("display.slides_output_1_theme", "slides")
    db.set_setting("display.output_1_theme", "fullscreen")

    from core.display_state import DisplayState
    from ui.tabs.presentation_tab import PresentationTab
    from ui.tabs.slides_tab import SlidesTab

    slides = SlidesTab.__new__(SlidesTab)
    slides._themes_by_output = {"1": "slides", "2": "slides"}
    slides._verse_themes_by_output = {"1": "default", "2": "default"}
    original = slides._build_payload(
        "I am overwhelmed by this deep longing, Lord",
        "Deep Calls to Deep",
        "",
        output_id="1",
        slide_format=None,
        deck_id=1,
    )
    assert original["content"] == "slide"
    assert original["theme"] == "slides"
    assert original["theme_data"]["slide"]["show_title"] is False

    live_data = {
        "item_type": "slide",
        "text": original["text"],
        "ref": original["ref"],
        "version": "",
        "deck_title": "Deep Calls to Deep",
        "slide_format": None,
        "slides": [{"text": original["text"], "section": ""}],
        "slide_index": 0,
        "deck_id": 1,
    }
    state = DisplayState()
    state.publish_live(original, live_data, None, False)
    slides._display = state

    sent = _capture_broadcasts(monkeypatch)
    slides._broadcast_to_ws(original, live_data)
    assert len(sent) == 2
    assert all(payload["theme"] == "slides" for payload, _target in sent)
    assert set(state.live_output_payloads) == {"1", "2"}
    assert set(state.matching_live_output_payloads()) == {"1", "2"}
    sent.clear()
    state.set_cloaked(True)
    assert set(state.matching_live_output_payloads()) == {"1", "2"}

    scripture = PresentationTab.__new__(PresentationTab)
    scripture._display = state
    scripture._themes_by_output = {"1": "fullscreen", "2": "fullscreen"}
    scripture._current_theme = "fullscreen"

    renders = []
    slot = lambda payload: renders.append(dict(payload))
    state.live_changed.connect(slot)
    try:
        scripture._on_clear_recall()
    finally:
        try:
            state.live_changed.disconnect(slot)
        except Exception:
            pass
        state.set_cloaked(False)

    assert state.cloaked is False
    assert renders, "uncloak must re-render live"
    restored = state.live_payload
    assert restored["content"] == "slide"
    assert renders[-1]["theme"] == "slides"
    assert restored["theme"] == "slides"
    assert restored["theme_data"]["slide"]["show_title"] is False
    assert sent, "uncloak must rebroadcast live"
    assert [(payload["theme"], target) for payload, target in sent] == [
        ("slides", "1"), ("slides", "2")
    ]
    assert all(payload.get("deck_id") == 1 for payload, _target in sent)

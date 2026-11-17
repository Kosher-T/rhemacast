"""Shared fakes for the display push-path tests.

Every path is exercised through its real tab method with a real
``DisplayState`` scope. Tabs are built with ``__new__`` (no widgets): the
contract under test is the payload each path builds and the motion kind it
feeds the shared model, not layout.

OBS fan-out is captured at the router boundary, so the assertions look at
the per-output payload that would actually go on the wire, after the tab
has rebuilt it for each output theme.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import core.database as db
import core.output_router as output_router


class BrowserPanelStub:
    """The browser-panel surface the push paths touch."""

    def __init__(self, book="John", translation="KJV", verse=None):
        self._current_book = book
        self._current_translation = translation
        self._verse = verse or {
            "chapter": "11", "verse": "36",
            "text": "Jesus wept.",
        }
        self.navigations = []

    def get_selected_verse(self):
        return dict(self._verse)

    def navigate_to_reference(self, *a, **k):
        self.navigations.append((a, k))

    def _set_highlight(self, *a, **k):
        pass

    def _scroll_to_highlight(self):
        pass

    def _update_navigator(self):
        pass


class Capture:
    """Per-output payloads + motion pushes recorded during one path call."""

    def __init__(self):
        self.outputs = []
        self.pushes = []

    @property
    def last_wire_payloads(self):
        assert self.outputs, "path did not reach the OBS fan-out"
        return self.outputs[-1][1]

    @property
    def last_wire_payload(self):
        return self.last_wire_payloads["1"]


def make_state():
    from core.display_state import DisplayState

    state = DisplayState()
    state.seed_output_id = "1"
    return state


def verse_data(text="Jesus wept.", book="John", chapter="11", verse="36",
               version="KJV", item_type="verse"):
    return {
        "item_type": item_type,
        "text": text,
        "book": book,
        "chapter": chapter,
        "verse_num": verse,
        "version": version,
    }


def prime_live(state, kind="scripture", text="Primed verse."):
    """Leave the shared scope SHOWN with content of ``kind``.

    That is the state a real operator is in before the next push, and the
    state the pairing rule compares against.
    """
    if kind == "freeform":
        payload = {
            "action": "display", "text": text, "ref": "Primed Deck",
            "reference": "Primed Deck", "translation": "",
            "book": "", "chapter": "", "verse": "",
            "content": "slide", "kind": "freeform",
            "theme": "slides", "theme_data": {"schema_version": 2},
        }
        data = {"item_type": "slide", "text": text, "ref": "Primed Deck",
                "deck_id": 1, "deck_title": "Primed Deck", "slides": [],
                "slide_index": 0, "version": ""}
    else:
        payload = {
            "action": "display", "text": text, "ref": "[KJV] John 11:1",
            "reference": "John 11:1", "translation": "King James Version",
            "book": "John", "chapter": "11", "verse": "1",
            "content": "verse", "kind": "scripture",
            "theme": "default", "theme_data": {"schema_version": 2},
        }
        data = verse_data(text=text, verse="1")
    state.publish_live(payload, data)
    state.remember_live_output_payloads({"1": payload})
    return payload


def install_capture(monkeypatch, state):
    """Capture OBS payloads and record every motion push with its actions."""
    capture = Capture()

    monkeypatch.setattr(db, "log_live_payload", lambda *a, **k: None)
    monkeypatch.setattr(
        output_router, "broadcast_tab_payload",
        lambda tab_key, themed: capture.outputs.append((tab_key, themed)))
    monkeypatch.setattr(output_router, "send_action", lambda *a, **k: False)

    original_push = state.motion.push

    def push(kind="other", **kwargs):
        actions = original_push(kind, **kwargs)
        capture.pushes.append((kind, actions))
        return actions

    monkeypatch.setattr(state.motion, "push", push)
    return capture


def presentation_tab(state, theme="default", browser=None):
    from ui.tabs.presentation_tab import PresentationTab

    tab = PresentationTab.__new__(PresentationTab)
    tab._display = state
    tab._themes_by_output = {"1": theme}
    tab._main_output = "1"
    tab._current_theme = theme
    tab.browser_panel = browser or BrowserPanelStub()
    tab._record_scripture_display = lambda *a, **k: None
    tab._arm_schedule_ring = lambda *a, **k: None
    return tab


def slides_tab(state, verse_theme="default", slide_theme="slides",
               browser=None):
    from ui.tabs.slides_tab import SlidesTab

    tab = SlidesTab.__new__(SlidesTab)
    tab._display = state
    tab._themes_by_output = {"1": slide_theme}
    tab._verse_themes_by_output = {"1": verse_theme}
    tab._main_output = "1"
    tab._current_theme = slide_theme
    tab.browser_panel = browser or BrowserPanelStub()
    tab.live_grid = object()
    tab.preview_grid = object()
    tab._sync_grid = lambda *a, **k: None
    tab._song_nav_active = False
    tab._song_nav_index = None
    return tab


def expected_actions(prime_kind, pushed_kind):
    if prime_kind == "scripture" and pushed_kind == "scripture":
        return ({"action": "transition_out"}, {"action": "transition_in"})
    return ({"action": "out"}, {"action": "in"})


def assert_live_push(capture, expected_kind, prime_kind="scripture",
                     check_actions=True):
    """Assert the last live push carried ``kind`` on the wire and in motion."""
    from core.websocket_server import sanitize_payload

    assert capture.pushes, "path did not publish to the shared state"
    pushed_kind, actions = capture.pushes[-1]
    assert pushed_kind == expected_kind, (
        f"motion saw {pushed_kind!r}, expected {expected_kind!r}")
    if check_actions:
        assert actions == expected_actions(prime_kind, expected_kind), (
            f"pairing for {prime_kind} -> {expected_kind} was {actions!r}")

    wire = capture.last_wire_payload
    assert wire.get("kind") == expected_kind, (
        f"OBS payload kind {wire.get('kind')!r}, expected {expected_kind!r}")
    assert wire.get("content") == (
        "verse" if expected_kind == "scripture" else "slide")
    sanitized = sanitize_payload(wire)
    assert sanitized.get("kind") == expected_kind
    assert "kind_missing" not in sanitized, (
        "a labelled payload must not be flagged as missing its kind")
    return wire

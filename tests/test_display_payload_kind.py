"""Every live verse/slide push path labels its payload for motion pairing.

The bug: an unlabelled payload was treated as ``scripture`` by the page, so
scripture -> scripture played the transition pair. The server now stamps
``other`` and the page treats a missing label as ``other`` (OUT/IN), which
means every live sender must carry its own ``kind``. These tests call each
push path on its real tab method and assert the kind that reaches the shared
motion model and the per-output OBS payload.

The theme used here (``default``) declares no animation slots at all, let
alone transition slots. Scripture -> scripture therefore has nothing to play;
the renderer-level zero-animation proof lives in ``test_display_js.py`` and
``test_theme_v2_animation_runtime.py``.
"""

from tests.display_push_paths import (
    assert_live_push, expected_actions, install_capture, make_state,
    presentation_tab, prime_live, slides_tab, verse_data,
)


def _has_transition_slots(theme: dict) -> bool:
    for container in theme.get("containers", []):
        animation = container.get("animation")
        if isinstance(animation, dict) and animation.get("transition"):
            return True
        for block in (container.get("blocks") or {}).values():
            if not isinstance(block, dict):
                continue
            animation = block.get("animation")
            if isinstance(animation, dict) and animation.get("transition"):
                return True
    return False


def _assert_no_transition_slots(wire: dict):
    assert not _has_transition_slots(wire["theme_data"]), (
        "the per-path zero-animation proof needs a theme without transition slots")


def _run(monkeypatch, build_tab, call, expected_kind,
         prime_kind="scripture", check_actions=True, check_wire=True):
    state = make_state()
    capture = install_capture(monkeypatch, state)
    prime_live(state, kind=prime_kind)
    capture.pushes.clear()
    tab = build_tab(state)
    call(tab, state)
    if check_wire:
        wire = assert_live_push(capture, expected_kind, prime_kind,
                                check_actions=check_actions)
        _assert_no_transition_slots(wire)
        return capture, wire
    assert capture.pushes, "path did not publish to the shared state"
    pushed_kind = capture.pushes[-1][0]
    assert pushed_kind == expected_kind
    return capture, None


# ── SCRIPTURE tab: direct verse gestures ─────────────────────────────────

def test_queue_show_labels_scripture(monkeypatch):
    _run(monkeypatch, presentation_tab,
         lambda tab, state: tab._on_display_verse(
             verse_data(text="Queue show verse.")),
         "scripture")


def test_browser_double_click_labels_scripture(monkeypatch):
    _run(monkeypatch, presentation_tab,
         lambda tab, state: tab._on_browser_broadcast("KJV"),
         "scripture")


def test_translation_broadcast_labels_scripture(monkeypatch):
    monkeypatch.setattr("core.bible_service.get_verse",
                        lambda *a, **k: {"text": "Translation text."})
    _run(monkeypatch, presentation_tab,
         lambda tab, state: tab._on_translation_broadcast("NKJV"),
         "scripture")


def test_translation_broadcast_falls_back_to_browser(monkeypatch):
    _run(monkeypatch, presentation_tab,
         lambda tab, state: tab._on_translation_broadcast("NKJV"),
         "scripture")


def test_navigator_push_labels_scripture(monkeypatch):
    monkeypatch.setattr("core.bible_service.get_verse",
                        lambda *a, **k: {"text": "Navigator text."})
    _run(monkeypatch, presentation_tab,
         lambda tab, state: tab._on_navigator_push("John", "11", "36"),
         "scripture")


def test_search_to_live_labels_scripture(monkeypatch):
    monkeypatch.setattr("core.bible_service.get_verse",
                        lambda *a, **k: {"text": "Search text."})
    _run(monkeypatch, presentation_tab,
         lambda tab, state: tab._on_search_to_live(
             {"book": "John", "chapter": "11", "verse_num": "36",
              "version": "KJV"}),
         "scripture")


def test_translation_badge_to_live_labels_scripture(monkeypatch):
    _run(monkeypatch, presentation_tab,
         lambda tab, state: tab._on_trans_badge_to_live(
             {"book": "John", "chapter": "11", "verse_num": "36",
              "text": "Badge text.", "version": "KJV"}),
         "scripture")


def test_history_double_click_labels_scripture(monkeypatch):
    monkeypatch.setattr("core.bible_service.get_verse",
                        lambda *a, **k: {"text": "History text."})
    _run(monkeypatch, presentation_tab,
         lambda tab, state: tab._on_history_verse_double_clicked(
             {"book": "John", "chapter": "11", "verse_num": "36",
              "version": "KJV"}),
         "scripture")


def test_preview_double_click_rebuild_labels_scripture(monkeypatch):
    def call(tab, state):
        state.preview_data = verse_data(text="Preview rebuilt.")
        state.preview_payload = None
        tab._on_preview_double_click()

    _run(monkeypatch, presentation_tab, call, "scripture")


def test_preview_double_click_replay_carries_stored_kind(monkeypatch):
    stored = {
        "action": "display", "text": "Preview stored.", "ref": "[KJV] John 11:36",
        "reference": "John 11:36", "translation": "King James Version",
        "book": "John", "chapter": "11", "verse": "36",
        "content": "verse", "kind": "scripture",
        "theme": "default", "theme_data": {"schema_version": 2},
    }

    def call(tab, state):
        data = verse_data(text="Preview stored.")
        state.preview_data = data
        state.publish_preview(stored, data)
        tab._on_preview_double_click()

    _run(monkeypatch, presentation_tab, call, "scripture")


def test_theme_double_click_relabels_scripture(monkeypatch):
    def call(tab, state):
        state.live_data = verse_data(text="Primed verse.")
        tab._on_theme_double_click("1", "default")

    _run(monkeypatch, presentation_tab, call, "scripture")


def test_navigate_to_bible_verse_labels_scripture(monkeypatch):
    _run(monkeypatch, presentation_tab,
         lambda tab, state: tab._navigate_to_bible_verse(
             {"book": "John", "chapter": "11", "verse": "36",
              "text": "Navigated text."}, "KJV"),
         "scripture")


def test_schedule_item_labels_scripture(monkeypatch):
    _run(monkeypatch, presentation_tab,
         lambda tab, state: tab._display_schedule_item(
             {"ref": "[KJV] John 11:36", "text": "Schedule text.",
              "translation": "KJV"}),
         "scripture")


def test_schedule_double_click_labels_scripture(monkeypatch):
    _run(monkeypatch, presentation_tab,
         lambda tab, state: tab._on_schedule_double_click(
             {"ref": "[KJV] John 11:36", "book": "John", "chapter": "11",
              "verse": "36", "text": "Schedule text.", "translation": "KJV",
              "theme": "default"}),
         "scripture")


def test_translation_rename_relabels_scripture(monkeypatch):
    def call(tab, state):
        state.live_data = verse_data(text="Primed verse.")
        tab.refresh_display_names("KJV", "NKJV")

    _run(monkeypatch, presentation_tab, call, "scripture")


def test_uncloak_republish_carries_scripture(monkeypatch):
    def call(tab, state):
        state.set_cloaked(True)
        tab._uncloak_now()

    _run(monkeypatch, presentation_tab, call, "scripture",
         check_actions=False, check_wire=False)


def test_scripture_tab_slide_push_labels_freeform(monkeypatch):
    _run(monkeypatch, presentation_tab,
         lambda tab, state: tab._apply_slide_display(
             None, "Deck", [{"text": "Slide text."}], 0),
         "freeform")


# ── SLIDES tab: deck and verse gestures ──────────────────────────────────

def test_deck_slide_labels_freeform(monkeypatch):
    deck = {"id": 7, "title": "Deck", "slides": [{"text": "Slide text."}]}
    _run(monkeypatch, slides_tab,
         lambda tab, state: tab._show_slide(deck, 0, live=True),
         "freeform")


def test_slides_tab_verse_labels_scripture(monkeypatch):
    _run(monkeypatch, slides_tab,
         lambda tab, state: tab._show_verse(
             "[KJV] John 11:36", "Verse text.", "KJV", live=True,
             parts={"book": "John", "chapter": "11", "verse_num": "36"}),
         "scripture")


def test_slides_preview_slide_double_click_labels_freeform(monkeypatch):
    def call(tab, state):
        state.preview_data = {
            "item_type": "slide", "text": "Preview slide.",
            "ref": "Deck \u00b7 V1", "deck_title": "Deck", "deck_id": 7,
            "slides": [{"text": "Preview slide.", "section": "V1"}],
            "slide_index": 0, "slide_format": None, "version": "",
        }
        tab._on_preview_double_click()

    _run(monkeypatch, slides_tab, call, "freeform")


def test_slides_preview_verse_rebuild_labels_scripture(monkeypatch):
    def call(tab, state):
        state.preview_data = verse_data(text="Preview verse.")
        state.preview_payload = None
        tab._on_preview_double_click()

    _run(monkeypatch, slides_tab, call, "scripture")


def test_slides_preview_verse_replay_carries_stored_kind(monkeypatch):
    stored = {
        "action": "display", "text": "Preview verse.", "ref": "[KJV] John 11:36",
        "reference": "John 11:36", "translation": "King James Version",
        "book": "John", "chapter": "11", "verse": "36",
        "content": "verse", "kind": "scripture",
        "theme": "default", "theme_data": {"schema_version": 2},
    }

    def call(tab, state):
        data = verse_data(text="Preview verse.")
        state.preview_data = data
        state.publish_preview(stored, data)
        tab._on_preview_double_click()

    _run(monkeypatch, slides_tab, call, "scripture")


def test_slides_theme_double_click_relabels_freeform(monkeypatch):
    def call(tab, state):
        state.live_data = {
            "item_type": "slide", "text": "Live slide.", "ref": "Deck \u00b7 V1",
            "deck_id": 7, "deck_title": "Deck", "slides": [],
            "slide_index": 0, "slide_format": None, "version": "",
        }
        tab._on_output_theme_double_click("1", "slides")

    _run(monkeypatch, slides_tab, call, "freeform")


def test_slides_theme_double_click_relabels_scripture(monkeypatch):
    def call(tab, state):
        state.live_data = verse_data(text="Live verse.")
        tab._on_output_theme_double_click("1", "default")

    _run(monkeypatch, slides_tab, call, "scripture")


def test_slides_translation_rename_relabels_freeform(monkeypatch):
    def call(tab, state):
        state.live_data = {
            "item_type": "slide", "text": "Live slide.", "ref": "Deck",
            "deck_id": 7, "deck_title": "Deck", "slides": [],
            "slide_index": 0, "slide_format": None, "version": "",
        }
        tab.refresh_display_names("KJV", "NKJV")

    _run(monkeypatch, slides_tab, call, "freeform")


def test_slides_uncloak_republish_carries_kind(monkeypatch):
    def call(tab, state):
        state.set_cloaked(True)
        tab._uncloak_now()

    _run(monkeypatch, slides_tab, call, "scripture",
         check_actions=False, check_wire=False)


# ── The pairing rule itself is exercised by every assertion above ────────

def test_scripture_to_freeform_is_out_then_in():
    assert expected_actions("scripture", "freeform") == (
        {"action": "out"}, {"action": "in"})


def test_scripture_to_scripture_is_the_transition_pair():
    assert expected_actions("scripture", "scripture") == (
        {"action": "transition_out"}, {"action": "transition_in"})


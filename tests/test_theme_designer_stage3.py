"""Stage 3: phase cards host registry-driven ParamForm / Timeline editors."""

from __future__ import annotations

import copy
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from PyQt6.QtCore import QEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from core import animation_registry as registry  # noqa: E402
from ui.theme_kit import InlineMessage, Timeline  # noqa: E402
from ui.widgets.theme_designer.animation_panel import AnimationPanel  # noqa: E402
from ui.widgets.theme_designer.param_form import ParamForm  # noqa: E402

_QAPP = None


@pytest.fixture(scope="module")
def qapp():
    global _QAPP
    _QAPP = QApplication.instance() or QApplication([])
    return _QAPP


def _theme() -> dict:
    return {
        "schema_version": 2,
        "kind": "scripture",
        "name": "Stage 3 test",
        "unknown_top": {"keep": True},
        "animations": {
            "gold": {
                "type": "typewriter", "duration_ms": 900, "delay_ms": 0,
                "easing": "ease-out", "cursor": "block", "x_custom": 7,
            },
            "morph": {
                "type": "custom",
                "keyframes": [{"at": 0, "opacity": 0},
                              {"at": 1, "opacity": 1}],
            },
        },
        "containers": [{
            "id": "c1",
            "rect": {"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.6},
            "animation": {
                "entry": "gold",
                "out": {"type": "fade_in", "duration_ms": 400},
                "transition": {
                    "in": {"use": "gold", "duration_ms": 300},
                    "out": "morph",
                },
            },
        }],
    }


def _panel(qapp, theme=None):
    panel = AnimationPanel()
    panel.load_theme(theme or _theme())
    qapp.processEvents()
    return panel


def _flush(qapp):
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def _form(card):
    return card.findChild(ParamForm)


def test_five_registry_driven_phase_cards(qapp):
    panel = _panel(qapp)
    assert set(panel._cards) == {"entry", "transition_in", "sustain",
                                 "transition_out", "out"}
    entry = panel.card("entry")
    assert entry.value() == "gold"
    spec = registry.SLOT_PARAMS["duration_ms"]
    assert entry._duration_range == (spec.minimum, spec.maximum)
    assert entry._easing_presets == list(registry.ANIMATION_EASINGS)
    assert tuple(entry._origin_options) == tuple(registry.ORIGIN_VALUES)


def test_named_theme_definition_edits_preserve_unknown_keys(qapp):
    panel = _panel(qapp)
    emitted: list[dict] = []
    panel.theme_changed.connect(emitted.append)
    form = _form(panel.card("entry"))
    assert form is not None and form.spec.type == "typewriter"
    # Shared timing/origin rows belong to the card, not the embedded form.
    assert "duration_ms" not in form._rows
    form.set_value("reveal", "word", emit=True)

    gold = panel.theme()["animations"]["gold"]
    assert gold["reveal"] == "word"
    assert gold["duration_ms"] == 900
    assert gold["x_custom"] == 7
    assert emitted and emitted[-1]["unknown_top"] == {"keep": True}
    assert emitted[-1]["containers"][0]["animation"]["entry"] == "gold"


def test_inline_slot_edits_slot_in_place(qapp):
    theme = _theme()
    theme["containers"][0]["animation"]["transition"]["in"] = {
        "type": "typewriter", "duration_ms": 400, "reveal": "char"}
    panel = _panel(qapp, theme)
    form = _form(panel.card("transition_in"))
    assert form is not None and form.spec.type == "typewriter"
    form.set_value("reveal", "word", emit=True)

    slot = panel.theme()["containers"][0]["animation"]["transition"]["in"]
    assert slot["type"] == "typewriter"
    assert slot["reveal"] == "word"
    assert slot["duration_ms"] == 400


def test_custom_definition_hosts_timeline_and_writes_frames(qapp):
    panel = _panel(qapp)
    card = panel.card("transition_out")
    timeline = card.findChild(Timeline)
    assert timeline is not None
    frames = [
        {"at": 0, "opacity": 0, "x": 0, "y": 0, "scale": 1, "rotate": 0,
         "blur": 0},
        {"at": 0.5, "opacity": 1, "x": 0, "y": 0, "scale": 1, "rotate": 0,
         "blur": 0},
        {"at": 1, "opacity": 1, "x": 0, "y": 0, "scale": 1, "rotate": 0,
         "blur": 0},
    ]
    timeline.changed.emit(frames)
    assert len(panel.theme()["animations"]["morph"]["keyframes"]) == 3


def test_switch_to_builtin_shows_read_only_note(qapp):
    panel = _panel(qapp)
    card = panel.card("entry")
    builtin = next(name for name, raw in registry.default_definitions().items()
                   if raw.get("type") not in registry.PRESET_TYPES)
    card.set_value(builtin)
    card.changed.emit(card.value())
    _flush(qapp)

    entry = panel.card("entry")
    assert entry.value() == builtin
    assert _form(entry) is None
    notes = [n.text() for n in entry.findChildren(InlineMessage)]
    assert any("Built-in" in text for text in notes), notes
    assert panel.theme()["containers"][0]["animation"]["entry"] == builtin

    # The read-only note must offer an action that really copies the definition.
    from ui.theme_kit import IconButton
    copy = next(b for b in entry.findChildren(IconButton)
                if b.text() == "Copy into theme")
    copy.click()
    _flush(qapp)
    copied = panel.theme()
    assert copied["animations"][builtin]["type"] == "typewriter"
    assert copied["containers"][0]["animation"]["entry"] == builtin
    entry = panel.card("entry")
    assert _form(entry) is not None
    assert _form(entry).spec.type == "typewriter"


def test_slot_none_clears_and_preserves_transition_shape(qapp):
    panel = _panel(qapp)
    panel.card("transition_in").set_value("none")
    panel.card("transition_in").changed.emit("none")
    animation = panel.theme()["containers"][0]["animation"]
    assert "in" not in animation.get("transition", {})
    assert animation["transition"]["out"] == "morph"
    panel.card("out").set_value("none")
    panel.card("out").changed.emit("none")
    assert "out" not in panel.theme()["containers"][0]["animation"]


def test_container_without_v2_geometry_is_read_only(qapp):
    theme = {"animations": {}, "container": {"animation": {"entry": "gold"}}}
    panel = _panel(qapp, theme)
    assert panel.card("entry") is not None
    assert panel._container() is None


def test_builtin_typewriter_hides_unused_cursor_rows(qapp):
    theme = _theme()
    theme["animations"]["soft"] = {"type": "typewriter", "duration_ms": 500,
                                   "cursor": "none"}
    theme["containers"][0]["animation"]["entry"] = "soft"
    panel = _panel(qapp, theme)
    card = panel.card("entry")
    qapp.processEvents()
    # Read-only built-in: the cursor rows must not sit there labelled and empty.
    assert card.tw_char_row.isHidden()
    assert card.tw_color_row.isHidden()
    assert card.tw_blink_row.isHidden()
    assert card.tw_hide_row.isHidden()

    theme["containers"][0]["animation"]["entry"] = {
        "type": "typewriter", "duration_ms": 500,
        "cursor": {"char": "|", "color": "currentColor",
                   "blink_ms": 500, "hide_after_ms": 600},
    }
    panel.load_theme(theme)
    qapp.processEvents()
    card = panel.card("entry")
    assert not card.tw_char_row.isHidden()
    assert not card.tw_hide_row.isHidden()


def test_property_row_label_clears_the_reset_glyph(qapp):
    from ui.theme_kit import PropertyRow, TextInput
    row = PropertyRow("Duration", TextInput(""), label_width=80)
    row.set_reset_visible_mode("always")
    row.resize(200, 30)
    row.show()
    qapp.processEvents()
    assert row._label.text() == "Duration"
    row.close()


def test_copy_keeps_slot_overrides_and_creates_animations_map(qapp):
    theme = _theme()
    theme.pop("animations")
    theme["containers"][0]["animation"]["entry"] = {
        "use": "fade_up", "duration_ms": 420}
    panel = _panel(qapp, theme)
    entry = panel.card("entry")
    from ui.theme_kit import IconButton
    copy = next(b for b in entry.findChildren(IconButton)
                if b.text() == "Copy into theme")
    copy.click()
    qapp.processEvents()

    copied = panel.theme()
    assert copied["animations"]["fade_up"]["type"] == "fade_up"
    slot = copied["containers"][0]["animation"]["entry"]
    assert slot["use"] == "fade_up"
    assert slot["duration_ms"] == 420


def test_repeated_slot_switches_do_not_accumulate_editors(qapp):
    panel = _panel(qapp)
    entry = panel.card("entry")
    sequence = [
        "fade_up",
        {"type": "typewriter", "duration_ms": 500, "reveal": "char"},
        {"type": "custom", "duration_ms": 500,
         "keyframes": [{"at": 0, "opacity": 0}, {"at": 100, "opacity": 1}]},
        "gold",
        "none",
        {"type": "fade_in", "duration_ms": 400},
    ]
    for value in sequence:
        entry.set_value(value)
        entry.changed.emit(entry.value())
        _flush(qapp)
        entry = panel.card("entry")
        assert len(entry.findChildren(ParamForm)) <= 1
        assert len(entry.findChildren(Timeline)) <= 1
        assert len([f for f in entry.findChildren(ParamForm)
                    if f.isVisible()]) <= 1


def test_motion_controls_edit_theme_level_settings(qapp):
    theme = _theme()
    theme["motion"] = {
        "in_out": "sequential", "transition": "overlap",
        "sustain_when_cloaked": "pause", "deck_steps": "instant",
    }
    panel = _panel(qapp, theme)
    assert panel.motion_control("deck_steps").value() == "instant"
    assert panel.motion_control("transition").value() == "overlap"
    assert panel.motion_offset_field().value() == 200
    assert not panel._motion_note.isHidden()
    note = panel._motion_note.text()
    assert "200 ms" in note
    assert "incoming starts" in note
    assert "not supported" not in note

    panel.motion_offset_field().set_value(350, emit=True)
    assert panel.theme()["motion"]["overlap_in_offset_ms"] == 350
    assert "350 ms" in panel._motion_note.text()

    panel.motion_control("deck_steps").set_value("out_in", emit=True)
    panel.motion_control("transition").set_value("sequential", emit=True)
    panel.motion_control("sustain_when_cloaked").set_value("run", emit=True)

    motion = panel.theme()["motion"]
    assert motion["deck_steps"] == "out_in"
    assert motion["transition"] == "sequential"
    assert motion["sustain_when_cloaked"] == "run"
    assert motion["overlap_in_offset_ms"] == 350
    assert panel._motion_note.isHidden()


def test_motion_controls_show_defaults_when_theme_has_none(qapp):
    theme = _theme()
    theme.pop("motion", None)
    panel = _panel(qapp, theme)
    assert panel.motion_control("in_out").value() == "sequential"
    assert panel.motion_control("deck_steps").value() == "out_in"
    assert panel.motion_offset_field().value() == 200
    panel.motion_control("deck_steps").set_value("instant", emit=True)
    assert panel.theme()["motion"]["deck_steps"] == "instant"

"""Tests for the pure display motion state machine."""

import pytest

from core.constants import OVERLAP_IN_OFFSET_MS
from core.motion_state import (
    DEFAULT_MOTION, MotionSettings, MotionState, State,
)


def _shown(kind="scripture"):
    machine = MotionState()
    machine.push(kind)
    machine.phase_finished()
    assert machine.state is State.SHOWN
    return machine


def test_starts_empty():
    machine = MotionState()
    assert machine.state is State.EMPTY
    assert machine.sustain_active is False


def test_first_push_enters_then_shows():
    machine = MotionState()
    assert machine.push() == ({"action": "entry"},)
    assert machine.state is State.ENTERING
    assert machine.phase_finished() == (
        {"action": "sustain", "on": True},)
    assert machine.state is State.SHOWN


def test_scripture_to_scripture_plays_transitions():
    machine = _shown("scripture")
    assert machine.push("scripture") == (
        {"action": "transition_out"}, {"action": "transition_in"})
    assert machine.state is State.TRANSITIONING
    machine.phase_finished()
    assert machine.state is State.SHOWN


def test_scripture_to_scripture_ignores_the_theme_change():
    # Different theme, same kind: the pairing rule is kind-only.
    machine = _shown("scripture")
    assert machine.push("scripture") == (
        {"action": "transition_out"}, {"action": "transition_in"})


def test_scripture_to_freeform_plays_out_then_in():
    machine = _shown("scripture")
    assert machine.push("freeform") == ({"action": "out"}, {"action": "in"})


def test_freeform_to_scripture_plays_out_then_in():
    machine = _shown("freeform")
    assert machine.push("scripture") == ({"action": "out"}, {"action": "in"})


def test_freeform_to_freeform_plays_out_then_in():
    machine = _shown("freeform")
    assert machine.push("freeform") == ({"action": "out"}, {"action": "in"})
    assert machine.push("freeform") == ({"action": "out"}, {"action": "in"})


def test_unlabelled_content_plays_out_then_in():
    machine = _shown("other")
    assert machine.push("scripture") == ({"action": "out"}, {"action": "in"})
    assert machine.push("other") == ({"action": "out"}, {"action": "in"})


def test_step_uses_the_same_pairing_rule():
    machine = _shown("freeform")
    assert machine.step("freeform") == ({"action": "out"}, {"action": "in"})
    scripture = _shown("scripture")
    assert scripture.step("scripture") == (
        {"action": "transition_out"}, {"action": "transition_in"})


def test_incoming_theme_supplies_the_ordering():
    machine = _shown("scripture")
    machine.apply_theme({"motion": {"transition": "overlap"}})
    assert machine.push("scripture") == (
        {"action": "pair", "first": "transition_out",
         "second": "transition_in", "order": "overlap",
         "offset_ms": OVERLAP_IN_OFFSET_MS},)
    machine = _shown("freeform")
    machine.apply_theme({"motion": {"in_out": "overlap"}})
    assert machine.push("freeform") == (
        {"action": "pair", "first": "out", "second": "in",
         "order": "overlap", "offset_ms": OVERLAP_IN_OFFSET_MS},)


def test_overlap_offset_is_per_theme_and_clamped():
    machine = _shown("scripture")
    machine.apply_theme({"motion": {"transition": "overlap",
                                    "overlap_in_offset_ms": 420}})
    assert machine.push("scripture") == (
        {"action": "pair", "first": "transition_out",
         "second": "transition_in", "order": "overlap",
         "offset_ms": 420},)

    machine = _shown("freeform")
    machine.apply_theme({"motion": {"in_out": "overlap",
                                    "overlap_in_offset_ms": 9000}})
    assert machine.push("freeform")[0]["offset_ms"] == 2000

    machine = _shown("freeform")
    machine.apply_theme({"motion": {"in_out": "overlap",
                                    "overlap_in_offset_ms": -40}})
    assert machine.push("freeform")[0]["offset_ms"] == 0

    machine = _shown("freeform")
    machine.apply_theme({"motion": {"in_out": "overlap",
                                    "overlap_in_offset_ms": "soon"}})
    assert machine.push("freeform")[0]["offset_ms"] == OVERLAP_IN_OFFSET_MS


def test_push_while_out_replays_entry_only():
    machine = _shown("scripture")
    machine.out()
    assert machine.push("scripture") == ({"action": "in"},)
    assert machine.state is State.ENTERING


def test_out_from_shown_plays_exit():
    machine = _shown()
    assert machine.out() == ({"action": "out"},)
    assert machine.state is State.OUT
    assert machine.sustain_active is False


def test_out_twice_does_not_stack():
    machine = _shown()
    machine.out()
    assert machine.out() == ()
    assert machine.state is State.OUT


def test_out_cancels_phase_in_progress():
    machine = MotionState()
    machine.push("scripture")
    assert machine.out() == ({"action": "out"},)
    assert machine.state is State.OUT


def test_in_replays_entry_from_out():
    machine = _shown()
    machine.out()
    assert machine.enter() == ({"action": "in"},)
    assert machine.state is State.ENTERING
    machine.phase_finished()
    assert machine.state is State.SHOWN


def test_in_is_ignored_when_shown_or_empty():
    assert MotionState().enter() == ()
    machine = _shown()
    assert machine.enter() == ()
    assert machine.state is State.SHOWN


def test_cloak_then_uncloak_restores_shown():
    machine = _shown()
    assert machine.cloak() == ({"action": "cloak"},)
    assert machine.state is State.CLOAKED
    assert machine.covered is State.SHOWN
    assert machine.uncloak() == ({"action": "uncloak", "reveal": True},)
    assert machine.state is State.SHOWN


def test_out_then_cloak_then_uncloak_stays_out():
    machine = _shown()
    machine.out()
    machine.cloak()
    assert machine.covered is State.OUT
    assert machine.uncloak() == ({"action": "uncloak", "reveal": False},)
    assert machine.state is State.OUT
    # Still Out: In is the only thing that can bring content back.
    assert machine.enter() == ({"action": "in"},)


def test_in_while_cloaked_is_ignored():
    machine = _shown()
    machine.cloak()
    assert machine.enter() == ()
    assert machine.state is State.CLOAKED


def test_cloak_mid_transition_restores_content():
    machine = _shown()
    machine.push()
    machine.cloak()
    assert machine.covered is State.SHOWN
    machine.uncloak()
    assert machine.state is State.SHOWN


def test_cloak_from_empty_restores_empty():
    machine = MotionState()
    machine.cloak()
    assert machine.covered is State.EMPTY
    assert machine.uncloak() == ({"action": "uncloak", "reveal": False},)
    assert machine.state is State.EMPTY


def test_push_while_cloaked_stages_content_for_reveal():
    machine = _shown()
    machine.cloak()
    assert machine.push("scripture") == ()
    assert machine.state is State.CLOAKED
    assert machine.covered is State.SHOWN
    assert machine.kind == "scripture"
    machine.uncloak()
    assert machine.state is State.SHOWN


def test_clear_forgets_content():
    machine = _shown()
    assert machine.clear() == ({"action": "clear"},)
    assert machine.state is State.EMPTY
    assert machine.has_content is False
    assert machine.covered is State.EMPTY


def test_sustain_pauses_while_cloaked_by_default():
    machine = _shown()
    machine.cloak()
    assert machine.sustain_active is False


def test_sustain_can_run_behind_the_cloak():
    machine = MotionState(MotionSettings(sustain_when_cloaked="run"))
    machine.push("scripture")
    machine.phase_finished()
    machine.cloak()
    assert machine.sustain_active is True


def test_overlap_transition_is_one_action():
    machine = MotionState(MotionSettings(transition="overlap"))
    machine.push("scripture")
    machine.phase_finished()
    assert machine.push("scripture") == (
        {"action": "pair", "first": "transition_out",
         "second": "transition_in", "order": "overlap",
         "offset_ms": OVERLAP_IN_OFFSET_MS},)


# ── overlap sequencing ──────────────────────────────────────────────────

PAIRINGS = (
    ("scripture", "scripture", "transition_out", "transition_in"),
    ("scripture", "freeform", "out", "in"),
    ("freeform", "scripture", "out", "in"),
    ("freeform", "freeform", "out", "in"),
    ("scripture", "other", "out", "in"),
    ("other", "scripture", "out", "in"),
)


@pytest.mark.parametrize("old,new,first,second", PAIRINGS)
@pytest.mark.parametrize("mode", ["sequential", "overlap"])
def test_every_pairing_in_both_modes(old, new, first, second, mode):
    machine = MotionState(MotionSettings(in_out=mode, transition=mode))
    machine.push(old)
    machine.phase_finished()
    actions = machine.push(new)
    assert machine.state is State.TRANSITIONING
    if mode == "sequential":
        assert actions == ({"action": first}, {"action": second})
    else:
        assert actions == (
            {"action": "pair", "first": first, "second": second,
             "order": "overlap", "offset_ms": OVERLAP_IN_OFFSET_MS},)


def test_overlap_offset_is_a_positive_platform_constant():
    # The renderer reads the same value as RC_ANIM_DEFAULTS.overlap_in_offset_ms.
    assert OVERLAP_IN_OFFSET_MS > 0


def test_interrupted_overlap_returns_a_fresh_pair():
    """A push during an overlap replaces it with another overlap pair."""
    machine = MotionState(MotionSettings(transition="overlap"))
    machine.push("scripture")
    machine.phase_finished()
    first = machine.push("scripture")
    second = machine.push("scripture")
    assert second == first
    assert machine.state is State.TRANSITIONING
    machine.phase_finished()
    assert machine.state is State.SHOWN


@pytest.mark.parametrize("settings,old,new", [
    (MotionSettings(transition="overlap"), "scripture", "scripture"),
    (MotionSettings(in_out="overlap"), "freeform", "freeform"),
])
def test_cloak_mid_overlap_restores_content(settings, old, new):
    machine = MotionState(settings)
    machine.push(old)
    machine.phase_finished()
    machine.push(new)
    assert machine.state is State.TRANSITIONING
    assert machine.cloak() == ({"action": "cloak"},)
    assert machine.covered is State.SHOWN
    # In stays meaningless while cloaked, even mid-overlap.
    assert machine.enter() == ()
    assert machine.uncloak() == ({"action": "uncloak", "reveal": True},)
    assert machine.state is State.SHOWN


@pytest.mark.parametrize("settings,new", [
    (MotionSettings(transition="overlap"), "scripture"),
    (MotionSettings(in_out="overlap"), "freeform"),
])
def test_out_mid_overlap_holds_the_exit(settings, new):
    machine = MotionState(settings)
    machine.push(new)
    machine.phase_finished()
    machine.push(new)
    assert machine.state is State.TRANSITIONING
    assert machine.out() == ({"action": "out"},)
    assert machine.state is State.OUT
    # Out twice must not stack while an overlap was interrupted.
    assert machine.out() == ()


def test_settings_from_theme_ignores_bad_values():
    settings = MotionSettings.from_theme(
        {"motion": {"in_out": "sideways", "transition": "overlap"}})
    assert settings.in_out == "sequential"
    assert settings.transition == "overlap"
    assert settings.sustain_when_cloaked == "pause"
    assert MotionSettings.from_theme({}).as_dict() == DEFAULT_MOTION
    assert MotionSettings.from_theme(None).as_dict() == DEFAULT_MOTION


def test_toggle_target_follows_state():
    machine = _shown()
    assert machine.toggle_target == "out"
    machine.out()
    assert machine.toggle_target == "in"


# ── schema integration ──────────────────────────────────────────────────

def _theme(**extra):
    raw = {
        "schema_version": 2,
        "name": "motion_test",
        "kind": "scripture",
        "containers": [{"id": "main"}],
    }
    raw.update(extra)
    from core.theme_schema import normalize_theme
    return normalize_theme(raw, kind="scripture", name="motion_test")


def test_schema_defaults_motion_to_todays_behavior():
    theme, report = _theme()
    assert not report.errors
    assert theme["motion"] == DEFAULT_MOTION


def test_schema_keeps_overlap_for_round_trip():
    theme, report = _theme(motion={"in_out": "overlap",
                                  "transition": "overlap",
                                  "sustain_when_cloaked": "run"})
    assert not report.errors
    assert theme["motion"] == {"in_out": "overlap",
                               "transition": "overlap",
                               "overlap_in_offset_ms": OVERLAP_IN_OFFSET_MS,
                               "sustain_when_cloaked": "run",
                               "deck_steps": "out_in"}
    # Overlap is implemented now, so it must not warn on the way through.
    assert not any("overlap" in w for w in report.warnings)


def test_schema_rejects_unknown_motion_values():
    theme, report = _theme(motion={"in_out": "sideways"})
    assert theme["motion"]["in_out"] == "sequential"
    assert any("motion.in_out" in w for w in report.warnings)


def test_schema_clamps_overlap_offset():
    theme, report = _theme(motion={"overlap_in_offset_ms": 9000})
    assert theme["motion"]["overlap_in_offset_ms"] == 2000
    assert any("motion.overlap_in_offset_ms" in w for w in report.warnings)

    theme, report = _theme(motion={"overlap_in_offset_ms": 0})
    assert theme["motion"]["overlap_in_offset_ms"] == 0
    assert not report.errors


def test_schema_deck_steps_defaults_and_round_trips():
    theme, report = _theme()
    assert not report.errors
    assert theme["motion"]["deck_steps"] == "out_in"

    theme, report = _theme(motion={"deck_steps": "instant"})
    assert theme["motion"]["deck_steps"] == "instant"

    theme, report = _theme(motion={"deck_steps": "instantish"})
    assert theme["motion"]["deck_steps"] == "out_in"
    assert any("motion.deck_steps" in w for w in report.warnings)


def test_schema_accepts_sustain_slot():
    theme, report = _theme(containers=[{
        "id": "main",
        "animation": {"entry": "fade_in", "sustain": "fade_up"},
    }])
    assert not report.errors
    animation = theme["containers"][0]["animation"]
    assert animation["sustain"] == {"use": "fade_up"}
    assert "fade_up" in theme["animations"]


def test_schema_sustain_resolves_library_reference():
    theme, report = _theme(
        animations={"pulse": {"type": "custom", "duration_ms": 900,
                              "keyframes": [{"at": 0, "opacity": 1},
                                            {"at": 100, "opacity": 0.8}]}},
        containers=[{"id": "main",
                     "animation": {"sustain": {"use": "pulse"}}}],
    )
    assert not report.errors
    assert theme["containers"][0]["animation"]["sustain"] == {"use": "pulse"}
    assert "pulse" in theme["animations"]

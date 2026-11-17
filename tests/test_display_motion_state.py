"""DisplayState integration: shared motion state, cloak coverage, reveal."""

from core.display_state import DisplayState
from core.motion_state import State


def _display():
    state = DisplayState()
    shown = {"action": "display", "text": "A", "reference": "1:1",
             "theme_data": {"schema_version": 2}}
    state.publish_live(shown)
    return state


def test_publish_live_pushes_motion():
    state = _display()
    assert state.motion.state is State.SHOWN


def test_cloak_clears_and_uncloak_reveals_payload():
    state = _display()
    revealed = []
    state.revealed.connect(revealed.append)
    state.set_cloaked(True)
    assert state.motion.state is State.CLOAKED
    state.set_cloaked(False)
    assert state.motion.state is State.SHOWN
    assert revealed and revealed[-1]["text"] == "A"


def test_out_then_cloak_then_uncloak_stays_blank():
    state = _display()
    state.motion.out()
    revealed = []
    state.revealed.connect(revealed.append)
    state.set_cloaked(True)
    state.set_cloaked(False)
    assert state.motion.state is State.OUT
    assert revealed == [{}]


def test_publish_clear_forgets_motion():
    state = _display()
    state.publish_clear()
    assert state.motion.state is State.EMPTY
    assert state.motion.has_content is False


def test_push_while_cloaked_does_not_render():
    state = _display()
    state.set_cloaked(True)
    payloads = []
    state.live_changed.connect(payloads.append)
    state.publish_live({"action": "display", "text": "B",
                        "reference": "1:2",
                        "theme_data": {"schema_version": 2}})
    assert payloads == []
    assert state.motion.covered_name == "shown"

"""Pure display motion state machine.

One authoritative table for when a screen plays entry, transition, exit,
sustain, cloak or an instant reveal. It is intentionally free of Qt, the
renderer and the theme schema so the live output path and the Theme Designer
preview can share exactly the same rules.

States
------
``empty``        nothing has been shown (fresh screen, or after clear)
``entering``     entry phase is playing
``shown``        content is visible and idle
``transitioning`` old content is leaving and new content is arriving
``out``          exit has completed; its final keyframe is held
``cloaked``      screen is blank; the covered state is remembered

Commands return renderer actions (plain dicts). They are ordered; renderers
that play out/in themselves simply consume the list in order.

Pairing rule
------------
Every replacement compares the display ``kind`` of the current item with
the incoming one. Scripture replaced by scripture plays the transition
pair; every other pairing (freeform, deck, image, video, unlabelled
``other``) plays OUT then IN. The incoming content's theme supplies the
ordering. Missing phases switch instantly; an exit/entry is never
substituted for a transition, or the reverse.

Settings (theme ``motion`` object)
----------------------------------
``in_out``               ``sequential`` (default) or ``overlap``
``transition``           ``sequential`` (default) or ``overlap``
``overlap_in_offset_ms`` 0 to 2000, default 200; delay before the incoming phase
``sustain_when_cloaked`` ``pause`` (default) or ``run``
``deck_steps``           ``out_in`` (default) or ``instant``

``motion.in_out`` orders the OUT/IN pair for non-scripture pairings;
``motion.transition`` orders the transition pair for scripture pairings.
Overlap plays both phases together: the outgoing phase starts at t=0 and
the incoming phase starts ``overlap_in_offset_ms`` later (200 ms by
default), stacked above the outgoing content. Sequential remains the
default.
``motion.deck_steps`` lets a freeform theme switch instantly when Prev/Next
stays inside one deck; it is executed by the renderer, which sees the deck
ids, not by this state machine.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from core.constants import (
    OVERLAP_IN_OFFSET_MAX_MS,
    OVERLAP_IN_OFFSET_MIN_MS,
    OVERLAP_IN_OFFSET_MS,
)

__all__ = [
    "MotionSettings", "MotionState", "State",
    "DEFAULT_MOTION", "DECK_STEP_VALUES", "IN_OUT_VALUES", "SUSTAIN_VALUES",
    "TRANSITION_VALUES",
]


class State(str, Enum):
    EMPTY = "empty"
    ENTERING = "entering"
    SHOWN = "shown"
    TRANSITIONING = "transitioning"
    OUT = "out"
    CLOAKED = "cloaked"


IN_OUT_VALUES = ("sequential", "overlap")
TRANSITION_VALUES = ("sequential", "overlap")
SUSTAIN_VALUES = ("pause", "run")
DECK_STEP_VALUES = ("out_in", "instant")

DEFAULT_MOTION = {
    "in_out": "sequential",
    "transition": "sequential",
    "overlap_in_offset_ms": OVERLAP_IN_OFFSET_MS,
    "sustain_when_cloaked": "pause",
    "deck_steps": "out_in",
}


@dataclass(frozen=True)
class MotionSettings:
    """The theme settings that change motion ordering and behaviour."""

    in_out: str = "sequential"
    transition: str = "sequential"
    overlap_in_offset_ms: int = OVERLAP_IN_OFFSET_MS
    sustain_when_cloaked: str = "pause"
    deck_steps: str = "out_in"

    @classmethod
    def from_theme(cls, theme: Any) -> "MotionSettings":
        """Read ``theme["motion"]``, ignoring invalid/missing values."""
        raw = theme.get("motion") if isinstance(theme, dict) else None
        if not isinstance(raw, dict):
            return cls()
        return cls(
            in_out=_pick(raw.get("in_out"), IN_OUT_VALUES, "sequential"),
            transition=_pick(raw.get("transition"), TRANSITION_VALUES,
                             "sequential"),
            overlap_in_offset_ms=_offset(raw.get("overlap_in_offset_ms")),
            sustain_when_cloaked=_pick(raw.get("sustain_when_cloaked"),
                                       SUSTAIN_VALUES, "pause"),
            deck_steps=_pick(raw.get("deck_steps"), DECK_STEP_VALUES,
                             "out_in"),
        )

    def as_dict(self) -> dict:
        return {
            "in_out": self.in_out,
            "transition": self.transition,
            "overlap_in_offset_ms": self.overlap_in_offset_ms,
            "sustain_when_cloaked": self.sustain_when_cloaked,
            "deck_steps": self.deck_steps,
        }


def _pick(value: Any, allowed: Iterable[str], default: str) -> str:
    return value if value in allowed else default


def _offset(value: Any) -> int:
    """Clamp a theme's overlap offset into the documented range."""
    if isinstance(value, bool):
        return OVERLAP_IN_OFFSET_MS
    try:
        number = int(value)
    except (TypeError, ValueError):
        return OVERLAP_IN_OFFSET_MS
    return max(OVERLAP_IN_OFFSET_MIN_MS,
               min(OVERLAP_IN_OFFSET_MAX_MS, number))


class MotionState:
    """Pure motion state for one display screen.

    ``covered`` is the state cloak must restore: ``shown``, ``out`` or
    ``empty``. It is what makes *Out -> Cloak -> Uncloak* stay blank.
    """

    def __init__(self, settings: MotionSettings | None = None):
        self.settings = settings or MotionSettings()
        self.state = State.EMPTY
        self.covered = State.EMPTY
        self.kind = "other"
        self._has_content = False

    # ── settings ────────────────────────────────────────────────────────────
    def set_settings(self, settings: MotionSettings) -> None:
        self.settings = settings

    def apply_theme(self, theme: Any) -> None:
        self.settings = MotionSettings.from_theme(theme)

    def copy_from(self, other: "MotionState") -> None:
        """Adopt another screen's state (scope carry, tests)."""
        self.settings = other.settings
        self.state = other.state
        self.covered = other.covered
        self.kind = other.kind
        self._has_content = other._has_content

    # ── queries ─────────────────────────────────────────────────────────────
    @property
    def has_content(self) -> bool:
        return self._has_content

    @property
    def is_cloaked(self) -> bool:
        return self.state is State.CLOAKED

    @property
    def is_out(self) -> bool:
        return self.state is State.OUT

    @property
    def can_enter(self) -> bool:
        """In is meaningful only when content is hidden by an exit."""
        return self.state is State.OUT

    @property
    def toggle_target(self) -> str:
        """What the Out/In toggle should do next: ``"out"`` or ``"in"``.

        Cloaked screens return ``"in"``; the control is disabled there, so
        the value only documents the state.
        """
        return "in" if self.state is State.OUT else "out"

    @property
    def sustain_active(self) -> bool:
        """Whether sustain should currently be running.

        Paused by default while cloaked; the ``run`` setting keeps it alive
        behind the cloak so an uncloak can reveal a mid-sustain frame.
        """
        if self.state is State.SHOWN:
            return True
        return (self.state is State.CLOAKED
                and self.covered is State.SHOWN
                and self.settings.sustain_when_cloaked == "run")

    @property
    def covered_name(self) -> str:
        return self.covered.value

    # ── transitions ─────────────────────────────────────────────────────────
    def _to(self, state: State) -> None:
        self.state = state

    def push(self, kind: str = "other", *,
             has_content: bool = True) -> tuple[dict, ...]:
        """Content of *kind* arrived (new verse/slide, or a re-render).

        Replacing scripture with scripture plays the transition pair; every
        other pairing plays an exit and an entry. Unlabelled content is
        ``"other"`` and therefore always takes the OUT/IN path.

        While cloaked the model advances silently: nothing is rendered and
        the cloak keeps covering content, so uncloak reveals it instantly.
        """
        if has_content:
            self._has_content = True
        kind = kind or "other"
        if self.state is State.CLOAKED:
            if has_content:
                self.covered = State.SHOWN
                self.kind = kind
            return ()
        if not has_content:
            self.kind = kind
            return ()
        previous_kind = self.kind
        self.kind = kind
        if self.state is State.EMPTY:
            self._to(State.ENTERING)
            return ({"action": "entry"},)
        if self.state is State.OUT:
            self._to(State.ENTERING)
            return ({"action": "in"},)
        self._to(State.TRANSITIONING)
        return self._pair_actions(previous_kind, kind)

    def step(self, kind: str = "other") -> tuple[dict, ...]:
        """Prev/Next: same pairing rule as any other replacement."""
        return self.push(kind, has_content=True)

    def _pair_actions(self, previous_kind: str, kind: str) -> tuple[dict, ...]:
        """Transition pair for scripture->scripture, OUT/IN otherwise.

        Ordering comes from the *incoming* content's theme. Overlap is one
        action describing the pair: ``first`` starts at t=0, ``second``
        starts ``offset_ms`` later. The offset is carried in the action so a
        later per-theme setting only replaces the value, not the shape.
        """
        if previous_kind == "scripture" and kind == "scripture":
            first, second, mode = "transition_out", "transition_in", \
                self.settings.transition
        else:
            first, second, mode = "out", "in", self.settings.in_out
        if mode == "overlap":
            return ({"action": "pair", "first": first, "second": second,
                     "order": "overlap",
                     "offset_ms": self.settings.overlap_in_offset_ms},)
        return ({"action": first}, {"action": second})

    def out(self) -> tuple[dict, ...]:
        """Out: cancel whatever is playing and exit what is visible.

        Out while already Out does nothing (it must never restart or stack).
        Out while cloaked does nothing.
        """
        if self.state in (State.CLOAKED, State.OUT, State.EMPTY):
            return ()
        self._to(State.OUT)
        return ({"action": "out"},)

    def enter(self) -> tuple[dict, ...]:
        """In: replay entry from the held exit frame.

        Ignored while cloaked (the operator must uncloak), and ignored when
        content is already visible or the screen is empty.
        """
        if self.state is not State.OUT:
            return ()
        self._to(State.ENTERING)
        return ({"action": "in"},)

    def phase_finished(self) -> tuple[dict, ...]:
        """Renderer reports the current phase (entry/transition/exit) ended."""
        if self.state in (State.ENTERING, State.TRANSITIONING):
            self._to(State.SHOWN)
            return ({"action": "sustain", "on": self.sustain_active},)
        if self.state is State.OUT:
            return ({"action": "sustain", "on": False},)
        return ()

    def cloak(self) -> tuple[dict, ...]:
        """Blank instantly. Remembers whether content was shown or Out."""
        if self.state is State.CLOAKED:
            return ()
        if self.state is State.OUT:
            self.covered = State.OUT
        elif self.state is State.EMPTY:
            self.covered = State.EMPTY
        else:
            # Entering/transitioning content counts as shown: uncloak
            # restores the content, not a half-played phase.
            self.covered = State.SHOWN
        self._to(State.CLOAKED)
        return ({"action": "cloak"},)

    def uncloak(self) -> tuple[dict, ...]:
        """Restore the covered state instantly, with no entry."""
        if self.state is not State.CLOAKED:
            return ()
        restored = self.covered
        self._to(restored)
        reveal = restored is State.SHOWN
        return ({"action": "uncloak", "reveal": reveal},)

    def clear(self) -> tuple[dict, ...]:
        """Existing clear semantics: blank and forget the content.

        Kept separate from :meth:`cloak`: shutdown and router helpers still
        use clear, and clear does not leave a remembered state behind.
        """
        self._has_content = False
        self.kind = "other"
        self.covered = State.EMPTY
        self._to(State.EMPTY)
        return ({"action": "clear"},)

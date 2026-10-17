"""
core/display_state.py

Source of truth for preview/live screen contents, per display scope.

In prioritized mode every display tab shares the singleton scope below, so
preview and live screens are identical across tabs by construction.
In simultaneous mode each display tab owns its own scope and the tabs
evolve independently. Tabs never touch a scope directly: they hold a
DisplayStateHandle for the whole session, and the mode selects which scope
that handle points at — so switching modes re-points the handles instead of
rebuilding every tab's signal graph, and the switch works mid-session.

Flow:
  - A tab gesture builds a display PAYLOAD (via its _build_payload) and calls
    publish_live() / publish_preview(). The payload is what panels render
    (payload["text"], payload["ref"], theme_data, ...).
  - The originating gesture ALSO stores its navigation DATA dict
    (verse fields / slide list+index) so prev/next, clear/recall and theme
    re-render keep working. Data dicts live here too (live_data,
    preview_data) so either tab can continue the sequence.
  - Panels subscribe directly: live_changed.connect(panel.set_live_payload),
    preview_changed.connect(panel.set_preview_payload),
    cleared.connect(panel.clear_live).
  - OBS broadcast stays with the ORIGINATING tab's gesture (no double-send).
  - Once a live payload is published, its theme travels with it. Restore
    paths (notably uncloak) replay the stored themed payload/outputs; they
    never rebuild the theme from whichever tab happens to be active. New
    live gestures replace the stored theme snapshots.

Schedule anchoring (for prev/next schedule-walking):
  - live_sched_uid + live_from_schedule travel with the live state.
"""

from PyQt6.QtCore import QObject, pyqtSignal

import copy
import logging

logger = logging.getLogger(__name__)


class DisplayState(QObject):
    """Shared preview/live payloads + navigation data."""

    live_changed = pyqtSignal(dict)      # full display payload
    preview_changed = pyqtSignal(dict)   # full display payload
    cleared = pyqtSignal()               # live was cleared
    nav_changed = pyqtSignal()           # data/anchor fields changed (no re-render)
    cloak_changed = pyqtSignal(bool)     # invisibility-cloak state changed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.live_payload: dict | None = None
        self.preview_payload: dict | None = None
        self._live_data: dict | None = None
        self.preview_data: dict | None = None
        # Callbacks fired whenever live_data changes. Live data is THE
        # record of what is displayed, so anything derived from it (the
        # prev/next verse queue) belongs here rather than being
        # re-derived at each of the many places that display a verse.
        # That is how a queue ends up bracketing the wrong verse: a new
        # display path is added, forgets to refresh it, and the stale
        # neighbours from the previous verse silently take over.
        self._live_data_hooks: list = []
        # Exact per-output payloads last sent (or staged) for OBS. These are
        # the authoritative theme snapshots for restore paths: output themes
        # live in tab-local namespaces, so only the originating gesture knows
        # the right theme for every output.
        self.live_output_payloads: dict[str, dict] = {}
        self.live_sched_uid: str | None = None
        self.live_from_schedule = False
        self.is_cleared = True
        self.last_cleared_data: dict | None = None
        self.live_muted = False
        # Which output id owns the live payload in this scope: the tab's
        # main output. Restore paths seed and fall back on THIS id, never
        # a hardcoded "1" — a deck push stored under scripture's output 1
        # is exactly how one wayward payload reaches the wrong screen.
        self.seed_output_id: str = "1"
        # Invisibility cloak over OBS output: THE live-screen blank state,
        # shared across tabs (replaces per-tab clear). While on, pushes
        # update the model with zero renders and nothing is broadcast.
        self.cloaked = False

    def set_live_muted(self, muted: bool):
        """Mute operator live renders (cloak support): while muted,
        publish_live advances the model but emits no live_changed, so
        nothing reaches the screens — not even for a frame."""
        self.live_muted = muted

    def set_cloaked(self, on: bool):
        """Cloak is shared live-screen state: every tab's button, gate,
        and push path reads this — never a tab-local flag. Entering
        blanks all operator live views at once (cleared); the mute then
        holds them blank through subsequent pushes."""
        on = bool(on)
        if on == self.cloaked:
            return
        self.cloaked = on
        self.set_live_muted(on)
        self.cloak_changed.emit(on)
        if on:
            self.cleared.emit()
        self.nav_changed.emit()

    def remember_live_output_payloads(self, payloads: dict | None) -> None:
        """Snapshot the exact payload sent (or staged) for every OBS output.

        Called by broadcast paths after they resolve per-output themes, even
        when cloaked: content staged behind the cloak is exactly what uncloak
        must show. Replaces the previous snapshot; a new live gesture owns
        the next snapshot.
        """
        remembered: dict[str, dict] = {}
        for output_id, payload in (payloads or {}).items():
            if isinstance(payload, dict):
                remembered[str(output_id)] = copy.deepcopy(payload)
        self.live_output_payloads = remembered

    def _stored_live_payload_matches(self, payload: object) -> bool:
        """Whether a stored payload still describes the current live data.

        Restore paths must not resurrect deleted/replaced content. Content
        and text identity are checked; the theme itself is deliberately not
        part of the match because preserving it is the point.
        """
        if not isinstance(payload, dict):
            return False
        if payload.get("action") != "display":
            return False
        if not payload.get("theme") or not isinstance(payload.get("theme_data"), dict):
            return False
        if not isinstance(self.live_data, dict):
            return False
        if self.live_data.get("item_type") == "slide":
            return (
                payload.get("content") == "slide"
                and payload.get("text") == self.live_data.get("text")
                and payload.get("deck_id") == self.live_data.get("deck_id")
            )
        return (
            payload.get("content") == "verse"
            and payload.get("text") == self.live_data.get("text")
        )

    def matching_live_output_payload(self, output_id: str | None = None) -> dict | None:
        """Authoritative stored payload for one output, if it is still current.

        Defaults to this scope's owning output (seed_output_id).
        """
        oid = str(output_id or self.seed_output_id)
        payload = self.live_output_payloads.get(oid)
        if self._stored_live_payload_matches(payload):
            return copy.deepcopy(payload)
        if oid == self.seed_output_id and self._stored_live_payload_matches(self.live_payload):
            return copy.deepcopy(self.live_payload)
        return None

    def matching_live_output_payloads(self) -> dict[str, dict]:
        """Authoritative stored payloads for all outputs with current snapshots."""
        matched = {
            output_id: copy.deepcopy(payload)
            for output_id, payload in self.live_output_payloads.items()
            if self._stored_live_payload_matches(payload)
        }
        seed = self.seed_output_id
        if seed not in matched and self._stored_live_payload_matches(self.live_payload):
            matched[seed] = copy.deepcopy(self.live_payload)
        return matched

    @property
    def live_data(self) -> dict | None:
        """The verse/slide dict currently on live (None when cleared)."""
        return self._live_data

    @live_data.setter
    def live_data(self, value: dict | None) -> None:
        if value is self._live_data:
            return
        self._live_data = value
        for hook in list(self._live_data_hooks):
            try:
                hook(value)
            except Exception:
                # A misbehaving observer must never break a display.
                logger.exception("live_data hook failed")

    def add_live_data_hook(self, fn) -> None:
        """Observe every live_data change. Called immediately with the
        current value so late subscribers are not left stale."""
        self._live_data_hooks.append(fn)
        try:
            fn(self._live_data)
        except Exception:
            logger.exception("live_data hook failed")

    def publish_live(self, payload: dict, data: dict | None = None,
                     sched_uid: str | None = None, from_schedule: bool = False,
                     seed_output_id: str | None = None):
        """Set live screen content (renders in ALL tabs' live views).

        seed_output_id: the output that owns this content (the pushing
        tab's main output). Recorded so restore paths look up this
        scope's own output instead of a hardcoded id.
        """
        if seed_output_id:
            self.seed_output_id = str(seed_output_id)
        self.live_payload = dict(payload)
        _note_authority(self)
        if data is not None:
            self.live_data = data
        self.live_sched_uid = sched_uid
        self.live_from_schedule = from_schedule
        self.is_cleared = False
        # Seed the owning output only when nothing stored still matches. In
        # particular, a restore republishes an already-stored payload, and
        # that publish must not wipe the other outputs' snapshots before
        # broadcast.
        if not self.matching_live_output_payloads():
            self.remember_live_output_payloads({self.seed_output_id: payload})
        if not self.live_muted:
            self.live_changed.emit(dict(payload))
        self.nav_changed.emit()

    def publish_preview(self, payload: dict, data: dict | None = None):
        """Set preview screen content (renders in ALL tabs' preview views)."""
        self.preview_payload = dict(payload)
        _note_authority(self)
        if data is not None:
            self.preview_data = data
        self.preview_changed.emit(dict(payload))
        self.nav_changed.emit()

    def publish_clear(self):
        """Clear the live screen everywhere. Stashes current data for recall.

        The schedule anchor is preserved so clear → recall → prev/next
        continues the sequence where it left off.
        """
        if not self.is_cleared and self.live_data is not None:
            self.last_cleared_data = self.live_data
        self.live_payload = None
        self.live_data = None
        self.live_output_payloads = {}
        self.is_cleared = True
        _note_authority(self)
        self.cleared.emit()
        self.nav_changed.emit()

    def anchor_live(self, sched_uid: str | None, from_schedule: bool):
        """Update schedule anchoring without re-rendering."""
        self.live_sched_uid = sched_uid
        self.live_from_schedule = from_schedule
        self.nav_changed.emit()


# The scope whose screen is authoritative: whichever one published last.
# Decides what the shared scope converges on when the mode switches.
_authority: "DisplayState | None" = None


def _note_authority(scope: "DisplayState") -> None:
    global _authority
    _authority = scope


def _carry_into(source: "DisplayState", target: "DisplayState") -> None:
    """Republish the source scope's screen into a (empty) target scope."""
    try:
        if source.live_payload is not None:
            target.publish_live(
                dict(source.live_payload), source.live_data,
                source.live_sched_uid, source.live_from_schedule,
                seed_output_id=source.seed_output_id)
            if source.live_output_payloads:
                target.remember_live_output_payloads(
                    source.live_output_payloads)
        if source.preview_payload is not None:
            target.publish_preview(dict(source.preview_payload),
                                   source.preview_data)
        if source.cloaked:
            target.set_cloaked(True)
    except Exception:
        logger.exception("failed to carry display state across scopes")


def _clear_scope(scope: "DisplayState") -> None:
    """Empty a scope without emitting: used for a scope that stopped being
    authoritative, so nothing stale can be restored from it later."""
    try:
        scope.live_payload = None
        scope.preview_payload = None
        scope.live_data = None
        scope.preview_data = None
        scope.live_output_payloads = {}
        scope.is_cleared = True
        scope.live_sched_uid = None
        scope.live_from_schedule = False
        scope.cloaked = False
        scope.live_muted = False
    except Exception:
        logger.exception("failed to clear display scope")


# Module singleton — THE shared display scope used in prioritized mode.
# Handles bind to it (see DisplayStateHandle); core code that must reach the
# shared scope directly (output_router cloaking) uses this.
display_state = DisplayState()

_scoped_states: dict[str, DisplayState] = {}
_handles: dict[str, "DisplayStateHandle"] = {}


def _scope_for(tab_key: str) -> DisplayState:
    """The DisplayState a tab publishes through for the CURRENT mode."""
    from core.outputs import shared_display_enabled
    if shared_display_enabled():
        return display_state
    if tab_key not in _scoped_states:
        _scoped_states[tab_key] = DisplayState()
    return _scoped_states[tab_key]


class DisplayStateHandle(QObject):
    """A tab's stable stand-in for whichever scope the mode selects.

    Tabs hold this object for the whole session and never rebind it, so
    their signal graphs (views, hooks, gates) are wired exactly once. A
    mode change only re-points this proxy at another scope underneath —
    which is why switching modes no longer needs a restart, and why
    nothing goes stale across the switch.

    Also owns the output-identity rule: publishes and restore lookups use
    this tab's own main output id, so a deck push can never be stored or
    restored under scripture's output.
    """

    live_changed = pyqtSignal(dict)
    preview_changed = pyqtSignal(dict)
    cleared = pyqtSignal()
    nav_changed = pyqtSignal()
    cloak_changed = pyqtSignal(bool)

    def __init__(self, tab_key: str, parent=None):
        super().__init__(parent)
        self._tab_key = tab_key
        self._scope = _scope_for(tab_key)
        self._hooks: list = []
        self._wires: list[tuple] = []
        self._wire()

    # ── scope binding ──────────────────────────────────────────────────────
    @property
    def tab_key(self) -> str:
        return self._tab_key

    @property
    def scope(self) -> DisplayState:
        return self._scope

    def _wire(self):
        s = self._scope
        pairs = (
            (s.live_changed, self.live_changed.emit),
            (s.preview_changed, self.preview_changed.emit),
            (s.cleared, self.cleared.emit),
            (s.nav_changed, self.nav_changed.emit),
            (s.cloak_changed, self.cloak_changed.emit),
        )
        for signal, slot in pairs:
            signal.connect(slot)
            self._wires.append((signal, slot))

    def _unwire(self):
        for signal, slot in self._wires:
            try:
                signal.disconnect(slot)
            except Exception:
                pass
        self._wires.clear()

    def rebind(self, scope: DisplayState, *, carry: bool = True):
        """Point this tab at another scope, optionally carrying the screen.

        Content follows the tab when it leaves the shared scope (each tab
        takes the shared screen with it into its own scope). Returning to
        the shared scope does NOT carry here — convergence is decided once,
        centrally, in follow_output_mode(), from whichever scope actually
        published last, so the result never depends on rebind order.
        """
        if scope is self._scope:
            return
        previous = self._scope
        if (carry and previous is display_state
                and scope.live_payload is None):
            _carry_into(previous, scope)
        self._unwire()
        self._scope = scope
        self._wire()
        for hook in self._hooks:
            try:
                scope.add_live_data_hook(hook)
            except Exception:
                logger.exception("live_data hook failed on rebind")
        if previous is not None:
            self._replay_to_subscribers()

    def _replay_to_subscribers(self):
        s = self._scope
        try:
            if s.preview_payload:
                self.preview_changed.emit(dict(s.preview_payload))
            if s.cloaked or s.live_payload is None:
                self.cleared.emit()
            else:
                self.live_changed.emit(dict(s.live_payload))
            self.cloak_changed.emit(bool(s.cloaked))
            self.nav_changed.emit()
        except Exception:
            logger.exception("failed to replay display state to subscribers")

    # ── delegated state ────────────────────────────────────────────────────
    @property
    def live_payload(self) -> dict | None:
        return self._scope.live_payload

    @live_payload.setter
    def live_payload(self, value: dict | None) -> None:
        self._scope.live_payload = value

    @property
    def preview_payload(self) -> dict | None:
        return self._scope.preview_payload

    @preview_payload.setter
    def preview_payload(self, value: dict | None) -> None:
        self._scope.preview_payload = value

    @property
    def live_data(self) -> dict | None:
        return self._scope.live_data

    @live_data.setter
    def live_data(self, value: dict | None) -> None:
        self._scope.live_data = value

    @property
    def preview_data(self) -> dict | None:
        return self._scope.preview_data

    @preview_data.setter
    def preview_data(self, value: dict | None) -> None:
        self._scope.preview_data = value

    @property
    def live_output_payloads(self) -> dict:
        return self._scope.live_output_payloads

    @property
    def live_sched_uid(self) -> str | None:
        return self._scope.live_sched_uid

    @live_sched_uid.setter
    def live_sched_uid(self, value) -> None:
        self._scope.live_sched_uid = value

    @property
    def live_from_schedule(self) -> bool:
        return self._scope.live_from_schedule

    @live_from_schedule.setter
    def live_from_schedule(self, value) -> None:
        self._scope.live_from_schedule = value

    @property
    def is_cleared(self) -> bool:
        return self._scope.is_cleared

    @is_cleared.setter
    def is_cleared(self, value) -> None:
        self._scope.is_cleared = value

    @property
    def last_cleared_data(self) -> dict | None:
        return self._scope.last_cleared_data

    @last_cleared_data.setter
    def last_cleared_data(self, value) -> None:
        self._scope.last_cleared_data = value

    @property
    def live_muted(self) -> bool:
        return self._scope.live_muted

    @property
    def cloaked(self) -> bool:
        return self._scope.cloaked

    @property
    def seed_output_id(self) -> str:
        """This tab's main output — the id its content is stored under."""
        from core.outputs import main_output_for_tab
        return main_output_for_tab(self._tab_key) or self._scope.seed_output_id

    # ── delegated operations ───────────────────────────────────────────────
    def publish_live(self, payload: dict, data: dict | None = None,
                     sched_uid: str | None = None, from_schedule: bool = False):
        self._scope.publish_live(payload, data, sched_uid, from_schedule,
                                 seed_output_id=self.seed_output_id)

    def publish_preview(self, payload: dict, data: dict | None = None):
        self._scope.publish_preview(payload, data)

    def publish_clear(self):
        self._scope.publish_clear()

    def set_cloaked(self, on: bool):
        self._scope.set_cloaked(on)

    def set_live_muted(self, muted: bool):
        self._scope.set_live_muted(muted)

    def anchor_live(self, sched_uid: str | None, from_schedule: bool):
        self._scope.anchor_live(sched_uid, from_schedule)

    def remember_live_output_payloads(self, payloads: dict | None) -> None:
        self._scope.remember_live_output_payloads(payloads)

    def matching_live_output_payload(self, output_id: str | None = None) -> dict | None:
        return self._scope.matching_live_output_payload(
            output_id or self.seed_output_id)

    def matching_live_output_payloads(self) -> dict[str, dict]:
        return self._scope.matching_live_output_payloads()

    def add_live_data_hook(self, fn) -> None:
        self._hooks.append(fn)
        self._scope.add_live_data_hook(fn)


def display_state_for(tab_key: str) -> DisplayStateHandle:
    """The display-state handle a display tab must publish through and
    render from.

    The handle is created once per tab and never replaced: it points at
    the shared scope in prioritized mode and at the tab's own scope in
    simultaneous mode, and follow_output_mode() re-points it when the
    operator changes the mode mid-session.
    """
    if tab_key not in _handles:
        _handles[tab_key] = DisplayStateHandle(tab_key)
    return _handles[tab_key]


def follow_output_mode() -> bool:
    """Re-point every tab's handle at the scope the current mode selects.

    Called when the operator changes the mode in Settings — the switch
    takes effect immediately, no restart.

    Leaving the shared scope: each tab takes the shared screen with it,
    and the shared scope is emptied so it cannot resurrect stale content
    later. Entering the shared scope: the screen converges on whichever
    scope published LAST (the authoritative one), so the result is the
    same no matter which handle rebinds first.
    """
    moving = [
        (handle, _scope_for(tab_key))
        for tab_key, handle in list(_handles.items())
        if _scope_for(tab_key) is not handle.scope
    ]
    if not moving:
        return False
    entering_shared = all(scope is display_state for _, scope in moving)
    for handle, scope in moving:
        handle.rebind(scope, carry=not entering_shared)
    if entering_shared:
        # Convergence: the last scope that published owns the shared screen.
        if display_state.live_payload is None and _authority is not None \
                and _authority is not display_state:
            _carry_into(_authority, display_state)
    elif display_state is not _authority:
        _clear_scope(display_state)
    return True


def reset_display_states() -> None:
    """Drop every scope and handle (tests / hard resets)."""
    global display_state, _authority
    _authority = None
    for handle in list(_handles.values()):
        handle._unwire()
        handle._hooks.clear()
    _handles.clear()
    _scoped_states.clear()
    display_state = DisplayState()

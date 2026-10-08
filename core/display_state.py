"""
core/display_state.py

Single shared source of truth for preview/live screen contents.

Both workspace tabs (SCRIPTURE, SLIDES) render their own LivePreviewPanel
widgets, but ALL of them reflect this one state — preview and live screens
are identical across tabs by construction, never by syncing.

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

    def matching_live_output_payload(self, output_id: str = "1") -> dict | None:
        """Authoritative stored payload for one output, if it is still current."""
        payload = self.live_output_payloads.get(str(output_id))
        if self._stored_live_payload_matches(payload):
            return copy.deepcopy(payload)
        if str(output_id) == "1" and self._stored_live_payload_matches(self.live_payload):
            return copy.deepcopy(self.live_payload)
        return None

    def matching_live_output_payloads(self) -> dict[str, dict]:
        """Authoritative stored payloads for all outputs with current snapshots."""
        matched = {
            output_id: copy.deepcopy(payload)
            for output_id, payload in self.live_output_payloads.items()
            if self._stored_live_payload_matches(payload)
        }
        if "1" not in matched and self._stored_live_payload_matches(self.live_payload):
            matched["1"] = copy.deepcopy(self.live_payload)
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
                     sched_uid: str | None = None, from_schedule: bool = False):
        """Set live screen content (renders in ALL tabs' live views)."""
        self.live_payload = dict(payload)
        if data is not None:
            self.live_data = data
        self.live_sched_uid = sched_uid
        self.live_from_schedule = from_schedule
        self.is_cleared = False
        # Seed output 1 only when nothing stored still matches. In particular,
        # a restore republishes an already-stored payload, and that publish
        # must not wipe the other outputs' snapshots before broadcast.
        if not self.matching_live_output_payloads():
            self.remember_live_output_payloads({"1": payload})
        if not self.live_muted:
            self.live_changed.emit(dict(payload))
        self.nav_changed.emit()

    def publish_preview(self, payload: dict, data: dict | None = None):
        """Set preview screen content (renders in ALL tabs' preview views)."""
        self.preview_payload = dict(payload)
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
        self.cleared.emit()
        self.nav_changed.emit()

    def anchor_live(self, sched_uid: str | None, from_schedule: bool):
        """Update schedule anchoring without re-rendering."""
        self.live_sched_uid = sched_uid
        self.live_from_schedule = from_schedule
        self.nav_changed.emit()


# Module singleton — THE display state. Tabs must use this.
display_state = DisplayState()

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

Schedule anchoring (for prev/next schedule-walking):
  - live_sched_uid + live_from_schedule travel with the live state.
"""

from PyQt6.QtCore import QObject, pyqtSignal


class DisplayState(QObject):
    """Shared preview/live payloads + navigation data."""

    live_changed = pyqtSignal(dict)      # full display payload
    preview_changed = pyqtSignal(dict)   # full display payload
    cleared = pyqtSignal()               # live was cleared
    nav_changed = pyqtSignal()           # data/anchor fields changed (no re-render)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.live_payload: dict | None = None
        self.preview_payload: dict | None = None
        self.live_data: dict | None = None
        self.preview_data: dict | None = None
        self.live_sched_uid: str | None = None
        self.live_from_schedule = False
        self.is_cleared = True
        self.last_cleared_data: dict | None = None

    def publish_live(self, payload: dict, data: dict | None = None,
                     sched_uid: str | None = None, from_schedule: bool = False):
        """Set live screen content (renders in ALL tabs' live views)."""
        self.live_payload = dict(payload)
        if data is not None:
            self.live_data = data
        self.live_sched_uid = sched_uid
        self.live_from_schedule = from_schedule
        self.is_cleared = False
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

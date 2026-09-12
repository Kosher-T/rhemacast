"""
core/schedule_model.py

Single shared source of truth for the service schedule.

Both workspace tabs (SCRIPTURE, SLIDES) render their own SchedulePanel
widgets, but ALL of them reflect this one model — schedule contents are
identical across tabs by construction, never by syncing.

Row identity: every item carries a "_sched_uid" (stamped on add). Panels must
match rows by uid, never by object identity — Qt's UserRole round-trips dicts
by copy.
"""

import json
import logging
import uuid
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

_SCHEDULES_DIR = Path(__file__).resolve().parent.parent / "data" / "schedules"


class ScheduleModel(QObject):
    """Ordered schedule items + file state. All mutations emit items_changed."""

    items_changed = pyqtSignal()
    file_changed = pyqtSignal()  # current file / modified flag changed

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[dict] = []
        self._modified = False
        self._current_file: str | None = None

    # ── Reads ─────────────────────────────────────────────────────────────

    def get_items(self) -> list[dict]:
        """Return the live item list (shared refs — mutate only via model)."""
        return self._items

    def get_item(self, uid: str) -> dict | None:
        return next((d for d in self._items if d.get("_sched_uid") == uid), None)

    def index_of(self, uid: str) -> int | None:
        for i, d in enumerate(self._items):
            if d.get("_sched_uid") == uid:
                return i
        return None

    @property
    def is_modified(self) -> bool:
        return self._modified

    @property
    def current_file(self) -> str | None:
        return self._current_file

    # ── Mutations ─────────────────────────────────────────────────────────

    @staticmethod
    def _stamp(data: dict) -> dict:
        if "_sched_uid" not in data:
            data["_sched_uid"] = uuid.uuid4().hex
        return data

    def add_item(self, data: dict) -> dict:
        """Append an item. Returns the stored (stamped) dict."""
        self._stamp(data)
        self._items.append(data)
        self._mark_modified()
        self.items_changed.emit()
        return data

    def insert_item(self, index: int, data: dict) -> dict:
        self._stamp(data)
        self._items.insert(max(0, min(index, len(self._items))), data)
        self._mark_modified()
        self.items_changed.emit()
        return data

    def remove_uids(self, uids: list[str]) -> list[dict]:
        """Remove items by uid. Returns removed dicts."""
        uidset = set(uids)
        removed = [d for d in self._items if d.get("_sched_uid") in uidset]
        if removed:
            self._items = [d for d in self._items if d.get("_sched_uid") not in uidset]
            self._mark_modified()
            self.items_changed.emit()
        return removed

    def update_item(self, uid: str, data: dict) -> bool:
        """Replace the item with uid (matched by uid). Returns success."""
        for i, d in enumerate(self._items):
            if d.get("_sched_uid") == uid:
                data["_sched_uid"] = uid
                self._items[i] = data
                self._mark_modified()
                self.items_changed.emit()
                return True
        return False

    def patch_item(self, uid: str, **fields) -> bool:
        """Update fields of the item with uid in place. Returns success."""
        item = self.get_item(uid)
        if item is None:
            return False
        item.update(fields)
        self._mark_modified()
        self.items_changed.emit()
        return True

    def rename_translation_in_model(self, old_display: str, new_display: str) -> int:
        """Rewrite stored refs/translations after a translation rename.

        Single mutation + single items_changed emission so all schedule views
        refresh at once. Returns the number of changed items.
        """
        from core.bible_service import _rewrite_item_translation
        changed = 0
        for item in self._items:
            if isinstance(item, dict) and _rewrite_item_translation(
                    item, old_display, new_display):
                changed += 1
        if changed:
            self._mark_modified()
            self.items_changed.emit()
        return changed

    def set_order(self, uids_in_order: list[str]):
        """Reorder items to match the given uid sequence (drag-drop)."""
        by_uid = {d.get("_sched_uid"): d for d in self._items}
        ordered = [by_uid[u] for u in uids_in_order if u in by_uid]
        # Keep any items missing from the order list at the end (defensive)
        missing = [d for d in self._items if d.get("_sched_uid") not in set(uids_in_order)]
        new_order = ordered + missing
        if [d.get("_sched_uid") for d in new_order] != [d.get("_sched_uid") for d in self._items]:
            self._items = new_order
            self._mark_modified()
        # Emit regardless — views rebuild to match model order exactly
        self.items_changed.emit()

    # ── File state ────────────────────────────────────────────────────────

    def _mark_modified(self):
        if not self._modified:
            self._modified = True
            self.file_changed.emit()

    def get_serializable(self) -> list[dict]:
        return [dict(d) for d in self._items]

    def save(self, file_path: str | None = None) -> str | None:
        """Write JSON schedule file. Returns path on success, None on failure."""
        path = file_path or self._current_file
        if not path:
            return None
        try:
            _SCHEDULES_DIR.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "items": self.get_serializable()},
                          f, indent=2, ensure_ascii=False)
            self._current_file = path
            self._modified = False
            self.file_changed.emit()
            logger.info(f"Schedule saved to: {path}")
            return path
        except Exception as e:
            logger.error(f"Failed to save schedule: {e}")
            return None

    def load(self, file_path: str) -> bool:
        """Replace contents from a JSON schedule file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = data.get("items", []) if isinstance(data, dict) else data
            self._items = [self._stamp(dict(d)) for d in items]
            self._current_file = file_path
            self._modified = False
            self.items_changed.emit()
            self.file_changed.emit()
            logger.info(f"Schedule loaded from: {file_path} ({len(items)} items)")
            return True
        except Exception as e:
            logger.error(f"Failed to load schedule: {e}")
            return False

    def clear(self):
        self._items = []
        self._modified = False
        self._current_file = None
        self.items_changed.emit()
        self.file_changed.emit()

    def list_schedules(self) -> list:
        _SCHEDULES_DIR.mkdir(parents=True, exist_ok=True)
        files = []
        for f in _SCHEDULES_DIR.glob("*.json"):
            try:
                files.append((f.name, str(f), f.stat().st_mtime))
            except OSError:
                continue
        files.sort(key=lambda x: x[2], reverse=True)
        return [(name, path) for name, path, _ in files]


# Module singleton — THE schedule. Tabs must use this, never their own list.
schedule_model = ScheduleModel()

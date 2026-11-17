"""
ui/widgets/theme_designer/theme_watcher.py

Debounced watch of the themes folder for changes made outside the app
(text editor, sync tool, another process).

``QFileSystemWatcher`` is watched at two levels because the platforms differ:
the folder signals added/removed/renamed files, while editing a file's bytes
signals that file only. Events are coalesced into one ``changed`` emission
after ``interval_ms`` (250 ms by default), so a save that touches a temp file
and renames it produces one reload, not four.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QFileSystemWatcher, QObject, QTimer, pyqtSignal

import core.theme_loader as theme_loader

DEFAULT_INTERVAL_MS = 250


class ThemeFolderWatcher(QObject):
    """Watch ``themes/`` (and every theme file in it); emit once per burst.

    Signals
        changed() — files may have been added, edited or deleted; read the
            disk yourself (the watcher never parses theme JSON).
    """

    changed = pyqtSignal()

    def __init__(self, parent=None, root: Optional[Path] = None,
                 interval_ms: int = DEFAULT_INTERVAL_MS):
        super().__init__(parent)
        self._root = Path(root) if root is not None else None
        self._interval = max(0, int(interval_ms))
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_signal)
        self._watcher.fileChanged.connect(self._on_signal)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self._interval)
        self._timer.timeout.connect(self._emit_changed)
        self._started = False

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Begin watching. Safe to call twice."""
        if self._started:
            return
        self._sync_watches()
        self._started = True

    def stop(self) -> None:
        """Stop watching and drop any pending emission."""
        self._timer.stop()
        paths = (self._watcher.directories() + self._watcher.files())
        if paths:
            self._watcher.removePaths(paths)
        self._started = False

    def is_started(self) -> bool:
        return self._started

    @property
    def root(self) -> Path:
        return self._root if self._root is not None else theme_loader.themes_dir()

    # ── internals ────────────────────────────────────────────────────────────

    def _on_signal(self, _path: str = "") -> None:
        # A directory event may mean a new subfolder: refresh the watch set
        # now, then debounce the notification itself.
        self._sync_watches()
        if self._timer.isActive():
            self._timer.stop()
        if self._interval == 0:
            self._emit_changed()
        else:
            self._timer.start()

    def _emit_changed(self) -> None:
        # Editors that save by rename remove the file watch; re-add it before
        # announcing so the next edit is seen too.
        self._sync_watches()
        self.changed.emit()

    @staticmethod
    def _theme_files(root: Path) -> list[Path]:
        """Theme JSON files under ``root``, support folders excluded."""
        return sorted(
            path for path in root.rglob("*.json")
            if not any(part.startswith("_")
                       for part in path.relative_to(root).parts))

    def _sync_watches(self) -> None:
        root = self.root
        desired_dirs: set[str] = set()
        desired_files: set[str] = set()
        if root.exists():
            desired_dirs.add(str(root))
            for child in root.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    desired_dirs.add(str(child))
            for path in self._theme_files(root):
                desired_files.add(str(path))

        current_dirs = set(self._watcher.directories())
        current_files = set(self._watcher.files())
        add_dirs = sorted(desired_dirs - current_dirs)
        add_files = sorted(desired_files - current_files)
        stale = sorted((current_dirs - desired_dirs)
                       | (current_files - desired_files))
        if stale:
            self._watcher.removePaths(stale)
        added = add_dirs + add_files
        if added:
            self._watcher.addPaths(added)

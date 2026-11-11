"""Single-owner document for the Theme Designer.

The tab owns one :class:`ThemeDocument`. The property, workspace and animation
panels are views: they read a snapshot for their controls and request path
edits through this object. No panel owns or emits a whole document, so a stale
panel cannot revert another panel's edit.

Paths are tuples of dict keys and list indices, for example
``("containers", 0, "blocks", "text", "size")``. ``None`` deletes a leaf key.
"""

from __future__ import annotations

import copy
from typing import Any, Iterable, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from core import theme_schema as schema
from ui.widgets.theme_designer import container_geometry as geometry

Path = tuple
_MISSING = object()


class ThemeDocument(QObject):
    """The one mutable theme document.

    Signals
        changed(tuple[path], object) — one or more paths changed; ``source`` is
            the panel that requested it (``None`` for the tab).
        replaced(object) — the whole document was replaced (theme load, JSON
            apply, import); ``source`` is the requester.
    """

    changed = pyqtSignal(object, object)
    replaced = pyqtSignal(object)

    def __init__(self, theme: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self._theme: dict = copy.deepcopy(theme) if isinstance(theme, dict) else {}
        self._revision = 0

    # ── reads ────────────────────────────────────────────────────────────────
    @property
    def revision(self) -> int:
        return self._revision

    def snapshot(self) -> dict:
        """A deep copy safe for a panel to render or the tab to save."""
        return copy.deepcopy(self._theme)

    def get(self, path: Path, default: Any = None) -> Any:
        node: Any = self._theme
        for key in path:
            if isinstance(key, int):
                if not isinstance(node, list) or key >= len(node):
                    return default
                node = node[key]
            else:
                if not isinstance(node, dict):
                    return default
                if key not in node:
                    return default
                node = node[key]
        return node

    def containers(self) -> list[dict]:
        containers = self._theme.get("containers")
        return containers if isinstance(containers, list) else []

    def container(self, container_id: str) -> Optional[dict]:
        for container in self.containers():
            if isinstance(container, dict) and str(
                    container.get("id", "")) == str(container_id):
                return container
        return None

    def container_index(self, container_id: str) -> int:
        for index, container in enumerate(self.containers()):
            if isinstance(container, dict) and str(
                    container.get("id", "")) == str(container_id):
                return index
        return -1

    # ── writes ───────────────────────────────────────────────────────────────
    def set(self, path: Path, value: Any, *, source=None) -> bool:
        """Set or delete one leaf. Returns True when the document changed."""
        return bool(self.set_many([(path, value)], source=source))

    def set_many(self, edits: Iterable[tuple[Path, Any]], *,
                 source=None) -> tuple[tuple, ...]:
        """Apply several path edits and emit once."""
        changed: list[tuple] = []
        for path, value in edits:
            path = tuple(path)
            if not path:
                continue
            if self._set(path, value):
                changed.append(path)
        if changed:
            self._revision += 1
            self.changed.emit(tuple(changed), source)
        return tuple(changed)

    def replace(self, theme: dict, *, source=None) -> None:
        """Replace the whole document (load, import, JSON apply)."""
        self._theme = copy.deepcopy(theme) if isinstance(theme, dict) else {}
        self._revision += 1
        self.replaced.emit(source)

    # ── structural operations ────────────────────────────────────────────────
    def add_container(self, *, source=None) -> Optional[str]:
        containers = self._containers_mutable()
        if len(containers) >= schema.MAX_CONTAINERS:
            return None
        width, height = self._canvas_size()
        container_id = self._unique_id(containers)
        top = max((int(c.get("layer") or 0) for c in containers
                   if isinstance(c, dict)), default=0)
        offset = 8 * (len(containers) - 1)
        containers.append({
            "id": container_id,
            "label": f"Container {len(containers) + 1}",
            "layer": min(100, top + 10),
            "visible": True,
            "position": {"anchor": "center", "x": offset, "y": offset},
            "width": max(12, int(width * 0.55)),
            "height": max(12, int(height * 0.35)),
        })
        self._emit_containers(source)
        return container_id

    def duplicate_container(self, container_id: str, *, source=None
                            ) -> Optional[str]:
        containers = self._containers_mutable()
        if len(containers) >= schema.MAX_CONTAINERS:
            return None
        index = self.container_index(container_id)
        if index < 0:
            return None
        duplicate = copy.deepcopy(containers[index])
        duplicate["id"] = self._unique_id(containers)
        duplicate["label"] = (
            f"{duplicate.get('label') or duplicate['id']} copy")
        top = max((int(c.get("layer") or 0) for c in containers
                   if isinstance(c, dict)), default=0)
        duplicate["layer"] = min(100, top + 10)
        containers.append(duplicate)
        rect = geometry.container_rect(duplicate, self._canvas_size())
        rect["x"] += 24
        rect["y"] += 24
        geometry.apply_rect(duplicate, rect, self._canvas_size())
        self._emit_containers(source)
        return duplicate["id"]

    def delete_container(self, container_id: str, *, source=None
                         ) -> Optional[str]:
        containers = self._containers_mutable()
        if len(containers) <= 1:
            return None
        index = self.container_index(container_id)
        if index < 0:
            return None
        del containers[index]
        remaining = [str(c.get("id", "")) for c in containers
                     if isinstance(c, dict)]
        selected = remaining[min(index, len(remaining) - 1)]
        self._emit_containers(source)
        return selected

    def reorder_containers(self, ids: Iterable[str], *, source=None) -> bool:
        order = [str(value) for value in ids]
        current = [str(c.get("id", "")) for c in self.containers()
                   if isinstance(c, dict)]
        if sorted(order) != sorted(current):
            return False
        count = len(order)
        for index, container_id in enumerate(order):
            container = self.container(container_id)
            if container is None:
                continue
            if count == 1:
                layer = int(container.get("layer") or 0)
            else:
                layer = round((count - 1 - index) * 100 / (count - 1))
            container["layer"] = layer
        self._emit_containers(source)
        return True

    def set_container_rect(self, container_id: str, rect: dict, *,
                          source=None) -> bool:
        container = self.container(container_id)
        if container is None:
            return False
        before = copy.deepcopy(container)
        geometry.apply_rect(container, rect, self._canvas_size())
        if container == before:
            return False
        index = self.container_index(container_id)
        self._revision += 1
        self.changed.emit((("containers", index),), source)
        return True

    # ── internals ────────────────────────────────────────────────────────────
    def _containers_mutable(self) -> list:
        containers = self._theme.get("containers")
        if not isinstance(containers, list):
            containers = []
            self._theme["containers"] = containers
        return containers

    def _canvas_size(self) -> tuple[float, float]:
        canvas = self._theme.get("canvas")
        if not isinstance(canvas, dict):
            canvas = {}
        try:
            width = float(canvas.get("width"))
        except (TypeError, ValueError):
            width = 1920.0
        try:
            height = float(canvas.get("height"))
        except (TypeError, ValueError):
            height = 1080.0
        return max(320.0, width), max(240.0, height)

    @staticmethod
    def _unique_id(containers: list) -> str:
        used = {str(c.get("id", "")) for c in containers
                if isinstance(c, dict)}
        number = len(used) + 1
        while f"container{number}" in used:
            number += 1
        return f"container{number}"

    def _emit_containers(self, source) -> None:
        self._revision += 1
        self.changed.emit((("containers",),), source)

    def _set(self, path: Path, value: Any) -> bool:
        if value is None and self.get(path, _MISSING) is _MISSING:
            # Deleting an absent leaf is a no-op; do not create empty parents.
            return False
        node: Any = self._theme
        for key in path[:-1]:
            if isinstance(key, int):
                if not isinstance(node, list):
                    return False
                while len(node) <= key:
                    node.append({})
                child = node[key]
                if not isinstance(child, (dict, list)):
                    child = {}
                    node[key] = child
                node = child
            else:
                if not isinstance(node, dict):
                    return False
                child = node.get(key)
                if not isinstance(child, (dict, list)):
                    child = {}
                    node[key] = child
                node = child
        leaf = path[-1]
        if isinstance(node, dict):
            if value is None:
                if leaf not in node:
                    return False
                node.pop(leaf)
                return True
            if leaf in node and node[leaf] == value:
                return False
            node[leaf] = copy.deepcopy(value)
            return True
        if isinstance(node, list) and isinstance(leaf, int):
            if leaf < 0:
                return False
            while len(node) <= leaf:
                node.append(None)
            if node[leaf] == value:
                return False
            node[leaf] = copy.deepcopy(value)
            return True
        return False

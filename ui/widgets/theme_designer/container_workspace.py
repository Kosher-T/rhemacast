"""Stage 4 container workspace: canvas, layer strip and exact geometry.

The workspace owns a copy of the raw theme document and emits the whole
document, so unknown keys survive every canvas or field edit. Selection is a
view: the Designer tab owns the selected id and pushes it back here.
"""

from __future__ import annotations

import copy
from typing import Any, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QScrollArea, QVBoxLayout, QWidget,
)

from core import theme_schema as schema
from ui import dialogs, tokens
from ui.theme_kit import (
    ChoiceOption, CompactDropdown, ContainerBox, ContainerCanvas,
    ContainerStrip, NumberField, PropertyRow, SectionLabel, Switch,
)
from ui.widgets.theme_designer import container_geometry as geometry
from ui.widgets.theme_designer.document import ThemeDocument, container_id_from_name

_SIDE_WIDTH = 240


def _canvas_size(theme: dict) -> tuple[float, float]:
    canvas = theme.get("canvas")
    if not isinstance(canvas, dict):
        canvas = {}
    width = canvas.get("width")
    height = canvas.get("height")
    try:
        width = float(width)
    except (TypeError, ValueError):
        width = 1920.0
    try:
        height = float(height)
    except (TypeError, ValueError):
        height = 1080.0
    return max(320.0, width), max(240.0, height)


class ContainerWorkspace(QWidget):
    """Canvas + strip + anchor/length fields for the raw theme document."""

    theme_changed = pyqtSignal(dict)
    preview_changed = pyqtSignal(dict)
    container_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._document: Optional[ThemeDocument] = None
        self._theme: dict = {}
        self._selected_id = ""
        self._syncing = False

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.canvas = ContainerCanvas((1920, 1080), show_readout=True)
        self.canvas.setMinimumWidth(220)
        self.canvas.selected.connect(self._on_selected)
        self.canvas.changed.connect(self._on_canvas_changed)
        self.canvas.preview.connect(self._on_canvas_preview)
        root.addWidget(self.canvas, 1)

        side = QWidget(self)
        side.setFixedWidth(_SIDE_WIDTH)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(4, 4, 4, 4)
        side_layout.setSpacing(6)

        self.strip = ContainerStrip(max_visible_rows=5)
        self.strip.selected.connect(self._on_selected)
        self.strip.add_requested.connect(self.prompt_add_container)
        self.strip.duplicate_requested.connect(self.duplicate_container)
        self.strip.delete_requested.connect(self.delete_container)
        self.strip.visibility_toggled.connect(self._set_visible)
        self.strip.reordered.connect(self._reorder)
        side_layout.addWidget(self.strip, 0)

        self._scroll = QScrollArea(side)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        host = QWidget(self._scroll)
        fields = QVBoxLayout(host)
        fields.setContentsMargins(0, 0, 0, 0)
        fields.setSpacing(4)
        fields.addWidget(SectionLabel("Geometry"))

        self.anchor_field = CompactDropdown(
            [ChoiceOption(value, value.replace("_", " ").title())
             for value in schema.ANCHORS], "center")
        self.anchor_field.changed.connect(
            lambda value: self._write("position.anchor", value))
        self._anchor_row = PropertyRow("Anchor", self.anchor_field,
                                       label_width=62)
        fields.addWidget(self._anchor_row)

        width_total, height_total = self._canvas()

        def _convert(axis: str):
            return lambda value, old, new: schema.convert_length(
                value, old, new,
                self._canvas()[0 if axis == "width" else 1])

        # Bounds come from the schema helpers, never from this widget; the
        # pixel maxima are re-read from the live canvas in `_sync_fields`.
        self.x_field = NumberField(
            0, units=["px", "%"],
            unit_ranges=schema.offset_limits(width_total),
            unit_converter=_convert("width"), label="X offset")
        self.y_field = NumberField(
            0, units=["px", "%"],
            unit_ranges=schema.offset_limits(height_total),
            unit_converter=_convert("height"), label="Y offset")
        self.width_field = NumberField(
            "auto", units=["px", "%"], keywords=("auto",),
            unit_ranges=schema.size_limits(width_total),
            placeholder="auto",
            unit_converter=_convert("width"), label="Width")
        self.height_field = NumberField(
            "auto", units=["px", "%"], keywords=("auto",),
            unit_ranges=schema.size_limits(height_total),
            placeholder="auto",
            unit_converter=_convert("height"), label="Height")
        self.x_field.changed.connect(lambda value: self._write("position.x", value))
        self.y_field.changed.connect(lambda value: self._write("position.y", value))
        self.width_field.changed.connect(lambda value: self._write("width", value))
        self.height_field.changed.connect(lambda value: self._write("height", value))
        self._offset_rows = []
        for label, field in (("X", self.x_field), ("Y", self.y_field),
                             ("Width", self.width_field),
                             ("Height", self.height_field)):
            row = PropertyRow(label, field, label_width=62)
            fields.addWidget(row)
            self._offset_rows.append(row)

        self.layer_field = NumberField(
            0, integer=True, unit_ranges=schema.limits_for("layer"),
            label="Layer")
        self.layer_field.changed.connect(lambda value: self._write("layer", value))
        fields.addWidget(PropertyRow("Layer", self.layer_field, label_width=62))

        self.visible_switch = Switch(True)
        self.visible_switch.changed.connect(self._on_visible_switch)
        fields.addWidget(PropertyRow("Visible", self.visible_switch,
                                     label_width=62))
        fields.addStretch(1)
        self._scroll.setWidget(host)
        side_layout.addWidget(self._scroll, 1)
        root.addWidget(side, 0)

    # ── public API ──────────────────────────────────────────────────────────
    def bind_document(self, document: ThemeDocument,
                      selected_id: str = "") -> None:
        """Share the tab's document; this panel only renders and requests edits."""
        if self._document is document:
            self._refresh_from_document(selected_id)
            return
        if self._document is not None:
            try:
                self._document.changed.disconnect(self._on_document_changed)
                self._document.replaced.disconnect(self._on_document_replaced)
            except (TypeError, RuntimeError):
                pass
        self._document = document
        document.changed.connect(self._on_document_changed)
        document.replaced.connect(self._on_document_replaced)
        self._refresh_from_document(selected_id)

    def load_theme(self, theme: dict, selected_id: str = "") -> None:
        """Standalone load (tests); the tab uses ``bind_document`` instead."""
        if self._document is None:
            self.bind_document(ThemeDocument(theme), selected_id)
            return
        self._syncing = True
        try:
            self._document.replace(
                theme if isinstance(theme, dict) else {}, source=self)
            self._refresh_from_document(selected_id)
        finally:
            self._syncing = False

    def _refresh_from_document(self, selected_id: str = "") -> None:
        self._theme = (self._document.snapshot()
                       if self._document is not None else {})
        ids = self._ids()
        self._selected_id = (selected_id if selected_id in ids else
                             (self._selected_id if self._selected_id in ids
                              else (ids[0] if ids else "")))
        self._sync_all()

    def _on_document_changed(self, _paths, source) -> None:
        if source is self or self._syncing:
            return
        self._refresh_from_document()

    def _on_document_replaced(self, source) -> None:
        if self._syncing:
            return
        self._refresh_from_document()

    def theme(self) -> dict:
        if self._document is not None:
            return self._document.snapshot()
        return copy.deepcopy(self._theme)

    def selected_id(self) -> str:
        return self._selected_id

    def set_selected(self, container_id: str, *, emit: bool = False) -> None:
        self._select(container_id, emit=emit)

    def container_ids(self) -> list[str]:
        return self._ids()

    # ── document access ─────────────────────────────────────────────────────
    def _ids(self) -> list[str]:
        return [str(c.get("id", "")) for c in self._containers()
                if isinstance(c, dict)]

    def _containers(self) -> list[dict]:
        containers = self._theme.get("containers")
        if not isinstance(containers, list):
            containers = []
            self._theme["containers"] = containers
        return containers

    def _selected(self) -> Optional[dict]:
        for container in self._containers():
            if isinstance(container, dict) and \
                    str(container.get("id", "")) == self._selected_id:
                return container
        return None

    def _index(self, container_id: str) -> int:
        for index, container in enumerate(self._containers()):
            if isinstance(container, dict) and \
                    str(container.get("id", "")) == container_id:
                return index
        return -1

    def _unique_id(self) -> str:
        used = set(self._ids())
        number = len(used) + 1
        while f"container{number}" in used:
            number += 1
        return f"container{number}"

    def _emit(self) -> None:
        self.theme_changed.emit(self.theme())

    def _emit_preview(self) -> None:
        # Preview-only geometry lives in the read model until release; the
        # document must not see a drag frame.
        self.preview_changed.emit(copy.deepcopy(self._theme))

    def _canvas(self) -> tuple[float, float]:
        return _canvas_size(self._theme)

    # ── syncing ─────────────────────────────────────────────────────────────
    def _sync_all(self) -> None:
        self._sync_canvas()
        self._sync_fields()
        if self._selected_id:
            self.canvas.set_selected(self._selected_id)
            self.strip.set_selected(self._selected_id)

    def _boxes(self) -> list[ContainerBox]:
        size = self._canvas()
        boxes = []
        for container in self._containers():
            if not isinstance(container, dict):
                continue
            rect = geometry.container_rect(container, size)
            boxes.append(ContainerBox(
                id=str(container.get("id", "")),
                label=str(container.get("label", "")),
                x=float(rect["x"]), y=float(rect["y"]),
                width=float(rect["width"]), height=float(rect["height"]),
                layer=int(container.get("layer") or 0),
                visible=bool(container.get("visible", True)),
                fill=bool(rect.get("fill")),
            ))
        return boxes

    def _sync_canvas(self) -> None:
        width, height = self._canvas()
        canvas_theme = self._theme.get("canvas")
        background = "transparent"
        if isinstance(canvas_theme, dict):
            background = str(canvas_theme.get("background") or "transparent")
        self.canvas.set_canvas_size(width, height)
        self.canvas.set_background(background)
        boxes = self._boxes()
        self.canvas.set_boxes(boxes, self._selected_id)
        ordered = sorted(boxes, key=lambda b: (b.layer, b.id), reverse=True)
        self.strip.set_boxes(ordered, self._selected_id)

    def _sync_fields(self) -> None:
        container = self._selected()
        enabled = container is not None
        self._syncing = True
        try:
            # px limits follow the live canvas; % is always 0–100.
            width_total, height_total = self._canvas()
            self.x_field.set_unit_ranges(schema.offset_limits(width_total))
            self.y_field.set_unit_ranges(schema.offset_limits(height_total))
            self.width_field.set_unit_ranges(schema.size_limits(width_total))
            self.height_field.set_unit_ranges(schema.size_limits(height_total))
            for widget in (self.anchor_field, self.x_field, self.y_field, self.width_field,
                           self.height_field, self.layer_field, self.visible_switch):
                widget.setEnabled(enabled)
            if container is None:
                return
            anchor = geometry._anchor(container)
            fill = anchor == "fill"
            self.anchor_field.set_value(anchor)
            self.x_field.set_value(geometry.offset_value(container, "x"))
            self.y_field.set_value(geometry.offset_value(container, "y"))
            self.width_field.set_value(geometry.size_value(container, "width"))
            self.height_field.set_value(geometry.size_value(container, "height"))
            self.layer_field.set_value(int(container.get("layer") or 0))
            self.visible_switch.set_value(bool(container.get("visible", True)))
            for widget in (self.x_field, self.y_field, self.width_field, self.height_field):
                widget.setEnabled(enabled and not fill)
        finally:
            self._syncing = False

    def _select(self, container_id: str, *, emit: bool) -> None:
        ids = self._ids()
        if container_id not in ids:
            container_id = ids[0] if ids else ""
        if not container_id:
            return
        self._selected_id = container_id
        self.canvas.set_selected(container_id)
        self.strip.set_selected(container_id)
        self._sync_fields()
        if emit:
            self.container_selected.emit(container_id)

    # ── canvas events ───────────────────────────────────────────────────────
    def _on_selected(self, container_id: str) -> None:
        self._select(container_id, emit=True)

    def _apply_canvas(self, container_id: str,
                      rect: dict[str, Any]) -> None:
        for container in self._containers():
            if str(container.get("id", "")) == container_id:
                geometry.apply_rect(container, rect, self._canvas())
                return

    def _on_canvas_preview(self, container_id: str,
                           rect: dict[str, Any]) -> None:
        self._apply_canvas(container_id, rect)
        self._emit_preview()

    def _on_canvas_changed(self, container_id: str,
                           rect: dict[str, Any]) -> None:
        if self._document is not None:
            self._document.set_container_rect(
                container_id, rect, source=self)
            self._theme = self._document.snapshot()
        else:
            self._apply_canvas(container_id, rect)
        self._sync_canvas()
        self._sync_fields()
        self._emit()

    # ── exact fields ────────────────────────────────────────────────────────
    def _write(self, path: str, value: Any) -> None:
        if self._syncing:
            return
        container = self._selected()
        if container is None:
            return
        index = self._index(self._selected_id)
        if self._document is not None and index >= 0:
            if path == "position.anchor":
                self._document.set(
                    ("containers", index, "position", "anchor"), value,
                    source=self)
            elif path in ("position.x", "position.y"):
                self._document.set(
                    ("containers", index, "position", path.split(".")[-1]),
                    value if value not in (None, "") else None, source=self)
            elif path in ("width", "height"):
                self._document.set(
                    ("containers", index, path),
                    "auto" if value in (None, "") else value, source=self)
            elif path == "layer":
                self._document.set(("containers", index, "layer"),
                                   int(value or 0), source=self)
            elif path == "visible":
                self._document.set(("containers", index, "visible"),
                                   bool(value), source=self)
            self._theme = self._document.snapshot()
            self._sync_canvas()
            self._sync_fields()
            self._emit()
            return
        if path == "position.anchor":
            position = container.get("position")
            if not isinstance(position, dict):
                position = {}
            position["anchor"] = value
            container["position"] = position
        elif path in ("position.x", "position.y"):
            position = container.get("position")
            if not isinstance(position, dict):
                position = {}
            key = path.split(".")[-1]
            if value in (None, ""):
                position.pop(key, None)
            else:
                position[key] = value
            container["position"] = position
        elif path in ("width", "height"):
            container[path] = "auto" if value in (None, "") else value
        elif path == "layer":
            container["layer"] = int(value or 0)
        elif path == "visible":
            container["visible"] = bool(value)
        self._sync_canvas()
        self._sync_fields()
        self._emit()

    def _on_visible_switch(self, value: bool) -> None:
        self._write("visible", bool(value))

    # ── structural operations ───────────────────────────────────────────────
    def add_container(self, name: Optional[str] = None) -> None:
        """Append a container. Programmatic: no prompt, no dialog."""
        if self._document is None:
            return
        container_id = self._document.add_container(name, source=self)
        if not container_id:
            return
        self._theme = self._document.snapshot()
        self._selected_id = container_id
        self._sync_all()
        self._emit()
        self.container_selected.emit(container_id)

    def prompt_add_container(self) -> None:
        """The strip's + button: ask for a name, then add one container.

        The name becomes the id, so it is validated here rather than at render
        time; a rejected name keeps the dialog open with the reason showing.
        """
        if self._document is None:
            return
        if len(self._containers()) >= schema.MAX_CONTAINERS:
            return
        name, accepted = dialogs.get_validated_text(
            self, "Add container", "Name",
            validator=self._new_container_reason,
            placeholder="e.g. Lower third")
        if not accepted:
            return
        self.add_container(name)

    def _new_container_reason(self, name: str) -> str:
        """Rejection reason for a new container name, or ``""``."""
        if self._document is None:
            return ""
        container_id = container_id_from_name(name)
        _ok, reason = self._document.validate_container_id(container_id)
        if reason == "That id is already used." and container_id:
            return f"'{container_id}' is already used."
        return reason

    def duplicate_container(self, container_id: str) -> None:
        if self._document is None:
            return
        duplicate_id = self._document.duplicate_container(
            container_id, source=self)
        if not duplicate_id:
            return
        self._theme = self._document.snapshot()
        self._selected_id = duplicate_id
        self._sync_all()
        self._emit()
        self.container_selected.emit(self._selected_id)

    def delete_container(self, container_id: str) -> None:
        if self._document is None:
            return
        selected = self._document.delete_container(container_id, source=self)
        if not selected:
            return
        self._theme = self._document.snapshot()
        self._selected_id = selected
        self._sync_all()
        self._emit()
        self.container_selected.emit(self._selected_id)

    def _set_visible(self, container_id: str, visible: bool) -> None:
        index = self._index(container_id)
        if index < 0:
            return
        if self._document is not None:
            self._document.set(
                ("containers", index, "visible"), bool(visible), source=self)
            self._theme = self._document.snapshot()
        else:
            self._containers()[index]["visible"] = bool(visible)
        self._sync_canvas()
        self._sync_fields()
        self._emit()

    def _reorder(self, ids: list) -> None:
        if self._document is None:
            return
        if not self._document.reorder_containers(ids, source=self):
            return
        self._theme = self._document.snapshot()
        self._sync_canvas()
        self._sync_fields()
        self._emit()

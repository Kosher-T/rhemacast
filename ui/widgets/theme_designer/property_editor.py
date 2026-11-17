"""Schema-driven property editor for the Theme Designer (Stage 2).

The editor is property-agnostic: every row is described by a small spec and
built from ``ui.theme_kit`` widgets. Defaults are never re-declared — the
editor renders a snapshot and lets ``normalize_theme`` judge every value. It
requests path edits through the tab-owned ``ThemeDocument`` and keeps a
read-only copy for its controls, so keys the UI does not manage survive load
and save untouched.

Stage 3 integration points are marked ``STAGE 3``: animation slots, split and
the container canvas geometry editor are not built here.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from core import theme_schema as schema
from core.theme_shared import load_family
from ui import tokens
from ui.theme_kit import (
    BlockTabBar, BorderField, ChipSelect, ChoiceOption, ColorField,
    CompactDropdown, FourSideField, NumberField, PaintField, PropertyRow,
    PropertySection, SegmentedToggle, ShadowField, SplitEditor, Switch,
    TextInput,
)
from ui.widgets.theme_designer.animation_panel import definitions_for
from ui.widgets.theme_designer.document import ThemeDocument

_PX_RE = re.compile(r"^(-?\d+(?:\.\d+)?)\s*px$", re.I)


# ─── helpers ────────────────────────────────────────────────────────────────


def _palette_pairs() -> list[tuple[str, str]]:
    family = load_family("palettes") or {}
    colors = family.get("colors") if isinstance(family, dict) else {}
    if not isinstance(colors, dict):
        return []
    return [(str(k), str(v)) for k, v in colors.items()
            if isinstance(v, str) and not v.startswith("@")]


def _shared_names(family: str) -> list[str]:
    data = load_family(family) or {}
    entries = data.get(family) if isinstance(data, dict) else {}
    return sorted(entries) if isinstance(entries, dict) else []


def _length_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return f"{value:g}px"
    return str(value)


def _length_doc(text: Any) -> Any:
    raw = str(text or "").strip()
    if not raw:
        return None
    match = _PX_RE.match(raw)
    if match:
        number = float(match.group(1))
        return int(number) if number.is_integer() else number
    return raw


def _widget_value(widget: Any) -> Any:
    for name in ("value", "values", "text", "currentText"):
        method = getattr(widget, name, None)
        if callable(method):
            try:
                return method()
            except TypeError:
                continue
    checked = getattr(widget, "isChecked", None)
    return checked() if callable(checked) else None


def _connect(widget: Any, handler) -> None:
    signal = getattr(widget, "changed", None)
    if signal is None:
        signal = getattr(widget, "textChanged", None)
    if signal is not None:
        signal.connect(handler)


def _report_items(report: Any) -> list:
    for name in ("items", "messages", "entries", "warnings", "notes"):
        value = getattr(report, name, None)
        if isinstance(value, (list, tuple)):
            return list(value)
    return []


def _option(value: str) -> ChoiceOption:
    return ChoiceOption(value, str(value).replace("_", " ").title())


# ─── specs ──────────────────────────────────────────────────────────────────

CANVAS_SPECS = [
    {"path": ("width",), "label": "Width", "kind": "int", "step": 10},
    {"path": ("height",), "label": "Height", "kind": "int", "step": 10},
    {"path": ("background",), "label": "Background", "kind": "paint",
     "full": True},
]

CONTAINER_SPECS = [
    {"path": ("id",), "label": "ID", "kind": "text", "read_only": True},
    {"path": ("label",), "label": "Label", "kind": "text"},
    {"kind": "note",
     "text": "Kind is authoring metadata. Rendering uses Visible, not Kind."},
    {"path": ("layer",), "label": "Layer", "kind": "int"},
    {"path": ("visible",), "label": "Visible", "kind": "bool"},
    {"path": ("min_width",), "label": "Min width", "kind": "length",
     "units": ["px", "%"]},
    {"path": ("max_width",), "label": "Max width", "kind": "length",
     "units": ["px", "%"], "nullable": True},
    {"path": ("min_height",), "label": "Min height", "kind": "length",
     "units": ["px", "%"]},
    {"path": ("max_height",), "label": "Max height", "kind": "length",
     "units": ["px", "%"], "nullable": True},
    {"path": ("background",), "label": "Background", "kind": "paint",
     "full": True},
    {"path": ("border",), "label": "Border", "kind": "border", "full": True},
    {"path": ("border_radius",), "label": "Radius", "kind": "length",
     "units": ["px"], "nullable": True},
    {"path": ("box_shadow",), "label": "Shadow", "kind": "shadow",
     "full": True},
    {"path": ("backdrop_filter",), "label": "Backdrop", "kind": "text",
     "full": True},
    {"path": ("opacity",), "label": "Opacity", "kind": "float", "step": 0.05,
     "default": 1.0},
    {"path": ("overflow",), "label": "Overflow", "kind": "enum",
     "options": schema.OVERFLOWS, "chips": True},
]

_COMMON_BLOCK = [
    {"path": ("visible",), "label": "Visible", "kind": "bool"},
    {"path": ("color",), "label": "Color", "kind": "color"},
    {"path": ("font_family",), "label": "Font", "kind": "text"},
    {"path": ("size",), "label": "Size", "kind": "length",
     "units": ["px", "em"]},
    {"path": ("min_size",), "label": "Min size", "kind": "length",
     "units": ["px"]},
    {"path": ("max_size",), "label": "Max size", "kind": "length",
     "units": ["px"]},
    {"path": ("weight",), "label": "Weight", "kind": "int", "step": 100},
    {"path": ("line_height",), "label": "Line height", "kind": "float",
     "step": 0.05},
    {"path": ("letter_spacing",), "label": "Letter space", "kind": "length",
     "units": ["px", "em"]},
    {"path": ("word_spacing",), "label": "Word space", "kind": "length",
     "units": ["px", "em"]},
    {"path": ("text_shadow",), "label": "Shadow", "kind": "shadow_no_shared",
     "full": True},
    {"path": ("text_outline",), "label": "Outline", "kind": "text",
     "full": True},
    {"path": ("text_transform",), "label": "Transform", "kind": "enum",
     "options": schema.TEXT_TRANSFORMS, "chips": True},
    {"path": ("text_align",), "label": "Align", "kind": "enum",
     "options": schema.TEXT_ALIGNS, "chips": True},
    {"path": ("font_style",), "label": "Style", "kind": "enum",
     "options": schema.FONT_STYLES, "chips": True},
    {"path": ("text_decoration",), "label": "Decoration", "kind": "enum",
     "options": schema.TEXT_DECORATIONS},
    {"path": ("opacity",), "label": "Opacity", "kind": "float", "step": 0.05},
    {"path": ("max_lines",), "label": "Max lines", "kind": "int_null"},
    {"path": ("direction",), "label": "Direction", "kind": "enum",
     "options": schema.DIRECTIONS, "chips": True},
    {"path": (), "label": "Margins", "kind": "sides", "base": "margin",
     "template": "margin_{side}", "linked": False, "minimum": -400,
     "maximum": 400, "units": ["px", "em"]},
    {"path": (), "label": "Padding", "kind": "sides", "base": "padding",
     "template": "padding_{side}", "linked": True, "minimum": 0,
     "maximum": 400, "units": ["px"]},
]


def block_specs(block: str) -> list[dict]:
    if block == "body":
        return [
            {"kind": "note",
             "text": "The container Visible switch hides this panel. Body "
                     "visible is preserved but not rendered."},
            {"path": ("valign",), "label": "Align", "kind": "enum",
             "options": schema.VALIGNS, "chips": True},
            {"path": ("gap",), "label": "Gap", "kind": "length",
             "units": ["px"]},
            {"path": (), "label": "Padding", "kind": "sides",
             "base": "padding", "template": "padding_{side}", "linked": True,
             "minimum": 0, "maximum": 400, "units": ["px"]},
        ]
    specs = list(_COMMON_BLOCK)
    if block == "text":
        specs.insert(5, {"path": ("autosize",), "label": "Autosize",
                         "kind": "bool"})
    if block in ("reference", "title"):
        specs.insert(1, {"path": ("position",), "label": "Position",
                         "kind": "enum",
                         "options": schema.REFERENCE_POSITIONS,
                         "chips": True})
    if block == "translation":
        specs = [
            {"path": ("visible",), "label": "Visible", "kind": "bool"},
            {"path": ("position",), "label": "Position", "kind": "enum",
             "options": schema.TRANSLATION_POSITIONS},
            {"path": ("color",), "label": "Color", "kind": "color"},
            {"path": ("margin_left",), "label": "Margin left",
             "kind": "length", "units": ["px", "em"]},
        ] + [s for s in _COMMON_BLOCK
             if s["path"] in (("font_family",), ("size",), ("weight",),
                              ("line_height",), ("letter_spacing",),
                              ("text_transform",), ("font_style",),
                              ("text_align",))]
    if block == "verse_num":
        specs = [
            {"path": ("visible",), "label": "Visible", "kind": "bool"},
            {"path": ("mode",), "label": "Mode", "kind": "enum",
             "options": schema.VERSE_MODES, "chips": True},
            {"kind": "note",
             "text": "Position is not supported by the renderer. The stored "
                     "value is preserved."},
            {"path": ("vertical_align",), "label": "V align", "kind": "enum",
             "options": schema.VERTICAL_ALIGNS},
            {"path": ("margin_right",), "label": "Margin right",
             "kind": "length", "units": ["px", "em"]},
            {"path": ("size",), "label": "Size", "kind": "length",
             "units": ["px", "em"]},
            {"path": ("weight",), "label": "Weight", "kind": "int",
             "step": 100},
            {"path": ("opacity",), "label": "Opacity", "kind": "float",
             "step": 0.05},
            {"path": ("line_height",), "label": "Line height",
             "kind": "float", "step": 0.05},
            {"path": ("color",), "label": "Color", "kind": "color"},
            {"path": ("font_family",), "label": "Font", "kind": "text"},
        ]
    # Block enum rows use the compact dropdown: at 240 px even two chips
    # clip their labels, and these options are words, not short tokens.
    return [{k: v for k, v in spec.items() if k != "chips"}
            for spec in specs]


# ─── editor ─────────────────────────────────────────────────────────────────


class ThemePropertyEditor(QWidget):
    """Edits the raw v2 theme document with schema-aware controls."""

    theme_changed = pyqtSignal(dict)
    #: Request only: the Designer tab owns the actual selected container.
    container_selected = pyqtSignal(str)
    #: Request only: the Animations panel target follows this block.
    block_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._document: Optional[ThemeDocument] = None
        self._doc: dict = {}
        self._kind = schema.SCRIPTURE
        self._container_index = 0
        self._block = "text"
        self._loaded = False
        self._loading = True
        self._palette = _palette_pairs()
        self._borders = _shared_names("borders")
        self._shadows = _shared_names("shadows")

        root = QVBoxLayout(self)
        # 4 px side margins keep the 240 px panel clear of a horizontal
        # scrollbar (the four-side rows need 214 px; the viewport is 210 at
        # 8 px margins).
        root.setContentsMargins(4, 8, 4, 8)
        root.setSpacing(6)
        self._pages = SegmentedToggle(
            [ChoiceOption("canvas", "Canvas"),
             ChoiceOption("container", "Container"),
             ChoiceOption("blocks", "Blocks")], "canvas")
        self._pages.changed.connect(self._on_page)
        root.addWidget(self._pages)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setStyleSheet("QScrollArea, QWidget { background: transparent; }")
        self._host = QWidget(self._scroll)
        self._layout = QVBoxLayout(self._host)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._scroll.setWidget(self._host)
        root.addWidget(self._scroll, 1)

        self._note = QLabel("")
        self._note.setWordWrap(True)
        self._note.setStyleSheet(f"color: {tokens.WARNING}; font-size: 11px;")
        root.addWidget(self._note)

        self._loading = False
        self._rebuild()

    # ── public API ──────────────────────────────────────────────────────────
    def bind_document(self, document: ThemeDocument,
                      selected_id: Optional[str] = None) -> None:
        """Share the tab's document; this panel only renders and requests edits."""
        if self._document is document:
            self._load_snapshot(document.snapshot(), selected_id)
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
        self._load_snapshot(document.snapshot(), selected_id, first=True)

    def load_theme(self, theme: dict, selected_id: Optional[str] = None) -> None:
        """Standalone load (tests); the tab uses ``bind_document`` instead."""
        if self._document is None:
            self.bind_document(ThemeDocument(theme), selected_id)
            return
        self._loading = True
        try:
            self._document.replace(
                theme if isinstance(theme, dict) else {}, source=self)
            self._load_snapshot(self._document.snapshot(), selected_id)
        finally:
            self._loading = False

    def _load_snapshot(self, theme: dict,
                       selected_id: Optional[str] = None,
                       *, first: Optional[bool] = None) -> None:
        """Load a read-model snapshot without resetting the visible page."""
        first = (not self._loaded) if first is None else first
        current = self.container_id()
        self._loading = True
        try:
            self._doc = copy.deepcopy(theme) if isinstance(theme, dict) else {}
            self._kind = str(self._doc.get("kind") or schema.SCRIPTURE)
            ids = self._container_ids()
            wanted = selected_id if selected_id in ids else (
                current if current in ids else (ids[0] if ids else ""))
            self._container_index = ids.index(wanted) if wanted in ids else 0
            allowed = list(schema.BLOCK_IDS.get(self._kind, ()))
            if first or self._block not in allowed:
                self._block = "text" if "text" in allowed else (
                    allowed[0] if allowed else "body")
            self._loaded = True
        finally:
            self._loading = False
        self._rebuild()

    def _on_document_changed(self, _paths, source) -> None:
        if source is self:
            return
        self._load_snapshot(self._document.snapshot())

    def _on_document_replaced(self, source) -> None:
        if self._loading:
            return
        self._load_snapshot(self._document.snapshot())

    def get_theme(self) -> dict:
        if self._document is not None:
            return self._document.snapshot()
        return copy.deepcopy(self._doc)

    def set_field(self, dotted: str, value: Any) -> None:
        """Programmatic edit (tests, presets, Stage 3 hooks)."""
        path = tuple(int(part) if part.isdigit() else part
                     for part in str(dotted).split("."))
        self._write(path, value)
        self._after_edit(path[-1] if path else "")

    def field_paths(self) -> list[str]:
        return [".".join(str(part) for part in path)
                for path in self._current_paths()]

    def container_id(self) -> str:
        containers = self._containers()
        if 0 <= self._container_index < len(containers):
            container = containers[self._container_index]
            if isinstance(container, dict):
                return str(container.get("id", ""))
        return ""

    def set_selected_container(self, container_id: str) -> None:
        """Follow the tab's single selection without emitting it back."""
        for index, container in enumerate(self._containers()):
            if isinstance(container, dict) and \
                    str(container.get("id", "")) == container_id:
                if index == self._container_index:
                    return
                self._container_index = index
                if self._page() in ("container", "blocks"):
                    self._rebuild()
                return

    def selected_block(self) -> str:
        return self._block

    def set_selected_block(self, block: str) -> None:
        """Follow the Animations panel target without emitting it back."""
        allowed = list(schema.BLOCK_IDS.get(self._kind, ()))
        if block not in allowed:
            return
        changed = block != self._block
        self._block = block
        on_blocks = self._page() == "blocks"
        if not on_blocks:
            self._pages.set_value("blocks")
        if changed or not on_blocks:
            self._rebuild()

    # ── document access ─────────────────────────────────────────────────────
    def _container_ids(self) -> list[str]:
        return [str(c.get("id", "")) for c in self._containers()
                if isinstance(c, dict)]

    def _containers(self) -> list:
        containers = self._doc.get("containers")
        if isinstance(containers, list):
            return containers
        if isinstance(containers, dict):
            return list(containers.values())
        return []

    def _container(self) -> dict:
        containers = self._doc.setdefault("containers", [])
        if not isinstance(containers, list):
            containers = []
            self._doc["containers"] = containers
        while len(containers) <= self._container_index:
            containers.append({"id": "main", "blocks": {}})
        if not isinstance(containers[self._container_index], dict):
            containers[self._container_index] = {"id": "main", "blocks": {}}
        return containers[self._container_index]

    def _get(self, path: tuple) -> Any:
        node: Any = self._doc
        for key in path:
            if isinstance(key, int):
                if not isinstance(node, list) or key >= len(node):
                    return None
                node = node[key]
            else:
                if not isinstance(node, dict):
                    return None
                node = node.get(key)
        return node

    def _write(self, path: tuple, value: Any) -> None:
        if not path:
            return
        if self._document is not None:
            self._document.set(tuple(path), value, source=self)
            self._doc = self._document.snapshot()
            return
        if path[0] == "containers" and len(path) >= 2:
            self._container()
        node: Any = self._doc
        for key in path[:-1]:
            if isinstance(key, int):
                if not isinstance(node, list):
                    return
                while len(node) <= key:
                    node.append({})
                node = node[key]
            else:
                if not isinstance(node, dict):
                    return
                child = node.get(key)
                if child is None:
                    child = {}
                    node[key] = child
                elif not isinstance(child, (dict, list)):
                    child = {}
                    node[key] = child
                node = child
        leaf = path[-1]
        if isinstance(node, dict):
            if value is None:
                node.pop(leaf, None)
            else:
                node[leaf] = value

    # ── page building ───────────────────────────────────────────────────────
    def _prefix(self) -> tuple:
        if self._page() == "canvas":
            return ("canvas",)
        if self._page() == "container":
            return ("containers", self._container_index)
        return ("containers", self._container_index, "blocks", self._block)

    def _page(self) -> str:
        return self._pages.value() or "canvas"

    def _on_page(self, _value: str) -> None:
        self._rebuild()

    def _rebuild(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # deleteLater alone leaves the old page parented and visible
                # until the event loop deletes it, so it paints over the new
                # page. Unparent and hide now, delete afterwards.
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        page = self._page()
        if page == "canvas":
            self._add_specs(CANVAS_SPECS, ("canvas",))
            self._add_slide_options()
        elif page == "container":
            self._add_container_picker()
            self._add_specs(CONTAINER_SPECS,
                            ("containers", self._container_index))
        else:
            self._add_block_bar()
            prefix = ("containers", self._container_index, "blocks",
                      self._block)
            self._add_specs(block_specs(self._block), prefix)
            if self._block in schema.SPLIT_BLOCKS:
                self._add_split_editor(prefix)
        self._layout.addStretch(1)
        self._layout.activate()
        self._align_page_rows()
        self._note.setText("")

    def _align_page_rows(self) -> None:
        """Align the page's top-level rows to the widest label."""
        rows = []
        for index in range(self._layout.count()):
            item = self._layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if isinstance(widget, PropertyRow) and not widget._full_width:
                rows.append(widget)
        if not rows:
            return
        width = max(row.required_label_width() for row in rows)
        for row in rows:
            row.set_label_column_width(width)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._align_page_rows()

    def _add_split_editor(self, prefix: tuple) -> None:
        block = self._get(prefix)
        animation = block.get("animation") if isinstance(block, dict) else None
        split = animation.get("split") if isinstance(animation, dict) else None
        library, builtins = definitions_for(self._doc)
        editor = SplitEditor(
            split if isinstance(split, dict) else None,
            library=library, builtins=builtins, palette=self._palette,
            defaults=schema.split_defaults(),
            unit_labels=("First line", "Rest"),
        )
        editor.changed.connect(
            lambda value, p=prefix: self._write_split(p, value))
        section = PropertySection("Split", expanded=isinstance(split, dict))
        section.add_widget(editor)
        self._layout.addWidget(section)

    def _write_split(self, prefix: tuple, value: Any) -> None:
        block = (self._document.get(prefix) if self._document is not None
                 else self._get(prefix))
        if not isinstance(block, dict):
            return
        animation = copy.deepcopy(block.get("animation"))
        if not isinstance(animation, dict):
            animation = {}
        if value is None:
            animation.pop("split", None)
        else:
            current = animation.get("split")
            unknown = {}
            if isinstance(current, dict):
                unknown = {key: item for key, item in current.items()
                           if key not in ("by", "stagger_ms", "first", "rest",
                                          "look")}
            animation["split"] = {**unknown, **dict(value)}
        self._write(prefix + ("animation",), animation or None)
        self._after_edit("split")

    def _add_container_picker(self) -> None:
        containers = self._containers()
        ids = [str(c.get("id", f"container{i}")) if isinstance(c, dict)
               else f"container{i}" for i, c in enumerate(containers)] or ["main"]
        index = min(self._container_index, len(ids) - 1)
        picker = CompactDropdown([ChoiceOption(i, i) for i in ids], ids[index])
        picker.changed.connect(self._on_container_pick)
        self._layout.addWidget(PropertyRow("Container", picker,
                                           label_width=76))

    def _on_container_pick(self, value: str) -> None:
        self.container_selected.emit(str(value))

    def _add_block_bar(self) -> None:
        allowed = list(schema.BLOCK_IDS.get(self._kind, ()))
        if self._kind == schema.FREEFORM and "title" in allowed:
            allowed = ["title" if b == "reference" else b for b in allowed]
        if self._block not in allowed:
            self._block = allowed[0] if allowed else "body"
        bar = BlockTabBar([(b, b.replace("_", " ").title())
                           for b in allowed], self._block)
        bar.selected.connect(self._on_block)
        self._layout.addWidget(bar)

    def _on_block(self, value: str) -> None:
        value = str(value or "")
        if value == self._block:
            return
        self._block = value
        self._rebuild()
        self.block_selected.emit(value)

    def _add_slide_options(self) -> None:
        """Show-title is the only slide switch, so it lives on the Canvas page."""
        if self._kind != schema.FREEFORM:
            return
        slide = self._doc.get("slide")
        current = True
        if isinstance(slide, dict):
            current = bool(slide.get("show_title", True))
        switch = Switch(current)
        switch.changed.connect(self._on_show_title_changed)
        self._show_title_switch = switch
        section = PropertySection("Freeform slide", expanded=True)
        section.add_row(PropertyRow("Show title", switch, label_width=76))
        note = QLabel("When off, the reference line is hidden on slide payloads.")
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color: {tokens.TEXT_MUTED}; font-size: 11px; background: transparent;")
        section.add_widget(note)
        self._layout.addWidget(section)

    def _on_show_title_changed(self, checked: bool) -> None:
        if self._loading:
            return
        if self._document is not None:
            self._document.set(("slide", "show_title"), bool(checked),
                               source=self)
            self._doc = self._document.snapshot()
        else:
            self._write(("slide", "show_title"), bool(checked))
        self._after_edit("show_title")

    def _current_paths(self) -> list[tuple]:
        prefix = self._prefix()
        if self._page() == "canvas":
            specs = CANVAS_SPECS
        elif self._page() == "container":
            specs = CONTAINER_SPECS
        else:
            specs = block_specs(self._block)
        paths: list[tuple] = []
        for spec in specs:
            if spec["kind"] == "note":
                continue
            if spec["kind"] == "sides":
                base = str(spec["base"])
                template = str(spec.get("template", base + "_{side}"))
                paths.append(prefix + (base,))
                paths.extend(prefix + (template.format(side=side),)
                             for side in ("top", "right", "bottom", "left"))
            else:
                paths.append(prefix + tuple(spec["path"]))
        return paths

    def _add_specs(self, specs: list[dict], prefix: tuple) -> None:
        for spec in specs:
            if spec["kind"] == "note":
                note = QLabel(str(spec.get("text", "")))
                note.setWordWrap(True)
                note.setStyleSheet(
                    f"color: {tokens.TEXT_MUTED}; font-size: 11px; "
                    "background: transparent;")
                self._layout.addWidget(note)
                continue
            if spec["kind"] == "sides":
                self._add_sides(spec, prefix)
                continue
            path = prefix + tuple(spec["path"])
            initial = self._get(path)
            if initial is None and spec["kind"] == "float":
                initial = self._float_default(spec)
            widget = self._make(spec, initial)
            if widget is None:
                continue
            chips = isinstance(widget, ChipSelect)
            row = PropertyRow(spec["label"], widget, label_width=76,
                              full_width=spec.get("full", False) or chips)
            self._layout.addWidget(row)
            self._bind(widget, path, spec)
            if path == ("canvas", "background"):
                # The reset glyph restores the schema default through the same
                # document write every other background edit uses.
                row.reset_requested.connect(
                    lambda _checked=False, target=path, control=widget:
                    self._reset_paint(target, control))

    def _add_sides(self, spec: dict, prefix: tuple) -> None:
        base = str(spec["base"])
        template = str(spec.get("template", base + "_{side}"))
        values: dict = {}
        for name, value in ((base, self._get(prefix + (base,))),
                            *((side, self._get(prefix + (template.format(
                                side=side),))) for side in
                              ("top", "right", "bottom", "left"))):
            values[name] = _length_text(value)
        widget = FourSideField(
            values, base_key=base, side_template=template,
            linked=bool(spec.get("linked", True)),
            units=spec.get("units", ["px"]), minimum=spec.get("minimum", 0),
            maximum=spec.get("maximum", 400))
        row = PropertyRow(spec["label"], widget, label_width=76,
                          full_width=True)
        self._layout.addWidget(row)

        def changed(*_args) -> None:
            if self._loading:
                return
            out = widget.value() or {}
            edits = [(prefix + (key,), _length_doc(value))
                     for key, value in out.items()]
            if self._document is not None:
                self._document.set_many(edits, source=self)
                self._doc = self._document.snapshot()
            else:
                for path, value in edits:
                    self._write(path, value)
            self._after_edit(base)

        _connect(widget, changed)

    # ── widgets ─────────────────────────────────────────────────────────────
    def _float_default(self, spec: dict) -> float:
        """Effective default for an absent float, never a false zero.

        The panel edits the raw document, so a missing key used to display 0
        even though the schema renders 1 for opacity and 1.2 for line height.
        """
        explicit = spec.get("default")
        if isinstance(explicit, (int, float)) and not isinstance(explicit, bool):
            return float(explicit)
        key = spec["path"][-1] if spec["path"] else ""
        if self._page() == "blocks":
            value = schema.block_defaults(self._block).get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
        return 0.0

    def _make(self, spec: dict, initial: Any) -> Optional[QWidget]:
        kind = spec["kind"]
        if kind in ("int", "int_null"):
            return NumberField(
                "" if initial is None else initial,
                integer=True, step=spec.get("step", 1),
                nullable=(kind == "int_null"),
                placeholder="Default")
        if kind == "float":
            return NumberField(0.0 if initial is None else initial,
                               step=spec.get("step", 0.1))
        if kind in ("length", "length_null"):
            return NumberField(
                _length_text(initial), units=spec.get("units", ["px", "em"]),
                nullable=True,
                keywords=spec.get("keywords", ()),
                placeholder="Default" if kind == "length_null" else "Inherit")
        if kind == "bool":
            return Switch(bool(initial))
        if kind == "enum":
            options = [_option(value) for value in spec["options"]]
            current = initial if initial in spec["options"] else (
                spec["options"][0] if spec["options"] else "")
            # Chips need room: at 240 px the control column is ~112 px, so
            # only short option sets stay as chips (rendered full-width by
            # _add_specs); everything else uses the compact dropdown.
            short = sum(len(option.label) for option in options) <= 18
            if spec.get("chips") is True and len(options) <= 3 and short:
                return ChipSelect(options, current)
            return CompactDropdown(options, current)
        if kind == "color":
            return ColorField(str(initial or ""), palette=self._palette,
                              keywords=("inherit", "currentColor"))
        if kind == "paint":
            return PaintField(str(initial or ""), palette=self._palette)
        if kind == "border":
            return BorderField(initial or "none",
                               shared_options=self._borders,
                               palette=self._palette)
        if kind in ("shadow", "shadow_no_shared"):
            allow = kind == "shadow"
            return ShadowField(initial or "none",
                               shared_options=self._shadows if allow else (),
                               palette=self._palette, allow_shared=allow,
                               structured=True)
        if kind in ("text", "font"):
            widget = TextInput(str(initial or ""))
            if spec.get("read_only"):
                setter = getattr(widget, "setReadOnly", None)
                if callable(setter):
                    setter(True)
            return widget
        return None

    def _bind(self, widget: QWidget, path: tuple, spec: dict) -> None:
        def changed(*_args) -> None:
            if self._loading:
                return
            self._write(path, self._doc_value(spec, widget))
            self._after_edit(str(path[-1]))

        _connect(widget, changed)

        # Live values (plane/hue/alpha drags, typing, sliders) land in the
        # document immediately so the preview follows the pointer. Committed
        # edits still go through `changed` for validation and the save path.
        live = getattr(widget, "preview", None)
        if live is not None and hasattr(live, "connect"):
            live.connect(lambda *_a: self._preview_value(path, spec, widget))

    def _preview_value(self, path: tuple, spec: dict,
                       widget: QWidget) -> None:
        """Publish an in-flight value without the commit-side work."""
        if self._loading:
            return
        value = self._doc_value(spec, widget)
        if self._document is not None:
            self._document.preview(path, value, source=self)
        else:
            self._write(path, value)

    def _doc_value(self, spec: dict, widget: QWidget) -> Any:
        kind = spec["kind"]
        if kind in ("int", "float"):
            number = widget.numeric_value()
            if number is None:
                return None
            return int(number) if kind == "int" else float(number)
        if kind in ("length", "length_null"):
            return _length_doc(widget.value())
        if kind == "bool":
            return bool(_widget_value(widget))
        if kind in ("border", "shadow", "shadow_no_shared"):
            return widget.value()
        value = _widget_value(widget)
        if value is None or str(value).strip() == "":
            return None
        return str(value)

    def _reset_paint(self, path: tuple, widget: QWidget) -> None:
        """Reset the canvas background to the schema default in one write."""
        default = schema.SAFE_THEME.get("canvas", {}).get("background",
                                                         "transparent")
        setter = getattr(widget, "set_value", None)
        if callable(setter):
            setter(default)
        if self._document is not None:
            self._document.set(path, default, source=self)
            self._doc = self._document.snapshot()
        else:
            self._write(path, default)
        self._after_edit(str(path[-1]))

    # ── validation ──────────────────────────────────────────────────────────
    def _after_edit(self, key: str) -> None:
        if self._document is not None:
            self._doc = self._document.snapshot()
        try:
            _, report = schema.normalize_theme(copy.deepcopy(self._doc),
                                               kind=self._kind)
            items = _report_items(report)
        except Exception:  # never let a report crash the editor
            items = []
        message = ""
        for item in items:
            path = str(getattr(item, "path", ""))
            if key and key in path:
                message = str(getattr(item, "message", item))
                break
        if not message and items:
            message = str(getattr(items[0], "message", items[0]))
        self._note.setText(message)
        self.theme_changed.emit(self.get_theme())

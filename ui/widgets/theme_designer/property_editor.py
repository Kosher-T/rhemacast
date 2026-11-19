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

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from core import theme_schema as schema
from core.theme_shared import load_family
from ui import tokens
from ui.scrollbars import reserve_scrollbar_lane
from ui.theme_kit import (
    AnchorPicker, BackdropField, BlockTabBar, BorderField, ChipSelect,
    ChoiceOption, ColorField, CompactDropdown, FourSideField, IconButton,
    InlineMessage, NumberField, PaintField, ParamGroup, PropertyRow,
    PropertySection, SegmentedToggle, ShadowField, SplitEditor, Switch,
    TextInput, panel_state,
)
from ui.theme_kit.paint_field import paint_mode
from ui.theme_kit.panel_layout import PANEL_PAD
from ui.widgets.theme_designer import container_geometry as geometry
from ui.widgets.theme_designer.animation_panel import definitions_for
from ui.widgets.theme_designer.document import ThemeDocument

_PX_RE = re.compile(r"^(-?\d+(?:\.\d+)?)\s*px$", re.I)

#: Control kinds that sit under their label instead of beside it. At 240 px
#: their content does not fit the shared value column and the label reads as
#: the field's name (docs/PANEL_ORGANIZATION.md §2).
_STACKED_KINDS = frozenset({
    "border", "color", "enum", "font", "paint", "shadow", "shadow_no_shared",
    "text",
})

#: Container size leaves: preferred size and the bounds around it.
_SIZE_LEAVES = ("width", "min_width", "max_width",
                "height", "min_height", "max_height")

#: Tooltip on the preferred-size rows.
_PREFERRED_SIZE_HINT = "Preferred size. Kept between Min and Max."

#: "No override" for optional arguments whose real value may be ``None``.
_UNSET = object()


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


def _size_number(value: float) -> Any:
    """A pixel size as the document stores it: int when whole."""
    number = float(value)
    return int(number) if number.is_integer() else number


def _clean_number(value: Any) -> Any:
    """A position coordinate rounded once, the way the canvas displays it."""
    try:
        number = round(float(value or 0.0), 2)
    except (TypeError, ValueError):
        number = 0.0
    return int(number) if float(number).is_integer() else number


def _distance_parts(text: Any) -> tuple[Any, str]:
    """Split a distance field into the stored number and its unit."""
    raw = str(text or "").strip()
    if raw.endswith("%"):
        number, unit = raw[:-1], "percent"
    elif raw.endswith("px"):
        number, unit = raw[:-2], "px"
    else:
        number, unit = raw, "px"
    try:
        return _clean_number(float(number)), unit
    except (TypeError, ValueError):
        return 0, "px"


def _distance_text(edge: dict) -> str:
    """The distance field's text: the stored number with its unit."""
    suffix = "%" if str(edge.get("unit") or "px") == "percent" else "px"
    value = edge.get("d")
    number = float(value) if isinstance(value, (int, float)) else 0.0
    return f"{number:g}{suffix}"


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

CONTAINER_LAYOUT = [
    {"group": "Identity", "state_key": "identity", "rows": [
        # The selector is also the rename surface: the stored `label` stays in
        # the document (the canvas badge reads it) but is no longer a row of
        # its own — it only repeated the id.
        {"kind": "container_identity"},
        {"kind": "note",
         "text": "Kind is authoring metadata. Rendering uses Visible, not "
                 "Kind."},
    ]},
    {"group": "Visibility", "state_key": "visibility", "rows": [
        {"path": ("visible",), "label": "Visible", "kind": "bool"},
        {"path": ("layer",), "label": "Layer", "kind": "int"},
        {"path": ("opacity",), "label": "Opacity", "kind": "float",
         "step": 0.05, "default": 1.0},
    ]},
    {"group": "Size", "state_key": "size", "rows": [
        {"path": ("width",), "label": "Width", "kind": "length",
         "units": ["px", "%"], "keywords": ("auto",), "placeholder": "auto",
         "state_key": "size.width", "expanded": False,
         "sub": [
             {"path": ("min_width",), "label": "Min", "kind": "length",
              "units": ["px", "%"], "placeholder": "Unset"},
             {"path": ("max_width",), "label": "Max", "kind": "length",
              "units": ["px", "%"], "nullable": True,
              "placeholder": "Unset"},
         ]},
        {"path": ("height",), "label": "Height", "kind": "length",
         "units": ["px", "%"], "keywords": ("auto",), "placeholder": "auto",
         "state_key": "size.height", "expanded": False,
         "sub": [
             {"path": ("min_height",), "label": "Min", "kind": "length",
              "units": ["px", "%"], "placeholder": "Unset"},
             {"path": ("max_height",), "label": "Max", "kind": "length",
              "units": ["px", "%"], "nullable": True,
              "placeholder": "Unset"},
         ]},
        {"path": ("overflow",), "label": "Overflow", "kind": "enum",
         "options": schema.OVERFLOWS, "chips": True},
    ]},
    # Position is a compound control (mode switch, pin grid, pin fields), so it
    # builds its own rows instead of naming one spec per key. Same tier rules:
    # inline controls sit in the shared value column, wide ones span the row.
    {"group": "Position", "state_key": "position", "builder": "position"},
    {"group": "Fill", "state_key": "fill", "rows": [
        {"path": ("container_background",), "label": "Container bg",
         "kind": "paint", "full": True},
    ]},
    {"group": "Border", "state_key": "border", "rows": [
        {"path": ("border",), "label": "Border", "kind": "border",
         "full": True, "state_key": "border.options", "expanded": True,
         "sub": [
             # The border layer always exists: Fill, Pad, Radius and the border
             # shadow change the render even when no outline is stroked, so
             # "Border = none" never disables them (docs/PANEL_ORGANIZATION.md
             # §3, decisions 1 and 2 of round 3).
             {"path": ("background",), "label": "Fill", "kind": "paint",
              "full": True},
             {"path": ("border_padding",), "label": "Pad", "kind": "length",
              "units": ["px"]},
             {"path": ("border_radius",), "label": "Radius", "kind": "length",
              "units": ["px"], "nullable": True},
             {"path": ("border_shadow",), "label": "Border shadow",
              "kind": "shadow", "full": True},
         ]},
    ]},
    {"group": "Effects", "state_key": "effects", "rows": [
        # Exactly one of the two shadows is painted: the container shadow owns
        # a filled rectangle, the border shadow owns the border shape. The
        # hidden row keeps its stored value (docs §3, decision 3).
        {"path": ("box_shadow",), "label": "Shadow", "kind": "shadow",
         "full": True},
        # Stacked: the blur field is wide, and keeping it on its own line
        # leaves the shared label column at the width of the short rows.
        {"path": ("backdrop_filter",), "label": "Backdrop",
         "kind": "backdrop", "full": True},
    ]},
]


def _flatten_layout(layout: list[dict]) -> list[dict]:
    """Every spec in a tiered layout, parents before their subparameters."""
    flat: list[dict] = []
    for entry in layout:
        for spec in entry.get("rows") or []:
            flat.append(spec)
            flat.extend(spec.get("sub") or [])
    return flat


#: Flat view of the container page. Paths, limits and validation read this;
#: only the layout tree above decides where a row sits.
CONTAINER_SPECS = _flatten_layout(CONTAINER_LAYOUT)

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


# ─── identity control ───────────────────────────────────────────────────────


class _InlineIdEdit(TextInput):
    """TextInput that reports Esc instead of leaving it to the focus path."""

    cancelled = pyqtSignal()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class _ContainerIdentity(QWidget):
    """Container selector with an inline rename of the selected id.

    The control owns layout and edit mode only: it never decides whether an id
    is acceptable. The editor validates, then calls :meth:`end_rename` or
    :meth:`show_error`, so the rule lives in ``ThemeDocument``.

    Signals
        picked(str)           — another container was chosen.
        rename_requested(str) — an id was submitted (Enter or focus loss).
    """

    picked = pyqtSignal(str)
    rename_requested = pyqtSignal(str)

    def __init__(self, ids: list[str], current: str, parent=None):
        super().__init__(parent)
        self._editing = False
        self._current = str(current)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.SPACE_4)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(tokens.SPACE_4)
        self.picker = CompactDropdown(
            [ChoiceOption(value, value) for value in ids], current)
        self.picker.changed.connect(self._on_pick)
        row.addWidget(self.picker, 1)
        self._rename = IconButton(
            text="Rename", tooltip="Rename this container id",
            accessible_name="Rename container")
        self._rename.clicked.connect(self._on_rename_clicked)
        row.addWidget(self._rename, 0)
        layout.addLayout(row)

        self._edit = _InlineIdEdit(
            "", placeholder="new-id",
            max_length=schema.CONTAINER_ID_MAX_LENGTH)
        self._edit.changed.connect(self._on_submitted)
        self._edit.cancelled.connect(self.end_rename)
        self._edit.hide()
        layout.addWidget(self._edit)

        self._message = InlineMessage("", "danger")
        self._message.hide()
        layout.addWidget(self._message)

    # ── edit mode ───────────────────────────────────────────────────────────
    def is_editing(self) -> bool:
        return self._editing

    def begin_rename(self) -> None:
        self._editing = True
        self._message.hide()
        self._edit.set_state("neutral")
        self._edit.setText(self._current)
        self._edit.show()
        self._edit.setFocus()
        self._edit.selectAll()
        self._rename.setText("Cancel")

    def end_rename(self) -> None:
        self._editing = False
        self._edit.setText(self._current)
        self._edit.hide()
        self._message.hide()
        self._rename.setText("Rename")

    def show_error(self, reason: str) -> None:
        text = str(reason or "")
        self._message.setText(text)
        self._message.setVisible(bool(text))
        self._edit.set_state("error" if text else "neutral", text)

    # ── signals ─────────────────────────────────────────────────────────────
    def _on_pick(self, value: str) -> None:
        self._current = str(value)
        self.picked.emit(self._current)

    def _on_rename_clicked(self) -> None:
        if self._editing:
            self.end_rename()
        else:
            self.begin_rename()

    def _on_submitted(self, text: str) -> None:
        if not self._editing:
            return
        self.rename_requested.emit(str(text))


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
        #: Path → numeric control, for wiring sibling limits after a rebuild.
        self._field_widgets: dict[tuple, QWidget] = {}

        root = QVBoxLayout(self)
        # PANEL_PAD is the grid origin the tiered page counts from: a Tier-1
        # heading starts at x=8 and its text sits one gutter right of that.
        # Everything below reads ui.theme_kit.panel_layout, never these numbers.
        root.setContentsMargins(PANEL_PAD, 8, PANEL_PAD, 8)
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
        # The lane is reserved and painted here too, not only by the app-wide
        # filter and stylesheet: at 240 px the difference between the token's
        # 8 px bar and the platform default (14 px) is the difference between
        # the block page reflowing and growing a horizontal bar, so the panel
        # has to behave the same in a bare test app as it does at runtime.
        reserve_scrollbar_lane(self._scroll, horizontal=False)
        self._scroll.setStyleSheet(
            "QScrollArea, QWidget { background: transparent; }"
            + tokens.scrollbar_qss())
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
        self._field_widgets = {}
        #: Rows this page built. Alignment uses this registry so nested
        #: subparameters share the page grid without reaching into widgets
        #: another editor owns (SplitEditor). Filtered to the mounted rows.
        self._page_rows: list[PropertyRow] = []
        #: Shadow row → which of the two it is. Exactly one is visible at a
        #: time, following the container background (docs §3, decision 3).
        self._shadow_rows: dict[str, PropertyRow] = {}
        #: The Position section's controls; None when that page is not mounted.
        self._position: Optional[dict] = None
        #: Container size leaves → field and row, for the Min/Max/Width rules.
        self._size_fields: dict[str, NumberField] = {}
        self._size_rows: dict[str, PropertyRow] = {}
        self._identity: Optional[_ContainerIdentity] = None
        page = self._page()
        if page == "canvas":
            self._add_specs(CANVAS_SPECS, ("canvas",))
            self._add_slide_options()
        elif page == "container":
            prefix = ("containers", self._container_index)
            self._add_container_layout(CONTAINER_LAYOUT, prefix)
            self._wire_size_fields(prefix)
            self._refresh_container_shadow_state()
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
        self._refresh_size_markers()
        self._note.setText("")

    def _align_page_rows(self) -> None:
        """Align the page's rows to the widest label, nesting included."""
        rows = []
        for row in self._page_rows:
            try:
                if row.parent() is not None and not row._full_width:
                    rows.append(row)
            except RuntimeError:
                # A rebuilt page deleted the underlying widget.
                continue
        self._page_rows = rows
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

    # ── container page (tiered) ────────────────────────────────────────────
    # Tier 1 headings are PropertySections, Tier 2 parameters are rows and
    # Tier 3 subparameters live in a ParamGroup body. The rules are in
    # docs/PANEL_ORGANIZATION.md; this builder only follows the spec tree.
    def _add_container_layout(self, layout: list[dict], prefix: tuple) -> None:
        for entry in layout:
            key = str(entry.get("state_key") or entry["group"])
            section = PropertySection(
                entry["group"], state_key=key, tiered=True,
                expanded=panel_state.is_open("container", key,
                                             default=entry.get("expanded",
                                                               True)))
            section.expanded_changed.connect(self._on_group_toggled)
            if entry.get("builder") == "position":
                self._add_position_rows(section, prefix)
            for spec in entry.get("rows") or []:
                self._add_container_item(section, spec, prefix)
            self._layout.addWidget(section)

    def _add_container_item(self, section: PropertySection, spec: dict,
                            prefix: tuple) -> None:
        kind = spec["kind"]
        if kind == "note":
            section.add_widget(self._note_label(spec.get("text", "")))
            return
        if kind == "container_identity":
            row = self._identity_row()
            row.set_disclosure(False, reserve=True)
            section.add_row(row)
            return

        path = prefix + tuple(spec["path"])
        initial = self._get(path)
        if initial is None and kind == "float":
            initial = self._float_default(spec)
        widget = self._make(spec, initial)
        if widget is None:
            return
        row = PropertyRow(spec["label"], widget, label_width=76,
                          full_width=self._stacked(spec, widget))
        self._bind(widget, path, spec)
        if isinstance(widget, NumberField):
            self._field_widgets[path] = widget
        leaf = str(spec["path"][-1])
        if leaf in _SIZE_LEAVES:
            self._size_rows[leaf] = row

        sub = spec.get("sub") or []
        if sub:
            state_key = str(spec.get("state_key")
                            or ".".join(str(part) for part in spec["path"]))
            group = ParamGroup(
                row, state_key=state_key,
                expanded=panel_state.is_open(
                    "container", state_key,
                    default=bool(spec.get("expanded", False))))
            group.expanded_changed.connect(self._on_group_toggled)
            for child in sub:
                self._add_container_sub(group, child, prefix)
            section.add_widget(group)
        else:
            # Keep the empty chevron gutter so every parameter label starts
            # at the same x (docs/PANEL_ORGANIZATION.md §2).
            row.set_disclosure(False, reserve=True)
            section.add_row(row)
        if not row._full_width:
            self._page_rows.append(row)
        self._register_container_row(row, leaf)

    def _add_container_sub(self, group: ParamGroup, spec: dict,
                           prefix: tuple) -> None:
        path = prefix + tuple(spec["path"])
        widget = self._make(spec, self._get(path))
        if widget is None:
            return
        row = PropertyRow(spec["label"], widget, label_width=76,
                          full_width=self._stacked(spec, widget))
        group.add_row(row)
        row.set_disclosure(False, reserve=True)
        self._bind(widget, path, spec)
        if isinstance(widget, NumberField):
            self._field_widgets[path] = widget
        leaf = str(spec["path"][-1])
        if leaf in _SIZE_LEAVES:
            self._size_rows[leaf] = row
        if not row._full_width:
            self._page_rows.append(row)
        self._register_container_row(row, leaf)

    @staticmethod
    def _stacked(spec: dict, widget: QWidget) -> bool:
        """Whether the control sits under its label (docs §2, alignment).

        Number fields and small toggles stay in the shared value column;
        dropdowns, colour/paint boxes, text inputs and the compound border,
        shadow and identity controls need the whole width.
        """
        return bool(spec.get("full", False)) or isinstance(widget, ChipSelect) \
            or spec["kind"] in _STACKED_KINDS

    def _identity_row(self) -> PropertyRow:
        ids = self._container_ids() or ["main"]
        index = min(max(self._container_index, 0), len(ids) - 1)
        control = _ContainerIdentity(ids, ids[index])
        control.picked.connect(self._on_container_pick)
        control.rename_requested.connect(self._on_container_rename)
        self._identity = control
        return PropertyRow("Container", control, label_width=76,
                           full_width=True)

    def _note_label(self, text: str) -> QLabel:
        note = QLabel(str(text))
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color: {tokens.TEXT_MUTED}; font-size: 11px; "
            "background: transparent;")
        return note

    def _on_group_toggled(self, state_key: str, expanded: bool) -> None:
        """Remember a heading or disclosure state in the saved UI state."""
        panel_state.remember("container", state_key, expanded)

    def _register_container_row(self, row: PropertyRow, leaf: str) -> None:
        """Remember the rows whose visibility follows another control."""
        role = {"box_shadow": "container", "border_shadow": "border"}.get(leaf)
        if role:
            self._shadow_rows[role] = row

    # ── Position (pin model) ────────────────────────────────────────────────
    # One pin per container: a point of its own box, placed on the canvas. The
    # rules are in docs/PANEL_ORGANIZATION.md §3; the arithmetic lives in
    # container_geometry (Python) and _modelPosition (both JS renderers).
    _POINT_LABELS = (
        ("top_left", "Top left"), ("top", "Top"), ("top_right", "Top right"),
        ("left", "Left"), ("center", "Center"), ("right", "Right"),
        ("bottom_left", "Bottom left"), ("bottom", "Bottom"),
        ("bottom_right", "Bottom right"),
    )
    _EDGE_LABELS = (("top", "Top"), ("bottom", "Bottom"),
                    ("left", "Left"), ("right", "Right"))

    def _add_position_rows(self, section: PropertySection,
                           prefix: tuple) -> None:
        """Mode switch, 3×3 align grid, pin point, pin coordinates.

        The section writes ``position.mode``/``canvas``/``edge`` as one object,
        so every edit — including a mode switch — is a single change. A legacy
        file has no payload: its live rectangle is shown as a top-left pin and
        the first edit freezes that pin into the document.
        """
        mode = SegmentedToggle([ChoiceOption("canvas", "Canvas"),
                                ChoiceOption("edge", "Edge")], "canvas")
        grid = AnchorPicker("top_left", allow_fill=False, dormant=True,
                            accessible_name="Align position")
        point = CompactDropdown(
            [ChoiceOption(value, label) for value, label in self._POINT_LABELS],
            "top_left", variant="field")
        edge = CompactDropdown(
            [ChoiceOption(value, label) for value, label in self._EDGE_LABELS],
            "left", variant="field")
        low, high = schema.POSITION_LIMITS
        x_field = NumberField(0, minimum=low, maximum=high, step=1,
                              label="Pin x")
        y_field = NumberField(0, minimum=low, maximum=high, step=1,
                              label="Pin y")
        distance = NumberField(
            0, minimum=low, maximum=high, step=1, units=["px", "%"],
            unit_ranges=schema.offset_limits(self._canvas_extents()[0]),
            label="Distance")
        # Tie rows (round 5): the target is the canvas or another container;
        # `targetPoint` is the point on the target, `axis` the way d is spent.
        tie = CompactDropdown(
            [ChoiceOption(schema.POSITION_TARGET_DEFAULT, "Canvas")],
            schema.POSITION_TARGET_DEFAULT, variant="field")
        target_point = CompactDropdown(
            [ChoiceOption(value, label) for value, label in self._POINT_LABELS],
            "top_left", variant="field")
        axis = SegmentedToggle([ChoiceOption("x", "X"), ChoiceOption("y", "Y")],
                               "x")
        marker = self._note_label("")

        rows: dict[str, PropertyRow] = {}

        def add(label: str, control: QWidget, *, full: bool = False,
                key: str) -> None:
            row = PropertyRow(label, control, label_width=76,
                              full_width=full)
            # Keep the empty chevron gutter so labels share one left edge.
            row.set_disclosure(False, reserve=True)
            section.add_row(row)
            if not full:
                self._page_rows.append(row)
            rows[key] = row

        add("Mode", mode, full=True, key="mode")
        # A note, not a control: it has no row chrome and never takes width
        # from the fields (docs/PANEL_ORGANIZATION.md §2).
        section.add_widget(marker)
        add("Tie to", tie, full=True, key="tie")
        add("Align", grid, key="align")
        add("Point", point, full=True, key="point")
        add("Edge", edge, full=True, key="edge")
        add("X", x_field, key="x")
        add("Y", y_field, key="y")
        add("Target point", target_point, full=True, key="target_point")
        add("Direction", axis, key="direction")
        add("Distance", distance, key="distance")

        self._position = {"mode": mode, "grid": grid, "point": point,
                          "edge": edge, "x": x_field, "y": y_field,
                          "distance": distance, "tie": tie,
                          "target_point": target_point, "axis": axis,
                          "marker": marker, "rows": rows}
        mode.changed.connect(self._on_position_mode)
        grid.changed.connect(self._on_position_align)
        point.changed.connect(self._on_position_point)
        edge.changed.connect(self._on_position_edge)
        tie.changed.connect(self._on_position_tie)
        target_point.changed.connect(self._on_position_target_point)
        axis.changed.connect(self._on_position_axis)
        x_field.changed.connect(lambda value: self._on_position_xy("x", value))
        y_field.changed.connect(lambda value: self._on_position_xy("y", value))
        distance.changed.connect(self._on_position_distance)
        for field in (x_field, y_field, distance):
            field.preview.connect(self._preview_position)
        self._sync_position()

    def _canvas_extents(self) -> tuple[float, float]:
        return (schema.canvas_axis(self._doc, "width"),
                schema.canvas_axis(self._doc, "height"))

    def _position_payload(self) -> dict:
        container = self._get(self._prefix())
        position = (container.get("position")
                    if isinstance(container, dict) else None)
        return dict(position) if isinstance(position, dict) else {}

    def _position_state(self) -> dict:
        """Active mode, both payloads, the live rectangle, for the controls.

        Legacy positions have no payload: they are presented as a top-left pin
        at the rectangle they render today. Nothing is stored until an edit.
        """
        container = self._get(self._prefix())
        if not isinstance(container, dict):
            container = {}
        position = container.get("position")
        position = position if isinstance(position, dict) else {}
        canvas_size = self._canvas_extents()
        containers = [c for c in self._containers() if isinstance(c, dict)]
        container_id = str(container.get("id", ""))
        errors: dict = {}
        scene = (geometry.resolve_scene(containers, canvas_size, errors=errors)
                 if containers else {})
        rect = (scene.get(container_id)
                or geometry.container_rect(container, canvas_size))
        model = geometry.position_model(position)
        if model is not None:
            canvas = dict(model.get("canvas") or {})
            edge = dict(model.get("edge") or {})
            mode = str(model.get("mode") or "canvas")
        else:
            canvas = {"aligned": None, "anchor": "top_left",
                      "x": _clean_number(rect["x"]),
                      "y": _clean_number(rect["y"])}
            edge = {"anchor": "top_left", "edge": "left",
                    "d": _clean_number(rect["x"]), "unit": "px",
                    "target": schema.POSITION_TARGET_DEFAULT}
            mode = "canvas"
        canvas.setdefault("aligned", None)
        canvas.setdefault("anchor", "top_left")
        canvas.setdefault("x", 0)
        canvas.setdefault("y", 0)
        edge.setdefault("anchor", "top_left")
        edge.setdefault("edge", "left")
        edge.setdefault("d", 0)
        edge.setdefault("unit", "px")
        edge.setdefault("target", schema.POSITION_TARGET_DEFAULT)
        target = str(edge.get("target") or schema.POSITION_TARGET_DEFAULT)
        tied = mode == "edge" and target != schema.POSITION_TARGET_DEFAULT
        return {"mode": mode, "canvas": canvas, "edge": edge, "rect": rect,
                "width": float(rect["width"]),
                "height": float(rect["height"]),
                "id": container_id, "containers": containers, "scene": scene,
                "count": len(containers), "target": target, "tied": tied,
                "targetPoint": (edge.get("targetPoint")
                                or edge.get("anchor") or "top_left"),
                "axis": str(edge.get("axis") or "x"),
                "tie_error": errors.get(container_id, "")}

    def _write_position(self, *, canvas: Optional[dict] = None,
                        edge: Optional[dict] = None,
                        mode: Optional[str] = None) -> None:
        """Write the whole position object: one path, one change."""
        position = self._position_payload()
        position["mode"] = mode or str(position.get("mode") or "canvas")
        if canvas is not None:
            position["canvas"] = dict(canvas)
        if edge is not None:
            position["edge"] = dict(edge)
        self._write(self._prefix() + ("position",), position)
        self._after_edit("position")

    def _sync_position(self) -> None:
        ui = self._position
        if ui is None:
            return
        state = self._position_state()
        canvas, edge = state["canvas"], state["edge"]
        mode = state["mode"]
        aligned = canvas.get("aligned")
        ui["mode"].set_value(mode)
        ui["grid"].set_value(aligned if aligned in geometry.FRACTIONS else "")
        ui["point"].set_value((aligned or canvas.get("anchor")
                               or edge.get("anchor") or "top_left"))
        ui["edge"].set_value(str(edge.get("edge") or "left"))
        if aligned in geometry.FRACTIONS:
            # An aligned pin is derived from the canvas, so the fields show
            # where it sits now and follow a canvas resize (docs §3).
            ax, ay = geometry.fractions(aligned)
            width_total, height_total = self._canvas_extents()
            shown_x, shown_y = ax * width_total, ay * height_total
        else:
            shown_x, shown_y = canvas.get("x"), canvas.get("y")
        ui["x"].set_value(_clean_number(shown_x))
        ui["y"].set_value(_clean_number(shown_y))
        ui["distance"].set_value(_distance_text(edge))
        rows = ui["rows"]
        on_canvas = mode == "canvas"
        rows["align"].setVisible(on_canvas)
        rows["x"].setVisible(on_canvas)
        rows["y"].setVisible(on_canvas)
        rows["edge"].setVisible(not on_canvas)
        rows["distance"].setVisible(not on_canvas)
        pinned = str(edge.get("edge") or "left")
        tied = bool(state["tied"])
        options = [ChoiceOption(schema.POSITION_TARGET_DEFAULT, "Canvas")]
        for other in state["containers"]:
            other_id = str(other.get("id", ""))
            if not other_id:
                continue
            # Also greyed, never hidden: the loop reason is the user's answer
            # to "why is this one not offered".
            options.append(ChoiceOption(
                other_id, other_id,
                disabled_reason=geometry.tie_cycle_reason(
                    state["containers"], state["id"], other_id)))
        target = state["target"]
        if target != schema.POSITION_TARGET_DEFAULT \
                and target not in [option.value for option in options]:
            # A dangling target stays visible so the marker has a subject.
            options.append(ChoiceOption(target, target,
                                        disabled_reason="no such container"))
        ui["tie"].set_options(options, value=target)
        ui["target_point"].set_value(str(state["targetPoint"]))
        ui["axis"].set_value(str(state["axis"]))
        ui["marker"].setText(
            "Tie not applied: " + state["tie_error"] if state["tie_error"]
            else "")
        ui["marker"].setVisible(bool(state["tie_error"]))
        rows["tie"].setVisible(not on_canvas and state["count"] > 1)
        rows["point"].set_label("My point" if tied else "Point")
        rows["target_point"].setVisible(tied)
        rows["direction"].setVisible(tied)
        rows["edge"].setVisible(not on_canvas and not tied)
        rows["distance"].set_label(
            "d" if tied else ("X" if pinned in ("left", "right") else "Y"))

    def _on_position_mode(self, mode: str) -> None:
        """Switch modes without moving the pin.

        Both payloads stay in the document, so switching back restores what
        the other mode held. The new mode is seeded from the rendered pin, so
        canvas → edge keeps x and edge → canvas keeps both axes.
        """
        if self._loading or self._position is None:
            return
        state = self._position_state()
        if mode == state["mode"]:
            return
        canvas = dict(state["canvas"])
        edge = dict(state["edge"])
        anchor = (canvas.get("anchor") if mode == "edge"
                  else edge.get("anchor")) or "top_left"
        ax, ay = geometry.fractions(anchor)
        pin_x = float(state["rect"]["x"]) + ax * state["width"]
        pin_y = float(state["rect"]["y"]) + ay * state["height"]
        if mode == "edge":
            if str(edge.get("target") or schema.POSITION_TARGET_DEFAULT) \
                    != schema.POSITION_TARGET_DEFAULT:
                # A stored tie still owns the placement; switching back to
                # Edge restores it instead of reseeding from the canvas pin.
                self._write_position(edge=edge, mode="edge")
                return
            edge.update({"anchor": anchor, "edge": "left",
                         "d": _clean_number(pin_x), "unit": "px",
                         "target": schema.POSITION_TARGET_DEFAULT})
        else:
            canvas.update({"aligned": None, "anchor": anchor,
                           "x": _clean_number(pin_x),
                           "y": _clean_number(pin_y)})
        self._write_position(canvas=canvas, edge=edge, mode=mode)

    def _on_position_align(self, point: str) -> None:
        """A grid cell pins that point of the box to that canvas point."""
        if self._loading:
            return
        width_total, height_total = self._canvas_extents()
        ax, ay = geometry.fractions(point)
        canvas = dict(self._position_state()["canvas"])
        canvas.update({"aligned": point, "anchor": point,
                       "x": _clean_number(ax * width_total),
                       "y": _clean_number(ay * height_total)})
        self._write_position(canvas=canvas, mode="canvas")

    def _on_position_point(self, point: str) -> None:
        """Choosing the pin sets the anchor and frees it from the grid."""
        if self._loading:
            return
        state = self._position_state()
        if state["mode"] == "edge":
            edge = dict(state["edge"])
            edge["anchor"] = point
            self._write_position(edge=edge, mode="edge")
            return
        canvas = dict(state["canvas"])
        canvas.update({"anchor": point, "aligned": None})
        self._write_position(canvas=canvas, mode="canvas")

    def _on_position_xy(self, axis: str, value: Any) -> None:
        """Editing a coordinate moves the pin and detaches the grid."""
        if self._loading:
            return
        canvas = dict(self._position_state()["canvas"])
        canvas[axis] = _clean_number(value)
        canvas["aligned"] = None
        self._write_position(canvas=canvas, mode="canvas")

    def _on_position_tie(self, target: str) -> None:
        """Point the tie at the canvas or another container.

        Canvas → container seeds the tie so the box does not jump along x: the
        anchor stays, the target point takes the same name, the axis is x, and
        d closes the gap to that point. The y position may move. Container →
        canvas keeps the stored canvas ``edge`` payload, so switching back
        restores it.
        """
        if self._loading or self._position is None:
            return
        state = self._position_state()
        target = str(target or schema.POSITION_TARGET_DEFAULT)
        if target == state["target"]:
            return
        edge = dict(state["edge"])
        if target == schema.POSITION_TARGET_DEFAULT:
            edge["target"] = schema.POSITION_TARGET_DEFAULT
            self._write_position(edge=edge, mode="edge")
            return
        if geometry.tie_cycle_reason(state["containers"], state["id"], target):
            self._sync_position()
            return
        target_rect = state["scene"].get(target)
        if target_rect is None:
            self._sync_position()
            return
        anchor = str(edge.get("anchor") or "top_left")
        ax, _ay = geometry.fractions(anchor)
        pin_x = float(state["rect"]["x"]) + ax * state["width"]
        tx, _ty = geometry.fractions(anchor)
        point_x = float(target_rect["x"]) + tx * float(target_rect["width"])
        edge.update({"target": target, "targetPoint": anchor, "axis": "x",
                     "anchor": anchor, "d": _clean_number(pin_x - point_x),
                     "unit": "px"})
        self._write_position(edge=edge, mode="edge")

    def _on_position_target_point(self, point: str) -> None:
        if self._loading or self._position is None:
            return
        edge = dict(self._position_state()["edge"])
        edge["targetPoint"] = str(point or "top_left")
        self._write_position(edge=edge, mode="edge")

    def _on_position_axis(self, axis: str) -> None:
        if self._loading or self._position is None:
            return
        edge = dict(self._position_state()["edge"])
        edge["axis"] = "y" if str(axis) == "y" else "x"
        self._write_position(edge=edge, mode="edge")

    def _on_position_edge(self, edge_name: str) -> None:
        if self._loading:
            return
        edge = dict(self._position_state()["edge"])
        edge["edge"] = str(edge_name or "left")
        self._write_position(edge=edge, mode="edge")

    def _on_position_distance(self, *_args) -> None:
        if self._loading or self._position is None:
            return
        edge = dict(self._position_state()["edge"])
        number, unit = _distance_parts(self._position["distance"].value())
        edge["d"], edge["unit"] = number, unit
        self._write_position(edge=edge, mode="edge")

    def _preview_position(self, *_args) -> None:
        """Follow a drag without committing it (document preview only)."""
        ui = self._position
        if ui is None or self._loading or self._document is None:
            return
        state = self._position_state()
        canvas = dict(state["canvas"])
        edge = dict(state["edge"])
        if str(ui["mode"].value() or "canvas") == "edge":
            number, unit = _distance_parts(ui["distance"].value())
            edge["d"], edge["unit"] = number, unit
        else:
            canvas["x"] = _clean_number(ui["x"].numeric_value())
            canvas["y"] = _clean_number(ui["y"].numeric_value())
            canvas["aligned"] = None
        position = self._position_payload()
        position.update({"mode": str(ui["mode"].value() or "canvas"),
                         "canvas": canvas, "edge": edge})
        self._document.preview(self._prefix() + ("position",), position,
                               source=self)

    def _refresh_container_shadow_state(self, background: Any = _UNSET) -> None:
        """Show the shadow of what is actually visible (docs §3, decision 3).

        A container background is a rectangle, so it owns the container
        shadow; without one, the border shape owns the shadow. The hidden row
        keeps its stored value, so switching the fill back restores it.

        ``background`` overrides the document for the in-flight paint drag; the
        preview path never writes ``self._doc``, so it must pass its value.
        """
        if self._page() != "container":
            return
        if background is _UNSET:
            background = self._get(("containers", self._container_index,
                                    "container_background"))
        filled = paint_mode(background) != "none"
        for role, show in (("container", filled), ("border", not filled)):
            row = self._shadow_rows.get(role)
            if row is None:
                continue
            try:
                row.setVisible(show)
            except RuntimeError:
                # The page was rebuilt; the registry is replaced there.
                continue

    def _on_container_pick(self, value: str) -> None:
        self.container_selected.emit(str(value))

    def _on_container_rename(self, new_id: str) -> None:
        """Validate a typed id, rename in one write, then rebuild the page."""
        control = self._identity
        document = self._document
        old = self.container_id()
        if control is None or document is None or not old:
            return
        ok, reason = document.validate_container_id(new_id, ignore=old)
        if not ok:
            control.show_error(reason)
            return
        renamed = document.rename_container(old, new_id, source=self)
        if not renamed:
            control.show_error("That id is already used.")
            return
        self._doc = document.snapshot()
        self._container_index = document.container_index(renamed)
        self._rebuild()
        self.theme_changed.emit(self.get_theme())
        self.container_selected.emit(renamed)

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
        if self._page() == "container":
            # The Position section builds its rows itself; its three keys are
            # still part of what this page edits.
            paths.extend(prefix + ("position", key)
                         for key in ("mode", "canvas", "edge"))
        for spec in specs:
            if spec["kind"] == "note" or "path" not in spec:
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

    def _wire_size_fields(self, prefix: tuple) -> None:
        """Collect the size fields and give the preferred rows their hint.

        Min/Max are not bound to each other with limit providers any more: a
        provider clamps the field being edited, which cannot express "raising
        Min raises Max". Each edit decides what it moves (``_size_edits``).
        """
        for leaf in _SIZE_LEAVES:
            widget = self._field_widgets.get(prefix + (leaf,))
            if isinstance(widget, NumberField):
                self._size_fields[leaf] = widget
        for leaf in ("width", "height"):
            row = self._size_rows.get(leaf)
            if row is not None:
                row.set_label_tooltip(_PREFERRED_SIZE_HINT)

    def _size_numbers(self, axis: str) -> tuple[Optional[float], ...]:
        """(preferred, min, max) for one axis as pixels, or ``None`` each.

        Only same-unit values are comparable: ``auto``, unset and percent
        fields stay out of the comparison instead of being converted against
        a canvas the operator may not be thinking about.
        """
        def value(leaf: str) -> Optional[float]:
            field = self._size_fields.get(leaf)
            if field is None or field.keyword():
                return None
            number = field.numeric_value()
            if number is None or field.unit() != "px":
                return None
            return float(number)

        return value(axis), value(f"min_{axis}"), value(f"max_{axis}")

    def _rendered_size(self, axis: str) -> Optional[float]:
        """The size the renderer will use, given Min/Max."""
        preferred, low, high = self._size_numbers(axis)
        if preferred is None:
            return None
        if low is not None:
            preferred = max(preferred, low)
        if high is not None:
            preferred = min(preferred, high)
        return preferred

    def _size_edits(self, leaf: str, path: tuple,
                    widget: NumberField) -> list[tuple[tuple, Any]]:
        """The writes one size edit implies, the clamped value first."""
        prefix = path[:-1]
        axis = "width" if leaf.endswith("width") else "height"
        low_leaf, high_leaf = f"min_{axis}", f"max_{axis}"
        preferred, low, high = self._size_numbers(axis)
        edits: list[tuple[tuple, Any]] = [(path, _length_doc(widget.value()))]
        if leaf == low_leaf and low is not None and high is not None \
                and low > high:
            # Raising Min raises Max instead of clamping Min back.
            self._set_size_widget(self._size_fields[high_leaf], low)
            edits.append((prefix + (high_leaf,), _size_number(low)))
        elif leaf == high_leaf and low is not None and high is not None \
                and high < low:
            # Lowering Max lowers Min.
            self._set_size_widget(self._size_fields[low_leaf], high)
            edits.append((prefix + (low_leaf,), _size_number(high)))
        elif leaf == axis:
            rendered = self._rendered_size(axis)
            if rendered is not None and preferred is not None \
                    and rendered != preferred:
                self._set_size_widget(widget, rendered)
                edits[0] = (path, _size_number(rendered))
        return edits

    def _write_size(self, leaf: str, path: tuple,
                    widget: NumberField) -> None:
        edits = self._size_edits(leaf, path, widget)
        if self._document is not None:
            self._document.set_many(edits, source=self)
            self._doc = self._document.snapshot()
        else:
            for edit_path, value in edits:
                self._write(edit_path, value)
        self._after_edit(leaf)

    @staticmethod
    def _set_size_widget(field: NumberField, value: float) -> None:
        field.set_value(f"{value:g}px", emit=False)

    def _refresh_size_markers(self) -> None:
        """Say where a preferred size will actually render.

        Loading never rewrites the document. When Min/Max push Width or Height
        somewhere else, the authored value stays and the row carries the
        marker "Renders as <value>" instead.
        """
        if self._page() != "container":
            return
        for axis in ("width", "height"):
            row = self._size_rows.get(axis)
            if row is None:
                continue
            preferred, _low, _high = self._size_numbers(axis)
            rendered = self._rendered_size(axis)
            if rendered is None or preferred is None or rendered == preferred:
                row.set_warning("")
            else:
                row.set_warning(f"Renders as {rendered:g}px")

    def _add_specs(self, specs: list[dict], prefix: tuple) -> None:
        for spec in specs:
            if spec["kind"] == "note":
                self._layout.addWidget(self._note_label(spec.get("text", "")))
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
            if not row._full_width:
                self._page_rows.append(row)
            self._bind(widget, path, spec)
            if isinstance(widget, NumberField):
                self._field_widgets[path] = widget
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

    @staticmethod
    def _converter(total: float):
        return lambda value, old, new: schema.convert_length(
            value, old, new, total)

    def _length_limits(self, leaf: str, units: list[str]):
        """Per-mode ranges for a length field, canvas-aware for px/%."""
        if "px" in units and "%" in units:
            axis = "height" if "height" in leaf else "width"
            total = schema.canvas_axis(self._doc, axis)
            if leaf in ("width", "height") or leaf.startswith(
                    ("min_", "max_")):
                return schema.size_limits(total), self._converter(total)
            return schema.offset_limits(total), self._converter(total)
        ranges = schema.limits_for(leaf)
        if ranges:
            narrowed = {unit: ranges[unit] for unit in units
                        if unit in ranges}
            return (narrowed or ranges), None
        return None, None

    def _make(self, spec: dict, initial: Any) -> Optional[QWidget]:
        kind = spec["kind"]
        leaf = spec["path"][-1] if spec["path"] else ""
        if kind in ("int", "int_null"):
            ranges = schema.limits_for(leaf)
            return NumberField(
                "" if initial is None else initial,
                integer=True, step=spec.get("step", 1),
                nullable=(kind == "int_null"),
                unit_ranges=ranges,
                placeholder="Default")
        if kind == "float":
            ranges = schema.limits_for(leaf)
            return NumberField(0.0 if initial is None else initial,
                               step=spec.get("step", 0.1),
                               unit_ranges=ranges)
        if kind in ("length", "length_null"):
            units = list(spec.get("units", ["px", "em"]))
            ranges, converter = self._length_limits(leaf, units)
            placeholder = spec.get("placeholder") or (
                "Default" if kind == "length_null" else "Inherit")
            return NumberField(
                _length_text(initial), units=units,
                nullable=True,
                keywords=spec.get("keywords", ()),
                unit_ranges=ranges, unit_converter=converter,
                placeholder=placeholder)
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
        if kind == "backdrop":
            return BackdropField(initial if initial is not None else "none")
        if kind in ("text", "font"):
            return TextInput(str(initial or ""))
        return None

    def _bind(self, widget: QWidget, path: tuple, spec: dict) -> None:
        def changed(*_args) -> None:
            if self._loading:
                return
            leaf = str(path[-1])
            if leaf in _SIZE_LEAVES and self._page() == "container":
                # Size fields cannot be written alone: Min, Max and the
                # preferred value move each other (docs §2, size semantics).
                self._write_size(leaf, path, widget)
                return
            self._write(path, self._doc_value(spec, widget))
            self._after_edit(leaf)

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
        # A live paint drag can flip which shadow is visible before it commits,
        # and the preview does not touch the document snapshot this reads.
        self._refresh_container_shadow_state(
            value if path and path[-1] == "container_background" else _UNSET)

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
        if kind in ("border", "shadow", "shadow_no_shared", "backdrop"):
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
        self._refresh_container_shadow_state()
        self._refresh_size_markers()
        self._sync_position()
        self.theme_changed.emit(self.get_theme())

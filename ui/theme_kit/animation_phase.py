"""ui/theme_kit/animation_phase.py

AnimationPhaseCard — one animation phase (Entry, Transition In/Out, Exit).

The card speaks the slot grammar from the theme reference:

* absent (``None``) or ``"none"`` — the phase is off / inherits its parent,
* ``"name"`` — a library, shared or built-in definition,
* ``{"use": name, ...}`` — that definition with duration/delay/easing/origin
  overrides, and
* an inline definition object with a ``type``.

Library definitions are passed in as :class:`AnimationDefinition` records so
the card can show overrides against the values it is overriding and reset them
back. Nothing here validates a slot; invalid choices are disabled with the
caller's reason (plus the reference's typewriter-on-out rule).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractButton, QFrame, QHBoxLayout, QLineEdit, QSizePolicy, QVBoxLayout,
    QWidget,
)

from ui import tokens
from ui.theme_kit.base import (
    ChoiceOption, coerce_options, draw_chevron, elide, font, paint_focus_ring,
)
from ui.theme_kit.chip_select import ChipSelect
from ui.theme_kit.color_field import ColorField
from ui.theme_kit.dropdown import CompactDropdown
from ui.theme_kit.easing_picker import EasingPicker
from ui.theme_kit.number_field import NumberField
from ui.theme_kit.property_row import PropertyRow
from ui.theme_kit.small import IconButton, InlineMessage
from ui.theme_kit.switch import Switch

#: Inline definition types from the reference. The caller may narrow this.
INLINE_TYPES = (
    "fade_in", "fade_up", "fade_down", "scale_up", "scale_down",
    "slide_up", "slide_down", "typewriter", "custom",
)
ORIGINS = (
    "center", "top", "bottom", "left", "right",
    "top left", "top right", "bottom left", "bottom right",
)
_OVERRIDE_KEYS = ("duration_ms", "delay_ms", "easing", "origin")
_OFF_PHASES = ("transition_out", "out")


@dataclass
class AnimationDefinition:
    """One animation the caller can offer in a slot.

    ``source`` is display-only ("library", "shared", "built-in"); the card does
    not resolve names itself.
    """

    name: str
    type: str
    label: str = ""
    duration_ms: int = 0
    delay_ms: int = 0
    easing: str = "ease-out"
    origin: str = "center"
    source: str = ""
    reveal: str = ""
    cursor: Any = None
    raw: dict[str, Any] = field(default_factory=dict)

    def title(self) -> str:
        return self.label or self.name.replace("_", " ").title()

    def as_dict(self) -> dict[str, Any]:
        data = dict(self.raw)
        data.setdefault("type", self.type)
        if self.duration_ms:
            data.setdefault("duration_ms", self.duration_ms)
        data.setdefault("delay_ms", self.delay_ms)
        data.setdefault("easing", self.easing)
        data.setdefault("origin", self.origin)
        if self.reveal:
            data.setdefault("reveal", self.reveal)
        if self.cursor is not None:
            data.setdefault("cursor", self.cursor)
        return data


def slot_mode(value: Any) -> str:
    """``none``, ``name``, ``overrides`` or ``inline``."""
    if value is None:
        return "none"
    if isinstance(value, str):
        return "none" if value.strip().lower() in ("none", "off", "") else "name"
    if isinstance(value, dict):
        if "use" in value:
            return "overrides"
        if value:
            return "inline"
    return "none"


def resolve_slot(value: Any,
                 definitions: dict[str, AnimationDefinition]
                 ) -> dict[str, Any]:
    """Effective definition data for a slot (empty when the phase is off)."""
    mode = slot_mode(value)
    if mode == "none":
        return {}
    if mode == "name":
        definition = definitions.get(str(value))
        return definition.as_dict() if definition else {}
    if mode == "overrides":
        name = str(value.get("use"))
        definition = definitions.get(name)
        data = (definition.as_dict() if definition
                else {"type": "fade_in", "name": name})
        for key in _OVERRIDE_KEYS:
            if key in value:
                data[key] = value[key]
        return data
    return dict(value)


class _PhaseHeader(QAbstractButton):
    """Collapsed line: chevron, phase name, type chip, delay/duration bar."""

    def __init__(self, title: str, *, light: bool = False, parent=None):
        super().__init__(parent)
        self._title = title
        self._type_label = "None"
        self._active = False
        self._delay = 0
        self._duration = 0
        self._light = light
        self._hover = False
        self.setCheckable(True)
        self.setChecked(False)
        self.setFixedHeight(22 if light else 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setAccessibleName(f"{title} phase")
        self.toggled.connect(self.update)

    def set_summary(self, type_label: str, *, active: bool, delay: int,
                    duration: int) -> None:
        self._type_label = type_label
        self._active = bool(active)
        self._delay = max(0, int(delay))
        self._duration = max(0, int(duration))
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())
        if self._hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tokens.BG_CARD_HOVER))
            painter.drawRoundedRect(rect, tokens.RADIUS_SM, tokens.RADIUS_SM)
        draw_chevron(
            painter, QRectF(rect.left() + 2, rect.top(), 14,
                            rect.height()).center(),
            "down" if self.isChecked() else "right",
            tokens.TEXT_SECONDARY if self._hover else tokens.TEXT_MUTED,
            size=4.6)

        title_font = font(tokens.TYPE_CAPTION, tokens.WEIGHT_SEMIBOLD)
        painter.setFont(title_font)
        painter.setPen(QColor(tokens.TEXT_PRIMARY if self._active
                              else tokens.TEXT_SECONDARY))
        title_width = min(
            QFontMetrics(title_font).horizontalAdvance(self._title) + 6,
            96.0, max(30.0, rect.width() * 0.62))
        title_rect = QRectF(rect.left() + 18, rect.top(),
                            title_width, rect.height())
        painter.drawText(
            title_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            elide(self._title, title_rect.width(),
                  weight=tokens.WEIGHT_SEMIBOLD))

        chip_font = font(10, tokens.WEIGHT_SEMIBOLD)
        metrics = QFontMetrics(chip_font)
        chip_text = self._type_label
        chip_width = min(metrics.horizontalAdvance(chip_text) + 12, 68.0,
                         max(0.0, rect.right() - title_rect.right() - 8))
        chip = QRectF(title_rect.right() + 4, rect.center().y() - 8,
                      chip_width, 16)
        if chip_width > 24:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tokens.ACCENT_TINT if self._active
                                    else tokens.BG_FIELD))
            painter.drawRoundedRect(chip, 8, 8)
            painter.setFont(chip_font)
            painter.setPen(QColor(tokens.ACCENT_TEXT if self._active
                                  else tokens.TEXT_MUTED))
            painter.drawText(
                chip.adjusted(5, 0, -5, 0),
                int(Qt.AlignmentFlag.AlignLeft |
                    Qt.AlignmentFlag.AlignVCenter),
                metrics.elidedText(chip_text, Qt.TextElideMode.ElideRight,
                                   int(chip.width() - 10)))
            bar_left = chip.right() + 6
        else:
            bar_left = title_rect.right() + 6

        bar_right = rect.right() - 4
        if (self._active and bar_right - bar_left >= 26
                and (self._delay or self._duration)):
            track = QRectF(bar_left, rect.center().y() - 2,
                           bar_right - bar_left, 4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tokens.BORDER_HAIRLINE))
            painter.drawRoundedRect(track, 2, 2)
            total = max(1, self._delay + self._duration)
            delay_width = track.width() * self._delay / total
            if delay_width >= 1:
                painter.setBrush(QColor(tokens.TEXT_MUTED))
                painter.drawRoundedRect(
                    QRectF(track.left(), track.top(), delay_width,
                           track.height()), 2, 2)
            start = track.left() + delay_width
            duration_width = max(1.0, track.right() - start)
            painter.setBrush(QColor(tokens.ACCENT))
            painter.drawRoundedRect(
                QRectF(start, track.top(), duration_width, track.height()),
                2, 2)
        if self.hasFocus():
            paint_focus_ring(painter, rect.adjusted(1, 1, -1, -1),
                             tokens.RADIUS_SM)
        painter.end()


class AnimationPhaseCard(QFrame):
    """One animation phase, collapsible, with library overrides and replay.

    Signals
        changed(object) — the new slot value.
        preview(object) — the slot value while a continuous control drags.
        replay(object) — the current slot, for playing just this phase.

    Args
        phase: ``entry``, ``transition_in``, ``transition_out`` or ``out``.
            ``out`` phases disable typewriter automatically.
        library/builtins: :class:`AnimationDefinition` lists (builtins are
            usually a subset of the library; both are offered).
        inline_types: type values offered under "Inline".
        disabled_types: ``[(type, reason)]`` from the caller.
        disabled_library: ``[(name, reason)]`` from the caller.
        off_value: value emitted when the switch is off (``"none"`` for a
            normal phase, ``None`` for an inheritable split assignment).
        typewriter: show the nested typewriter controls (default True).
    """

    changed = pyqtSignal(object)
    preview = pyqtSignal(object)
    replay = pyqtSignal(object)

    def __init__(self, title: str, value: Any = None, *,
                 phase: str = "entry",
                 library: Iterable[AnimationDefinition] = (),
                 builtins: Iterable[AnimationDefinition] = (),
                 inline_types: Iterable[str] = INLINE_TYPES,
                 disabled_types: Iterable[tuple[str, str]] = (),
                 disabled_library: Iterable[tuple[str, str]] = (),
                 duration_range: tuple[float, float] = (0, 5000),
                 delay_range: tuple[float, float] = (0, 5000),
                 easing_presets: Optional[list[str]] = None,
                 origin_options: Iterable[str] = ORIGINS,
                 palette: Iterable[tuple[str, str]] = (),
                 allow_none: bool = True,
                 off_value: Any = "none",
                 off_label: str = "None",
                 typewriter: bool = True,
                 slot_defaults: Optional[dict[str, Any]] = None,
                 light: bool = False,
                 expanded: bool = False,
                 parent=None):
        super().__init__(parent)
        self._title = str(title)
        self._phase = phase
        self._light = bool(light)
        self._off_value = off_value
        self._off_label = off_label
        self._allow_none = bool(allow_none)
        self._duration_range = duration_range
        self._delay_range = delay_range
        self._easing_presets = easing_presets
        self._origin_options = list(origin_options)
        self._palette = list(palette)
        self._slot_defaults = dict(slot_defaults or {})
        self._typewriter_enabled = bool(typewriter)
        self._definitions: dict[str, AnimationDefinition] = {}
        self._library = list(library)
        self._builtins = list(builtins)
        for definition in self._library + self._builtins:
            self._definitions[definition.name] = definition
        self._inline_types = [str(t) for t in inline_types]
        self._disabled_types = dict(disabled_types)
        if phase in _OFF_PHASES:
            self._disabled_types.setdefault(
                "typewriter", "Typewriter cannot run on an out phase")
        self._disabled_library = dict(disabled_library)

        self._mode = "none"
        self._name = ""
        self._overrides: dict[str, Any] = {}
        self._inline: dict[str, Any] = {}
        self._last_on: Any = None
        self._updating = False
        self._expanded = bool(expanded)
        self._replay_available = True
        self._editor: Optional[QWidget] = None

        self._label_width = 68 if self._light else 84
        self.setObjectName("rcPhaseCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QFrame#rcPhaseCard {{ background: {tokens.BG_CARD};"
            f" border-radius: {tokens.RADIUS_MD}px; }}")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(tokens.SPACE_4, tokens.SPACE_4,
                                 tokens.SPACE_4, tokens.SPACE_4)
        outer.setSpacing(tokens.SPACE_4)

        head = QWidget(self)
        head_row = QHBoxLayout(head)
        head_row.setContentsMargins(0, 0, 0, 0)
        head_row.setSpacing(2)
        self.header = _PhaseHeader(self._title, light=self._light, parent=head)
        self.header.setChecked(self._expanded)
        self.header.toggled.connect(self._on_header_toggled)
        head_row.addWidget(self.header, 1)
        self.replay_button = IconButton(
            glyph="play", tooltip="Replay this phase",
            accessible_name="Replay this phase",
            variant="ghost", compact=True, parent=head)
        self.replay_button.clicked.connect(self._on_replay)
        head_row.addWidget(self.replay_button, 0)
        self.switch = Switch(self._mode != "none", parent=head)
        self.switch.setAccessibleName(f"{self._title} enabled")
        self.switch.changed.connect(self._on_switch)
        head_row.addWidget(self.switch, 0)
        outer.addWidget(head)

        self.body = QWidget(self)
        self.body.setVisible(self._expanded)
        body = QVBoxLayout(self.body)
        body.setContentsMargins(2, 2, 2, 2)
        body.setSpacing(tokens.SPACE_4)

        self.selector = CompactDropdown(self._selector_options(), None,
                                        searchable=True, parent=self.body)
        self.selector.changed.connect(self._on_selector)
        self.selector_row = PropertyRow(
            "Animation", self.selector, label_width=self._label_width)
        body.addWidget(self.selector_row)

        self.duration = NumberField(
            self._value("duration_ms"),
            minimum=duration_range[0], maximum=duration_range[1],
            integer=True, step=50, coarse_step=500,
            suffix="ms", label=f"{title} duration")
        self.duration_row = PropertyRow(
            "Duration", self.duration, label_width=self._label_width)
        self.duration_row.reset_requested.connect(
            lambda: self._clear_override("duration_ms"))
        body.addWidget(self.duration_row)

        self.delay = NumberField(
            self._value("delay_ms"),
            minimum=delay_range[0], maximum=delay_range[1],
            integer=True, step=10, coarse_step=100,
            suffix="ms", label=f"{title} delay")
        self.delay_row = PropertyRow(
            "Delay", self.delay, label_width=self._label_width)
        self.delay_row.reset_requested.connect(
            lambda: self._clear_override("delay_ms"))
        body.addWidget(self.delay_row)

        self.easing = EasingPicker(
            self._value("easing") or "ease-out",
            presets=easing_presets, parent=self.body)
        self.easing_row = PropertyRow(
            "Easing", self.easing, label_width=self._label_width)
        self.easing_row.reset_requested.connect(
            lambda: self._clear_override("easing"))
        body.addWidget(self.easing_row)

        short = {"center": "C", "top": "T", "bottom": "B",
                 "left": "L", "right": "R", "top left": "TL",
                 "top right": "TR", "bottom left": "BL",
                 "bottom right": "BR"}
        origin_options = [ChoiceOption(
            origin, short.get(origin, str(origin).replace("_", " ")[:2]),
            tooltip=str(origin).replace("_", " ").title())
            for origin in self._origin_options]
        self.origin = ChipSelect(origin_options, self._value("origin"),
                                 parent=self.body)
        self.origin.set_accessible_label(f"{title} origin")
        self.origin_row = PropertyRow(
            "Origin", self.origin, label_width=self._label_width)
        self.origin_row.reset_requested.connect(
            lambda: self._clear_override("origin"))
        body.addWidget(self.origin_row)

        self.typewriter_host = QWidget(self.body)
        tw = QVBoxLayout(self.typewriter_host)
        tw.setContentsMargins(0, 2, 0, 0)
        tw.setSpacing(tokens.SPACE_4)
        tw.addWidget(InlineMessage("Typewriter", role="info"))
        self.tw_readonly = InlineMessage("", role="muted")
        tw.addWidget(self.tw_readonly)
        self.tw_reveal = ChipSelect(
            [ChoiceOption("default", "Default", muted=True),
             ChoiceOption("char", "Char"), ChoiceOption("word", "Word")],
            "default", parent=self.typewriter_host)
        self.tw_reveal.changed.connect(
            lambda value: self._write_typewriter(
                "reveal", None if value == "default" else value))
        tw.addWidget(PropertyRow("Reveal", self.tw_reveal,
                                 label_width=self._label_width))
        self.tw_cursor = ChipSelect(
            [ChoiceOption("default", "Default", muted=True),
             ChoiceOption("none", "None"), ChoiceOption("custom", "Custom")],
            "default", parent=self.typewriter_host)
        self.tw_cursor.changed.connect(self._on_cursor_changed)
        tw.addWidget(PropertyRow("Cursor", self.tw_cursor,
                                 label_width=self._label_width))
        self.tw_char = QLineEdit(self.typewriter_host)
        self.tw_char.setMaxLength(2)
        self.tw_char.setFixedHeight(tokens.CONTROL_HEIGHT)
        self.tw_char.setPlaceholderText("▌")
        self.tw_char.setAccessibleName("Cursor character")
        self.tw_char.setStyleSheet(
            f"QLineEdit {{ background: {tokens.BG_FIELD};"
            f" color: {tokens.TEXT_PRIMARY};"
            f" border: 1px solid {tokens.BORDER_POPOVER};"
            f" border-radius: {tokens.RADIUS_SM}px;"
            f" padding: 0 {tokens.SPACE_8}px;"
            f" font-size: {tokens.TYPE_CAPTION}px; }}"
            f"QLineEdit:focus {{ border-color: {tokens.ACCENT}; }}")
        self.tw_char.editingFinished.connect(
            lambda: self._set_cursor_field("char", self.tw_char.text()))
        self.tw_char_row = PropertyRow("Char", self.tw_char,
                                    label_width=self._label_width)
        tw.addWidget(self.tw_char_row)
        self.tw_color = ColorField(
            "currentColor", palette=self._palette,
            keywords=("currentColor",), nullable=True, parent=self.typewriter_host)
        self.tw_color.changed.connect(
            lambda value: self._set_cursor_field("color", value))
        self.tw_color_row = PropertyRow("Color", self.tw_color,
                                    label_width=self._label_width)
        tw.addWidget(self.tw_color_row)
        self.tw_blink = NumberField(
            None, minimum=0, maximum=2000, integer=True, step=50,
            suffix="ms", nullable=True, placeholder="Default",
            label="Cursor blink")
        self.tw_blink.changed.connect(
            lambda value: self._set_cursor_field("blink_ms", value))
        self.tw_blink_row = PropertyRow("Blink", self.tw_blink,
                                    label_width=self._label_width)
        tw.addWidget(self.tw_blink_row)
        self.tw_hide = NumberField(
            None, minimum=0, maximum=5000, integer=True, step=100,
            suffix="ms", nullable=True, placeholder="Default",
            label="Cursor hide after")
        self.tw_hide.changed.connect(
            lambda value: self._set_cursor_field("hide_after_ms", value))
        self.tw_hide_row = PropertyRow("Hide", self.tw_hide,
                                    label_width=self._label_width)
        tw.addWidget(self.tw_hide_row)
        self.tw_convert = IconButton(
            text="Edit as inline", tooltip="Copy into an inline animation",
            accessible_name="Edit typewriter as inline animation",
            parent=self.typewriter_host)
        tw.addWidget(self.tw_convert, 0, Qt.AlignmentFlag.AlignLeft)
        self.tw_convert.clicked.connect(self._convert_to_inline)
        body.addWidget(self.typewriter_host)

        self.note = InlineMessage("", role="muted")
        self.note.hide()
        body.addWidget(self.note)
        outer.addWidget(self.body)

        self.duration.changed.connect(
            lambda value: self._write_override("duration_ms", value))
        self.duration.preview.connect(
            lambda value: self._write_override("duration_ms", value,
                                               commit=False))
        self.delay.changed.connect(
            lambda value: self._write_override("delay_ms", value))
        self.delay.preview.connect(
            lambda value: self._write_override("delay_ms", value,
                                              commit=False))
        self.easing.changed.connect(
            lambda value: self._write_override("easing", value))
        self.easing.preview.connect(
            lambda value: self._write_override("easing", value,
                                               commit=False))
        self.origin.changed.connect(
            lambda value: self._write_override("origin", value))
        self.set_value(value)
        self._apply_expanded()

    # ── public ──────────────────────────────────────────────────────────────
    def value(self) -> Any:
        if self._mode == "none":
            return self._off_value
        if self._mode == "name":
            return self._name
        if self._mode == "overrides":
            data: dict[str, Any] = {"use": self._name}
            data.update(self._overrides)
            return data
        return dict(self._inline)

    def set_value(self, value: Any) -> None:
        self._updating = True
        try:
            mode = slot_mode(value)
            self._mode = mode
            self._name = ""
            self._overrides = {}
            self._inline = {}
            if mode == "name":
                self._name = str(value)
            elif mode == "overrides":
                self._name = str(value.get("use", ""))
                # Keep overrides the card has no row for (typewriter reveal,
                # cursor, custom origin data) so editing one field cannot
                # silently drop the rest of the slot.
                self._overrides = {key: value[key] for key in value
                                   if key != "use"}
            elif mode == "inline":
                self._inline = dict(value)
            if mode != "none":
                self._last_on = self.value()
            self._sync()
        finally:
            self._updating = False

    def effective(self) -> dict[str, Any]:
        return resolve_slot(self.value(), self._definitions)

    def is_active(self) -> bool:
        return self._mode != "none"

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = bool(expanded)
        self.header.blockSignals(True)
        self.header.setChecked(self._expanded)
        self.header.blockSignals(False)
        self._apply_expanded()

    def is_expanded(self) -> bool:
        return self._expanded

    def set_replay_available(self, available: bool) -> None:
        self._replay_available = bool(available)
        self._sync_replay()

    def set_warning(self, text: str) -> None:
        self.note.setText(str(text or ""))
        self.note.set_role("warning" if text else "muted")
        self.note.setVisible(bool(text))

    def set_editor_widget(self, widget: Optional[QWidget]) -> None:
        """Attach a caller-owned editor (ParamForm/Timeline) below the rows."""
        if widget is self._editor:
            return
        if self._editor is not None:
            self.body.layout().removeWidget(self._editor)
            self._editor.setParent(None)
            self._editor.deleteLater()
        self._editor = widget
        if widget is not None:
            self.body.layout().addWidget(widget)

    def editor_widget(self) -> Optional[QWidget]:
        return self._editor

    def set_library(self, library: Iterable[AnimationDefinition],
                    builtins: Iterable[AnimationDefinition] = ()) -> None:
        self._library = list(library)
        self._builtins = list(builtins)
        self._definitions = {}
        for definition in self._library + self._builtins:
            self._definitions[definition.name] = definition
        self.selector.set_options(self._selector_options(),
                                  value=self._selector_value())
        self._sync()

    # ── state ───────────────────────────────────────────────────────────────
    def _value(self, key: str, default: Any = None) -> Any:
        mode = self._mode
        if mode == "none":
            return self._slot_defaults.get(key, default)
        if mode == "name":
            definition = self._definitions.get(self._name)
            if definition is not None:
                return definition.as_dict().get(
                    key, self._slot_defaults.get(key, default))
            return self._slot_defaults.get(key, default)
        if mode == "overrides":
            if key in self._overrides:
                return self._overrides[key]
            definition = self._definitions.get(self._name)
            if definition is not None:
                return definition.as_dict().get(
                    key, self._slot_defaults.get(key, default))
            return self._slot_defaults.get(key, default)
        return self._inline.get(key, self._slot_defaults.get(key, default))

    def _selector_options(self) -> list[ChoiceOption]:
        options = [ChoiceOption(None, self._off_label, muted=True)]
        for definition in self._library:
            reason = self._disabled_library.get(definition.name, "")
            if not reason and definition.type in self._disabled_types:
                reason = self._disabled_types[definition.type]
            options.append(ChoiceOption(
                definition.name, definition.title(),
                group=definition.source.title() or "Library",
                disabled_reason=reason,
                tooltip=f"{definition.type} · {definition.duration_ms} ms"
                        + (f" — {reason}" if reason else "")))
        for definition in self._builtins:
            if definition.name in self._definitions and any(
                    option.value == definition.name for option in options):
                continue
            reason = self._disabled_library.get(definition.name, "")
            options.append(ChoiceOption(
                definition.name, definition.title(), group="Built-in",
                disabled_reason=reason))
        for type_value in self._inline_types:
            reason = self._disabled_types.get(type_value, "")
            options.append(ChoiceOption(
                ("inline", type_value),
                f"Inline · {type_value.replace('_', ' ').title()}",
                group="Inline custom", disabled_reason=reason))
        if self._mode in ("name", "overrides") and self._name and not any(
                option.value == self._name for option in options):
            options.insert(1, ChoiceOption(
                self._name, f"{self._name} (unavailable)",
                group="Unavailable"))
        return options

    def _selector_value(self) -> Any:
        if self._mode == "none":
            return None
        if self._mode == "inline":
            return ("inline", self._inline.get("type", self._inline_types[0]
                                               if self._inline_types else ""))
        return self._name

    def _type_label(self) -> str:
        if self._mode == "none":
            return self._off_label if self._allow_none else "None"
        data = self.effective()
        name = str(data.get("type", ""))
        definition = self._definitions.get(self._name)
        if definition is not None and definition.name == self._name:
            return definition.title()
        if name:
            return name.replace("_", " ").title()
        return self._name or "Unknown"

    def _sync(self) -> None:
        self._updating = True
        try:
            self.selector.set_options(self._selector_options(),
                                      value=self._selector_value())
            self.duration.set_value(self._value("duration_ms", 0))
            self.delay.set_value(self._value("delay_ms", 0))
            self.easing.set_value(self._value("easing") or "ease-out")
            self.origin.set_value(self._value("origin") or "center")
            self._sync_changed()
            self._sync_typewriter()
            self.switch.set_value(self._mode != "none")
            data = self.effective()
            self.header.set_summary(
                self._type_label(),
                active=self._mode != "none",
                delay=int(data.get("delay_ms", 0) or 0),
                duration=int(data.get("duration_ms", 0) or 0))
            self._sync_replay()
        finally:
            self._updating = False

    def _sync_changed(self) -> None:
        overridden = set(self._overrides) if self._mode == "overrides" else set()
        if self._mode == "inline":
            overridden = set(self._inline)
        self.duration_row.set_changed("duration_ms" in overridden)
        self.delay_row.set_changed("delay_ms" in overridden)
        self.easing_row.set_changed("easing" in overridden)
        self.origin_row.set_changed("origin" in overridden)
        active = self._mode != "none"
        for row in (self.duration_row, self.delay_row, self.easing_row,
                    self.origin_row):
            row.setEnabled(active)
        self.selector_row.setEnabled(True)
        data = self.effective()
        is_typewriter = str(data.get("type", "")) == "typewriter"
        self.origin_row.set_disabled_reason(
            "Typewriter does not use an origin" if is_typewriter else "")

    def _sync_replay(self) -> None:
        self.replay_button.setEnabled(
            self._mode != "none" and self._replay_available)
        self.replay_button.setVisible(self._replay_available)

    def _apply_expanded(self) -> None:
        self.body.setVisible(self._expanded)

    # ── writing ─────────────────────────────────────────────────────────────
    def _write_override(self, key: str, value: Any, *,
                        commit: bool = True) -> None:
        if self._updating or self._mode == "none":
            return
        if self._mode == "inline":
            if value is None:
                self._inline.pop(key, None)
            else:
                self._inline[key] = value
        else:
            if self._mode == "name":
                self._mode = "overrides"
                self._overrides = {}
            if value is None:
                self._overrides.pop(key, None)
                if not self._overrides:
                    self._mode = "name"
            else:
                self._overrides[key] = value
        self._last_on = self.value()
        self._sync()
        if commit:
            self.changed.emit(self.value())
        else:
            self.preview.emit(self.value())

    def _clear_override(self, key: str) -> None:
        if self._mode == "inline":
            self._inline.pop(key, None)
        elif self._mode == "overrides":
            self._overrides.pop(key, None)
            if not self._overrides:
                self._mode = "name"
        else:
            return
        self._sync()
        self.changed.emit(self.value())

    def _on_selector(self, value: Any) -> None:
        if self._updating:
            return
        if value is None:
            self._mode = "none"
            self._name = ""
            self._overrides = {}
            self._inline = {}
        elif isinstance(value, tuple) and value and value[0] == "inline":
            self._mode = "inline"
            self._inline = {"type": value[1]}
            self._name = ""
            self._overrides = {}
        else:
            self._mode = "name"
            self._name = str(value)
            self._overrides = {}
            self._inline = {}
        if self._mode != "none":
            self._last_on = self.value()
        self._sync()
        self.changed.emit(self.value())

    def _on_switch(self, checked: bool) -> None:
        if self._updating:
            return
        if checked:
            if self._last_on is not None and slot_mode(self._last_on) != "none":
                self.set_value(self._last_on)
            else:
                self._select_default()
        else:
            if self._mode != "none":
                self._last_on = self.value()
            self._mode = "none"
            self._name = ""
            self._overrides = {}
            self._inline = {}
            self._sync()
        self.changed.emit(self.value())

    def _select_default(self) -> None:
        for option in self._selector_options():
            if option.value is None or option.disabled_reason:
                continue
            if isinstance(option.value, tuple):
                self._mode = "inline"
                self._inline = {"type": option.value[1]}
            else:
                self._mode = "name"
                self._name = str(option.value)
            self._last_on = self.value()
            self._sync()
            return

    def _on_header_toggled(self, expanded: bool) -> None:
        self._expanded = bool(expanded)
        self._apply_expanded()

    def _on_replay(self) -> None:
        if self._mode != "none":
            self.replay.emit(self.value())

    # ── typewriter ──────────────────────────────────────────────────────────
    @staticmethod
    def _cursor_data(data: dict[str, Any]) -> dict[str, Any]:
        cursor = data.get("cursor", None)
        if isinstance(cursor, dict):
            return dict(cursor)
        return {}

    def _cursor_mode(self) -> str:
        data = self.effective()
        cursor = data.get("cursor", None)
        if cursor in (None, ""):
            return "default"
        if isinstance(cursor, str):
            return "none" if cursor == "none" else "default"
        return "custom"

    def _effective_cursor(self) -> dict[str, Any]:
        return self._cursor_data(self.effective())

    def _sync_typewriter(self) -> None:
        data = self.effective()
        is_typewriter = str(data.get("type", "")) == "typewriter"
        self.typewriter_host.setVisible(is_typewriter and self._typewriter_enabled)
        if not (is_typewriter and self._typewriter_enabled):
            return
        editable = self._mode == "inline"
        cursor = self._cursor_data(data)
        self.tw_readonly.setVisible(not editable)
        self.tw_convert.setVisible(not editable)
        self.tw_readonly.setText(
            "Defined by the animation. Edit as inline to change it.")
        for widget in (self.tw_reveal, self.tw_cursor, self.tw_char,
                       self.tw_color, self.tw_blink, self.tw_hide):
            widget.setEnabled(editable)
        reveal = data.get("reveal", "default")
        self.tw_reveal.set_value(reveal if reveal in ("char", "word")
                                 else "default")
        self.tw_cursor.set_value(self._cursor_mode())
        custom_visible = editable and self._cursor_mode() == "custom"
        for row, widget in ((self.tw_char_row, self.tw_char),
                            (self.tw_color_row, self.tw_color),
                            (self.tw_blink_row, self.tw_blink),
                            (self.tw_hide_row, self.tw_hide)):
            widget.setVisible(custom_visible)
            row.setVisible(custom_visible)
        if custom_visible:
            self.tw_char.setText(str(cursor.get("char", "")))
            self.tw_color.set_value(cursor.get("color", "currentColor"))
            self.tw_blink.set_value(cursor.get("blink_ms"))
            self.tw_hide.set_value(cursor.get("hide_after_ms"))

    def _on_cursor_changed(self, value: Any) -> None:
        if self._updating:
            return
        if value == "none":
            self._write_override("cursor", "none")
        elif value == "default":
            self._write_override("cursor", None)
        else:
            self._write_override("cursor", dict(self._effective_cursor()))

    def _write_typewriter(self, key: str, value: Any) -> None:
        if self._updating or self._mode != "inline":
            return
        if value is None:
            self._inline.pop(key, None)
        else:
            self._inline[key] = value
        self._sync()
        self.changed.emit(self.value())

    def _set_cursor_field(self, key: str, value: Any) -> None:
        if self._updating or self._mode != "inline":
            return
        cursor = dict(self._effective_cursor())
        if value in (None, ""):
            cursor.pop(key, None)
        else:
            cursor[key] = value
        self._inline["cursor"] = cursor
        self._sync()
        self.changed.emit(self.value())

    def _convert_to_inline(self) -> None:
        data = self.effective()
        self._mode = "inline"
        self._inline = dict(data)
        self._name = ""
        self._overrides = {}
        self._sync()
        self.changed.emit(self.value())


__all__ = [
    "AnimationDefinition", "AnimationPhaseCard", "INLINE_TYPES", "ORIGINS",
    "slot_mode", "resolve_slot",
]

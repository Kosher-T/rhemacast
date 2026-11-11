"""ParamForm — build controls for one animation from the registry.

Stage 3 embeds this; it is not a phase card or a timeline. The form owns no
per-animation code: give it a type (or a definition) and it renders the
registry's parameters with theme_kit widgets.

Round-trip: the form edits a copy of the definition it was given, so keys the
registry does not know survive. Bounds come from the registry (the same values
the validator uses); the host still runs ``normalize_theme`` and displays the
validator's message via :meth:`set_warning`.
"""

from __future__ import annotations

import copy
from typing import Any, Iterable, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from core import animation_registry as registry
from ui.theme_kit import (
    ChipSelect, ChoiceOption, ColorField, CompactDropdown, EasingPicker,
    InlineMessage, NumberField, PropertyRow, SectionLabel, Switch, TextInput,
)

_ADVANCED_LABEL = "Advanced"


def _connect(widget: Any, handler) -> None:
    for name in ("changed", "toggled", "textChanged"):
        signal = getattr(widget, name, None)
        if signal is not None:
            signal.connect(handler)
            return


def _widget_value(widget: Any) -> Any:
    for name in ("numeric_value", "value", "text"):
        method = getattr(widget, name, None)
        if callable(method):
            try:
                return method()
            except TypeError:
                continue
    checked = getattr(widget, "isChecked", None)
    return checked() if callable(checked) else None


class ParamForm(QWidget):
    """Controls for one animation definition, driven by the registry."""

    changed = pyqtSignal(dict)

    def __init__(self, animation: Any, value: Optional[dict] = None, *,
                 palette: Any = (), exclude: Iterable[str] = (), parent=None):
        super().__init__(parent)
        if isinstance(animation, registry.AnimationSpec):
            self.spec = animation
        elif isinstance(animation, dict):
            self.spec = registry.spec_for(animation.get("type"))
        else:
            self.spec = registry.spec_for(str(animation))

        self._raw = copy.deepcopy(value) if isinstance(value, dict) else {}
        self._raw.setdefault("type", self.spec.type)
        self._palette = list(palette)
        self._exclude = {str(key) for key in exclude}
        params = [param for param in self.spec.params
                  if param.key not in self._exclude]
        self._rows: dict[str, tuple[PropertyRow, Optional[QWidget],
                                    registry.ParamSpec]] = {}
        self._show_advanced = False
        self._loading = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._layout = layout

        advanced = any(p.advanced for p in params)
        if advanced:
            toggle = Switch(False)
            toggle_row = PropertyRow(_ADVANCED_LABEL, toggle, label_width=76)
            _connect(toggle, self._on_advanced)
            layout.addWidget(toggle_row)
            self._advanced_row = toggle_row

        last_group = ""
        for param in params:
            if param.group and param.group != last_group:
                layout.addWidget(SectionLabel(param.group))
                last_group = param.group
            row, widget = self._build_row(param)
            self._rows[param.key] = (row, widget, param)
            layout.addWidget(row)

        self._note = InlineMessage("", "warning")
        self._note.hide()
        layout.addWidget(self._note)
        layout.addStretch(1)

        self._loading = False
        self._apply_visibility()

    # ── public API ──────────────────────────────────────────────────────────
    def values(self) -> dict:
        return copy.deepcopy(self._raw)

    def row_for(self, key: str) -> Optional[PropertyRow]:
        entry = self._rows.get(key)
        return entry[0] if entry else None

    def control_for(self, key: str) -> Optional[QWidget]:
        entry = self._rows.get(key)
        return entry[1] if entry else None

    def param(self, key: str) -> registry.ParamSpec:
        return self.spec.param(key)

    def set_value(self, key: str, value: Any, *, emit: bool = False) -> None:
        """Programmatic edit (tests, presets)."""
        self._write(key, value)
        self._apply_visibility()
        if emit:
            self.changed.emit(self.values())

    def set_warning(self, key: str, text: str) -> None:
        """Show the validator's message for one parameter (or the form)."""
        message = str(text or "")
        control = self.control_for(key)
        setter = getattr(control, "set_warning", None) if control else None
        if callable(setter):
            setter(message)
            self._note.hide()
        else:
            self._note.setText(message)
            self._note.setVisible(bool(message))

    # ── building ────────────────────────────────────────────────────────────
    def _build_row(self, param: registry.ParamSpec):
        widget = self._make_widget(param)
        full = param.type in ("text", "keyframes")
        row = PropertyRow(param.label, widget, label_width=76,
                          full_width=full)
        return row, widget

    def _current(self, key: str) -> Any:
        """Read a possibly-nested parameter from the raw definition."""
        if "." in key:
            root, leaf = key.split(".", 1)
            current = self._raw.get(root)
            if root == "cursor" and key == "cursor.enabled":
                return current != "none"
            if isinstance(current, dict):
                return current.get(leaf, self.spec.param(key).default)
            return self.spec.param(key).default
        return self._raw.get(key, self.spec.param(key).default)

    def _make_widget(self, param: registry.ParamSpec) -> QWidget:
        value = self._current(param.key)
        kind = param.type
        if kind in ("number", "angle", "length"):
            units = None
            unit = param.unit
            if kind == "length":
                units = [unit or "px"]
                unit = ""
            widget = NumberField(
                value if value is not None else param.default,
                minimum=param.minimum, maximum=param.maximum,
                step=param.step or 1, integer=bool(
                    param.step in (1, 50, 100) and float(
                        param.default or 0).is_integer()),
                unit=unit, units=units)
            _connect(widget, lambda *_: self._commit(param))
            return widget
        if kind == "enum":
            options = [ChoiceOption(o.value, o.label) for o in param.options]
            current = value if value in param.option_values else param.default
            if len(options) <= 8:
                widget = ChipSelect(options, current)
                _connect(widget, lambda *_: self._commit(param))
            else:
                widget = CompactDropdown(options, current)
                _connect(widget, lambda *_: self._commit(param))
            return widget
        if kind == "easing":
            widget = EasingPicker(
                value or param.default,
                presets=[o.value for o in param.options], allow_custom=True)
            _connect(widget, lambda *_: self._commit(param))
            return widget
        if kind == "bool":
            widget = Switch(bool(value))
            _connect(widget, lambda *_: self._commit(param))
            return widget
        if kind == "color":
            widget = ColorField(
                str(value or param.default), palette=self._palette,
                keywords=("currentColor",))
            _connect(widget, lambda *_: self._commit(param))
            return widget
        if kind == "text":
            widget = TextInput(str(value or ""))
            if param.max_length:
                widget.setMaxLength(int(param.max_length))
            _connect(widget, lambda *_: self._commit(param))
            return widget
        # keyframes: the timeline owns the editor (Stage 3).
        message = InlineMessage(param.help or "Edited on the timeline.", "muted")
        widget = message
        return widget

    # ── writes ──────────────────────────────────────────────────────────────
    def _commit(self, param: registry.ParamSpec) -> None:
        if self._loading:
            return
        value = _widget_value(self.control_for(param.key))
        if param.type in ("number", "angle", "length"):
            if value in (None, ""):
                value = None
            else:
                number = float(value) if isinstance(value, str) else value
                value = int(round(number)) if bool(
                    param.step in (1, 50, 100)) and float(
                        param.default or 0).is_integer() else number
        self._write(param.key, value)
        self._apply_visibility()
        self.changed.emit(self.values())

    def _write(self, key: str, value: Any) -> None:
        if key.startswith("cursor."):
            if key == "cursor.enabled":
                if not value:
                    self._raw["cursor"] = "none"
                else:
                    current = self._raw.get("cursor")
                    if not isinstance(current, dict):
                        self._raw["cursor"] = registry.cursor_defaults()
                return
            current = self._raw.get("cursor")
            if not isinstance(current, dict):
                current = registry.cursor_defaults()
            current[key.split(".", 1)[1]] = value
            self._raw["cursor"] = current
            return
        self._raw[key] = value

    # ── visibility ──────────────────────────────────────────────────────────
    def _on_advanced(self, on: bool) -> None:
        self._show_advanced = bool(on)
        self._apply_visibility()

    def _apply_visibility(self) -> None:
        for key, (row, _control, param) in self._rows.items():
            visible = True
            if param.advanced and not self._show_advanced:
                visible = False
            elif param.visible_if:
                visible = self._matches(param.visible_if)
            row.setVisible(visible)

    def _matches(self, condition: dict) -> bool:
        value = self._current(str(condition.get("key", "")))
        return value == condition.get("equals")

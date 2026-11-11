"""ui/theme_kit/split_editor.py

SplitEditor — ``animation.split`` for text-bearing blocks.

The editor composes the kit's phase cards in their light variant: a unit's
phases are absent by default and read as "inherit from parent". Nested split is
never offered; when the caller disables the editor it supplies the reason so
the widget can explain itself in a tooltip and a note.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from ui import tokens
from ui.theme_kit.animation_phase import (
    INLINE_TYPES, AnimationDefinition, AnimationPhaseCard,
)
from ui.theme_kit.base import ChoiceOption
from ui.theme_kit.chip_select import ChipSelect
from ui.theme_kit.color_field import ColorField
from ui.theme_kit.dropdown import CompactDropdown
from ui.theme_kit.number_field import NumberField
from ui.theme_kit.popup import attach_tooltip
from ui.theme_kit.property_row import PropertyRow, PropertySection
from ui.theme_kit.small import InlineMessage
from ui.theme_kit.switch import Switch as _Switch
from ui.theme_kit.slider_field import SliderField

#: phase key -> path inside a split assignment
_PHASE_PATHS = {
    "entry": ("entry",),
    "transition_in": ("transition", "in"),
}

_LOOK_FIELDS = (
    ("color", "Color"),
    ("weight", "Weight"),
    ("font_style", "Italic"),
    ("text_decoration", "Decoration"),
    ("opacity", "Opacity"),
    ("letter_spacing", "Letter spacing"),
)


class SplitEditor(QWidget):
    """Per-line / per-word split editor built from light phase cards.

    Signals
        changed(object) — the split object, or ``None`` when disabled.
        preview(object) — the split object while a control drags.
        replay(object) — one phase slot to replay: ``{"unit": "first"|"rest",
            "phase": key, "slot": value}``.

    Args
        defaults: schema defaults from the caller (``by``, ``stagger_ms``);
            used when the switch is turned on. Not validation — just the
            starting value.
        disabled_reason: when set, the whole editor is disabled and explains
            why (for example "Nested split is not supported").
    """

    changed = pyqtSignal(object)
    preview = pyqtSignal(object)
    replay = pyqtSignal(object)

    def __init__(self, value: Any = None, *,
                 library: Iterable[AnimationDefinition] = (),
                 builtins: Iterable[AnimationDefinition] = (),
                 inline_types: Iterable[str] = INLINE_TYPES,
                 palette: Iterable[tuple[str, str]] = (),
                 phases: Iterable[tuple[str, str]] = (
                     ("entry", "Entry"), ("transition_in", "Transition In")),
                 defaults: Optional[dict[str, Any]] = None,
                 disabled_reason: str = "",
                 unit_labels: tuple[str, str] = ("First unit", "Rest"),
                 parent=None):
        super().__init__(parent)
        self._library = list(library)
        self._builtins = list(builtins)
        self._inline_types = list(inline_types)
        self._palette = list(palette)
        self._phases = list(phases)
        self._defaults = dict(defaults or {})
        self._unit_labels = unit_labels
        self._disabled_reason = str(disabled_reason or "")
        self._updating = False
        self._data: dict[str, Any] = {}
        self._cards: dict[tuple[str, str], AnimationPhaseCard] = {}
        self._look_controls: dict[tuple[str, str], QWidget] = {}
        self._look_rows: dict[tuple[str, str], PropertyRow] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.SPACE_4)

        head = QWidget(self)
        head_row = QHBoxLayout(head)
        head_row.setContentsMargins(0, 0, 0, 0)
        head_row.setSpacing(tokens.SPACE_4)
        self.enabled_switch = _Switch(False, parent=head)
        self.enabled_switch.setAccessibleName("Split enabled")
        self.enabled_switch.changed.connect(self._on_enabled)
        head_row.addWidget(self.enabled_switch, 0)
        head_row.addSpacing(2)
        self.readout = InlineMessage("", role="muted")
        head_row.addWidget(self.readout, 1)
        layout.addWidget(head)

        self.note = InlineMessage("", role="muted")
        self.note.setVisible(False)
        layout.addWidget(self.note)

        self.body = QWidget(self)
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(tokens.SPACE_4)

        by_options = [ChoiceOption("line", "Line"), ChoiceOption("word", "Word")]
        self.by = ChipSelect(by_options, "line", parent=self.body)
        self.by.set_accessible_label("Split by")
        self.by.changed.connect(
            lambda value: self._set_key("by", value))
        self.stagger = NumberField(
            self._defaults.get("stagger_ms", 0), minimum=0, maximum=2000,
            integer=True, step=10, suffix="ms", label="Stagger")
        self.stagger.changed.connect(
            lambda value: self._set_key("stagger_ms", value))
        self.stagger.preview.connect(
            lambda value: self._set_key("stagger_ms", value, commit=False))
        by_host = QWidget(self.body)
        by_row = QHBoxLayout(by_host)
        by_row.setContentsMargins(0, 0, 0, 0)
        by_row.setSpacing(tokens.SPACE_4)
        by_row.addWidget(self.by, 1)
        # Keep the Line/Word chips on one row in a 240 px side column.
        self.stagger.setFixedWidth(60)
        by_row.addWidget(self.stagger, 0)
        body.addWidget(PropertyRow("By", by_host, label_width=42))

        for unit, label in (("first", unit_labels[0]),
                            ("rest", unit_labels[1])):
            body.addWidget(InlineMessage(label, role="info"))
            for phase, phase_label in self._phases:
                card = AnimationPhaseCard(
                    phase_label, None, phase=phase,
                    library=self._library, builtins=self._builtins,
                    inline_types=self._inline_types,
                    palette=self._palette,
                    off_value=None, off_label="Inherit",
                    typewriter=True, light=True, expanded=False,
                    parent=self.body)
                card.changed.connect(
                    lambda value, u=unit, p=phase: self._on_card(u, p, value,
                                                               commit=True))
                card.preview.connect(
                    lambda value, u=unit, p=phase: self._on_card(u, p, value,
                                                               commit=False))
                card.replay.connect(
                    lambda value, u=unit, p=phase: self.replay.emit(
                        {"unit": u, "phase": p, "slot": value}))
                body.addWidget(card)
                self._cards[(unit, phase)] = card

            section = PropertySection(f"Look · {label}", expanded=False,
                                      parent=self.body)
            for key, field_label in _LOOK_FIELDS:
                control = self._build_look_control(key, unit)
                row = PropertyRow(field_label, control, label_width=66)
                row.reset_requested.connect(
                    lambda u=unit, k=key: self._clear_look(u, k))
                section.add_row(row)
                self._look_controls[(unit, key)] = control
                self._look_rows[(unit, key)] = row
            body.addWidget(section)

        layout.addWidget(self.body)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Minimum)
        if self._disabled_reason:
            self.setToolTip(self._disabled_reason)
            self.note.setText(self._disabled_reason)
            self.note.setVisible(True)
            self.setEnabled(False)
        self.set_value(value)

    # ── public ──────────────────────────────────────────────────────────────
    def value(self) -> Any:
        if not self.enabled_switch.value():
            return None
        data: dict[str, Any] = {}
        for key in ("by", "stagger_ms"):
            if key in self._data:
                data[key] = self._data[key]
        for unit in ("first", "rest"):
            assignment = self._data.get(unit)
            if assignment:
                data[unit] = assignment
        look = self._data.get("look")
        if look:
            clean = {unit: spec for unit, spec in look.items() if spec}
            if clean:
                data["look"] = clean
        return data

    def set_value(self, value: Any) -> None:
        self._updating = True
        try:
            self._data = dict(value) if isinstance(value, dict) else {}
            active = isinstance(value, dict)
            self.enabled_switch.set_value(active)
            self.body.setVisible(active)
            self.by.set_value(self._data.get("by", "line"))
            self.stagger.set_value(self._data.get(
                "stagger_ms", self._defaults.get("stagger_ms", 0)))
            for (unit, phase), card in self._cards.items():
                card.set_value(self._slot_for(unit, phase))
                card.setVisible(active)
            for (unit, key), control in self._look_controls.items():
                self._sync_look(unit, key)
                control.setEnabled(active)
            self._sync_rows()
        finally:
            self._updating = False

    def set_readout(self, text: str) -> None:
        """Caller-supplied sample readout ("3 lines in current sample")."""
        self.readout.setText(str(text or ""))
        self.readout.setVisible(bool(text))

    def set_note(self, text: str, role: str = "muted") -> None:
        self.note.setText(str(text or ""))
        self.note.set_role(role)
        self.note.setVisible(bool(text))

    def set_disabled_reason(self, reason: str) -> None:
        self._disabled_reason = str(reason or "")
        self.setEnabled(not self._disabled_reason)
        attach_tooltip(self, lambda: self._disabled_reason)

    # ── look controls ───────────────────────────────────────────────────────
    def _build_look_control(self, key: str, unit: str) -> QWidget:
        def commit(value: Any, u: str = unit, k: str = key) -> None:
            self._set_look(u, k, value)

        def preview(value: Any, u: str = unit, k: str = key) -> None:
            self._set_look(u, k, value, commit=False)

        if key == "color":
            control = ColorField(
                "#ffffff", palette=self._palette,
                keywords=("currentColor", "inherit"), nullable=True,
                placeholder="Inherit")
            control.changed.connect(commit)
            control.preview.connect(preview)
            return control
        if key == "weight":
            control = NumberField(
                None, minimum=100, maximum=900, integer=True, step=100,
                nullable=True, placeholder="Inherit", label="Weight")
            control.changed.connect(commit)
            control.preview.connect(preview)
            return control
        if key == "font_style":
            control = CompactDropdown(
                [ChoiceOption(None, "Inherit", muted=True),
                 ChoiceOption("normal", "Regular"),
                 ChoiceOption("italic", "Italic")],
                None, variant="field")
            control.changed.connect(commit)
            return control
        if key == "text_decoration":
            control = CompactDropdown(
                [ChoiceOption(None, "Inherit", muted=True),
                 ChoiceOption("none", "None"),
                 ChoiceOption("underline", "Underline"),
                 ChoiceOption("line-through", "Line through")],
                None, variant="field")
            control.changed.connect(commit)
            return control
        if key == "opacity":
            control = SliderField(
                1.0, minimum=0.0, maximum=1.0, step=0.01, default=1.0,
                decimals=2, label="Look opacity")
            control.changed.connect(commit)
            control.preview.connect(preview)
            return control
        control = NumberField(
            None, minimum=-20, maximum=40, step=0.1, decimals=2,
            units=["px", "em"], nullable=True, placeholder="Inherit",
            label="Letter spacing")
        control.changed.connect(commit)
        control.preview.connect(preview)
        return control

    def _sync_look(self, unit: str, key: str) -> None:
        control = self._look_controls[(unit, key)]
        look = self._data.get("look", {}).get(unit, {})
        value = look.get(key)
        if key == "opacity":
            control.set_value(1.0 if value is None else value)
        else:
            control.set_value(value)
        self._look_rows[(unit, key)].set_changed(value is not None)

    def _set_look(self, unit: str, key: str, value: Any, *,
                  commit: bool = True) -> None:
        if self._updating:
            return
        look = self._data.setdefault("look", {})
        spec = look.setdefault(unit, {})
        if value is None or (key == "opacity" and value == 1.0):
            spec.pop(key, None)
        else:
            spec[key] = value
        if not spec:
            look.pop(unit, None)
        if not look:
            self._data.pop("look", None)
        self._sync_rows()
        if commit:
            self.changed.emit(self.value())
        else:
            self.preview.emit(self.value())

    def _clear_look(self, unit: str, key: str) -> None:
        self._set_look(unit, key, None)

    def _sync_rows(self) -> None:
        look = self._data.get("look", {})
        for (unit, key), row in self._look_rows.items():
            row.set_changed(look.get(unit, {}).get(key) is not None)

    # ── assignment plumbing ─────────────────────────────────────────────────
    def _slot_for(self, unit: str, phase: str) -> Any:
        path = _PHASE_PATHS.get(phase)
        node: Any = self._data.get(unit)
        if not path or not isinstance(node, dict):
            return None
        for key in path:
            if not isinstance(node, dict):
                return None
            node = node.get(key)
        return node

    def _on_card(self, unit: str, phase: str, value: Any, *,
                 commit: bool) -> None:
        if self._updating:
            return
        path = _PHASE_PATHS.get(phase)
        assignment = self._data.setdefault(unit, {})
        node = assignment
        for key in path[:-1]:
            node = node.setdefault(key, {})
            if not isinstance(node, dict):
                node = {}
                assignment[path[0]] = node
        leaf = path[-1]
        if value is None or (isinstance(value, str) and value == "none"):
            node.pop(leaf, None)
        else:
            node[leaf] = value
        self._prune(unit)
        if commit:
            self.changed.emit(self.value())
        else:
            self.preview.emit(self.value())

    def _prune(self, unit: str) -> None:
        assignment = self._data.get(unit)
        if not isinstance(assignment, dict):
            return
        transition = assignment.get("transition")
        if isinstance(transition, dict):
            transition = {key: value for key, value in transition.items()
                          if value is not None}
            if transition:
                assignment["transition"] = transition
            else:
                assignment.pop("transition", None)
        assignment = {key: value for key, value in assignment.items()
                      if value not in (None, {})}
        if assignment:
            self._data[unit] = assignment
        else:
            self._data.pop(unit, None)

    def _set_key(self, key: str, value: Any, *, commit: bool = True) -> None:
        if self._updating:
            return
        if value in (None, ""):
            self._data.pop(key, None)
        else:
            self._data[key] = value
        if commit:
            self.changed.emit(self.value())
        else:
            self.preview.emit(self.value())

    def _on_enabled(self, checked: bool) -> None:
        if self._updating:
            return
        if checked:
            self._data.setdefault("by", "line")
            self._data.setdefault(
                "stagger_ms", self._defaults.get("stagger_ms", 0))
        self.body.setVisible(checked)
        for card in self._cards.values():
            card.setVisible(checked)
        for control in self._look_controls.values():
            control.setEnabled(checked)
        if checked:
            self.by.set_value(self._data.get("by", "line"))
            self.stagger.set_value(self._data.get(
                "stagger_ms", self._defaults.get("stagger_ms", 0)))
        self.changed.emit(self.value())


__all__ = ["SplitEditor"]

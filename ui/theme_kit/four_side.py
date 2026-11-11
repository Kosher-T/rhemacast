"""ui/theme_kit/four_side.py

FourSideField — a linked/unlinked four-side numeric control.

The caller owns the mapping to its data shape. With ``base_key=None`` the
widget emits ``{"top": ..., "right": ..., "bottom": ..., "left": ...}``. With
a ``base_key`` (for example ``"padding"``) it emits the schema-friendly form:
the base value plus only the side overrides that differ (``padding_right``).
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QWidget,
)

from ui import tokens
from ui.theme_kit.number_field import NumberField
from ui.theme_kit.popup import attach_tooltip
from ui.theme_kit.small import IconButton

_SIDES = ("top", "right", "bottom", "left")
_SIDE_LABELS = {"top": "T", "right": "R", "bottom": "B", "left": "L"}


class FourSideField(QWidget):
    """Four numeric fields with an optional link toggle.

    Signals
        changed(object) — committed value (see module docstring).
        preview(object) — live value while scrubbing/dragging.
    """

    changed = pyqtSignal(object)
    preview = pyqtSignal(object)

    def __init__(self, value: Any = 0, *,
                 base_key: Optional[str] = "padding",
                 side_keys: Iterable[str] = _SIDES,
                 side_template: str = "{base}_{side}",
                 linked: bool = True, unit: str = "px",
                 units: Optional[Iterable[str]] = None,
                 minimum: Optional[float] = 0,
                 maximum: Optional[float] = 400,
                 step: float = 1, integer: bool = True,
                 decimals: Optional[int] = None,
                 nullable: bool = False,
                 keywords: Iterable[str] = (),
                 side_labels: Optional[dict[str, str]] = None,
                 parent=None):
        super().__init__(parent)
        self._sides = tuple(side_keys)
        self._base_key = base_key
        self._side_template = side_template
        self._updating = False
        self._fields: dict[str, NumberField] = {}
        self._labels = dict(_SIDE_LABELS)
        if side_labels:
            self._labels.update(side_labels)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.SPACE_4)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(tokens.SPACE_4)
        grid.setVerticalSpacing(tokens.SPACE_4)
        self._grid = grid

        for index, side in enumerate(self._sides):
            row, column = divmod(index, 2)
            cell = QWidget(self)
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(2)
            label = QLabel(self._labels.get(side, side[:1].upper()), cell)
            label.setFixedWidth(10)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(
                f"color: {tokens.TEXT_MUTED};"
                f"font-size: 10px; font-weight: {tokens.WEIGHT_SEMIBOLD};"
                "background: transparent;")
            cell_layout.addWidget(label, 0)
            field = NumberField(
                0, minimum=minimum, maximum=maximum, step=step,
                integer=integer, decimals=decimals, unit=unit,
                units=units, keywords=keywords, nullable=nullable,
                # At 240 px the side cells leave ~30 px of text beside the
                # unit selector; "Not set" elides there, so use the short
                # form (same reason as the keyframe track).
                placeholder="Unset",
                label=f"{side.title()} side")
            field.changed.connect(
                lambda _value, s=side: self._on_field_changed(s, commit=True))
            field.preview.connect(
                lambda _value, s=side: self._on_field_changed(s,
                                                              commit=False))
            cell_layout.addWidget(field, 1)
            grid.addWidget(cell, row, column)
            self._fields[side] = field
            attach_tooltip(label, f"{side.title()} side")

        self._link = IconButton(
            glyph="link", checkable=True, checked=bool(linked),
            tooltip="Link all sides" if linked else "Unlink sides",
            accessible_name="Link sides", compact=False, parent=self)
        self._link.changed.connect(self._on_link_changed)
        layout.addLayout(grid, 1)
        layout.addWidget(self._link, 0, Qt.AlignmentFlag.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Fixed)
        self.set_value(value)

    # ── public ──────────────────────────────────────────────────────────────
    def linked(self) -> bool:
        return self._link.isChecked()

    def set_linked(self, linked: bool) -> None:
        self._link.blockSignals(True)
        self._link.setChecked(bool(linked))
        self._link.blockSignals(False)
        self._link.update()
        if linked:
            self._sync_others(self._sides[0])

    def value(self) -> dict[str, Any]:
        values = {side: self._fields[side].value() for side in self._sides}
        if not self._base_key:
            return values
        base = values.get(self._sides[0], 0)
        result: dict[str, Any] = {self._base_key: base}
        for side in self._sides[1:]:
            side_key = self._side_template.format(
                base=self._base_key, side=side)
            if values.get(side) != base:
                result[side_key] = values[side]
        return result

    def set_value(self, value: Any, *, emit: bool = False) -> None:
        self._updating = True
        try:
            if isinstance(value, dict):
                base = value.get(self._base_key) if self._base_key else None
                for side in self._sides:
                    side_key = (self._side_template.format(
                        base=self._base_key, side=side)
                        if self._base_key else side)
                    raw = value.get(side_key, base)
                    self._fields[side].set_value(
                        raw if raw is not None else base)
            else:
                for side in self._sides:
                    self._fields[side].set_value(value)
        finally:
            self._updating = False
        if emit:
            self.changed.emit(self.value())

    def set_range(self, minimum: Optional[float],
                  maximum: Optional[float]) -> None:
        for field in self._fields.values():
            field.set_range(minimum, maximum, emit=False)

    def set_warning(self, text: str) -> None:
        for field in self._fields.values():
            field.set_warning(text)

    # ── behaviour ───────────────────────────────────────────────────────────
    def _on_link_changed(self, linked: bool) -> None:
        self._link.setProperty(
            "_rc_kit_tooltip",
            "Unlink sides" if linked else "Link all sides")
        if linked:
            self._sync_others(self._sides[0])
        self.changed.emit(self.value())

    def _sync_others(self, side: str) -> None:
        value = self._fields[side].value()
        self._updating = True
        try:
            for other, field in self._fields.items():
                if other != side:
                    field.set_value(value)
        finally:
            self._updating = False

    def _on_field_changed(self, side: str, *, commit: bool) -> None:
        if self._updating:
            return
        if self.linked():
            self._sync_others(side)
        if commit:
            self.changed.emit(self.value())
        else:
            self.preview.emit(self.value())


__all__ = ["FourSideField"]

"""ui/theme_kit/param_group.py

ParamGroup — a parameter row with its subparameters tucked underneath.

Three tiers, defined in ``docs/PANEL_ORGANIZATION.md``:

    Tier 1  PropertySection   group heading (a label organizer, not a value)
    Tier 2  PropertyRow       parameter row, always visible
    Tier 3  ParamGroup body   subparameters, revealed by the row's chevron

A control is a subparameter when it has no meaning without another control or
only refines it: ``Min``/``Max`` refine ``Width``, ``Fill``/``Pad`` refine
``Border``. Everything else is a parameter and stays a plain row.

The group owns no value, range or validation: it moves rows in and out of the
layout and reports open/closed changes so the panel can remember them.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from ui import tokens
from ui.theme_kit.panel_layout import GUTTER, TIER_STEP
from ui.theme_kit.property_row import PropertyRow

#: Indent applied to the subparameter body: exactly one tier step, so a Tier-3
#: label lands at ``panel_layout.label_x(3)``.
SUB_INDENT = TIER_STEP

#: Where the nesting guide hangs: the chevron's centre, so the line looks like
#: the chevron's continuation rather than a stray rule beside the labels.
GUIDE_X = GUTTER // 2


class _SubBody(QWidget):
    """Body that paints the nesting guide line in its left margin."""

    def __init__(self, guide_x: int, parent=None):
        super().__init__(parent)
        self._guide_x = int(guide_x)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        x = self._guide_x
        if 0 <= x < self.width() and self.height() > 0:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.fillRect(x, 2, 1, max(0, self.height() - 4),
                             QColor(tokens.BORDER_HAIRLINE))
        painter.end()


class ParamGroup(QWidget):
    """A Tier-2 parameter row plus its Tier-3 subparameters.

    ``state_key`` identifies the group in the panel's saved open state
    (``ui.theme_kit.panel_state``); the group itself never writes settings.
    """

    expanded_changed = pyqtSignal(str, bool)

    def __init__(self, param_row: PropertyRow, *, state_key: str = "",
                 expanded: bool = False, indent: int = SUB_INDENT,
                 parent=None):
        super().__init__(parent)
        self.state_key = str(state_key)
        self.param_row = param_row
        self._expanded = bool(expanded)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(param_row)

        self.body = _SubBody(GUIDE_X, self)
        self._body_layout = QVBoxLayout(self.body)
        self._body_layout.setContentsMargins(int(indent), 0, 0, 0)
        self._body_layout.setSpacing(tokens.SPACE_4)
        layout.addWidget(self.body)

        param_row.set_disclosure(True, self._expanded)
        param_row.disclosure_toggled.connect(self._on_disclosure)
        self.body.setVisible(self._expanded)

    # ── contents ────────────────────────────────────────────────────────────
    def add_row(self, row: QWidget) -> QWidget:
        self._body_layout.addWidget(row)
        return row

    def add_widget(self, widget: QWidget) -> QWidget:
        self._body_layout.addWidget(widget)
        return widget

    def add_layout(self, layout) -> None:
        self._body_layout.addLayout(layout)

    def sub_rows(self) -> list[QWidget]:
        return [self._body_layout.itemAt(i).widget()
                for i in range(self._body_layout.count())
                if self._body_layout.itemAt(i).widget() is not None]

    # ── open / closed ───────────────────────────────────────────────────────
    def _on_disclosure(self, expanded: bool) -> None:
        self._set_expanded(bool(expanded), notify=True)

    def set_expanded(self, expanded: bool, *, notify: bool = False) -> None:
        self._set_expanded(bool(expanded), notify=notify)

    def _set_expanded(self, expanded: bool, *, notify: bool) -> None:
        self._expanded = bool(expanded)
        self.body.setVisible(self._expanded)
        self.param_row.set_disclosure_expanded(self._expanded)
        if notify:
            self.expanded_changed.emit(self.state_key, self._expanded)

    def is_expanded(self) -> bool:
        return self._expanded

    def param(self) -> PropertyRow:
        return self.param_row


__all__ = ["GUIDE_X", "ParamGroup", "SUB_INDENT"]

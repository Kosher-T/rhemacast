"""
ui/widgets/theme_designer/theme_combo.py

The Theme Designer's selector: option text is the theme **label**, option
value is the permanent **ID** (file name stem).

The closed combo shows ``label`` (plus `` (id)`` when another theme resolves
to the same label). The popup rows paint the same text with the ID suffix in
muted text and the theme's description as a muted second line, truncated to
one line. A stale entry (its file stopped parsing) carries a small warning
dot; the last good entry stays selectable.

The combo is populated from :class:`core.theme_catalog.ThemeCatalog`; it
never reads the filesystem itself.
"""

from __future__ import annotations

from typing import Iterable, Optional

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import QComboBox, QStyle, QStyledItemDelegate

from core.theme_catalog import ThemeEntry
from ui import tokens
from ui.popups import install_combo

#: Item data roles the delegate paints apart from the option text.
ID_ROLE = Qt.ItemDataRole.UserRole
SUFFIX_ROLE = int(Qt.ItemDataRole.UserRole) + 1
DESCRIPTION_ROLE = int(Qt.ItemDataRole.UserRole) + 2
WARNING_ROLE = int(Qt.ItemDataRole.UserRole) + 3
#: The bare label, without the duplicate-ID suffix that the closed combo shows.
LABEL_ROLE = int(Qt.ItemDataRole.UserRole) + 4

#: Description lines never widen the popup past this, keeping one long
#: description from making every row unreadably wide.
_DESCRIPTION_MAX_WIDTH = 420
#: Reserved lane for the stale-file warning dot.
_WARNING_LANE = 12


class ThemeRowDelegate(QStyledItemDelegate):
    """Two-line dropdown row: label (+ muted ID), then muted description."""

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        enabled = bool(option.state & QStyle.StateFlag.State_Enabled)

        surface = tokens.BG_FIELD
        if selected:
            surface = tokens.BG_CARD_SELECTED
        elif hovered:
            surface = tokens.BG_CARD_HOVER
        painter.fillRect(rect, QColor(surface))
        if selected:
            painter.fillRect(
                QRectF(rect.left(), rect.top(), tokens.SELECTED_BAR_WIDTH,
                       rect.height()),
                QColor(tokens.ACCENT))

        label = str(index.data(LABEL_ROLE)
                    or index.data(Qt.ItemDataRole.DisplayRole) or "")
        suffix = str(index.data(SUFFIX_ROLE) or "")
        description = str(index.data(DESCRIPTION_ROLE) or "")
        warning = str(index.data(WARNING_ROLE) or "")

        pad_y = tokens.SPACE_4
        text_left = rect.left() + tokens.SELECTED_BAR_WIDTH + tokens.SPACE_8
        text_right = rect.right() - tokens.SPACE_8
        if warning:
            text_right -= _WARNING_LANE

        label_font = QFont(option.font)
        label_font.setWeight(tokens.WEIGHT_SEMIBOLD)
        suffix_font = QFont(option.font)
        suffix_font.setWeight(tokens.WEIGHT_REGULAR)
        desc_font = QFont(option.font)
        desc_font.setPointSizeF(max(7.0, option.font.pointSizeF() - 1))

        label_metrics = QFontMetrics(label_font)
        suffix_metrics = QFontMetrics(suffix_font)
        desc_metrics = QFontMetrics(desc_font)

        label_height = label_metrics.height()
        desc_height = desc_metrics.height() if description else 0
        content_height = label_height + (
            2 + desc_height if description else 0)
        top = rect.top() + max(pad_y, (rect.height() - content_height) // 2)

        available = max(0, text_right - text_left)
        suffix_width = suffix_metrics.horizontalAdvance(suffix) if suffix else 0
        label_width = max(0, available - suffix_width)
        label_text = label_metrics.elidedText(
            label, Qt.TextElideMode.ElideRight, label_width)

        painter.setFont(label_font)
        painter.setPen(QColor(tokens.TEXT_PRIMARY if enabled
                              else tokens.TEXT_MUTED))
        painter.drawText(
            text_left, top, label_width, label_height,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            label_text)

        if suffix:
            painter.setFont(suffix_font)
            painter.setPen(QColor(tokens.TEXT_MUTED))
            painter.drawText(
                text_left + label_metrics.horizontalAdvance(label_text), top,
                suffix_width, label_height,
                int(Qt.AlignmentFlag.AlignLeft
                    | Qt.AlignmentFlag.AlignVCenter),
                suffix)

        if description:
            painter.setFont(desc_font)
            painter.setPen(QColor(tokens.TEXT_MUTED))
            painter.drawText(
                text_left, top + label_height + 2,
                available, desc_height,
                int(Qt.AlignmentFlag.AlignLeft
                    | Qt.AlignmentFlag.AlignVCenter),
                desc_metrics.elidedText(
                    description, Qt.TextElideMode.ElideRight, available))

        if warning:
            dot = 6
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tokens.WARNING))
            painter.drawEllipse(QRectF(
                text_right + 3, rect.center().y() - dot / 2, dot, dot))

        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        label = str(index.data(LABEL_ROLE)
                    or index.data(Qt.ItemDataRole.DisplayRole) or "")
        suffix = str(index.data(SUFFIX_ROLE) or "")
        description = str(index.data(DESCRIPTION_ROLE) or "")

        label_font = QFont(option.font)
        label_font.setWeight(tokens.WEIGHT_SEMIBOLD)
        label_metrics = QFontMetrics(label_font)
        width = label_metrics.horizontalAdvance(label)
        width += label_metrics.horizontalAdvance(suffix)

        height = label_metrics.height()
        if description:
            desc_font = QFont(option.font)
            desc_font.setPointSizeF(max(7.0, option.font.pointSizeF() - 1))
            desc_metrics = QFontMetrics(desc_font)
            width = max(width, min(
                desc_metrics.horizontalAdvance(description),
                _DESCRIPTION_MAX_WIDTH))
            height += 2 + desc_metrics.height()

        width += (tokens.SELECTED_BAR_WIDTH + 2 * tokens.SPACE_8
                  + tokens.SPACE_16 + _WARNING_LANE)
        height += 2 * tokens.SPACE_4
        return QSize(width,
                     max(tokens.BUTTON_HEIGHT, height))


class ThemeSelector(QComboBox):
    """Catalog-backed theme picker: labels on screen, IDs as values."""

    def __init__(self, parent=None):
        super().__init__(parent)
        install_combo(self)
        view = self.view()
        if view is not None:
            view.setItemDelegate(ThemeRowDelegate(view))
        self.setMaxVisibleItems(16)
        self.setAccessibleName("Theme")

    # ── population ───────────────────────────────────────────────────────────

    def set_entries(self, entries: Iterable[ThemeEntry],
                    selected_id: str = "") -> str:
        """Rebuild the options in catalog order, keeping ``selected_id``.

        Selection is restored by ID, so re-sorting or re-labelling never moves
        the operator to a different theme. Returns the ID actually selected
        ("" when the list is empty).
        """
        entries = list(entries)
        self.blockSignals(True)
        try:
            self.clear()
            for entry in entries:
                self.addItem(entry.label + entry.suffix, entry.id)
                row = self.count() - 1
                self.setItemData(row, entry.label, LABEL_ROLE)
                self.setItemData(row, entry.suffix, SUFFIX_ROLE)
                self.setItemData(row, entry.description, DESCRIPTION_ROLE)
                self.setItemData(
                    row, entry.warning if entry.stale else "", WARNING_ROLE)
                self.setItemData(row, self._tooltip(entry),
                                 Qt.ItemDataRole.ToolTipRole)
            if not entries:
                self.addItem("No themes found", "")
                self.setEnabled(False)
                self.setCurrentIndex(0)
                return ""
            self.setEnabled(True)
            index = self.findData(selected_id) if selected_id else -1
            self.setCurrentIndex(index if index >= 0 else 0)
            return str(self.currentData() or "")
        finally:
            self.blockSignals(False)

    def current_id(self) -> str:
        data = self.currentData()
        return str(data) if data else ""

    def current_warning(self) -> str:
        index = self.currentIndex()
        if index < 0:
            return ""
        return str(self.itemData(index, WARNING_ROLE) or "")

    # ── internals ────────────────────────────────────────────────────────────

    @staticmethod
    def _tooltip(entry: ThemeEntry) -> str:
        lines = [entry.label, f"ID: {entry.id}"]
        if entry.description:
            lines.append(entry.description)
        if entry.stale:
            lines.append(
                "This file is not valid JSON right now. Showing the last "
                "good version.")
        return "\n".join(lines)

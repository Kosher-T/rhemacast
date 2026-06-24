"""
ui/panels/queue_panel.py

Operator review queue: shows auto-detected verse matches from Thread 3.
Show → fires broadcast_display() + Stage 3 DB log.
Reject → discards and frees memory.
Limited to 50 visible items (virtual scrolling).
"""

import asyncio
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal

from ui.styles import (
    PANEL_HEADER_STYLE, PANEL_HEADER_LABEL_STYLE, PANEL_BODY_STYLE,
    QUEUE_ITEM_STYLE, SHOW_BTN_STYLE, REJECT_BTN_STYLE,
    CYAN_400, SLATE_300, SLATE_500, SLATE_600, WHITE, BORDER_SUBTLE
)
from core.queues import db_write_queue

logger = logging.getLogger(__name__)

MAX_VISIBLE_ITEMS = 50


class QueueItemWidget(QFrame):
    """A single verse match in the operator review queue."""

    show_clicked = pyqtSignal(dict)
    reject_clicked = pyqtSignal(dict)

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self.data = data
        self.setStyleSheet(QUEUE_ITEM_STYLE)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        # Confidence dot
        conf = data.get("confidence", 0)
        dot_color = CYAN_400 if conf >= 85 else SLATE_600
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {dot_color}; font-size: 8px;")
        dot.setFixedWidth(12)
        layout.addWidget(dot)

        # Verse ref
        ref_text = f"{data.get('book', '')} {data.get('chapter', '')}:{data.get('verse_num', '')}"
        ref_label = QLabel(ref_text)
        ref_label.setStyleSheet(f"color: {SLATE_300}; font-size: 11px; font-weight: 700;")
        ref_label.setToolTip(data.get("text", ""))
        layout.addWidget(ref_label)

        layout.addStretch()

        # Confidence %
        conf_label = QLabel(f"{conf:.0f}%")
        conf_label.setStyleSheet(f"color: {SLATE_500}; font-size: 9px; font-weight: 600;")
        conf_label.setToolTip("Confidence threshold: verses above this go to the review queue")
        layout.addWidget(conf_label)

        # Show
        show_btn = QPushButton("Show")
        show_btn.setStyleSheet(SHOW_BTN_STYLE)
        show_btn.setToolTip("Broadcast this verse to the live display output")
        show_btn.setFixedWidth(50)
        show_btn.clicked.connect(lambda: self.show_clicked.emit(self.data))
        layout.addWidget(show_btn)

        # Reject
        reject_btn = QPushButton("✕")
        reject_btn.setStyleSheet(REJECT_BTN_STYLE)
        reject_btn.setToolTip("Discard this suggestion from the queue")
        reject_btn.setFixedWidth(28)
        reject_btn.clicked.connect(lambda: self.reject_clicked.emit(self.data))
        layout.addWidget(reject_btn)


class QueuePanel(QWidget):
    """Operator review queue panel."""

    # Emitted when the operator clicks "Show" on a verse
    display_requested = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(PANEL_BODY_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setStyleSheet(PANEL_HEADER_STYLE)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 6, 12, 6)

        # Sub-tabs
        queue_label = QLabel("QUEUE")
        queue_label.setStyleSheet(f"""
            color: {CYAN_400};
            font-size: 10px; font-weight: 700;
            background: rgba(34, 211, 238, 0.1);
            padding: 4px 12px;
            border-radius: 3px;
        """)
        header_layout.addWidget(queue_label)
        header_layout.addStretch()

        # Item count
        self.count_label = QLabel("0")
        self.count_label.setStyleSheet(f"color: {SLATE_500}; font-size: 9px; font-weight: 600;")
        header_layout.addWidget(self.count_label)

        layout.addWidget(header)

        # List
        self.list_widget = QListWidget()
        self.list_widget.setSpacing(4)
        self.list_widget.setStyleSheet("QListWidget { padding: 6px; }")
        layout.addWidget(self.list_widget)

    def add_item(self, data: dict):
        """Add a verse match to the review queue."""
        # Enforce 50-item cap
        while self.list_widget.count() >= MAX_VISIBLE_ITEMS:
            self.list_widget.takeItem(self.list_widget.count() - 1)

        widget = QueueItemWidget(data)
        widget.show_clicked.connect(self._on_show)
        widget.reject_clicked.connect(self._on_reject)

        item = QListWidgetItem()
        item.setSizeHint(widget.sizeHint())
        item.setData(Qt.ItemDataRole.UserRole, data)

        # High priority items go to the top
        if data.get("priority") == "high":
            self.list_widget.insertItem(0, item)
        else:
            self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, widget)

        self.count_label.setText(str(self.list_widget.count()))

    def _on_show(self, data: dict):
        """Operator approved the verse for broadcast."""
        import time

        # Emit display signal
        self.display_requested.emit(data)

        # Stage 3 DB log
        db_write_queue.put({
            "type": "display_event",
            "payload": {
                "action": "operator_approved",
                "ref": f"[{data.get('version','')}] {data.get('book','')} {data.get('chapter','')}:{data.get('verse_num','')}",
                "confidence": data.get("confidence", 0),
                "timestamp_ms": int(time.time() * 1000)
            }
        })

        # Remove from list
        self._remove_item_by_data(data)

    def _on_reject(self, data: dict):
        """Operator rejected the verse."""
        self._remove_item_by_data(data)

    def _remove_item_by_data(self, data: dict):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == data:
                widget = self.list_widget.itemWidget(item)
                self.list_widget.takeItem(i)
                if widget:
                    widget.deleteLater()
                break
        self.count_label.setText(str(self.list_widget.count()))

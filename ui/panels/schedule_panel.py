"""
ui/panels/schedule_panel.py

Left panel: Drag-and-drop ordered verse list for the service schedule.
Accepts drops from the Bible browser and the operator review queue.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QHBoxLayout, QFrame, QAbstractItemView
)
from PyQt6.QtCore import Qt, QMimeData
from PyQt6.QtGui import QDrag

from ui.styles import (
    PANEL_HEADER_STYLE, PANEL_HEADER_LABEL_STYLE,
    PANEL_BODY_STYLE, SLATE_400, SLATE_500, WHITE, BORDER_SUBTLE
)


class ScheduleItem(QFrame):
    """A single draggable schedule row."""

    def __init__(self, ref: str, translation: str = "", text: str = "", theme: str = "default", parent=None):
        super().__init__(parent)
        self.ref = ref
        self.translation = translation
        self.text = text
        self.theme = theme

        self.setStyleSheet(f"""
            QFrame {{
                background: rgba(30, 41, 59, 150); /* bg-slate-800/60 */
                border: 1px solid rgba(255, 255, 255, 12); /* border-white/5 */
                border-radius: 6px;
                padding: 12px;
            }}
            QFrame:hover {{
                border-color: rgba(59, 130, 246, 75); /* hover:border-blue-500/30 */
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        ref_label = QLabel(ref)
        ref_label.setStyleSheet(f"color: {WHITE}; font-size: 12px; font-weight: 600;")

        time_label = QLabel("")
        time_label.setStyleSheet(f"color: {SLATE_500}; font-size: 9px;")

        layout.addWidget(ref_label)
        layout.addStretch()
        layout.addWidget(time_label)


class SchedulePanel(QWidget):
    """Schedule panel with drag-and-drop reordering."""

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

        title = QLabel("Schedule")
        title.setStyleSheet(PANEL_HEADER_LABEL_STYLE)
        header_layout.addWidget(title)
        header_layout.addStretch()

        layout.addWidget(header)

        # List
        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget.setAcceptDrops(True)
        self.list_widget.setSpacing(4)
        self.list_widget.setStyleSheet("QListWidget { padding: 8px; }")
        layout.addWidget(self.list_widget)

    def add_item(self, ref: str, translation: str = "", text: str = "", theme: str = "default"):
        """Append a verse to the schedule."""
        item_widget = ScheduleItem(ref, translation, text, theme)
        list_item = QListWidgetItem()
        list_item.setSizeHint(item_widget.sizeHint())
        list_item.setData(Qt.ItemDataRole.UserRole, {
            "ref": ref, "translation": translation, "text": text, "theme": theme
        })
        self.list_widget.addItem(list_item)
        self.list_widget.setItemWidget(list_item, item_widget)

    def get_schedule(self) -> list:
        """Return all schedule items as dicts."""
        items = []
        for i in range(self.list_widget.count()):
            data = self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            if data:
                items.append(data)
        return items

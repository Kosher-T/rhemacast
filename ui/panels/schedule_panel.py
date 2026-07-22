"""
ui/panels/schedule_panel.py

Ordered verse list for the service schedule.
Programmatic add via Alt+click in the browser panel.

Interactions:
  - Single-click → preview verse
  - Double-click → push verse to live
  - Right-click → context menu (Rename / Themes / Delete)
  - Alt+Right-click → themes-only picker
  - Delete key → delete selected item(s)
  - Internal reorder via drag-and-drop
  - Multi-select via Ctrl/Shift click for batch operations
"""

import json
import logging
import os
import time
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QFrame, QAbstractItemView, QMenu, QLineEdit, QSizePolicy, QApplication,
    QFileDialog, QMessageBox, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEvent

from ui.styles import (
    PANEL_HEADER_STYLE, PANEL_HEADER_LABEL_STYLE,
    PANEL_BODY_STYLE, SLATE_400, SLATE_500, WHITE, BORDER_SUBTLE, BLUE_500
)

logger = logging.getLogger(__name__)

_DOUBLE_CLICK_THRESHOLD_MS = 400

# Schedules directory
_SCHEDULES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "schedules"

# Small button style for schedule header
_header_btn_style = f"""
    QPushButton {{
        background: transparent;
        color: {SLATE_400};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 3px;
        padding: 2px 6px;
        font-size: 11px;
    }}
    QPushButton:hover {{
        background: rgba(255, 255, 255, 0.05);
        color: {WHITE};
    }}
"""


class ScheduleItem(QFrame):
    """A single schedule row — displays reference and translation."""

    clicked = pyqtSignal()
    double_clicked = pyqtSignal()
    delete_requested = pyqtSignal()
    rename_requested = pyqtSignal()
    theme_change_requested = pyqtSignal(str)
    renamed = pyqtSignal()  # Emitted when rename is confirmed
    delete_requested = pyqtSignal()

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._data = data
        self._editing = False

        ref = data.get("ref", "")
        translation = data.get("translation", "")
        from core.bible_service import get_display_name
        display_name = get_display_name(translation) if translation else ""
        display = f"[{display_name}] {ref}" if display_name else ref

        # Use property-based styling for selected state
        self.setProperty("selected", False)
        self.setStyleSheet(f"""
            QFrame {{
                background: rgba(30, 41, 59, 150);
                border: 1px solid rgba(255, 255, 255, 12);
                border-radius: 6px;
                padding: 10px;
            }}
            QFrame[selected="true"] {{
                background: rgba(59, 130, 246, 100);
                border-color: {BLUE_500};
            }}
            QFrame:hover {{
                border-color: rgba(59, 130, 246, 75);
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        self._ref_label = QLabel(display)
        self._ref_label.setStyleSheet(f"color: {WHITE}; font-size: 12px; font-weight: 600; background: transparent;")
        layout.addWidget(self._ref_label)
        layout.addStretch()

        theme_label = self._theme_display_name(data.get("theme", "default"))
        self._theme_label = QLabel(theme_label)
        self._theme_label.setStyleSheet(f"color: {SLATE_500}; font-size: 9px; background: transparent;")
        layout.addWidget(self._theme_label)

        self._edit = QLineEdit()
        self._edit.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(0, 0, 0, 80);
                color: {WHITE};
                border: 1px solid rgba(59, 130, 246, 100);
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 12px;
            }}
        """)
        self._edit.setVisible(False)
        self._edit.returnPressed.connect(self._finish_rename)
        self._edit.editingFinished.connect(self._finish_rename)
        layout.addWidget(self._edit)

    @staticmethod
    def _theme_display_name(theme_name: str) -> str:
        """Return the human-readable label for a theme, falling back to the name."""
        from core.theme_loader import get_theme
        theme = get_theme(theme_name)
        if theme:
            return theme.get("label", theme.get("name", theme_name))
        return theme_name

    @property
    def data(self) -> dict:
        return self._data

    def set_name(self, name: str):
        self._data["name"] = name
        self._ref_label.setText(name)

    def set_theme(self, theme: str):
        self._data["theme"] = theme
        self._theme_label.setText(self._theme_display_name(theme))

    def set_selected(self, selected: bool):
        """Update the selected visual state."""
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def start_rename(self):
        self._editing = True
        current = self._data.get("name", self._data.get("ref", ""))
        self._edit.setText(current)
        self._ref_label.setVisible(False)
        self._edit.setVisible(True)
        self._edit.setFocus()
        self._edit.selectAll()

    def _finish_rename(self):
        if not self._editing:
            return
        self._editing = False
        new_name = self._edit.text().strip()
        if new_name:
            self._data["name"] = new_name
            self._ref_label.setText(new_name)
        self._edit.setVisible(False)
        self._ref_label.setVisible(True)
        self.renamed.emit()

    def mousePressEvent(self, event):
        if self._editing:
            super().mousePressEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            # Don't consume - let QListWidget handle selection naturally
            event.ignore()
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()

    def contextMenuEvent(self, event):
        """Handle right-click: regular menu with Delete. Alt+Right-click handled by SchedulePanel."""
        # Check for Alt modifier — if pressed, forward to SchedulePanel for themes menu
        if event.modifiers() & Qt.KeyboardModifier.AltModifier:
            # Find the parent SchedulePanel
            parent = self.parent()
            while parent and not isinstance(parent, QListWidget):
                parent = parent.parent()
            if parent:
                schedule_panel = parent.parent()
                while schedule_panel and not hasattr(schedule_panel, '_show_themes_menu_for_selection'):
                    schedule_panel = schedule_panel.parent()
                if schedule_panel and hasattr(schedule_panel, '_show_themes_menu_for_selection'):
                    # Select this item if not already selected
                    for i in range(parent.count()):
                        list_item = parent.item(i)
                        if parent.itemWidget(list_item) is self:
                            if not list_item.isSelected():
                                parent.clearSelection()
                                list_item.setSelected(True)
                            break
                    schedule_panel._show_themes_menu_for_selection(event.globalPos())
            return
            
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: rgba(30, 41, 59, 240);
                color: {WHITE};
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background: rgba(59, 130, 246, 60);
            }}
        """)

        rename_action = menu.addAction("Rename")
        rename_action.triggered.connect(self.rename_requested.emit)

        self._add_themes_submenu(menu)

        menu.addSeparator()

        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(self.delete_requested.emit)

        menu.exec(event.globalPos())

    def _add_themes_submenu(self, parent_menu: QMenu):
        """Populate a Themes submenu with human-readable labels."""
        themes_menu = parent_menu.addMenu("Themes")
        from core.theme_loader import get_all_themes
        current_theme = self._data.get("theme", "default")
        for name, theme_data in sorted(get_all_themes().items()):
            label = theme_data.get("label", theme_data.get("name", name))
            action = themes_menu.addAction(label)
            if name == current_theme:
                action.setCheckable(True)
                action.setChecked(True)
            action.triggered.connect(lambda checked, n=name: self.theme_change_requested.emit(n))


class SchedulePanel(QWidget):
    """Schedule panel with drag-and-drop reordering."""

    item_clicked = pyqtSignal(dict)
    item_double_clicked = pyqtSignal(dict)
    item_theme_changed = pyqtSignal(str, str)
    item_renamed = pyqtSignal(str, str)
    items_deleted = pyqtSignal(list)
    schedule_modified = pyqtSignal()  # Emitted when schedule changes
    schedule_loaded = pyqtSignal(str)  # Emitted with file path when loaded

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(PANEL_BODY_STYLE)
        self._modified = False
        self._current_file = None  # Path to currently loaded/saved schedule file

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet(PANEL_HEADER_STYLE)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 6, 12, 6)
        self._title_label = QLabel("Schedule")
        self._title_label.setStyleSheet(PANEL_HEADER_LABEL_STYLE)
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()

        # Save button
        self._save_btn = QPushButton("Save")
        self._save_btn.setStyleSheet(_header_btn_style)
        self._save_btn.setToolTip("Save schedule to file")
        self._save_btn.clicked.connect(lambda: self.save_schedule())
        header_layout.addWidget(self._save_btn)

        layout.addWidget(header)

        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget.setDragEnabled(True)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_widget.setSpacing(4)
        self.list_widget.setStyleSheet("QListWidget { padding: 8px; }")
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._on_context_menu)
        self.list_widget.model().rowsMoved.connect(self._on_rows_moved)
        self.list_widget.itemSelectionChanged.connect(self._sync_selection_state)
        # Event filter for proper multi-select handling
        self.list_widget.viewport().installEventFilter(self)
        layout.addWidget(self.list_widget)

        # Ensure schedules directory exists
        _SCHEDULES_DIR.mkdir(parents=True, exist_ok=True)

    def add_item(self, data: dict):
        """Add a verse to the schedule."""
        item_widget = ScheduleItem(data)
        item_widget.clicked.connect(lambda: self.item_clicked.emit(item_widget.data))
        item_widget.double_clicked.connect(lambda: self.item_double_clicked.emit(item_widget.data))
        item_widget.rename_requested.connect(lambda: self._start_rename(item_widget))
        item_widget.theme_change_requested.connect(lambda theme: self._change_theme(item_widget, theme))
        item_widget.delete_requested.connect(lambda: self._delete_item_widget(item_widget))
        item_widget.renamed.connect(self._mark_modified)

        list_item = QListWidgetItem()
        list_item.setFlags(list_item.flags() | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        list_item.setSizeHint(item_widget.sizeHint())
        list_item.setData(Qt.ItemDataRole.UserRole, data)
        list_item.setData(Qt.ItemDataRole.UserRole + 1, item_widget)
        self.list_widget.addItem(list_item)
        self.list_widget.setItemWidget(list_item, item_widget)
        
        # Sync selection state initially
        item_widget.setProperty("selected", list_item.isSelected())
        item_widget.style().unpolish(item_widget)
        item_widget.style().polish(item_widget)

        self._mark_modified()

    def get_schedule(self) -> list:
        """Return all schedule items as dicts."""
        items = []
        for i in range(self.list_widget.count()):
            data = self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            if data:
                items.append(data)
        return items

    def _find_list_item_for_widget(self, item_widget: ScheduleItem) -> QListWidgetItem | None:
        """Find the QListWidgetItem that wraps the given ScheduleItem."""
        for i in range(self.list_widget.count()):
            list_item = self.list_widget.item(i)
            if list_item.data(Qt.ItemDataRole.UserRole + 1) is item_widget:
                return list_item
        return None

    def _start_rename(self, item_widget: ScheduleItem):
        item_widget.start_rename()
        self.item_renamed.emit(
            str(id(item_widget)),
            item_widget.data.get("name", item_widget.data.get("ref", ""))
        )

    def _delete_item_widget(self, item_widget: ScheduleItem):
        """Delete a single schedule item by widget reference."""
        list_item = self._find_list_item_for_widget(item_widget)
        if list_item:
            row = self.list_widget.row(list_item)
            item = self.list_widget.takeItem(row)
            data = item.data(Qt.ItemDataRole.UserRole)
            if data:
                self.items_deleted.emit([data])
            widget = item.data(Qt.ItemDataRole.UserRole + 1)
            if widget:
                widget.deleteLater()
            self._mark_modified()

    def _change_theme(self, item_widget: ScheduleItem, theme: str):
        item_widget.set_theme(theme)
        self.item_theme_changed.emit(str(id(item_widget)), theme)
        self._mark_modified()

    def _on_rows_moved(self):
        self._mark_modified()

    def _sync_selection_state(self):
        """Sync ScheduleItem's 'selected' property with QListWidget's selection."""
        for i in range(self.list_widget.count()):
            list_item = self.list_widget.item(i)
            item_widget = list_item.data(Qt.ItemDataRole.UserRole + 1)
            if item_widget:
                selected = list_item.isSelected()
                if item_widget.property("selected") != selected:
                    item_widget.setProperty("selected", selected)
                    item_widget.style().unpolish(item_widget)
                    item_widget.style().polish(item_widget)

    def contextMenuEvent(self, event):
        """Handle context menu on the list widget."""
        pos = event.pos()
        self._on_context_menu(pos)

    def _on_context_menu(self, pos):
        """Handle context menu on the list widget."""
        item = self.list_widget.itemAt(pos)
        if item:
            item_widget = item.data(Qt.ItemDataRole.UserRole + 1)
            # Check if Alt is pressed for themes menu
            from PyQt6.QtWidgets import QApplication
            if QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier:
                if item_widget:
                    # Select this item if not already selected
                    if not item.isSelected():
                        self.list_widget.clearSelection()
                        item.setSelected(True)
                self._show_themes_menu_for_selection(self.list_widget.mapToGlobal(pos))
                return
        # Regular right-click on empty space or item - could add a menu here if needed
        pass
        # If no item or empty space, we could show a menu too (optional)

    def keyPressEvent(self, event):
        """Handle key events: Delete for multi-delete, Ctrl+A for select all."""
        if event.key() == Qt.Key.Key_Delete:
            self._delete_selected_items()
        elif event.key() == Qt.Key.Key_A and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.list_widget.selectAll()
        else:
            super().keyPressEvent(event)

    def _delete_selected_items(self):
        """Delete all currently selected schedule items."""
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return
        
        deleted_data = []
        # Delete from bottom up to avoid index shifting
        for item in reversed(selected_items):
            row = self.list_widget.row(item)
            list_item = self.list_widget.takeItem(row)
            data = list_item.data(Qt.ItemDataRole.UserRole)
            if data:
                deleted_data.append(data)
            widget = list_item.data(Qt.ItemDataRole.UserRole + 1)
            if widget:
                widget.deleteLater()
            # QListWidgetItem is not a QObject, don't call deleteLater()
        
        if deleted_data:
            self.items_deleted.emit(deleted_data)
            self._mark_modified()

    def _sync_selection_state(self):
        """Sync the visual selected state of all schedule item widgets."""
        for i in range(self.list_widget.count()):
            list_item = self.list_widget.item(i)
            widget = list_item.data(Qt.ItemDataRole.UserRole + 1)
            if widget:
                selected = list_item.isSelected()
                widget.set_selected(selected)

    def eventFilter(self, watched, event):
        """Event filter to handle mouse events for proper selection with custom item widgets."""
        if watched is self.list_widget.viewport() and event.type() == event.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                # Get the item at the click position
                item = self.list_widget.itemAt(event.pos())
                if item:
                    item_widget = item.data(Qt.ItemDataRole.UserRole + 1)
                    if item_widget:
                        # Emit clicked signal for preview update
                        item_widget.clicked.emit()
                        # Let the list widget handle selection natively
                        # (don't return True here - let event propagate to list widget)
                # Don't consume the event - let the list widget handle selection
        return super().eventFilter(watched, event)

    def _show_themes_menu_for_selection(self, global_pos):
        """Show themes menu that applies to all selected items."""
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return
        
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: rgba(30, 41, 59, 240);
                color: {WHITE};
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background: rgba(59, 130, 246, 60);
            }}
        """)

        from core.theme_loader import get_all_themes
        themes = get_all_themes()
        
        # Show current theme of first selected item as checked (for reference)
        first_widget = selected_items[0].data(Qt.ItemDataRole.UserRole + 1)
        current_theme = first_widget.data.get("theme", "default") if first_widget else "default"
        
        for name, theme_data in sorted(themes.items()):
            label = theme_data.get("label", theme_data.get("name", name))
            action = menu.addAction(label)
            if name == current_theme:
                action.setCheckable(True)
                action.setChecked(True)
            action.triggered.connect(lambda checked, n=name: self._apply_theme_to_selection(n))
        
        menu.exec(global_pos)

    def _apply_theme_to_selection(self, theme: str):
        """Apply a theme to all selected schedule items."""
        selected_items = self.list_widget.selectedItems()
        for item in selected_items:
            item_widget = item.data(Qt.ItemDataRole.UserRole + 1)
            if item_widget:
                item_widget.set_theme(theme)
                self.item_theme_changed.emit(str(id(item_widget)), theme)

    def _get_selected_item_widgets(self) -> list:
        """Get list of ScheduleItem widgets for currently selected items."""
        widgets = []
        for item in self.list_widget.selectedItems():
            widget = item.data(Qt.ItemDataRole.UserRole + 1)
            if widget:
                widgets.append(widget)
        return widgets

    # ── Schedule Filing ──────────────────────────────────────────────

    def _update_title(self):
        """Update the header title to show current schedule name."""
        if self._current_file:
            name = Path(self._current_file).stem
            if self._modified:
                name += " *"
        else:
            name = "Schedule"
        self._title_label.setText(name)

    def _mark_modified(self):
        """Mark the schedule as modified."""
        if not self._modified:
            self._modified = True
            self._update_title()
            self.schedule_modified.emit()

    @property
    def is_modified(self) -> bool:
        return self._modified

    @property
    def current_file(self) -> str | None:
        return self._current_file

    def get_schedule_data(self) -> list:
        """Return schedule items as a list of dicts for serialization."""
        items = []
        for i in range(self.list_widget.count()):
            data = self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            if data:
                # Copy to avoid mutating the live data
                items.append(dict(data))
        return items

    def save_schedule(self, file_path: str = None) -> bool:
        """Save the current schedule to a JSON file. Returns True on success."""
        if file_path is None:
            file_path = self._current_file

        if file_path is None:
            # No file yet — prompt user
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save Schedule", str(_SCHEDULES_DIR),
                "Schedule Files (*.json);;All Files (*)"
            )
            if not file_path:
                return False  # User cancelled
            if not file_path.endswith(".json"):
                file_path += ".json"

        try:
            data = {
                "version": 1,
                "items": self.get_schedule_data()
            }
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self._current_file = file_path
            self._modified = False
            self._update_title()
            logger.info(f"Schedule saved to: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save schedule: {e}")
            QMessageBox.critical(self, "Save Error", f"Could not save schedule:\n{e}")
            return False

    def load_schedule(self, file_path: str = None) -> bool:
        """Load a schedule from a JSON file. Returns True on success."""
        if file_path is None:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Open Schedule", str(_SCHEDULES_DIR),
                "Schedule Files (*.json);;All Files (*)"
            )
            if not file_path:
                return False  # User cancelled

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            items = data.get("items", []) if isinstance(data, dict) else data

            # Clear existing schedule
            self.clear_all(silent=True)

            # Load items
            for item_data in items:
                self.add_item(item_data)

            self._current_file = file_path
            self._modified = False
            self._update_title()
            self.schedule_loaded.emit(file_path)
            logger.info(f"Schedule loaded from: {file_path} ({len(items)} items)")
            return True
        except Exception as e:
            logger.error(f"Failed to load schedule: {e}")
            QMessageBox.critical(self, "Load Error", f"Could not load schedule:\n{e}")
            return False

    def clear_all(self, silent: bool = False):
        """Clear all schedule items."""
        if not silent and self._modified:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "The current schedule has unsaved changes. Clear anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return

        self.list_widget.clear()
        self._modified = False
        self._current_file = None
        self._update_title()

    def list_schedules(self) -> list:
        """Return list of available schedule files sorted by last modified (newest first)."""
        _SCHEDULES_DIR.mkdir(parents=True, exist_ok=True)
        files = []
        for f in _SCHEDULES_DIR.glob("*.json"):
            try:
                mtime = f.stat().st_mtime
                files.append((f.name, f, mtime))
            except OSError:
                continue
        # Sort by modification time, newest first
        files.sort(key=lambda x: x[2], reverse=True)
        return [(name, path) for name, path, _ in files]

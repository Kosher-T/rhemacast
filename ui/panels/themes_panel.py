"""
ui/panels/themes_panel.py

Theme selector panel with multi-output support.
Each output gets its own column of theme cards.
Up to 3 outputs can be active simultaneously.
"""

import logging
import socket
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QMenu, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal

from ui.styles import (
    PANEL_BODY_STYLE,
    CYAN_400, SLATE_300, SLATE_400, SLATE_500, WHITE
)

logger = logging.getLogger(__name__)

MAX_OUTPUTS = 3
HTTP_PORT = 8766


def _get_lan_ip() -> str:
    """Detect the LAN IP address (non-loopback)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class ThemeCard(QFrame):
    """Compact theme card — no description text."""

    theme_selected = pyqtSignal(str)
    theme_double_clicked = pyqtSignal(str)
    theme_edit_requested = pyqtSignal(str)

    def __init__(self, theme: dict, parent=None):
        super().__init__(parent)
        self.theme_name = theme["name"]
        self._active = False

        accent = "#3b82f6"
        container = theme.get("container", {})
        border = container.get("border", "")
        if "rgba(" in border:
            try:
                parts = border.split("solid")[1].strip().rstrip(")")
                accent = parts
            except (IndexError, ValueError):
                pass

        bg = container.get("background", "rgba(15, 23, 42, 0.6)")

        self.setStyleSheet(f"""
            QFrame {{ background: transparent; border: none; }}
            QFrame:hover {{ background: rgba(255, 255, 255, 5); }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        swatch = QLabel()
        swatch.setFixedSize(24, 24)
        swatch.setStyleSheet(f"""
            background: {bg};
            border: 2px solid {accent};
            border-radius: 5px;
        """)
        layout.addWidget(swatch)

        name_label = QLabel(theme.get("label", theme["name"]))
        name_label.setStyleSheet(f"color: {WHITE}; font-size: 11px; font-weight: 700; background: transparent;")
        layout.addWidget(name_label)
        layout.addStretch()

    def set_active(self, active: bool):
        self._active = active
        if active:
            self.setStyleSheet(f"QFrame {{ background: rgba(34, 211, 238, 10); border: none; }}")
        else:
            self.setStyleSheet(f"""
                QFrame {{ background: transparent; border: none; }}
                QFrame:hover {{ background: rgba(255, 255, 255, 5); }}
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.theme_selected.emit(self.theme_name)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.theme_double_clicked.emit(self.theme_name)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        edit_action = menu.addAction("Quick Edit")
        edit_action.triggered.connect(lambda: self.theme_edit_requested.emit(self.theme_name))
        menu.exec(event.globalPos())


class OutputColumn(QWidget):
    """A single output's theme column with label and remove button."""

    theme_changed = pyqtSignal(str, str)
    theme_double_clicked = pyqtSignal(str, str)
    theme_edit_requested = pyqtSignal(str)
    remove_clicked = pyqtSignal(str)  # output_id

    def __init__(self, output_id: str, show_remove: bool = False, parent=None):
        super().__init__(parent)
        self.output_id = output_id
        self._current_theme = "default"
        self._cards: dict[str, ThemeCard] = {}

        self.setStyleSheet("background: transparent; border: none;")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)

        # ── Header: label + optional remove button ──
        header = QWidget()
        header.setStyleSheet("background: transparent; border: none;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 2, 8, 2)
        header_layout.setSpacing(4)

        label = QLabel("Main" if output_id == "1" else f"Output {output_id}")
        label.setStyleSheet(f"color: {SLATE_300}; font-size: 10px; font-weight: 700; background: transparent;")

        # Build tooltip with local + network URLs
        lan_ip = _get_lan_ip()
        local_url = f"http://127.0.0.1:{HTTP_PORT}/display.html?output={output_id}"
        network_url = f"http://{lan_ip}:{HTTP_PORT}/display.html?output={output_id}"
        label.setToolTip(
            f"<span style='color:#94a3b8'>Local:</span> {local_url}<br><br>"
            f"<span style='color:#94a3b8'>Network:</span> {network_url}"
        )
        label.setCursor(Qt.CursorShape.WhatsThisCursor)
        header_layout.addWidget(label)
        header_layout.addStretch()

        if show_remove:
            rm_btn = QPushButton("\u00d7")
            rm_btn.setFixedSize(18, 18)
            rm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            rm_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {SLATE_400};
                    border: none;
                    border-radius: 4px;
                    font-size: 13px;
                    font-weight: 700;
                }}
                QPushButton:hover {{
                    color: #ef4444;
                    background: rgba(239, 68, 68, 0.1);
                }}
            """)
            rm_btn.clicked.connect(lambda: self.remove_clicked.emit(self.output_id))
            header_layout.addWidget(rm_btn)

        self._layout.addWidget(header)

        self._load_themes()
        self._layout.addStretch()

    def _load_themes(self):
        from core.theme_loader import get_all_themes
        from core.database import get_setting

        themes = get_all_themes()
        for name, theme in themes.items():
            card = ThemeCard(theme)
            card.theme_selected.connect(self._on_theme_selected)
            card.theme_double_clicked.connect(self._on_theme_double_clicked)
            card.theme_edit_requested.connect(self.theme_edit_requested.emit)
            self._layout.addWidget(card)
            self._cards[name] = card

        saved = get_setting(f"display.output_{self.output_id}_theme", "default")
        if saved in self._cards:
            self._cards[saved].set_active(True)
            self._current_theme = saved

    def _on_theme_selected(self, name: str):
        if name == self._current_theme:
            return
        if name not in self._cards:
            return
        if self._current_theme in self._cards:
            self._cards[self._current_theme].set_active(False)
        self._cards[name].set_active(True)
        self._current_theme = name

        from core.database import set_setting
        set_setting(f"display.output_{self.output_id}_theme", name)

        self.theme_changed.emit(self.output_id, name)
        logger.info(f"Output {self.output_id} theme changed to: {name}")

    def _on_theme_double_clicked(self, name: str):
        if name != self._current_theme:
            if self._current_theme in self._cards:
                self._cards[self._current_theme].set_active(False)
            self._cards[name].set_active(True)
            self._current_theme = name

            from core.database import set_setting
            set_setting(f"display.output_{self.output_id}_theme", name)

            self.theme_changed.emit(self.output_id, name)

        self.theme_double_clicked.emit(self.output_id, name)
        logger.info(f"Output {self.output_id} theme double-clicked: {name}")

    @property
    def current_theme(self) -> str:
        return self._current_theme


class ThemesPanel(QWidget):
    """Theme selector panel with per-output columns."""

    theme_changed = pyqtSignal(str, str)
    theme_double_clicked = pyqtSignal(str, str)
    theme_edit_requested = pyqtSignal(str)
    output_count_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(PANEL_BODY_STYLE)
        self._output_count = 1
        self._columns: dict[str, OutputColumn] = {}

        self._root_layout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(8, 8, 8, 8)
        self._root_layout.setSpacing(6)

        # ── Columns container ──
        self._columns_container = QWidget()
        self._columns_container.setStyleSheet("background: transparent; border: none;")
        self._columns_layout = QHBoxLayout(self._columns_container)
        self._columns_layout.setContentsMargins(0, 0, 0, 0)
        self._columns_layout.setSpacing(8)
        self._root_layout.addWidget(self._columns_container, 1)

        # ── Add / Remove buttons row ──
        btn_row = QWidget()
        btn_row.setStyleSheet("background: transparent; border: none;")
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(4)

        self._add_btn = QPushButton("+ Output")
        self._add_btn.setFixedHeight(24)
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {SLATE_400};
                border: 1px dashed rgba(255, 255, 255, 0.1);
                border-radius: 4px;
                font-size: 10px;
                font-weight: 600;
                padding: 0 10px;
            }}
            QPushButton:hover {{
                color: {CYAN_400};
                border-color: rgba(34, 211, 238, 0.3);
            }}
        """)
        self._add_btn.clicked.connect(self._add_output)
        btn_layout.addWidget(self._add_btn)
        btn_layout.addStretch()
        self._root_layout.addWidget(btn_row)

        # ── Initialize ──
        self._load_output_count()
        self._rebuild_columns()

    def _load_output_count(self):
        from core.database import get_setting
        self._output_count = int(get_setting("display.output_count", 1))
        self._output_count = max(1, min(MAX_OUTPUTS, self._output_count))

    def _save_output_count(self):
        from core.database import set_setting
        set_setting("display.output_count", self._output_count)

    def _add_output(self):
        if self._output_count >= MAX_OUTPUTS:
            return
        self._output_count += 1
        self._save_output_count()
        self._rebuild_columns()
        self.output_count_changed.emit(self._output_count)
        logger.info(f"Added output {self._output_count}")

    def _remove_output(self, output_id: str):
        if self._output_count <= 1:
            return
        # Clean up DB setting for removed output
        from core.database import set_setting
        set_setting(f"display.output_{output_id}_theme", None)

        self._output_count -= 1
        self._save_output_count()
        self._rebuild_columns()
        self.output_count_changed.emit(self._output_count)
        logger.info(f"Removed output {output_id}")

    def _rebuild_columns(self):
        # Clear existing
        for col in self._columns.values():
            self._columns_layout.removeWidget(col)
            col.deleteLater()
        self._columns.clear()

        for i in range(1, self._output_count + 1):
            oid = str(i)
            show_remove = self._output_count > 1 and i > 1

            col = OutputColumn(oid, show_remove=show_remove)
            col.theme_changed.connect(self.theme_changed.emit)
            col.theme_double_clicked.connect(self.theme_double_clicked.emit)
            col.theme_edit_requested.connect(self.theme_edit_requested.emit)
            col.remove_clicked.connect(self._remove_output)
            self._columns_layout.addWidget(col)
            self._columns[oid] = col

        self._add_btn.setVisible(self._output_count < MAX_OUTPUTS)

    def reload(self):
        """Force-reload all themes from disk and rebuild cards."""
        from core.theme_loader import reload_themes
        reload_themes()
        self._rebuild_columns()

    def get_theme_for_output(self, output_id: str) -> str:
        if output_id in self._columns:
            return self._columns[output_id].current_theme
        return "default"

    def get_all_output_themes(self) -> dict[str, str]:
        return {oid: col.current_theme for oid, col in self._columns.items()}

    @property
    def output_count(self) -> int:
        return self._output_count

"""
ui/panels/themes_panel.py

Theme selector panel with multi-output support.
Each active output gets its own stacked block of theme cards.
Outputs can be added/removed per tab (see core/outputs.py).
"""

import logging
import socket
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFrame, QMenu, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal

from ui.styles import (
    PANEL_BODY_STYLE,
    CYAN_400, SLATE_300, SLATE_400, SLATE_500, WHITE, SELECTION_BG,
    TEXT_MUTED, ACCENT_BORDER,
)

logger = logging.getLogger(__name__)

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
            self.setStyleSheet(f"QFrame {{ background: {SELECTION_BG}; border: none; }}")
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
    """A single output's theme block: header (label + remove X) with its
    theme cards stacked in a compact grid below.

    Stacked vertically, not side by side: the panel is tall and narrow,
    so each output's themes read as a block down the column.
    """

    theme_changed = pyqtSignal(str, str)
    theme_double_clicked = pyqtSignal(str, str)
    theme_edit_requested = pyqtSignal(str)
    remove_clicked = pyqtSignal(str)  # output_id

    GRID_COLUMNS = 2

    def __init__(self, output_id: str, show_remove: bool = False, *,
                 theme_kind=None, setting_prefix: str = "display.output",
                 default_theme: str = "default", title: str | None = None,
                 parent=None):
        super().__init__(parent)
        from core.theme_loader import SCRIPTURE
        self.output_id = output_id
        self._theme_kind = theme_kind or SCRIPTURE
        self._setting_prefix = setting_prefix
        self._default_theme = default_theme
        self._current_theme = default_theme
        self._cards: dict[str, ThemeCard] = {}
        self._show_remove = show_remove

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

        label = QLabel(title or f"Output {output_id}")
        label.setStyleSheet(f"color: {SLATE_300}; font-size: 10px; font-weight: 700; background: transparent;")

        # Build tooltip with local + network URLs
        lan_ip = _get_lan_ip()
        local_url = f"http://127.0.0.1:{HTTP_PORT}/display.html?output={output_id}"
        network_url = f"http://{lan_ip}:{HTTP_PORT}/display.html?output={output_id}"
        label.setToolTip(
            f"<span style='color:{TEXT_MUTED}'>Local:</span> {local_url}<br><br>"
            f"<span style='color:{TEXT_MUTED}'>Network:</span> {network_url}"
        )
        label.setCursor(Qt.CursorShape.WhatsThisCursor)
        header_layout.addWidget(label)
        header_layout.addStretch()

        self._remove_btn = None
        if show_remove:
            rm_btn = QPushButton()
            rm_btn.setToolTip("Remove this output")
            from ui.icons import apply_button
            apply_button(rm_btn, "close")
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
                QPushButton:disabled {{
                    color: {SLATE_500};
                    background: transparent;
                }}
            """)
            rm_btn.clicked.connect(lambda: self.remove_clicked.emit(self.output_id))
            header_layout.addWidget(rm_btn)
            self._remove_btn = rm_btn

        self._layout.addWidget(header)

        # ── Theme cards: compact grid, stacked down the panel ──
        self._grid = QGridLayout()
        self._grid.setContentsMargins(4, 0, 4, 4)
        self._grid.setHorizontalSpacing(4)
        self._grid.setVerticalSpacing(2)
        self._layout.addLayout(self._grid)

        self._load_themes()

    def set_remove_enabled(self, enabled: bool):
        """A tab must keep at least one output: the last X is disabled."""
        if self._remove_btn is not None:
            self._remove_btn.setEnabled(bool(enabled))

    def _load_themes(self):
        from core.theme_loader import get_themes_by_kind
        from core.database import get_setting

        # Theme kind follows the owning tab: scripture themes here, the
        # freeform (song/slide) folder in deck columns — never mixed.
        themes = get_themes_by_kind(self._theme_kind)
        for index, (name, theme) in enumerate(themes.items()):
            card = ThemeCard(theme)
            card.theme_selected.connect(self._on_theme_selected)
            card.theme_double_clicked.connect(self._on_theme_double_clicked)
            card.theme_edit_requested.connect(self.theme_edit_requested.emit)
            self._grid.addWidget(card, index // self.GRID_COLUMNS,
                                 index % self.GRID_COLUMNS)
            self._cards[name] = card

        saved = get_setting(f"{self._setting_prefix}_{self.output_id}_theme",
                            self._default_theme)
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
        set_setting(f"{self._setting_prefix}_{self.output_id}_theme", name)

        self.theme_changed.emit(self.output_id, name)
        logger.info(f"Output {self.output_id} theme changed to: {name}")

    def _on_theme_double_clicked(self, name: str):
        if name != self._current_theme:
            if self._current_theme in self._cards:
                self._cards[self._current_theme].set_active(False)
            self._cards[name].set_active(True)
            self._current_theme = name

            from core.database import set_setting
            set_setting(f"{self._setting_prefix}_{self.output_id}_theme", name)

            self.theme_changed.emit(self.output_id, name)

        self.theme_double_clicked.emit(self.output_id, name)
        logger.info(f"Output {self.output_id} theme double-clicked: {name}")

    @property
    def current_theme(self) -> str:
        return self._current_theme


class ThemesPanel(QWidget):
    """Theme selector panel: one stacked block per output in its set.

    Outputs are VERTICAL, not side by side — the panel is tall and narrow,
    so each output's themes read as a block down the column. Each block has
    a remove X, and a "+ Add output" row appears while the set is below its
    size. Both actions write the tab's active-output list (core/outputs.py);
    a tab always keeps at least one output.
    """

    theme_changed = pyqtSignal(str, str)
    theme_double_clicked = pyqtSignal(str, str)
    theme_edit_requested = pyqtSignal(str)
    outputs_changed = pyqtSignal(list)

    def __init__(self, parent=None, *, output_ids=("1",),
                 theme_kind=None, setting_prefix: str = "display.output",
                 default_theme: str = "default",
                 main_label: str = "Main", tab_key: str | None = None,
                 allow_add_remove: bool = False):
        super().__init__(parent)
        from core.theme_loader import SCRIPTURE
        self._output_ids = tuple(output_ids)
        self._theme_kind = theme_kind or SCRIPTURE
        self._setting_prefix = setting_prefix
        self._default_theme = default_theme
        self._main_label = main_label
        self._tab_key = tab_key
        self._allow_add_remove = bool(allow_add_remove)
        self._columns: dict[str, OutputColumn] = {}

        self.setStyleSheet(PANEL_BODY_STYLE)

        self._root_layout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(8, 8, 8, 8)
        self._root_layout.setSpacing(6)

        # ── Blocks container: stacked vertically ──
        self._columns_container = QWidget()
        self._columns_container.setStyleSheet("background: transparent; border: none;")
        self._columns_layout = QVBoxLayout(self._columns_container)
        self._columns_layout.setContentsMargins(0, 0, 0, 0)
        self._columns_layout.setSpacing(8)
        self._root_layout.addWidget(self._columns_container, 1)

        # ── Add-output row (only while the set is below its size) ──
        self._add_btn = QPushButton("+  Add output")
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {SLATE_400};
                border: 1px dashed {ACCENT_BORDER};
                border-radius: 6px;
                padding: 6px 8px;
                font-size: 11px;
                font-weight: 700;
                text-align: left;
            }}
            QPushButton:hover {{
                color: {WHITE};
                border-color: {CYAN_400};
            }}
        """)
        self._add_btn.clicked.connect(self._on_add_output)
        self._add_btn.setVisible(False)
        self._root_layout.addWidget(self._add_btn)

        # ── Initialize ──
        self._rebuild_columns()

    def _rebuild_columns(self):
        # Clear existing
        while self._columns_layout.count():
            item = self._columns_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for col in self._columns.values():
            col.deleteLater()
        self._columns.clear()

        can_remove = len(self._output_ids) > 1
        for index, oid in enumerate(self._output_ids):
            col = OutputColumn(
                oid, show_remove=self._allow_add_remove,
                theme_kind=self._theme_kind,
                setting_prefix=self._setting_prefix,
                default_theme=self._default_theme,
                title=self._main_label if index == 0 else None)
            col.set_remove_enabled(can_remove)
            col.theme_changed.connect(self.theme_changed.emit)
            col.theme_double_clicked.connect(self.theme_double_clicked.emit)
            col.theme_edit_requested.connect(self.theme_edit_requested.emit)
            col.remove_clicked.connect(self._on_remove_output)
            self._columns_layout.addWidget(col)
            self._columns[oid] = col
        self._columns_layout.addStretch()

        self._refresh_add_button()

    def _refresh_add_button(self):
        """The + row exists only while an unused pool id remains."""
        if not self._allow_add_remove or not self._tab_key:
            self._add_btn.setVisible(False)
            return
        from core.outputs import can_add_output
        available = can_add_output(self._tab_key)
        self._add_btn.setVisible(available)
        self._add_btn.setEnabled(available)

    def _on_add_output(self):
        from core.outputs import add_active_output
        if not self._tab_key:
            return
        updated = add_active_output(self._tab_key)
        if tuple(updated) == self._output_ids:
            return
        self._output_ids = tuple(updated)
        self._rebuild_columns()
        self.outputs_changed.emit(list(updated))
        logger.info(f"Outputs added: {updated}")

    def _on_remove_output(self, output_id: str):
        """Delete an output: stop writing to it AND blank its OBS scene."""
        from core.outputs import remove_active_output
        if not self._tab_key:
            return
        updated = remove_active_output(self._tab_key, output_id)
        if tuple(updated) == self._output_ids:
            return
        # Nothing writes to a deleted output any more, so blank its OBS
        # scene now — otherwise it stays frozen on the last frame.
        try:
            from core.output_router import clear_output
            clear_output(output_id)
        except Exception:
            logger.exception(f"failed to clear removed output {output_id}")
        self._output_ids = tuple(updated)
        self._rebuild_columns()
        self.outputs_changed.emit(list(updated))
        logger.info(f"Output {output_id} removed: {updated}")

    def reload(self):
        """Force-reload all themes from disk and rebuild cards."""
        from core.theme_loader import reload_themes
        reload_themes()
        self._rebuild_columns()

    def get_theme_for_output(self, output_id: str) -> str:
        if output_id in self._columns:
            return self._columns[output_id].current_theme
        return self._default_theme

    def get_all_output_themes(self) -> dict[str, str]:
        return {oid: col.current_theme for oid, col in self._columns.items()}

"""
ui/panels/themes_panel.py

Theme selector panel with multi-output support.
Each active output gets its own stacked block of theme cards.
Outputs can be added/removed per tab (see core/outputs.py).
"""

import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFrame, QMenu, )
from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QCursor

from ui.popups import menu_qss
from ui.styles import PANEL_BODY_STYLE
from ui.tokens import (
    ACCENT_BORDER, ACCENT_TEXT, OPTION_OBJECT_NAME, RADIUS_MD,
    SELECTED_BAR_WIDTH, SPACE_12, SPACE_16, SPACE_24, SPACE_4, SPACE_8,
    TEXT_MUTED, TEXT_PRIMARY, TYPE_CAPTION, WEIGHT_SEMIBOLD,
    ghost_button_qss, option_row_qss,
)
from ui.widgets.output_links import OutputLinksPopup, OutputLinksPreview

logger = logging.getLogger(__name__)

HTTP_PORT = 8766

# Group captions (MAIN / OUTPUT 2 / OUTPUT 3) — same voice as the panel
# captions elsewhere (caption size, semibold, tracked out, muted). They are
# buttons now: hover previews the display links, click opens the copy card.
# The 4px pill padding is why the header's left inset is 12 - 4.
_GROUP_BUTTON_QSS = ghost_button_qss(
    font_css=(
        f"font-size: {TYPE_CAPTION}px;"
        f" font-weight: {WEIGHT_SEMIBOLD};"
        " letter-spacing: 0.8px;"
        " text-align: left;"),
    padding="2px 4px",
)

# Ghost close button: no border, no fill at rest, a quiet surface on hover.
# The glyph is 16px so the mark matches the caption's visual weight inside
# the 24x24 hit area (the area itself is unchanged).
_GHOST_CLOSE_QSS = ghost_button_qss(
    font_css="font-size: 16px; font-weight: " + str(WEIGHT_SEMIBOLD) + ";")


def _get_lan_ip() -> str:
    """LAN IP address, falling back to loopback (legacy helper).

    Callers that must distinguish "offline" from "localhost" should use
    core.network_watcher.detect_lan_ip(), which returns None instead of
    inventing an address.
    """
    from core.network_watcher import detect_lan_ip
    return detect_lan_ip() or "127.0.0.1"


def output_display_urls(output_id: str,
                        lan_ip: str | None) -> tuple[str, str | None]:
    """(local, network) display URLs for one output.

    Network is None when the machine is offline, so the UI can say "Not
    connected" rather than print a loopback address that no phone can reach.
    """
    local = f"http://127.0.0.1:{HTTP_PORT}/display.html?output={output_id}"
    if not lan_ip:
        return local, None
    return local, f"http://{lan_ip}:{HTTP_PORT}/display.html?output={output_id}"


class ThemeCard(QFrame):
    """One theme option row — the whole row is the click target.

    No indicator and no swatch. These are text-rendering themes, so a 24px
    colour chip previewed nothing (all five are transparent with white
    text) — it was a constant square, and the last blue in the UI. The row
    itself carries every state: surface, hover wash, and the accent bar.
    """

    theme_selected = pyqtSignal(str)
    theme_double_clicked = pyqtSignal(str)
    theme_edit_requested = pyqtSignal(str)

    def __init__(self, theme: dict, parent=None):
        super().__init__(parent)
        self.theme_name = theme["name"]
        self._active = False
        self._label_text = theme.get("label", theme["name"])

        self.setObjectName(OPTION_OBJECT_NAME)
        # A QWidget subclass ignores QSS background/border without this.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setProperty("selected", False)
        # Qt does not evaluate :hover on an ancestor selector, so the row
        # tracks the pointer itself (see option_row_qss).
        self.setProperty("hovered", False)
        self.setStyleSheet(option_row_qss())
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(self._label_text)
        self.setAccessibleDescription(
            "Display theme. Click to use it, double-click to push it live.")

        layout = QHBoxLayout(self)
        # The 12px visual inset includes the 3px bar, so checking a row
        # cannot shift its label.
        layout.setContentsMargins(
            SPACE_12 - SELECTED_BAR_WIDTH, SPACE_8, SPACE_12, SPACE_8)
        layout.setSpacing(0)

        self._label = QLabel(self._label_text)
        # The row is the hit target: a label that swallowed the pointer
        # would break both the hover wash and click-anywhere selection.
        self._label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._label)
        layout.addStretch()

    def _repolish(self):
        """Re-evaluate the property rules for the row *and* its label.

        A property selector re-polishes the widget it matches, not its
        descendants — the label needs its own pass for the text colour.
        """
        for widget in (self, self._label):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def _set_hovered(self, hovered: bool):
        if bool(self.property("hovered")) == hovered:
            return
        self.setProperty("hovered", hovered)
        self._repolish()

    def enterEvent(self, event):
        super().enterEvent(event)
        self._set_hovered(True)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        # Moving onto a child fires Leave on the frame; keep the row lit
        # while the pointer is still anywhere inside it.
        if not self.rect().contains(self.mapFromGlobal(QCursor.pos())):
            self._set_hovered(False)

    def set_active(self, active: bool):
        self._active = active
        self.setProperty("selected", active)
        self._repolish()
        self.update()

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
        menu.setStyleSheet(menu_qss())
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
        self._layout.setSpacing(SPACE_8)

        # ── Header: label + optional remove button ──
        header = QWidget()
        header.setStyleSheet("background: transparent; border: none;")
        header_layout = QHBoxLayout(header)
        # The row's 3px bar sits outside its own contents, so its text
        # starts 12px in: the caption takes the same inset, minus the
        # button's own 4px pill padding, and shares the labels' left edge.
        header_layout.setContentsMargins(
            SPACE_12 - SPACE_4, SPACE_4, SPACE_12, SPACE_4)
        header_layout.setSpacing(SPACE_8)

        self._title = title or f"Output {output_id}"
        # Qt has no text-transform for labels: uppercase here, keep the
        # original string for the link card's title and accessible names.
        self._link_button = QPushButton(self._title.upper())
        self._link_button.setObjectName("outputNameButton")
        self._link_button.setStyleSheet(_GROUP_BUTTON_QSS)
        self._link_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._link_button.setCheckable(True)
        self._link_button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._link_button.setAccessibleName(f"{self._title} display links")
        self._link_button.setAccessibleDescription(
            "Hover for the addresses, click to open the copy card")
        self._link_button.clicked.connect(self._toggle_display_links)
        self._link_button.installEventFilter(self)

        from core.network_watcher import network_watcher
        # Hover preview (cursor-anchored, read-only) and the persistent
        # copy card share one live link set.
        self._link_preview = OutputLinksPreview(self)
        self._link_popup = OutputLinksPopup(self)
        self._link_popup.closed.connect(
            lambda: self._link_button.setChecked(False))
        self._lan_address = network_watcher().current()
        self._refresh_display_links()
        network_watcher().address_changed.connect(
            self._on_network_address_changed)

        header_layout.addWidget(self._link_button)
        header_layout.addStretch()

        self._remove_btn = None
        if show_remove:
            # Text glyph, not the SVG icon: the icon set is drawn in
            # near-white and QSS cannot tint a QIcon, so a ghost button
            # that colours with the tokens has to own its glyph.
            rm_btn = QPushButton("\u00d7")
            rm_btn.setToolTip("Remove this output")
            rm_btn.setAccessibleName(f"Remove {self._title}")
            rm_btn.setFixedSize(SPACE_24, SPACE_24)
            rm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            rm_btn.setStyleSheet(_GHOST_CLOSE_QSS)
            rm_btn.clicked.connect(lambda: self.remove_clicked.emit(self.output_id))
            header_layout.addWidget(rm_btn)
            self._remove_btn = rm_btn

        self._layout.addWidget(header)

        # ── Theme rows: compact grid, stacked down the panel ──
        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(SPACE_12)
        self._grid.setVerticalSpacing(SPACE_8)
        self._layout.addLayout(self._grid)

        self._load_themes()

    # ── Display links (hover preview + click card) ───────────────────────
    def _refresh_display_links(self):
        """Recompute this output's URLs and push them into both cards."""
        self._local_url, self._network_url = output_display_urls(
            self.output_id, self._lan_address or None)
        self._link_preview.set_links(self._local_url, self._network_url)
        self._link_popup.set_links(
            self._local_url, self._network_url, title=self._title)

    def _on_network_address_changed(self, address: str):
        """Watcher signal: the machine joined/left a network mid-service."""
        address = address or ""
        if address == self._lan_address:
            return
        self._lan_address = address
        self._refresh_display_links()

    def _card_open(self) -> bool:
        """True while any output's persistent card is up on this panel."""
        parent = self.parentWidget()
        if parent is None:
            return self._link_popup.isVisible()
        return any(popup.isVisible()
                   for popup in parent.findChildren(OutputLinksPopup))

    def _toggle_display_links(self):
        """Click pins the copy card; a second click dismisses it."""
        if self._link_popup.isVisible():
            self._link_popup.hide()
            return
        self._link_preview.cancel_show()
        self._link_preview.hide()
        # One card at a time across the three outputs.
        parent = self.parentWidget()
        if parent is not None:
            for popup in parent.findChildren(OutputLinksPopup):
                if popup is not self._link_popup:
                    popup.hide()
        self._link_button.setChecked(True)
        self._link_popup.show_persistent(self._link_button)

    def eventFilter(self, obj, event):
        """Hovering the output name previews its addresses; leaving hides
        the preview. The click card is opened by the button's clicked
        signal, so keyboard activation works too."""
        if obj is self._link_button:
            kind = event.type()
            if kind == QEvent.Type.Enter:
                if not self._card_open():
                    self._link_preview.schedule_show(self._link_button)
            elif kind == QEvent.Type.Leave:
                self._link_preview.cancel_show()
                self._link_preview.hide()
        return super().eventFilter(obj, event)

    def hideEvent(self, event):
        # Switching sub-pages/tabs must not leave a floating card behind.
        self._link_preview.cancel_show()
        self._link_preview.hide()
        self._link_popup.hide()
        super().hideEvent(event)

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
        self._columns_layout.setSpacing(SPACE_16)
        self._root_layout.addWidget(self._columns_container, 1)

        # ── Add-output row (only while the set is below its size) ──
        self._add_btn = QPushButton("+  Add output")
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_MUTED};
                border: 1px dashed {ACCENT_BORDER};
                border-radius: {RADIUS_MD}px;
                padding: 6px 8px;
                font-size: {TYPE_CAPTION}px;
                font-weight: {WEIGHT_SEMIBOLD};
                text-align: left;
            }}
            QPushButton:hover {{
                color: {TEXT_PRIMARY};
                border-color: {ACCENT_TEXT};
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

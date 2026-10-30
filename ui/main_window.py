"""
ui/main_window.py

Frameless main window with Chrome-style tab bar and lazy-loaded tabs.
Implements window dragging, resizing, and global hotkeys.
"""

import os
import logging
import time

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QSizeGrip
)
from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut

from ui import dialogs
from ui.popups import menu_qss
from ui.styles import (
    SLATE_950, WHITE, BORDER_SUBTLE,
    ACCENT, ACCENT_LIGHT, TEXT_FAINT, TEXT_PRIMARY,
)
from ui.tokens import (
    TAB_LOADED_BG, TAB_LOADED_TEXT, TAB_UNLOADED_BG, TAB_UNLOADED_TEXT,
    TAB_SELECTED_BG, TAB_SELECTED_TEXT,
    BUTTON_HEIGHT, DANGER, SPACE_4, SPACE_8, SPACE_12, SPACE_16, SUCCESS,
    button_qss, tone_button_qss,
)
from ui.tabs.presentation_tab import PresentationTab
from ui.tabs.library_tab import LibraryTab
from ui.tabs.slides_tab import SlidesTab
from ui.tabs.settings_tab import SettingsTab
from ui.widgets.status_bar import StatusBar

logger = logging.getLogger(__name__)

# Key-event tap for diagnosing swallowed hotkeys. Enable with
# RHEMACAST_KEYTAP=1 in the environment. Logs every key event (with focus
# + spontaneity), every shortcut activation, and focus/activation changes.
# Off by default: zero overhead, zero console spam.
import os as _os
_KEYTAP_ENABLED = _os.environ.get("RHEMACAST_KEYTAP") == "1"
# Double-tap Ctrl releases the keyboard from a focused search box. Generous
# enough for a deliberate double tap, short enough that two unrelated Ctrl
# presses (e.g. around a Ctrl+Tab) never read as one.
_CTRL_DOUBLE_TAP_SECONDS = 0.45


class ChromeTab(QPushButton):
    """Custom button acting as a Chrome-style tab.

    ``loaded`` chooses the resting surface: loaded tabs wear a subtle accent
    wash, unloaded tabs stay neutral grey. The checked state is stronger than
    both and adds an accent underline, so the current tab never gets lost
    among the other loaded ones. Changing the state only repaints — the tab
    keeps its fixed height, padding, and width, so the bar never shifts.
    """
    middle_clicked = pyqtSignal()

    def __init__(self, text: str, is_active: bool = False, loaded: bool = True,
                 parent=None):
        super().__init__(text, parent)
        self._loaded = loaded
        self.setCheckable(True)
        self.setChecked(is_active)
        self.setFixedHeight(30)
        self.setAccessibleName(text)
        # self.setAccessibleRole(Qt.AccessibleRole.PageTab)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.apply_font()
        self._sync_accessible_state()
        from ui.app_theme import subscribe_interface_font_changed
        subscribe_interface_font_changed(self._on_interface_font_changed)

    def _on_interface_font_changed(self, prefix: str):
        if prefix == "tabs.names":
            self.apply_font()

    def set_loaded(self, loaded: bool):
        """Reflect whether this tab's content is currently instantiated.

        Colour is the at-a-glance signal; the tooltip and accessible
        description say it in words so the state is not colour-only.
        """
        if self._loaded == loaded:
            return
        self._loaded = loaded
        self.apply_font()
        self._sync_accessible_state()

    def _sync_accessible_state(self):
        state = "Loaded" if self._loaded else "Unloaded — click to reload"
        self.setToolTip("" if self._loaded else state)
        self.setAccessibleDescription(state)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.middle_clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def apply_font(self):
        """Top tab-name type — shared "tabs.names" font group."""
        from ui.app_theme import area_font, font_qss
        spec = area_font("tabs.names", 12, 600, size_min=8, size_max=20)
        if self._loaded:
            resting_bg, resting_fg = TAB_LOADED_BG, TAB_LOADED_TEXT
        else:
            resting_bg, resting_fg = TAB_UNLOADED_BG, TAB_UNLOADED_TEXT
        self.setStyleSheet(f"""
            QPushButton {{
                background: {resting_bg};
                color: {resting_fg};
                border: none;
                border-bottom: 2px solid transparent;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 0 14px;
                {font_qss(spec)}
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.05);
            }}
            QPushButton:checked {{
                background: {TAB_SELECTED_BG};
                color: {TAB_SELECTED_TEXT};
                border-bottom: 2px solid {ACCENT};
            }}
            QPushButton:checked:hover {{
                background: {TAB_SELECTED_BG};
                color: {TAB_SELECTED_TEXT};
                border-bottom: 2px solid {ACCENT};
            }}
        """)


class FramelessTitleBar(QWidget):
    """Custom title bar implementing dragging and Chrome tabs.
    
    Uses native window frame when possible for accessibility.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setFixedHeight(42)
        self.setObjectName("FramelessTitleBar")
        self.setAccessibleName("Window title bar")
        # self.setAccessibleRole(Qt.AccessibleRole.TitleBar)
        
        self._drag_pos = None
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(0)
        
        # Brand mark icon (painted from the app theme)
        from ui.widgets.loading_screen import mark_pixmap
        icon_label = QLabel()
        icon_label.setPixmap(mark_pixmap(20))
        icon_label.setFixedSize(24, 24)
        icon_label.setStyleSheet("background: transparent; padding: 0px 6px 0px 0px;")
        layout.addWidget(icon_label)
        
        # Logo — two-tone wordmark matching the brand (Rhema bright, Cast light purple)
        logo = QLabel()
        logo.setAccessibleName("Application name")
        logo.setText(
            '<span style="color: ' + TEXT_PRIMARY + ';">Rhema</span>'
            '<span style="color: ' + ACCENT_LIGHT + ';">Cast</span>'
        )
        logo.setTextFormat(Qt.TextFormat.RichText)
        logo.setStyleSheet("""
            font-size: 13px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: -0.5px;
            padding-right: 16px;
        """)
        layout.addWidget(logo)
        
        # Tabs
        self.tabs_layout = QHBoxLayout()
        self.tabs_layout.setSpacing(0)
        layout.addLayout(self.tabs_layout)
        
        layout.addStretch()
        
        # Window Controls
        ctrl_style = """
            QPushButton {
                background: transparent;
                color: white;
                border: none;
                font-size: 14px;
                padding: 0;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
            }
        """
        
        min_btn = QPushButton("—")
        min_btn.setAccessibleName("Minimize")
        # min_btn.setAccessibleRole(Qt.AccessibleRole.Button)
        min_btn.setFixedSize(44, 32)
        min_btn.setStyleSheet(ctrl_style)
        min_btn.clicked.connect(self.parent_window.showMinimized)
        
        max_btn = QPushButton("□")
        max_btn.setAccessibleName("Maximize")
        # max_btn.setAccessibleRole(Qt.AccessibleRole.Button)
        max_btn.setFixedSize(44, 32)
        max_btn.setStyleSheet(ctrl_style)
        max_btn.clicked.connect(self._toggle_maximize)
        
        close_btn = QPushButton("✕")
        close_btn.setAccessibleName("Close")
        # close_btn.setAccessibleRole(Qt.AccessibleRole.Button)
        close_btn.setFixedSize(48, 32)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: white;
                border: none;
                font-size: 16px;
                padding: 0;
            }}
            QPushButton:hover {{
                background: #dc2626;
            }}
        """)
        close_btn.clicked.connect(self.parent_window.close)
        
        # Align controls to the top right
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(0)
        controls_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        controls_layout.addWidget(min_btn)
        controls_layout.addWidget(max_btn)
        controls_layout.addWidget(close_btn)
        
        layout.addLayout(controls_layout)

    def _toggle_maximize(self):
        if self.parent_window.isMaximized():
            self.parent_window.showNormal()
        else:
            self.parent_window.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.parent_window.move(self.parent_window.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()


class PlaceholderTab(QWidget):
    """A lazily built tab that can also be unloaded back to a placeholder.

    States:
      pending   — never built; the first show builds it.
      loaded    — the real widget is instantiated.
      unloaded  — explicitly released; it is rebuilt only when the operator
                  asks for it again (tab click, menu, or middle-click).

    ``showEvent`` deliberately does *not* rebuild an explicitly unloaded tab:
    the placeholder is already on screen after an unload, and rebuilding it
    there would undo the unload immediately.
    """
    loaded = pyqtSignal(object)  # emits the real widget after every build

    def __init__(self, init_func, parent=None):
        super().__init__(parent)
        self.init_func = init_func
        self._loaded = False
        self._unloaded = False
        self.real_widget = None

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Kept for the life of the placeholder: it is the unloaded face too.
        self.loading_label = QLabel("Loading...")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setWordWrap(True)
        self.loading_label.setStyleSheet(f"color: {TEXT_FAINT}; font-size: 14px;")
        self.layout.addWidget(self.loading_label)

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def is_unloaded(self) -> bool:
        return self._unloaded

    def ensure_loaded(self):
        """Build the real widget if it is pending or explicitly unloaded."""
        if not self._loaded:
            self._load()
        return self.real_widget

    def _load(self):
        widget = self.init_func()
        self.real_widget = widget
        self._loaded = True
        self._unloaded = False
        self.loading_label.hide()
        self.layout.addWidget(widget)
        self.loaded.emit(widget)

    def unload(self) -> bool:
        """Destroy the real widget and show the unloaded face.

        Returns False when there is nothing to release. The caller owns the
        guard checks (unsaved edits, running work) — this method only does
        the mechanical teardown.
        """
        if not self._loaded or self.real_widget is None:
            return False
        widget = self.real_widget
        self.layout.removeWidget(widget)
        widget.hide()
        widget.setParent(None)
        widget.deleteLater()
        self.real_widget = None
        self._loaded = False
        self._unloaded = True
        self.loading_label.setText(
            "Tab unloaded to free resources.\nClick the tab to reload it.")
        self.loading_label.show()
        return True

    def showEvent(self, event):
        if not self._loaded and not self._unloaded:
            self._load()
        super().showEvent(event)


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()

        # Keypresses that arrive while the window is inactive (e.g. the press
        # that reactivates it) are skipped by QShortcut matching — recorded
        # here as (key, modifiers, monotonic) and replayed on activation.
        self._inactive_keypresses: list = []
        self._last_shortcut_at: float = 0.0

        # Accessibility
        self.setWindowTitle("RhemaCast — Sermon Transcription & Verse Display")
        self.setAccessibleName("RhemaCast Main Window")
        self.setAccessibleDescription("Live sermon transcription with verse suggestion and OBS broadcast")
        
        # Frameless window configuration.
        # Deliberately NOT translucent: an RGBA top-level surface forces
        # grayscale antialiasing for every glyph in the window. The window
        # paints an opaque container (no rounded outer corners, no shadow),
        # so dropping WA_TranslucentBackground changes nothing visually and
        # lets Qt take the platform's subpixel text path.
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setMinimumSize(1024, 768)
        self.resize(1280, 800)

        # Set window icon (brand mark, painted from the app theme)
        from ui.widgets.loading_screen import mark_pixmap
        from PyQt6.QtGui import QIcon
        self.setWindowIcon(QIcon(mark_pixmap(64)))
        
        # Focus policy for keyboard navigation
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # Main container with styling
        self.container = QWidget()
        self.container.setStyleSheet(f"""
            QWidget#MainContainer {{
                background-color: {SLATE_950};
                border: 1px solid {BORDER_SUBTLE};
            }}
        """)
        self.container.setObjectName("MainContainer")
        self.setCentralWidget(self.container)
        
        root_layout = QVBoxLayout(self.container)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        
        # 1. Title Bar
        self.title_bar = FramelessTitleBar(self)
        root_layout.addWidget(self.title_bar)
        
        # 1.5 Sub-toolbar (View | Schedule Remote Live Sync)
        self.sub_toolbar = QWidget()
        self.sub_toolbar.setObjectName("SubToolbar")
        
        # The menu row is the ghost variant of the one button language:
        # text until hovered, same height/radius as every other button.
        _greyed_btn_style = button_qss(
            "ghost", padding=f"0 {SPACE_8}px")
        # Start/Stop carries its state in a tone (green ready / red running)
        # AND in the label text, so it never relies on colour alone.
        _service_btn_style = tone_button_qss(SUCCESS)
        
        self.sub_toolbar.setStyleSheet(f"""
            QWidget#SubToolbar {{
                background-color: {SLATE_950};
                border-bottom: 1px solid {BORDER_SUBTLE};
            }}
        """)
        sub_layout = QHBoxLayout(self.sub_toolbar)
        sub_layout.setContentsMargins(SPACE_12, SPACE_4, SPACE_12, SPACE_4)
        sub_layout.setSpacing(SPACE_4)

        # Greyed-out menu items
        for text in ["View"]:
            btn = QPushButton(text)
            btn.setFixedHeight(BUTTON_HEIGHT)
            btn.setStyleSheet(_greyed_btn_style)
            btn.setEnabled(False)
            btn.setToolTip(f"{text} — coming soon")
            sub_layout.addWidget(btn)

        # Schedule button — shows dropdown of available schedules
        self.schedule_btn = QPushButton("Schedule")
        self.schedule_btn.setFixedHeight(BUTTON_HEIGHT)
        self.schedule_btn.setStyleSheet(_greyed_btn_style)
        self.schedule_btn.setEnabled(True)
        self.schedule_btn.setToolTip("Load a schedule (click) or show schedule menu (hold)")
        self.schedule_btn.clicked.connect(self._show_schedule_menu)
        sub_layout.addWidget(self.schedule_btn)
        
        for text in ["Remote", "Live Sync"]:
            btn = QPushButton(text)
            btn.setFixedHeight(BUTTON_HEIGHT)
            btn.setStyleSheet(_greyed_btn_style)
            btn.setEnabled(False)
            btn.setToolTip(f"{text} — coming soon")
            sub_layout.addWidget(btn)
            
        sub_layout.addStretch()
        
        # Start Service button
        self.start_service_btn = QPushButton("Start Service")
        from ui.icons import apply_button
        apply_button(self.start_service_btn, "play")
        self.start_service_btn.setText("Start Service")
        self.start_service_btn.setFixedHeight(BUTTON_HEIGHT)
        self.start_service_btn.setStyleSheet(_service_btn_style)
        self.start_service_btn.setToolTip("Boot all backend threads (Audio, STT, Search, DB Writer, Hardware Monitor)")
        self.start_service_btn.clicked.connect(self._toggle_service)
        sub_layout.addWidget(self.start_service_btn)
        self._service_running = False
        
        root_layout.addWidget(self.sub_toolbar)
        
        # 2. Stacked Widget (Tab content)
        self.stack = QStackedWidget()
        root_layout.addWidget(self.stack, 1)
        
        # 3. Status Bar
        self.status_bar = StatusBar()
        root_layout.addWidget(self.status_bar)
        
        # Add resize grip to bottom right
        grip_layout = QHBoxLayout()
        grip_layout.setContentsMargins(0, 0, 0, 0)
        grip_layout.addStretch()
        grip = QSizeGrip(self)
        grip.setFixedSize(16, 16)
        grip_layout.addWidget(grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        
        # Overlay the grip
        grip_widget = QWidget(self.container)
        grip_widget.setLayout(grip_layout)
        grip_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        root_layout.addWidget(grip_widget)
        
        # Initialize Tabs
        self._tabs = {}
        self._tab_buttons = {}
        self._tab_state = {}
        self._setup_tabs()
        
        # Setup Hotkeys
        self._setup_hotkeys()
        
        # Install app-wide event filter for Alt+Click (add to schedule)
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().installEventFilter(self)
        
        # Phase 10: Operator Consent Gate at boot
        self._check_offline_queue()

    def showEvent(self, event):
        """One-shot: align the menu row with the first tab once the title
        bar's layout has real geometry (the tab's x depends on the logo)."""
        super().showEvent(event)
        if not getattr(self, "_menu_row_aligned", False):
            self._menu_row_aligned = True
            QTimer.singleShot(0, self._align_menu_row)

    def _align_menu_row(self):
        btn = self._tab_buttons.get("SCRIPTURE")
        if btn is None:
            return
        x = btn.mapTo(self.sub_toolbar, QPoint(0, 0)).x()
        layout = self.sub_toolbar.layout()
        if x > 0 and layout is not None:
            layout.setContentsMargins(
                x, SPACE_4, SPACE_12, SPACE_4)

    def _check_offline_queue(self):
        import os
        from cloud.extraction import OFFLINE_QUEUE_PATH
        if os.path.exists(OFFLINE_QUEUE_PATH):
            try:
                with open(OFFLINE_QUEUE_PATH, 'r', encoding='utf-8') as f:
                    lines = [line for line in f if line.strip()]
                if lines:
                    msg = dialogs.MessageDialog(self)
                    msg.setWindowTitle("Offline Extraction Queue")
                    msg.setText(f"{len(lines)} past services pending. Process now or after service?")
                    msg.setStandardButtons(dialogs.Yes | dialogs.No)
                    msg.button(dialogs.Yes).setText("Process Now")
                    msg.button(dialogs.No).setText("After Service")
                    msg.setModal(False) # Non-blocking
                    msg.show()
                    
                    # Prevent garbage collection of the non-blocking message box
                    self._offline_msg = msg
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to check offline queue: {e}")

    def _setup_tabs(self):
        # Tabs: (internal key, display label, group, widget factory).
        # Display tabs (live-output workspaces) lead; core tabs follow,
        # separated in the bar. Future display tabs (Media, Presentation)
        # join the display group; pack gating filters this list.
        # Keys stay UPPER_SNAKE (referenced across main_window, workers,
        # and tests); only labels are user-facing.
        tabs_config = [
            ("SCRIPTURE", "Scriptures", "display", lambda: PresentationTab()),
            ("SLIDES", "Decks", "display", lambda: SlidesTab()),
            ("LIBRARY", "Library", "core", lambda: LibraryTab()),
            ("THEME DESIGNER", "Theme Designer", "core",
             self._init_theme_designer),
            ("SETTINGS", "Settings", "core", lambda: SettingsTab()),
        ]

        seen_core = False
        for i, (key, label, group, init_func) in enumerate(tabs_config):
            if group == "core" and not seen_core:
                seen_core = True
                self.title_bar.tabs_layout.addWidget(self._tab_group_gap())
            # Create content widget
            if key == "SCRIPTURE":
                # Presentation tab is fully loaded immediately
                content = init_func()
                # Connect theme quick-edit from queue panel
                content.queue_panel.theme_edit_requested.connect(self._open_theme_quick_editor)
                # Far-reaching translation rename cascade
                content.browser_panel.translation_renamed.connect(self._on_translation_renamed)
            else:
                # Other tabs are lazy-loaded Placeholders
                content = PlaceholderTab(init_func)
                # Every build (first load or reload) re-wires its owner.
                content.loaded.connect(
                    lambda widget, k=key: self._on_tab_content_loaded(k, widget))
            self.stack.addWidget(content)
            self._tabs[key] = content

            # Create tab button. Only Scriptures exists at startup; the lazy
            # tabs start in the unloaded/grey state until first shown.
            btn = ChromeTab(label, is_active=(i == 0),
                            loaded=(key == "SCRIPTURE"))
            # Create a closure to capture the index
            btn.clicked.connect(lambda checked, idx=i, n=key: self._switch_tab(idx, n))
            btn.middle_clicked.connect(lambda k=key: self._toggle_tab_loaded(k))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, k=key, b=btn: self._show_tab_menu(k, b.mapToGlobal(pos)))

            # Add container to align tabs to the bottom of the title bar
            btn_layout = QVBoxLayout()
            btn_layout.setContentsMargins(0, 0, 0, 0)
            btn_layout.addStretch()
            btn_layout.addWidget(btn)

            tab_container = QWidget()
            tab_container.setLayout(btn_layout)

            self.title_bar.tabs_layout.addWidget(tab_container)
            self._tab_buttons[key] = btn

    @staticmethod
    def _tab_group_gap() -> QWidget:
        """Breathing room between display tabs and core tabs.

        A painted vertical rule used to sit here; against the chrome it read
        as a stray divider, so the group boundary is spacing now (token
        scale) and the tabs alone carry the grouping.
        """
        gap = QWidget()
        gap.setFixedWidth(SPACE_16)
        gap.setStyleSheet("background: transparent;")
        return gap

    def _switch_tab(self, index: int, name: str):
        # Update button states
        for btn_name, btn in self._tab_buttons.items():
            btn.setChecked(btn_name == name)
            
        # Hide sub-toolbar for tabs that don't need it
        # (SLIDES keeps it: same View/Schedule/Remote/LiveSync + Start Service strip)
        self.sub_toolbar.setVisible(name not in ("LIBRARY", "SETTINGS"))

        # A click is an explicit request for content: build a pending tab or
        # rebuild an explicitly unloaded one before it is presented.
        target = self.stack.widget(index)
        if isinstance(target, PlaceholderTab):
            target.ensure_loaded()

        # Switch stack
        # Fresh frame first: give the incoming tab a head start on
        # committing a current frame (idempotent re-push; showEvent
        # repeats it as belt-and-suspenders).
        resync = getattr(target, "resync_screens", None)
        if callable(resync):
            try:
                resync()
            except Exception as e:
                logger.warning(f"Screen resync before tab switch failed: {e}")
        self.stack.setCurrentIndex(index)

    # ── Tab unloading (Firefox-style) ───────────────────────────────────
    #
    # Only tabs whose whole state is either disposable or restorable may be
    # released. The two display workspaces are deliberately excluded: their
    # objects own the live-output stepping ops and the STT/worker bindings,
    # so destroying them would detach running functionality, not just a view.

    _TAB_UNLOAD_BLOCKERS = {
        "SCRIPTURE": (
            "Scriptures cannot be unloaded: it owns the STT start/stop "
            "controls, verse stepping, and the live scripture hotkeys. "
            "Unloading it would detach those from the running service."
        ),
        "SLIDES": (
            "Decks cannot be unloaded: it owns the live deck display and "
            "its prev/next stepping. A live deck would stop responding."
        ),
    }

    def _on_tab_content_loaded(self, key: str, widget):
        """A placeholder just built its real widget (first load or reload)."""
        self._set_tab_loaded_visual(key, True)
        state = self._tab_state.pop(key, None)
        if state:
            restore = getattr(widget, "restore_state", None)
            if callable(restore):
                try:
                    restore(state)
                except Exception:
                    logger.exception("Failed to restore %s tab state", key)
        if key == "SETTINGS":
            self._on_settings_tab_loaded(widget)

    def _set_tab_loaded_visual(self, key: str, loaded: bool):
        btn = self._tab_buttons.get(key)
        if btn is not None:
            btn.set_loaded(loaded)

    def _can_unload_tab(self, key: str):
        """Return (allowed, reason). Empty reason means nothing to report."""
        blocker = self._TAB_UNLOAD_BLOCKERS.get(key)
        if blocker:
            return False, blocker
        content = self._tabs.get(key)
        if not isinstance(content, PlaceholderTab):
            return False, "This tab has no unloadable content."
        if not content.is_loaded:
            return False, ""
        real = content.real_widget
        guard = getattr(real, "can_unload", None)
        if callable(guard):
            try:
                result = guard()
                if isinstance(result, tuple):
                    return bool(result[0]), str(result[1] or "")
                if not result:
                    return False, "This tab cannot be unloaded right now."
            except Exception:
                logger.exception("Unload guard failed for %s", key)
                return False, "This tab cannot be unloaded right now."
        return True, ""

    def _unload_tab(self, key: str) -> bool:
        """Release a tab's view if its guard allows it."""
        allowed, reason = self._can_unload_tab(key)
        if not allowed:
            if reason:
                dialogs.information(self, "Cannot unload tab", reason)
            return False
        content = self._tabs.get(key)
        real = content.real_widget
        # Persist the small amount of view state worth carrying across.
        current = getattr(real, "current_state", None)
        if callable(current):
            try:
                self._tab_state[key] = current()
            except Exception:
                logger.exception("Failed to save %s tab state", key)
        if key == "THEME DESIGNER" and getattr(
                self, "_theme_designer_tab", None) is real:
            self._theme_designer_tab = None
        if not content.unload():
            return False
        self._set_tab_loaded_visual(key, False)
        return True

    def _toggle_tab_loaded(self, key: str):
        """Middle-click: unload a loaded tab, load an unloaded one."""
        if key in self._TAB_UNLOAD_BLOCKERS:
            self._unload_tab(key)   # explains why it stays loaded
            return
        content = self._tabs.get(key)
        if isinstance(content, PlaceholderTab) and content.is_loaded:
            self._unload_tab(key)
            return
        self._switch_tab(list(self._tabs.keys()).index(key), key)

    def _show_tab_menu(self, key: str, global_pos):
        from PyQt6.QtWidgets import QMenu
        content = self._tabs.get(key)
        menu = QMenu(self)
        menu.setStyleSheet(menu_qss())
        if isinstance(content, PlaceholderTab) and not content.is_loaded:
            label = "Reload Tab" if content.is_unloaded else "Load Tab"
            action = menu.addAction(label)
            action.triggered.connect(
                lambda: self._switch_tab(list(self._tabs.keys()).index(key), key))
        else:
            action = menu.addAction("Unload Tab")
            action.triggered.connect(lambda: self._unload_tab(key))
        menu.exec(global_pos)

    def _on_translation_renamed(self, canonical: str):
        """Cascade a translation rename across schedules and screens.

        Data (mapping, schedule files, history rows) was already rewritten by
        bible_service.rename_translation; this syncs the live model, views
        and current screens.
        """
        from core.bible_service import get_last_rename
        info = get_last_rename()
        if not info or info[0] != canonical:
            return
        _, old_display, new_display = info
        if old_display == new_display:
            return
        logger.info(f"Translation renamed: {canonical} {old_display!r} → {new_display!r}")

        # In-memory schedule: reload the rewritten file when clean, else
        # patch items in place (keeps unsaved user edits). Views on both
        # tabs rebuild via items_changed either way.
        try:
            from core.schedule_model import schedule_model
            if schedule_model.is_modified():
                schedule_model.rename_translation_in_model(old_display, new_display)
            elif schedule_model.current_file:
                schedule_model.load(schedule_model.current_file)
        except Exception as e:
            logger.warning(f"Schedule rename sync failed: {e}")

        # Re-render the ACTIVE tab's screens (shared state → all screens,
        # operator + OBS, follow from the single republish).
        try:
            tab = self._active_workspace_tab()
            if tab is not None and hasattr(tab, "refresh_display_names"):
                tab.refresh_display_names(old_display, new_display)
        except Exception as e:
            logger.warning(f"Screen rename refresh failed: {e}")

    def _on_settings_tab_loaded(self, widget):
        """Connect hotkey editor and font size signals once the Settings tab finishes lazy-loading."""
        if hasattr(widget, '_hotkey_editor'):
            widget._hotkey_editor.bindings_changed.connect(self._on_hotkey_bindings_changed)
        if hasattr(widget, 'font_size_changed'):
            widget.font_size_changed.connect(self._on_font_size_changed)
        if hasattr(widget, 'bible_font_changed'):
            widget.bible_font_changed.connect(self._on_bible_font_changed)

    def _on_font_size_changed(self, text_size: int, ref_size: int):
        """Propagate font size changes to the browser panel for live preview."""
        pres_tab = self._tabs.get("SCRIPTURE")
        if pres_tab and hasattr(pres_tab, "browser_panel"):
            pres_tab.browser_panel.update_verse_font_sizes(text_size, ref_size)

    def _on_bible_font_changed(self):
        """Propagate family/weight changes (sizes ride along — the panel
        re-reads all six Bible font keys)."""
        pres_tab = self._tabs.get("SCRIPTURE")
        if pres_tab and hasattr(pres_tab, "browser_panel"):
            pres_tab.browser_panel.update_verse_fonts()
        
    def _init_theme_designer(self) -> QWidget:
        from ui.tabs.theme_designer_tab import ThemeDesignerTab
        tab = ThemeDesignerTab()
        self._theme_designer_tab = tab
        return tab

    def _open_theme_quick_editor(self, theme_name: str):
        from ui.widgets.lite_designer.lite_designer import LiteDesigner
        editor = LiteDesigner(parent=self, theme_name=theme_name,
                              default_tab="theme", freeform_enabled=False)
        editor.edit_full_requested.connect(self._open_full_designer)
        editor.theme_saved.connect(self._on_theme_saved)
        editor.show()

    def _open_full_designer(self, theme_name: str):
        # Switch to the Theme Designer tab
        for idx, name in enumerate(self._tabs.keys()):
            if name == "THEME DESIGNER":
                self._switch_tab(idx, name)
                break
        # Set the theme in the designer tab
        if hasattr(self, '_theme_designer_tab') and self._theme_designer_tab:
            self._theme_designer_tab.set_theme(theme_name)

    def _on_theme_saved(self, theme_name: str):
        # Reload themes in the presentation tab's queue panel
        pres_tab = self._tabs.get("SCRIPTURE")
        if pres_tab and hasattr(pres_tab, 'queue_panel'):
            pres_tab.queue_panel._themes_panel.reload()

    @staticmethod
    def _press_in_schedule(obj) -> bool:
        """True when a press target sits inside a schedule list (matched
        by class name to avoid importing panels here)."""
        w = obj
        while w is not None:
            if type(w).__name__ == "SchedulePanel":
                return True
            w = w.parentWidget() if hasattr(w, "parentWidget") else None
        return False

    @staticmethod
    def _cursor_in_schedule() -> bool:
        """True when the mouse cursor itself sits over a schedule list
        (hit-test, independent of which object got the press event)."""
        try:
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtGui import QCursor
            return MainWindow._press_in_schedule(
                QApplication.widgetAt(QCursor.pos()))
        except Exception:
            return False

    def eventFilter(self, obj, event):
        """App-wide event filter: intercept Alt+Click and defocus search panels."""
        from PyQt6.QtCore import QEvent as _QE
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        if _KEYTAP_ENABLED and event.type() in (_QE.Type.KeyPress, _QE.Type.KeyRelease):
            try:
                from PyQt6.QtWidgets import QApplication as _QA
                _fw = _QA.focusWidget()
                logger.info(
                    "KEYTAP %s key=%s mods=%s spont=%s focus=%s obj=%s active=%s",
                    "KeyPress" if event.type() == _QE.Type.KeyPress else "KeyRelease",
                    event.key(), event.modifiers(),
                    event.spontaneous(),
                    type(_fw).__name__ if _fw is not None else None,
                    type(obj).__name__, self.isActiveWindow())
            except Exception:
                pass

        if _KEYTAP_ENABLED and event.type() in (
                _QE.Type.MouseButtonPress, _QE.Type.MouseButtonDblClick,
                _QE.Type.FocusIn, _QE.Type.FocusOut):
            try:
                from PyQt6.QtWidgets import QApplication as _QA2
                from PyQt6.QtCore import QTimer as _QT2
                _fw2 = _QA2.focusWidget()
                _kind = { _QE.Type.MouseButtonPress: "MousePress",
                    _QE.Type.MouseButtonDblClick: "MouseDblClick",
                    _QE.Type.FocusIn: "FocusIn",
                    _QE.Type.FocusOut: "FocusOut" }.get(event.type(), "?")
                _chain = type(obj).__name__
                try:
                    _p = obj.parent()
                    if _p is not None:
                        _chain += "<" + type(_p).__name__
                        _gp = _p.parent()
                        if _gp is not None:
                            _chain += "<" + type(_gp).__name__
                except Exception:
                    pass
                try:
                    _aw = _QA2.activeWindow()
                    _awname = type(_aw).__name__ if _aw is not None else None
                except Exception:
                    _awname = "?"
                try:
                    _modal = _QA2.activeModalWidget()
                    _modalname = type(_modal).__name__ \
                        if _modal is not None else None
                except Exception:
                    _modalname = "?"
                logger.info(
                    "KEYTAP %s button=%s spont=%s focus=%s obj=%s "
                    "active=%s activeWin=%s modal=%s",
                    _kind,
                    getattr(event, "button", lambda: None)(),
                    event.spontaneous(),
                    type(_fw2).__name__ if _fw2 is not None else None,
                    _chain, self.isActiveWindow(), _awname, _modalname)
                if event.type() == _QE.Type.MouseButtonPress:
                    _QT2.singleShot(0, lambda: logger.info(
                        "KEYTAP post-press focus=%s active=%s",
                        (lambda w: type(w).__name__ if w is not None else None)(
                            _QA2.focusWidget()), self.isActiveWindow()))
            except Exception:
                pass

        # Ctrl release ends slide section-hop navigation — but only if a full
        # Ctrl+Arrow combo started one; a bare Ctrl press/release never arms it.
        if event.type() == _QE.Type.KeyRelease:
            if event.key() == Qt.Key.Key_Control and not event.isAutoRepeat():
                self._end_song_nav_if_any()
                self._maybe_release_focus_from_textbox()
        elif event.type() == _QE.Type.KeyPress and not event.isAutoRepeat():
            # A Ctrl tap only counts when Ctrl was pressed ALONE: Ctrl+A
            # followed by Ctrl+C (select all, copy) must not read as a
            # double tap and drop the operator's focus mid-copy.
            if event.key() == Qt.Key.Key_Control:
                self._ctrl_tap_clean = True
            elif getattr(self, "_ctrl_tap_clean", False):
                self._ctrl_tap_clean = False

        # Presses arriving while the window is inactive are skipped by
        # QShortcut matching (and must not arm song-nav either) — record them
        # for replay on activation instead of acting now. Skipped entirely
        # while an app-modal dialog owns input (those keys belong to it).
        if event.type() == _QE.Type.KeyPress and not event.isAutoRepeat():
            try:
                from PyQt6.QtWidgets import QApplication as _QA2
                if (not self.isActiveWindow()
                        and _QA2.activeModalWidget() is None):
                    now = time.monotonic()
                    pending = getattr(self, "_inactive_keypresses", [])
                    self._inactive_keypresses = [
                        (k, m, t) for (k, m, t) in pending if now - t < 1.0]
                    self._inactive_keypresses.append(
                        (event.key(), event.modifiers(), now))
            except Exception:
                pass

        # Built-in chords live here, not in DEFAULT_BINDINGS, because they
        # are deliberately NOT editable (see BUILT_IN_KEYS in Settings).
        if event.type() == _QE.Type.KeyPress:
            if self.isActiveWindow() and self._maybe_display_tab_chord(event):
                return True

        # Slide section-hop combos are intercepted here (not via QShortcut):
        # the app filter runs before delivery, so QWebEngineView viewports
        # can't swallow these as browser back/forward first.
        if event.type() == _QE.Type.KeyPress:
            if self.isActiveWindow() and self._maybe_song_nav_key(event):
                if _KEYTAP_ENABLED:
                    logger.info("KEYTAP song-nav consumed key=%s",
                                event.key())
                return True

        # Ctrl+S saves the schedule. Same interception path (and for the same
        # reason) as the section hops above — Chromium owns Ctrl+S inside the
        # display view, so a QShortcut would never fire there.
        if event.type() == _QE.Type.KeyPress:
            if self.isActiveWindow() and self._maybe_save_schedule_key(event):
                if _KEYTAP_ENABLED:
                    logger.info("KEYTAP save-schedule consumed key=%s",
                                event.key())
                return True

        if event.type() == _QE.Type.MouseButtonPress:
            # Client-side activation recovery: if the compositor never
            # activates this window (presses arrive, active stays False,
            # focus can never transfer), claim active state ourselves so
            # in-app focus routing works. Only when this press targets
            # the main window itself — popups/menus manage their own.
            # No-op whenever the window is already active.
            try:
                from PyQt6.QtWidgets import QApplication as _QA5
                _tl = obj.window() if hasattr(obj, "window") else None
                if _tl is not None and _tl is self \
                        and not self.isActiveWindow():
                    _QA5.setActiveWindow(self)
            except Exception:
                pass
            if (event.button() == Qt.MouseButton.LeftButton
                    and event.modifiers() & Qt.KeyboardModifier.AltModifier):
                # ...unless the press is inside a schedule list itself:
                # Alt+clicking a schedule item would re-add the current
                # selection as a duplicate. Let it through instead.
                # Both the event target and the cursor hit-test count:
                # either one inside a schedule panel vetoes the hotkey.
                _in_sched = MainWindow._press_in_schedule(obj) \
                    or MainWindow._cursor_in_schedule()
                if _KEYTAP_ENABLED:
                    logger.info("KEYTAP alt-add %s",
                                "skipped-in-schedule" if _in_sched
                                else "fired")
                if not _in_sched:
                    self._hotkey_add_to_schedule()
                    # consume — don't let Qt do alt-click text selection
                    return True
            # Defocus search panels on click outside them
            if event.button() == Qt.MouseButton.LeftButton:
                self._defocus_search_if_outside(obj)
        elif event.type() == _QE.Type.MouseButtonDblClick:
            if event.button() == Qt.MouseButton.LeftButton:
                self._defocus_search_if_outside(obj)
        
        # Prevent QWebEngineView from consuming ShortcutOverride events
        # This allows QShortcut (parented to MainWindow) to work after Alt+Tab
        if event.type() == _QE.Type.ShortcutOverride:
            # Check if the object is a QWebEngineView or a child of one
            current = obj
            while current is not None:
                if isinstance(current, QWebEngineView):
                    # Reject the event to prevent QWebEngineView from consuming it
                    event.ignore()
                    return True
                current = current.parent() if hasattr(current, 'parent') else None
        
        return super().eventFilter(obj, event)

    def _defocus_search_if_outside(self, widget):
        """Clear focus from search panels if the clicked widget is outside them."""
        pres = self._tabs.get("SCRIPTURE")
        if not pres:
            return
        qpanel = pres.queue_panel
        if not qpanel:
            return

        # Check if click is inside either search panel
        for panel_attr in ('_fts_search_panel', '_fuzzy_search_panel'):
            panel = getattr(qpanel, panel_attr, None)
            if panel is None:
                continue
            # Walk up from clicked widget to see if it's inside this panel
            w = widget
            while w is not None:
                if w is panel or w is panel.query_input:
                    return  # inside search panel — don't defocus
                w = w.parentWidget() if hasattr(w, 'parentWidget') else None

        # Click is outside all search panels — defocus
        for panel_attr in ('_fts_search_panel', '_fuzzy_search_panel'):
            panel = getattr(qpanel, panel_attr, None)
            if panel is not None:
                panel.query_input.clearFocus()

    def event(self, e):
        from PyQt6.QtCore import QEvent as _QE, QTimer
        from ui.widgets.hotkey_editor import KeyboardHandler

        # After Alt+Tab or switching back, Qt doesn't restore keyboard focus
        # to MainWindow, so QShortcut (parented to self) won't fire until a
        # second keypress. Grab focus on window activation.
        if e.type() == _QE.Type.WindowActivate:
            self._resync_modifiers()
            self._replay_inactive_presses()
            if _KEYTAP_ENABLED:
                try:
                    from PyQt6.QtWidgets import QApplication as _QA2
                    _fw2 = _QA2.focusWidget()
                    logger.info("KEYTAP WindowActivate focus=%s pending=%d",
                                type(_fw2).__name__ if _fw2 is not None else None,
                                len(getattr(self, "_inactive_keypresses", [])))
                except Exception:
                    pass
            # Use a short delay to ensure the window is fully activated
            # before attempting to set focus
            def _ensure_focus():
                # Only set focus if no other widget currently has it
                # This prevents stealing focus from text inputs, etc.
                from PyQt6.QtWidgets import QApplication
                focused = QApplication.focusWidget()
                if focused is None or not focused.isEnabled():
                    self.setFocus()
            QTimer.singleShot(10, _ensure_focus)

        # Qt intercepts F1 for "What's This?" help. During hotkey capture mode,
        # accept the ShortcutOverride so the key reaches our KeyboardHandler
        # instead of being eaten by Qt's help system. During normal operation,
        # let it through so QShortcut can match it.
        if (e.type() == _QE.Type.ShortcutOverride
                and e.key() == Qt.Key.Key_F1
                and KeyboardHandler._target is not None):
            e.accept()
            return True
        return super().event(e)

    def _setup_hotkeys(self):
        """Setup hotkeys from saved bindings or defaults."""
        self._load_hotkey_bindings()
        self._create_shortcuts()
        
        # Connect to KeyboardHandler capture signals to disable shortcuts during capture
        from ui.widgets.hotkey_editor import KeyboardHandler
        KeyboardHandler._instance = KeyboardHandler()
        KeyboardHandler._instance.capture_started.connect(self._disable_shortcuts)
        KeyboardHandler._instance.capture_finished.connect(self._enable_shortcuts)

        # Losing focus (Alt+Tab) swallows the Ctrl release — finalize any
        # in-progress slide navigation instead of stranding it.
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt as _Qt
        _app = QApplication.instance()
        if _app is not None:
            _app.applicationStateChanged.connect(self._on_app_state_changed)

    def _on_app_state_changed(self, state):
        from PyQt6.QtCore import Qt as _Qt
        if state != _Qt.ApplicationState.ApplicationActive:
            self._end_song_nav_if_any()

    def _load_hotkey_bindings(self):
        """Load saved bindings from settings database."""
        from core.database import get_setting
        import json
        saved = get_setting("hotkeys.bindings", "{}")
        try:
            self._hotkey_bindings = json.loads(saved)
        except Exception:
            self._hotkey_bindings = {}
        
        # Defaults (single source: _HOTKEY_DEFAULTS)
        for action, key in self._HOTKEY_DEFAULTS.items():
            if action not in self._hotkey_bindings:
                self._hotkey_bindings[action] = key
        # Prune fossils: saved action IDs from older schemas (and only those —
        # a user's chosen keys for live actions are sacred).
        pruned = [a for a in list(self._hotkey_bindings)
                  if a not in self._HOTKEY_DEFAULTS]
        if pruned:
            for a in pruned:
                del self._hotkey_bindings[a]
            logger.info(f"Pruned obsolete hotkey bindings: {pruned}")
            try:
                import json
                from core.database import set_setting
                set_setting("hotkeys.bindings",
                            json.dumps(self._hotkey_bindings))
            except Exception:
                pass

    def _create_shortcuts(self):
        """Create QShortcuts from current bindings."""
        # Clear existing shortcuts
        for shortcut in getattr(self, '_shortcuts', []):
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self._shortcuts = []

        # Map action IDs to handler methods.
        # NOTE: song_prev/next_section are NOT here — QShortcuts for those
        # combos never fire when focus sits inside a QWebEngineView (Chromium
        # reserves Ctrl+Left/Right as back/forward). They are intercepted in
        # eventFilter() below, which runs before delivery, instead.
        action_handlers = {
            "clear_recall": self._hotkey_clear,
            "fts_search": self._hotkey_fts_search,
            "fuzzy_search": self._hotkey_fuzzy_search,
            "next_verse": self._hotkey_next_verse,
            "prev_verse": self._hotkey_prev_verse,
            "next_schedule_item": self._hotkey_next_schedule_item,
            "prev_schedule_item": self._hotkey_prev_schedule_item,
            "toggle_transcription": self._hotkey_toggle_transcription,
            "add_to_schedule": self._hotkey_add_to_schedule,
            "double_click": self._hotkey_double_click,
            "navigate_scripture": self._hotkey_navigate_scripture,
            "deck_search": self._hotkey_deck_search,
        }
        # Kept for replaying presses lost to window inactivation (see below).
        self._hotkey_actions = dict(action_handlers)

        for action_id, key in self._hotkey_bindings.items():
            if action_id in action_handlers and key and not QKeySequence(key).isEmpty():
                shortcut = QShortcut(QKeySequence(key), self)
                shortcut.activated.connect(action_handlers[action_id])
                shortcut.activated.connect(
                    lambda _=False: setattr(self, "_last_shortcut_at", time.monotonic()))
                if _KEYTAP_ENABLED:
                    shortcut.activated.connect(
                        lambda _=False, a=action_id: logger.info(f"KEYTAP shortcut fired: {a}"))
                self._shortcuts.append(shortcut)

        # Translation shortcuts (stored as trans_<VERSION> in bindings)
        import json
        from core.database import get_setting
        saved = get_setting("hotkeys.trans_bindings", "[]")
        try:
            trans_bindings = json.loads(saved)
        except Exception:
            trans_bindings = []

        for version, key in trans_bindings:
            if key:
                shortcut = QShortcut(QKeySequence(key), self)
                shortcut.activated.connect(lambda v=version: self._hotkey_switch_translation(v))
                self._shortcuts.append(shortcut)
        logger.info(f"Hotkeys active: {len(self._shortcuts)}")

    _HOTKEY_DEFAULTS = {
        "clear_recall": "Esc",
        "fts_search": "Ctrl+Shift+F",
        "fuzzy_search": "Ctrl+Shift+S",
        "next_verse": "Right",
        "prev_verse": "Left",
        "next_schedule_item": "Alt+Right",
        "prev_schedule_item": "Alt+Left",
        "toggle_transcription": "F7",
        "add_to_schedule": "Alt+Return",
        "save_schedule": "Ctrl+S",
            "double_click": "F1",
            "song_prev_section": "Ctrl+Left",
            "song_next_section": "Ctrl+Right",
            "navigate_scripture": "Ctrl+N",
            "deck_search": "Ctrl+G",
    }

    # Tabs that own a live output — and therefore a schedule. Everything
    # else (Library, Theme Designer, Settings) keeps Ctrl+S to itself.
    _DISPLAY_TAB_KEYS = ("SCRIPTURE", "SLIDES", "MEDIA", "PRESENTATION")

    def _on_hotkey_bindings_changed(self, bindings: dict):
        """Called when user changes bindings in Settings."""
        # Merge over defaults: the editor only sends previously-saved keys,
        # so a bare replace would permanently kill shortcuts for actions the
        # user never customized (e.g. newly added ones).
        import json
        from core.database import set_setting
        merged = dict(self._HOTKEY_DEFAULTS)
        merged.update({k: v for k, v in (bindings or {}).items() if k in merged})
        self._hotkey_bindings = merged
        try:
            set_setting("hotkeys.bindings", json.dumps(merged))
        except Exception:
            pass
        self._create_shortcuts()
        logger.info(f"Hotkeys rebuilt: {len(self._shortcuts)} active")

    def _disable_shortcuts(self):
        """Disable all shortcuts during hotkey capture."""
        if _KEYTAP_ENABLED:
            logger.info("KEYTAP shortcuts disabled (capture started)")
        for shortcut in getattr(self, '_shortcuts', []):
            shortcut.setEnabled(False)

    def _enable_shortcuts(self):
        """Re-enable all shortcuts after hotkey capture."""
        if _KEYTAP_ENABLED:
            logger.info("KEYTAP shortcuts re-enabled (capture finished)")
        for shortcut in getattr(self, '_shortcuts', []):
            shortcut.setEnabled(True)

    def _defocus_navigator(self):
        """Defocus the predictive scripture input fields if they have focus."""
        from PyQt6.QtWidgets import QApplication
        focused = QApplication.focusWidget()
        if focused is None:
            return
        # Check if focused widget is part of the predictive input
        pres_tab = self._tabs.get("SCRIPTURE")
        if pres_tab and hasattr(pres_tab, "browser_panel"):
            browser = pres_tab.browser_panel
            if hasattr(browser, "predictive_input"):
                pi = browser.predictive_input
                if focused in (pi.book_input, pi.chapter_input, pi.verse_input):
                    self.setFocus()

    def _maybe_display_tab_chord(self, event) -> bool:
        """Ctrl+Alt+Left/Right: cycle the DISPLAY tabs, wrapping around.

        Fixed on purpose (not in Settings), like the double-tap Ctrl: these
        are navigation reflexes, and an operator mid-service should not be
        able to lose them to a stray rebind. Only display tabs take part —
        Settings/Library/History are not on the path.
        """
        from PyQt6.QtCore import Qt as _Qt
        mods = event.modifiers()
        if not (mods & _Qt.KeyboardModifier.ControlModifier):
            return False
        if not (mods & _Qt.KeyboardModifier.AltModifier):
            return False
        if event.key() == _Qt.Key.Key_Left:
            step = -1
        elif event.key() == _Qt.Key.Key_Right:
            step = 1
        else:
            return False
        if event.isAutoRepeat():
            return True          # swallow the repeat, never wrap twice
        self._cycle_display_tab(step)
        return True

    def _cycle_display_tab(self, step: int) -> str | None:
        """Move `step` through the display tabs, wrapping at both ends."""
        display_keys = [k for k in self._tabs
                        if k in self._DISPLAY_TAB_KEYS]
        if not display_keys:
            return None
        names = list(self._tabs.keys())
        current = self.stack.currentIndex()
        current_key = (names[current] if 0 <= current < len(names) else None)
        if current_key in display_keys:
            idx = (display_keys.index(current_key) + step) % len(display_keys)
        else:
            # Arrived from a non-display tab (Settings/History/Library):
            # continue in the direction of travel to the next display tab,
            # wrapping — not "jump to an end", which would feel like the
            # chord skipped the tab the operator was on.
            position = names.index(current_key) if current_key in names else 0
            idx = None
            for offset in range(1, len(names) + 1):
                probe = (position + step * offset) % len(names)
                if names[probe] in display_keys:
                    idx = display_keys.index(names[probe])
                    break
            if idx is None:
                idx = 0
        key = display_keys[idx]
        self._switch_tab(names.index(key), key)
        logger.info(f"Display tab cycled to {key}")
        return key

    def _maybe_release_focus_from_textbox(self):
        """Double-tap Ctrl: hand the keyboard back to the operator's arrows.

        A focused search box swallows Left/Right for caret movement, so
        prev/next stop working while typing. Tapping Ctrl twice drops the
        focus and the arrow keys drive the display again — the tab decides
        what stepping means (the display state routes the step to the tab
        that owns the displayed content).
        """
        clean = getattr(self, "_ctrl_tap_clean", False)
        self._ctrl_tap_clean = False
        if not clean:
            # Ctrl was part of a combo (Ctrl+C, Ctrl+Tab, …): not a tap.
            return
        now = time.monotonic()
        last = getattr(self, "_last_ctrl_release_at", 0.0)
        self._last_ctrl_release_at = now
        if now - last > _CTRL_DOUBLE_TAP_SECONDS:
            return
        # Consume the pair so a triple tap doesn't fire twice.
        self._last_ctrl_release_at = 0.0
        from PyQt6.QtWidgets import (QAbstractSpinBox, QApplication,
                                     QLineEdit, QPlainTextEdit, QTextEdit)
        focused = QApplication.focusWidget()
        if not isinstance(focused, (QLineEdit, QTextEdit, QPlainTextEdit,
                                    QAbstractSpinBox)):
            return
        focused.clearFocus()
        tab = self._active_workspace_tab()
        if tab is not None:
            tab.setFocus(Qt.FocusReason.OtherFocusReason)
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        logger.info("Double-tap Ctrl: focus released from textbox")

    def _active_workspace_tab(self):
        """Return the workspace tab (SCRIPTURE or SLIDES) currently shown.

        Both expose live_preview with next_verse/prev_verse signals, so
        arrow-key stepping follows the operator's context.
        """
        try:
            names = list(self._tabs.keys())
            current = self.stack.currentIndex()
            if 0 <= current < len(names):
                tab = self._tabs[names[current]]
                # Unwrap lazy placeholder if already loaded
                real = getattr(tab, "real_widget", None)
                if real is not None and getattr(tab, "_loaded", False):
                    tab = real
                if hasattr(tab, "live_preview"):
                    return tab
        except Exception:
            pass
        return self._tabs.get("SCRIPTURE")

    def _active_display_tab(self):
        """Return the DISPLAY tab (SCRIPTURE/SLIDES) currently shown, or None.

        Unlike _active_workspace_tab() there is no fallback: on Library,
        Theme Designer or Settings there is no schedule to act on, not "the
        scripture tab's one".
        """
        try:
            names = list(self._tabs.keys())
            current = self.stack.currentIndex()
            if not (0 <= current < len(names)):
                return None
            if names[current] not in self._DISPLAY_TAB_KEYS:
                return None
            tab = self._tabs[names[current]]
            # Unwrap lazy placeholder if already loaded
            real = getattr(tab, "real_widget", None)
            if real is not None and getattr(tab, "_loaded", False):
                tab = real
            return tab
        except Exception:
            return None

    def _save_active_schedule(self) -> bool:
        """Ctrl+S: save the schedule. False when this tab has none.

        Both workspace tabs render the same shared model, so a lazily built
        display tab that has no SchedulePanel yet still saves through the
        loaded one — never through a second, divergent copy.
        """
        tab = self._active_display_tab()
        if tab is None:
            return False
        panel = getattr(tab, "schedule_panel", None)
        if panel is None:
            panel = getattr(self._tabs.get("SCRIPTURE"), "schedule_panel", None)
        if panel is None:
            return False
        # A never-saved empty schedule has nothing to save: don't pop the
        # file dialog for it.
        if not panel.current_file and not panel.get_schedule_data():
            return True
        if panel.save_schedule():
            logger.info("Schedule saved (Ctrl+S)")
        return True

    def _hotkey_capture_active(self) -> bool:
        """True while Settings is capturing a chord — hotkeys must stay out."""
        from ui.widgets.hotkey_editor import KeyboardHandler
        kh = KeyboardHandler._instance
        return (kh is not None
                and getattr(kh, "_target", None) is not None
                and getattr(kh._target, "_capturing", False))

    def _maybe_save_schedule_key(self, event) -> bool:
        """Ctrl+S saves the schedule — display tabs only. True if consumed.

        Intercepted here (not as a QShortcut) for the same reason as the
        slide section hops: a focused QWebEngineView claims Ctrl+S as
        Chromium's "save page" before shortcut matching ever sees it.
        """
        if self._hotkey_capture_active():
            return False
        combo = self._binding_combo("save_schedule")
        if combo is None:
            return False
        if event.key() != combo[0] or event.modifiers() != combo[1]:
            return False
        if self._active_display_tab() is None:
            return False          # core tab: Ctrl+S is not ours to consume
        return self._save_active_schedule()

    def _hotkey_next_verse(self):
        self._defocus_navigator()
        tab = self._active_workspace_tab()
        if tab and hasattr(tab, "live_preview"):
            tab.live_preview.next_verse.emit()

    def _hotkey_prev_verse(self):
        self._defocus_navigator()
        tab = self._active_workspace_tab()
        if tab and hasattr(tab, "live_preview"):
            tab.live_preview.prev_verse.emit()

    def _hotkey_prev_schedule_item(self):
        """Alt+Left: step to the previous SCHEDULE item (not the previous
        verse/slide — those belong to the plain Left/Right hotkeys)."""
        tab = self._active_workspace_tab()
        if tab and hasattr(tab, "_step_schedule"):
            tab._step_schedule(-1)

    def _hotkey_next_schedule_item(self):
        """Alt+Right: step to the next schedule item."""
        tab = self._active_workspace_tab()
        if tab and hasattr(tab, "_step_schedule"):
            tab._step_schedule(1)

    def _hotkey_toggle_transcription(self):
        pres_tab = self._tabs.get("SCRIPTURE")
        if pres_tab and hasattr(pres_tab, "stt_panel"):
            if pres_tab.stt_panel.is_recording:
                pres_tab.stt_panel.transcription_stopped.emit()
            else:
                pres_tab.stt_panel.transcription_started.emit()

    def _hotkey_add_to_schedule(self):
        """Global hotkey: add what's selected to the schedule, per active tab.

        SCRIPTURE tab → selected browser verses (existing behavior).
        SLIDES tab → the selected deck (click first to select one under cursor).
        """
        tab = self._active_workspace_tab()
        if tab is None:
            return
        if hasattr(tab, "deck_panel"):
            self._hotkey_add_deck_to_schedule(tab)
        elif hasattr(tab, "browser_panel"):
            self._hotkey_add_verses_to_schedule(tab)

    def _hotkey_add_deck_to_schedule(self, tab):
        """SLIDES path: click at cursor (selects deck/card under it), then queue."""
        self._synth_click_at_cursor()
        deck = None
        if hasattr(tab, "deck_panel"):
            deck = tab.deck_panel.selected_deck()
        if deck and hasattr(tab, "_on_deck_to_schedule"):
            tab._on_deck_to_schedule(dict(deck))

    def _synth_click_at_cursor(self):
        """Synthesize a left press+release at the cursor position."""
        from PyQt6.QtGui import QCursor, QMouseEvent, QPointingDevice
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QPointF

        global_point = QCursor.pos()
        target = QApplication.widgetAt(global_point)
        if not target:
            return

        local_pos = QPointF(target.mapFromGlobal(global_point))
        global_pos = QPointF(global_point)
        device = QPointingDevice.primaryPointingDevice()

        press = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            local_pos, global_pos,
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier, device,
        )
        release = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            local_pos, global_pos,
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier, device,
        )

        QApplication.sendEvent(target, press)
        QApplication.sendEvent(target, release)

    def _hotkey_add_verses_to_schedule(self, pres_tab):
        """SCRIPTURE path: single click at cursor (updates preview) + queue verses."""
        from PyQt6.QtGui import QCursor
        from PyQt6.QtWidgets import QApplication

        global_point = QCursor.pos()
        target = QApplication.widgetAt(global_point)
        if not target:
            return

        # Defocus navigator if cursor is outside it
        if hasattr(pres_tab, "browser_panel"):
            browser = pres_tab.browser_panel
            if hasattr(browser, "predictive_input"):
                pi = browser.predictive_input
                is_over_navigator = False
                w = target
                while w is not None:
                    if w in (pi.book_input, pi.chapter_input, pi.verse_input):
                        is_over_navigator = True
                        break
                    w = w.parentWidget() if hasattr(w, 'parentWidget') else None
                if not is_over_navigator and QApplication.focusWidget() in (pi.book_input, pi.chapter_input, pi.verse_input):
                    self.setFocus()

        self._synth_click_at_cursor()

        # Now add selected verses to schedule
        if hasattr(pres_tab, "browser_panel") and hasattr(pres_tab, "schedule_panel"):
            browser = pres_tab.browser_panel
            selected = browser.get_all_selected_verses()
            if not selected:
                # Fallback to single highlighted verse
                v = browser.get_selected_verse()
                if v:
                    selected = [v]
            for verse_data in selected:
                item_data = {
                    "ref": f"{verse_data.get('book', '')} {verse_data.get('chapter', '')}:{verse_data.get('verse', '')}".strip(),
                    "book": verse_data.get("book", ""),
                    "chapter": verse_data.get("chapter", ""),
                    "verse": verse_data.get("verse", ""),
                    "text": verse_data.get("text", ""),
                    "translation": verse_data.get("translation", browser._current_translation),
                    "theme": pres_tab._current_theme,
                }
                pres_tab.schedule_panel.add_item(item_data)

    @staticmethod
    def _focusable_ancestor(widget):
        """Nearest widget from `widget` up that can take keyboard focus.

        A real double-click gives focus to whatever is under the cursor, so
        the hotkey does the same: that is what moves the panel focus ring
        to the panel the operator deployed into. Returns None when nothing
        in the chain accepts focus.
        """
        from PyQt6.QtWidgets import QWidget
        w = widget
        while isinstance(w, QWidget):
            try:
                if (w.focusPolicy() != Qt.FocusPolicy.NoFocus
                        and w.isEnabled() and w.isVisible()):
                    return w
            except RuntimeError:
                return None
            w = w.parentWidget()
        return None

    def _hotkey_double_click(self):
        """Simulate a mouse double-click at the current cursor position.

        Focus follows the cursor like a real click: the nearest focusable
        ancestor of the widget under the pointer takes focus, so the panel
        focus ring moves to wherever the operator deployed (and next/prev
        hotkeys act on that panel's context).
        """
        from PyQt6.QtGui import QCursor, QMouseEvent, QPointingDevice
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QPointF

        global_point = QCursor.pos()
        target = QApplication.widgetAt(global_point)
        if not target:
            return

        # Real clicks move focus on press; do it before dispatching so the
        # handler sees the same focus state a mouse double-click gives.
        focused = self._focusable_ancestor(target)
        if focused is not None and focused is not QApplication.focusWidget():
            # MouseFocusReason, like a real click: some widgets treat a
            # programmatic focus reason as a different kind of arrival.
            focused.setFocus(Qt.FocusReason.MouseFocusReason)

        local_pos = QPointF(target.mapFromGlobal(global_point))
        global_pos = QPointF(global_point)
        device = QPointingDevice.primaryPointingDevice()

        def _make_event(event_type):
            return QMouseEvent(
                event_type,
                local_pos,
                global_pos,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                device,
            )

        QApplication.sendEvent(target, _make_event(QMouseEvent.Type.MouseButtonPress))
        QApplication.sendEvent(target, _make_event(QMouseEvent.Type.MouseButtonRelease))
        QApplication.sendEvent(target, _make_event(QMouseEvent.Type.MouseButtonDblClick))
        QApplication.sendEvent(target, _make_event(QMouseEvent.Type.MouseButtonRelease))

    def _hotkey_clear(self):
        # Trigger clear/recall on the ACTIVE workspace tab: each tab recalls
        # with its own theme (scripture vs slides). Hardcoding SCRIPTURE here
        # recalled slides with a scripture theme (gold title line).
        tab = self._active_workspace_tab()
        if tab and hasattr(tab, "live_preview"):
            tab.live_preview.clear_recall.emit()

    def _hotkey_navigate_scripture(self):
        """Switch to SCRIPTURE and focus the navigator book field for typing."""
        names = list(self._tabs.keys())
        if "SCRIPTURE" in names:
            self._switch_tab(names.index("SCRIPTURE"), "SCRIPTURE")
        tab = self._tabs.get("SCRIPTURE")
        real = getattr(tab, "real_widget", None)
        if real is not None and getattr(tab, "_loaded", False):
            tab = real
        book = getattr(getattr(getattr(tab, "browser_panel", None),
                               "predictive_input", None), "book_input", None)
        if book is None:
            logger.warning("Navigate hotkey: book input not available")
            return
        # Use the widget's arrival hook (not raw setFocus): it marks the
        # predictive state fresh so the first keystroke starts a new prefix
        # instead of appending to a stale one and redisplaying the same text.
        if hasattr(book, "_on_focus_arrived"):
            book._on_focus_arrived()
        else:
            book.setFocus()
            try:
                book.selectAll()
            except Exception:
                pass

    def _resync_modifiers(self):
        """Flush phantom modifiers on window return.

        Alt/Ctrl released while unfocused can stay 'held' in Qt's eyes, so
        the next hotkey arrives with foreign modifiers and matches nothing;
        that press resyncs state, which is why only the FIRST press dies.
        Synthetic releases clear it upfront — harmless when nothing is stuck,
        since physical state reasserts itself on the next real event.
        Logs when modifiers look stuck so the console proves the diagnosis.
        """
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QKeyEvent
        from PyQt6.QtCore import QEvent as _QE
        believed = QApplication.keyboardModifiers()
        if believed != Qt.KeyboardModifier.NoModifier:
            logger.info(f"Window reactivated with modifiers still held: {believed} — flushing")
        target = QApplication.focusWidget() or self
        for key in (Qt.Key.Key_Control, Qt.Key.Key_Alt,
                    Qt.Key.Key_Shift, Qt.Key.Key_Meta):
            QApplication.sendEvent(
                target, QKeyEvent(_QE.Type.KeyRelease, key,
                                  Qt.KeyboardModifier.NoModifier))

    def _end_song_nav_if_any(self):
        """Ctrl released (or app deactivated): finish section-hop navigation."""
        try:
            tab = self._active_workspace_tab()
        except Exception:
            return
        if tab is not None and hasattr(tab, "_end_song_nav"):
            tab._end_song_nav()

    def _maybe_song_nav_key(self, event) -> bool:
        """Intercept rebinding-aware slide section-hop combos. Returns True if consumed."""
        # Never steal keys while the user is rebinding hotkeys in Settings.
        if self._hotkey_capture_active():
            return False
        for action_id, delta in (("song_prev_section", -1), ("song_next_section", 1)):
            combo = self._binding_combo(action_id)
            if combo is None:
                continue
            if event.key() == combo[0] and event.modifiers() == combo[1]:
                # Honor the decline: text inputs keep the keys (word-jump)
                # — only consume when navigation actually acted.
                if self._fire_song_nav(delta):
                    return True
                return False
        return False

    def _fire_song_nav(self, delta: int) -> bool:
        """Route one section-hop step (shared by live interception + replay)."""
        from PyQt6.QtWidgets import QApplication, QLineEdit, QTextEdit, QPlainTextEdit
        fw = QApplication.focusWidget()
        if fw is not None and isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit)):
            return False  # text inputs keep word-jump
        tab = None
        try:
            tab = self._active_workspace_tab()
        except Exception:
            pass
        if tab is not None and hasattr(tab, "song_nav_step"):
            logger.info(f"Slide section-hop {'next' if delta > 0 else 'prev'}")
            tab.song_nav_step(delta)
            return True
        return False

    def _match_binding(self, key, mods):
        """Bound action id whose sequence is exactly (key, mods), else None."""
        for action_id in getattr(self, "_hotkey_bindings", {}):
            combo = self._binding_combo(action_id)
            if combo is not None and combo[0] == key and combo[1] == mods:
                return action_id
        return None

    def _invoke_hotkey_action(self, action_id: str) -> bool:
        """Invoke a hotkey action outside the shortcut system (replay path)."""
        if action_id == "song_prev_section":
            return self._fire_song_nav(-1)
        if action_id == "song_next_section":
            return self._fire_song_nav(1)
        if action_id == "save_schedule":
            return self._save_active_schedule()
        handler = getattr(self, "_hotkey_actions", {}).get(action_id)
        if handler is None:
            return False
        try:
            handler()
        except Exception as e:
            logger.warning(f"Replayed hotkey {action_id} failed: {e}")
            return False
        return True

    def _replay_inactive_presses(self):
        """Fire actions for keypresses lost to window inactivation.

        A press that arrives while the window is inactive is skipped by
        QShortcut matching (and skipped by _maybe_song_nav_key) — yet the
        press itself usually activates the window. On activation, replay any
        fresh unmatched presses so every physical press yields one action.
        """
        pending = getattr(self, "_inactive_keypresses", [])
        self._inactive_keypresses = []
        if _KEYTAP_ENABLED:
            logger.info(f"KEYTAP replay check: {len(pending)} pending")
        if not pending:
            return
        try:
            from PyQt6.QtWidgets import QApplication as _QA4
            if _QA4.activeModalWidget() is not None:
                return
        except Exception:
            pass
        now = time.monotonic()
        last_fired = getattr(self, "_last_shortcut_at", 0.0)
        for key, mods, t in pending:
            age = now - t
            if age > 1.0:
                if _KEYTAP_ENABLED:
                    logger.info(f"KEYTAP replay skip (stale {age:.2f}s): key={key}")
                continue
            if last_fired >= t:
                if _KEYTAP_ENABLED:
                    logger.info(f"KEYTAP replay skip (already fired): key={key}")
                continue
            action = self._match_binding(key, mods)
            if action is None:
                if _KEYTAP_ENABLED:
                    logger.info(f"KEYTAP replay skip (unbound): key={key} mods={mods}")
                continue
            logger.info(f"Replaying hotkey lost to inactive window: {action}")
            if _KEYTAP_ENABLED:
                logger.info(f"KEYTAP replaying lost press: {action}")
            self._invoke_hotkey_action(action)

    def _binding_combo(self, action_id: str):
        """Current (key, modifiers) for a binding id, or None if unbound."""
        from PyQt6.QtGui import QKeySequence
        key = getattr(self, "_hotkey_bindings", {}).get(
            action_id, self._HOTKEY_DEFAULTS.get(action_id, ""))
        if not key:
            return None
        seq = QKeySequence(key)
        if seq.count() == 0:
            return None
        combo = seq[0]
        return (combo.key(), combo.keyboardModifiers())

    def _hotkey_fuzzy_search(self):
        # Switch to Presentation tab, then to the Semantic search page
        pres_idx = 0  # PRESENTATION is the first tab
        self._switch_tab(pres_idx, "SCRIPTURE")
        pres_tab = self._tabs.get("SCRIPTURE")
        if pres_tab and hasattr(pres_tab, "queue_panel"):
            pres_tab.queue_panel.switch_to_fuzzy_search()

    def _hotkey_fts_search(self):
        # Switch to Presentation tab, then to the Keyword search page
        pres_idx = 0  # PRESENTATION is the first tab
        self._switch_tab(pres_idx, "SCRIPTURE")
        pres_tab = self._tabs.get("SCRIPTURE")
        if pres_tab and hasattr(pres_tab, "queue_panel"):
            pres_tab.queue_panel.switch_to_fts_search()

    def _hotkey_deck_search(self):
        """Open the Decks tab and put the cursor in its search box —
        the deck-library counterpart to Ctrl+F / Ctrl+Shift+F."""
        names = list(self._tabs.keys())
        if "SLIDES" in names:
            self._switch_tab(names.index("SLIDES"), "SLIDES")
        deck_tab = self._tabs.get("SLIDES")
        real = getattr(deck_tab, "real_widget", None)
        if real is not None and getattr(deck_tab, "_loaded", False):
            deck_tab = real
        deck_panel = getattr(deck_tab, "deck_panel", None)
        box = getattr(deck_panel, "search_box", None)
        if box is not None:
            box.setFocus()
            box.selectAll()

    def _hotkey_switch_translation(self, version: str):
        """Switch browser to the specified translation."""
        pres_tab = self._tabs.get("SCRIPTURE")
        if pres_tab and hasattr(pres_tab, "browser_panel"):
            browser = pres_tab.browser_panel
            browser._on_translation_single_click(version)

    def _open_schedules_folder(self):
        """Open the schedules folder in the system file manager."""
        from pathlib import Path
        import subprocess
        import sys
        schedules_dir = Path(__file__).resolve().parent.parent / "data" / "schedules"
        schedules_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(schedules_dir))
        elif sys.platform == "darwin":
            subprocess.run(["open", str(schedules_dir)], check=False)
        else:
            subprocess.run(["xdg-open", str(schedules_dir)], check=False)

    def _show_schedule_menu(self):
        """Show dropdown menu of available schedules."""
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction
        from pathlib import Path

        # Get schedule panel from PresentationTab
        pres_tab = self._tabs.get("SCRIPTURE")
        if not pres_tab or not hasattr(pres_tab, "schedule_panel"):
            return

        schedule_panel = pres_tab.schedule_panel
        schedules = schedule_panel.list_schedules()

        menu = QMenu(self)
        menu.setStyleSheet(menu_qss())

        if not schedules:
            action = menu.addAction("No schedules found")
            action.setEnabled(False)
        else:
            for name, path in schedules:
                action = menu.addAction(name)
                action.triggered.connect(lambda checked, p=str(path): self._load_schedule(p))

        # Separator before New
        menu.addSeparator()

        # New schedule option
        new_action = menu.addAction("New")
        new_action.triggered.connect(lambda: self._new_schedule())

        menu.exec(self.schedule_btn.mapToGlobal(
            self.schedule_btn.rect().bottomLeft()
        ))

    def _load_schedule(self, file_path: str):
        """Load a schedule file."""
        pres_tab = self._tabs.get("SCRIPTURE")
        if pres_tab and hasattr(pres_tab, "schedule_panel"):
            pres_tab.schedule_panel.load_schedule(file_path)

    def _new_schedule(self):
        """Start a new empty schedule, prompting to save if current has items."""
        pres_tab = self._tabs.get("SCRIPTURE")
        if not pres_tab or not hasattr(pres_tab, "schedule_panel"):
            return

        schedule_panel = pres_tab.schedule_panel

        # If current schedule has items and unsaved changes, prompt to save
        if schedule_panel.list_widget.count() > 0 and schedule_panel.is_modified:
            reply = dialogs.question(
                self, "Unsaved Changes",
                "The current schedule has unsaved changes. Save before starting a new schedule?",
                dialogs.Save |
                dialogs.Discard |
                dialogs.Cancel,
                dialogs.Save
            )
            if reply == dialogs.Save:
                if not schedule_panel.save_schedule():
                    return  # User cancelled save dialog
            elif reply == dialogs.Cancel:
                return

        # Clear the schedule
        schedule_panel.clear_all(silent=True)

    def _toggle_service(self):
        """Toggle the backend service threads on/off."""
        if self._service_running:
            self._stop_service()
        else:
            self._start_service()

    def _set_service_button(self, running: bool):
        """Paint Start/Stop from the shared tone tokens (state + label)."""
        self.start_service_btn.setStyleSheet(
            tone_button_qss(DANGER if running else SUCCESS))

    def _start_service(self):
        """Boot all backend threads via ServiceManager."""
        import logging
        logger = logging.getLogger(__name__)
        try:
            from core.service_manager import manager
            manager.boot()
            self._service_running = True
            self.start_service_btn.setText("■  Stop Service")
            self.start_service_btn.setToolTip("Stop all backend threads")
            self._set_service_button(True)
            logger.info("Service started successfully.")
        except Exception as e:
            logger.error(f"Failed to start service: {e}")

    def _stop_service(self):
        """Gracefully stop all backend threads."""
        import logging
        logger = logging.getLogger(__name__)
        try:
            from core.service_manager import manager
            manager.initiate_shutdown()
            self._service_running = False
            self.start_service_btn.setText("Start Service")
            self.start_service_btn.setToolTip("Boot all backend threads")
            self._set_service_button(False)
            logger.info("Service stopped.")
        except Exception as e:
            logger.error(f"Failed to stop service: {e}")

    def closeEvent(self, event):
        """Trigger graceful shutdown and clear OBS display on window close."""
        import logging
        logger = logging.getLogger(__name__)
        
        # Stop the service threads if running
        if getattr(self, '_service_running', False):
            self._stop_service()
        
        # Clear the display via WebSocket using the server's event loop
        try:
            from core.websocket_server import broadcast_display, _server_loop
            import asyncio
            if _server_loop and _server_loop.is_running():
                # Broadcast clear action to all outputs on the server's loop
                from core.outputs import ALL_OUTPUTS
                for output_id in ALL_OUTPUTS:
                    asyncio.run_coroutine_threadsafe(
                        broadcast_display({"action": "clear"}, target=output_id),
                        _server_loop
                    )
            else:
                logger.warning("WebSocket server loop not running; cannot clear display")
        except Exception as e:
            logger.warning(f"Failed to clear display on shutdown: {e}")
        
        event.accept()
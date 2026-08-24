"""
ui/main_window.py

Frameless main window with Chrome-style tab bar and lazy-loaded tabs.
Implements window dragging, resizing, and global hotkeys.
"""

import os

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QSizeGrip
)
from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QKeySequence, QShortcut

from ui.styles import (
    SLATE_950, SLATE_600, CHROME_BG, CHROME_TAB_ACTIVE,
    WHITE, SLATE_400, EMERALD_500, RED_500, BORDER_SUBTLE
)
from ui.tabs.presentation_tab import PresentationTab
from ui.tabs.library_tab import LibraryTab
from ui.tabs.settings_tab import SettingsTab
from ui.tabs.history_tab import HistoryTab
from ui.widgets.status_bar import StatusBar


class ChromeTab(QPushButton):
    """Custom button acting as a Chrome-style tab."""
    def __init__(self, text: str, is_active: bool = False, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setChecked(is_active)
        self.setFixedHeight(30)
        self.setAccessibleName(text)
        # self.setAccessibleRole(Qt.AccessibleRole.PageTab)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {SLATE_400};
                border: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 0 14px;
                font-size: 10px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.05);
            }}
            QPushButton:checked {{
                background: {CHROME_TAB_ACTIVE};
                color: {WHITE};
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
        
        # Favicon icon
        assets_dir = os.path.join(os.path.dirname(__file__), "assets")
        icon_path = os.path.join(assets_dir, "favicon.svg")
        if os.path.exists(icon_path):
            icon_label = QLabel()
            icon_pixmap = QPixmap(icon_path).scaled(
                20, 20, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            icon_label.setPixmap(icon_pixmap)
            icon_label.setFixedSize(24, 24)
            icon_label.setStyleSheet("background: transparent; padding: 0px 6px 0px 0px;")
            layout.addWidget(icon_label)
        
        # Logo
        logo = QLabel("RhemaCast")
        logo.setAccessibleName("Application name")
        logo.setStyleSheet("""
            color: #60a5fa;
            font-size: 12px;
            font-weight: 800;
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
    """A lazy-loaded tab placeholder that instantiates its true widget on first show."""
    loaded = pyqtSignal(object)  # emits the real widget once loaded

    def __init__(self, init_func, parent=None):
        super().__init__(parent)
        self.init_func = init_func
        self._loaded = False
        self.real_widget = None
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Show a loading indicator initially
        self.loading_label = QLabel("Loading...")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet("color: #64748b; font-size: 14px;")
        self.layout.addWidget(self.loading_label)

    def showEvent(self, event):
        if not self._loaded:
            # Instantiate the real widget
            widget = self.init_func()
            self.real_widget = widget
            self.layout.removeWidget(self.loading_label)
            self.loading_label.deleteLater()
            self.layout.addWidget(widget)
            self._loaded = True
            self.loaded.emit(widget)
        super().showEvent(event)


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        
        # Accessibility
        self.setWindowTitle("RhemaCast — Sermon Transcription & Verse Display")
        self.setAccessibleName("RhemaCast Main Window")
        self.setAccessibleDescription("Live sermon transcription with verse suggestion and OBS broadcast")
        
        # Frameless window configuration
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(1024, 768)
        self.resize(1280, 800)

        # Set window icon
        assets_dir = os.path.join(os.path.dirname(__file__), "assets")
        icon_path = os.path.join(assets_dir, "icon.svg")
        if os.path.exists(icon_path):
            from PyQt6.QtGui import QIcon
            self.setWindowIcon(QIcon(icon_path))
        
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
        
        _greyed_btn_style = f"""
            QPushButton {{
                background: transparent;
                color: {SLATE_600};
                font-size: 11px;
                padding: 4px 8px;
                border: none;
            }}
            QPushButton:disabled {{
                color: {SLATE_600};
            }}
        """
        
        _service_btn_style = f"""
            QPushButton {{
                background: rgba(16, 185, 129, 0.15);
                color: {EMERALD_500};
                font-size: 11px;
                font-weight: 700;
                padding: 4px 14px;
                border: 1px solid rgba(16, 185, 129, 0.3);
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background: rgba(16, 185, 129, 0.25);
            }}
            QPushButton:disabled {{
                background: rgba(239, 68, 68, 0.1);
                color: {RED_500};
                border-color: rgba(239, 68, 68, 0.2);
            }}
        """
        
        self.sub_toolbar.setStyleSheet(f"""
            QWidget#SubToolbar {{
                background-color: {SLATE_950};
                border-bottom: 1px solid {BORDER_SUBTLE};
            }}
        """)
        sub_layout = QHBoxLayout(self.sub_toolbar)
        sub_layout.setContentsMargins(12, 4, 12, 4)
        sub_layout.setSpacing(4)
        
        # Greyed-out menu items
        for text in ["View"]:
            btn = QPushButton(text)
            btn.setStyleSheet(_greyed_btn_style)
            btn.setEnabled(False)
            btn.setToolTip(f"{text} — coming soon")
            sub_layout.addWidget(btn)
            
        sep = QLabel("|")
        sep.setStyleSheet(f"color: {SLATE_600}; font-size: 11px; margin: 0 4px;")
        sub_layout.addWidget(sep)

        # Schedule button — shows dropdown of available schedules
        self.schedule_btn = QPushButton("Schedule")
        self.schedule_btn.setStyleSheet(_greyed_btn_style)
        self.schedule_btn.setEnabled(True)
        self.schedule_btn.setToolTip("Load a schedule (click) or show schedule menu (hold)")
        self.schedule_btn.clicked.connect(self._show_schedule_menu)
        sub_layout.addWidget(self.schedule_btn)
        
        for text in ["Remote", "Live Sync"]:
            btn = QPushButton(text)
            btn.setStyleSheet(_greyed_btn_style)
            btn.setEnabled(False)
            btn.setToolTip(f"{text} — coming soon")
            sub_layout.addWidget(btn)
            
        sub_layout.addStretch()
        
        # Start Service button
        self.start_service_btn = QPushButton("▶  Start Service")
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
        self._setup_tabs()
        
        # Setup Hotkeys
        self._setup_hotkeys()
        
        # Install app-wide event filter for Alt+Click (add to schedule)
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().installEventFilter(self)
        
        # Phase 10: Operator Consent Gate at boot
        self._check_offline_queue()

    def _check_offline_queue(self):
        import os
        from cloud.extraction import OFFLINE_QUEUE_PATH
        if os.path.exists(OFFLINE_QUEUE_PATH):
            try:
                with open(OFFLINE_QUEUE_PATH, 'r', encoding='utf-8') as f:
                    lines = [line for line in f if line.strip()]
                if lines:
                    from PyQt6.QtWidgets import QMessageBox
                    msg = QMessageBox(self)
                    msg.setWindowTitle("Offline Extraction Queue")
                    msg.setText(f"{len(lines)} past services pending. Process now or after service?")
                    msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                    msg.button(QMessageBox.StandardButton.Yes).setText("Process Now")
                    msg.button(QMessageBox.StandardButton.No).setText("After Service")
                    msg.setModal(False) # Non-blocking
                    msg.show()
                    
                    # Prevent garbage collection of the non-blocking message box
                    self._offline_msg = msg
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to check offline queue: {e}")

    def _setup_tabs(self):
        # Add tabs (name -> widget_init_function)
        tabs_config = [
            ("PRESENTATION", lambda: PresentationTab()),
            ("LIBRARY", lambda: LibraryTab()),
            ("HISTORY", lambda: HistoryTab()),
            ("SETTINGS", lambda: SettingsTab()),
            ("THEME DESIGNER", self._init_theme_designer)
        ]
        
        for i, (name, init_func) in enumerate(tabs_config):
            # Create content widget
            if i == 0:
                # Presentation tab is fully loaded immediately
                content = init_func()
                # Connect theme quick-edit from queue panel
                content.queue_panel.theme_edit_requested.connect(self._open_theme_quick_editor)
            else:
                # Other tabs are lazy-loaded Placeholders
                content = PlaceholderTab(init_func)
                # Connect hotkey editor when Settings tab finishes loading
                if name == "SETTINGS":
                    content.loaded.connect(self._on_settings_tab_loaded)
                
            self.stack.addWidget(content)
            self._tabs[name] = content
            
            # Create tab button
            btn = ChromeTab(name, is_active=(i == 0))
            # Create a closure to capture the index
            btn.clicked.connect(lambda checked, idx=i, n=name: self._switch_tab(idx, n))
            
            # Add container to align tabs to the bottom of the title bar
            btn_layout = QVBoxLayout()
            btn_layout.setContentsMargins(0, 0, 0, 0)
            btn_layout.addStretch()
            btn_layout.addWidget(btn)
            
            tab_container = QWidget()
            tab_container.setLayout(btn_layout)
            
            self.title_bar.tabs_layout.addWidget(tab_container)
            self._tab_buttons[name] = btn

    def _switch_tab(self, index: int, name: str):
        # Update button states
        for btn_name, btn in self._tab_buttons.items():
            btn.setChecked(btn_name == name)
            
        # Hide sub-toolbar for tabs that don't need it
        self.sub_toolbar.setVisible(name not in ("LIBRARY", "SETTINGS", "HISTORY"))
            
        # Switch stack
        self.stack.setCurrentIndex(index)

    def _on_settings_tab_loaded(self, widget):
        """Connect hotkey editor and font size signals once the Settings tab finishes lazy-loading."""
        if hasattr(widget, '_hotkey_editor'):
            widget._hotkey_editor.bindings_changed.connect(self._on_hotkey_bindings_changed)
        if hasattr(widget, 'font_size_changed'):
            widget.font_size_changed.connect(self._on_font_size_changed)
    
    def _on_font_size_changed(self, text_size: int, ref_size: int):
        """Propagate font size changes to the browser panel for live preview."""
        pres_tab = self._tabs.get("PRESENTATION")
        if pres_tab and hasattr(pres_tab, "browser_panel"):
            pres_tab.browser_panel.update_verse_font_sizes(text_size, ref_size)
        
    def _init_theme_designer(self) -> QWidget:
        from ui.tabs.theme_designer_tab import ThemeDesignerTab
        tab = ThemeDesignerTab()
        self._theme_designer_tab = tab
        return tab

    def _open_theme_quick_editor(self, theme_name: str):
        from ui.widgets.theme_quick_editor import ThemeQuickEditor
        editor = ThemeQuickEditor(theme_name, parent=self)
        editor.edit_full_requested.connect(self._open_full_designer)
        editor.theme_saved.connect(self._on_theme_saved)
        editor.show()

    def _open_full_designer(self, theme_name: str):
        # Switch to the Theme Designer tab
        for idx, (name, _) in enumerate([
            ("PRESENTATION", None), ("LIBRARY", None), ("HISTORY", None),
            ("SETTINGS", None), ("THEME DESIGNER", None)
        ]):
            if name == "THEME DESIGNER":
                self._switch_tab(idx, name)
                break
        # Set the theme in the designer tab
        if hasattr(self, '_theme_designer_tab') and self._theme_designer_tab:
            self._theme_designer_tab.set_theme(theme_name)

    def _on_theme_saved(self, theme_name: str):
        # Reload themes in the presentation tab's queue panel
        pres_tab = self._tabs.get("PRESENTATION")
        if pres_tab and hasattr(pres_tab, 'queue_panel'):
            pres_tab.queue_panel._themes_panel.reload()

    def eventFilter(self, obj, event):
        """App-wide event filter: intercept Alt+Click and defocus search panels."""
        from PyQt6.QtCore import QEvent as _QE
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        
        if event.type() == _QE.Type.MouseButtonPress:
            if (event.button() == Qt.MouseButton.LeftButton
                    and event.modifiers() & Qt.KeyboardModifier.AltModifier):
                self._hotkey_add_to_schedule()
                return True  # consume — don't let Qt do alt-click text selection
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
        pres = self._tabs.get("PRESENTATION")
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

    def _load_hotkey_bindings(self):
        """Load saved bindings from settings database."""
        from core.database import get_setting
        import json
        saved = get_setting("hotkeys.bindings", "{}")
        try:
            self._hotkey_bindings = json.loads(saved)
        except Exception:
            self._hotkey_bindings = {}
        
        # Defaults
        defaults = {
            "clear_recall": "F6",
            "fts_search": "Ctrl+Shift+F",
            "fuzzy_search": "Ctrl+Shift+S",
            "next_verse": "Right",
            "prev_verse": "Left",
            "toggle_transcription": "F7",
            "add_to_schedule": "Alt+Return",
            "double_click": "D",
        }
        for action, key in defaults.items():
            if action not in self._hotkey_bindings:
                self._hotkey_bindings[action] = key

    def _create_shortcuts(self):
        """Create QShortcuts from current bindings."""
        # Clear existing shortcuts
        for shortcut in getattr(self, '_shortcuts', []):
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self._shortcuts = []

        # Map action IDs to handler methods
        action_handlers = {
            "clear_recall": self._hotkey_clear,
            "fts_search": self._hotkey_fts_search,
            "fuzzy_search": self._hotkey_fuzzy_search,
            "next_verse": self._hotkey_next_verse,
            "prev_verse": self._hotkey_prev_verse,
            "toggle_transcription": self._hotkey_toggle_transcription,
            "add_to_schedule": self._hotkey_add_to_schedule,
            "double_click": self._hotkey_double_click,
        }

        for action_id, key in self._hotkey_bindings.items():
            if action_id in action_handlers and key:
                shortcut = QShortcut(QKeySequence(key), self)
                shortcut.activated.connect(action_handlers[action_id])
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

    def _on_hotkey_bindings_changed(self, bindings: dict):
        """Called when user changes bindings in Settings."""
        self._hotkey_bindings = bindings
        self._create_shortcuts()

    def _disable_shortcuts(self):
        """Disable all shortcuts during hotkey capture."""
        for shortcut in getattr(self, '_shortcuts', []):
            shortcut.setEnabled(False)

    def _enable_shortcuts(self):
        """Re-enable all shortcuts after hotkey capture."""
        for shortcut in getattr(self, '_shortcuts', []):
            shortcut.setEnabled(True)

    def _defocus_navigator(self):
        """Defocus the predictive scripture input fields if they have focus."""
        from PyQt6.QtWidgets import QApplication
        focused = QApplication.focusWidget()
        if focused is None:
            return
        # Check if focused widget is part of the predictive input
        pres_tab = self._tabs.get("PRESENTATION")
        if pres_tab and hasattr(pres_tab, "browser_panel"):
            browser = pres_tab.browser_panel
            if hasattr(browser, "predictive_input"):
                pi = browser.predictive_input
                if focused in (pi.book_input, pi.chapter_input, pi.verse_input):
                    self.setFocus()

    def _hotkey_next_verse(self):
        self._defocus_navigator()
        pres_tab = self._tabs.get("PRESENTATION")
        if pres_tab and hasattr(pres_tab, "live_preview"):
            pres_tab.live_preview.next_verse.emit()

    def _hotkey_prev_verse(self):
        self._defocus_navigator()
        pres_tab = self._tabs.get("PRESENTATION")
        if pres_tab and hasattr(pres_tab, "live_preview"):
            pres_tab.live_preview.prev_verse.emit()

    def _hotkey_toggle_transcription(self):
        pres_tab = self._tabs.get("PRESENTATION")
        if pres_tab and hasattr(pres_tab, "stt_panel"):
            if pres_tab.stt_panel.is_recording:
                pres_tab.stt_panel.transcription_stopped.emit()
            else:
                pres_tab.stt_panel.transcription_started.emit()

    def _hotkey_add_to_schedule(self):
        """Simulate a single click at cursor position (updates preview) and send to schedule."""
        from PyQt6.QtGui import QCursor, QMouseEvent, QPointingDevice
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt as QtCore, QPointF

        global_point = QCursor.pos()
        target = QApplication.widgetAt(global_point)
        if not target:
            return

        # Defocus navigator if cursor is outside it
        pres_tab = self._tabs.get("PRESENTATION")
        if pres_tab and hasattr(pres_tab, "browser_panel"):
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

        # Now add selected verses to schedule
        pres_tab = self._tabs.get("PRESENTATION")
        if pres_tab and hasattr(pres_tab, "browser_panel") and hasattr(pres_tab, "schedule_panel"):
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

    def _hotkey_double_click(self):
        """Simulate a mouse double-click at the current cursor position.
        
        Defocuses the navigator inputs if the cursor is outside them,
        so the double-click goes to the intended target and next/prev
        hotkeys work afterward.
        """
        from PyQt6.QtGui import QCursor, QMouseEvent, QPointingDevice
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt as QtCore, QPointF

        global_point = QCursor.pos()
        target = QApplication.widgetAt(global_point)
        if not target:
            return

        # Defocus navigator if cursor is outside it
        pres_tab = self._tabs.get("PRESENTATION")
        if pres_tab and hasattr(pres_tab, "browser_panel"):
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
        # Trigger clear/recall
        # The presentation tab handles this logic, we could signal it
        pres_tab = self._tabs.get("PRESENTATION")
        if pres_tab and hasattr(pres_tab, "live_preview"):
            pres_tab.live_preview.clear_recall.emit()

    def _hotkey_fuzzy_search(self):
        # Switch to Presentation tab, then to Fuzzy Search sub-tab
        pres_idx = 0  # PRESENTATION is the first tab
        self._switch_tab(pres_idx, "PRESENTATION")
        pres_tab = self._tabs.get("PRESENTATION")
        if pres_tab and hasattr(pres_tab, "queue_panel"):
            pres_tab.queue_panel.switch_to_fuzzy_search()

    def _hotkey_fts_search(self):
        # Switch to Presentation tab, then to FTS Search sub-tab
        pres_idx = 0  # PRESENTATION is the first tab
        self._switch_tab(pres_idx, "PRESENTATION")
        pres_tab = self._tabs.get("PRESENTATION")
        if pres_tab and hasattr(pres_tab, "queue_panel"):
            pres_tab.queue_panel.switch_to_fts_search()

    def _hotkey_switch_translation(self, version: str):
        """Switch browser to the specified translation."""
        pres_tab = self._tabs.get("PRESENTATION")
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
        pres_tab = self._tabs.get("PRESENTATION")
        if not pres_tab or not hasattr(pres_tab, "schedule_panel"):
            return

        schedule_panel = pres_tab.schedule_panel
        schedules = schedule_panel.list_schedules()

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {SLATE_950};
                color: {WHITE};
                border: 1px solid {BORDER_SUBTLE};
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 20px;
            }}
            QMenu::item:selected {{
                background: rgba(255, 255, 255, 0.1);
            }}
        """)

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
        pres_tab = self._tabs.get("PRESENTATION")
        if pres_tab and hasattr(pres_tab, "schedule_panel"):
            pres_tab.schedule_panel.load_schedule(file_path)

    def _new_schedule(self):
        """Start a new empty schedule, prompting to save if current has items."""
        from PyQt6.QtWidgets import QMessageBox

        pres_tab = self._tabs.get("PRESENTATION")
        if not pres_tab or not hasattr(pres_tab, "schedule_panel"):
            return

        schedule_panel = pres_tab.schedule_panel

        # If current schedule has items and unsaved changes, prompt to save
        if schedule_panel.list_widget.count() > 0 and schedule_panel.is_modified:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "The current schedule has unsaved changes. Save before starting a new schedule?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save
            )
            if reply == QMessageBox.StandardButton.Save:
                if not schedule_panel.save_schedule():
                    return  # User cancelled save dialog
            elif reply == QMessageBox.StandardButton.Cancel:
                return

        # Clear the schedule
        schedule_panel.clear_all(silent=True)

    def _toggle_service(self):
        """Toggle the backend service threads on/off."""
        if self._service_running:
            self._stop_service()
        else:
            self._start_service()

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
            # Switch to red-ish disabled style for the stop state
            self.start_service_btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(239, 68, 68, 0.15);
                    color: {RED_500};
                    font-size: 11px;
                    font-weight: 700;
                    padding: 4px 14px;
                    border: 1px solid rgba(239, 68, 68, 0.3);
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    background: rgba(239, 68, 68, 0.25);
                }}
            """)
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
            self.start_service_btn.setText("▶  Start Service")
            self.start_service_btn.setToolTip("Boot all backend threads")
            self.start_service_btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(16, 185, 129, 0.15);
                    color: {EMERALD_500};
                    font-size: 11px;
                    font-weight: 700;
                    padding: 4px 14px;
                    border: 1px solid rgba(16, 185, 129, 0.3);
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    background: rgba(16, 185, 129, 0.25);
                }}
            """)
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
                for output_id in ["1", "2", "3"]:
                    asyncio.run_coroutine_threadsafe(
                        broadcast_display({"action": "clear"}, target=output_id),
                        _server_loop
                    )
            else:
                logger.warning("WebSocket server loop not running; cannot clear display")
        except Exception as e:
            logger.warning(f"Failed to clear display on shutdown: {e}")
        
        event.accept()
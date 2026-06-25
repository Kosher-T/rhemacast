"""
ui/main_window.py

Frameless main window with Chrome-style tab bar and lazy-loaded tabs.
Implements window dragging, resizing, and global hotkeys.
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QSizeGrip
)
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut

from ui.styles import (
    SLATE_950, SLATE_600, CHROME_BG, CHROME_TAB_ACTIVE,
    WHITE, SLATE_400, EMERALD_500, RED_500, BORDER_SUBTLE
)
from ui.tabs.presentation_tab import PresentationTab
from ui.widgets.status_bar import StatusBar

class ChromeTab(QPushButton):
    """Custom button acting as a Chrome-style tab."""
    def __init__(self, text: str, is_active: bool = False, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setChecked(is_active)
        self.setFixedHeight(34)
        
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {SLATE_400};
                border: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 0 20px;
                font-size: 11px;
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
    """Custom title bar implementing dragging and Chrome tabs."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setFixedHeight(42)
        self.setObjectName("FramelessTitleBar")
        self.setStyleSheet(f"""
            QWidget#FramelessTitleBar {{
                background-color: {CHROME_BG};
                border-bottom: 1px solid rgba(0, 0, 0, 0.4);
            }}
        """)
        
        self._drag_pos = None
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(0)
        
        # Logo
        logo = QLabel("RhemaCast")
        logo.setStyleSheet(f"""
            color: #60a5fa;
            font-size: 13px;
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
        min_btn.setFixedSize(44, 32)
        min_btn.setStyleSheet(ctrl_style)
        min_btn.clicked.connect(self.parent_window.showMinimized)
        
        max_btn = QPushButton("□")
        max_btn.setFixedSize(44, 32)
        max_btn.setStyleSheet(ctrl_style)
        max_btn.clicked.connect(self._toggle_maximize)
        
        close_btn = QPushButton("✕")
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
    def __init__(self, init_func, parent=None):
        super().__init__(parent)
        self.init_func = init_func
        self._loaded = False
        
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
            self.layout.removeWidget(self.loading_label)
            self.loading_label.deleteLater()
            self.layout.addWidget(widget)
            self._loaded = True
        super().showEvent(event)

class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        
        # Frameless window configuration
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(1024, 768)
        self.resize(1280, 800)
        
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
        
        for text in ["Schedule", "Remote", "Live Sync"]:
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
            ("LIBRARY", lambda: QWidget()), # Mocks for now
            ("HISTORY", lambda: QWidget()),
            ("SETTINGS", lambda: QWidget()),
            ("THEME DESIGNER", self._init_theme_designer)
        ]
        
        for i, (name, init_func) in enumerate(tabs_config):
            # Create content widget
            if i == 0:
                # Presentation tab is fully loaded immediately
                content = init_func()
            else:
                # Other tabs are lazy-loaded Placeholders
                content = PlaceholderTab(init_func)
                
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
            
        # Switch stack
        self.stack.setCurrentIndex(index)
        
    def _init_theme_designer(self) -> QWidget:
        # Phase 9.5: Theme Designer (Minimal Viable Version)
        # Using a QWidget layout with QTextEdit and potentially QWebEngineView
        widget = QWidget()
        layout = QHBoxLayout(widget)
        
        from PyQt6.QtWidgets import QTextEdit
        text_edit = QTextEdit()
        text_edit.setPlainText("/* themes.css editor */")
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: #1e293b;
                color: #f8fafc;
                font-family: monospace;
                padding: 12px;
                border: 1px solid {BORDER_SUBTLE};
            }}
        """)
        layout.addWidget(text_edit, 1)
        
        # Only load WebEngine if available
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            web_view = QWebEngineView()
            web_view.setHtml("<html><body style='background: black; color: white;'><h2>Live Preview</h2></body></html>")
            layout.addWidget(web_view, 1)
        except ImportError:
            fallback = QLabel("PyQt6-WebEngine not installed. Live preview disabled.")
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(fallback, 1)
            
        return widget

    def _setup_hotkeys(self):
        # Default bindings (F1-F12)
        # Display: F5, Clear: F6
        self.shortcut_display = QShortcut(QKeySequence("F5"), self)
        self.shortcut_display.activated.connect(self._hotkey_display)
        
        self.shortcut_clear = QShortcut(QKeySequence("F6"), self)
        self.shortcut_clear.activated.connect(self._hotkey_clear)

    def _hotkey_display(self):
        # Trigger display action (e.g. from the selected item in the queue)
        pass

    def _hotkey_clear(self):
        # Trigger clear/recall
        # The presentation tab handles this logic, we could signal it
        pres_tab = self._tabs.get("PRESENTATION")
        if pres_tab and hasattr(pres_tab, "live_output"):
            pres_tab.live_output.clear_recall.emit()

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

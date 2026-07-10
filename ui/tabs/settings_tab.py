"""
ui/tabs/settings_tab.py

Settings tab with sidebar navigation and glass-card content sections.
Matches the design from ui_draft/settings.html
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QComboBox, QSlider, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from ui.widgets.hotkey_editor import HotkeyEditor

from ui.styles import (
    SLATE_950, SLATE_800, SLATE_700, SLATE_600, SLATE_500, SLATE_400,
    SLATE_300, WHITE, BLUE_500, CYAN_400, EMERALD_500, RED_500,
    AMBER_500, BORDER_SUBTLE
)

# Glass card style matching global.css
GLASS_CARD_STYLE = f"""
    QFrame {{
        background: rgba(30, 41, 59, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 8px;
    }}
"""

SIDEBAR_ITEM_STYLE = f"""
    QPushButton {{
        background: transparent;
        color: {SLATE_400};
        border: none;
        border-radius: 6px;
        padding: 10px 12px;
        text-align: left;
        font-size: 12px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background: rgba(255, 255, 255, 0.05);
        color: {WHITE};
    }}
    QPushButton[active="true"] {{
        background: rgba(37, 99, 235, 0.2);
        color: {WHITE};
    }}
"""

ACTIVE_SIDEBAR_STYLE = f"""
    QPushButton {{
        background: rgba(37, 99, 235, 0.3);
        color: {WHITE};
        border: none;
        border-radius: 6px;
        padding: 10px 12px;
        text-align: left;
        font-size: 12px;
        font-weight: 700;
    }}
"""

COMBO_STYLE = f"""
    QComboBox {{
        background: rgba(0, 0, 0, 0.4);
        color: {SLATE_300};
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 6px;
        padding: 8px 12px;
        font-size: 12px;
        min-width: 200px;
    }}
    QComboBox:hover {{
        border-color: rgba(59, 130, 246, 0.5);
    }}
    QComboBox:focus {{
        border-color: {BLUE_500};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {SLATE_400};
        margin-right: 8px;
    }}
    QComboBox QAbstractItemView {{
        background: {SLATE_800};
        color: {WHITE};
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 6px;
        selection-background-color: rgba(59, 130, 246, 0.3);
        padding: 4px;
    }}
"""

SLIDER_STYLE = f"""
    QSlider::groove:horizontal {{
        border: none;
        height: 4px;
        background: rgba(255, 255, 255, 0.1);
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: {BLUE_500};
        border: none;
        width: 16px;
        height: 16px;
        margin: -6px 0;
        border-radius: 8px;
    }}
    QSlider::handle:horizontal:hover {{
        background: {CYAN_400};
    }}
    QSlider::sub-page:horizontal {{
        background: {BLUE_500};
        border-radius: 2px;
    }}
"""

TOGGLE_STYLE = f"""
    QPushButton {{
        background: rgba(34, 197, 94, 0.1);
        border: 1px solid rgba(34, 197, 94, 0.2);
        border-radius: 16px;
        min-width: 56px;
        max-width: 56px;
        min-height: 28px;
        max-height: 28px;
    }}
    QPushButton:checked {{
        background: {EMERALD_500};
        border-color: {EMERALD_500};
    }}
"""

LABEL_STYLE = f"color: {WHITE}; font-size: 14px; font-weight: 700;"
SUBTITLE_STYLE = f"color: {SLATE_500}; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px;"
SECTION_LABEL_STYLE = f"color: {SLATE_400}; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;"
VALUE_STYLE = f"color: {BLUE_500}; font-size: 12px; font-family: monospace; font-weight: 600;"
TOGGLE_LABEL_STYLE = f"color: {SLATE_300}; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;"


class SettingsSidebarItem(QPushButton):
    """Sidebar navigation item with label."""
    
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)
        
        # Text
        text_label = QLabel(text)
        text_label.setStyleSheet(f"color: {SLATE_400}; font-size: 12px; font-weight: 600; background: transparent;")
        layout.addWidget(text_label)
        layout.addStretch()
        
    def set_active(self, active: bool):
        self.setChecked(active)
        if active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(37, 99, 235, 0.3);
                    color: {WHITE};
                    border: none;
                    border-radius: 6px;
                    padding: 10px 12px;
                    text-align: left;
                    font-size: 12px;
                    font-weight: 700;
                }}
            """)
        else:
            self.setStyleSheet(SIDEBAR_ITEM_STYLE)


class GlassCard(QFrame):
    """Glassmorphism card container."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(GLASS_CARD_STYLE)
        self.setContentsMargins(0, 0, 0, 0)


class SettingsTab(QWidget):
    """Settings tab with sidebar navigation and content sections."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(16)
        
        # ── Sidebar ──
        sidebar = QWidget()
        sidebar.setFixedWidth(256)
        sidebar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(4)
        
# Sidebar items
        self._sidebar_items = {}
        sidebar_categories = [
            "Audio Ingestion",
            "AI Models",
            "Display & Broadcast",
            "Database",
            "GPU & Hardware",
            "Hotkeys",
        ]
        
        for name in sidebar_categories:
            item = SettingsSidebarItem(name)
            item.clicked.connect(lambda checked, n=name: self._switch_section(n))
            sidebar_layout.addWidget(item)
            self._sidebar_items[name] = item
        
        sidebar_layout.addStretch()
        
        # Hardware Monitor Widget at bottom of sidebar
        self._hardware_widget = self._create_hardware_widget()
        sidebar_layout.addWidget(self._hardware_widget)
        
        root_layout.addWidget(sidebar)
        
        # ── Content Area ──
        content_scroll = QScrollArea()
        content_scroll.setWidgetResizable(True)
        content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content_scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 0.1);
                border-radius: 3px;
                min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)
        
        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 8, 0)
        self._content_layout.setSpacing(16)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # Create section widgets
        self._sections = {}
        self._create_audio_ingestion_section()
        self._create_ai_models_section()
        self._create_display_broadcast_section()
        self._create_database_section()
        self._create_gpu_hardware_section()
        self._create_hotkeys_section()
        
        # Initially show Audio Ingestion
        self._switch_section("Audio Ingestion")
        
        content_scroll.setWidget(self._content_widget)
        root_layout.addWidget(content_scroll, 1)
        
        # Start hardware monitoring update timer
        from PyQt6.QtCore import QTimer
        self._hw_timer = QTimer(self)
        self._hw_timer.timeout.connect(self._update_hardware_status)
        self._hw_timer.start(2000)
        self._update_hardware_status()
    
    def _create_hardware_widget(self) -> QFrame:
        """Create the Live Hardware Status widget at bottom of sidebar."""
        widget = GlassCard()
        widget.setFixedHeight(160)
        
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        
        # Title
        title = QLabel("Live Hardware Status")
        title.setStyleSheet(f"color: {SLATE_500}; font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px;")
        layout.addWidget(title)
        
        # GPU VRAM
        vram_layout = QVBoxLayout()
        vram_layout.setSpacing(4)
        
        vram_header = QHBoxLayout()
        vram_label = QLabel("GPU VRAM")
        vram_label.setStyleSheet(f"color: {SLATE_400}; font-size: 10px; font-weight: 700;")
        self._vram_value = QLabel("0.0 / 0.0 GB")
        self._vram_value.setStyleSheet(VALUE_STYLE)
        vram_header.addWidget(vram_label)
        vram_header.addStretch()
        vram_header.addWidget(self._vram_value)
        vram_layout.addLayout(vram_header)
        
        self._vram_bar = QFrame()
        self._vram_bar.setFixedHeight(4)
        self._vram_bar.setStyleSheet(f"""
            QFrame {{
                background: rgba(255, 255, 255, 0.1);
                border-radius: 2px;
            }}
        """)
        self._vram_fill = QFrame(self._vram_bar)
        self._vram_fill.setStyleSheet(f"""
            QFrame {{
                background: {BLUE_500};
                border-radius: 2px;
            }}
        """)
        self._vram_fill.setFixedHeight(4)
        self._vram_fill.setGeometry(0, 0, 0, 4)
        vram_layout.addWidget(self._vram_bar)
        
        layout.addLayout(vram_layout)
        
        # GPU Temp
        temp_layout = QVBoxLayout()
        temp_layout.setSpacing(4)
        
        temp_header = QHBoxLayout()
        temp_label = QLabel("GPU Temp")
        temp_label.setStyleSheet(f"color: {SLATE_400}; font-size: 10px; font-weight: 700;")
        self._temp_value = QLabel("0°C")
        self._temp_value.setStyleSheet(f"color: {EMERALD_500}; font-size: 12px; font-family: monospace; font-weight: 600;")
        temp_header.addWidget(temp_label)
        temp_header.addStretch()
        temp_header.addWidget(self._temp_value)
        temp_layout.addLayout(temp_header)
        
        self._temp_bar = QFrame()
        self._temp_bar.setFixedHeight(4)
        self._temp_bar.setStyleSheet(f"""
            QFrame {{
                background: rgba(255, 255, 255, 0.1);
                border-radius: 2px;
            }}
        """)
        self._temp_fill = QFrame(self._temp_bar)
        self._temp_fill.setStyleSheet(f"""
            QFrame {{
                background: {EMERALD_500};
                border-radius: 2px;
            }}
        """)
        self._temp_fill.setFixedHeight(4)
        self._temp_fill.setGeometry(0, 0, 0, 4)
        temp_layout.addWidget(self._temp_bar)
        
        layout.addLayout(temp_layout)
        
        return widget
    
    def _update_hardware_status(self):
        """Update hardware status from core monitor."""
        try:
            from core.hardware_monitor import get_hardware_info
            info = get_hardware_info()
            if info:
                # VRAM
                vram_used = info.get('vram_used_mb', 0) / 1024
                vram_total = info.get('vram_total_mb', 1) / 1024
                self._vram_value.setText(f"{vram_used:.1f} / {vram_total:.1f} GB")
                pct = (vram_used / vram_total * 100) if vram_total > 0 else 0
                self._vram_fill.setFixedWidth(int(self._vram_bar.width() * pct / 100))
                
                # Temp
                temp = info.get('temperature_c', 0)
                self._temp_value.setText(f"{temp}°C")
                # Green up to 70, amber to 82, red above
                if temp < 70:
                    color = EMERALD_500
                elif temp < 82:
                    color = AMBER_500
                else:
                    color = RED_500
                self._temp_value.setStyleSheet(f"color: {color}; font-size: 12px; font-family: monospace; font-weight: 600;")
                pct = min(100, max(0, (temp - 30) / 52 * 100))
                self._temp_fill.setFixedWidth(int(self._temp_bar.width() * pct / 100))
                self._temp_fill.setStyleSheet(f"QFrame {{ background: {color}; border-radius: 2px; }}")
        except Exception:
            pass
    
    def _switch_section(self, name: str):
        """Switch the visible content section."""
        # Update sidebar buttons
        for n, item in self._sidebar_items.items():
            item.set_active(n == name)
        
        # Show/hide sections
        for n, widget in self._sections.items():
            widget.setVisible(n == name)
    
    def _create_audio_ingestion_section(self):
        """Create the Audio Ingestion section with device selection, sample rate, and DeepFilterNet."""
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        
        # Section header
        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)
        
        title = QLabel("Audio Ingestion")
        title.setStyleSheet(LABEL_STYLE)
        header_layout.addWidget(title)
        
        subtitle = QLabel("Select and configure your primary audio source")
        subtitle.setStyleSheet(SUBTITLE_STYLE)
        header_layout.addWidget(subtitle)
        
        layout.addWidget(header)
        
        # Grid of controls
        grid = QWidget()
        grid_layout = QHBoxLayout(grid)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(16)
        
        # Input Device
        device_col = QWidget()
        device_layout = QVBoxLayout(device_col)
        device_layout.setContentsMargins(0, 0, 0, 0)
        device_layout.setSpacing(6)
        
        device_label = QLabel("Input Device")
        device_label.setStyleSheet(SECTION_LABEL_STYLE)
        device_layout.addWidget(device_label)
        
        self._device_combo = QComboBox()
        self._device_combo.setStyleSheet(COMBO_STYLE)
        # Populate from audio capture
        self._populate_audio_devices()
        device_layout.addWidget(self._device_combo)
        
        grid_layout.addWidget(device_col, 1)
        
        # Sample Rate
        rate_col = QWidget()
        rate_layout = QVBoxLayout(rate_col)
        rate_layout.setContentsMargins(0, 0, 0, 0)
        rate_layout.setSpacing(6)
        
        rate_label = QLabel("Sample Rate")
        rate_label.setStyleSheet(SECTION_LABEL_STYLE)
        rate_layout.addWidget(rate_label)
        
        self._rate_combo = QComboBox()
        self._rate_combo.setStyleSheet(COMBO_STYLE)
        self._rate_combo.addItems([
            "16,000 Hz (Optimal for Whisper)",
            "44,100 Hz",
            "48,000 Hz",
        ])
        rate_layout.addWidget(self._rate_combo)
        
        grid_layout.addWidget(rate_col, 1)
        layout.addWidget(grid)
        
        # DeepFilterNet status card
        dfn_card = GlassCard()
        dfn_layout = QHBoxLayout(dfn_card)
        dfn_layout.setContentsMargins(16, 12, 16, 12)
        dfn_layout.setSpacing(12)
        
        # Icon + text
        dfn_info = QWidget()
        dfn_info_layout = QVBoxLayout(dfn_info)
        dfn_info_layout.setContentsMargins(0, 0, 0, 0)
        dfn_info_layout.setSpacing(2)
        
        dfn_title = QLabel("DeepFilterNet 3 Active")
        dfn_title.setStyleSheet(f"color: {WHITE}; font-size: 13px; font-weight: 700;")
        dfn_info_layout.addWidget(dfn_title)
        
        dfn_desc = QLabel("Real-time background noise suppression enabled")
        dfn_desc.setStyleSheet(f"color: {EMERALD_500}; font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;")
        dfn_info_layout.addWidget(dfn_desc)
        
        dfn_layout.addWidget(dfn_info)
        dfn_layout.addStretch()
        
        # Toggle switch
        self._dfn_toggle = QPushButton()
        self._dfn_toggle.setCheckable(True)
        self._dfn_toggle.setChecked(True)
        self._dfn_toggle.setFixedSize(56, 28)
        self._dfn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dfn_toggle.setStyleSheet(TOGGLE_STYLE)
        dfn_layout.addWidget(self._dfn_toggle)
        
        layout.addWidget(dfn_card)
        layout.addStretch()
        
        self._sections["Audio Ingestion"] = section
        self._content_layout.addWidget(section)
    
    def _populate_audio_devices(self):
        """Populate the audio device combo box."""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            self._device_combo.clear()
            for i, dev in enumerate(devices):
                if dev['max_input_channels'] > 0:
                    name = f"{dev['name']} ({dev['hostapi']})"
                    self._device_combo.addItem(name, i)
        except Exception:
            self._device_combo.addItems(["Default", "System Loopback", "Wireless Receiver"])
    
    def _create_ai_models_section(self):
        """Create the AI Models section."""
        section = QWidget()
        section.setVisible(False)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        
        title = QLabel("AI Models")
        title.setStyleSheet(LABEL_STYLE)
        layout.addWidget(title)
        
        subtitle = QLabel("Configure STT, embedding, and LLM models")
        subtitle.setStyleSheet(SUBTITLE_STYLE)
        layout.addWidget(subtitle)
        
        # Placeholder cards
        for title_text, desc in [
            ("STT Engine", "Faster-Whisper tiny.en (CUDA)"),
            ("Embedding Model", "all-MiniLM-L6-v2 (ONNX)"),
            ("Cloud LLM", "Gemini 1.5 Flash / Claude Haiku"),
        ]:
            card = GlassCard()
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 12, 16, 12)
            card_layout.setSpacing(4)
            
            t = QLabel(title_text)
            t.setStyleSheet(f"color: {WHITE}; font-size: 13px; font-weight: 700;")
            card_layout.addWidget(t)
            
            d = QLabel(desc)
            d.setStyleSheet(f"color: {SLATE_500}; font-size: 11px;")
            card_layout.addWidget(d)
            
            layout.addWidget(card)
        
        layout.addStretch()
        self._sections["AI Models"] = section
        self._content_layout.addWidget(section)
    
    def _create_display_broadcast_section(self):
        """Create the Display & Broadcast section."""
        section = QWidget()
        section.setVisible(False)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        
        title = QLabel("Display & Broadcast")
        title.setStyleSheet(LABEL_STYLE)
        layout.addWidget(title)
        
        subtitle = QLabel("Configure OBS output, themes, and verse display")
        subtitle.setStyleSheet(SUBTITLE_STYLE)
        layout.addWidget(subtitle)
        
        # WebSocket port
        card = GlassCard()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(8)
        
        port_label = QLabel("WebSocket Port")
        port_label.setStyleSheet(SECTION_LABEL_STYLE)
        card_layout.addWidget(port_label)
        
        port_value = QLabel("8765")
        port_value.setStyleSheet(f"color: {WHITE}; font-size: 14px; font-family: monospace; font-weight: 600;")
        card_layout.addWidget(port_value)
        
        layout.addWidget(card)
        
        # Theme selection
        theme_card = GlassCard()
        theme_layout = QVBoxLayout(theme_card)
        theme_layout.setContentsMargins(16, 12, 16, 12)
        theme_layout.setSpacing(8)
        
        theme_label = QLabel("Default Theme")
        theme_label.setStyleSheet(SECTION_LABEL_STYLE)
        theme_layout.addWidget(theme_label)
        
        self._theme_combo = QComboBox()
        self._theme_combo.setStyleSheet(COMBO_STYLE)
        from core.theme_loader import get_all_themes
        for name, data in get_all_themes().items():
            self._theme_combo.addItem(data.get("label", name), name)
        theme_layout.addWidget(self._theme_combo)
        
        layout.addWidget(theme_card)
        layout.addStretch()
        
        self._sections["Display & Broadcast"] = section
        self._content_layout.addWidget(section)
    
    def _create_database_section(self):
        """Create the Database section."""
        section = QWidget()
        section.setVisible(False)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        
        title = QLabel("Database")
        title.setStyleSheet(LABEL_STYLE)
        layout.addWidget(title)
        
        subtitle = QLabel("Bible database management and index rebuilding")
        subtitle.setStyleSheet(SUBTITLE_STYLE)
        layout.addWidget(subtitle)
        
        # Rebuild indexes button
        card = GlassCard()
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(12)
        
        info = QWidget()
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)
        
        t = QLabel("Rebuild Search Indexes")
        t.setStyleSheet(f"color: {WHITE}; font-size: 13px; font-weight: 700;")
        info_layout.addWidget(t)
        
        d = QLabel("Rebuild BM25 + FAISS indexes from bible.db")
        d.setStyleSheet(f"color: {SLATE_500}; font-size: 11px;")
        info_layout.addWidget(d)
        
        card_layout.addWidget(info)
        card_layout.addStretch()
        
        rebuild_btn = QPushButton("Rebuild")
        rebuild_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rebuild_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(59, 130, 246, 0.2);
                color: {BLUE_500};
                border: 1px solid rgba(59, 130, 246, 0.3);
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: rgba(59, 130, 246, 0.3);
            }}
        """)
        rebuild_btn.clicked.connect(self._rebuild_indexes)
        card_layout.addWidget(rebuild_btn)
        
        layout.addWidget(card)
        layout.addStretch()
        
        self._sections["Database"] = section
        self._content_layout.addWidget(section)
    
    def _create_gpu_hardware_section(self):
        """Create the GPU & Hardware section."""
        section = QWidget()
        section.setVisible(False)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        
        title = QLabel("GPU & Hardware")
        title.setStyleSheet(LABEL_STYLE)
        layout.addWidget(title)
        
        subtitle = QLabel("Monitor GPU usage, temperature, and thermal limits")
        subtitle.setStyleSheet(SUBTITLE_STYLE)
        layout.addWidget(subtitle)
        
        # GPU info card
        card = GlassCard()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(12)
        
        # VRAM
        vram_layout = QVBoxLayout()
        vram_layout.setSpacing(6)
        
        vram_header = QHBoxLayout()
        vram_label = QLabel("VRAM Usage")
        vram_label.setStyleSheet(SECTION_LABEL_STYLE)
        self._gpu_vram_value = QLabel("0.0 / 0.0 GB")
        self._gpu_vram_value.setStyleSheet(VALUE_STYLE)
        vram_header.addWidget(vram_label)
        vram_header.addStretch()
        vram_header.addWidget(self._gpu_vram_value)
        vram_layout.addLayout(vram_header)
        
        self._gpu_vram_bar = QFrame()
        self._gpu_vram_bar.setFixedHeight(6)
        self._gpu_vram_bar.setStyleSheet(f"QFrame {{ background: rgba(255, 255, 255, 0.1); border-radius: 3px; }}")
        self._gpu_vram_fill = QFrame(self._gpu_vram_bar)
        self._gpu_vram_fill.setStyleSheet(f"QFrame {{ background: {BLUE_500}; border-radius: 3px; }}")
        self._gpu_vram_fill.setFixedHeight(6)
        self._gpu_vram_fill.setGeometry(0, 0, 0, 6)
        vram_layout.addWidget(self._gpu_vram_bar)
        
        card_layout.addLayout(vram_layout)
        
        # Temp
        temp_layout = QVBoxLayout()
        temp_layout.setSpacing(6)
        
        temp_header = QHBoxLayout()
        temp_label = QLabel("Temperature")
        temp_label.setStyleSheet(SECTION_LABEL_STYLE)
        self._gpu_temp_value = QLabel("0°C")
        self._gpu_temp_value.setStyleSheet(f"color: {EMERALD_500}; font-size: 14px; font-family: monospace; font-weight: 600;")
        temp_header.addWidget(temp_label)
        temp_header.addStretch()
        temp_header.addWidget(self._gpu_temp_value)
        temp_layout.addLayout(temp_header)
        
        self._gpu_temp_bar = QFrame()
        self._gpu_temp_bar.setFixedHeight(6)
        self._gpu_temp_bar.setStyleSheet(f"QFrame {{ background: rgba(255, 255, 255, 0.1); border-radius: 3px; }}")
        self._gpu_temp_fill = QFrame(self._gpu_temp_bar)
        self._gpu_temp_fill.setStyleSheet(f"QFrame {{ background: {EMERALD_500}; border-radius: 3px; }}")
        self._gpu_temp_fill.setFixedHeight(6)
        self._gpu_temp_fill.setGeometry(0, 0, 0, 6)
        temp_layout.addWidget(self._gpu_temp_bar)
        
        card_layout.addLayout(temp_layout)
        
        # Thermal limits
        limits_layout = QHBoxLayout()
        limits_layout.setSpacing(16)
        
        for label_text, value_text, color in [
            ("Critical", "82°C", RED_500),
            ("Throttle", "78°C", AMBER_500),
            ("Safe", "70°C", EMERALD_500),
        ]:
            limit_widget = QWidget()
            limit_layout = QVBoxLayout(limit_widget)
            limit_layout.setContentsMargins(0, 0, 0, 0)
            limit_layout.setSpacing(2)
            
            l = QLabel(label_text)
            l.setStyleSheet(f"color: {SLATE_500}; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;")
            limit_layout.addWidget(l)
            
            v = QLabel(value_text)
            v.setStyleSheet(f"color: {color}; font-size: 14px; font-family: monospace; font-weight: 700;")
            limit_layout.addWidget(v)
            
            limits_layout.addWidget(limit_widget)
        
        card_layout.addLayout(limits_layout)
        
        layout.addWidget(card)
        layout.addStretch()
        
        self._sections["GPU & Hardware"] = section
        self._content_layout.addWidget(section)
    
    def _create_hotkeys_section(self):
        """Create the Hotkeys section."""
        section = QWidget()
        section.setVisible(False)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._hotkey_editor = HotkeyEditor()
        layout.addWidget(self._hotkey_editor, 1)

        self._sections["Hotkeys"] = section
        self._content_layout.addWidget(section)
    
    def _rebuild_indexes(self):
        """Trigger index rebuild."""
        import subprocess
        try:
            subprocess.Popen(["python", "data/bible/build_bm25.py"], cwd="/home/itorousa/Documents/Code/rhemacast")
        except Exception as e:
            print(f"Failed to start index rebuild: {e}")

    def update_gpu_hardware(self, telemetry: dict):
        """Live-update the GPU & Hardware section from HardwareTelemetryWorker signal."""
        vram_used = telemetry.get("gpu_vram_used_mb", 0)
        vram_total = telemetry.get("vram_total_mb", 0)
        if vram_total > 0 and hasattr(self, "_gpu_vram_value"):
            used_gb = vram_used / 1024
            total_gb = vram_total / 1024
            self._gpu_vram_value.setText(f"{used_gb:.1f} / {total_gb:.1f} GB")
            pct = min(100, max(0, (vram_used / vram_total) * 100))
            self._gpu_vram_fill.setFixedWidth(int(self._gpu_vram_bar.width() * pct / 100))

        temp = telemetry.get("gpu_temp_c", 0)
        if hasattr(self, "_gpu_temp_value"):
            self._gpu_temp_value.setText(f"{temp}°C")
            if temp < 70:
                color = EMERALD_500
            elif temp < 82:
                color = AMBER_500
            else:
                color = RED_500
            self._gpu_temp_value.setStyleSheet(
                f"color: {color}; font-size: 14px; font-family: monospace; font-weight: 600;"
            )
            pct = min(100, max(0, (temp - 30) / 52 * 100))
            self._gpu_temp_fill.setFixedWidth(int(self._gpu_temp_bar.width() * pct / 100))
            self._gpu_temp_fill.setStyleSheet(f"QFrame {{ background: {color}; border-radius: 2px; }}")
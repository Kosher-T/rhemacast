"""
ui/tabs/settings_tab.py

Settings tab with sidebar navigation and glass-card content sections.
Matches the design from ui_draft/settings.html
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QComboBox, QSlider, QFrame, QSizePolicy, QSpinBox,
    QCheckBox, QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal
from ui.widgets.hotkey_editor import HotkeyEditor

from ui.styles import (
    SLATE_950, SLATE_800, SLATE_700, SLATE_600, SLATE_500, SLATE_400,
    SLATE_300, WHITE, BLUE_500, CYAN_400, EMERALD_500, RED_500,
    AMBER_500, BORDER_SUBTLE
)

# Load translations from persistent storage
import json as _json
import os as _os

_translations_path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
                                    "data", "indexes", "translations.json")
try:
    with open(_translations_path) as _f:
        ALL_TRANSLATIONS = _json.load(_f).get("translations", [])
except Exception:
    ALL_TRANSLATIONS = []



# Glass card style — transparent containers (no visible background/border)
GLASS_CARD_STYLE = f"""
    QFrame {{
        background: transparent;
        border: none;
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
        min-width: 140px;
        max-width: 220px;
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
    
    font_size_changed = pyqtSignal(int, int)  # verse_text_size, verse_ref_size
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)
        
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
            "Recording",
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
        self._content_layout.setSpacing(8)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        # Constrain content width so cards don't stretch edge-to-edge
        self._content_widget.setMaximumWidth(720)
        
        # Create section widgets
        self._sections = {}
        self._create_audio_ingestion_section()
        self._create_ai_models_section()
        self._create_display_broadcast_section()
        self._create_database_section()
        self._create_recording_section()
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
        layout.setSpacing(8)

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
        grid_layout.setSpacing(24)
        
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
        
        grid_layout.addWidget(device_col)
        
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
        
        grid_layout.addWidget(rate_col)
        layout.addWidget(grid)
        
        layout.addStretch()
        
        self._sections["Audio Ingestion"] = section
        self._content_layout.addWidget(section)
    
    def _populate_audio_devices(self):
        """Populate the audio device combo box and restore saved selection."""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            self._device_combo.clear()
            
            # On Linux with PipeWire, raw ALSA hw: devices are always locked.
            # Show only PipeWire/PulseAudio routed devices that actually work.
            skip_names = ['hw:', 'sysdefault', 'lavrate', 'samplerate', 'speexrate',
                          'speex', 'upmix', 'vdownmix']
            
            for i, dev in enumerate(devices):
                if dev['max_input_channels'] <= 0:
                    continue
                name_lower = dev['name'].lower()
                if any(s in name_lower for s in skip_names):
                    continue
                    
                hostapi = sd.query_hostapis(dev['hostapi'])['name']
                name = f"{dev['name']} ({hostapi})"
                self._device_combo.addItem(name, i)
            
            # If nothing survived filtering, show all input devices as fallback
            if self._device_combo.count() == 0:
                for i, dev in enumerate(devices):
                    if dev['max_input_channels'] > 0:
                        hostapi = sd.query_hostapis(dev['hostapi'])['name']
                        name = f"{dev['name']} ({hostapi})"
                        self._device_combo.addItem(name, i)
            
            # Restore saved device
            from core.database import get_setting
            saved = get_setting("audio.device_index", "")
            if saved and saved.isdigit():
                idx = int(saved)
                for c in range(self._device_combo.count()):
                    if self._device_combo.itemData(c) == idx:
                        self._device_combo.setCurrentIndex(c)
                        break
            
            # Save on change
            self._device_combo.currentIndexChanged.connect(self._on_device_changed)
        except Exception:
            self._device_combo.addItems(["Default"])
    
    def _on_device_changed(self, index: int):
        """Persist selected audio device index."""
        if index >= 0:
            device_data = self._device_combo.itemData(index)
            if device_data is not None:
                from core.database import set_setting
                set_setting("audio.device_index", str(device_data))
    
    def _create_ai_models_section(self):
        """Create the AI Models section."""
        section = QWidget()
        section.setVisible(False)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

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
            card_layout.setContentsMargins(12, 8, 12, 8)
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
        layout.setSpacing(8)

        title = QLabel("Display & Broadcast")
        title.setStyleSheet(LABEL_STYLE)
        layout.addWidget(title)
        
        subtitle = QLabel("Configure OBS output, themes, and verse display")
        subtitle.setStyleSheet(SUBTITLE_STYLE)
        layout.addWidget(subtitle)
        
        # WebSocket port
        card = GlassCard()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 8, 12, 8)
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
        theme_layout.setContentsMargins(12, 8, 12, 8)
        theme_layout.setSpacing(6)
        
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

        # Verse Display Font Sizes
        font_card = GlassCard()
        font_layout = QVBoxLayout(font_card)
        font_layout.setContentsMargins(12, 8, 12, 8)
        font_layout.setSpacing(8)

        font_title = QLabel("Verse Display")
        font_title.setStyleSheet(SECTION_LABEL_STYLE)
        font_layout.addWidget(font_title)

        from core.database import get_setting

        # Verse Text Size
        row1 = QHBoxLayout()
        row1.setSpacing(12)

        vt_label = QLabel("Verse Text Size")
        vt_label.setStyleSheet(f"color: {SLATE_300}; font-size: 12px; font-weight: 600;")
        row1.addWidget(vt_label)

        self._verse_text_spin = QSpinBox()
        self._verse_text_spin.setRange(8, 16)
        self._verse_text_spin.setValue(int(get_setting("bible.verse_text_size", "12")))
        self._verse_text_spin.setSuffix("px")
        self._verse_text_spin.setStyleSheet(f"""
            QSpinBox {{
                background: rgba(0, 0, 0, 0.4);
                color: {SLATE_300};
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                min-width: 80px;
            }}
            QSpinBox:focus {{ border-color: {BLUE_500}; }}
            QSpinBox::up-button, QSpinBox::down-button {{
                background: rgba(255, 255, 255, 0.1);
                border: none;
                width: 20px;
            }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background: rgba(255, 255, 255, 0.2);
            }}
            QSpinBox::up-arrow {{ border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid {SLATE_400}; }}
            QSpinBox::down-arrow {{ border-left: 4px solid transparent; border-right: 4px solid transparent; border-bottom: 5px solid {SLATE_400}; }}
        """)
        self._verse_text_spin.valueChanged.connect(self._on_font_size_changed)
        row1.addWidget(self._verse_text_spin)

        row1.addStretch()
        font_layout.addLayout(row1)

        # Reference Text Size
        row2 = QHBoxLayout()
        row2.setSpacing(12)

        vr_label = QLabel("Reference Text Size")
        vr_label.setStyleSheet(f"color: {SLATE_300}; font-size: 12px; font-weight: 600;")
        row2.addWidget(vr_label)

        self._verse_ref_spin = QSpinBox()
        self._verse_ref_spin.setRange(7, 14)
        self._verse_ref_spin.setValue(int(get_setting("bible.verse_ref_size", "11")))
        self._verse_ref_spin.setSuffix("px")
        self._verse_ref_spin.setStyleSheet(f"""
            QSpinBox {{
                background: rgba(0, 0, 0, 0.4);
                color: {SLATE_300};
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                min-width: 80px;
            }}
            QSpinBox:focus {{ border-color: {BLUE_500}; }}
            QSpinBox::up-button, QSpinBox::down-button {{
                background: rgba(255, 255, 255, 0.1);
                border: none;
                width: 20px;
            }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background: rgba(255, 255, 255, 0.2);
            }}
            QSpinBox::up-arrow {{ border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid {SLATE_400}; }}
            QSpinBox::down-arrow {{ border-left: 4px solid transparent; border-right: 4px solid transparent; border-bottom: 5px solid {SLATE_400}; }}
        """)
        self._verse_ref_spin.valueChanged.connect(self._on_font_size_changed)
        row2.addWidget(self._verse_ref_spin)

        row2.addStretch()
        font_layout.addLayout(row2)

        layout.addWidget(font_card)
        layout.addStretch()

        self._sections["Display & Broadcast"] = section
        self._content_layout.addWidget(section)

    def _on_font_size_changed(self):
        """Persist font sizes and emit signal for live preview."""
        from core.database import set_setting
        text_size = self._verse_text_spin.value()
        ref_size = self._verse_ref_spin.value()
        set_setting("bible.verse_text_size", str(text_size))
        set_setting("bible.verse_ref_size", str(ref_size))
        self.font_size_changed.emit(text_size, ref_size)
    
    def _create_database_section(self):
        """Create the Database section with index status and rebuild controls."""
        section = QWidget()
        section.setVisible(False)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        title = QLabel("Database")
        title.setStyleSheet(LABEL_STYLE)
        layout.addWidget(title)

        subtitle = QLabel("Search index status and rebuild controls")
        subtitle.setStyleSheet(SUBTITLE_STYLE)
        layout.addWidget(subtitle)

        # ── Index Management Cards ──
        self._index_widgets = {}
        index_defs = [
            ("FTS BM25", "fts", "bm25_fingerprint.json", "Full-text search (exact match)"),
            ("Fuzzy BM25", "fuzzy_bm25", "fuzzy_bm25_fingerprint.json", "Keyword search for fuzzy lane"),
            ("Fuzzy FAISS", "fuzzy_faiss", "faiss_fingerprint.json", "Semantic search (vectors)"),
        ]

        for label, key, fingerprint_file, desc in index_defs:
            card = GlassCard()
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(8)

            # Header row with name + status + rebuild button
            header_row = QHBoxLayout()
            header_row.setSpacing(8)

            name_label = QLabel(label)
            name_label.setStyleSheet(f"color: {WHITE}; font-size: 13px; font-weight: 700;")
            header_row.addWidget(name_label)

            status_label = QLabel("Loading...")
            status_label.setStyleSheet(f"color: {SLATE_500}; font-size: 10px;")
            header_row.addWidget(status_label)

            header_row.addStretch()

            build_btn = QPushButton("Rebuild")
            build_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            build_btn.setFixedHeight(26)
            build_btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(59, 130, 246, 0.15);
                    color: {BLUE_500};
                    border: 1px solid rgba(59, 130, 246, 0.3);
                    border-radius: 4px;
                    padding: 4px 12px;
                    font-size: 10px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background: rgba(59, 130, 246, 0.25);
                }}
                QPushButton:disabled {{
                    background: rgba(255, 255, 255, 0.05);
                    color: {SLATE_600};
                    border: 1px solid rgba(255, 255, 255, 0.1);
                }}
            """)
            build_btn.clicked.connect(lambda checked, k=key: self._rebuild_single_index(k))
            header_row.addWidget(build_btn)

            card_layout.addLayout(header_row)

            # Description
            desc_label = QLabel(desc)
            desc_label.setStyleSheet(f"color: {SLATE_500}; font-size: 10px;")
            card_layout.addWidget(desc_label)

            # Translation tags container
            trans_label = QLabel("Translations:")
            trans_label.setStyleSheet(f"color: {SLATE_400}; font-size: 10px; font-weight: 700;")
            card_layout.addWidget(trans_label)

            tags_container = QWidget()
            tags_layout = QHBoxLayout(tags_container)
            tags_layout.setContentsMargins(0, 0, 0, 0)
            tags_layout.setSpacing(4)
            tags_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
            card_layout.addWidget(tags_container)

            # Add translation row
            add_row = QHBoxLayout()
            add_row.setSpacing(4)

            add_combo = QComboBox()
            add_combo.setStyleSheet(f"""
                QComboBox {{
                    background: rgba(0, 0, 0, 0.3);
                    color: {SLATE_300};
                    border: 1px solid {BORDER_SUBTLE};
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 10px;
                    min-width: 120px;
                    max-height: 24px;
                }}
                QComboBox::drop-down {{
                    border: none;
                    width: 20px;
                }}
                QComboBox::down-arrow {{
                    border-left: 4px solid transparent;
                    border-right: 4px solid transparent;
                    border-top: 5px solid {SLATE_400};
                }}
            """)
            add_combo.setPlaceholderText("Add...")
            add_row.addWidget(add_combo)

            add_btn = QPushButton("+")
            add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            add_btn.setFixedSize(24, 24)
            add_btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(34, 197, 94, 0.15);
                    color: {EMERALD_500};
                    border: 1px solid rgba(34, 197, 94, 0.3);
                    border-radius: 4px;
                    font-size: 14px;
                    font-weight: 700;
                }}
                QPushButton:hover {{
                    background: rgba(34, 197, 94, 0.3);
                }}
            """)
            add_row.addWidget(add_btn)
            add_row.addStretch()

            card_layout.addLayout(add_row)

            # Store widgets
            self._index_widgets[key] = {
                "status_label": status_label,
                "tags_container": tags_container,
                "tags_layout": tags_layout,
                "add_combo": add_combo,
                "add_btn": add_btn,
                "current_translations": [],
            }

            # Wire up add button
            add_btn.clicked.connect(lambda checked, k=key: self._add_translation_to_index(k))
            add_combo.currentIndexChanged.connect(lambda idx, k=key: self._on_combo_changed(idx, k))

            layout.addWidget(card)

        # ── Topical Index (special case) ──
        topical_card = GlassCard()
        topical_layout = QVBoxLayout(topical_card)
        topical_layout.setContentsMargins(12, 10, 12, 10)
        topical_layout.setSpacing(6)

        topical_header = QHBoxLayout()
        topical_header.setSpacing(8)

        topical_name = QLabel("Topical")
        topical_name.setStyleSheet(f"color: {WHITE}; font-size: 13px; font-weight: 700;")
        topical_header.addWidget(topical_name)

        topical_status = QLabel("Loading...")
        topical_status.setStyleSheet(f"color: {SLATE_500}; font-size: 10px;")
        topical_header.addWidget(topical_status)

        topical_header.addStretch()

        topical_build_btn = QPushButton("Rebuild")
        topical_build_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        topical_build_btn.setFixedHeight(26)
        topical_build_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(59, 130, 246, 0.15);
                color: {BLUE_500};
                border: 1px solid rgba(59, 130, 246, 0.3);
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 10px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: rgba(59, 130, 246, 0.25);
            }}
        """)
        topical_build_btn.clicked.connect(lambda: self._rebuild_single_index("topical"))
        topical_header.addWidget(topical_build_btn)

        topical_layout.addLayout(topical_header)

        topical_desc = QLabel("Stories, parables, and miracles index (uses topical_data.json)")
        topical_desc.setStyleSheet(f"color: {SLATE_500}; font-size: 10px;")
        topical_layout.addWidget(topical_desc)

        self._topical_status = topical_status
        layout.addWidget(topical_card)

        # ── Rebuild All ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._rebuild_all_btn = QPushButton("Rebuild All Indexes")
        self._rebuild_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rebuild_all_btn.setFixedHeight(32)
        self._rebuild_all_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(34, 197, 94, 0.15);
                color: {EMERALD_500};
                border: 1px solid rgba(34, 197, 94, 0.3);
                border-radius: 6px;
                padding: 6px 20px;
                font-size: 12px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background: rgba(34, 197, 94, 0.25);
            }}
            QPushButton:disabled {{
                background: rgba(255, 255, 255, 0.05);
                color: {SLATE_600};
                border: 1px solid rgba(255, 255, 255, 0.1);
            }}
        """)
        self._rebuild_all_btn.clicked.connect(self._rebuild_all_indexes)
        btn_row.addWidget(self._rebuild_all_btn)

        layout.addLayout(btn_row)

        # ── Build Log ──
        log_card = GlassCard()
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(12, 10, 12, 10)
        log_layout.setSpacing(6)

        log_header = QLabel("Build Log")
        log_header.setStyleSheet(f"color: {WHITE}; font-size: 13px; font-weight: 700;")
        log_layout.addWidget(log_header)

        self._build_log = QTextEdit()
        self._build_log.setReadOnly(True)
        self._build_log.setMaximumHeight(120)
        self._build_log.setStyleSheet(f"""
            QTextEdit {{
                background: rgba(0, 0, 0, 0.3);
                color: {SLATE_400};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 4px;
                padding: 6px;
                font-size: 10px;
                font-family: monospace;
            }}
        """)
        self._build_log.setPlaceholderText("Build output will appear here...")
        log_layout.addWidget(self._build_log)

        layout.addWidget(log_card)

        layout.addStretch()

        self._sections["Database"] = section
        self._content_layout.addWidget(section)

        # Load index status on startup
        self._load_index_status()

    def _make_translation_tag(self, translation: str, index_key: str) -> QPushButton:
        """Create a removable translation tag button."""
        tag = QPushButton(f"  {translation}  ×")
        tag.setCursor(Qt.CursorShape.PointingHandCursor)
        tag.setFixedHeight(22)
        tag.setStyleSheet(f"""
            QPushButton {{
                background: rgba(59, 130, 246, 0.2);
                color: {BLUE_500};
                border: 1px solid rgba(59, 130, 246, 0.3);
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: rgba(239, 68, 68, 0.2);
                color: {RED_500};
                border: 1px solid rgba(239, 68, 68, 0.3);
            }}
        """)
        tag.clicked.connect(lambda: self._remove_translation_from_index(index_key, translation))
        return tag

    def _add_translation_to_index(self, index_key: str):
        """Add selected translation from combo to the index."""
        widgets = self._index_widgets[index_key]
        combo = widgets["add_combo"]
        idx = combo.currentIndex()
        if idx < 0:
            return
        translation = combo.itemData(idx)
        if not translation:
            return
        if translation in widgets["current_translations"]:
            return

        widgets["current_translations"].append(translation)
        widgets["current_translations"].sort()
        self._refresh_translation_tags(index_key)
        combo.setCurrentIndex(-1)

    def _remove_translation_from_index(self, index_key: str, translation: str):
        """Remove a translation from the index."""
        widgets = self._index_widgets[index_key]
        if translation in widgets["current_translations"]:
            widgets["current_translations"].remove(translation)
            self._refresh_translation_tags(index_key)
            self._populate_add_combo(index_key)

    def _refresh_translation_tags(self, index_key: str):
        """Refresh the displayed translation tags for an index."""
        widgets = self._index_widgets[index_key]
        container = widgets["tags_container"]
        tags_layout = widgets["tags_layout"]

        # Clear existing tags
        while tags_layout.count():
            item = tags_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add tags
        for t in widgets["current_translations"]:
            tag = self._make_translation_tag(t, index_key)
            tags_layout.addWidget(tag)

        if not widgets["current_translations"]:
            empty = QLabel("No translations selected")
            empty.setStyleSheet(f"color: {SLATE_600}; font-size: 10px; font-style: italic;")
            tags_layout.addWidget(empty)

    def _populate_add_combo(self, index_key: str):
        """Populate the add translation combo with available translations."""
        widgets = self._index_widgets[index_key]
        combo = widgets["add_combo"]
        combo.clear()

        for t in sorted(ALL_TRANSLATIONS):
            if t not in widgets["current_translations"]:
                combo.addItem(t, t)

    def _on_combo_changed(self, idx: int, index_key: str):
        """Handle combo selection - auto-add on selection."""
        if idx >= 0:
            self._add_translation_to_index(index_key)

    def _load_index_status(self):
        """Load and display current index status from fingerprint files."""
        import json
        import os

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        indexes_dir = os.path.join(project_root, "data", "indexes")

        fingerprint_map = {
            "fts": "bm25_fingerprint.json",
            "fuzzy_bm25": "fuzzy_bm25_fingerprint.json",
            "fuzzy_faiss": "faiss_fingerprint.json",
        }

        for key, filename in fingerprint_map.items():
            fpath = os.path.join(indexes_dir, filename)
            widgets = self._index_widgets.get(key)
            if not widgets:
                continue

            if os.path.exists(fpath):
                try:
                    with open(fpath) as f:
                        data = json.load(f)
                    translations = data.get("translations", [])
                    verse_count = data.get("verse_count", 0)
                    built_at = data.get("built_at", "")[:10]

                    widgets["status_label"].setText(f"{verse_count:,} verses  •  {built_at}")
                    widgets["status_label"].setStyleSheet(f"color: {EMERALD_500}; font-size: 10px;")

                    # Set current translations
                    widgets["current_translations"] = sorted(translations)
                    self._refresh_translation_tags(key)
                    self._populate_add_combo(key)
                except Exception as e:
                    widgets["status_label"].setText("Error reading fingerprint")
                    widgets["status_label"].setStyleSheet(f"color: {RED_500}; font-size: 10px;")
            else:
                widgets["status_label"].setText("Not built")
                widgets["status_label"].setStyleSheet(f"color: {AMBER_500}; font-size: 10px;")
                widgets["current_translations"] = []
                self._refresh_translation_tags(key)
                self._populate_add_combo(key)

        # Topical index status
        topical_path = os.path.join(indexes_dir, "topical_lookup.pkl")

        if os.path.exists(topical_path):
            try:
                import pickle
                with open(topical_path, "rb") as f:
                    lookup = pickle.load(f)
                self._topical_status.setText(f"{len(lookup)} topics  •  Ready")
                self._topical_status.setStyleSheet(f"color: {EMERALD_500}; font-size: 10px;")
            except Exception:
                self._topical_status.setText("Error reading topical index")
                self._topical_status.setStyleSheet(f"color: {RED_500}; font-size: 10px;")
        else:
            self._topical_status.setText("Not built")
            self._topical_status.setStyleSheet(f"color: {AMBER_500}; font-size: 10px;")

    def _rebuild_single_index(self, index_type: str):
        """Rebuild a single index type."""
        import subprocess
        import os

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        python_bin = os.path.join(project_root, "venv", "bin", "python")
        if not os.path.exists(python_bin):
            python_bin = "python3"

        self._build_log.clear()
        self._build_log.append(f"Building {index_type} index...")

        # Disable buttons
        self._set_build_buttons_enabled(False)

        scripts = {
            "fts": [python_bin, os.path.join(project_root, "data", "bible", "build_bm25.py")],
            "fuzzy_bm25": [python_bin, os.path.join(project_root, "data", "bible", "build_bm25.py"), "--fuzzy"],
            "fuzzy_faiss": [python_bin, os.path.join(project_root, "data", "bible", "build_faiss.py")],
            "topical": [python_bin, os.path.join(project_root, "data", "bible", "build_topical.py"), "--cpu"],
        }

        cmd = scripts.get(index_type)
        if not cmd:
            self._build_log.append(f"Unknown index type: {index_type}")
            self._set_build_buttons_enabled(True)
            return

        # Add translation flags from the index widgets
        if index_type == "fts" and "fts" in self._index_widgets:
            trans = self._index_widgets["fts"]["current_translations"]
            if trans:
                cmd.extend(["--translations", ",".join(trans)])
        elif index_type in ("fuzzy_bm25", "fuzzy_faiss") and index_type in self._index_widgets:
            trans = self._index_widgets[index_type]["current_translations"]
            if trans:
                cmd.extend(["--translations", ",".join(trans)])

        try:
            self._build_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=project_root,
            )

            # Read output in a timer
            from PyQt6.QtCore import QTimer
            self._build_timer = QTimer(self)
            self._build_timer.timeout.connect(lambda: self._read_build_output(index_type))
            self._build_timer.start(100)
        except Exception as e:
            self._build_log.append(f"Error: {e}")
            self._set_build_buttons_enabled(True)

    def _read_build_output(self, index_type: str):
        """Read build process output."""
        import signal

        if not hasattr(self, "_build_process") or self._build_process is None:
            return

        # Non-blocking read
        try:
            import select
            if select.select([self._build_process.stdout], [], [], 0)[0]:
                line = self._build_process.stdout.readline()
                if line:
                    self._build_log.append(line.rstrip())
                    # Auto-scroll
                    sb = self._build_log.verticalScrollBar()
                    sb.setValue(sb.maximum())
        except Exception:
            pass

        # Check if process finished
        if self._build_process.poll() is not None:
            self._build_timer.stop()
            rc = self._build_process.returncode
            if rc == 0:
                self._build_log.append(f"\n✓ {index_type} index built successfully")
            else:
                self._build_log.append(f"\n✗ Build failed (exit code {rc})")
            self._build_process = None
            self._set_build_buttons_enabled(True)
            self._load_index_status()

    def _rebuild_all_indexes(self):
        """Rebuild all indexes sequentially."""
        import subprocess
        import os

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        python_bin = os.path.join(project_root, "venv", "bin", "python")
        if not os.path.exists(python_bin):
            python_bin = "python3"

        self._build_log.clear()
        self._build_log.append("Building all indexes...")

        self._set_build_buttons_enabled(False)

        fts_trans = self._index_widgets.get("fts", {}).get("current_translations", [])
        fuzzy_trans = self._index_widgets.get("fuzzy_bm25", {}).get("current_translations", [])

        scripts = [
            ([python_bin, os.path.join(project_root, "data", "bible", "build_bm25.py"),
              "--translations", ",".join(fts_trans)], "FTS BM25"),
            ([python_bin, os.path.join(project_root, "data", "bible", "build_bm25.py"),
              "--fuzzy", "--translations", ",".join(fuzzy_trans)], "Fuzzy BM25"),
            ([python_bin, os.path.join(project_root, "data", "bible", "build_faiss.py"),
              "--translations", ",".join(fuzzy_trans)], "Fuzzy FAISS"),
            ([python_bin, os.path.join(project_root, "data", "bible", "build_topical.py"),
              "--cpu"], "Topical"),
        ]

        self._build_queue = scripts
        self._build_queue_idx = 0
        self._run_next_build()

    def _run_next_build(self):
        """Run the next build in the queue."""
        import subprocess
        import os

        if self._build_queue_idx >= len(self._build_queue):
            self._build_log.append("\n✓ All indexes built successfully")
            self._set_build_buttons_enabled(True)
            self._load_index_status()
            return

        cmd, name = self._build_queue[self._build_queue_idx]
        self._build_log.append(f"\n── Building {name} ──")

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        try:
            self._build_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=project_root,
            )

            from PyQt6.QtCore import QTimer
            self._build_timer = QTimer(self)
            self._build_timer.timeout.connect(lambda: self._read_build_output_queue(name))
            self._build_timer.start(100)
        except Exception as e:
            self._build_log.append(f"Error building {name}: {e}")
            self._build_queue_idx += 1
            self._run_next_build()

    def _read_build_output_queue(self, name: str):
        """Read build process output for queued builds."""
        import select

        if not hasattr(self, "_build_process") or self._build_process is None:
            return

        try:
            if select.select([self._build_process.stdout], [], [], 0)[0]:
                line = self._build_process.stdout.readline()
                if line:
                    self._build_log.append(line.rstrip())
                    sb = self._build_log.verticalScrollBar()
                    sb.setValue(sb.maximum())
        except Exception:
            pass

        if self._build_process.poll() is not None:
            self._build_timer.stop()
            rc = self._build_process.returncode
            if rc == 0:
                self._build_log.append(f"✓ {name} done")
            else:
                self._build_log.append(f"✗ {name} failed (exit code {rc})")
            self._build_process = None
            self._build_queue_idx += 1

            # Run next after a short delay
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(200, self._run_next_build)

    def _set_build_buttons_enabled(self, enabled: bool):
        """Enable/disable all build buttons."""
        for key, widgets in self._index_widgets.items():
            if "build_btn" in widgets:
                widgets["build_btn"].setEnabled(enabled)
        if hasattr(self, "_rebuild_all_btn"):
            self._rebuild_all_btn.setEnabled(enabled)

    def _create_recording_section(self):
        """Create the Recording section."""
        section = QWidget()
        section.setVisible(False)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("Recording")
        title.setStyleSheet(LABEL_STYLE)
        layout.addWidget(title)

        subtitle = QLabel("Audio recording format and storage")
        subtitle.setStyleSheet(SUBTITLE_STYLE)
        layout.addWidget(subtitle)

        # Encoding format
        card = GlassCard()
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(12, 8, 12, 8)
        card_layout.setSpacing(8)

        info = QWidget()
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)

        t = QLabel("Encoding Format")
        t.setStyleSheet(f"color: {WHITE}; font-size: 13px; font-weight: 700;")
        info_layout.addWidget(t)

        d = QLabel("WAV is lossless; MP3/FLAC/OGG require ffmpeg")
        d.setStyleSheet(f"color: {SLATE_500}; font-size: 11px;")
        info_layout.addWidget(d)

        card_layout.addWidget(info)
        card_layout.addStretch()

        self._rec_format_combo = QComboBox()
        self._rec_format_combo.addItems(["WAV", "MP3", "FLAC", "OGG"])
        self._rec_format_combo.setFixedWidth(120)
        self._rec_format_combo.setStyleSheet(COMBO_STYLE)
        from core.database import get_setting as _gs, set_setting as _ss
        saved = _gs("recording.format", "WAV")
        idx = self._rec_format_combo.findText(saved)
        if idx >= 0:
            self._rec_format_combo.setCurrentIndex(idx)
        self._rec_format_combo.currentTextChanged.connect(
            lambda v: _ss("recording.format", v)
        )
        card_layout.addWidget(self._rec_format_combo)

        layout.addWidget(card)

        # Recording directory info
        dir_card = GlassCard()
        dir_layout = QHBoxLayout(dir_card)
        dir_layout.setContentsMargins(12, 8, 12, 8)
        dir_layout.setSpacing(8)

        dir_info = QWidget()
        dir_info_l = QVBoxLayout(dir_info)
        dir_info_l.setContentsMargins(0, 0, 0, 0)
        dir_info_l.setSpacing(2)

        dt = QLabel("Recording Directory")
        dt.setStyleSheet(f"color: {WHITE}; font-size: 13px; font-weight: 700;")
        dir_info_l.addWidget(dt)

        dd = QLabel("data/recordings/")
        dd.setStyleSheet(f"color: {SLATE_400}; font-size: 11px; font-family: monospace;")
        dir_info_l.addWidget(dd)

        dir_layout.addWidget(dir_info)
        layout.addWidget(dir_card)

        layout.addStretch()

        self._sections["Recording"] = section
        self._content_layout.addWidget(section)
    
    def _create_gpu_hardware_section(self):
        """Create the GPU & Hardware section."""
        section = QWidget()
        section.setVisible(False)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("GPU & Hardware")
        title.setStyleSheet(LABEL_STYLE)
        layout.addWidget(title)
        
        subtitle = QLabel("Monitor GPU usage, temperature, and thermal limits")
        subtitle.setStyleSheet(SUBTITLE_STYLE)
        layout.addWidget(subtitle)
        
        # GPU info card
        card = GlassCard()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 8, 12, 8)
        card_layout.setSpacing(8)
        
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
        limits_layout.setSpacing(8)
        
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
        layout.addWidget(self._hotkey_editor)

        self._sections["Hotkeys"] = section
        self._content_layout.addWidget(section)
    
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
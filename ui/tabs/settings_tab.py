"""
ui/tabs/settings_tab.py

Settings tab with sidebar navigation and glass-card content sections.
Matches the design from ui_draft/settings.html
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QComboBox, QSlider, QFrame, QSizePolicy, QSpinBox,
    QCheckBox, QTextEdit, QFontComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from ui.popups import install_combo
from ui.widgets.hotkey_editor import HotkeyEditor

from ui.styles import (
    SLATE_950, SLATE_800, SLATE_700, SLATE_600, SLATE_500, SLATE_400,
    SLATE_300, WHITE, BLUE_500, CYAN_400, EMERALD_500, RED_500,
    AMBER_500, BORDER_SUBTLE,
    ACCENT, ACCENT_SOFT, ACCENT_BORDER, SELECTION_BG, SELECTION_BORDER,
    TEXT_SELECTION,
    TEXT_FAINT,
    ACCENT_TEXT,
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
        font-size: 13px;
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
        font-size: 13px;
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
        font-size: 13px;
        min-width: 140px;
        max-width: 220px;
    }}
    QComboBox:hover {{
        border-color: {SELECTION_BORDER};
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
        selection-background-color: {TEXT_SELECTION};
        padding: 4px;
    }}
"""

SPIN_STYLE = f"""
    QSpinBox {{
        background: rgba(0, 0, 0, 0.4);
        color: {SLATE_300};
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 6px;
        padding: 6px 12px;
        font-size: 13px;
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
SUBTITLE_STYLE = f"color: {SLATE_500}; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;"
SECTION_LABEL_STYLE = f"color: {SLATE_400}; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;"
VALUE_STYLE = f"color: {BLUE_500}; font-size: 13px; font-family: monospace; font-weight: 600;"
TOGGLE_LABEL_STYLE = f"color: {SLATE_300}; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;"


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
        text_label.setStyleSheet(f"color: {SLATE_400}; font-size: 13px; font-weight: 600; background: transparent;")
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
                    font-size: 13px;
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
    bible_font_changed = pyqtSignal()  # family/weight (sizes ride along)
    
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
            "Audio",
            "AI Models",
            "Display & Broadcast",
            "Interface",
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
        self._content_scroll = content_scroll
        content_scroll.setWidgetResizable(True)
        content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content_scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
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
        self._font_groups = {}
        self._create_audio_section()
        self._create_ai_models_section()
        self._create_display_broadcast_section()
        self._create_interface_section()
        self._create_database_section()
        self._create_gpu_hardware_section()
        self._create_hotkeys_section()

        # Initially show Audio
        self._switch_section("Audio")
        
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
        title.setStyleSheet(f"color: {SLATE_500}; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px;")
        layout.addWidget(title)
        
        # GPU VRAM
        vram_layout = QVBoxLayout()
        vram_layout.setSpacing(4)
        
        vram_header = QHBoxLayout()
        vram_label = QLabel("GPU VRAM")
        vram_label.setStyleSheet(f"color: {SLATE_400}; font-size: 12px; font-weight: 700;")
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
        temp_label.setStyleSheet(f"color: {SLATE_400}; font-size: 12px; font-weight: 700;")
        self._temp_value = QLabel("0°C")
        self._temp_value.setStyleSheet(f"color: {EMERALD_500}; font-size: 13px; font-family: monospace; font-weight: 600;")
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
                self._temp_value.setStyleSheet(f"color: {color}; font-size: 13px; font-family: monospace; font-weight: 600;")
                pct = min(100, max(0, (temp - 30) / 52 * 100))
                self._temp_fill.setFixedWidth(int(self._temp_bar.width() * pct / 100))
                self._temp_fill.setStyleSheet(f"QFrame {{ background: {color}; border-radius: 2px; }}")
        except Exception:
            pass
    
    def _switch_section(self, name: str):
        """Switch the visible content section."""
        self._current_section = name
        # Update sidebar buttons
        for n, item in self._sidebar_items.items():
            item.set_active(n == name)
        
        # Show/hide sections
        for n, widget in self._sections.items():
            widget.setVisible(n == name)

    # ── Unload contract (see MainWindow._unload_tab) ─────────────────────

    def can_unload(self):
        """Index builds and key capture are live work: finish them first."""
        if getattr(self, "_build_process", None) is not None:
            return False, (
                "Settings cannot be unloaded while an index build is running. "
                "Wait for it to finish, then unload the tab.")
        timer = getattr(self, "_build_timer", None)
        if timer is not None and timer.isActive():
            return False, (
                "Settings cannot be unloaded while an index build is running. "
                "Wait for it to finish, then unload the tab.")
        queue = getattr(self, "_build_queue", None)
        if queue and getattr(self, "_build_queue_idx", 0) < len(queue):
            return False, (
                "Settings cannot be unloaded while the index build queue is "
                "still running. Wait for it to finish.")
        from ui.widgets.hotkey_editor import KeyboardHandler
        target = KeyboardHandler._target
        if target is not None and getattr(target, "_capturing", False):
            return False, (
                "Finish the hotkey capture first — unloading Settings would "
                "cancel it.")
        return True, ""

    def current_state(self) -> dict:
        scroll = 0
        try:
            scroll = self._content_scroll.verticalScrollBar().value()
        except (AttributeError, RuntimeError):
            pass
        return {"section": getattr(self, "_current_section", "Audio"),
                "scroll": scroll}

    def restore_state(self, state: dict) -> None:
        section = state.get("section", "Audio")
        if section in self._sections:
            self._switch_section(section)
        scroll = int(state.get("scroll", 0) or 0)
        if scroll:
            from PyQt6.QtCore import QTimer

            def _restore():
                try:
                    self._content_scroll.verticalScrollBar().setValue(scroll)
                except RuntimeError:
                    pass

            QTimer.singleShot(0, _restore)
    
    def _create_audio_section(self):
        """Create the Audio section: ingestion (device, sample rate) and
        recording (format, storage)."""
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Section header
        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        title = QLabel("Audio")
        title.setStyleSheet(LABEL_STYLE)
        header_layout.addWidget(title)

        subtitle = QLabel("Select your audio source and recording format")
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
        install_combo(self._device_combo)
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
        install_combo(self._rate_combo)
        self._rate_combo.setStyleSheet(COMBO_STYLE)
        self._rate_combo.addItems([
            "16,000 Hz (Optimal for Whisper)",
            "44,100 Hz",
            "48,000 Hz",
        ])
        rate_layout.addWidget(self._rate_combo)
        
        grid_layout.addWidget(rate_col)
        layout.addWidget(grid)

        # Recording: format + storage, merged into the same Audio section.
        self._add_recording_group(layout)

        layout.addStretch()

        self._sections["Audio"] = section
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
            d.setStyleSheet(f"color: {SLATE_500}; font-size: 12px;")
            card_layout.addWidget(d)
            
            layout.addWidget(card)
        
        layout.addStretch()
        self._sections["AI Models"] = section
        self._content_layout.addWidget(section)
    
    def _create_display_broadcast_section(self):
        """Create the Display & Broadcast section."""
        from core.database import get_setting
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
        install_combo(self._theme_combo)
        self._theme_combo.setStyleSheet(COMBO_STYLE)
        from core.theme_loader import get_themes_by_kind, SCRIPTURE
        for name, data in get_themes_by_kind(SCRIPTURE).items():
            self._theme_combo.addItem(data.get("label", name), name)
        theme_layout.addWidget(self._theme_combo)
        
        layout.addWidget(theme_card)

        # Display Output sets + broadcast mode
        output_card = GlassCard()
        output_layout = QVBoxLayout(output_card)
        output_layout.setContentsMargins(12, 8, 12, 8)
        output_layout.setSpacing(8)

        output_title = QLabel("Display Output")
        output_title.setStyleSheet(SECTION_LABEL_STYLE)
        output_layout.addWidget(output_title)

        output_sub = QLabel(
            "Each display tab owns its output set; add or remove outputs in "
            "the tab's Outputs page. Mode changes apply immediately.")
        output_sub.setStyleSheet(f"color: {SLATE_500}; font-size: 12px;")
        output_sub.setWordWrap(True)
        output_layout.addWidget(output_sub)

        from core.outputs import (
            get_output_mode, set_output_mode, shared_display_enabled,
            MODE_SIMULTANEOUS, MODE_PRIORITIZED, TAB_OUTPUTS,
        )
        mode_row = QHBoxLayout()
        mode_row.setSpacing(12)
        mode_label = QLabel("Broadcast Mode")
        mode_label.setStyleSheet(
            f"color: {SLATE_300}; font-size: 13px; font-weight: 600;")
        mode_label.setToolTip(
            "Simultaneous: every tab broadcasts through its own set at the "
            "same time (each tab keeps its own Preview/Live). Prioritized: "
            "one set on air at a time — pushing from a tab cloaks the "
            "other sets (tabs share one Preview/Live).")
        mode_row.addWidget(mode_label)
        self._output_mode_combo = QComboBox()
        install_combo(self._output_mode_combo)
        self._output_mode_combo.setStyleSheet(COMBO_STYLE)
        self._output_mode_combo.addItem("Simultaneous", MODE_SIMULTANEOUS)
        self._output_mode_combo.addItem("Prioritized", MODE_PRIORITIZED)
        current_mode = get_output_mode()
        self._output_mode_combo.setCurrentIndex(
            max(0, self._output_mode_combo.findData(current_mode)))
        self._output_mode_combo.currentIndexChanged.connect(
            self._on_output_mode_changed)
        mode_row.addWidget(self._output_mode_combo)
        mode_row.addStretch()
        output_layout.addLayout(mode_row)

        self._shared_display_label = QLabel()
        self._shared_display_label.setStyleSheet(
            f"color: {SLATE_500}; font-size: 12px;")
        output_layout.addWidget(self._shared_display_label)
        self._refresh_shared_display_label()

        self._output_roster = QLabel()
        self._output_roster.setStyleSheet(f"color: {SLATE_500}; font-size: 12px;")
        output_layout.addWidget(self._output_roster)
        self._refresh_output_roster()

        layout.addWidget(output_card)

        # Slides & history behavior (font sizes moved to Interface)
        font_card = GlassCard()
        font_layout = QVBoxLayout(font_card)
        font_layout.setContentsMargins(12, 8, 12, 8)
        font_layout.setSpacing(8)

        font_title = QLabel("Behavior")
        font_title.setStyleSheet(SECTION_LABEL_STYLE)
        font_layout.addWidget(font_title)

        # Slide Navigation Behavior (Ctrl+Left/Right section-hop)
        row5 = QHBoxLayout()
        row5.setSpacing(12)

        sn_label = QLabel("Slide Keys Display")
        sn_label.setStyleSheet(f"color: {SLATE_300}; font-size: 13px; font-weight: 600;")
        sn_label.setToolTip("What the display does while section-hopping with Ctrl+Left/Right")
        row5.addWidget(sn_label)

        self._song_nav_combo = QComboBox()
        install_combo(self._song_nav_combo)
        self._song_nav_combo.setStyleSheet(COMBO_STYLE)
        self._song_nav_combo.addItem("Send on Ctrl release", "deferred")
        self._song_nav_combo.addItem("Update instantly", "instant")
        self._song_nav_combo.addItem("Blank while navigating", "blank")
        saved_nav = get_setting("slides.nav_mode", "deferred")
        self._song_nav_combo.setCurrentIndex(max(0, self._song_nav_combo.findData(saved_nav)))
        self._song_nav_combo.currentIndexChanged.connect(self._on_song_nav_mode_changed)
        row5.addWidget(self._song_nav_combo)

        row5.addStretch()
        font_layout.addLayout(row5)

        # Future: media background while blank (greyed out until image/video streaming lands)
        row6 = QHBoxLayout()
        row6.setSpacing(12)

        mb_label = QLabel("Media Background While Blank")
        mb_label.setStyleSheet(f"color: {SLATE_500}; font-size: 13px; font-weight: 600;")
        row6.addWidget(mb_label)

        self._song_nav_media_combo = QComboBox()
        install_combo(self._song_nav_media_combo)
        self._song_nav_media_combo.setStyleSheet(COMBO_STYLE)
        self._song_nav_media_combo.addItem("Remain visible", "remain")
        self._song_nav_media_combo.addItem("Disappear with text", "disappear")
        saved_media = get_setting("slides.nav_media_bg", "remain")
        self._song_nav_media_combo.setCurrentIndex(max(0, self._song_nav_media_combo.findData(saved_media)))
        self._song_nav_media_combo.setEnabled(False)
        self._song_nav_media_combo.setToolTip("Coming with image/video streaming over WebSocket")
        row6.addWidget(self._song_nav_media_combo)

        row6.addStretch()
        font_layout.addLayout(row6)

        # History verse-context size (verses before/after in preview strip)
        row7 = QHBoxLayout()
        row7.setSpacing(12)

        hc_label = QLabel("History Context Verses")
        hc_label.setStyleSheet(f"color: {SLATE_300}; font-size: 13px; font-weight: 600;")
        hc_label.setToolTip("Verses shown before/after a verse in the History preview strip")
        row7.addWidget(hc_label)

        self._history_context_spin = QSpinBox()
        self._history_context_spin.setRange(0, 10)
        self._history_context_spin.setValue(int(get_setting("history.context_verses", "3")))
        self._history_context_spin.setSuffix(" verses")
        self._history_context_spin.setStyleSheet(SPIN_STYLE)
        self._history_context_spin.valueChanged.connect(self._on_history_context_changed)
        row7.addWidget(self._history_context_spin)

        row7.addStretch()
        font_layout.addLayout(row7)

        layout.addWidget(font_card)

        # Quick-verse typing budget (Bible panel: bare digits → Enter pushes)
        qv_card = GlassCard()
        qv_layout = QVBoxLayout(qv_card)
        qv_layout.setContentsMargins(12, 8, 12, 8)
        qv_layout.setSpacing(8)

        qv_row = QHBoxLayout()
        qv_row.setSpacing(12)

        qv_label = QLabel("Quick Verse Timeout")
        qv_label.setStyleSheet(f"color: {SLATE_300}; font-size: 13px; font-weight: 600;")
        qv_label.setToolTip("Gap allowed between quick-verse keystrokes before the typed number is discarded")
        qv_row.addWidget(qv_label)

        from core.constants import (
            QUICK_VERSE_TIMEOUT_MS_DEFAULT, QUICK_VERSE_TIMEOUT_MS_MIN,
            QUICK_VERSE_TIMEOUT_MS_MAX,
        )
        self._quick_verse_spin = QSpinBox()
        self._quick_verse_spin.setRange(QUICK_VERSE_TIMEOUT_MS_MIN,
                                        QUICK_VERSE_TIMEOUT_MS_MAX)
        try:
            saved_timeout = int(get_setting("bible.quick_verse_timeout_ms",
                                            str(QUICK_VERSE_TIMEOUT_MS_DEFAULT)))
        except (TypeError, ValueError):
            saved_timeout = QUICK_VERSE_TIMEOUT_MS_DEFAULT
        self._quick_verse_spin.setValue(max(QUICK_VERSE_TIMEOUT_MS_MIN,
                                            min(QUICK_VERSE_TIMEOUT_MS_MAX,
                                                saved_timeout)))
        self._quick_verse_spin.setSuffix(" ms")
        self._quick_verse_spin.setStyleSheet(SPIN_STYLE)
        self._quick_verse_spin.valueChanged.connect(self._on_quick_verse_timeout_changed)
        qv_row.addWidget(self._quick_verse_spin)

        qv_row.addStretch()
        qv_layout.addLayout(qv_row)

        layout.addWidget(qv_card)
        layout.addStretch()

        self._sections["Display & Broadcast"] = section
        self._content_layout.addWidget(section)

    def _on_bible_font_changed(self):
        """A Bible font control moved: persist nothing here (each control
        saves its own key), just push live updates to the verse list."""
        groups = self._font_groups
        self.font_size_changed.emit(groups["bible.verse"]["size"].value(),
                                    groups["bible.ref"]["size"].value())
        self.bible_font_changed.emit()

    def _create_interface_section(self):
        """Per-area type controls: family + weight + size + live preview.

        Each control saves only its own key on change, so untouched axes
        stay unset and today's rendering is preserved. Consumers pick
        settings up live (Bible list, tab names, panel headers, schedule
        rows) or on next show/search/open (slide strips, deck list,
        designer, search results).
        """
        section = QWidget()
        section.setVisible(False)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("Interface")
        title.setStyleSheet(LABEL_STYLE)
        layout.addWidget(title)

        subtitle = QLabel("Type per area — sizes in px")
        subtitle.setStyleSheet(SUBTITLE_STYLE)
        layout.addWidget(subtitle)

        self._add_font_group(
            layout, prefix="bible.verse", title="Bible Verses",
            subtitle="Verse list text. Applies instantly.",
            size_min=8, size_max=16, size_default=13, weight_default=400,
            preview_text="And God said, Let there be light: "
                         "and there was light.",
            family_key="bible.verse_font_family",
            weight_key="bible.verse_font_weight",
            size_key="bible.verse_text_size",
            on_change=self._on_bible_font_changed)
        self._add_font_group(
            layout, prefix="bible.ref", title="Bible Reference",
            subtitle="Book chapter:verse. Applies instantly.",
            size_min=7, size_max=14, size_default=12, weight_default=700,
            preview_text="GEN 1:3",
            family_key="bible.verse_ref_font_family",
            weight_key="bible.verse_ref_font_weight",
            size_key="bible.verse_ref_size",
            on_change=self._on_bible_font_changed)
        self._add_font_group(
            layout, prefix="slides.strip", title="Slide Strips",
            subtitle="Applies when Slides is next shown. Family and "
                     "weight override the deck theme once changed.",
            size_min=9, size_max=20, size_default=13, weight_default=700,
            preview_text="Amazing grace how sweet the sound",
            family_key="slides.strip_font_family",
            weight_key="slides.strip_font_weight",
            size_key="slides.strip_font_size")
        self._add_font_group(
            layout, prefix="slides.deck", title="Deck List",
            subtitle="Deck titles. Applies when Slides is next shown.",
            size_min=9, size_max=18, size_default=13, weight_default=700,
            preview_text="Amazing Grace",
            family_key="slides.deck_font_family",
            weight_key="slides.deck_font_weight",
            size_key="slides.deck_font_size")
        self._add_font_group(
            layout, prefix="slides.editor", title="Designer Text",
            subtitle="Lite Designer panes. Applies when the designer is "
                     "next opened.",
            size_min=9, size_max=24, size_default=13, weight_default=400,
            preview_text="Bless the Lord, O my soul",
            family_key="slides.editor_font_family",
            weight_key="slides.editor_font_weight",
            size_key="slides.editor_font_size")
        self._add_font_group(
            layout, prefix="search.result", title="Search Results",
            subtitle="Keyword and Semantic result text. Applies to new searches.",
            size_min=8, size_max=16, size_default=13, weight_default=400,
            preview_text="For God so loved the world, that he gave…",
            family_key="search.result_font_family",
            weight_key="search.result_font_weight",
            size_key="search.result_font_size")
        self._add_font_group(
            layout, prefix="search.ref", title="Search Result Reference",
            subtitle="Result citations. Applies to new searches.",
            size_min=7, size_max=14, size_default=12, weight_default=700,
            preview_text="JHN 3:16",
            family_key="search.ref_font_family",
            weight_key="search.ref_font_weight",
            size_key="search.ref_font_size")
        self._add_font_group(
            layout, prefix="tabs.names", title="Tab Names",
            subtitle="Top tab bar and sub-page tabs (Outputs, Keyword, "
                     "Semantic). Applies instantly.",
            size_min=8, size_max=20, size_default=12, weight_default=600,
            preview_text="Scriptures   Decks   Library   Settings")
        self._add_font_group(
            layout, prefix="panel.labels", title="Panel Labels",
            subtitle="All-caps panel headers — Preview, Live, Schedule, "
                     "STT Monitor. Applies instantly.",
            size_min=8, size_max=28, size_default=13, weight_default=600,
            preview_text="OPERATOR PREVIEW   ·   LIVE   ·   SCHEDULE")
        self._add_font_group(
            layout, prefix="schedule.cards", title="Schedule Cards",
            subtitle="Schedule list rows. Applies instantly.",
            size_min=8, size_max=24, size_default=12, weight_default=600,
            preview_text="[KJV] John 3:16        Default")

        layout.addStretch()

        self._sections["Interface"] = section
        self._content_layout.addWidget(section)

    def _add_font_group(self, parent_layout, *, prefix, title, subtitle,
                        size_min, size_max, size_default, weight_default,
                        preview_text, family_key=None, weight_key=None,
                        size_key=None, on_change=None):
        """One font area card. Returns the control dict (also stored in
        self._font_groups[prefix]). All values set before connecting, so
        building never saves. size_key overrides the default
        "<prefix>.font_size" (legacy size keys keep working)."""
        from PyQt6.QtGui import QFont, QFontDatabase
        from PyQt6.QtWidgets import QApplication, QFontComboBox
        from core.database import get_setting, set_setting
        from ui.app_theme import (INTERFACE_FONT_WEIGHTS, build_interface_font,
                                  notify_interface_font_changed)

        family_setting = family_key or f"{prefix}.font_family"
        weight_setting = weight_key or f"{prefix}.font_weight"
        size_setting = size_key or f"{prefix}.font_size"

        card = GlassCard()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 8, 12, 8)
        card_layout.setSpacing(6)

        head = QLabel(title)
        head.setStyleSheet(SECTION_LABEL_STYLE)
        card_layout.addWidget(head)
        sub = QLabel(subtitle)
        sub.setStyleSheet(f"color: {SLATE_500}; font-size: 12px;")
        sub.setWordWrap(True)
        card_layout.addWidget(sub)

        system_family = QApplication.font().family()
        families = set(QFontDatabase.families())

        fam_combo = QFontComboBox()
        install_combo(fam_combo)
        fam_combo.setStyleSheet(COMBO_STYLE)
        fam_combo.setToolTip("Font family")
        saved_family = get_setting(family_setting, "")
        if saved_family not in families:
            saved_family = ""
        fam_combo.setCurrentFont(QFont(saved_family or system_family))
        card_layout.addWidget(fam_combo)

        row = QHBoxLayout()
        row.setSpacing(8)
        wt_combo = QComboBox()
        install_combo(wt_combo)
        wt_combo.setStyleSheet(COMBO_STYLE)
        wt_combo.setToolTip("Font weight")
        for value, label in INTERFACE_FONT_WEIGHTS:
            wt_combo.addItem(label, value)
        try:
            saved_weight = int(get_setting(weight_setting, ""))
        except (TypeError, ValueError):
            saved_weight = weight_default
        nearest = min((v for v, _ in INTERFACE_FONT_WEIGHTS),
                      key=lambda v: abs(v - saved_weight))
        wt_combo.setCurrentIndex(max(0, wt_combo.findData(nearest)))
        row.addWidget(wt_combo, 1)

        size_spin = QSpinBox()
        size_spin.setRange(size_min, size_max)
        try:
            saved_size = int(get_setting(size_setting, ""))
        except (TypeError, ValueError):
            saved_size = size_default
        size_spin.setValue(max(size_min, min(size_max, saved_size)))
        size_spin.setSuffix(" px")
        size_spin.setToolTip("Font size")
        size_spin.setStyleSheet(SPIN_STYLE)
        row.addWidget(size_spin)
        card_layout.addLayout(row)

        preview = QLabel(preview_text)
        preview.setWordWrap(True)
        preview.setMinimumHeight(56)
        preview.setStyleSheet(f"""
            QLabel {{
                background: rgba(0, 0, 0, 0.4);
                color: {WHITE};
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                padding: 10px 12px;
            }}
        """)
        card_layout.addWidget(preview)

        controls = {"family": fam_combo, "weight": wt_combo,
                    "size": size_spin, "preview": preview,
                    "meta": {"size_min": size_min, "size_max": size_max,
                             "size_default": size_default,
                             "weight_default": weight_default}}
        self._font_groups[prefix] = controls

        def refresh(*_args):
            meta = controls["meta"]
            preview.setFont(build_interface_font(
                fam_combo.currentFont().family(), size_spin.value(),
                wt_combo.currentData(), meta["size_min"], meta["size_max"],
                meta["size_default"], meta["weight_default"]))

        def save_family(*_args):
            set_setting(family_setting,
                        fam_combo.currentFont().family())
            refresh()
            notify_interface_font_changed(prefix)
            if on_change is not None:
                on_change()

        def save_weight(*_args):
            set_setting(weight_setting, str(wt_combo.currentData()))
            refresh()
            notify_interface_font_changed(prefix)
            if on_change is not None:
                on_change()

        def save_size(*_args):
            set_setting(size_setting, str(size_spin.value()))
            refresh()
            notify_interface_font_changed(prefix)
            if on_change is not None:
                on_change()

        fam_combo.currentFontChanged.connect(save_family)
        wt_combo.currentIndexChanged.connect(save_weight)
        size_spin.valueChanged.connect(save_size)
        refresh()
        parent_layout.addWidget(card)
        return controls

    def _on_song_nav_mode_changed(self):
        """Persist song section-hop display behavior (read live on each use)."""
        from core.database import set_setting
        set_setting("slides.nav_mode", self._song_nav_combo.currentData())

    def _on_history_context_changed(self):
        """Persist History preview context size (read live on each use)."""
        from core.database import set_setting
        set_setting("history.context_verses", str(self._history_context_spin.value()))

    def _refresh_shared_display_label(self):
        """Derived shared-state indicator for the saved mode."""
        from core.outputs import shared_display_enabled
        try:
            on = shared_display_enabled(
                self._output_mode_combo.currentData())
        except (AttributeError, RuntimeError):
            return
        self._shared_display_label.setText(
            "Shared display: ON — tabs share one Preview/Live." if on else
            "Shared display: OFF — each tab keeps its own Preview/Live.")

    def _on_output_mode_changed(self):
        """Persist the broadcast mode and apply it immediately.

        Switching to Prioritized re-points every tab's display handle at
        the shared scope (carrying the current screen across, so nothing
        blanks and both tabs converge on one content); switching to
        Simultaneous hands each tab its own scope, seeded from what was
        on screen. No restart: the handles are bound once per tab and
        re-pointed underneath.
        """
        from core.outputs import set_output_mode
        from core.display_state import follow_output_mode
        if set_output_mode(self._output_mode_combo.currentData()):
            follow_output_mode()
        self._refresh_shared_display_label()
        self._refresh_output_roster()

    def _refresh_output_roster(self):
        """Roster line: each tab's pool plus what it is currently using."""
        if not hasattr(self, "_output_roster") or self._output_roster is None:
            return
        from core.outputs import TAB_OUTPUTS, active_outputs, outputs_for_tab
        lines = []
        for tab_key, label in (("SCRIPTURE", "Scriptures"),
                               ("SLIDES", "Decks"),
                               ("MEDIA", "Media"),
                               ("PRESENTATION", "Presentation")):
            pool = outputs_for_tab(tab_key)
            if not pool:
                continue
            span = f"{pool[0]}–{pool[-1]}" if len(pool) > 1 else pool[0]
            active = active_outputs(tab_key)
            if tab_key in ("MEDIA", "PRESENTATION"):
                detail = "reserved"
            elif tuple(active) == tuple(pool):
                detail = "all in use"
            else:
                detail = "using " + ", ".join(active)
            lines.append(f"{label} → Displays {span}  ({detail})")
        self._output_roster.setText("\n".join(lines))

    def _on_quick_verse_timeout_changed(self):
        """Persist the quick-verse inter-keystroke budget (read live on each use)."""
        from core.database import set_setting
        set_setting("bible.quick_verse_timeout_ms", str(self._quick_verse_spin.value()))
    
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
        # Card titles name the SEARCH PAGE each index feeds, not the file
        # format — the operator thinks in pages, not index internals. The
        # description keeps the technical name for whoever rebuilds it.
        index_defs = [
            ("Keyword Index", "fts", None,
             "Keyword page — SQLite FTS5 over all translations, Porter "
             "stemming in the index, ranked by bm25"),
            ("Semantic · BM25", "fuzzy_bm25", "fuzzy_bm25_fingerprint.json",
             "Semantic page, keyword lane — fuzzy BM25 over the "
             "translations below"),
            ("Semantic · Vectors", "fuzzy_faiss", "faiss_fingerprint.json",
             "Semantic page, vector lane — FAISS embeddings (long build on "
             "CPU)"),
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
            status_label.setStyleSheet(f"color: {SLATE_500}; font-size: 12px;")
            header_row.addWidget(status_label)

            header_row.addStretch()

            build_btn = QPushButton("Rebuild")
            build_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            build_btn.setFixedHeight(26)
            build_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {ACCENT_SOFT};
                    color: {ACCENT_TEXT};
                    border: 1px solid {ACCENT_BORDER};
                    border-radius: 4px;
                    padding: 4px 12px;
                    font-size: 12px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background: {SELECTION_BG};
                }}
                QPushButton:disabled {{
                    background: rgba(255, 255, 255, 0.05);
                    color: {TEXT_FAINT};
                    border: 1px solid rgba(255, 255, 255, 0.1);
                }}
            """)
            build_btn.clicked.connect(lambda checked, k=key: self._rebuild_single_index(k))
            header_row.addWidget(build_btn)

            card_layout.addLayout(header_row)

            # Description
            desc_label = QLabel(desc)
            desc_label.setStyleSheet(f"color: {SLATE_500}; font-size: 12px;")
            card_layout.addWidget(desc_label)

            # Every card registers its status label here. The FTS5 card
            # used to register it inside the branch below, which left its
            # status line permanently dead.
            self._index_widgets[key] = {"status_label": status_label}

            if fingerprint_file is None:
                # FTS5 holds every translation in one table, so there is no
                # build-time translation set to pass to a script. But there
                # IS a search-time one: which translations a query fans out
                # across, and that is the operator's choice.
                self._build_fts_translation_picker(card_layout)
                # Same card, same search-time family: how long the lane
                # waits after the last keystroke before it queries.
                self._build_fts_auto_delay_row(card_layout)
            else:
                # Indexes built from a chosen set of translations get the
                # tag picker that feeds their rebuild command.
                # Translation tags container
                trans_label = QLabel("Translations:")
                trans_label.setStyleSheet(f"color: {SLATE_400}; font-size: 12px; font-weight: 700;")
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
                install_combo(add_combo)
                add_combo.setStyleSheet(f"""
                    QComboBox {{
                        background: rgba(0, 0, 0, 0.3);
                        color: {SLATE_300};
                        border: 1px solid {BORDER_SUBTLE};
                        border-radius: 4px;
                        padding: 4px 8px;
                        font-size: 12px;
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

                # Build-flag widgets, alongside the status label stored above
                self._index_widgets[key].update({
                    "tags_container": tags_container,
                    "tags_layout": tags_layout,
                    "add_combo": add_combo,
                    "add_btn": add_btn,
                    "current_translations": [],
                })

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
        topical_status.setStyleSheet(f"color: {SLATE_500}; font-size: 12px;")
        topical_header.addWidget(topical_status)

        topical_header.addStretch()

        topical_build_btn = QPushButton("Rebuild")
        topical_build_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        topical_build_btn.setFixedHeight(26)
        topical_build_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT_SOFT};
                color: {ACCENT_TEXT};
                border: 1px solid {ACCENT_BORDER};
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {SELECTION_BG};
            }}
        """)
        topical_build_btn.clicked.connect(lambda: self._rebuild_single_index("topical"))
        topical_header.addWidget(topical_build_btn)

        topical_layout.addLayout(topical_header)

        topical_desc = QLabel("Stories, parables, and miracles index (uses topical_data.json)")
        topical_desc.setStyleSheet(f"color: {SLATE_500}; font-size: 12px;")
        topical_layout.addWidget(topical_desc)

        self._topical_status = topical_status
        layout.addWidget(topical_card)

        # ── Keyword Index (special case) ──
        keyword_card = GlassCard()
        keyword_layout = QVBoxLayout(keyword_card)
        keyword_layout.setContentsMargins(12, 10, 12, 10)
        keyword_layout.setSpacing(6)

        keyword_header = QHBoxLayout()
        keyword_header.setSpacing(8)

        keyword_name = QLabel("Keyword")
        keyword_name.setStyleSheet(f"color: {WHITE}; font-size: 13px; font-weight: 700;")
        keyword_header.addWidget(keyword_name)

        keyword_status = QLabel("Loading...")
        keyword_status.setStyleSheet(f"color: {SLATE_500}; font-size: 12px;")
        keyword_header.addWidget(keyword_status)

        keyword_header.addStretch()

        keyword_build_btn = QPushButton("Rebuild")
        keyword_build_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        keyword_build_btn.setFixedHeight(26)
        keyword_build_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT_SOFT};
                color: {ACCENT_TEXT};
                border: 1px solid {ACCENT_BORDER};
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {SELECTION_BG};
            }}
        """)
        keyword_build_btn.clicked.connect(lambda: self._rebuild_single_index("keywords"))
        keyword_header.addWidget(keyword_build_btn)

        keyword_layout.addLayout(keyword_header)

        keyword_desc = QLabel("Per-verse topics (Nave's) + lemma glosses (Strong's) — synonyms the verse text never spells out")
        keyword_desc.setStyleSheet(f"color: {SLATE_500}; font-size: 12px;")
        keyword_desc.setWordWrap(True)
        keyword_layout.addWidget(keyword_desc)

        # Display translation: which translation renders keyword-lane hits
        # (keyword results are bare references until looked up here).
        display_row = QHBoxLayout()
        display_row.setSpacing(8)
        display_label = QLabel("Display translation:")
        display_label.setStyleSheet(f"color: {SLATE_400}; font-size: 12px; font-weight: 700;")
        display_row.addWidget(display_label)

        keyword_display_combo = QComboBox()
        install_combo(keyword_display_combo)
        keyword_display_combo.setStyleSheet(f"""
            QComboBox {{
                background: rgba(0, 0, 0, 0.3);
                color: {SLATE_300};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
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
            QComboBox QAbstractItemView {{
                background: rgba(0, 0, 0, 0.9);
                color: {SLATE_300};
        selection-background-color: {TEXT_SELECTION};
            }}
        """)
        keyword_display_combo.currentTextChanged.connect(self._on_keyword_display_changed)
        display_row.addWidget(keyword_display_combo)
        display_row.addStretch()
        keyword_layout.addLayout(display_row)

        self._keyword_status = keyword_status
        self._keyword_build_btn = keyword_build_btn
        self._keyword_display_combo = keyword_display_combo
        layout.addWidget(keyword_card)

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
                font-size: 13px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background: rgba(34, 197, 94, 0.25);
            }}
            QPushButton:disabled {{
                background: rgba(255, 255, 255, 0.05);
                color: {TEXT_FAINT};
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
                font-size: 12px;
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
                background: {ACCENT_SOFT};
                color: {ACCENT_TEXT};
                border: 1px solid {ACCENT_BORDER};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 12px;
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
            empty.setStyleSheet(f"color: {TEXT_FAINT}; font-size: 12px; font-style: italic;")
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

    def _build_fts_auto_delay_row(self, card_layout):
        """How long the Keyword lane waits after the last keystroke.

        A search-time setting like the translation picker above, so it
        persists straight to `search.auto_delay_ms` and the panel reads
        it live on the next keystroke — no restart, no index rebuild.
        "Every keystroke" is 0; the rest are fixed slots so the operator
        cannot pick a delay that stalls the lane.
        """
        from core.constants import (
            SEARCH_AUTO_DELAY_MS_DEFAULT, SEARCH_AUTO_DELAY_MS_SLOTS,
        )
        from core.database import get_setting, set_setting

        row = QHBoxLayout()
        row.setSpacing(6)

        label = QLabel("Auto-search:")
        label.setStyleSheet(f"color: {SLATE_400}; font-size: 12px; font-weight: 700;")
        row.addWidget(label)

        combo = QComboBox()
        install_combo(combo)
        combo.setStyleSheet(f"""
            QComboBox {{
                background: rgba(0, 0, 0, 0.3);
                color: {SLATE_300};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
                min-width: 120px;
                max-height: 24px;
            }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox::down-arrow {{
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {SLATE_400};
            }}
        """)
        combo.addItem("Every keystroke", 0)
        for ms in SEARCH_AUTO_DELAY_MS_SLOTS:
            combo.addItem(f"after {ms} ms", ms)
        try:
            saved = int(get_setting("search.auto_delay_ms",
                                    str(SEARCH_AUTO_DELAY_MS_DEFAULT)))
        except (TypeError, ValueError):
            saved = SEARCH_AUTO_DELAY_MS_DEFAULT
        idx = combo.findData(saved)
        if idx < 0:
            # Hand-edited value between slots: snap to the nearest slot
            # and store it, so the combo never shows a delay that will
            # not run. 0 and the default are always exact matches.
            saved = min(SEARCH_AUTO_DELAY_MS_SLOTS,
                        key=lambda ms: abs(ms - saved)) if saved > 0 \
                else SEARCH_AUTO_DELAY_MS_DEFAULT
            idx = combo.findData(saved)
            set_setting("search.auto_delay_ms", str(saved))
        combo.setCurrentIndex(idx)
        combo.currentIndexChanged.connect(self._on_search_auto_delay_changed)
        row.addWidget(combo)
        self._search_auto_delay_combo = combo

        hint = QLabel("wait after the last keystroke")
        hint.setStyleSheet(f"color: {TEXT_FAINT}; font-size: 12px;")
        row.addWidget(hint)
        row.addStretch()

        card_layout.addLayout(row)

    def _on_search_auto_delay_changed(self, idx: int):
        """Persist the chosen auto-search delay (0 = every keystroke)."""
        from core.database import set_setting
        combo = self._search_auto_delay_combo
        value = combo.itemData(idx) if idx >= 0 else None
        if value is None:
            return
        set_setting("search.auto_delay_ms", str(int(value)))

    # ── FTS5 search translations (search-time, not build-time) ────────────

    def _build_fts_translation_picker(self, card_layout):
        """Which translations an FTS query fans out across.

        This is a search-time setting, so it persists straight to
        `search.fts_translations` and takes effect on the next query —
        there is no index to rebuild. Capped because past a handful the
        fan-out stops being a search and becomes a corpus scan per
        keystroke.
        """
        from core.constants import FTS_MAX_TRANSLATIONS
        from core.bible_service import fts_translations

        header = QHBoxLayout()
        header.setSpacing(6)
        label = QLabel("Search translations:")
        label.setStyleSheet(f"color: {SLATE_400}; font-size: 12px; font-weight: 700;")
        header.addWidget(label)
        self._fts_trans_count = QLabel("")
        self._fts_trans_count.setStyleSheet(f"color: {SLATE_500}; font-size: 12px;")
        header.addWidget(self._fts_trans_count)
        header.addStretch()
        card_layout.addLayout(header)

        tags_container = QWidget()
        tags_layout = QHBoxLayout(tags_container)
        tags_layout.setContentsMargins(0, 0, 0, 0)
        tags_layout.setSpacing(4)
        tags_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        card_layout.addWidget(tags_container)

        add_row = QHBoxLayout()
        add_row.setSpacing(4)
        combo = QComboBox()
        install_combo(combo)
        combo.setStyleSheet(f"""
            QComboBox {{
                background: rgba(0, 0, 0, 0.3);
                color: {SLATE_300};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
                min-width: 120px;
                max-height: 24px;
            }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox::down-arrow {{
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {SLATE_400};
            }}
        """)
        combo.setPlaceholderText("Add...")
        add_row.addWidget(combo)
        add_row.addStretch()
        card_layout.addLayout(add_row)

        self._fts_trans_widgets = {
            "tags_layout": tags_layout,
            "combo": combo,
            "current": list(fts_translations()),
        }
        combo.currentIndexChanged.connect(self._on_fts_translation_picked)
        self._refresh_fts_translation_tags()

    def _refresh_fts_translation_tags(self):
        """Redraw the tags and the n/max counter, and refill the combo."""
        from core.constants import FTS_MAX_TRANSLATIONS
        from core.bible_service import get_available_translations

        w = getattr(self, "_fts_trans_widgets", None)
        if not w:
            return
        current = w["current"]
        while w["tags_layout"].count():
            item = w["tags_layout"].takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not current:
            empty = QLabel("No translations selected")
            empty.setStyleSheet(f"color: {TEXT_FAINT}; font-size: 12px; font-style: italic;")
            w["tags_layout"].addWidget(empty)
        for t in current:
            tag = QPushButton(f"  {t}  ×")
            tag.setCursor(Qt.CursorShape.PointingHandCursor)
            tag.setFixedHeight(22)
            tag.setStyleSheet(f"""
                QPushButton {{
                    background: {ACCENT_SOFT};
                    color: {ACCENT_TEXT};
                    border: 1px solid {ACCENT_BORDER};
                    border-radius: 4px;
                    padding: 2px 8px;
                    font-size: 12px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background: rgba(239, 68, 68, 0.2);
                    color: {RED_500};
                    border: 1px solid rgba(239, 68, 68, 0.3);
                }}
            """)
            tag.clicked.connect(lambda _=False, t=t: self._remove_fts_translation(t))
            w["tags_layout"].addWidget(tag)

        at_cap = len(current) >= FTS_MAX_TRANSLATIONS
        if getattr(self, "_fts_trans_count", None) is not None:
            self._fts_trans_count.setText(f"{len(current)} / {FTS_MAX_TRANSLATIONS}")

        combo = w["combo"]
        combo.clear()
        if not at_cap:
            try:
                available = get_available_translations()
            except Exception:
                available = []
            for t in sorted(available):
                if t.upper() not in current:
                    combo.addItem(t, t)
        combo.setEnabled(not at_cap and combo.count() > 0)

    def _on_fts_translation_picked(self, idx):
        """Add the chosen translation and persist immediately."""
        from core.bible_service import set_fts_translations
        w = getattr(self, "_fts_trans_widgets", None)
        if not w or idx < 0:
            return
        combo = w["combo"]
        translation = combo.itemData(idx)
        combo.setCurrentIndex(-1)
        if not translation or translation.upper() in w["current"]:
            return
        w["current"] = set_fts_translations(w["current"] + [translation])
        self._refresh_fts_translation_tags()
        self._rebuild_fts_index_for_selection()

    def _rebuild_fts_index_for_selection(self):
        """The index IS the selection, so a new selection means a rebuild.

        Left to the Rebuild button this would be a silent trap: the search
        would keep answering from the old set, and a translation the
        operator just chose would return nothing with no explanation. The
        build is a subprocess writing to bible.db, so it runs off the GUI
        thread exactly like the other index builds; the card's status line
        reports progress and the build log carries the output.
        """
        self._load_fts_status(self._project_root())
        self._rebuild_single_index("fts")

    @staticmethod
    def _project_root() -> str:
        return _os.path.dirname(_os.path.dirname(
            _os.path.dirname(_os.path.abspath(__file__))))

    def _remove_fts_translation(self, translation):
        """Drop a translation and persist immediately."""
        from core.bible_service import set_fts_translations
        w = getattr(self, "_fts_trans_widgets", None)
        if not w:
            return
        remaining = [t for t in w["current"] if t.upper() != translation.upper()]
        if not remaining:
            # Never leave the lane searching nothing.
            return
        w["current"] = set_fts_translations(remaining)
        self._refresh_fts_translation_tags()
        self._rebuild_fts_index_for_selection()

    def _load_fts_status(self, project_root):
        """Report the live FTS5 index: row count and its tokenizer.

        Stemming lives in the index, so the tokenizer is the fact that
        matters here — a table without `porter` is a stale build that will
        silently miss inflections.
        """
        import sqlite3
        widgets = self._index_widgets.get("fts")
        if not widgets:
            return
        label = widgets["status_label"]
        db_path = _os.path.join(project_root, "data", "bible", "bible.db")
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            try:
                row = conn.execute(
                    "SELECT sql FROM sqlite_master WHERE name='verses_fts'"
                ).fetchone()
                indexed = conn.execute(
                    "SELECT COUNT(*) FROM verses_fts").fetchone()[0]
                verses = conn.execute(
                    "SELECT COUNT(*) FROM verses").fetchone()[0]
                # Which translations are actually IN the index, as opposed
                # to which ones are chosen. These diverge whenever the
                # selection changes and the rebuild has not happened yet —
                # and until it does, every query silently misses the newly
                # chosen translation.
                indexed_versions = {r[0] for r in conn.execute(
                    "SELECT DISTINCT v.version FROM verses_fts fts "
                    "JOIN verses v ON v.id = fts.rowid")}
            finally:
                conn.close()
        except Exception as e:
            label.setText(f"Error reading index: {e}")
            label.setStyleSheet(f"color: {RED_500}; font-size: 12px;")
            return
        if not row:
            label.setText("Not built")
            label.setStyleSheet(f"color: {AMBER_500}; font-size: 12px;")
            return
        tokenizer = ""
        for part in row[0].split(","):
            if "tokenize" in part:
                tokenizer = part.strip().strip("()").strip().strip("'\"")
                break
        stemmed = "porter" in tokenizer
        from core.bible_service import fts_translations
        chosen = set(fts_translations())
        stale = indexed_versions != chosen
        if not stemmed or stale:
            note = []
            if not stemmed:
                note.append("no stemming")
            if stale:
                missing = sorted(chosen - indexed_versions)
                extra = sorted(indexed_versions - chosen)
                if missing:
                    note.append(f"missing {', '.join(missing)}")
                if extra:
                    note.append(f"stale {', '.join(extra)}")
            label.setText(f"{indexed:,} indexed  •  needs rebuild — "
                          + "; ".join(note))
            label.setStyleSheet(f"color: {AMBER_500}; font-size: 12px;")
            return
        label.setText(f"{indexed:,} indexed  •  Porter stemming  •  "
                      f"{len(chosen)} translation(s)")
        label.setStyleSheet(f"color: {EMERALD_500}; font-size: 12px;")

    def _load_index_status(self):
        """Load and display current index status from fingerprint files."""
        import json
        import os

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        indexes_dir = os.path.join(project_root, "data", "indexes")

        # The FTS lane has no fingerprint: it is a virtual table inside
        # bible.db, so its status is the table itself.
        self._load_fts_status(project_root)

        fingerprint_map = {
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
                    widgets["status_label"].setStyleSheet(f"color: {EMERALD_500}; font-size: 12px;")

                    # Set current translations
                    widgets["current_translations"] = sorted(translations)
                    self._refresh_translation_tags(key)
                    self._populate_add_combo(key)
                except Exception as e:
                    widgets["status_label"].setText("Error reading fingerprint")
                    widgets["status_label"].setStyleSheet(f"color: {RED_500}; font-size: 12px;")
            else:
                widgets["status_label"].setText("Not built")
                widgets["status_label"].setStyleSheet(f"color: {AMBER_500}; font-size: 12px;")
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
                self._topical_status.setStyleSheet(f"color: {EMERALD_500}; font-size: 12px;")
            except Exception:
                self._topical_status.setText("Error reading topical index")
                self._topical_status.setStyleSheet(f"color: {RED_500}; font-size: 12px;")
        else:
            self._topical_status.setText("Not built")
            self._topical_status.setStyleSheet(f"color: {AMBER_500}; font-size: 12px;")

        # Keyword index status + display-translation combo
        meta_path = os.path.join(indexes_dir, "keywords_meta.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
                verses = meta.get("verses_indexed", 0)
                built_at = meta.get("built_at", "")[:10]
                self._keyword_status.setText(f"{verses:,} verses  •  {built_at}")
                self._keyword_status.setStyleSheet(f"color: {EMERALD_500}; font-size: 12px;")
            except Exception:
                self._keyword_status.setText("Error reading keyword index")
                self._keyword_status.setStyleSheet(f"color: {RED_500}; font-size: 12px;")
        else:
            self._keyword_status.setText("Not built")
            self._keyword_status.setStyleSheet(f"color: {AMBER_500}; font-size: 12px;")
        self._refresh_keyword_display_combo()

    def _refresh_keyword_display_combo(self):
        """Populate the keyword display-translation combo from the setting."""
        from core.database import get_setting
        combo = self._keyword_display_combo
        combo.blockSignals(True)
        try:
            combo.clear()
            options = [t for t in ALL_TRANSLATIONS] if ALL_TRANSLATIONS else ["KJV"]
            for t in options:
                combo.addItem(t)
            current = (get_setting("search.keyword_display_translation", "KJV") or "KJV").upper()
            idx = combo.findText(current)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
        finally:
            combo.blockSignals(False)

    def _on_keyword_display_changed(self, text: str):
        """Persist the keyword display translation (validated at read time)."""
        from core.database import set_setting
        if text:
            set_setting("search.keyword_display_translation", text.upper())

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
            "fts": [python_bin, os.path.join(project_root, "data", "bible", "rebuild_fts.py")],
            "fuzzy_bm25": [python_bin, os.path.join(project_root, "data", "bible", "build_bm25.py"), "--fuzzy"],
            "fuzzy_faiss": [python_bin, os.path.join(project_root, "data", "bible", "build_faiss.py")],
            "topical": [python_bin, os.path.join(project_root, "data", "bible", "build_topical.py"), "--cpu"],
            "keywords": [python_bin, os.path.join(project_root, "data", "bible", "build_keywords.py")],
        }

        cmd = scripts.get(index_type)
        if not cmd:
            self._build_log.append(f"Unknown index type: {index_type}")
            self._set_build_buttons_enabled(True)
            return

        # Add translation flags from the index widgets. The FTS index has
        # no tag picker: it spans every translation in one table.
        if index_type in ("fuzzy_bm25", "fuzzy_faiss") and index_type in self._index_widgets:
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

        fuzzy_trans = self._index_widgets.get("fuzzy_bm25", {}).get("current_translations", [])

        scripts = [
            # FTS is one stemmed table over every translation: no
            # translation set to pass, and no BM25 pickle to build.
            ([python_bin, os.path.join(project_root, "data", "bible", "rebuild_fts.py")],
             "Keyword Index"),
            ([python_bin, os.path.join(project_root, "data", "bible", "build_bm25.py"),
              "--fuzzy", "--translations", ",".join(fuzzy_trans)],
             "Semantic · BM25"),
            ([python_bin, os.path.join(project_root, "data", "bible", "build_faiss.py"),
              "--translations", ",".join(fuzzy_trans)],
             "Semantic · Vectors"),
            ([python_bin, os.path.join(project_root, "data", "bible", "build_topical.py"),
              "--cpu"], "Topical"),
            ([python_bin, os.path.join(project_root, "data", "bible", "build_keywords.py")],
             "Topical Keywords"),
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
        if hasattr(self, "_keyword_build_btn"):
            self._keyword_build_btn.setEnabled(enabled)

    def _add_recording_group(self, layout: QVBoxLayout):
        """Append the recording controls (format + storage) to *layout*.

        Called from `_create_audio_section` so ingestion and recording sit
        under the single Audio subtab; the controls are unchanged.
        """
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
        d.setStyleSheet(f"color: {SLATE_500}; font-size: 12px;")
        info_layout.addWidget(d)

        card_layout.addWidget(info)
        card_layout.addStretch()

        self._rec_format_combo = QComboBox()
        install_combo(self._rec_format_combo)
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
        dd.setStyleSheet(f"color: {SLATE_400}; font-size: 12px; font-family: monospace;")
        dir_info_l.addWidget(dd)

        dir_layout.addWidget(dir_info)
        layout.addWidget(dir_card)

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
            l.setStyleSheet(f"color: {SLATE_500}; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;")
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
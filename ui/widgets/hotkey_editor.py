"""
ui/widgets/hotkey_editor.py

Video-game style hotkey editor widget.
Allows users to bind keys to actions with backspace to clear.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QSizePolicy, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent
from PyQt6.QtGui import QKeySequence, QKeyEvent, QFont

from ui.styles import (
    SLATE_950, SLATE_800, SLATE_700, SLATE_600, SLATE_500, SLATE_400,
    SLATE_300, WHITE, BLUE_500, CYAN_400, EMERALD_500, AMBER_500, RED_500,
    BORDER_SUBTLE
)


class HotkeyCaptureButton(QPushButton):
    """Button that captures a key press for hotkey binding."""

    key_captured = pyqtSignal(str)  # Emits the key sequence string

    def __init__(self, current_key: str = "", parent=None):
        super().__init__(parent)
        self._current_key = current_key
        self._capturing = False
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_text()
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {SLATE_400};
                border: none;
                border-bottom: 2px solid transparent;
                padding: 2px 6px;
                font-size: 11px;
                font-family: monospace;
                font-weight: 600;
                min-width: 100px;
            }}
            QPushButton:hover {{
                color: {WHITE};
                border-bottom-color: rgba(59, 130, 246, 0.5);
            }}
            QPushButton:checked {{
                color: {CYAN_400};
                border-bottom-color: {BLUE_500};
            }}
        """)

    def _update_text(self):
        if self._capturing:
            self.setText("Press a key... (Space×3 to cancel)")
        elif self._current_key:
            self.setText(self._current_key)
        else:
            self.setText("Not bound")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_capture()
        super().mousePressEvent(event)

    def _start_capture(self):
        self._capturing = True
        self._space_press_count = 0
        self._last_space_time = 0
        self._current_modifiers = Qt.KeyboardModifier.NoModifier
        self.setChecked(True)
        self._update_text()
        KeyboardHandler.install(self)

    def event(self, e):
        if self._capturing and e.type() == QEvent.Type.KeyPress:
            self._handle_key_capture(e)
            return True
        return super().event(e)

    def keyPressEvent(self, event: QKeyEvent):
        if self._capturing:
            self._handle_key_capture(event)
        else:
            super().keyPressEvent(event)

    def _handle_key_capture(self, event: QKeyEvent):
        key = event.key()
        modifiers = event.modifiers()

# Map common media keys to their F-key equivalents
        # This allows capturing volume/brightness keys as F-keys without Fn
        MEDIA_TO_FKEY = {
            Qt.Key.Key_VolumeMute: Qt.Key.Key_F1,
            Qt.Key.Key_VolumeDown: Qt.Key.Key_F2,
            Qt.Key.Key_VolumeUp: Qt.Key.Key_F3,
            Qt.Key.Key_MediaPlay: Qt.Key.Key_F4,
            Qt.Key.Key_MediaPause: Qt.Key.Key_F4,
            Qt.Key.Key_MediaStop: Qt.Key.Key_F5,
            Qt.Key.Key_MediaPrevious: Qt.Key.Key_F6,
            Qt.Key.Key_MediaNext: Qt.Key.Key_F7,
            Qt.Key.Key_MediaRecord: Qt.Key.Key_F8,
            Qt.Key.Key_HomePage: Qt.Key.Key_F9,
            Qt.Key.Key_Search: Qt.Key.Key_F11,
            Qt.Key.Key_Sleep: Qt.Key.Key_F12,
            Qt.Key.Key_WakeUp: Qt.Key.Key_F12,
            Qt.Key.Key_MonBrightnessDown: Qt.Key.Key_F1,
            Qt.Key.Key_MonBrightnessUp: Qt.Key.Key_F2,
            Qt.Key.Key_KeyboardLightOnOff: Qt.Key.Key_F5,
            Qt.Key.Key_KeyboardBrightnessDown: Qt.Key.Key_F1,
            Qt.Key.Key_KeyboardBrightnessUp: Qt.Key.Key_F2,
            Qt.Key.Key_AudioForward: Qt.Key.Key_F8,
            Qt.Key.Key_AudioRewind: Qt.Key.Key_F7,
            Qt.Key.Key_MicVolumeUp: Qt.Key.Key_F3,
            Qt.Key.Key_MicVolumeDown: Qt.Key.Key_F2,
            Qt.Key.Key_MicMute: Qt.Key.Key_F1,
            Qt.Key.Key_AudioCycleTrack: Qt.Key.Key_F9,
            Qt.Key.Key_Video: Qt.Key.Key_F10,
            Qt.Key.Key_Camera: Qt.Key.Key_F11,
            Qt.Key.Key_Exit: Qt.Key.Key_F12,
            Qt.Key.Key_Select: Qt.Key.Key_F12,
            Qt.Key.Key_Print: Qt.Key.Key_F12,
            Qt.Key.Key_Execute: Qt.Key.Key_F12,
        }

        # Translate media keys to F-keys
        if key in MEDIA_TO_FKEY:
            key = MEDIA_TO_FKEY[key]

        # Triple Space cancels (press Space 3 times quickly)
        if key == Qt.Key.Key_Space:
            import time
            now = time.time()
            if now - self._last_space_time < 0.5:
                self._space_press_count += 1
            else:
                self._space_press_count = 1
            self._last_space_time = now
            if self._space_press_count >= 3:
                self._cancel_capture()
            return

        # Reset space counter on any other key
        self._space_press_count = 0

        # Backspace clears the binding
        if key == Qt.Key.Key_Backspace:
            self._current_key = ""
            self.key_captured.emit("")
            self._cancel_capture()
            return

        # Ignore modifier keys when pressed alone (Ctrl, Alt, Shift, Meta)
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift, Qt.Key.Key_Meta):
            self._current_modifiers = modifiers
            self._update_capturing_text()
            return

        # A non-modifier key was pressed - build the full combination
        parts = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            parts.append("Meta")

        # Get key name
        key_text = QKeySequence(key).toString(QKeySequence.SequenceFormat.NativeText)
        if key_text:
            parts.append(key_text)

        if parts:
            self._current_key = "+".join(parts)
            self.key_captured.emit(self._current_key)
        else:
            self._current_key = ""

        self._cancel_capture()

    def _update_capturing_text(self):
        """Update button text while waiting for the main key."""
        parts = []
        if self._current_modifiers & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if self._current_modifiers & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if self._current_modifiers & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if self._current_modifiers & Qt.KeyboardModifier.MetaModifier:
            parts.append("Meta")
        
        if parts:
            self.setText(" + ".join(parts) + " + ...")
        else:
            self.setText("Press a key... (Space×3 to cancel)")

    def _handle_mouse_capture(self, event):
        """Handle mouse button press during hotkey capture."""
        button = event.button()
        
        # Map mouse buttons to readable names
        MOUSE_BUTTON_MAP = {
            Qt.MouseButton.LeftButton: "MouseLeft",
            Qt.MouseButton.RightButton: "MouseRight",
            Qt.MouseButton.MiddleButton: "MouseMiddle",
            Qt.MouseButton.BackButton: "MouseBack",
            Qt.MouseButton.ForwardButton: "MouseForward",
        }
        
        # Get button name
        button_name = MOUSE_BUTTON_MAP.get(button)
        if not button_name:
            return
        
        # Build modifier combo
        modifiers = event.modifiers()
        parts = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            parts.append("Meta")
        
        parts.append(button_name)
        
        self._current_key = "+".join(parts)
        self.key_captured.emit(self._current_key)
        self._cancel_capture()

    def _cancel_capture(self):
        self._capturing = False
        self.setChecked(False)
        self._update_text()
        KeyboardHandler.uninstall(self)

    def set_key(self, key: str):
        """Set the key programmatically."""
        self._current_key = key
        self._update_text()

    def get_key(self) -> str:
        return self._current_key


class KeyboardHandler(QWidget):
    """Global keyboard event filter for capturing keys."""
    
    _instance = None
    _target = None
    capture_started = pyqtSignal()
    capture_finished = pyqtSignal()
    
    @classmethod
    def install(cls, target):
        if cls._instance is None:
            cls._instance = cls()
        cls._target = target
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().installEventFilter(cls._instance)
        cls._instance.capture_started.emit()
    
    @classmethod
    def uninstall(cls, target):
        if cls._target is target:
            cls._target = None
            if cls._instance:
                from PyQt6.QtWidgets import QApplication
                QApplication.instance().removeEventFilter(cls._instance)
                cls._instance.capture_finished.emit()
    
    def eventFilter(self, obj, event):
        if self._target and hasattr(self._target, '_capturing') and self._target._capturing:
            # Block keyboard events during capture (including ShortcutOverride that eats F1)
            if event.type() in (QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride):
                if event.type() == QEvent.Type.KeyPress:
                    self._target.keyPressEvent(event)
                return True
            # Capture mouse clicks during hotkey capture
            if event.type() == QEvent.Type.MouseButtonPress:
                self._target._handle_mouse_capture(event)
                return True
        return super().eventFilter(obj, event)


class HotkeyRow(QFrame):
    """A single row in the hotkey editor: action name + capture button."""

    changed = pyqtSignal(str, str)  # action_id, key_sequence

    def __init__(self, action_id: str, action_name: str, description: str, current_key: str, parent=None):
        super().__init__(parent)
        self.action_id = action_id
        self.setStyleSheet(f"""
            QFrame {{
                background: transparent;
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(12)

        # Action info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(0)

        name_label = QLabel(action_name)
        name_label.setStyleSheet(f"color: {WHITE}; font-size: 12px; font-weight: 600;")
        info_layout.addWidget(name_label)

        desc_label = QLabel(description)
        desc_label.setStyleSheet(f"color: {SLATE_500}; font-size: 10px;")
        info_layout.addWidget(desc_label)

        layout.addLayout(info_layout, 1)

        # Capture button
        self.capture_btn = HotkeyCaptureButton(current_key)
        self.capture_btn.key_captured.connect(self._on_key_captured)
        layout.addWidget(self.capture_btn)

        # Clear button
        self.clear_btn = QPushButton("✕")
        self.clear_btn.setFixedSize(22, 22)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {SLATE_600};
                border: none;
                border-radius: 3px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                color: {RED_500};
            }}
        """)
        self.clear_btn.clicked.connect(self._on_clear)
        layout.addWidget(self.clear_btn)

    def _on_key_captured(self, key: str):
        self.changed.emit(self.action_id, key)

    def _on_clear(self):
        self.capture_btn.set_key("")
        self.changed.emit(self.action_id, "")

    def get_key(self) -> str:
        return self.capture_btn.get_key()


class TranslationHotkeyRow(QFrame):
    """A row for translation-specific hotkey: name + dropdown + capture button + remove."""

    changed = pyqtSignal(str, str)  # translation, key_sequence
    removed = pyqtSignal(str)       # translation

    def __init__(self, translation: str, key: str, available: list[str], parent=None):
        super().__init__(parent)
        self._translation = translation
        self.setStyleSheet(f"""
            QFrame {{
                background: transparent;
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(12)

        # Left side: name + dropdown
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        name_label = QLabel("Switch Translation")
        name_label.setStyleSheet(f"color: {WHITE}; font-size: 12px; font-weight: 600;")
        info_layout.addWidget(name_label)

        # Dropdown inline under the name
        self._combo = QComboBox()
        self._combo.addItems(available)
        if translation in available:
            self._combo.setCurrentText(translation)
        self._combo.setFixedHeight(24)
        self._combo.setStyleSheet(f"""
            QComboBox {{
                background: transparent;
                color: {SLATE_300};
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                padding: 1px 4px;
                font-size: 10px;
                font-weight: 600;
                min-width: 60px;
            }}
            QComboBox:hover {{
                border-bottom-color: rgba(59, 130, 246, 0.5);
            }}
            QComboBox::drop-down {{
                border: none;
                width: 14px;
            }}
            QComboBox QAbstractItemView {{
                background: {SLATE_800};
                color: {WHITE};
                border: 1px solid {BORDER_SUBTLE};
                selection-background-color: rgba(59, 130, 246, 0.3);
            }}
        """)
        self._combo.currentTextChanged.connect(self._on_translation_changed)
        info_layout.addWidget(self._combo)

        layout.addLayout(info_layout, 1)

        # Capture button (same as HotkeyRow)
        self.capture_btn = HotkeyCaptureButton(key)
        self.capture_btn.key_captured.connect(self._on_key_captured)
        layout.addWidget(self.capture_btn)

        # Remove button (same as HotkeyRow clear_btn)
        self._remove_btn = QPushButton("✕")
        self._remove_btn.setFixedSize(22, 22)
        self._remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remove_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {SLATE_600};
                border: none;
                border-radius: 3px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                color: {RED_500};
            }}
        """)
        self._remove_btn.clicked.connect(lambda: self.removed.emit(self._translation))
        layout.addWidget(self._remove_btn)

    def _on_translation_changed(self, text: str):
        old = self._translation
        self._translation = text
        self.changed.emit(old, self.capture_btn.get_key())

    def _on_key_captured(self, key: str):
        self.changed.emit(self._translation, key)

    def get_translation(self) -> str:
        return self._combo.currentText()

    def get_key(self) -> str:
        return self.capture_btn.get_key()


class HotkeyEditor(QWidget):
    """Main hotkey editor widget with list of bindable actions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._actions = {}
        self._rows = {}
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Header
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        title = QLabel("Hotkeys")
        title.setStyleSheet(f"color: {WHITE}; font-size: 14px; font-weight: 700;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        
        # Reset to defaults button
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {SLATE_500};
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 10px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                color: {AMBER_500};
            }}
        """)
        reset_btn.clicked.connect(self._reset_to_defaults)
        header_layout.addWidget(reset_btn)
        
        layout.addWidget(header)

        # Scrollable list of hotkey rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 0.1);
                border-radius: 3px;
            }}
        """)

        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.setSpacing(8)
        self._container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self._container)

        layout.addWidget(scroll, 1)

        # Define default actions
        self._default_bindings = {
            "clear_recall": ("Clear / Recall", "Clear live display or recall last verse", "F6"),
            "fts_search": ("FTS Search", "Open FTS5+BM25 search across 6 translations", "Ctrl+Shift+F"),
            "fuzzy_search": ("Fuzzy Search", "Open semantic/FAISS search panel", "Ctrl+Shift+S"),
            "next_verse": ("Next", "Navigate to next scheduled verse", "Right"),
            "prev_verse": ("Previous", "Navigate to previous scheduled verse", "Left"),
            "toggle_transcription": ("Start/Stop Transcription", "Toggle live transcription", "F7"),
            "add_to_schedule": ("Add to Schedule", "Add selected verse to schedule", "Alt+Return"),
            "double_click": ("Double Click", "Simulate mouse double-click at cursor", "D"),
        }

        self._load_bindings()
        self._build_rows()

    def _load_bindings(self):
        """Load saved bindings from settings."""
        from core.database import get_setting
        import json
        saved = get_setting("hotkeys.bindings", "{}")
        try:
            self._bindings = json.loads(saved)
        except Exception:
            self._bindings = {}

    def _save_bindings(self):
        """Save bindings to settings."""
        from core.database import set_setting
        import json
        set_setting("hotkeys.bindings", json.dumps(self._bindings))

    def _build_rows(self):
        """Build the UI rows for each action."""
        for action_id, (name, desc, default_key) in self._default_bindings.items():
            # Get saved key or use default
            key = self._bindings.get(action_id, default_key)
            row = HotkeyRow(action_id, name, desc, key)
            row.changed.connect(self._on_binding_changed)
            self._container_layout.addWidget(row)
            self._rows[action_id] = row

        # ── Translation Shortcuts section ──
        self._container_layout.addSpacing(16)

        trans_header = QLabel("Translation Shortcuts")
        trans_header.setStyleSheet(f"color: {WHITE}; font-size: 14px; font-weight: 800;")
        self._container_layout.addWidget(trans_header)

        trans_desc = QLabel("Bind a key to instantly switch to a specific translation")
        trans_desc.setStyleSheet(f"color: {SLATE_500}; font-size: 11px;")
        self._container_layout.addWidget(trans_desc)

        self._container_layout.addSpacing(4)

        self._trans_rows_container = QWidget()
        self._trans_rows_layout = QVBoxLayout(self._trans_rows_container)
        self._trans_rows_layout.setContentsMargins(0, 0, 0, 0)
        self._trans_rows_layout.setSpacing(6)
        self._container_layout.addWidget(self._trans_rows_container)

        self._trans_rows: list[TranslationHotkeyRow] = []

        # Add button
        self._add_trans_btn = QPushButton("+ Add Translation Shortcut")
        self._add_trans_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_trans_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {CYAN_400};
                border: 1px dashed rgba(34, 211, 238, 0.3);
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                border-color: {CYAN_400};
                background: rgba(34, 211, 238, 0.05);
            }}
        """)
        self._add_trans_btn.clicked.connect(self._add_translation_row)
        self._container_layout.addWidget(self._add_trans_btn)

        self._container_layout.addStretch()

        # Load existing translation bindings
        self._load_trans_bindings()

    def _get_available_translations(self) -> list[str]:
        """Get list of available translation abbreviations."""
        from core.bible_service import get_available_translations
        return get_available_translations()

    def _get_used_translations(self) -> set[str]:
        """Get translations already bound to a hotkey."""
        return {row.get_translation() for row in self._trans_rows}

    def _load_trans_bindings(self):
        """Load saved translation hotkey bindings."""
        import json
        from core.database import get_setting
        saved = get_setting("hotkeys.trans_bindings", "[]")
        try:
            bindings = json.loads(saved)
        except Exception:
            bindings = []

        available = self._get_available_translations()
        for trans, key in bindings:
            self._add_translation_row(trans, key, available)

    def _save_trans_bindings(self):
        """Save translation hotkey bindings."""
        import json
        from core.database import set_setting
        bindings = [(row.get_translation(), row.get_key()) for row in self._trans_rows]
        set_setting("hotkeys.trans_bindings", json.dumps(bindings))

    def _add_translation_row(self, translation: str = None, key: str = "", available: list[str] = None):
        """Add a new translation hotkey row."""
        if available is None:
            available = self._get_available_translations()

        if not translation:
            # Pick first unused translation
            used = self._get_used_translations()
            for t in available:
                if t not in used:
                    translation = t
                    break
            if not translation:
                translation = available[0] if available else "KJV"

        row = TranslationHotkeyRow(translation, key, available)
        row.changed.connect(self._on_trans_binding_changed)
        row.removed.connect(self._remove_translation_row)
        self._trans_rows_layout.addWidget(row)
        self._trans_rows.append(row)
        self._save_trans_bindings()
        self._apply_bindings()

    def _remove_translation_row(self, translation: str):
        """Remove a translation hotkey row."""
        for row in self._trans_rows:
            if row.get_translation() == translation:
                self._trans_rows.remove(row)
                self._trans_rows_layout.removeWidget(row)
                row.deleteLater()
                break
        self._save_trans_bindings()
        self._apply_bindings()

    def _on_trans_binding_changed(self, old_trans: str, key: str):
        """Handle translation binding change (key captured or dropdown changed)."""
        self._save_trans_bindings()
        self._apply_bindings()

    def _on_binding_changed(self, action_id: str, key: str):
        self._bindings[action_id] = key
        self._save_bindings()
        self._apply_bindings()

    def _reset_to_defaults(self):
        """Reset all bindings to defaults."""
        self._bindings = {}
        for action_id, (_, _, default_key) in self._default_bindings.items():
            self._bindings[action_id] = default_key
            if action_id in self._rows:
                self._rows[action_id].capture_btn.set_key(default_key)
        self._save_bindings()
        self._apply_bindings()

    def _apply_bindings(self):
        """Apply the current bindings to the application."""
        # This will be connected to MainWindow to update shortcuts
        self.bindings_changed.emit(self._bindings)

    bindings_changed = pyqtSignal(dict)
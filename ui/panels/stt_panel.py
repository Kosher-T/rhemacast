"""
ui/panels/stt_panel.py

Right panel: STT transcript monitor.
Shows live transcription output from Thread 2.
Emits transcription_started/stopped signals for backend control.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from ui.styles import (
    PANEL_HEADER_STYLE, PANEL_HEADER_LABEL_STYLE, PANEL_BODY_STYLE,
    EMERALD_400, EMERALD_500, SLATE_100, SLATE_300, SLATE_400, SLATE_500,
    WHITE, BORDER_SUBTLE, BLUE_500, CYAN_400, AMBER_500
)

# Colors for model indicator
_WHISPER_COLOR = CYAN_400
_VOSK_COLOR = AMBER_500


class STTPanel(QWidget):
    """STT Monitor panel (right side)."""

    transcription_started = pyqtSignal()
    transcription_stopped = pyqtSignal()
    recording_started = pyqtSignal()
    recording_stopped = pyqtSignal()
    recording_paused = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(PANEL_BODY_STYLE)
        self._is_transcribing = False
        self._is_recording = False
        self._active_model = "none"  # "whisper", "vosk", "none"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ──
        header = QWidget()
        header.setStyleSheet(PANEL_HEADER_STYLE)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 6, 12, 6)

        title = QLabel("STT Monitor")
        title.setStyleSheet(PANEL_HEADER_LABEL_STYLE)
        header_layout.addWidget(title)
        header_layout.addStretch()

        # Model indicator
        self._model_label = QLabel()
        self._model_label.setStyleSheet(f"color: {SLATE_500}; font-size: 10px; font-weight: 600;")
        self._model_label.setText("No model")
        header_layout.addWidget(self._model_label)

        header_layout.addSpacing(8)

        # Transcribe button
        self.transcribe_btn = QPushButton("●")
        self.transcribe_btn.setFixedSize(28, 28)
        self._set_btn_ready()
        self.transcribe_btn.setToolTip("Start/Stop live transcription")
        self.transcribe_btn.clicked.connect(self._toggle_transcription)
        header_layout.addWidget(self.transcribe_btn)

        layout.addWidget(header)

        # Transcript output
        self.transcript_view = QTextEdit()
        self.transcript_view.setReadOnly(True)
        self.transcript_view.setStyleSheet(f"""
            QTextEdit {{
                background: rgba(0, 0, 0, 50);
                color: {SLATE_100};
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                border: none;
                padding: 12px;
                line-height: 1.6;
            }}
        """)
        layout.addWidget(self.transcript_view)

        # ── Control buttons (centered at bottom) ──
        STT_BTN_STYLE = f"""
            QPushButton {{
                background: rgba(30, 41, 59, 0.6);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 4px;
                font-size: 10px;
                font-weight: 600;
                padding: 0 10px;
            }}
            QPushButton:hover {{
                background: rgba(30, 41, 59, 0.9);
                color: #f8fafc;
            }}
        """
        STT_BTN_ACTIVE_STYLE = f"""
            QPushButton {{
                background: rgba(239, 68, 68, 0.2);
                color: #ef4444;
                border: 1px solid rgba(239, 68, 68, 0.3);
                border-radius: 4px;
                font-size: 10px;
                font-weight: 600;
                padding: 0 10px;
            }}
            QPushButton:hover {{
                background: rgba(239, 68, 68, 0.3);
            }}
        """
        REC_BTN_STYLE = f"""
            QPushButton {{
                background: rgba(30, 41, 59, 0.6);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 4px;
                font-size: 10px;
                font-weight: 600;
                padding: 0 10px;
            }}
            QPushButton:hover {{
                background: rgba(30, 41, 59, 0.9);
                color: #f8fafc;
            }}
        """
        REC_BTN_ACTIVE_STYLE = f"""
            QPushButton {{
                background: rgba(239, 68, 68, 0.25);
                color: #ef4444;
                border: 1px solid rgba(239, 68, 68, 0.3);
                border-radius: 4px;
                font-size: 10px;
                font-weight: 600;
                padding: 0 10px;
            }}
            QPushButton:hover {{
                background: rgba(239, 68, 68, 0.4);
            }}
        """

        ctrl_bar = QHBoxLayout()
        ctrl_bar.setContentsMargins(0, 8, 0, 8)
        ctrl_bar.setSpacing(6)
        ctrl_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_transcribe = QPushButton("TRANSCRIBE")
        self.btn_transcribe.setFixedHeight(24)
        self.btn_transcribe.setStyleSheet(STT_BTN_STYLE)
        self.btn_transcribe.setToolTip("Start/Stop live transcription")
        self.btn_transcribe.clicked.connect(self._toggle_transcription)
        ctrl_bar.addWidget(self.btn_transcribe)

        self.btn_record = QPushButton("REC")
        self.btn_record.setFixedHeight(24)
        self.btn_record.setStyleSheet(REC_BTN_STYLE)
        self.btn_record.setToolTip("Start/Stop audio recording")
        self.btn_record.clicked.connect(self._on_record_clicked)
        ctrl_bar.addWidget(self.btn_record)

        self.btn_pause_rec = QPushButton("PAUSE")
        self.btn_pause_rec.setFixedHeight(24)
        self.btn_pause_rec.setStyleSheet(STT_BTN_STYLE)
        self.btn_pause_rec.setToolTip("Pause/Resume recording")
        self.btn_pause_rec.setEnabled(False)
        self.btn_pause_rec.clicked.connect(self._on_pause_clicked)
        ctrl_bar.addWidget(self.btn_pause_rec)

        layout.addLayout(ctrl_bar)

        # Store styles for state changes
        self._stt_btn_style = STT_BTN_STYLE
        self._stt_btn_active_style = STT_BTN_ACTIVE_STYLE
        self._rec_btn_style = REC_BTN_STYLE
        self._rec_btn_active_style = REC_BTN_ACTIVE_STYLE

    def _set_btn_ready(self):
        self.transcribe_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(16, 185, 129, 0.2);
                color: {EMERALD_400};
                border: none;
                border-radius: 14px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: rgba(16, 185, 129, 0.35);
            }}
        """)

    def _set_btn_recording(self):
        self.transcribe_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(239, 68, 68, 0.25);
                color: #ef4444;
                border: none;
                border-radius: 14px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: rgba(239, 68, 68, 0.4);
            }}
        """)

    def _toggle_transcription(self):
        self._is_transcribing = not self._is_transcribing
        if self._is_transcribing:
            self._set_btn_recording()
            self.transcribe_btn.setToolTip("Stop live transcription")
            self.btn_transcribe.setText("STOP")
            self.btn_transcribe.setStyleSheet(self._stt_btn_active_style)
            self.transcription_started.emit()
        else:
            self._set_btn_ready()
            self.transcribe_btn.setToolTip("Start live transcription")
            self.btn_transcribe.setText("TRANSCRIBE")
            self.btn_transcribe.setStyleSheet(self._stt_btn_style)
            self._active_model = "none"
            self._update_model_label()
            self.transcription_stopped.emit()

    def _on_record_clicked(self):
        """Emit recording signal; PresentationTab handles the actual logic."""
        if self._is_recording:
            self._is_recording = False
            self.btn_record.setText("REC")
            self.btn_record.setStyleSheet(self._rec_btn_style)
            self.btn_pause_rec.setEnabled(False)
            self.btn_pause_rec.setText("PAUSE")
            self.recording_stopped.emit()
        else:
            self._is_recording = True
            self.btn_record.setText("STOP")
            self.btn_record.setStyleSheet(self._rec_btn_active_style)
            self.btn_pause_rec.setEnabled(True)
            self.recording_started.emit()

    def _on_pause_clicked(self):
        """Emit recording_paused signal; PresentationTab handles the actual logic."""
        self.recording_paused.emit()

    def set_recording_state(self, recording: bool):
        """Update recording button state externally."""
        self._is_recording = recording
        if recording:
            self.btn_record.setText("STOP")
            self.btn_record.setStyleSheet(self._rec_btn_active_style)
            self.btn_pause_rec.setEnabled(True)
        else:
            self.btn_record.setText("REC")
            self.btn_record.setStyleSheet(self._rec_btn_style)
            self.btn_pause_rec.setEnabled(False)
            self.btn_pause_rec.setText("PAUSE")

    def set_model(self, model: str):
        """Update the active model indicator. model: 'whisper' or 'vosk'."""
        self._active_model = model
        self._update_model_label()

    def _update_model_label(self):
        if self._active_model == "whisper":
            self._model_label.setText("Whisper tiny.en")
            self._model_label.setStyleSheet(f"color: {_WHISPER_COLOR}; font-size: 10px; font-weight: 600;")
        elif self._active_model == "vosk":
            self._model_label.setText("Vosk (failover)")
            self._model_label.setStyleSheet(f"color: {_VOSK_COLOR}; font-size: 10px; font-weight: 600;")
        else:
            self._model_label.setText("")
            self._model_label.setStyleSheet(f"color: {SLATE_500}; font-size: 10px; font-weight: 600;")

    def append_transcript(self, text: str):
        """Append a new transcript chunk to the monitor."""
        # Check for model switch prefix
        if text.startswith("[MODEL:"):
            model = text.split("]")[0].replace("[MODEL:", "")
            self.set_model(model)
            return

        self.transcript_view.append(
            f'<span style="color: {SLATE_300};">{text}</span>'
        )
        # Auto-scroll to bottom
        sb = self.transcript_view.verticalScrollBar()
        sb.setValue(sb.maximum())

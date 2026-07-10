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
from PyQt6.QtCore import Qt, pyqtSignal

from ui.styles import (
    PANEL_HEADER_STYLE, PANEL_HEADER_LABEL_STYLE, PANEL_BODY_STYLE,
    EMERALD_400, EMERALD_500, SLATE_100, SLATE_400, SLATE_500,
    WHITE, BORDER_SUBTLE, BLUE_500
)


class STTPanel(QWidget):
    """STT Monitor panel (right side)."""

    transcription_started = pyqtSignal()
    transcription_stopped = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(PANEL_BODY_STYLE)
        self._is_transcribing = False

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

        # Transcribe button
        self.transcribe_btn = QPushButton("●")
        self.transcribe_btn.setFixedSize(28, 28)
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
        self.transcript_view.setHtml(
            f'<p style="color: {EMERALD_400}; opacity: 0.6; font-style: italic;">'
            '🟢 // Audio Stream Ready</p>'
        )
        layout.addWidget(self.transcript_view)

    def _toggle_transcription(self):
        self._is_transcribing = not self._is_transcribing
        if self._is_transcribing:
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
            self.transcribe_btn.setToolTip("Stop live transcription")
            self.transcript_view.append(
                f'<p style="color: {EMERALD_400}; font-style: italic;">'
                '🔴 // Transcription Started</p>'
            )
            self.transcription_started.emit()
        else:
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
            self.transcribe_btn.setToolTip("Start live transcription")
            self.transcript_view.append(
                f'<p style="color: {EMERALD_400}; font-style: italic;">'
                '🟢 // Transcription Stopped</p>'
            )
            self.transcription_stopped.emit()

    def append_transcript(self, text: str):
        """Append a new transcript chunk to the monitor."""
        self.transcript_view.append(f'<p style="color: {SLATE_100};">{text}</p>')

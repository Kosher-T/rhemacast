"""
ui/panels/stt_panel.py

Right panel: STT transcript monitor + operator preview.
Shows live transcription output from Thread 2.
Emits transcription_started/stopped signals for backend control.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFrame, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal

from ui.widgets.aspect_ratio import AspectRatioWidget
from ui.styles import (
    PANEL_HEADER_STYLE, PANEL_HEADER_LABEL_STYLE, PANEL_BODY_STYLE,
    EMERALD_400, EMERALD_500, SLATE_100, SLATE_400, SLATE_500,
    WHITE, BORDER_SUBTLE, BLUE_500
)


class STTPanel(QWidget):
    """STT Monitor + Operator Preview panel (right side)."""

    transcription_started = pyqtSignal()
    transcription_stopped = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(PANEL_BODY_STYLE)
        self._is_transcribing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Vertical Splitter: STT on top, Preview on bottom ──
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        # ── STT Section ──
        stt_container = QWidget()
        stt_layout = QVBoxLayout(stt_container)
        stt_layout.setContentsMargins(0, 0, 0, 0)
        stt_layout.setSpacing(0)

        # Header
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

        stt_layout.addWidget(header)

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
        stt_layout.addWidget(self.transcript_view)

        splitter.addWidget(stt_container)

        # ── Preview Section ──
        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)

        preview_header = QWidget()
        preview_header.setStyleSheet(f"""
            border-top: 1px solid {BORDER_SUBTLE};
            padding: 6px 12px;
        """)
        preview_header_layout = QHBoxLayout(preview_header)
        preview_header_layout.setContentsMargins(12, 4, 12, 4)
        preview_title = QLabel("OPERATOR PREVIEW")
        preview_title.setStyleSheet(f"""
            color: {SLATE_500}; font-size: 9px; font-weight: 700;
            letter-spacing: 2px;
        """)
        preview_header_layout.addWidget(preview_title)
        preview_layout.addWidget(preview_header, 0) # stretch=0

        # Preview viewport
        self.preview_frame = QFrame()
        self.preview_frame.setObjectName("OperatorPreviewViewport")
        self.preview_frame.setStyleSheet(f"""
            QFrame#OperatorPreviewViewport {{
                background: black;
                border: 1px solid rgba(59, 130, 246, 0.2);
                border-radius: 6px;
                margin: 8px;
            }}
        """)
        
        self.preview_ar_widget = AspectRatioWidget(self.preview_frame, aspect_ratio=16.0/9.0, min_width=160, max_width=540)

        preview_inner = QVBoxLayout(self.preview_frame)
        preview_inner.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.preview_label = QLabel("PREVIEW")
        self.preview_label.setStyleSheet(f"""
            color: rgba(255, 255, 255, 12);
            font-size: 18px; font-weight: 900;
            font-style: italic; letter-spacing: 4px;
        """)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_inner.addWidget(self.preview_label)

        preview_layout.addWidget(self.preview_ar_widget, 1) # stretch=1
        splitter.addWidget(preview_container)

        # Default ratio: 70% STT, 30% Preview
        splitter.setSizes([350, 150])
        layout.addWidget(splitter)

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

    def update_preview(self, text: str, ref: str):
        """Update the operator preview with the current display state."""
        self.preview_label.setText(f"{text}\n\n— {ref}")
        self.preview_label.setStyleSheet(f"""
            color: {WHITE};
            font-size: 13px; font-weight: 600;
            font-style: normal; letter-spacing: 0px;
            padding: 12px;
        """)

    def clear_preview(self):
        """Reset the preview to its default state."""
        self.preview_label.setText("PREVIEW")
        self.preview_label.setStyleSheet(f"""
            color: rgba(255, 255, 255, 12);
            font-size: 18px; font-weight: 900;
            font-style: italic; letter-spacing: 4px;
        """)

"""
ui/dialogs/add_translation_dialog.py

Dialog for adding Bible translations. Offers two options:
  1. Visit the download page (biblelist.netlify.app)
  2. Import a local file (XML, XMM, CSV, JSON)

The layout and behavior are unchanged; the surface, option rows and Cancel
button now resolve through ``ui.tokens`` so this dialog matches the message
dialogs on both platforms.
"""

import os
import webbrowser
import logging

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QFileDialog,
)
from PyQt6.QtCore import Qt

from ui import dialogs, tokens

logger = logging.getLogger(__name__)

_DOWNLOAD_URL = "https://biblelist.netlify.app/"
_FILE_FILTER = (
    "Bible Source Files (*.xml *.xmm *.csv *.json);;"
    "XML Files (*.xml);;"
    "XMM Files (*.xmm);;"
    "CSV Files (*.csv);;"
    "JSON Files (*.json);;"
    "All Files (*)"
)

_OPTION_NAME = "rcDialogOption"
_OPTION_TITLE_NAME = "rcDialogOptionTitle"
_OPTION_HINT_NAME = "rcDialogOptionHint"


class AddTranslationDialog(dialogs.Dialog):
    """Modal dialog offering download-page or local-file import."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Translation")
        # Fixed width, natural height: text wraps at one width on every
        # platform, and extra wrapped lines grow the card instead of being
        # clipped by a hard-coded pixel height.
        self.setFixedWidth(400)
        self._selected_path: str | None = None
        self._build_ui()

    def _build_ui(self):
        layout = self.body_layout

        title = QLabel("Add Translation", self.surface)
        title.setObjectName("rcDialogTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            "Download from the web, or import a file you already have.",
            self.surface)
        subtitle.setObjectName("rcDialogBody")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addSpacing(tokens.SPACE_4)

        web_btn = self._make_option_button(
            "Visit Download Page",
            "Open biblelist.netlify.app in your browser",
            on_click=self._on_visit_web,
        )
        layout.addWidget(web_btn)

        file_btn = self._make_option_button(
            "Import File...",
            "Pick XML, XMM, CSV, or JSON from your file manager",
            on_click=self._on_import_file,
        )
        layout.addWidget(file_btn)

        layout.addStretch(1)

        cancel_row = QHBoxLayout()
        cancel_row.addStretch(1)
        cancel_btn = QPushButton("Cancel", self.surface)
        cancel_btn.setFixedHeight(tokens.BUTTON_HEIGHT)
        cancel_btn.setMinimumWidth(84)
        cancel_btn.setStyleSheet(tokens.button_qss("secondary"))
        cancel_btn.clicked.connect(self.reject)
        cancel_row.addWidget(cancel_btn)
        layout.addLayout(cancel_row)

    def _make_option_button(self, title: str, subtitle: str,
                            on_click=None) -> QFrame:
        """Create a styled two-line option button."""
        frame = QFrame(self.surface)
        frame.setObjectName(_OPTION_NAME)
        frame.setFixedHeight(52)
        frame.setCursor(Qt.CursorShape.PointingHandCursor)
        frame.setStyleSheet(f"""
            QFrame#{_OPTION_NAME} {{
                background: {tokens.BG_CARD};
                border: 1px solid {tokens.BORDER_HAIRLINE};
                border-radius: {tokens.RADIUS_SM}px;
            }}
            QFrame#{_OPTION_NAME}:hover {{
                background: {tokens.BG_CARD_HOVER};
                border-color: {tokens.ACCENT_BORDER};
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(
            tokens.SPACE_12, tokens.SPACE_8,
            tokens.SPACE_12, tokens.SPACE_8)
        layout.setSpacing(2)

        title_label = QLabel(title, frame)
        title_label.setObjectName(_OPTION_TITLE_NAME)
        title_label.setStyleSheet(f"""
            QLabel#{_OPTION_TITLE_NAME} {{
                background: transparent;
                border: none;
                color: {tokens.TEXT_PRIMARY};
                font-size: {tokens.TYPE_BODY}px;
                font-weight: {tokens.WEIGHT_SEMIBOLD};
            }}
        """)
        layout.addWidget(title_label)

        subtitle_label = QLabel(subtitle, frame)
        subtitle_label.setObjectName(_OPTION_HINT_NAME)
        subtitle_label.setStyleSheet(f"""
            QLabel#{_OPTION_HINT_NAME} {{
                background: transparent;
                border: none;
                color: {tokens.TEXT_MUTED};
                font-size: {tokens.TYPE_CAPTION}px;
                font-weight: {tokens.WEIGHT_REGULAR};
            }}
        """)
        layout.addWidget(subtitle_label)

        if on_click:
            def _mousePressEvent(event):
                if event.button() == Qt.MouseButton.LeftButton:
                    on_click()
            frame.mousePressEvent = _mousePressEvent

        return frame

    def _on_visit_web(self):
        webbrowser.open(_DOWNLOAD_URL)
        self.accept()

    def _on_import_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Select Bible Source File",
            os.path.expanduser("~/Downloads"),
            _FILE_FILTER,
        )
        if not filepath:
            return  # user cancelled file picker, stay in dialog

        ext = os.path.splitext(filepath)[1].lower()
        if ext not in (".xml", ".xmm", ".csv", ".json"):
            dialogs.warning(
                self,
                "Unsupported File",
                f"Expected .xml, .xmm, .csv, or .json file.\n\nGot: {ext}",
            )
            return

        self._selected_path = filepath
        self.accept()

    def selected_path(self) -> str | None:
        """Return the selected file path, or None if cancelled / visit-web."""
        return self._selected_path

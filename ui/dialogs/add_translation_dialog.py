"""
ui/dialogs/add_translation_dialog.py

Dialog for adding Bible translations. Offers two options:
  1. Visit the download page (biblelist.netlify.app)
  2. Import a local file (XML, XMM, CSV, JSON)
"""

import os
import webbrowser
import logging

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QWidget
)
from PyQt6.QtCore import Qt

from ui.styles import SLATE_950, SLATE_800, SLATE_500, SLATE_300, BLUE_500, WHITE

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


class AddTranslationDialog(QDialog):
    """Modal dialog offering download-page or local-file import."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Translation")
        self.setFixedSize(380, 220)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {SLATE_950};
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }}
        """)
        self._selected_path: str | None = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # Title
        title = QLabel("Add Translation")
        title.setStyleSheet(f"color: {WHITE}; font-size: 14px; font-weight: 700;")
        layout.addWidget(title)

        subtitle = QLabel("Download from the web, or import a file you already have.")
        subtitle.setStyleSheet(f"color: {SLATE_500}; font-size: 11px;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addSpacing(6)

        # Option 1: Visit download page
        web_btn = self._make_option_button(
            "Visit Download Page",
            "Open biblelist.netlify.app in your browser",
        )
        web_btn.clicked.connect(self._on_visit_web)
        layout.addWidget(web_btn)

        # Option 2: Import file
        file_btn = self._make_option_button(
            "Import File...",
            "Pick XML, XMM, CSV, or JSON from your file manager",
        )
        file_btn.clicked.connect(self._on_import_file)
        layout.addWidget(file_btn)

        layout.addStretch()

        # Cancel
        cancel_row = QHBoxLayout()
        cancel_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(80)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {SLATE_500};
                font-size: 11px;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 4px;
                padding: 5px 12px;
            }}
            QPushButton:hover {{
                color: {WHITE};
                border-color: {SLATE_500};
            }}
        """)
        cancel_btn.clicked.connect(self.reject)
        cancel_row.addWidget(cancel_btn)
        layout.addLayout(cancel_row)

    def _make_option_button(self, title: str, subtitle: str) -> QPushButton:
        """Create a styled two-line option button."""
        btn = QPushButton()
        btn.setFixedHeight(52)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {SLATE_800};
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 6px;
                text-align: left;
                padding: 8px 14px;
            }}
            QPushButton:hover {{
                border-color: {BLUE_500};
                background: rgba(59, 130, 246, 0.08);
            }}
        """)
        btn.setText(f"<b style='color:{WHITE}; font-size:12px;'>{title}</b><br>"
                    f"<span style='color:{SLATE_500}; font-size:10px;'>{subtitle}</span>")
        return btn

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
            QMessageBox.warning(
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

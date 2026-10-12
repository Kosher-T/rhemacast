"""
tests/test_scrollbar.py

Shared minimal scrollbar (lite-designer spec): permanently reserved
lane, flat thumb, no arrows — identical behavior on every scroll area.
"""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication, QScrollArea, QListWidget
from PyQt6.QtCore import Qt
import pytest

from ui.styles import apply_minimal_scrollbar, MINIMAL_SCROLLBAR_CSS


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test"])
    return app


def test_policies_and_rules(qapp):
    area = QScrollArea()
    area.setStyleSheet("QScrollArea { background: transparent; }")
    apply_minimal_scrollbar(area)
    assert area.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOn
    assert area.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    sheet = area.styleSheet()
    assert "QScrollArea { background: transparent; }" in sheet
    assert "QScrollBar:vertical" in sheet
    assert "width: 6px" in sheet


def test_idempotent_and_widget_generic(qapp):
    lst = QListWidget()
    apply_minimal_scrollbar(lst)
    apply_minimal_scrollbar(lst)
    assert lst.styleSheet().count("QScrollBar:vertical {") == 1
    lst.show()
    qapp.processEvents()
    assert lst.verticalScrollBar().isVisibleTo(lst)

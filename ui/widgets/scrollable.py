"""
ui/widgets/scrollable.py

Minimal scroll-area wrapper for panels that can outgrow their slot.
Transparent chrome so the scrollbar sits on the app's own background.
"""

from PyQt6.QtWidgets import QScrollArea, QWidget
from PyQt6.QtCore import Qt


def scrollable(widget: QWidget, *, horizontal: bool = False) -> QScrollArea:
    """Wrap a widget in a borderless, transparent vertical scroll area."""
    area = QScrollArea()
    area.setWidget(widget)
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAsNeeded if horizontal
        else Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    area.viewport().setStyleSheet("background: transparent;")
    area.setStyleSheet("background: transparent; border: none;")
    area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return area

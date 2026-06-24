"""
ui/widgets/aspect_ratio.py

A custom wrapper widget that enforces a 16:9 aspect ratio for its child.
Used for the Live Output and Operator Preview viewports to prevent ugly stretching.
"""

from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import Qt, QSize, QRect

class AspectRatioWidget(QWidget):
    """
    A widget that maintains a strict aspect ratio (default 16:9) for its child.
    The child widget is centered within the available space.
    """
    def __init__(self, widget: QWidget, aspect_ratio: float = 16.0 / 9.0, 
                 min_width: int = 160, max_width: int = 1920, parent=None):
        super().__init__(parent)
        self.aspect_ratio = aspect_ratio
        self.min_width = min_width
        self.max_width = max_width
        
        self.child_widget = widget
        self.child_widget.setParent(self)
        
        # Ensure the wrapper widget expands to take available space
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Remove any minimum size restrictions on the child so it can be shrunk
        self.child_widget.setMinimumSize(1, 1)
        self.child_widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

    def minimumSizeHint(self) -> QSize:
        """Allow the widget to be shrunk down almost completely by the parent layout."""
        return QSize(self.min_width, max(1, int(self.min_width / self.aspect_ratio)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        
        size = event.size()
        w = size.width()
        h = size.height()
        
        # Calculate the largest 16:9 box that fits inside the current size
        target_w = w
        target_h = int(w / self.aspect_ratio)
        
        if target_h > h:
            target_h = h
            target_w = int(h * self.aspect_ratio)
            
        # Enforce min/max width on target size
        if target_w < self.min_width:
            target_w = self.min_width
            target_h = int(target_w / self.aspect_ratio)
        elif target_w > self.max_width:
            target_w = self.max_width
            target_h = int(target_w / self.aspect_ratio)
            
        x = (w - target_w) // 2
        y = (h - target_h) // 2
        
        # Manually set geometry without layouts so it doesn't inflate minimum size
        self.child_widget.setGeometry(QRect(x, y, target_w, target_h))

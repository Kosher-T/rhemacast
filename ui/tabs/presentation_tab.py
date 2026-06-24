"""
ui/tabs/presentation_tab.py

The main workspace: nested QSplitter layout matching the HTML draft.
  Top: Schedule (L) | Live Output + Controls (C) | STT + Preview (R)
  Bottom: Manual Browser (L) | Queue (R)
"""

import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel, QPushButton, QFrame
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, pyqtSignal, QSize

from ui.panels.schedule_panel import SchedulePanel
from ui.panels.queue_panel import QueuePanel
from ui.panels.browser_panel import BrowserPanel
from ui.panels.stt_panel import STTPanel
from ui.widgets.aspect_ratio import AspectRatioWidget
from ui.styles import (
    MACRO_BTN_AMBER, MACRO_BTN_CLEAR,
    RED_500, WHITE, SLATE_950, BORDER_SUBTLE
)


class LiveOutputFrame(QWidget):
    """Center panel: Live output viewport + macro controls."""

    clear_recall = pyqtSignal()
    prev_verse = pyqtSignal()
    next_verse = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Live indicator (outside the viewport)
        live_row = QHBoxLayout()
        live_row.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        live_row.setContentsMargins(0, 0, 0, 4)
        live_dot = QLabel("●")
        live_dot.setStyleSheet(f"color: {RED_500}; font-size: 10px;")
        live_label = QLabel("LIVE")
        live_label.setStyleSheet(f"""
            color: {RED_500}; font-size: 12px; font-weight: 900;
            letter-spacing: 3px;
        """)
        live_row.addWidget(live_dot)
        live_row.addWidget(live_label)
        layout.addLayout(live_row)
        
        # ── Live Output Viewport ──
        self.viewport = QFrame()
        self.viewport.setObjectName("LiveOutputViewport")
        self.viewport.setStyleSheet(f"""
            QFrame#LiveOutputViewport {{
                background: black;
                border: 1px solid rgba(239, 68, 68, 0.4);
                border-radius: 8px;
            }}
        """)
        
        self.ar_widget = AspectRatioWidget(self.viewport, aspect_ratio=16.0/9.0, min_width=320, max_width=840)

        vp_layout = QVBoxLayout(self.viewport)
        vp_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.output_label = QLabel("LIVE OUTPUT")
        self.output_label.setStyleSheet(f"""
            color: rgba(255, 255, 255, 12);
            font-size: 28px; font-weight: 900;
            font-style: italic;
        """)
        self.output_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vp_layout.addWidget(self.output_label)

        layout.addWidget(self.ar_widget, 1)

        # ── Macro Controls ──
        controls_container = QWidget()
        controls = QHBoxLayout(controls_container)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(12)

        btn_prev = QPushButton("<")
        btn_prev.setStyleSheet(MACRO_BTN_AMBER)
        btn_prev.setFixedSize(80, 40)
        btn_prev.setToolTip("Previous Verse")
        btn_prev.clicked.connect(self.prev_verse.emit)
        controls.addWidget(btn_prev)

        _icon_path = os.path.join(os.path.dirname(__file__), "..", "assets", "eye-off.svg")
        self.btn_clear = QPushButton()
        self.btn_clear.setIcon(QIcon(_icon_path))
        self.btn_clear.setIconSize(QSize(18, 18))
        self.btn_clear.setStyleSheet(MACRO_BTN_CLEAR)
        self.btn_clear.setFixedSize(90, 40)
        self.btn_clear.setToolTip("Clear screen / Recall last cleared verse")
        self.btn_clear.clicked.connect(self.clear_recall.emit)
        controls.addWidget(self.btn_clear)

        btn_next = QPushButton(">")
        btn_next.setStyleSheet(MACRO_BTN_AMBER)
        btn_next.setFixedSize(80, 40)
        btn_next.setToolTip("Next Verse")
        btn_next.clicked.connect(self.next_verse.emit)
        controls.addWidget(btn_next)

        macro_wrapper = QHBoxLayout()
        macro_wrapper.addStretch()
        macro_wrapper.addWidget(controls_container)
        macro_wrapper.addStretch()
        layout.addLayout(macro_wrapper)


class PresentationTab(QWidget):
    """The main Presentation workspace tab."""

    def __init__(self, parent=None):
        super().__init__(parent)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(0)
        
        def wrap_panel(panel: QWidget) -> QWidget:
            """Wraps a panel in a container with a 4px margin (m-1 in Tailwind)"""
            wrapper = QWidget()
            l = QVBoxLayout(wrapper)
            l.setContentsMargins(4, 4, 4, 4)
            l.setSpacing(0)
            panel.setProperty("class", "MainPanel")
            l.addWidget(panel)
            return wrapper

        # ── Main Vertical Splitter: Top / Bottom ──
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.setChildrenCollapsible(False)

        # ──── Top Section (Horizontal Splitter) ────
        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        top_splitter.setChildrenCollapsible(False)

        self.schedule_panel = SchedulePanel()
        self.live_output = LiveOutputFrame()
        self.stt_panel = STTPanel()

        top_splitter.addWidget(wrap_panel(self.schedule_panel))
        top_splitter.addWidget(self.live_output) # Center panel has its own padding/wrapper logic
        top_splitter.addWidget(wrap_panel(self.stt_panel))

        # Center panel gets the most space and cannot be collapsed completely
        top_splitter.setStretchFactor(0, 0)
        top_splitter.setStretchFactor(1, 1)
        top_splitter.setStretchFactor(2, 0)
        top_splitter.setCollapsible(1, False)
        
        # Default widths: 25% | 50% | 25%
        top_splitter.setSizes([300, 600, 300])

        main_splitter.addWidget(top_splitter)

        # ──── Bottom Section (Horizontal Splitter) ────
        bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        bottom_splitter.setChildrenCollapsible(False)

        self.browser_panel = BrowserPanel()
        self.queue_panel = QueuePanel()

        bottom_splitter.addWidget(wrap_panel(self.browser_panel))
        bottom_splitter.addWidget(wrap_panel(self.queue_panel))

        # Default widths: 60% | 40%
        bottom_splitter.setSizes([600, 400])

        main_splitter.addWidget(bottom_splitter)

        # Default heights: 65% top | 35% bottom
        main_splitter.setSizes([650, 350])

        root_layout.addWidget(main_splitter)

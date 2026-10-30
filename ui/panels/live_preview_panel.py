"""
ui/panels/live_preview_panel.py

Center panel: Preview (left) + Live (right) + macro controls under Live.
Each viewport is a QWebEngineView rendering the same HTML/CSS/JS as OBS.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSplitter
)
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtCore import Qt, pyqtSignal, QEvent

from ui.widgets.display_view import DisplayView
from ui.widgets.aspect_ratio import AspectRatioWidget
from ui.styles import (
    PANEL_HEADER_STYLE, PANEL_BODY_STYLE,
    ACCENT_BORDER, RED_500,
)
from ui.tokens import (
    BUTTON_HEIGHT, WARNING, icon_button_qss,
)
from ui.connection_status import connection_monitor, live_viewport_qss


class PreviewOverlay(QWidget):
    """Transparent overlay that captures clicks and double-clicks on the preview viewport."""
    clicked = pyqtSignal()
    double_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        self.double_clicked.emit()

    def mouseReleaseEvent(self, event: QMouseEvent):
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        event.accept()

    def wheelEvent(self, event):
        event.accept()


class LiveOverlay(QWidget):
    """Transparent overlay that captures single-clicks on the live viewport."""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        event.accept()

    def wheelEvent(self, event):
        event.accept()


class LivePreviewPanel(QWidget):
    """Center panel: Preview (left) + Live (right) + macro controls."""

    clear_recall = pyqtSignal()
    prev_verse = pyqtSignal()
    next_verse = pyqtSignal()
    preview_double_clicked = pyqtSignal()
    preview_clicked = pyqtSignal()
    live_clicked = pyqtSignal()

    def __init__(self, parent=None, *, monitor=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── Splitter: Preview (left) | Live (right) ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ── Preview Panel (left) ──
        preview_panel = QWidget()
        preview_panel.setStyleSheet(PANEL_BODY_STYLE)
        preview_panel_layout = QVBoxLayout(preview_panel)
        preview_panel_layout.setContentsMargins(8, 8, 8, 8)
        preview_panel_layout.setSpacing(0)

        preview_header = QWidget()
        preview_header.setStyleSheet(PANEL_HEADER_STYLE)
        preview_header_layout = QHBoxLayout(preview_header)
        preview_header_layout.setContentsMargins(12, 6, 12, 6)
        preview_title = QLabel("OPERATOR PREVIEW")
        self._preview_title = preview_title
        preview_header_layout.addWidget(preview_title)
        preview_header_layout.addStretch()
        preview_panel_layout.addWidget(preview_header)

        # Spacer between header and viewport (matches live panel)
        _prev_header_spacer = QWidget()
        _prev_header_spacer.setFixedHeight(8)
        _prev_header_spacer.setStyleSheet("background: transparent;")
        preview_panel_layout.addWidget(_prev_header_spacer)

        self.preview_frame = QFrame()
        self.preview_frame.setObjectName("OperatorPreviewViewport")
        self.preview_frame.setStyleSheet(f"""
            QFrame#OperatorPreviewViewport {{
                background: black;
                border: 1px solid {ACCENT_BORDER};
                border-radius: 6px;
            }}
        """)

        self.preview_view = DisplayView(live_mode=False)
        self.preview_view.setMinimumHeight(1)

        preview_inner = QVBoxLayout(self.preview_frame)
        preview_inner.setContentsMargins(0, 0, 0, 0)
        preview_inner.addWidget(self.preview_view)

        self._preview_overlay = PreviewOverlay(self.preview_frame)
        self._preview_overlay.clicked.connect(self.preview_clicked.emit)
        self._preview_overlay.double_clicked.connect(self.preview_double_clicked.emit)
        self._preview_overlay.raise_()
        # Switch cover: opaque black, above the view, below the click
        # overlay. Shown on tab arrival until the silent refresh acks
        # presented frames — a hidden view's last committed (stale)
        # frame must never surface, not even for a frame.
        self._preview_cover = QWidget(self.preview_frame)
        self._preview_cover.setStyleSheet("background: black;")
        self._preview_cover.stackUnder(self._preview_overlay)
        self._preview_cover.hide()
        self.preview_frame.installEventFilter(self)

        self.preview_ar_widget = AspectRatioWidget(
            self.preview_frame, aspect_ratio=16.0 / 9.0,
            min_width=320, max_width=840
        )
        preview_panel_layout.addWidget(self.preview_ar_widget, 1)

        # Spacer matching nav bar height so preview viewport equals live viewport
        _nav_spacer = QWidget()
        _nav_spacer.setFixedHeight(24)
        _nav_spacer.setStyleSheet("background: transparent;")
        preview_panel_layout.addWidget(_nav_spacer)

        # Bottom spacer (matches live panel)
        _prev_bottom_spacer = QWidget()
        _prev_bottom_spacer.setFixedHeight(4)
        _prev_bottom_spacer.setStyleSheet("background: transparent;")
        preview_panel_layout.addWidget(_prev_bottom_spacer)

        splitter.addWidget(preview_panel)

        # ── Live Panel (right) ──
        live_panel = QWidget()
        live_panel.setStyleSheet(PANEL_BODY_STYLE)
        live_panel_layout = QVBoxLayout(live_panel)
        live_panel_layout.setContentsMargins(8, 8, 8, 8)
        live_panel_layout.setSpacing(0)

        live_header = QWidget()
        live_header.setStyleSheet(PANEL_HEADER_STYLE)
        live_header_layout = QHBoxLayout(live_header)
        live_header_layout.setContentsMargins(12, 6, 12, 6)

        live_row = QHBoxLayout()
        live_row.setSpacing(4)
        live_dot = QLabel("●")
        live_dot.setStyleSheet(f"color: {RED_500}; font-size: 12px;")
        live_label = QLabel("LIVE")
        self._live_label = live_label
        live_row.addWidget(live_dot)
        live_row.addWidget(live_label)
        live_header_layout.addLayout(live_row)
        live_header_layout.addStretch()
        live_panel_layout.addWidget(live_header)

        # Spacer between header and viewport
        _header_spacer = QWidget()
        _header_spacer.setFixedHeight(8)
        _header_spacer.setStyleSheet("background: transparent;")
        live_panel_layout.addWidget(_header_spacer)

        self.viewport = QFrame()
        self.viewport.setObjectName("LiveOutputViewport")
        self._connection_monitor = (
            monitor if monitor is not None else connection_monitor())
        self.viewport.setStyleSheet(
            live_viewport_qss(self._connection_monitor.snapshot.state))
        self._connection_monitor.changed.connect(self._apply_connection_state)

        vp_layout = QVBoxLayout(self.viewport)
        vp_layout.setContentsMargins(0, 0, 0, 0)

        self.live_view = DisplayView(live_mode=False)
        self.live_view.setMinimumHeight(1)
        vp_layout.addWidget(self.live_view)

        self._live_overlay = LiveOverlay(self.viewport)
        self._live_overlay.clicked.connect(self.live_clicked.emit)
        self._live_overlay.raise_()
        self._live_cover = QWidget(self.viewport)
        self._live_cover.setStyleSheet("background: black;")
        self._live_cover.stackUnder(self._live_overlay)
        self._live_cover.hide()
        self.viewport.installEventFilter(self)

        self.ar_widget = AspectRatioWidget(
            self.viewport, aspect_ratio=16.0 / 9.0,
            min_width=320, max_width=840
        )
        live_panel_layout.addWidget(self.ar_widget, 1)

        # ── Nav buttons (centered below live viewport) ──
        nav_bar = QHBoxLayout()
        nav_bar.setContentsMargins(0, 0, 0, 0)
        nav_bar.setSpacing(6)
        nav_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_prev = QPushButton()
        btn_prev.setStyleSheet(icon_button_qss())
        btn_prev.setFixedSize(36, BUTTON_HEIGHT)
        btn_prev.setToolTip("Previous Verse")
        from ui.icons import apply_button
        apply_button(btn_prev, "chevron-left")
        btn_prev.clicked.connect(self.prev_verse.emit)
        nav_bar.addWidget(btn_prev)

        btn_clear = QPushButton()
        apply_button(btn_clear, "eye-off")
        btn_clear.setStyleSheet(icon_button_qss())
        btn_clear.setFixedSize(36, BUTTON_HEIGHT)
        btn_clear.setToolTip("Cloak / Uncloak")
        btn_clear.clicked.connect(self.clear_recall.emit)
        nav_bar.addWidget(btn_clear)
        self.btn_clear = btn_clear

        btn_next = QPushButton()
        btn_next.setStyleSheet(icon_button_qss())
        btn_next.setFixedSize(36, BUTTON_HEIGHT)
        btn_next.setToolTip("Next Verse")
        apply_button(btn_next, "chevron-right")
        btn_next.clicked.connect(self.next_verse.emit)
        nav_bar.addWidget(btn_next)

        live_panel_layout.addLayout(nav_bar)

        # Bottom spacer
        _bottom_spacer = QWidget()
        _bottom_spacer.setFixedHeight(4)
        _bottom_spacer.setStyleSheet("background: transparent;")
        live_panel_layout.addWidget(_bottom_spacer)

        splitter.addWidget(live_panel)

        # Default splitter ratio: 50% | 50%
        splitter.setSizes([500, 500])
        layout.addWidget(splitter, 1)

        # Settings → Interface: panel headers share one font group.
        from ui.app_theme import subscribe_interface_font_changed
        subscribe_interface_font_changed(self._on_interface_font_changed)
        self.apply_panel_label_fonts()

    def _apply_connection_state(self, snapshot):
        """One source of truth with the status-bar badge (ui.connection_status)."""
        self.viewport.setStyleSheet(live_viewport_qss(snapshot.state))

    def _on_interface_font_changed(self, prefix: str):
        if prefix == "panel.labels":
            self.apply_panel_label_fonts()

    def apply_panel_label_fonts(self):
        """Re-read the "panel.labels" group for both header labels."""
        from ui.app_theme import area_font, font_qss
        from ui.styles import panel_header_label_style

        self._preview_title.setStyleSheet(panel_header_label_style())
        live = area_font("panel.labels", 13, 700, size_min=8, size_max=28)
        self._live_label.setStyleSheet(
            f"color: {RED_500};{font_qss(live)} letter-spacing: 3px;")

    def eventFilter(self, obj, event):
        """Resize overlays to match their parent frames."""
        if obj is self.preview_frame and event.type() == QEvent.Type.Resize:
            r = self.preview_frame.contentsRect()
            self._preview_overlay.setGeometry(r)
            self._preview_cover.setGeometry(r)
        if hasattr(self, 'viewport') and obj is self.viewport and event.type() == QEvent.Type.Resize:
            r = self.viewport.contentsRect()
            self._live_overlay.setGeometry(r)
            self._live_cover.setGeometry(r)
        return super().eventFilter(obj, event)

    def set_live_payload(self, payload: dict):
        """Send a verse payload to the live viewport."""
        self.live_view.display_verse(payload)

    def cover_screens(self):
        """Black covers over both viewports (tab-switch resync)."""
        self._preview_cover.setGeometry(self.preview_frame.contentsRect())
        self._live_cover.setGeometry(self.viewport.contentsRect())
        self._preview_cover.show()
        self._live_cover.show()

    def reveal_screens(self):
        """Hide the switch covers. Idempotent — safe as multi-ack
        target and timer fallback."""
        self._preview_cover.hide()
        self._live_cover.hide()

    def refresh_views(self, live=None, preview=None, done=None):
        """Cover + silent frame-acked refresh of both views.

        live/preview: payload dict → silent refresh; "clear" → silent
        blank; None → leave untouched. done() fires after every
        requested view acks (2 presented frames); skipped views count
        immediately. Tabs pair this with a reveal fallback timer.
        """
        self.cover_screens()
        pending = []
        if isinstance(live, dict):
            pending.append(("live", live))
        elif live == "clear":
            pending.append(("clear-live", None))
        if isinstance(preview, dict):
            pending.append(("preview", preview))
        if not pending:
            self.reveal_screens()
            if done is not None:
                done()
            return
        remaining = [len(pending)]

        def _ack(_result=None):
            remaining[0] -= 1
            if remaining[0] <= 0:
                self.reveal_screens()
                if done is not None:
                    done()

        for kind, payload in pending:
            if kind == "live":
                self.live_view.refresh(payload, _ack)
            elif kind == "clear-live":
                self.live_view.refresh_clear(_ack)
            else:
                self.preview_view.refresh(payload, _ack)

    def clear_live(self):
        """Clear the live viewport."""
        self.live_view.clear()

    def set_clear_active(self, active: bool):
        """Cloak indicator on the cloak button (amber when output is
        blanked). Mirrors the SHARED cloak state — both tabs subscribe,
        so both buttons follow whichever tab toggles."""
        self.btn_clear.setProperty("cloaked", active)
        self.btn_clear.setStyleSheet(
            icon_button_qss(WARNING if active else None))
        self.btn_clear.setToolTip(
            "Output cloaked — showing blank (click to uncloak)"
            if active else "Cloak / Uncloak")

    def set_preview_payload(self, payload: dict):
        """Send a verse payload to the preview viewport."""
        self.preview_view.display_verse(payload)

    def clear_preview(self):
        """Clear the preview viewport."""
        self.preview_view.clear()

    def apply_theme(self, theme_data: dict):
        """Apply a theme to both viewports."""
        self.live_view.apply_theme(theme_data)
        self.preview_view.apply_theme(theme_data)

    def apply_theme_to_preview(self, theme_data: dict):
        """Apply a theme to the preview viewport only."""
        self.preview_view.apply_theme(theme_data)

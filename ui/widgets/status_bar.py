"""
ui/widgets/status_bar.py

Status bar: browser-display connection indicator, GPU telemetry strip, RAM
warning. The connection badge and the Live border share one monitor
(ui/connection_status.py), so they can never disagree.
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel

from ui.styles import (
    RED_500, SLATE_400, SLATE_500, SLATE_900, BORDER_SUBTLE
)
from ui.connection_status import connection_monitor


_PILL_STYLE = """
    background: rgba(255, 255, 255, 5);
    border: 1px solid rgba(255, 255, 255, 8);
    border-radius: 4px;
    padding: 2px 8px;
"""


class StatusBar(QWidget):
    """Bottom status bar with browser-display status, GPU telemetry, and RAM."""

    def __init__(self, parent=None, *, monitor=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {SLATE_900};
                border-top: 1px solid {BORDER_SUBTLE};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(12)

        # ── Left: browser-display connection ──
        self._monitor = monitor if monitor is not None else connection_monitor()
        snapshot = self._monitor.snapshot
        self.browser_label = self._make_browser_pill(
            snapshot.color, f"Browser: {snapshot.label}")
        self.browser_label.setToolTip(
            "Browser display clients connected to the overlay server "
            "(OBS Browser Source or another display)")

        layout.addWidget(self.browser_label)
        layout.addStretch()

        # ── Right: Hardware Metrics ──
        self.gpu_label = self._make_pill("GPU", "--°C")
        self.gpu_label.setToolTip("GPU temperature from NVML hardware monitor")

        self.vram_label = self._make_pill("VRAM", "-- MB")
        self.vram_label.setToolTip("GPU video memory usage")

        self.ram_label = self._make_pill("RAM", "--%")
        self.ram_label.setToolTip("System RAM usage")

        layout.addWidget(self.gpu_label)
        layout.addWidget(self.vram_label)
        layout.addWidget(self.ram_label)

        # Throttle indicator
        self.throttle_label = QLabel("")
        self.throttle_label.setStyleSheet(
            f"color: {RED_500}; font-size: 12px; font-weight: 700; background: transparent;"
        )
        layout.addWidget(self.throttle_label)

        # One monitor drives both the badge and the Live border; no local
        # timer here, so the two always read the same snapshot.
        self._monitor.changed.connect(self._apply_connection_state)

    def _make_pill(self, label: str, value: str) -> QLabel:
        lbl = QLabel(f'<span style="color: {SLATE_500};">{label}</span> '
                      f'<span style="color: {SLATE_400}; font-weight: 600;">{value}</span>')
        lbl.setStyleSheet(_PILL_STYLE)
        return lbl

    def _set_pill_value(self, label: QLabel, name: str, value: str, color: str = None):
        if color is None:
            color = SLATE_400
        label.setText(f'<span style="color: {SLATE_500};">{name}</span> '
                      f'<span style="color: {color}; font-weight: 600;">{value}</span>')

    def _make_browser_pill(self, dot_color: str, text: str) -> QLabel:
        lbl = QLabel(f'<span style="color: {dot_color};">●</span> '
                      f'<span style="color: {SLATE_400}; font-weight: 600;">{text}</span>')
        lbl.setStyleSheet(_PILL_STYLE)
        return lbl

    def _apply_connection_state(self, snapshot):
        """Follow the shared monitor (the Live border follows the same one)."""
        self._set_browser_pill(snapshot.color, f"Browser: {snapshot.label}")

    def _set_browser_pill(self, dot_color: str, text: str):
        self.browser_label.setText(
            f'<span style="color: {dot_color};">●</span> '
            f'<span style="color: {SLATE_400}; font-weight: 600;">{text}</span>')

    def update_hardware(self, telemetry: dict):
        """Called by HardwareTelemetryWorker signal. Already debounced."""
        temp = telemetry.get("gpu_temp_c")
        if temp is not None:
            color = RED_500 if temp >= 82 else None
            self._set_pill_value(self.gpu_label, "GPU", f"{temp}°C", color)

        vram = telemetry.get("gpu_vram_used_mb")
        if vram is not None:
            self._set_pill_value(self.vram_label, "VRAM", f"{vram:.0f} MB")

        ram_pct = telemetry.get("ram_percent")
        if ram_pct is not None:
            color = RED_500 if ram_pct >= 90 else None
            self._set_pill_value(self.ram_label, "RAM", f"{ram_pct:.0f}%", color)

        throttled = telemetry.get("is_throttled", False)
        self.throttle_label.setText("⚠ THROTTLED" if throttled else "")

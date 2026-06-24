"""
ui/widgets/status_bar.py

Status bar: OBS connection indicator (green/red), GPU telemetry strip, RAM warning.
Debounced to max 30 FPS updates.
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt6.QtCore import QTimer

from ui.styles import (
    EMERALD_500, RED_500, SLATE_400, SLATE_500, SLATE_900,
    WHITE, BORDER_SUBTLE
)
from core.websocket_server import get_connected_client_count


_PILL_STYLE = """
    background: rgba(255, 255, 255, 5);
    border: 1px solid rgba(255, 255, 255, 8);
    border-radius: 4px;
    padding: 2px 8px;
"""


class StatusBar(QWidget):
    """Bottom status bar with OBS indicator, GPU telemetry, and RAM info."""

    def __init__(self, parent=None):
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

        # ── Left: OBS Connection ──
        self.obs_label = self._make_obs_pill(RED_500, "OBS: Disconnected")
        self.obs_label.setToolTip("WebSocket connection status to OBS Browser Source")

        layout.addWidget(self.obs_label)
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
            f"color: {RED_500}; font-size: 10px; font-weight: 700; background: transparent;"
        )
        layout.addWidget(self.throttle_label)

        # Refresh timer
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._poll_obs_status)
        self._refresh_timer.start(1000)

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

    def _make_obs_pill(self, dot_color: str, text: str) -> QLabel:
        lbl = QLabel(f'<span style="color: {dot_color};">●</span> '
                      f'<span style="color: {SLATE_400}; font-weight: 600;">{text}</span>')
        lbl.setStyleSheet(_PILL_STYLE)
        return lbl

    def _poll_obs_status(self):
        """Poll WebSocket client count for OBS status indicator."""
        count = get_connected_client_count()
        if count > 0:
            self._set_obs_pill(EMERALD_500, f"OBS: Connected ({count})")
        else:
            self._set_obs_pill(RED_500, "OBS: Disconnected")

    def _set_obs_pill(self, dot_color: str, text: str):
        self.obs_label.setText(f'<span style="color: {dot_color};">●</span> '
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

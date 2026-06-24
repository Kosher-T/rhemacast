"""
ui/widgets/status_bar.py

Status bar: OBS connection indicator (green/red), GPU telemetry strip, RAM warning.
Debounced to max 30 FPS updates.
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt6.QtCore import QTimer

from ui.styles import (
    EMERALD_500, RED_500, SLATE_400, SLATE_500, SLATE_800,
    WHITE, BORDER_SUBTLE
)
from core.websocket_server import get_connected_client_count


class StatusBar(QWidget):
    """Bottom status bar with OBS indicator, GPU telemetry, and RAM info."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {SLATE_800};
                border-top: 1px solid {BORDER_SUBTLE};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(16)

        # OBS Connection
        self.obs_dot = QLabel("●")
        self.obs_dot.setStyleSheet(f"color: {RED_500}; font-size: 8px;")
        layout.addWidget(self.obs_dot)

        self.obs_label = QLabel("OBS: Disconnected")
        self.obs_label.setStyleSheet(f"color: {SLATE_400}; font-size: 10px; font-weight: 600;")
        self.obs_label.setToolTip("WebSocket connection status to OBS Browser Source")
        layout.addWidget(self.obs_label)

        layout.addStretch()

        # GPU Temp
        self.gpu_label = QLabel("GPU: --°C")
        self.gpu_label.setStyleSheet(f"color: {SLATE_500}; font-size: 10px;")
        self.gpu_label.setToolTip("GPU temperature from NVML hardware monitor")
        layout.addWidget(self.gpu_label)

        # VRAM
        self.vram_label = QLabel("VRAM: -- MB")
        self.vram_label.setStyleSheet(f"color: {SLATE_500}; font-size: 10px;")
        self.vram_label.setToolTip("GPU video memory usage")
        layout.addWidget(self.vram_label)

        # RAM
        self.ram_label = QLabel("RAM: --%")
        self.ram_label.setStyleSheet(f"color: {SLATE_500}; font-size: 10px;")
        self.ram_label.setToolTip("System RAM usage")
        layout.addWidget(self.ram_label)

        # Throttle indicator
        self.throttle_label = QLabel("")
        self.throttle_label.setStyleSheet(f"color: {RED_500}; font-size: 10px; font-weight: 700;")
        layout.addWidget(self.throttle_label)

        # Refresh timer: ~30 FPS (33 ms)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._poll_obs_status)
        self._refresh_timer.start(1000)  # OBS status once per second is sufficient

    def _poll_obs_status(self):
        """Poll WebSocket client count for OBS status indicator."""
        count = get_connected_client_count()
        if count > 0:
            self.obs_dot.setStyleSheet(f"color: {EMERALD_500}; font-size: 8px;")
            self.obs_label.setText(f"OBS: Connected ({count})")
        else:
            self.obs_dot.setStyleSheet(f"color: {RED_500}; font-size: 8px;")
            self.obs_label.setText("OBS: Disconnected")

    def update_hardware(self, telemetry: dict):
        """Called by HardwareTelemetryWorker signal. Already debounced."""
        temp = telemetry.get("gpu_temp_c")
        if temp is not None:
            color = RED_500 if temp >= 82 else SLATE_500
            self.gpu_label.setStyleSheet(f"color: {color}; font-size: 10px;")
            self.gpu_label.setText(f"GPU: {temp}°C")

        vram = telemetry.get("gpu_vram_used_mb")
        if vram is not None:
            self.vram_label.setText(f"VRAM: {vram:.0f} MB")

        ram_pct = telemetry.get("ram_percent")
        if ram_pct is not None:
            color = RED_500 if ram_pct >= 90 else SLATE_500
            self.ram_label.setStyleSheet(f"color: {color}; font-size: 10px;")
            self.ram_label.setText(f"RAM: {ram_pct:.0f}%")

        throttled = telemetry.get("is_throttled", False)
        self.throttle_label.setText("⚠ THROTTLED" if throttled else "")

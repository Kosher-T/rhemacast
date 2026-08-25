"""
core/ui.py

Entry point for the RhemaCast PyQt6 UI.
Initializes the QApplication, workers, and main window.
Boots background services: DB Writer (T4), Hardware Monitor (T5), WebSocket server.
"""

import sys
import os
import logging
import threading

# Ensure the parent directory (project root) is in the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QGuiApplication

from ui.main_window import MainWindow
from ui.workers import OperatorQueueWorker, HardwareTelemetryWorker, TranscriptStreamWorker
from ui.theme import apply_theme

logger = logging.getLogger(__name__)


def _configure_high_dpi():
    """Configure high-DPI scaling before QApplication creation."""
    # Qt 6: High DPI scaling is enabled by default
    # PassThrough policy respects the OS scaling factor
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )


def _boot_background_services():
    """
    Boot persistent background services that run for the lifetime of the app:
    - Database initialization
    - WebSocket server (in a daemon thread)
    
    Note: T4 (DB Writer) and T5 (Hardware Monitor) are registered but only
    started when the operator clicks "Start Service". The HardwareTelemetryWorker
    QThread polls independently for UI status bar updates.
    """
    # Initialize database schema
    try:
        from core.database import init_db
        init_db()
        logger.info("Database initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

    # Start WebSocket server in a daemon thread
    try:
        from core.websocket_server import run_server_thread
        ws_thread = threading.Thread(target=run_server_thread, name="WebSocket-Server", daemon=True)
        ws_thread.start()
        logger.info("WebSocket server started on ws://0.0.0.0:8765")
    except Exception as e:
        logger.error(f"Failed to start WebSocket server: {e}")

    # Preload search indexes + embedding model in background
    try:
        from core.model_manager import model_manager
        model_manager.preload_search()
        # Load STT models in parallel background threads (non-blocking)
        model_manager.preload_stt()
    except Exception as e:
        logger.error(f"Failed to load models: {e}")


class RhemaCastApp(QApplication):
    def __init__(self, argv):
        _configure_high_dpi()
        super().__init__(argv)
        
        # Apply theme palette for native look + accessibility
        apply_theme(self, "dark")
        
        # Show loading screen immediately
        from ui.widgets.loading_screen import LoadingScreen
        self.loading_screen = LoadingScreen()
        self.loading_screen.show()
        self.processEvents()
        
        # Boot persistent background services after a short delay
        QTimer.singleShot(100, self._boot_and_show)
        
    def _boot_and_show(self):
        """Boot background services, then show main window."""
        _boot_background_services()
        
        self.main_window = MainWindow()
        
        # Initialize background workers
        self._init_workers()
        
        # Close loading screen and show main window
        self.loading_screen.close()
        self.main_window.show()
        self.loading_screen.deleteLater()
        
    def _init_workers(self):
        # Operator Queue Worker: reads from operator_queue → queue panel
        self.queue_worker = OperatorQueueWorker(self)
        pres_tab = self.main_window._tabs.get("SCRIPTURE")
        if pres_tab:
            self.queue_worker.new_item.connect(pres_tab.queue_panel.add_item)
        self.queue_worker.start()
        
        # Hardware Telemetry Worker: polls GPU/RAM → status bar + settings tab
        self.hw_worker = HardwareTelemetryWorker(self)
        self.hw_worker.telemetry_update.connect(self.main_window.status_bar.update_hardware)
        # Connect to settings tab GPU section once it's lazy-loaded
        settings_tab = self.main_window._tabs.get("SETTINGS")
        if settings_tab:
            def _connect_hw_to_settings():
                if hasattr(settings_tab, 'update_gpu_hardware'):
                    self.hw_worker.telemetry_update.connect(settings_tab.update_gpu_hardware)
            QTimer.singleShot(500, _connect_hw_to_settings)
        self.hw_worker.start()
        
        # Transcript Stream Worker: reads from transcript_ui_queue → STT panel
        self.transcript_worker = TranscriptStreamWorker(self)
        if pres_tab:
            self.transcript_worker.new_transcript.connect(pres_tab.stt_panel.append_transcript)
        self.transcript_worker.start()

    def stop_workers(self):
        self.queue_worker.stop()
        self.hw_worker.stop()
        self.transcript_worker.stop()


def launch_ui():
    """Starts the PyQt6 event loop (must run on the main thread)."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S"
    )
    
    app = RhemaCastApp(sys.argv)
    
    # Run the event loop
    exit_code = app.exec()
    
    # Clean up workers on exit
    app.stop_workers()

    # Clear OBS display so nothing remains on screen
    try:
        from core.websocket_server import clear_display
        clear_display()
    except Exception:
        pass

    # Graceful shutdown of any running services
    try:
        from core.service_manager import manager, ServiceState
        if manager.state not in (ServiceState.BOOTING, ServiceState.SHUTTING_DOWN):
            manager.initiate_shutdown()
    except Exception:
        pass
    
    return exit_code

if __name__ == "__main__":
    sys.exit(launch_ui())

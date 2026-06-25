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

from ui.main_window import MainWindow
from ui.styles import APP_STYLESHEET
from ui.workers import OperatorQueueWorker, HardwareTelemetryWorker, TranscriptStreamWorker

logger = logging.getLogger(__name__)


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
        logger.info("WebSocket server started on ws://127.0.0.1:8765")
    except Exception as e:
        logger.error(f"Failed to start WebSocket server: {e}")


class RhemaCastApp(QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        self.setStyleSheet(APP_STYLESHEET)
        
        # Boot persistent background services
        _boot_background_services()
        
        self.main_window = MainWindow()
        
        # Initialize background workers
        self._init_workers()
        
    def _init_workers(self):
        # Operator Queue Worker: reads from operator_queue → queue panel
        self.queue_worker = OperatorQueueWorker(self)
        pres_tab = self.main_window._tabs.get("PRESENTATION")
        if pres_tab:
            self.queue_worker.new_item.connect(pres_tab.queue_panel.add_item)
        self.queue_worker.start()
        
        # Hardware Telemetry Worker: polls GPU/RAM → status bar
        self.hw_worker = HardwareTelemetryWorker(self)
        self.hw_worker.telemetry_update.connect(self.main_window.status_bar.update_hardware)
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
    app.main_window.show()
    
    # Run the event loop
    exit_code = app.exec()
    
    # Clean up workers on exit
    app.stop_workers()
    
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

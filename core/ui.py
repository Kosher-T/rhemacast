"""
core/ui.py

Entry point for the RhemaCast PyQt6 UI.
Initializes the QApplication, workers, and main window.
"""

import sys
import os
import logging

# Ensure the parent directory (project root) is in the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.styles import APP_STYLESHEET
from ui.workers import OperatorQueueWorker, HardwareTelemetryWorker

logger = logging.getLogger(__name__)

class RhemaCastApp(QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        self.setStyleSheet(APP_STYLESHEET)
        
        self.main_window = MainWindow()
        
        # Initialize background workers
        self._init_workers()
        
    def _init_workers(self):
        # Operator Queue Worker
        self.queue_worker = OperatorQueueWorker(self)
        pres_tab = self.main_window._tabs.get("PRESENTATION")
        if pres_tab:
            self.queue_worker.new_item.connect(pres_tab.queue_panel.add_item)
        self.queue_worker.start()
        
        # Hardware Telemetry Worker
        self.hw_worker = HardwareTelemetryWorker(self)
        self.hw_worker.telemetry_update.connect(self.main_window.status_bar.update_hardware)
        self.hw_worker.start()

    def stop_workers(self):
        self.queue_worker.stop()
        self.hw_worker.stop()

def launch_ui():
    """Starts the PyQt6 event loop (must run on the main thread)."""
    app = RhemaCastApp(sys.argv)
    app.main_window.show()
    
    # Run the event loop
    exit_code = app.exec()
    
    # Clean up workers on exit
    app.stop_workers()
    
    return exit_code

if __name__ == "__main__":
    sys.exit(launch_ui())

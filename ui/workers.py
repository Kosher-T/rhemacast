"""
ui/workers.py

Background QThread workers to bridge Python queues → Qt signals.
All heavy/blocking queue reads happen here so the UI thread never stalls.
"""

import queue
import logging
from PyQt6.QtCore import QThread, pyqtSignal

from core.queues import operator_queue, db_write_queue

logger = logging.getLogger(__name__)


class OperatorQueueWorker(QThread):
    """
    Polls the operator_queue (Thread 3 → UI) and emits new items
    as Qt signals. The UI binds to `new_item` to update the list widget.
    """
    new_item = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True

    def run(self):
        while self._running:
            try:
                item = operator_queue.get(timeout=0.25)
                self.new_item.emit(item)
                operator_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"OperatorQueueWorker error: {e}")

    def stop(self):
        self._running = False
        self.wait(2000)


class HardwareTelemetryWorker(QThread):
    """
    Reads hardware_telemetry payloads from the db_write_queue
    (or a dedicated telemetry channel) and emits them for the status bar.
    Debounces to ~30 FPS (≈33 ms minimum interval).
    """
    telemetry_update = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True
        self._last_emit_ms = 0

    def run(self):
        import time
        while self._running:
            try:
                # We peek the db_write_queue for hardware_telemetry items
                # In practice this would read from a dedicated telemetry channel
                # For now, we poll at 30 FPS cadence
                time.sleep(0.033)  # ~30 FPS
                self.msleep(1)
            except Exception as e:
                logger.error(f"HardwareTelemetryWorker error: {e}")

    def stop(self):
        self._running = False
        self.wait(2000)

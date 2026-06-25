"""
ui/workers.py

Background QThread workers to bridge Python queues → Qt signals.
All heavy/blocking queue reads happen here so the UI thread never stalls.
"""

import queue
import logging
from PyQt6.QtCore import QThread, pyqtSignal

from core.queues import operator_queue

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
    Polls HardwareMonitor for GPU temp, VRAM, and RAM metrics.
    Emits telemetry_update signal for the status bar at ~0.5 Hz (every 2 seconds).
    """
    telemetry_update = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True

    def run(self):
        import time
        from core.hardware_monitor import HardwareMonitor

        monitor = HardwareMonitor()
        loop_count = 0

        while self._running:
            try:
                payload = {}

                # Poll GPU every cycle (~2 seconds)
                gpu_stats = monitor.poll_gpu()
                payload.update(gpu_stats)

                # Poll RAM every 15 cycles (~30 seconds)
                if loop_count % 15 == 0:
                    ram_stats = monitor.poll_ram()
                    payload.update(ram_stats)

                if payload:
                    self.telemetry_update.emit(payload)

                loop_count += 1
                time.sleep(2.0)

            except Exception as e:
                logger.error(f"HardwareTelemetryWorker error: {e}")
                time.sleep(2.0)

    def stop(self):
        self._running = False
        self.wait(3000)


class TranscriptStreamWorker(QThread):
    """
    Reads transcript text chunks from the transcript_ui_queue and emits
    them as Qt signals for the STT panel to display.
    """
    new_transcript = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True

    def run(self):
        from core.queues import transcript_ui_queue
        while self._running:
            try:
                text = transcript_ui_queue.get(timeout=0.25)
                self.new_transcript.emit(text)
                transcript_ui_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"TranscriptStreamWorker error: {e}")

    def stop(self):
        self._running = False
        self.wait(2000)

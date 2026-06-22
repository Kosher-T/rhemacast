"""
core/db_writer.py

Implements the Database Write Queue pattern (Thread 4).
Single-writer thread that pulls and executes all inserts, 
and handles flat-file logging with PermissionError rotation.
"""

import queue
import json
import os
import sys
import logging
from dataclasses import asdict
from typing import Any

from .database import get_connection
from .events import BaseEvent, TranscriptChunk, SearchResult, DisplayCommand

logger = logging.getLogger(__name__)

# Single-writer queue
db_write_queue = queue.Queue()

# Sentinel for graceful shutdown (Phase 2.4 will use this)
POISON_PILL = object()

if sys.platform == "win32":
    BASE_LOG_DIR = r"C:\ProgramData\RhemaCast\Logs"
else:
    BASE_LOG_DIR = "/var/lib/rhemacast/logs"

class FlatFileHandler:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.part = 1
        self.file = None
        self._open_file()

    def _get_path(self):
        suffix = "" if self.part == 1 else f"_PART{self.part}"
        return os.path.join(BASE_LOG_DIR, f"{self.session_id}{suffix}.log")

    def _open_file(self):
        os.makedirs(BASE_LOG_DIR, exist_ok=True)
        path = self._get_path()
        while True:
            try:
                self.file = open(path, "a", encoding="utf-8")
                break
            except PermissionError:
                self.part += 1
                path = self._get_path()

    def write(self, event: BaseEvent):
        if self.file is not None:
            try:
                data = asdict(event)
                data["_event_type"] = event.__class__.__name__
                self.file.write(json.dumps(data) + "\n")
                self.file.flush()
            except PermissionError:
                logger.warning(f"PermissionError on {self._get_path()}, rotating to next part.")
                self.close()
                self.part += 1
                self._open_file()
                self.write(event)

    def close(self):
        if self.file:
            self.file.close()
            self.file = None

def db_writer_thread():
    """Main loop for Thread 4: DB Writer."""
    conn = get_connection()
    flat_files = {}

    logger.info("DB Writer thread started.")
    
    while True:
        try:
            item = db_write_queue.get()
            
            if item is POISON_PILL:
                logger.info("DB Writer received POISON_PILL, shutting down.")
                db_write_queue.task_done()
                break
                
            if not isinstance(item, BaseEvent):
                logger.warning("DB Writer received unknown item type. Ignoring.")
                db_write_queue.task_done()
                continue
                
            session_id = getattr(item, "session_id", None)
            
            if session_id:
                if session_id not in flat_files:
                    flat_files[session_id] = FlatFileHandler(session_id)
                # Simultaneous write to flat file
                flat_files[session_id].write(item)

            # Simultaneous write to SQLite
            if isinstance(item, TranscriptChunk):
                conn.execute(
                    "INSERT INTO transcripts (session_id, sequence_id, text_chunk, word_count, timestamp_ms) VALUES (?, ?, ?, ?, ?)",
                    (item.session_id, item.sequence_id, item.text_chunk, item.word_count, item.timestamp_ms)
                )
            elif isinstance(item, SearchResult):
                results_json = json.dumps([asdict(r) for r in item.results])
                conn.execute(
                    "INSERT INTO search_results (session_id, sequence_id, confidence_pct, intent_matched, latency_ms, results_json, timestamp_ms) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (item.session_id, item.sequence_id, item.confidence_pct, item.intent_matched, item.latency_ms, results_json, item.timestamp_ms)
                )
            elif isinstance(item, DisplayCommand):
                session_id_val = session_id if session_id else "global"
                conn.execute(
                    "INSERT INTO display_events (session_id, action, ref, text, translation, theme, timestamp_ms) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (session_id_val, item.action, item.ref, item.text, item.translation, item.theme, item.timestamp_ms)
                )
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"DatabaseWriteFailure: {e}", exc_info=True)
        finally:
            db_write_queue.task_done()

    # Teardown
    for handler in flat_files.values():
        handler.close()
    conn.close()
    logger.info("DB Writer thread cleanly exited.")

"""
core/logging_config.py

Centralized logging configuration for RhemaCast.
Provides structured human-readable logs and optional JSON-lines formatting.
Thread-safe by default through Python's logging module.
"""

import sys
import os
import json
import logging
from logging.handlers import RotatingFileHandler

if sys.platform == "win32":
    BASE_LOG_DIR = r"C:\ProgramData\RhemaCast\Logs"
else:
    BASE_LOG_DIR = "/var/lib/rhemacast/logs"

class JsonFormatter(logging.Formatter):
    """Formats log records as JSON lines for machine parsing."""
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)

def setup_logging(debug_mode: bool = False, json_mode: bool = False):
    """
    Configures the root logger and specific module loggers.
    Must be called exactly once at application startup.
    """
    global BASE_LOG_DIR
    
    # Ensure log directory exists
    try:
        os.makedirs(BASE_LOG_DIR, exist_ok=True)
    except PermissionError:
        # Fallback to local directory if permissions are lacking (e.g., Linux without sudo)
        fallback_dir = os.path.join(os.getcwd(), "logs")
        os.makedirs(fallback_dir, exist_ok=True)
        print(f"WARNING: Lacking permissions for {BASE_LOG_DIR}. Falling back to {fallback_dir}")
        BASE_LOG_DIR = fallback_dir

    log_file_path = os.path.join(BASE_LOG_DIR, "rhemacast.log")

    # Root logger setup
    root_logger = logging.getLogger()
    
    # Reset existing handlers if any to prevent duplicate logging
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    root_logger.setLevel(logging.DEBUG if debug_mode else logging.INFO)

    # 10 MB per file, keep 7 backup files
    file_handler = RotatingFileHandler(
        filename=log_file_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=7,
        encoding="utf-8"
    )

    console_handler = logging.StreamHandler(sys.stdout)

    if json_mode:
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")

    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Configure specific module levels
    core_level = logging.DEBUG if debug_mode else logging.WARNING
    logging.getLogger("core").setLevel(core_level)
    logging.getLogger("tests").setLevel(logging.INFO)

    # Send a startup marker
    logging.getLogger("core.logging_config").info(f"Logging initialized. Output: {log_file_path} (JSON: {json_mode}, DEBUG: {debug_mode})")

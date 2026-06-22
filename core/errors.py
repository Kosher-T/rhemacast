"""
core/errors.py

Formal error taxonomy for the RhemaCast service.
Defines standard attributes for how errors should be handled by the Service Manager.
"""

from enum import Enum, auto

class ErrorPropagationPattern(Enum):
    CONTINUE = auto()   # Transient error: log warning, push error event to DB queue, resume loop
    DEGRADE = auto()    # Non-critical subsystem failure: notify operator of degraded state
    FAILOVER = auto()   # Critical component failure: transition to FAILOVER state (e.g., Vosk fallback)
    SHUTDOWN = auto()   # Unrecoverable error: cascade poison pills, log critical error, exit

class RhemaCastError(Exception):
    """Base exception class for all RhemaCast specific errors."""
    pattern: ErrorPropagationPattern = ErrorPropagationPattern.SHUTDOWN
    retryable: bool = False
    fatal: bool = False
    operator_visible: bool = False
    auto_recoverable: bool = False

    def __init__(self, message: str, **kwargs):
        super().__init__(message)
        self.message = message
        self.context = kwargs

class ComputeFailure(RhemaCastError):
    """Raised when the primary STT engine (Faster-Whisper) fails or stalls."""
    pattern = ErrorPropagationPattern.FAILOVER
    retryable = True
    fatal = False
    operator_visible = True
    auto_recoverable = True  # Triggers Vosk failover

class AudioDeviceLost(RhemaCastError):
    """Raised when the audio capture stream dies (e.g., receiver unplugged)."""
    pattern = ErrorPropagationPattern.SHUTDOWN
    retryable = False
    fatal = True
    operator_visible = True
    auto_recoverable = False

class GPUOverheat(RhemaCastError):
    """Raised when the GPU temperature exceeds the critical threshold."""
    pattern = ErrorPropagationPattern.DEGRADE
    retryable = True
    fatal = False
    operator_visible = True
    auto_recoverable = True  # Triggers power limit throttling

class DatabaseWriteFailure(RhemaCastError):
    """Raised when the DB writer thread cannot commit payloads."""
    pattern = ErrorPropagationPattern.CONTINUE
    retryable = True
    fatal = False
    operator_visible = False
    auto_recoverable = True  # Falls back to flat-file logging

class IndexMismatch(RhemaCastError):
    """Raised on startup if BM25/FAISS indexes don't match the Bible database."""
    pattern = ErrorPropagationPattern.SHUTDOWN
    retryable = False
    fatal = True
    operator_visible = True
    auto_recoverable = False

class DisplayDisconnected(RhemaCastError):
    """Raised when the OBS Browser Source or WebSocket client disconnects."""
    pattern = ErrorPropagationPattern.CONTINUE
    retryable = True
    fatal = False
    operator_visible = True
    auto_recoverable = True  # Client auto-reconnects

class CloudExtractionFailure(RhemaCastError):
    """Raised when post-service LLM processing fails via API."""
    pattern = ErrorPropagationPattern.CONTINUE
    retryable = True
    fatal = False
    operator_visible = False
    auto_recoverable = True  # Sent to offline queue for later retry

class StartupCheckError(RhemaCastError):
    """Raised when a critical startup verification step fails (e.g. missing indexes)."""
    pattern = ErrorPropagationPattern.SHUTDOWN
    retryable = False
    fatal = True
    operator_visible = True
    auto_recoverable = False

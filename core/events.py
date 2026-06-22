"""
core/events.py

Dataclasses for all inter-thread payloads (Event Bus).
Each event type is versioned to prevent schema drift and ensure compatibility
when events are serialized to the database or broadcasted.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time

@dataclass(kw_only=True)
class BaseEvent:
    """Base class for all events to enforce versioning and timestamps."""
    version: int
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))

@dataclass(kw_only=True)
class TranscriptChunk(BaseEvent):
    """Payload pushed to Queue B from the STT engine."""
    session_id: str
    sequence_id: int
    text_chunk: str
    word_count: int
    version: int = 1

@dataclass(kw_only=True)
class SearchQuery(BaseEvent):
    """Payload representing a triggered search attempt."""
    session_id: str
    sequence_id: int
    raw_query: str
    normalized_query: str
    trigger_phrase: Optional[str]
    version: int = 1

@dataclass(kw_only=True)
class VerseResult:
    """A single verse result within a SearchResult payload."""
    rank: int
    version: str
    book: str
    chapter: int
    verse_num: int
    text: str
    bm25_rank: Optional[int]
    faiss_rank: Optional[int]
    rrf_score: float

@dataclass(kw_only=True)
class SearchResult(BaseEvent):
    """Payload representing the results of a search."""
    session_id: str
    sequence_id: int
    confidence_pct: float
    intent_matched: bool
    results: List[VerseResult]
    latency_ms: float
    version: int = 1

@dataclass(kw_only=True)
class DisplayCommand(BaseEvent):
    """Payload for broadcasting commands to the WebSocket display clients."""
    action: str  # "display", "clear", etc.
    ref: Optional[str] = None
    text: Optional[str] = None
    translation: Optional[str] = None
    theme: Optional[str] = None
    version: int = 1

@dataclass(kw_only=True)
class TelemetrySample(BaseEvent):
    """Payload for hardware and system monitoring."""
    gpu_temp_c: Optional[float] = None
    gpu_power_w: Optional[float] = None
    gpu_vram_used_mb: Optional[float] = None
    gpu_utilization_pct: Optional[float] = None
    is_throttled: bool = False
    system_ram_available_mb: Optional[float] = None
    queue_a_depth: int = 0
    queue_b_depth: int = 0
    db_queue_depth: int = 0
    operator_queue_depth: int = 0
    version: int = 1

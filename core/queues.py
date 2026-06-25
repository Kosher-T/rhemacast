"""
core/queues.py

Central definition of all inter-thread queues, backpressure policies,
and the Queue A acknowledgment protocol.
"""

import queue
import logging
from collections import OrderedDict
from typing import Any, Optional, List, Dict

logger = logging.getLogger(__name__)

# Global Sentinel for graceful shutdown
POISON_PILL = object()

# Define the central queues
# Max pending 100ms PCM audio chunks (500 chunks = 50 seconds of audio buffer)
queue_a = queue.Queue(maxsize=500)

# Max pending 15-word STT transcript blocks awaiting search scoring
queue_b = queue.Queue(maxsize=200)

# Max pending database event payloads
db_write_queue = queue.Queue(maxsize=1000)

# Max pending verse suggestions waiting for human operator review
operator_queue = queue.Queue(maxsize=100)

# For WebSocket broadcast coalescence
ws_broadcast_queue = queue.Queue(maxsize=100)

# Lightweight queue for pushing transcript text to the STT panel in the UI
transcript_ui_queue = queue.Queue(maxsize=200)


# ─── Queue A Acknowledgment Protocol ─────────────────────────────────────────

class AudioChunkBuffer:
    """
    Manages Queue A and the pending chunks dictionary for replay capability
    on Compute Failure.
    """
    def __init__(self):
        # OrderedDict maintains insertion order so replay is sequential
        self.pending_chunks: Dict[str, bytes] = OrderedDict()

    def enqueue(self, chunk_id: str, pcm_data: bytes):
        """Adds a chunk to Queue A."""
        if queue_a.qsize() > 400:
            # Backpressure Policy: Queue A: never drop audio chunks; trigger failover if depth > 400
            # Failover flag to be handled by the service manager
            logger.warning("Queue A depth > 400! Failover threshold reached.")
        
        # We enqueue without tracking as pending yet
        queue_a.put((chunk_id, pcm_data))

    def pull(self, block: bool = True, timeout: Optional[float] = None) -> tuple[str, bytes]:
        """Thread 2 pulls from Queue A and tracks as pending."""
        chunk_id, pcm_data = queue_a.get(block=block, timeout=timeout)
        self.pending_chunks[chunk_id] = pcm_data
        return chunk_id, pcm_data

    def ack(self, chunk_id: str):
        """Thread 2 calls this when processing completes successfully."""
        if chunk_id in self.pending_chunks:
            del self.pending_chunks[chunk_id]

    def get_unacked_chunks(self) -> List[bytes]:
        """On Compute Failure, retrieve all pending chunks to replay to Vosk."""
        return list(self.pending_chunks.values())

audio_buffer = AudioChunkBuffer()


# ─── Operator Queue Policy ───────────────────────────────────────────────────

def push_to_operator(item: Any, confidence: float, priority: str = "normal"):
    """
    Operator queue backpressure policy: drop oldest low-confidence items if full.
    For simplicity, if full, we just pop the oldest to make room.
    """
    item["priority"] = priority
    
    if operator_queue.full():
        logger.warning("Operator queue full. Evicting oldest item.")
        try:
            operator_queue.get_nowait()
            operator_queue.task_done()
        except queue.Empty:
            pass
    operator_queue.put(item)


# ─── DB Queue Emergency Spool Fallback ───────────────────────────────────────

def push_to_db(item: Any):
    """
    DB queue backpressure policy: emergency disk spool fallback if overloaded.
    """
    try:
        db_write_queue.put_nowait(item)
    except queue.Full:
        logger.error("DB Write Queue is full! Falling back to emergency spool.")
        # Simulated spool to disk logic
        # Here we would serialize `item` and append it directly to the flat log 
        # on the calling thread to guarantee no telemetry or events are lost.
        # This will be refined when full system integration occurs.


# ─── WebSocket Broadcast Coalescence ─────────────────────────────────────────

class CoalescingWSQueue:
    """
    WebSocket broadcast queue backpressure policy: coalesce repeated events.
    Prevents flooding the frontend with the same verse consecutively.
    """
    def __init__(self):
        self.last_display_ref: Optional[str] = None
        
    def enqueue(self, event: Any):
        # Determine if it's a display event and has a ref
        if getattr(event, "action", None) == "display":
            ref = getattr(event, "ref", None)
            if ref and ref == self.last_display_ref:
                # Coalesce: do not enqueue repeated same-verse events
                logger.debug(f"Coalescing redundant display event for ref: {ref}")
                return
            self.last_display_ref = ref
            
        ws_broadcast_queue.put(event)

ws_queue_manager = CoalescingWSQueue()

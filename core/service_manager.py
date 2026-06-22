"""
core/service_manager.py

Central threading harness and state machine orchestrator for RhemaCast.
Manages thread boot sequence, health monitoring, crash escalation, and teardown.

Thread Inventory & Lifecycle:
| Thread | Purpose | Started At | Stopped At |
|--------|---------|-----------|-----------|
| Main Thread | UI rendering, operator controls, lifecycle | Application launch | Application exit |
| Thread 1 — Audio Capture | Captures PCM audio, pushes to Queue A | "Start Transcription" | Poison pill from Queue A |
| Thread 2 — STT Inference | Faster-Whisper on GPU, sliding window | "Start Transcription" | Poison pill from Queue A |
| Thread 3 — Search & Scoring | BM25 + FAISS parallel, RRF fusion | "Start Transcription" | Poison pill from Queue B |
| Thread 4 — DB Writer | SQL inserts + flat file append | Phase 1 init | Poison pill from DB Queue |
| Thread 5 — Hardware Monitor | GPU temp polling via pynvml | Phase 1 init | Service flag set to False |
| WebSocket Server | Push display payloads to HTML renderer | Phase 1 init | Application exit |

Error Propagation Patterns:
1. CONTINUE (transient error): Log warning, push error event to DB queue, resume loop.
2. DEGRADE (non-critical subsystem failure): Transition system to DEGRADED state, notify operator.
3. FAILOVER (critical component failure): Transition to FAILOVER state (e.g., Vosk fallback).
4. SHUTDOWN (unrecoverable error): Cascade poison pills, log critical error, exit.
"""

import threading
import time
import logging
import queue
import tracemalloc
from enum import Enum, auto
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from .queues import queue_a, queue_b, db_write_queue, operator_queue, POISON_PILL

logger = logging.getLogger(__name__)

# ─── Global State & Events ───────────────────────────────────────────────────

class ServiceState(Enum):
    BOOTING = auto()
    READY = auto()
    RUNNING = auto()
    DEGRADED = auto()
    FAILOVER = auto()
    SHUTTING_DOWN = auto()
    CRASHED = auto()

# Global events that threads can listen to
service_active = threading.Event()
compute_failure = threading.Event()

# ─── Thread Registry ─────────────────────────────────────────────────────────

@dataclass
class ThreadMetadata:
    id: str
    target: Callable
    thread_obj: Optional[threading.Thread] = None
    last_heartbeat: float = 0.0
    restart_count: int = 0
    max_restarts: int = 0
    critical: bool = True

class ServiceManager:
    def __init__(self, poll_interval: float = 2.0, timeout_seconds: float = 10.0):
        self.state = ServiceState.BOOTING
        self.threads: Dict[str, ThreadMetadata] = {}
        self.watchdog_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.poll_interval = poll_interval
        self.timeout_seconds = timeout_seconds
        
    def register_thread(self, thread_id: str, target: Callable, max_restarts: int = 0, critical: bool = True):
        with self._lock:
            self.threads[thread_id] = ThreadMetadata(
                id=thread_id,
                target=target,
                max_restarts=max_restarts,
                critical=critical
            )
            
    def heartbeat(self, thread_id: str):
        """Called by a worker thread to signal it is alive."""
        with self._lock:
            if thread_id in self.threads:
                self.threads[thread_id].last_heartbeat = time.time()

    def _start_thread(self, thread_id: str):
        meta = self.threads[thread_id]
        meta.last_heartbeat = time.time() # Initialize heartbeat
        meta.thread_obj = threading.Thread(target=meta.target, name=f"Worker-{thread_id}", daemon=True)
        meta.thread_obj.start()
        logger.info(f"Started thread {thread_id} (restarts: {meta.restart_count}/{meta.max_restarts})")

    def boot(self):
        """Boots all registered threads in specific sequence."""
        logger.info("Service Manager initiating boot sequence...")
        
        # Start tracemalloc for OOM crash dumps
        tracemalloc.start()
        
        self.state = ServiceState.BOOTING
        service_active.set()
        compute_failure.clear()
        
        # Strict boot order: T4 -> T5 -> T1 -> T2 -> T3
        boot_order = ["T4", "T5", "T1", "T2", "T3"]
        
        for tid in boot_order:
            if tid in self.threads:
                self._start_thread(tid)
                # Small delay to ensure the thread actually starts and initializes its resources
                time.sleep(0.1)
                
        # Start watchdog
        self.watchdog_thread = threading.Thread(target=self._watchdog_loop, name="Watchdog", daemon=True)
        self.watchdog_thread.start()
        
        self.state = ServiceState.RUNNING
        logger.info("System is RUNNING.")

    def _watchdog_loop(self):
        """Monitors thread health and applies restart policies."""
        while service_active.is_set():
            time.sleep(self.poll_interval)
            
            with self._lock:
                now = time.time()
                for tid, meta in self.threads.items():
                    if meta.thread_obj is None:
                        continue
                        
                    is_alive = meta.thread_obj.is_alive()
                    timed_out = (now - meta.last_heartbeat) > self.timeout_seconds
                    
                    if not is_alive or timed_out:
                        reason = "died" if not is_alive else "timed out"
                        logger.warning(f"Thread {tid} {reason}!")
                        
                        if meta.restart_count < meta.max_restarts:
                            meta.restart_count += 1
                            logger.info(f"Restarting thread {tid}...")
                            self._start_thread(tid)
                        else:
                            self._handle_escalation(tid, meta)

    def _handle_escalation(self, thread_id: str, meta: ThreadMetadata):
        """Determines what to do when a thread exceeds its restart limit."""
        if meta.critical:
            if thread_id == "T2":
                logger.error("STT Inference (T2) failed permanently. Transitioning to FAILOVER.")
                self.state = ServiceState.FAILOVER
                compute_failure.set() # Signals Vosk to take over
                meta.critical = False # Demote so it doesn't crash the whole system on next loop
            else:
                logger.critical(f"Critical thread {thread_id} failed permanently! Escalating to CRASHED.")
                self.state = ServiceState.CRASHED
                self.initiate_shutdown()
        else:
            if self.state not in (ServiceState.FAILOVER, ServiceState.CRASHED):
                logger.warning(f"Non-critical thread {thread_id} failed permanently. Transitioning to DEGRADED.")
                self.state = ServiceState.DEGRADED

    def initiate_shutdown(self):
        """Performs a graceful teardown with sequential poison pills."""
        if self.state == ServiceState.SHUTTING_DOWN:
            return
            
        logger.info("Initiating graceful shutdown...")
        self.state = ServiceState.SHUTTING_DOWN
        service_active.clear() # Signal threads to break their main loops
        
        # 1. Join producer threads first (T1, T2, T3)
        for tid in ["T1", "T2", "T3"]:
            if tid in self.threads and self.threads[tid].thread_obj:
                self.threads[tid].thread_obj.join(timeout=3.0)
                
        # 2. Drain transient queues to ensure no memory leaks and cleanly free buffers
        logger.info("Draining transient queues...")
        for q in [queue_a, queue_b, operator_queue]:
            while not q.empty():
                try: 
                    q.get_nowait()
                    q.task_done()
                except queue.Empty: 
                    break

        # 3. Inject POISON_PILL to DB queue (T4) to flush disk
        logger.info("Injecting POISON_PILL to DB queue...")
        db_write_queue.put(POISON_PILL)
        
        if "T4" in self.threads and self.threads["T4"].thread_obj:
            self.threads["T4"].thread_obj.join(timeout=5.0)
            
        # 4. Join remaining non-critical threads (T5)
        if "T5" in self.threads and self.threads["T5"].thread_obj:
            self.threads["T5"].thread_obj.join(timeout=2.0)
            
        logger.info("Teardown complete.")

# Global singleton instance
manager = ServiceManager()

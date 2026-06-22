import logging
import threading
import time
import queue

from core.queues import audio_buffer, queue_a
from core.audio_capture import capture_paused
from core.errors import ComputeFailure
from core.service_manager import manager, service_active, compute_failure

logger = logging.getLogger(__name__)

# Internal state
_stt_running = threading.Event()
_last_processed_time = 0.0
_stt_lock = threading.Lock()

def _stt_thread_target():
    """
    Mock primary STT Inference Loop (Thread 2).
    In Phase 4, this will run Faster-Whisper. For Phase 3.2, it simulates processing.
    """
    global _last_processed_time
    logger.info("Starting STT Inference (Thread 2) mock")
    _stt_running.set()
    
    with _stt_lock:
        _last_processed_time = time.time()
        
    while _stt_running.is_set() and service_active.is_set():
        try:
            # Pull from Queue A (moves chunk to pending)
            chunk_id, pcm_data = audio_buffer.pull(block=True, timeout=0.5)
            
            # Simulate STT processing time (~50ms)
            time.sleep(0.05)
            
            # Update heartbeat
            with _stt_lock:
                _last_processed_time = time.time()
            manager.heartbeat("T2")
            
            # Ack on successful processing
            audio_buffer.ack(chunk_id)
            
        except queue.Empty:
            # No audio incoming, update heartbeat anyway so we don't failover due to silence
            with _stt_lock:
                _last_processed_time = time.time()
            manager.heartbeat("T2")
        except Exception as e:
            logger.error(f"STT Inference error: {e}")

def _stt_watchdog_target():
    """
    Watchdog thread specifically for monitoring STT compute stalls.
    Refined Compute Failure detection: if stalled for > 2 seconds while audio is incoming.
    """
    global _last_processed_time
    logger.info("Starting STT Watchdog")
    
    while _stt_running.is_set() and service_active.is_set():
        time.sleep(0.5)
        
        with _stt_lock:
            time_since_last = time.time() - _last_processed_time
            
        # If stalled for > 2s AND there is audio waiting in the queue
        if time_since_last > 2.0 and queue_a.qsize() > 0:
            logger.critical(f"STT Inference stalled for {time_since_last:.1f}s while audio is incoming!")
            _trigger_failover_sequence()
            break  # Exit watchdog since primary STT is dead

def _trigger_failover_sequence():
    """
    Executes the Pause -> Replay -> Resume sequence for Vosk fallback.
    """
    logger.warning("Initiating STT Failover Sequence...")
    
    # 1. Pause audio capture (Thread 1 buffers new chunks)
    capture_paused.set()
    logger.info("Live audio capture paused.")
    
    # 2. Replay pending unacknowledged chunks to Vosk
    unacked = audio_buffer.get_unacked_chunks()
    logger.info(f"Retrieved {len(unacked)} unacknowledged chunks for Vosk replay.")
    
    # Empty out Queue A since Thread 2 is dead, these also need to go to Vosk
    while not queue_a.empty():
        try:
            _, pcm = queue_a.get_nowait()
            unacked.append(pcm)
            queue_a.task_done()
        except queue.Empty:
            break
            
    logger.info(f"Total chunks sent to Vosk fallback: {len(unacked)}")
    
    # 3. Trigger ServiceManager failover state
    compute_failure.set()
    
    # 4. Resume capture (Thread 1 flushes buffer to Queue A for Vosk to read)
    capture_paused.clear()
    logger.info("Live audio capture resumed. Vosk is now primary.")
    
    # Kill the primary STT loop
    _stt_running.clear()

def start_stt():
    """Spawns the STT loop and its watchdog."""
    t_main = threading.Thread(target=_stt_thread_target, name="STT-Inference", daemon=True)
    t_watch = threading.Thread(target=_stt_watchdog_target, name="STT-Watchdog", daemon=True)
    
    t_main.start()
    t_watch.start()
    return t_main, t_watch

def stop_stt():
    """Gracefully stops STT threads."""
    _stt_running.clear()

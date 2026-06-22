import time
import queue
import logging
import threading
import collections
import numpy as np

from core.queues import audio_buffer, queue_a, queue_b, db_write_queue
from core.audio_capture import capture_paused, silence_detected
from core.errors import ComputeFailure
from core.service_manager import manager, service_active, compute_failure
from core.model_manager import model_manager

logger = logging.getLogger(__name__)

# Internal state
_stt_running = threading.Event()
_last_processed_time = 0.0
_stt_lock = threading.Lock()
sequence_counter = 0
session_id = time.strftime("%Y-%m-%d_%H-%M")

def _stt_thread_target():
    """Primary STT Inference Loop (Thread 2) using Faster-Whisper."""
    global _last_processed_time, sequence_counter
    logger.info("Starting STT Inference (Thread 2) with Faster-Whisper")
    
    with _stt_lock:
        _last_processed_time = time.time()
        
    whisper_model = model_manager.whisper_model
    
    word_buffer = []
    trigger_buffer = collections.deque(maxlen=50)
    wait_state = False
    
    # Audio accumulation buffer (collect chunks to form a longer segment)
    pcm_accumulator = []
    accumulated_chunk_ids = []
    
    while _stt_running.is_set() and service_active.is_set() and not compute_failure.is_set():
        try:
            chunk_id, pcm_data = audio_buffer.pull(block=True, timeout=0.1)
            pcm_accumulator.append(pcm_data)
            accumulated_chunk_ids.append(chunk_id)
            
            with _stt_lock:
                _last_processed_time = time.time()
            manager.heartbeat("T2")
            
            # If we have 1 second of audio (10 chunks of 100ms) or silence is detected
            if len(pcm_accumulator) >= 10 or silence_detected.is_set():
                # Process audio
                audio_array = np.concatenate(pcm_accumulator).flatten()
                
                # Transcribe
                if whisper_model:
                    segments, _ = whisper_model.transcribe(audio_array)
                    
                    for segment in segments:
                        words = segment.text.strip().split()
                        if not words: continue
                        
                        word_buffer.extend(words)
                        trigger_buffer.extend(words)
                        
                        # Wait state logic
                        if wait_state:
                            # Preceding: extract prior 15 words from trigger_buffer
                            prior = list(trigger_buffer)[-15:]
                            # Snap proceeding words
                            wait_state = False
                        
                        # Sliding window logic
                        while len(word_buffer) >= 15:
                            chunk_words = word_buffer[:15]
                            payload = {
                                "session_id": session_id,
                                "sequence_id": sequence_counter,
                                "timestamp_ms": int(time.time() * 1000),
                                "text_chunk": " ".join(chunk_words),
                                "word_count": len(chunk_words)
                            }
                            sequence_counter += 1
                            queue_b.put(payload)
                            
                            # Log to DB Write Queue
                            db_write_queue.put({"type": "raw_stt", "payload": payload})
                            
                            # Retain last 6 words (overlap), drop oldest 9
                            word_buffer = word_buffer[9:]
                
                # TTL Override (silence flush)
                if silence_detected.is_set() and len(word_buffer) > 0:
                    payload = {
                        "session_id": session_id,
                        "sequence_id": sequence_counter,
                        "timestamp_ms": int(time.time() * 1000),
                        "text_chunk": " ".join(word_buffer),
                        "word_count": len(word_buffer)
                    }
                    sequence_counter += 1
                    queue_b.put(payload)
                    db_write_queue.put({"type": "raw_stt", "payload": payload})
                    word_buffer.clear()
                    silence_detected.clear()
                
                # Ack all processed chunks
                for cid in accumulated_chunk_ids:
                    audio_buffer.ack(cid)
                pcm_accumulator.clear()
                accumulated_chunk_ids.clear()
                
        except queue.Empty:
            with _stt_lock:
                _last_processed_time = time.time()
            manager.heartbeat("T2")
        except Exception as e:
            logger.error(f"STT Inference error: {e}")

def _vosk_thread_target():
    """Vosk Failover Thread."""
    global _last_processed_time, sequence_counter
    logger.info("Vosk fallback thread waiting in standby (0 CPU)...")
    
    # Block on the failover event flag
    compute_failure.wait()
    
    if not _stt_running.is_set() or not service_active.is_set():
        return
        
    logger.info("Vosk failover activated. Replaying unacknowledged chunks...")
    vosk_model = model_manager.vosk_model
    if not vosk_model:
        logger.critical("Vosk model not available for failover!")
        return
        
    from vosk import KaldiRecognizer
    rec = KaldiRecognizer(vosk_model, 16000)
    
    unacked = audio_buffer.get_unacked_chunks()
    
    while not queue_a.empty():
        try:
            _, pcm = queue_a.get_nowait()
            unacked.append(pcm)
            queue_a.task_done()
        except queue.Empty:
            break
            
    # Replay
    word_buffer = []
    
    for pcm_data in unacked:
        # Convert float32 to int16 for Vosk
        int16_data = (pcm_data * 32767).astype(np.int16).tobytes()
        if rec.AcceptWaveform(int16_data):
            res = rec.Result()
            import json
            text = json.loads(res).get("text", "")
            if text:
                words = text.split()
                word_buffer.extend(words)
                
                while len(word_buffer) >= 15:
                    chunk_words = word_buffer[:15]
                    payload = {
                        "session_id": session_id,
                        "sequence_id": sequence_counter,
                        "timestamp_ms": int(time.time() * 1000),
                        "text_chunk": " ".join(chunk_words),
                        "word_count": len(chunk_words)
                    }
                    sequence_counter += 1
                    queue_b.put(payload)
                    db_write_queue.put({"type": "raw_stt", "payload": payload})
                    word_buffer = word_buffer[9:]
        time.sleep(0.01) # Yield
        
    # Resume live capture
    capture_paused.clear()
    logger.info("Vosk replay complete. Resuming live capture in CPU-only mode.")
    
    # Now continue loop for Vosk
    while _stt_running.is_set() and service_active.is_set():
        try:
            chunk_id, pcm_data = audio_buffer.pull(block=True, timeout=0.1)
            int16_data = (pcm_data * 32767).astype(np.int16).tobytes()
            
            if rec.AcceptWaveform(int16_data):
                res = rec.Result()
                import json
                text = json.loads(res).get("text", "")
                if text:
                    words = text.split()
                    word_buffer.extend(words)
                    
                    while len(word_buffer) >= 15:
                        chunk_words = word_buffer[:15]
                        payload = {
                            "session_id": session_id,
                            "sequence_id": sequence_counter,
                            "timestamp_ms": int(time.time() * 1000),
                            "text_chunk": " ".join(chunk_words),
                            "word_count": len(chunk_words)
                        }
                        sequence_counter += 1
                        queue_b.put(payload)
                        db_write_queue.put({"type": "raw_stt", "payload": payload})
                        word_buffer = word_buffer[9:]
            audio_buffer.ack(chunk_id)
        except queue.Empty:
            pass

def _stt_watchdog_target():
    """Watchdog thread for monitoring STT compute stalls."""
    global _last_processed_time
    logger.info("Starting STT Watchdog")
    
    while _stt_running.is_set() and service_active.is_set():
        time.sleep(0.5)
        
        # If compute_failure is already set, exit watchdog
        if compute_failure.is_set():
            break
            
        with _stt_lock:
            time_since_last = time.time() - _last_processed_time
            
        if time_since_last > 2.0 and queue_a.qsize() > 0:
            logger.critical(f"STT Inference stalled for {time_since_last:.1f}s while audio is incoming!")
            _trigger_failover_sequence()
            break

def _trigger_failover_sequence():
    """Executes the Pause -> Replay -> Resume sequence for Vosk fallback."""
    logger.warning("Initiating STT Failover Sequence...")
    capture_paused.set()
    logger.info("Live audio capture paused.")
    compute_failure.set() # This unblocks _vosk_thread_target

def start_stt():
    """Spawns the STT loop and its watchdog."""
    _stt_running.set()
    
    if model_manager.stt_mode == "vosk_primary":
        # Start Vosk thread as primary
        compute_failure.set() # Instant unblock
        t_main = threading.Thread(target=_vosk_thread_target, name="STT-Vosk-Primary", daemon=True)
        t_main.start()
        return t_main, None
    else:
        t_main = threading.Thread(target=_stt_thread_target, name="STT-Inference", daemon=True)
        t_watch = threading.Thread(target=_stt_watchdog_target, name="STT-Watchdog", daemon=True)
        t_vosk = threading.Thread(target=_vosk_thread_target, name="STT-Vosk-Failover", daemon=True)
        
        t_main.start()
        t_watch.start()
        t_vosk.start()
        return t_main, t_watch

def stop_stt():
    """Gracefully stops STT threads."""
    _stt_running.clear()
    compute_failure.set() # Ensure vosk thread unblocks and exits

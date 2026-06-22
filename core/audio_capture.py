import logging
import threading
import time
import uuid
import numpy as np
import sounddevice as sd

from typing import List, Dict, Optional

from core import constants
from core.queues import audio_buffer, db_write_queue, push_to_db, ws_queue_manager
from core.errors import AudioDeviceLost
from core.events import TelemetrySample, DisplayCommand

logger = logging.getLogger(__name__)

# Globally accessible event set when 3 seconds of silence is detected
silence_detected = threading.Event()

# Internal event to control the capture loop
_capture_running = threading.Event()

# Globally accessible event to pause capture queueing during failover
capture_paused = threading.Event()
_paused_buffer = []

# Internal state for tracking silence duration
_silence_duration_blocks = 0
SILENCE_THRESHOLD_DB = -50.0
BLOCKS_FOR_3_SECONDS = 30  # 30 blocks * 100ms = 3 seconds

def get_input_devices() -> List[Dict[str, str]]:
    """
    Enumerates all available audio input devices.
    Returns a list of dictionaries containing 'index' and 'name'.
    """
    devices = []
    try:
        device_list = sd.query_devices()
        # Blacklist of common Linux ALSA virtual/routing devices to hide from the UI
        linux_virtual_blacklist = ['lavrate', 'speex', 'pulse', 'upmix', 'vdownmix', 'pipewire', 'samplerate', 'sysdefault', 'default']
        
        for idx, dev in enumerate(device_list):
            if dev['max_input_channels'] > 0:
                name_lower = dev['name'].lower()
                if any(b in name_lower for b in linux_virtual_blacklist):
                    continue
                    
                devices.append({
                    'index': idx,
                    'name': dev['name'],
                    'hostapi': sd.query_hostapis(dev['hostapi'])['name']
                })
    except Exception as e:
        logger.error(f"Failed to query audio devices: {e}")
    return devices

def check_device(device_index: int) -> bool:
    """
    Pre-flight device check. Verifies that the device supports the required settings:
    16kHz, Mono, float32.
    """
    try:
        sd.check_input_settings(
            device=device_index,
            channels=1,
            dtype='float32',
            samplerate=constants.SAMPLE_RATE
        )
        return True
    except Exception as e:
        logger.warning(f"Device {device_index} failed pre-flight check: {e}")
        return False

def _calculate_rms_db(indata: np.ndarray) -> float:
    """
    Calculates the RMS energy of the audio block in decibels.
    """
    rms = np.sqrt(np.mean(indata**2))
    if rms > 0:
        return 20 * np.log10(rms)
    return -100.0

def _audio_callback(indata: np.ndarray, frames: int, time_info: dict, status: sd.CallbackFlags):
    """
    Callback function invoked by sounddevice for each audio block.
    """
    global _silence_duration_blocks
    
    if status:
        logger.warning(f"Audio callback status: {status}")

    if not _capture_running.is_set():
        raise sd.CallbackStop()

    # Calculate RMS energy for silence detection
    rms_db = _calculate_rms_db(indata)
    if rms_db < SILENCE_THRESHOLD_DB:
        _silence_duration_blocks += 1
        if _silence_duration_blocks >= BLOCKS_FOR_3_SECONDS and not silence_detected.is_set():
            logger.debug("Silence threshold reached (3s). Setting silence_detected event.")
            silence_detected.set()
    else:
        _silence_duration_blocks = 0
        if silence_detected.is_set():
            silence_detected.clear()

    # Generate unique ID and PCM data
    chunk_id = str(uuid.uuid4())
    pcm_data = indata.copy().tobytes()
    
    if capture_paused.is_set():
        _paused_buffer.append((chunk_id, pcm_data))
    else:
        # Flush buffer first to preserve order
        if _paused_buffer:
            for c_id, data in _paused_buffer:
                audio_buffer.enqueue(c_id, data)
            _paused_buffer.clear()
        audio_buffer.enqueue(chunk_id, pcm_data)

def _capture_thread_target(device_index: int):
    """
    Main audio capture loop for Thread 1.
    """
    logger.info(f"Starting audio capture on device {device_index}")
    _capture_running.set()
    _silence_duration_blocks = 0
    silence_detected.clear()
    
    try:
        with sd.InputStream(
            device=device_index,
            channels=1,
            samplerate=constants.SAMPLE_RATE,
            blocksize=constants.BLOCK_SIZE,
            dtype='float32',
            callback=_audio_callback
        ):
            while _capture_running.is_set():
                time.sleep(0.1)
                
    except sd.PortAudioError as e:
        logger.error(f"FATAL_AUDIO_LOSS: PortAudioError: {e}")
        _handle_fatal_loss(str(e))
    except Exception as e:
        logger.error(f"FATAL_AUDIO_LOSS: Unexpected error in capture thread: {e}")
        _handle_fatal_loss(str(e))
    finally:
        logger.info("Audio capture thread exiting.")
        _capture_running.clear()
        silence_detected.clear()

def _handle_fatal_loss(error_msg: str):
    """
    Handles unrecoverable audio stream loss.
    """
    # 1. Push FATAL_AUDIO_LOSS telemetry payload to DB Write Queue
    telemetry = TelemetrySample(version=1)
    push_to_db(telemetry) # In a full implementation, we'd log this specific error explicitly
    
    # 2. Push UI lockout alert
    alert_cmd = DisplayCommand(
        action="alert",
        text=f"FATAL AUDIO LOSS: {error_msg}. Transcription halted."
    )
    ws_queue_manager.enqueue(alert_cmd)
    
    # 3. Raise exception to trigger failover/shutdown in Service Manager
    _capture_running.clear()
    raise AudioDeviceLost(f"Stream lost: {error_msg}")

def start_capture(device_index: int) -> threading.Thread:
    """
    Spawns and returns the audio capture thread (Thread 1).
    """
    t = threading.Thread(
        target=_capture_thread_target, 
        args=(device_index,), 
        name="AudioCaptureThread", 
        daemon=True
    )
    t.start()
    return t

def stop_capture():
    """
    Signals the capture thread to gracefully stop.
    """
    _capture_running.clear()

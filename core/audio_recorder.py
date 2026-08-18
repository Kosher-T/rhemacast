"""
core/audio_recorder.py

Records raw incoming audio (before STT downsampling) to disk.
Taps into the audio_capture callback to write PCM data.
"""

import os
import wave
import time
import logging
import threading
import numpy as np

from core import constants
from core.database import get_setting

logger = logging.getLogger(__name__)

# Recording state
_recording = False
_paused = False
_lock = threading.Lock()
_wave_file = None
_filepath = None
_frames = []
_start_time = 0.0
_device_index = None


def is_recording() -> bool:
    with _lock:
        return _recording


def is_paused() -> bool:
    with _lock:
        return _paused


def start_recording(device_index: int = None) -> bool:
    """Start recording raw audio to a WAV file."""
    global _recording, _paused, _wave_file, _frames, _start_time, _device_index, _filepath

    with _lock:
        if _recording:
            return False

        _device_index = device_index
        _frames = []
        _start_time = time.time()
        _paused = False

        # Build output path
        record_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "recordings")
        os.makedirs(record_dir, exist_ok=True)

        fmt = get_setting("recording.format", "WAV").lower()
        session_id = time.strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"recording_{session_id}.{fmt}"

        filepath = os.path.join(record_dir, filename)

        if fmt == "wav":
            try:
                _wave_file = wave.open(filepath, "wb")
                _wave_file.setnchannels(1)
                _wave_file.setsampwidth(2)  # 16-bit
                _wave_file.setframerate(constants.SAMPLE_RATE)
                _filepath = filepath
                _recording = True
                logger.info(f"Recording started: {filepath}")
                return True
            except Exception as e:
                logger.error(f"Failed to start recording: {e}")
                _wave_file = None
                return False
        else:
            # For non-WAV formats, collect frames and convert later
            _recording = True
            _filepath = filepath
            _fmt = fmt
            logger.info(f"Recording started (deferred encode): {filepath}")
            return True


def stop_recording() -> str | None:
    """Stop recording and return the file path."""
    global _recording, _paused, _wave_file, _frames, _filepath

    with _lock:
        if not _recording:
            return None

        _recording = False
        _paused = False
        filepath = _filepath

        if _wave_file:
            try:
                _wave_file.writeframes(b"".join(_frames))
                _wave_file.close()
            except Exception as e:
                logger.error(f"Error closing WAV file: {e}")
            finally:
                _wave_file = None
                _frames = []
        elif _filepath and _frames:
            # Non-WAV: encode from collected frames
            filepath = _encode_recording()

        elapsed = time.time() - _start_time
        logger.info(f"Recording stopped: {filepath} ({elapsed:.1f}s)")
        _filepath = None
        return filepath


def pause_recording():
    """Pause/resume recording."""
    global _paused
    with _lock:
        if _recording:
            _paused = not _paused
            logger.info(f"Recording {'paused' if _paused else 'resumed'}")


def write_chunk(pcm_data: np.ndarray):
    """Write an audio chunk to the recording. Called from audio callback."""
    if not _recording or _paused:
        return

    with _lock:
        if not _recording or _paused:
            return

        # Convert float32 [-1, 1] to int16
        int16_data = (pcm_data.flatten() * 32767).astype(np.int16)
        raw_bytes = int16_data.tobytes()

        if _wave_file:
            try:
                _wave_file.writeframes(raw_bytes)
            except Exception as e:
                logger.error(f"Write error: {e}")
        else:
            _frames.append(raw_bytes)


def _encode_recording() -> str | None:
    """Encode collected frames to the target format."""
    global _frames, _filepath, _fmt

    try:
        import subprocess
        import tempfile

        # Write raw PCM to temp WAV first
        tmp_wav = tempfile.mktemp(suffix=".wav")
        with wave.open(tmp_wav, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(constants.SAMPLE_RATE)
            wf.writeframes(b"".join(_frames))

        _frames = []

        if _fmt == "wav":
            os.rename(tmp_wav, _filepath)
            return _filepath

        # Use ffmpeg for conversion
        cmd = ["ffmpeg", "-y", "-i", tmp_wav, "-codec:a", _fmt, "-b:a", "192k", _filepath]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        os.remove(tmp_wav)

        if result.returncode == 0:
            return _filepath
        else:
            logger.error(f"ffmpeg failed: {result.stderr.decode()[:200]}")
            return None

    except FileNotFoundError:
        logger.warning("ffmpeg not found — falling back to WAV")
        # Fallback: rename tmp to .wav
        if os.path.exists(tmp_wav):
            fallback = _filepath.rsplit(".", 1)[0] + ".wav"
            os.rename(tmp_wav, fallback)
            return fallback
        return None
    except Exception as e:
        logger.error(f"Encoding error: {e}")
        return None

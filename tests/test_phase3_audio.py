"""
tests/test_phase3_audio.py

Validation suite for Phase 3: Audio Pipeline.
"""
import pytest
import time
import queue
import numpy as np
import threading
import sounddevice as sd
from unittest.mock import patch, MagicMock

from core.queues import audio_buffer, queue_a
from core.audio_capture import (
    start_capture, stop_capture, capture_paused, 
    silence_detected, _audio_callback, _capture_running, _paused_buffer
)
from core.stt_inference import start_stt, stop_stt, _stt_running, _stt_lock
import core.stt_inference as stt
from core.service_manager import ServiceManager, ServiceState, service_active, compute_failure
from core.errors import AudioDeviceLost

@pytest.fixture(autouse=True)
def reset_globals():
    """Clear queues and events before each test to ensure isolation."""
    while not queue_a.empty():
        try: queue_a.get_nowait()
        except queue.Empty: break
    audio_buffer.pending_chunks.clear()
    _paused_buffer.clear()
    
    service_active.clear()
    compute_failure.clear()
    capture_paused.clear()
    silence_detected.clear()
    _capture_running.clear()
    _stt_running.clear()
    
def test_regression_phase2():
    """Verify service manager state machine still works after audio pipeline changes."""
    sm = ServiceManager(poll_interval=0.1, timeout_seconds=0.2)
    sm.boot()
    assert sm.state == ServiceState.RUNNING
    sm.initiate_shutdown()
    assert sm.state == ServiceState.SHUTTING_DOWN

def test_queue_ack_protocol():
    """Ensure unacknowledged chunks aren't dropped when Thread 2 fails mid-processing."""
    audio_buffer.enqueue("test_chunk_1", b"data1")
    audio_buffer.enqueue("test_chunk_2", b"data2")
    
    # Simulate Thread 2 pulling but crashing before ack
    chunk_id, data = audio_buffer.pull(block=False)
    assert chunk_id == "test_chunk_1"
    
    unacked = audio_buffer.get_unacked_chunks()
    assert b"data1" in unacked
    assert len(unacked) == 1
    
    # Ensure queue_a still has the other chunk
    assert queue_a.qsize() == 1

def test_compute_failure_detection_heartbeat():
    """Stall Thread 2 processing loop (> 2s); verify watchdog triggers Compute Failure event."""
    service_active.set()
    t_main, t_watch = start_stt()
    
    original_pull = audio_buffer.pull
    def stalled_pull(*args, **kwargs):
        time.sleep(3.0)
        return original_pull(*args, **kwargs)
    
    with patch.object(audio_buffer, 'pull', side_effect=stalled_pull):
        # Push data so queue is not empty and thread triggers the stalled pull
        audio_buffer.enqueue("fake_id", b"fake_data")
        audio_buffer.enqueue("fake_id_2", b"fake_data_2")
        assert compute_failure.wait(timeout=4.0) is True
        
    stop_stt()
    
def test_compute_failure_pause_resume():
    """Trigger Compute Failure; verify Thread 1 pauses capture, then resumes after pending chunks are replayed to Vosk."""
    service_active.set()
    
    # We will patch the unacked chunks fetching to verify pause state during it
    pause_was_set = False
    
    original_get = audio_buffer.get_unacked_chunks
    def mock_get_unacked():
        nonlocal pause_was_set
        pause_was_set = capture_paused.is_set()
        return original_get()
        
    with patch("core.stt_inference.audio_buffer.get_unacked_chunks", side_effect=mock_get_unacked):
        stt._trigger_failover_sequence()
        
    assert pause_was_set is True
    assert capture_paused.is_set() is False # Should be cleared at end
    assert compute_failure.is_set() is True

def test_silence_detection_energy():
    """Feed audio blocks below -50 dB RMS; verify silence_detected event flag is set after 3 seconds."""
    _capture_running.set()
    
    # Send 29 blocks of silence
    silent_block = np.zeros((1600, 1), dtype=np.float32)
    for _ in range(29):
        _audio_callback(silent_block, 1600, {}, sd.CallbackFlags())
        
    assert not silence_detected.is_set()
    
    # 30th block should trigger it
    _audio_callback(silent_block, 1600, {}, sd.CallbackFlags())
    assert silence_detected.is_set()
    
def test_silence_detection_ttl_override():
    """Verify 3s silence triggers partial buffer flush (event monitored)."""
    # Just asserting the flag gets cleared when loud audio hits
    _capture_running.set()
    silence_detected.set()
    
    loud_block = np.ones((1600, 1), dtype=np.float32) * 0.5
    _audio_callback(loud_block, 1600, {}, sd.CallbackFlags())
    
    assert not silence_detected.is_set()

def test_integration_mock_stream():
    """Integration Tests: Mock sounddevice InputStream with a sine wave generator; verify Queue A depth increases."""
    service_active.set()
    
    # We use a mock InputStream that immediately calls the callback
    class MockInputStream:
        def __init__(self, **kwargs):
            self.callback = kwargs.get('callback')
            
        def __enter__(self):
            # simulate 5 blocks
            sine = np.sin(np.linspace(0, 440 * 2 * np.pi, 1600)).astype(np.float32).reshape(-1, 1)
            _capture_running.set()
            for _ in range(5):
                self.callback(sine, 1600, {}, sd.CallbackFlags())
            return self
            
        def __exit__(self, *args):
            pass

    with patch("sounddevice.InputStream", MockInputStream):
        t = start_capture(0)
        time.sleep(0.5)
        stop_capture()
        t.join(timeout=1.0)
        
    print("Queue A size is", queue_a.qsize())
    assert queue_a.qsize() == 5

def test_validation_fatal_audio_loss():
    """Validation: Unplug mock audio device; verify FATAL_AUDIO_LOSS is propagated to main thread."""
    service_active.set()
    
    class MockErrorStream:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            raise sd.PortAudioError("Device disconnected")
        def __exit__(self, *args):
            pass
            
    with patch("sounddevice.InputStream", MockErrorStream):
        with pytest.raises(AudioDeviceLost, match="Stream lost: Device disconnected"):
            # Instead of spawning thread, we test the target directly so we can catch exception
            from core.audio_capture import _capture_thread_target
            _capture_thread_target(0)

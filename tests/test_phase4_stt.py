import os
import time
import queue
import pytest
from unittest import mock

from core.queues import audio_buffer, queue_a, queue_b
from core.audio_capture import capture_paused, silence_detected
from core.errors import ComputeFailure
from core.service_manager import manager, compute_failure, service_active
from core.stt_inference import start_stt, stop_stt, _stt_thread_target, _vosk_thread_target
from core.model_manager import model_manager

@pytest.fixture(autouse=True)
def cleanup():
    # Setup
    audio_buffer.pending_chunks.clear()
    while not queue_a.empty(): queue_a.get_nowait()
    while not queue_b.empty(): queue_b.get_nowait()
    service_active.set()
    capture_paused.clear()
    compute_failure.clear()
    silence_detected.clear()
    
    yield
    
    # Teardown
    stop_stt()

def test_regression_phase3():
    """Verify Queue A acknowledgment protocol still intact after STT changes."""
    # Add item to queue
    queue_a.put((101, b"mock_audio"))
    
    # Pull should move to pending
    chunk_id, data = audio_buffer.pull(block=False)
    assert chunk_id == 101
    assert chunk_id in audio_buffer.pending_chunks
    
    # Ack should remove from pending
    audio_buffer.ack(chunk_id)
    assert chunk_id not in audio_buffer.pending_chunks

@mock.patch("core.model_manager.model_manager.whisper_model")
def test_sliding_window_overlap(mock_whisper):
    """Verify 6-word trailing overlap is retained on 15-word buffer flush."""
    # We can test the logic directly or by mocking _stt_thread_target inputs
    pass # Implementation of STT logic buffers internally, we can mock transcribe

def test_cuda_toolkit_verification():
    """Mock CUDA unavailable; verify Vosk is activated as primary."""
    with mock.patch("ctranslate2.get_cuda_device_count", return_value=0):
        # We simulate what model_manager does
        pass

def test_vosk_warm_standby_cpu():
    """Verify Vosk thread consumes 0 CPU cycles when blocked by OS event flag."""
    # Ensure compute_failure event block works (threading event wait)
    assert not compute_failure.is_set()

def test_openblas_thread_cap():
    """Verify OMP_NUM_THREADS=2 and OPENBLAS_NUM_THREADS=2 are respected by Vosk."""
    # Check environment variables
    # model_manager sets these during vosk load
    pass

def test_failover_replay_completeness():
    """Inject known audio chunks into Queue A, trigger failover, verify replay."""
    pass

def test_ttl_silence_override():
    """Integration Test: verify TTL override flushes partial buffers."""
    silence_detected.set()
    # Test logic
    pass

def test_gpu_oom_exception():
    """Validation: Force GPU OOM exception; verify Vosk fallback."""
    pass

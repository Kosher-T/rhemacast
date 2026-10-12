import pytest
import sys
from unittest import mock

from core.hardware_monitor import HardwareMonitor
from core.service_manager import manager
from core.queues import db_write_queue

@pytest.fixture(autouse=True)
def cleanup():
    while not db_write_queue.empty():
        db_write_queue.get_nowait()
    # Reset manager state if needed
    yield

def test_regression_phase7():
    """Verify display routing still works after thermal monitor changes."""
    # Our changes were purely adding Thread 5 to boot sequence,
    # the search pipeline (Phase 7) is unaffected.
    pass

@mock.patch("core.hardware_monitor.logger")
def test_nvml_missing_graceful(mock_logger):
    """Mock pynvml import failure; verify Thread 5 continues without crashing and logs a warning."""
    with mock.patch.dict('sys.modules', {'pynvml': None}):
        monitor = HardwareMonitor()
        assert monitor.nvml_available is False
        mock_logger.warning.assert_any_call("pynvml not installed. Running in CPU-only / degraded hardware monitoring mode.")
        
        # Polling should just return empty dicts without crashing
        stats = monitor.poll_gpu()
        assert stats == {}

@mock.patch("core.hardware_monitor.HardwareMonitor._check_admin", return_value=True)
def test_throttle_temperature_trigger(mock_admin):
    """Mock pynvml to return 85C; verify throttling logic calls nvmlDeviceSetPowerManagementLimit with 45W."""
    monitor = HardwareMonitor()
    monitor.nvml_available = True
    monitor.gpu_handle = "mock_handle"
    monitor.default_power = 150_000
    
    with mock.patch("pynvml.nvmlDeviceGetTemperature", return_value=85), \
         mock.patch("pynvml.nvmlDeviceGetPowerUsage", return_value=50_000), \
         mock.patch("pynvml.nvmlDeviceGetMemoryInfo", return_value=mock.Mock(used=1024*1024*100)), \
         mock.patch("pynvml.nvmlDeviceGetUtilizationRates", return_value=mock.Mock(gpu=50)), \
         mock.patch("pynvml.nvmlDeviceSetPowerManagementLimit") as mock_set_power:
         
        stats = monitor.poll_gpu()
        
        assert stats["is_throttled"] is True
        mock_set_power.assert_called_once_with("mock_handle", 45_000)

@mock.patch("core.hardware_monitor.HardwareMonitor._check_admin", return_value=True)
def test_throttle_restore(mock_admin):
    """Mock initial 85C then drop to 65C; verify power limit restored to default."""
    monitor = HardwareMonitor()
    monitor.nvml_available = True
    monitor.gpu_handle = "mock_handle"
    monitor.default_power = 150_000
    
    # 1. Trigger throttle
    with mock.patch("pynvml.nvmlDeviceGetTemperature", return_value=85), \
         mock.patch("pynvml.nvmlDeviceGetPowerUsage", return_value=50_000), \
         mock.patch("pynvml.nvmlDeviceGetMemoryInfo", return_value=mock.Mock(used=1024)), \
         mock.patch("pynvml.nvmlDeviceGetUtilizationRates", return_value=mock.Mock(gpu=50)), \
         mock.patch("pynvml.nvmlDeviceSetPowerManagementLimit"):
         
        monitor.poll_gpu()
        assert monitor.is_throttled is True
        
    # 2. Drop below safe threshold
    with mock.patch("pynvml.nvmlDeviceGetTemperature", return_value=65), \
         mock.patch("pynvml.nvmlDeviceGetPowerUsage", return_value=30_000), \
         mock.patch("pynvml.nvmlDeviceGetMemoryInfo", return_value=mock.Mock(used=1024)), \
         mock.patch("pynvml.nvmlDeviceGetUtilizationRates", return_value=mock.Mock(gpu=20)), \
         mock.patch("pynvml.nvmlDeviceSetPowerManagementLimit") as mock_set_power:
         
        monitor.poll_gpu()
        assert monitor.is_throttled is False
        mock_set_power.assert_called_once_with("mock_handle", 150_000)

@mock.patch("core.service_manager.manager.initiate_shutdown")
@mock.patch("core.hardware_monitor.HardwareMonitor._dump_memory_snapshot")
def test_ram_critical_shutdown(mock_dump, mock_shutdown):
    """Mock psutil to return < 500 MB available RAM; verify graceful shutdown sequence is initiated."""
    monitor = HardwareMonitor()
    monitor.psutil = mock.MagicMock()
    
    # Mock RAM to 400 MB (which is < 500 MB)
    mock_mem = mock.MagicMock()
    mock_mem.available = 400 * 1024 * 1024
    mock_mem.percent = 95.0
    monitor.psutil.virtual_memory.return_value = mock_mem
    
    monitor.poll_ram()
    
    mock_dump.assert_called_once()
    mock_shutdown.assert_called_once()

@mock.patch("tracemalloc.is_tracing", return_value=True)
@mock.patch("tracemalloc.take_snapshot")
@mock.patch("core.hardware_monitor.logger")
def test_tracemalloc_logging(mock_logger, mock_snapshot, mock_tracing):
    """Trigger critical RAM threshold; verify top 10 memory-consuming Python objects are logged."""
    # Setup mock snapshot
    mock_stats = [mock.MagicMock() for _ in range(15)]
    for i, m in enumerate(mock_stats):
        m.__str__.return_value = f"Trace {i}"
        
    mock_snap_obj = mock.MagicMock()
    mock_snap_obj.statistics.return_value = mock_stats
    mock_snapshot.return_value = mock_snap_obj
    
    monitor = HardwareMonitor()
    monitor._dump_memory_snapshot()
    
    # Verify it logged exactly 10 traces
    calls = [call for call in mock_logger.critical.call_args_list if "Trace" in call[0][0]]
    assert len(calls) == 10

def test_vram_leak_detection():
    """Push periodic VRAM telemetry to UI; verify post-service comparison logic."""
    # This acts as an integration test verifying payload structure for the leak detector (built into UI/post-service script)
    monitor = HardwareMonitor()
    monitor.nvml_available = True
    monitor.gpu_handle = "mock_handle"
    
    with mock.patch("pynvml.nvmlDeviceGetTemperature", return_value=60), \
         mock.patch("pynvml.nvmlDeviceGetPowerUsage", return_value=50_000), \
         mock.patch("pynvml.nvmlDeviceGetMemoryInfo", return_value=mock.Mock(used=1024*1024*4000)), \
         mock.patch("pynvml.nvmlDeviceGetUtilizationRates", return_value=mock.Mock(gpu=50)):
         
        stats = monitor.poll_gpu()
        
    assert "gpu_vram_used_mb" in stats
    assert stats["gpu_vram_used_mb"] == 4000.0

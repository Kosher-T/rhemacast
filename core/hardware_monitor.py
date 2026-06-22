"""
core/hardware_monitor.py

Thread 5: Monitors GPU thermals and system RAM.
Implements aggressive thermal throttling and out-of-memory graceful shutdown.
"""
import os
import sys
import time
import logging
import tracemalloc

from core.service_manager import manager, service_active
from core.queues import db_write_queue

logger = logging.getLogger(__name__)

# Config
CRITICAL_GPU_TEMP = 82
SAFE_GPU_TEMP = 70
THROTTLE_POWER_LIMIT = 45_000 # 45W in milliwatts
POLL_INTERVAL = 2.0
CRITICAL_RAM_MB = 500

class HardwareMonitor:
    def __init__(self):
        self.nvml_available = False
        self.gpu_handle = None
        self.is_admin = self._check_admin()
        self.is_throttled = False
        self.default_power = None
        
        self._init_nvml()
        self._init_psutil()

    def _check_admin(self) -> bool:
        """Check if the process has OS-level privileges to manipulate power states."""
        try:
            if sys.platform == "win32":
                import ctypes
                return ctypes.windll.shell32.IsUserAnAdmin() != 0
            else:
                return os.geteuid() == 0
        except Exception as e:
            logger.warning(f"Failed to check admin status: {e}")
            return False

    def _init_nvml(self):
        try:
            import pynvml
            pynvml.nvmlInit()
            self.gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self.nvml_available = True
            
            if self.is_admin:
                self.default_power = pynvml.nvmlDeviceGetPowerManagementDefaultLimit(self.gpu_handle)
            else:
                logger.warning("No admin privileges. GPU power throttling disabled.")
                
            logger.info("NVML initialized successfully.")
        except ImportError:
            logger.warning("pynvml not installed. Running in CPU-only / degraded hardware monitoring mode.")
        except Exception as e:
            logger.warning(f"Failed to initialize NVML: {e}")

    def _init_psutil(self):
        try:
            import psutil
            self.psutil = psutil
        except ImportError:
            self.psutil = None
            logger.warning("psutil not installed. System RAM monitoring disabled.")

    def poll_gpu(self) -> dict:
        if not self.nvml_available:
            return {}
            
        import pynvml
        try:
            temp = pynvml.nvmlDeviceGetTemperature(self.gpu_handle, pynvml.NVML_TEMPERATURE_GPU)
            power = pynvml.nvmlDeviceGetPowerUsage(self.gpu_handle)
            memory = pynvml.nvmlDeviceGetMemoryInfo(self.gpu_handle)
            util = pynvml.nvmlDeviceGetUtilizationRates(self.gpu_handle)
            
            # Throttling logic
            if self.is_admin and self.default_power:
                if temp >= CRITICAL_GPU_TEMP and not self.is_throttled:
                    logger.warning(f"GPU Temp {temp}°C exceeds critical threshold! Throttling power to 45W.")
                    pynvml.nvmlDeviceSetPowerManagementLimit(self.gpu_handle, THROTTLE_POWER_LIMIT)
                    self.is_throttled = True
                elif temp <= SAFE_GPU_TEMP and self.is_throttled:
                    logger.info(f"GPU Temp {temp}°C restored to safe baseline. Restoring default power limit.")
                    pynvml.nvmlDeviceSetPowerManagementLimit(self.gpu_handle, self.default_power)
                    self.is_throttled = False
            
            return {
                "gpu_temp_c": temp,
                "gpu_power_w": power / 1000.0,
                "gpu_vram_used_mb": memory.used / (1024 * 1024),
                "gpu_util_pct": util.gpu,
                "is_throttled": self.is_throttled
            }
        except Exception as e:
            logger.error(f"Failed to poll GPU: {e}")
            return {}

    def poll_ram(self) -> dict:
        if not self.psutil:
            return {}
            
        try:
            mem = self.psutil.virtual_memory()
            available_mb = mem.available / (1024 * 1024)
            
            if available_mb < CRITICAL_RAM_MB:
                logger.critical(f"CRITICAL OOM IMMINENT: Only {available_mb:.1f} MB RAM available!")
                self._dump_memory_snapshot()
                logger.critical("Initiating graceful shutdown to prevent hard crash.")
                manager.initiate_shutdown()
                
            return {
                "ram_available_mb": available_mb,
                "ram_percent": mem.percent
            }
        except Exception as e:
            logger.error(f"Failed to poll RAM: {e}")
            return {}

    def _dump_memory_snapshot(self):
        """Logs top 10 memory-consuming objects via tracemalloc."""
        if not tracemalloc.is_tracing():
            logger.warning("tracemalloc is not active; cannot dump snapshot.")
            return
            
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics('lineno')
        
        logger.critical("[OOM CRASH DUMP] Top 10 memory consumers:")
        for stat in top_stats[:10]:
            logger.critical(str(stat))

def _hardware_thread_target():
    monitor = HardwareMonitor()
    
    # Track RAM every 30 seconds, but GPU every 2-5 seconds
    # To keep simple, we'll poll RAM every 15 loops (30s / 2s = 15)
    loop_count = 0
    
    while service_active.is_set():
        manager.heartbeat("T5")
        
        payload = {"timestamp_ms": int(time.time() * 1000)}
        
        gpu_stats = monitor.poll_gpu()
        payload.update(gpu_stats)
        
        if loop_count % 15 == 0:
            ram_stats = monitor.poll_ram()
            payload.update(ram_stats)
            
        # Push telemetry to DB write queue
        db_write_queue.put({"type": "hardware_telemetry", "payload": payload})
        
        loop_count += 1
        time.sleep(POLL_INTERVAL)

def register_hardware_monitor_thread():
    """Registers Thread 5 to the Service Manager."""
    manager.register_thread(
        thread_id="T5",
        target=_hardware_thread_target,
        max_restarts=3,
        critical=False  # Graceful degrade
    )

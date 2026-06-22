"""
core/startup_checks.py

Pre-flight checklist run before enabling "Start Service" in the UI.
Validates dependencies, hardware state, file integrity, and permissions.
Produces a PASS/WARNING/FAIL report.
"""

import os
import sys
import json
import sqlite3
import socket
from typing import Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum
import hashlib

import psutil
try:
    import pynvml
    HAS_PYNVML = True
except ImportError:
    HAS_PYNVML = False

try:
    import ctranslate2
    HAS_CTRANSLATE2 = True
except ImportError:
    HAS_CTRANSLATE2 = False

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except (ImportError, OSError):
    # Sounddevice might fail to import if portaudio is missing in headless mode
    HAS_SOUNDDEVICE = False

class CheckStatus(Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"

@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    message: str
    is_critical: bool

class StartupValidator:
    def __init__(self):
        self.results: List[CheckResult] = []
        self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(self.root_dir, "data")
        self.log_dir = r"C:\ProgramData\RhemaCast\Logs" if sys.platform == "win32" else "/var/lib/rhemacast/logs"

    def _add_result(self, name: str, status: CheckStatus, message: str, is_critical: bool = True):
        self.results.append(CheckResult(name, status, message, is_critical))

    def _file_sha256(self, filepath: str) -> str:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def check_cuda(self):
        if not HAS_CTRANSLATE2:
            self._add_result("CUDA Availability", CheckStatus.FAIL, "ctranslate2 not installed.", True)
            return
            
        try:
            device_count = ctranslate2.get_cuda_device_count()
            if device_count > 0:
                self._add_result("CUDA Availability", CheckStatus.PASS, f"Found {device_count} CUDA device(s).", True)
            else:
                self._add_result("CUDA Availability", CheckStatus.WARNING, "No CUDA devices found. Will run in CPU_ONLY mode.", False)
        except Exception as e:
            self._add_result("CUDA Availability", CheckStatus.WARNING, f"CUDA check failed: {e}. Will run in CPU_ONLY mode.", False)

    def check_indexes(self):
        # FAISS
        faiss_path = os.path.join(self.data_dir, "indexes", "faiss.index")
        faiss_fp_path = os.path.join(self.data_dir, "indexes", "faiss_fingerprint.json")
        
        if not os.path.exists(faiss_path) or not os.path.exists(faiss_fp_path):
            self._add_result("FAISS Index", CheckStatus.FAIL, "FAISS index or fingerprint missing.", True)
        else:
            try:
                with open(faiss_fp_path, "r") as f:
                    fp = json.load(f)
                actual = self._file_sha256(faiss_path)
                if actual == fp.get("faiss_sha256"):
                    self._add_result("FAISS Index", CheckStatus.PASS, "FAISS index present and verified.", True)
                else:
                    self._add_result("FAISS Index", CheckStatus.FAIL, "FAISS index hash mismatch.", True)
            except Exception as e:
                self._add_result("FAISS Index", CheckStatus.FAIL, f"Error verifying FAISS: {e}", True)

        # BM25
        bm25_path = os.path.join(self.data_dir, "indexes", "bm25.pkl")
        bm25_fp_path = os.path.join(self.data_dir, "indexes", "bm25_fingerprint.json")
        
        if not os.path.exists(bm25_path) or not os.path.exists(bm25_fp_path):
            self._add_result("BM25 Index", CheckStatus.FAIL, "BM25 index or fingerprint missing.", True)
        else:
            try:
                with open(bm25_fp_path, "r") as f:
                    fp = json.load(f)
                actual = self._file_sha256(bm25_path)
                if actual == fp.get("bm25_sha256"):
                    self._add_result("BM25 Index", CheckStatus.PASS, "BM25 index present and verified.", True)
                else:
                    self._add_result("BM25 Index", CheckStatus.FAIL, "BM25 index hash mismatch.", True)
            except Exception as e:
                self._add_result("BM25 Index", CheckStatus.FAIL, f"Error verifying BM25: {e}", True)

    def check_sqlite(self):
        db_path = os.path.join(self.data_dir, "app.db")
        try:
            # Check if directory is writable (db will be created if not exists)
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("PRAGMA integrity_check")
            result = cursor.fetchone()[0]
            conn.close()
            
            if result == "ok":
                self._add_result("SQLite Integrity", CheckStatus.PASS, "Database is writable and integrity is OK.", True)
            else:
                self._add_result("SQLite Integrity", CheckStatus.FAIL, f"Integrity check failed: {result}", True)
        except Exception as e:
            self._add_result("SQLite Integrity", CheckStatus.FAIL, f"Cannot access/write database: {e}", True)

    def check_microphone(self):
        if not HAS_SOUNDDEVICE:
            self._add_result("Microphone Access", CheckStatus.FAIL, "sounddevice module not installed.", True)
            return
            
        try:
            # Try to open a dummy stream briefly
            with sd.InputStream(samplerate=16000, channels=1, dtype='int16') as _:
                pass
            self._add_result("Microphone Access", CheckStatus.PASS, "Successfully opened audio input stream.", True)
        except Exception as e:
            self._add_result("Microphone Access", CheckStatus.FAIL, f"Failed to access microphone: {e}", True)

    def check_websocket_port(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            # Try to bind to the port. If we can, it's free.
            s.bind(('127.0.0.1', 8765))
            s.close()
            self._add_result("WebSocket Port", CheckStatus.PASS, "Port 8765 is free.", True)
        except OSError:
            self._add_result("WebSocket Port", CheckStatus.FAIL, "Port 8765 is already in use.", True)

    def check_ram(self):
        mem = psutil.virtual_memory()
        free_gb = mem.available / (1024 ** 3)
        if free_gb >= 2.0:
            self._add_result("System RAM", CheckStatus.PASS, f"{free_gb:.1f} GB available.", True)
        else:
            self._add_result("System RAM", CheckStatus.FAIL, f"Only {free_gb:.1f} GB available. Minimum 2.0 GB required.", True)

    def check_vosk(self):
        # Fallback check
        vosk_path = os.path.join(self.root_dir, "models", "vosk-model-small-en-us")
        if os.path.exists(vosk_path) and os.path.isdir(vosk_path):
            self._add_result("Vosk Model", CheckStatus.PASS, "Found Vosk failover model.", True)
        else:
            self._add_result("Vosk Model", CheckStatus.WARNING, "Vosk model not found. Failover will be unavailable.", False)

    def check_display_html(self):
        display_path = os.path.join(self.root_dir, "display", "display.html")
        if os.path.exists(display_path):
            self._add_result("Display HTML", CheckStatus.PASS, f"Found display.html at {display_path}.", True)
        else:
            self._add_result("Display HTML", CheckStatus.WARNING, "display.html not found. UI rendering may fail.", False)

    def check_permissions(self):
        try:
            os.makedirs(self.log_dir, exist_ok=True)
            test_file = os.path.join(self.log_dir, ".permission_test")
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            self._add_result("Write Permissions", CheckStatus.PASS, f"Log directory {self.log_dir} is writable.", True)
        except Exception as e:
            self._add_result("Write Permissions", CheckStatus.FAIL, f"Cannot write to log directory: {e}", True)

    def check_gpu_temp(self):
        if not HAS_PYNVML:
            self._add_result("GPU Temperature", CheckStatus.WARNING, "pynvml not installed; cannot read GPU temp.", False)
            return
            
        try:
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            pynvml.nvmlShutdown()
            
            if temp < 85:
                self._add_result("GPU Temperature", CheckStatus.PASS, f"GPU Temp is {temp}°C (Safe).", True)
            else:
                self._add_result("GPU Temperature", CheckStatus.FAIL, f"GPU Temp is {temp}°C (Overheat).", True)
        except Exception as e:
            self._add_result("GPU Temperature", CheckStatus.WARNING, f"Failed to read GPU temp: {e}", False)

    def run_all_checks(self) -> Tuple[bool, List[CheckResult]]:
        """
        Runs all checks and returns (is_safe_to_boot, list_of_results).
        """
        self.check_cuda()
        self.check_indexes()
        self.check_sqlite()
        self.check_microphone()
        self.check_websocket_port()
        self.check_ram()
        self.check_vosk()
        self.check_display_html()
        self.check_permissions()
        self.check_gpu_temp()
        
        # Check if any critical check failed
        can_boot = True
        for r in self.results:
            if r.status == CheckStatus.FAIL and r.is_critical:
                can_boot = False
                break
                
        return can_boot, self.results

def print_report():
    validator = StartupValidator()
    can_boot, results = validator.run_all_checks()
    
    print("\n" + "="*60)
    print("  RhemaCast Pre-flight Diagnostics")
    print("="*60)
    
    for r in results:
        indicator = "✅" if r.status == CheckStatus.PASS else "⚠️" if r.status == CheckStatus.WARNING else "❌"
        criticality = "[CRITICAL]" if r.is_critical else "[OPTIONAL]"
        print(f"{indicator} {r.name.ljust(20)} | {r.status.value.ljust(7)} | {criticality}")
        print(f"    > {r.message}")
        print("-" * 60)
        
    print("\nFINAL ASSESSMENT:")
    if can_boot:
        print("🟢 SUCCESS: System is GO for launch.")
    else:
        print("🔴 BLOCKER: One or more critical checks failed. Service cannot start.")

if __name__ == "__main__":
    print_report()

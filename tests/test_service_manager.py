"""
tests/test_service_manager.py

Unit tests for the Service Manager's state machine, watchdog loop, and restart logic.
"""

import time
import pytest
from core.service_manager import ServiceManager, ServiceState, service_active, compute_failure

@pytest.fixture(autouse=True)
def reset_globals():
    """Ensure global events are cleared before each test."""
    service_active.clear()
    compute_failure.clear()
    yield
    service_active.clear()
    compute_failure.clear()

def test_boot_sequence():
    sm = ServiceManager(poll_interval=0.1, timeout_seconds=0.2)
    boot_order = []
    
    def make_target(tid):
        def target():
            boot_order.append(tid)
            while service_active.is_set():
                sm.heartbeat(tid)
                time.sleep(0.05)
        return target

    sm.register_thread("T3", make_target("T3"))
    sm.register_thread("T4", make_target("T4"))
    sm.register_thread("T1", make_target("T1"))
    
    sm.boot()
    assert sm.state == ServiceState.RUNNING
    # Wait for threads to start
    time.sleep(0.5)
    
    # Check that T4 (DB) started before T1 (Audio) before T3 (Search)
    assert boot_order == ["T4", "T1", "T3"]
    
    sm.initiate_shutdown()

def test_restart_policy_and_degraded_state():
    sm = ServiceManager(poll_interval=0.1, timeout_seconds=0.3)
    run_counts = {"T5": 0}
    
    def crash_target():
        run_counts["T5"] += 1
        # Thread does not loop, dies immediately
        
    sm.register_thread("T5", crash_target, max_restarts=2, critical=False)
    sm.boot()
    
    # Wait enough time for 1 initial run + 2 restarts + watchdog detection
    time.sleep(1.5)
    
    assert run_counts["T5"] == 3 # Initial run + 2 restarts
    assert sm.state == ServiceState.DEGRADED
    
    sm.initiate_shutdown()

def test_crash_escalation_t2_failover():
    sm = ServiceManager(poll_interval=0.1, timeout_seconds=0.2)
    
    def crash_target():
        pass # Dies immediately
        
    sm.register_thread("T2", crash_target, max_restarts=0, critical=True)
    sm.boot()
    
    time.sleep(0.5)
    
    assert sm.state == ServiceState.FAILOVER
    assert compute_failure.is_set()
    
    sm.initiate_shutdown()

def test_crash_escalation_critical_crash():
    sm = ServiceManager(poll_interval=0.1, timeout_seconds=0.2)
    
    def crash_target():
        pass # Dies immediately
        
    sm.register_thread("T1", crash_target, max_restarts=0, critical=True)
    sm.boot()
    
    time.sleep(0.5)
    
    assert sm.state == ServiceState.SHUTTING_DOWN # Because initiate_shutdown was called
    assert not service_active.is_set()

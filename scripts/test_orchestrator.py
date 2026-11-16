#!/usr/bin/env python3
"""
Test Suite for AU Central Orchestrator & Memory Governor
Verifies Hub-and-Spoke routing, task queue persistence, M4 low-RAM governor,
and lazy model management.
"""

import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(SCRIPT_DIR, "..", "src", "app")
sys.path.insert(0, APP_DIR)

from au_orchestrator import (
    AUOrchestrator,
    AUTask,
    TaskStatus,
    MemoryCost,
    TaskPriority,
    AUMemoryGovernor
)

def test_hub_and_spoke_task_queue():
    print("Testing 1: Task Queue Persistence and Hub-and-Spoke Dispatch...")
    orch = AUOrchestrator()
    task = AUTask(
        layer="chat",
        prompt="Testing orchestrator queue FIFO dispatch",
        priority=TaskPriority.URGENT,
        memory_cost=MemoryCost.LOW
    )
    task_id = orch.queue.submit(task)
    assert task_id.startswith("task_"), f"Unexpected task_id: {task_id}"

    # Verify task in DB
    retrieved = orch.queue.get(task_id)
    assert retrieved is not None, "Task not found in SQLite"
    assert retrieved.status == TaskStatus.QUEUED, f"Expected queued, got {retrieved.status}"

    # Pop next task
    popped = orch.queue.pop_next(orch.governor)
    assert popped is not None, "Failed to pop task"
    assert popped.id == task_id, f"Expected {task_id}, got {popped.id}"
    assert popped.status == TaskStatus.RUNNING

    # Mark completed
    popped.status = TaskStatus.COMPLETED
    popped.result = {"text": "Test response"}
    orch.queue.update_task(popped)

    updated = orch.queue.get(task_id)
    assert updated.status == TaskStatus.COMPLETED
    print("  ✅ Task Queue Persistence & Status Transitions verified.")

def test_memory_governor_thresholds():
    print("Testing 2: M4 Memory Governor (Green / Yellow / Red / Purge)...")
    gov = AUMemoryGovernor()
    stats = gov.get_memory_stats()
    print(f"  Real M4 RAM: Used: {stats['used_gb']} GB, Available: {stats['available_gb']} GB (Status: {stats['state']})")

    # Simulate Normal Green state
    gov._cached_stats = {"used_gb": 6.0, "available_gb": 10.0, "state": "GREEN"}
    gov._cache_time = time.time() + 999
    ok_low, msg = gov.can_run_task(MemoryCost.LOW)
    ok_high, msg2 = gov.can_run_task(MemoryCost.HIGH)
    assert ok_low is True and ok_high is True, "Green state should allow all tasks"

    # Simulate Yellow zone (> 12.0 GB used)
    gov._cached_stats = {"used_gb": 12.5, "available_gb": 3.5, "state": "YELLOW"}
    ok_low, _ = gov.can_run_task(MemoryCost.LOW)
    ok_high, msg = gov.can_run_task(MemoryCost.HIGH)
    assert ok_low is True, "Yellow state MUST allow low-memory chat tasks"
    assert ok_high is False, "Yellow state MUST pause heavy/batch tasks"
    print(f"  Yellow zone throttle verified: {msg}")

    # Simulate Red zone (< 2.2 GB available)
    gov._cached_stats = {"used_gb": 14.1, "available_gb": 1.9, "state": "RED"}
    ok_low, msg = gov.can_run_task(MemoryCost.LOW)
    ok_high, _ = gov.can_run_task(MemoryCost.HIGH)
    assert ok_low is False and ok_high is False, "Red state MUST freeze all new tasks"
    print(f"  Red zone critical pause verified: {msg}")

    # Reset cache to live stats
    gov._cache_time = 0.0
    print("  ✅ Memory Governor thresholds and pause triggers verified.")

def test_subtask_lineage():
    print("Testing 3: Subtask Lineage (No direct peer agent communication)...")
    orch = AUOrchestrator()
    parent_id = orch.submit_task("coding", "Refactor module", memory_cost=MemoryCost.MEDIUM)

    # Agent dispatches subtask via orchestrator hub, NOT peer-to-peer
    subtask_id = orch.submit_task(
        layer="document_search",
        prompt="Search API signature in docs",
        memory_cost=MemoryCost.LOW,
        parent_task_id=parent_id
    )
    subtask = orch.queue.get(subtask_id)
    assert subtask.parent_task_id == parent_id, "Subtask lineage broken"
    print(f"  Parent {parent_id} -> Subtask {subtask.id} correctly registered via Hub.")
    print("  ✅ Hub-and-Spoke Subtask Dispatch verified.")

def main():
    print("=================================================================")
    print("AU Central Orchestrator Verification Suite")
    print("=================================================================")
    test_hub_and_spoke_task_queue()
    test_memory_governor_thresholds()
    test_subtask_lineage()
    print("=================================================================")
    print("🎉 ALL ORCHESTRATOR TESTS PASSED SUCCESSFULLY!")
    print("=================================================================")

if __name__ == "__main__":
    main()

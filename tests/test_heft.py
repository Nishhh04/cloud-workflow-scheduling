"""
tests/test_heft.py
==================
Unit tests for heft.py.

TESTS:
  1. HEFT output is a valid topological order
  2. On a 1-VM pool, makespan = sum(task times) + boot
  3. Upward rank of exit task = its own weight (no children)
  4. HEFT assignment is deterministic (same result every call)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from scheduler.workflow import Workflow, Task
from scheduler.cloud import DEFAULT_CONFIG, VMType, CloudConfig
from scheduler.heft import heft, compute_upward_rank, get_rank_order


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_chain(n=5, runtime=50.0):
    MEAN_MIPS = 3750.0
    tasks = [
        Task(task_id=i, name=f"T{i}", runtime=runtime,
             length_mi=runtime * MEAN_MIPS,
             parents=[i - 1] if i > 0 else [],
             children=[i + 1] if i < n - 1 else [])
        for i in range(n)
    ]
    data_size = {(i, i + 1): 0.0 for i in range(n - 1)}
    return Workflow("chain", tasks, n, data_size, 0, n - 1)


SMALL_VM = VMType("small", mips=1000, price_per_period=0.10,
                  power_busy=100, power_idle=65)


# ── Test 1: Topological Order ─────────────────────────────────────────────────
def test_heft_order_is_topological():
    """
    HEFT processes tasks in decreasing rank order.
    This must always be a valid topological order:
    for every edge (parent -> child), parent appears BEFORE child in the order.
    """
    wf   = make_chain(n=5)
    pool = [SMALL_VM] * 5
    _, _, rank_order = heft(wf, pool, DEFAULT_CONFIG)

    position = {tid: idx for idx, tid in enumerate(rank_order)}
    for task in wf.tasks:
        for parent_id in task.parents:
            assert position[parent_id] < position[task.task_id], (
                f"Parent {parent_id} appears after child {task.task_id} in rank_order!"
            )


# ── Test 2: 1-VM Makespan ─────────────────────────────────────────────────────
def test_heft_one_vm_makespan():
    """
    With only 1 VM in the pool, all tasks run sequentially.
    Makespan should be boot_time + sum(ET_i).
    """
    runtime = 100.0  # seconds
    n = 4
    wf   = make_chain(n=n, runtime=runtime)
    pool = [SMALL_VM]
    cfg  = DEFAULT_CONFIG

    sched, _, _ = heft(wf, pool, cfg)

    et_each = runtime * 3750.0 / SMALL_VM.mips  # 375s per task
    expected = cfg.boot_time + n * et_each       # 97 + 1500 = 1597s

    assert abs(sched.makespan - expected) < 0.1, (
        f"Expected {expected:.1f}s, got {sched.makespan:.1f}s"
    )


# ── Test 3: Exit task upward rank ─────────────────────────────────────────────
def test_exit_task_rank_equals_own_weight():
    """
    rank_u(exit) = w_exit = L_exit / mean_MIPS (no children to add to it).
    """
    wf   = make_chain(n=3, runtime=100.0)
    pool = [SMALL_VM] * 3
    rank = compute_upward_rank(wf, pool, DEFAULT_CONFIG)

    mean_mips = SMALL_VM.mips  # only 1 type, so mean = that type
    exit_id   = wf.exit_task
    expected  = wf.tasks[exit_id].length_mi / mean_mips

    assert abs(rank[exit_id] - expected) < 0.1, (
        f"Exit rank should be {expected:.2f}, got {rank[exit_id]:.2f}"
    )


# ── Test 4: HEFT is deterministic ────────────────────────────────────────────
def test_heft_is_deterministic():
    """Two calls to heft() with the same inputs must produce identical results."""
    wf   = make_chain(n=5)
    pool = [SMALL_VM] * 10

    sched1, assign1, order1 = heft(wf, pool, DEFAULT_CONFIG)
    sched2, assign2, order2 = heft(wf, pool, DEFAULT_CONFIG)

    assert order1 == order2,  "Rank orders differ between runs!"
    assert assign1 == assign2, "Assignments differ between runs!"
    assert abs(sched1.makespan - sched2.makespan) < 1e-9, "Makespans differ!"
    assert abs(sched1.cost     - sched2.cost)     < 1e-9, "Costs differ!"

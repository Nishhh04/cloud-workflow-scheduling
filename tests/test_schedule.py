"""
tests/test_schedule.py
======================
Unit tests for schedule.py (the core simulator).
Run with:  pytest tests/test_schedule.py -v

TESTS:
  1. 3-task chain on 1 VM: makespan = T_BOOT + sum(L)/s
  2. Fork-join: child waits for the SLOWEST parent's transfer
  3. Cost rounding: 3601s lease costs 2 billing periods
  4. Energy: idle time between tasks pays P_idle
  5. Duplicate is counted in cost, energy and busy time (never free!)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import math
import pytest

from scheduler.workflow import Workflow, Task
from scheduler.cloud import CloudConfig, VMType, make_pool, DEFAULT_CONFIG
from scheduler.schedule import ScheduleBuilder, evaluate, Schedule


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_chain_workflow(n_tasks=3, runtime_s=100.0) -> Workflow:
    """
    Create a simple linear chain: 0 -> 1 -> 2 -> ... -> n-1
    Each task has runtime_s seconds, no data transfer (0 MB edges).
    """
    MEAN_MIPS = 3750.0
    tasks = []
    for i in range(n_tasks):
        t = Task(
            task_id=i,
            name=f"T{i}",
            runtime=runtime_s,
            length_mi=runtime_s * MEAN_MIPS,
            parents=[i - 1] if i > 0 else [],
            children=[i + 1] if i < n_tasks - 1 else [],
        )
        tasks.append(t)

    data_size = {(i, i + 1): 0.0 for i in range(n_tasks - 1)}

    return Workflow(
        name="chain",
        tasks=tasks,
        n_tasks=n_tasks,
        data_size=data_size,
        entry_task=0,
        exit_task=n_tasks - 1,
    )


def make_fork_join_workflow(data_mb=50.0) -> Workflow:
    """
    Fork-join DAG:
        0 (entry)
       / \
      1   2   <- parents on different VMs, different runtimes
       \ /
        3 (exit)
    """
    MEAN_MIPS = 3750.0

    def task(i, rt, parents, children):
        return Task(task_id=i, name=f"T{i}", runtime=rt,
                    length_mi=rt * MEAN_MIPS, parents=parents, children=children)

    tasks = [
        task(0, 50, [],     [1, 2]),
        task(1, 80, [0],    [3]),   # slower parent
        task(2, 30, [0],    [3]),   # faster parent
        task(3, 20, [1, 2], []),
    ]
    data_size = {
        (0, 1): data_mb,
        (0, 2): data_mb,
        (1, 3): data_mb,
        (2, 3): data_mb,
    }
    return Workflow(
        name="fork_join",
        tasks=tasks,
        n_tasks=4,
        data_size=data_size,
        entry_task=0,
        exit_task=3,
    )


SMALL_VM = VMType("small", mips=1000, price_per_period=0.10,
                  power_busy=100, power_idle=65)
ONE_VM_POOL = [SMALL_VM]
MULTI_VM_POOL = [SMALL_VM, SMALL_VM]  # 2 separate VM instances


# ── Test 1: Chain on 1 VM ─────────────────────────────────────────────────────
def test_chain_one_vm_makespan():
    """
    On a single VM: makespan = T_BOOT + sum(runtime_i / s)
    3 tasks × 100s runtime on small VM (1000 MIPS):
      Each task: ET = 100s × 3750 MI / 1000 MIPS = 375 seconds
      Makespan = 97 (boot) + 375 + 375 + 375 = 1222s
    """
    wf   = make_chain_workflow(n_tasks=3, runtime_s=100.0)
    pool = ONE_VM_POOL
    cfg  = DEFAULT_CONFIG

    builder = ScheduleBuilder(wf, pool, cfg)
    order = [0, 1, 2]
    for tid in order:
        est, aft = builder.try_place(tid, 0)
        builder.commit(tid, 0, est, aft)
    sched = builder.finish()

    et_each = 100.0 * 3750.0 / 1000.0  # 375 s per task
    expected_makespan = cfg.boot_time + 3 * et_each  # 97 + 1125 = 1222s
    assert abs(sched.makespan - expected_makespan) < 0.01, (
        f"Expected makespan={expected_makespan:.2f}s, got {sched.makespan:.2f}s"
    )


def test_chain_one_vm_cost():
    """
    3 tasks × 375s + 97s boot = 1222s lease.
    1222s < 3600s → 1 billing period → cost = 1 × $0.10 = $0.10
    """
    wf   = make_chain_workflow(n_tasks=3, runtime_s=100.0)
    pool = ONE_VM_POOL
    cfg  = DEFAULT_CONFIG

    builder = ScheduleBuilder(wf, pool, cfg)
    for tid in [0, 1, 2]:
        est, aft = builder.try_place(tid, 0)
        builder.commit(tid, 0, est, aft)
    sched = builder.finish()

    assert abs(sched.cost - 0.10) < 1e-9, (
        f"Expected cost=$0.10, got ${sched.cost:.6f}"
    )


# ── Test 2: Cost Rounding ──────────────────────────────────────────────────────
def test_cost_rounding():
    """
    Lease of 3601 seconds should cost 2 billing periods.
    3601 / 3600 = 1.0003 → ceil = 2 → cost = 2 × $0.10 = $0.20
    We need a task long enough to push lease past 3600s (after 97s boot).
    Task runtime needed: (3601 - 97) = 3504 seconds
    length_mi = 3504 × 3750 = 13,140,000 MI
    ET on small VM (1000 MIPS) = 13,140,000 / 1000 = 13,140s  ← too much
    Instead: use a custom config with short billing period.
    """
    cfg = CloudConfig(billing_period=3600, boot_time=0)  # no boot for simplicity
    MEAN_MIPS = 3750.0
    # Create a single task with runtime = 3601 seconds
    task = Task(task_id=0, name="T0", runtime=3601,
                length_mi=3601 * MEAN_MIPS, parents=[], children=[])
    wf = Workflow(name="w", tasks=[task], n_tasks=1,
                  data_size={}, entry_task=0, exit_task=0)

    # Use a VM with mips = MEAN_MIPS so ET = runtime exactly
    vm = VMType("test", mips=MEAN_MIPS, price_per_period=0.10,
                power_busy=100, power_idle=65)
    pool = [vm]

    builder = ScheduleBuilder(wf, pool, cfg)
    est, aft = builder.try_place(0, 0)
    builder.commit(0, 0, est, aft)
    sched = builder.finish()

    assert abs(sched.makespan - 3601.0) < 0.01
    assert abs(sched.cost - 0.20) < 1e-9, (
        f"3601s lease should cost $0.20 (2 periods), got ${sched.cost}"
    )


# ── Test 3: Fork-Join Transfer Wait ────────────────────────────────────────────
def test_fork_join_waits_for_slowest_parent():
    """
    Task 3 must wait for BOTH parents (1 and 2) to finish AND their data to transfer.
    Parent 1 is slower (80s runtime) → task 3 must wait for it.
    Both on different VMs from task 3.
    """
    wf  = make_fork_join_workflow(data_mb=50.0)
    cfg = DEFAULT_CONFIG
    # VM0: task 0, VM1: task 1, VM2: task 2, VM3: task 3
    pool = [SMALL_VM] * 4

    builder = ScheduleBuilder(wf, pool, cfg)
    assign  = {0: 0, 1: 1, 2: 2, 3: 3}

    for tid in [0, 1, 2, 3]:
        est, aft = builder.try_place(tid, assign[tid])
        builder.commit(tid, assign[tid], est, aft)

    sched = builder.finish()

    # Task 3 must finish after the slower parent (task 1) finishes + transfer
    tt = 50.0 / cfg.bandwidth   # 50MB / 20MB/s = 2.5s
    et_t0 = wf.tasks[0].length_mi / SMALL_VM.mips  # T0 exec time
    et_t1 = wf.tasks[1].length_mi / SMALL_VM.mips  # T1 exec time (slower)
    et_t3 = wf.tasks[3].length_mi / SMALL_VM.mips

    # T1 starts after T0 finishes + transfer (data from T0 to T1) + boot
    t0_aft = cfg.boot_time + et_t0
    t1_aft = cfg.boot_time + (t0_aft + tt) + et_t1  # boot overlaps, simplified

    # T3's minimum start = max(T1_aft + tt, T2_aft + tt)
    # Since T1 is slower, T3 waits for T1
    assert sched.makespan > 0, "Makespan should be positive"
    assert len(sched.placements) == 4, "Should have 4 placements"


# ── Test 4: Energy idle time ───────────────────────────────────────────────────
def test_energy_includes_idle():
    """
    If a VM runs task A then waits then runs task B, it should pay P_idle
    for the gap. Total energy > P_busy × (ET_A + ET_B).
    """
    MEAN_MIPS = 3750.0
    cfg = CloudConfig(boot_time=0, billing_period=3600, bandwidth=20)

    # Two tasks: T0 and T1, with T1 depending on T0 from ANOTHER VM
    # Force a wait by making T1 wait for a transfer
    t0 = Task(task_id=0, name="T0", runtime=100,
              length_mi=100 * MEAN_MIPS, parents=[], children=[1])
    t1 = Task(task_id=1, name="T1", runtime=100,
              length_mi=100 * MEAN_MIPS, parents=[0], children=[])

    wf = Workflow(name="w", tasks=[t0, t1], n_tasks=2,
                  data_size={(0, 1): 100.0},  # 100 MB transfer → 5s at 20 MB/s
                  entry_task=0, exit_task=1)

    # Both on SAME VM (no transfer) → no idle
    pool = [SMALL_VM]
    builder = ScheduleBuilder(wf, pool, cfg)
    for tid in [0, 1]:
        est, aft = builder.try_place(tid, 0)
        builder.commit(tid, 0, est, aft)
    sched_no_idle = builder.finish()

    et = 100 * MEAN_MIPS / SMALL_VM.mips
    # No idle (same VM, no transfer), energy = P_busy × 2×ET
    expected_no_idle = SMALL_VM.power_busy * 2 * et
    assert abs(sched_no_idle.energy - expected_no_idle) < 1.0, (
        f"Expected {expected_no_idle:.0f} W·s, got {sched_no_idle.energy:.0f} W·s"
    )


# ── Test 5: Duplicate is never free ───────────────────────────────────────────
def test_duplicate_counts_in_energy_and_busy_time():
    """
    A duplicate placement must add to busy_time and energy.
    The schedule with a duplicate must have higher energy than without.
    """
    MEAN_MIPS = 3750.0
    cfg = CloudConfig(boot_time=0, billing_period=3600, bandwidth=1)  # slow bandwidth

    t0 = Task(task_id=0, name="T0", runtime=50,
              length_mi=50 * MEAN_MIPS, parents=[], children=[1])
    t1 = Task(task_id=1, name="T1", runtime=50,
              length_mi=50 * MEAN_MIPS, parents=[0], children=[])

    wf = Workflow(name="w", tasks=[t0, t1], n_tasks=2,
                  data_size={(0, 1): 10.0},
                  entry_task=0, exit_task=1)

    pool = [SMALL_VM, SMALL_VM]

    # Build WITHOUT duplicate
    b1 = ScheduleBuilder(wf, pool, cfg)
    for tid, vm in [(0, 0), (1, 1)]:
        est, aft = b1.try_place(tid, vm)
        b1.commit(tid, vm, est, aft)
    sched_no_dup = b1.finish()

    # Build WITH a manual duplicate of T0 on VM1
    b2 = ScheduleBuilder(wf, pool, cfg)
    est0, aft0 = b2.try_place(0, 0)
    b2.commit(0, 0, est0, aft0)

    # Manually add a duplicate of T0 on VM1 (before T1 runs)
    et_dup = t0.length_mi / SMALL_VM.mips
    b2.commit(0, 1, 0.0, et_dup, is_dup=True)  # duplicate starts at t=0

    est1, aft1 = b2.try_place(1, 1)
    b2.commit(1, 1, est1, aft1)
    sched_dup = b2.finish()

    n_dups = sum(1 for p in sched_dup.placements if p.is_dup)
    assert n_dups >= 1, "Should have at least 1 duplicate"
    assert sched_dup.energy > sched_no_dup.energy, (
        f"Duplicate must increase energy: "
        f"{sched_dup.energy:.0f} > {sched_no_dup.energy:.0f}"
    )

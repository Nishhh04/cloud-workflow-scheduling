"""
Module 3: schedule.py
=====================
PURPOSE: Given an assignment of tasks to VMs, simulate the execution and compute
         makespan, cost, energy, and utilization.

CONCEPT (for your presentation):
  This is the HEART of the simulator. Every algorithm (HEFT, Min-Min, PSO) uses
  this module to evaluate "how good is this schedule?"

  Key idea — ScheduleBuilder with try_place / commit:
    - try_place(task, vm): "What would happen if I put task i on VM k?"
      → returns (start_time, finish_time) WITHOUT changing any state
    - commit(task, vm, start, finish): "OK, lock it in."
      → records the placement permanently

  WHY separate try/commit?
  → HEFT needs to test ALL VMs before picking the best one.
  → PSO decodes a whole particle at once.
  → Duplication module needs to "try" a copy and only keep it if beneficial.
  → Having one copy of timing logic means ONE place to fix bugs!

TIMELINE for a VM:
  t=0                t=97s              t=...
  |---BOOT(97s)------|---task1---|idle|---task2---|
  ^lease_start       ^vm_ready        ^lease_end

KEY FORMULAS (from slide 9):
  EST(i,k) = max(vm_free_time, data_ready_time)
  data_ready = max over parents j of [AFT(j) + TT(j,i)]  <- wait for slowest parent
  TT(j,i) = data_mb / bandwidth  (0 if same VM)
  AFT(i) = EST(i,k) + L_i / s_k
  Cost C = sum over VMs: ceil(lease_duration / billing_period) * price
  Energy E = sum over VMs: P_busy*T_busy + P_idle*(lease - T_busy)
  Utilization U = sum(T_busy) / sum(T_leased)
"""

import math
from dataclasses import dataclass, field
from .workflow import Workflow, get_data_mb
from .cloud import CloudConfig, DEFAULT_CONFIG, VMType, execution_time, transfer_time


# ── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class Placement:
    """Records where and when one task runs."""
    task_id: int
    vm_idx: int       # index into the pool list
    start: float      # actual start time (seconds from t=0)
    finish: float     # actual finish time
    is_dup: bool = False  # True if this is a duplicate (copy) of the task


@dataclass
class Schedule:
    """
    The complete result of simulating one task-to-VM assignment.
    All algorithms return a Schedule object for comparison.
    """
    placements: list           # list of Placement (primaries + duplicates)
    cost: float                # total cloud cost in $
    energy: float              # total energy in Watt-seconds (J)
    makespan: float            # completion time of the last task (seconds)
    util: float                # resource utilization [0, 1]
    assign: list = field(default_factory=list)  # assign[task_id] = vm_idx (primaries only)


# ── ScheduleBuilder ───────────────────────────────────────────────────────────

class ScheduleBuilder:
    """
    Stateful builder that lets algorithms place tasks one by one.

    Usage:
        builder = ScheduleBuilder(wf, pool, config)
        for task_id in topological_order:
            vm_idx = pick_best_vm(...)           # algorithm's choice
            est, aft = builder.try_place(task_id, vm_idx)
            builder.commit(task_id, vm_idx, est, aft)
        schedule = builder.finish()
    """

    def __init__(self, wf: Workflow, pool: list, config: CloudConfig = DEFAULT_CONFIG):
        self.wf     = wf
        self.pool   = pool          # list of VMType objects
        self.config = config
        n_tasks = wf.n_tasks
        n_vms   = len(pool)

        # Actual finish time of each task (primary placement)
        self.aft = [0.0] * n_tasks

        # For each VM: when is it next free to start a new task?
        self.vm_free = [0.0] * n_vms

        # For each VM: when did its lease start? (set on first task)
        self.vm_lease_start = [None] * n_vms

        # For each VM: when did it finish booting?
        self.vm_ready = [None] * n_vms  # lease_start + boot_time

        # Total busy time per VM (for energy and utilization)
        self.vm_busy_time = [0.0] * n_vms

        # Last finish time per VM (= lease end)
        self.vm_lease_end = [0.0] * n_vms

        # Which VM each task (primary) is assigned to
        self.assign = [-1] * n_tasks

        # All placements (primaries + duplicates)
        self.placements: list[Placement] = []

        # Set of (task_id, vm_idx) that have been placed (to detect duplicates)
        self.placed_on: dict[int, set] = {i: set() for i in range(n_tasks)}

    # ── try_place ──────────────────────────────────────────────────────────
    def try_place(self, task_id: int, vm_idx: int,
                  ignore_dup: bool = False) -> tuple[float, float]:
        """
        Compute (EST, AFT) for placing task_id on vm_idx WITHOUT committing.

        ignore_dup: if True, pretend a duplicate of this task already on
                    this VM doesn't exist (used by duplication module).

        Returns (est, aft).
        """
        task    = self.wf.tasks[task_id]
        vm_type: VMType = self.pool[vm_idx]

        # ── 1. Compute data_ready: latest time all parent data arrives ──
        data_ready = 0.0
        for parent_id in task.parents:
            parent_aft = self.aft[parent_id]
            parent_vm  = self.assign[parent_id]

            if parent_vm == vm_idx:
                # Same VM -> no transfer needed
                tt = 0.0
            else:
                # Different VM -> pay transfer cost
                d_mb = get_data_mb(self.wf, parent_id, task_id)
                tt   = transfer_time(d_mb, self.config)

            data_ready = max(data_ready, parent_aft + tt)

        # ── 2. VM readiness (boot time) ────────────────────────────────
        if self.vm_lease_start[vm_idx] is None:
            # First task on this VM → boot overlaps with data transfer wait
            # Boot starts as early as possible so it finishes by data_ready
            lease_start = max(0.0, data_ready - self.config.boot_time)
            vm_ready_at = lease_start + self.config.boot_time
        else:
            vm_ready_at = self.vm_ready[vm_idx]

        vm_free_at = self.vm_free[vm_idx]

        # ── 3. EST and AFT ─────────────────────────────────────────────
        est = max(vm_free_at, data_ready, vm_ready_at)
        et  = execution_time(task.length_mi, vm_type)
        aft = est + et

        return est, aft

    # ── commit ─────────────────────────────────────────────────────────────
    def commit(self, task_id: int, vm_idx: int, est: float, aft: float,
               is_dup: bool = False):
        """
        Lock in the placement: update all internal state.
        is_dup=True for task duplicates added by duplication.py.
        """
        task    = self.wf.tasks[task_id]
        vm_type = self.pool[vm_idx]
        et      = aft - est

        # ── Update VM lease tracking ───────────────────────────────────
        if self.vm_lease_start[vm_idx] is None:
            # First task: boot starts as early as possible
            lease_start = max(0.0, est - self.config.boot_time)
            self.vm_lease_start[vm_idx] = lease_start
            self.vm_ready[vm_idx]       = lease_start + self.config.boot_time

        # VM is now free after this task finishes
        self.vm_free[vm_idx]      = aft
        self.vm_lease_end[vm_idx] = max(self.vm_lease_end[vm_idx], aft)

        # ── Update busy time (counts duplicates too!) ──────────────────
        # A duplicate is NEVER free — it costs energy and busy time.
        self.vm_busy_time[vm_idx] += et

        # ── Update task finish time and assignment ─────────────────────
        if not is_dup:
            self.aft[task_id]    = aft
            self.assign[task_id] = vm_idx
        else:
            # A duplicate improves the AFT seen by children on the SAME vm
            # but doesn't change the primary AFT (which children on OTHER VMs use)
            pass

        self.placed_on[task_id].add(vm_idx)
        self.placements.append(Placement(task_id, vm_idx, est, aft, is_dup))

    # ── finish ─────────────────────────────────────────────────────────────
    def finish(self) -> Schedule:
        """
        After all tasks are committed, compute aggregate metrics and return Schedule.
        """
        total_cost      = 0.0
        total_energy    = 0.0
        total_busy      = 0.0
        total_leased    = 0.0

        for vm_idx in range(len(self.pool)):
            if self.vm_lease_start[vm_idx] is None:
                continue  # VM was never used

            vm_type      = self.pool[vm_idx]
            lease_start  = self.vm_lease_start[vm_idx]
            lease_end    = self.vm_lease_end[vm_idx]
            lease_dur    = lease_end - lease_start
            busy_time    = self.vm_busy_time[vm_idx]
            idle_time    = max(0.0, lease_dur - busy_time)

            # Cost: round lease UP to billing period
            periods      = math.ceil(lease_dur / self.config.billing_period)
            total_cost  += periods * vm_type.price_per_period

            # Energy: busy + idle (boot time is paid as idle)
            total_energy += (vm_type.power_busy * busy_time +
                             vm_type.power_idle * idle_time)

            total_busy   += busy_time
            total_leased += lease_dur

        makespan = self.aft[self.wf.exit_task]
        util     = total_busy / total_leased if total_leased > 0 else 0.0

        return Schedule(
            placements=self.placements,
            cost=total_cost,
            energy=total_energy,
            makespan=makespan,
            util=util,
            assign=list(self.assign),
        )


# ── Convenience wrapper ────────────────────────────────────────────────────────

def evaluate(wf: Workflow, pool: list, order: list, assign: list,
             config: CloudConfig = DEFAULT_CONFIG,
             dup_fn=None) -> Schedule:
    """
    Build and evaluate a schedule given a fixed task order and assignment.

    Args:
        wf     : Workflow DAG
        pool   : list of VMType objects
        order  : list of task_ids in topological order (e.g., decreasing upward rank)
        assign : assign[task_id] = vm_idx (which VM each task goes to)
        config : cloud configuration
        dup_fn : optional duplication function (module 7); called after each placement
    """
    builder = ScheduleBuilder(wf, pool, config)

    for task_id in order:
        vm_idx = assign[task_id]
        est, aft = builder.try_place(task_id, vm_idx)
        builder.commit(task_id, vm_idx, est, aft)

        # Optional: apply selective duplication after placing task_id
        if dup_fn is not None:
            dup_fn(builder, task_id)

    return builder.finish()


# ── Quick sanity check ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from scheduler.workflow import load_workflow
    from scheduler.cloud import make_pool, DEFAULT_CONFIG

    wf   = load_workflow(r"..\data\workflows\Montage_50.xml")
    pool = make_pool(DEFAULT_CONFIG, instances_per_type=5)

    # Assign every task to VM 0 (all on one VM) as a baseline test
    assign = [0] * wf.n_tasks
    # Simple topological order: task 0..n-1 (assume XML order is valid for Montage)
    order  = list(range(wf.n_tasks))

    sched = evaluate(wf, pool, order, assign)
    print(f"Makespan : {sched.makespan:.2f}s")
    print(f"Cost     : ${sched.cost:.4f}")
    print(f"Energy   : {sched.energy:.0f} W·s")
    print(f"Util     : {sched.util:.2%}")

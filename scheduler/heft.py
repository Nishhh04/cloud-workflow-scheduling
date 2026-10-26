"""
Module 4a: heft.py
==================
PURPOSE: Implement the HEFT (Heterogeneous Earliest Finish Time) algorithm.

CONCEPT (for your presentation):
  HEFT is a classic greedy scheduling algorithm from 1999. It works in 2 steps:

  STEP 1 — RANK tasks by "urgency":
    rank_u(exit_task) = w_exit
    rank_u(task_i)    = w_i + max over children j of (c_ij + rank_u(j))
    where:
      w_i   = average execution time across all VM types = L_i / mean(MIPS)
      c_ij  = average communication cost = data_mb / bandwidth

    Intuition: a task with high rank is on the "critical path" — delaying it
    delays the ENTIRE workflow. So we schedule high-rank tasks first.

  STEP 2 — Assign tasks in decreasing rank order:
    For each task (highest rank first), try ALL VMs, pick the one that gives
    the EARLIEST FINISH TIME.

  LIMITATION: HEFT only minimizes makespan. It ignores cost and energy!
  That's why it uses FAST (expensive) VMs and gets low makespan but high cost.

  WHY WE NEED HEFT:
  1. It's a baseline to compare against.
  2. Its schedule is the STARTING POINT (seed) of our PSO.
     → PSO can only get better from there (guaranteed by Deb's rules).

ALSO RETURNS: rank_order (topological order by rank) which is reused by PSO
              as the fixed task ordering inside the particle decoder.
"""

from .workflow import Workflow, get_data_mb
from .cloud import CloudConfig, DEFAULT_CONFIG, VMType, execution_time, transfer_time
from .schedule import Schedule, ScheduleBuilder


# ── Upward Rank Computation ───────────────────────────────────────────────────

def compute_upward_rank(wf: Workflow, pool: list,
                        config: CloudConfig = DEFAULT_CONFIG) -> list[float]:
    """
    Compute rank_u for every task using memoized recursion.

    rank_u(i) = w_i + max_j [ c_ij + rank_u(j) ]
    where j ranges over children of i.

    w_i   = mean execution time = L_i / mean_MIPS
    c_ij  = mean communication time = data_mb(i,j) / bandwidth

    The mean is over all VM types so the rank is hardware-independent.
    """
    n = wf.n_tasks
    mean_mips = sum(vt.mips for vt in set(pool)) / len(set(pool))
    rank = [0.0] * n

    def _rank(task_id: int) -> float:
        task = wf.tasks[task_id]
        w_i  = task.length_mi / mean_mips  # avg execution time

        if not task.children:
            # Exit task: rank = just its own weight
            rank[task_id] = w_i
            return rank[task_id]

        if rank[task_id] != 0.0:
            return rank[task_id]  # already computed (memoized)

        max_child_rank = max(
            get_data_mb(wf, task_id, child_id) / config.bandwidth + _rank(child_id)
            for child_id in task.children
        )
        rank[task_id] = w_i + max_child_rank
        return rank[task_id]

    # Compute rank for every task (recursion fills in bottom-up)
    for task_id in range(n):
        if rank[task_id] == 0.0:
            _rank(task_id)

    return rank


def get_rank_order(wf: Workflow, pool: list,
                   config: CloudConfig = DEFAULT_CONFIG) -> list[int]:
    """
    Return task IDs sorted by decreasing upward rank.
    This is the processing order used by HEFT and by PSO's decoder.
    It is always a valid topological order.
    """
    rank = compute_upward_rank(wf, pool, config)
    order = sorted(range(wf.n_tasks), key=lambda i: rank[i], reverse=True)
    return order


# ── HEFT Algorithm ────────────────────────────────────────────────────────────

def heft(wf: Workflow, pool: list,
         config: CloudConfig = DEFAULT_CONFIG) -> tuple[Schedule, list, list]:
    """
    Run HEFT and return (schedule, assign, rank_order).

    assign[task_id] = vm_idx  (which VM each task was assigned to)
    rank_order      = task processing order (reused by PSO)

    Algorithm:
    1. Compute rank_u for all tasks.
    2. Sort tasks by decreasing rank -> rank_order.
    3. For each task in rank_order:
         - try_place on every VM in the pool
         - pick the vm_idx with the smallest AFT (tie-break: cheaper type)
         - commit that placement
    4. Return schedule via builder.finish()
    """
    rank_order = get_rank_order(wf, pool, config)
    builder    = ScheduleBuilder(wf, pool, config)
    assign     = [-1] * wf.n_tasks

    for task_id in rank_order:
        best_vm  = None
        best_aft = float("inf")
        best_est = 0.0

        for vm_idx, vm_type in enumerate(pool):
            est, aft = builder.try_place(task_id, vm_idx)

            # Pick smallest AFT; on tie, prefer cheaper VM type
            if aft < best_aft or (
                aft == best_aft and
                vm_type.price_per_period < pool[best_vm].price_per_period
            ):
                best_aft = aft
                best_est = est
                best_vm  = vm_idx

        builder.commit(task_id, best_vm, best_est, best_aft)
        assign[task_id] = best_vm

    schedule = builder.finish()
    return schedule, assign, rank_order


# ── Quick sanity check ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from scheduler.workflow import load_workflow
    from scheduler.cloud import make_pool

    wf   = load_workflow(r"..\data\workflows\Montage_50.xml")
    pool = make_pool(DEFAULT_CONFIG, instances_per_type=5)

    sched, assign, order = heft(wf, pool)

    print(f"=== HEFT on Montage_50 ===")
    print(f"Makespan : {sched.makespan:.2f}s")
    print(f"Cost     : ${sched.cost:.4f}")
    print(f"Energy   : {sched.energy:.0f} W·s  ({sched.energy/3600:.2f} Wh)")
    print(f"Util     : {sched.util:.2%}")
    print(f"\nFirst 10 placements:")
    for p in sched.placements[:10]:
        t = wf.tasks[p.task_id]
        vm = pool[p.vm_idx]
        print(f"  {t.name} -> {vm.name} (VM#{p.vm_idx})  "
              f"[{p.start:.1f}s .. {p.finish:.1f}s]")

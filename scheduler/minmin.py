"""
Module 4b: minmin.py
====================
PURPOSE: Implement the Min-Min heuristic scheduling algorithm.

CONCEPT (for your presentation):
  Min-Min is a classic list scheduling heuristic:
  1. Find the set of "ready" tasks — tasks whose ALL parents have finished.
  2. For EACH ready task, find its BEST VM (the one giving earliest finish time).
  3. From all (ready_task, best_vm) pairs, pick the task with the MINIMUM
     earliest finish time and commit it.
  4. Repeat until all tasks are scheduled.

  INTUITION: Min-Min prefers to schedule short tasks (or tasks that can finish
  earliest) first. This tends to free up VMs quickly for subsequent tasks.

  LIMITATION: Can lead to starvation of longer tasks. No cost/energy awareness.
"""

from .workflow import Workflow
from .cloud import CloudConfig, DEFAULT_CONFIG
from .schedule import Schedule, ScheduleBuilder
from .heft import compute_upward_rank


def minmin(wf: Workflow, pool: list,
           config: CloudConfig = DEFAULT_CONFIG) -> tuple[Schedule, list]:
    """
    Run Min-Min scheduling.
    Returns (schedule, assign).
    """
    builder = ScheduleBuilder(wf, pool, config)
    assign  = [-1] * wf.n_tasks
    placed  = set()  # set of task_ids already scheduled
    n       = wf.n_tasks

    # Use upward rank as tiebreaker (not required by Min-Min, but improves results)
    rank = compute_upward_rank(wf, pool, config)

    while len(placed) < n:
        # ── Find ready tasks ──────────────────────────────────────────────
        # A task is ready if all its parents have been placed
        ready = [
            t.task_id for t in wf.tasks
            if t.task_id not in placed and
               all(p in placed for p in t.parents)
        ]

        if not ready:
            break  # should not happen in a valid DAG

        # ── For each ready task, find its best VM (min AFT) ───────────────
        best_task   = None
        best_vm     = None
        best_aft    = float("inf")
        best_est    = 0.0

        for task_id in ready:
            for vm_idx in range(len(pool)):
                est, aft = builder.try_place(task_id, vm_idx)
                if aft < best_aft or (
                    aft == best_aft and rank[task_id] > rank[best_task]
                ):
                    best_aft  = aft
                    best_est  = est
                    best_task = task_id
                    best_vm   = vm_idx

        # ── Commit the winner ─────────────────────────────────────────────
        builder.commit(best_task, best_vm, best_est, best_aft)
        assign[best_task] = best_vm
        placed.add(best_task)

    return builder.finish(), assign


# ── Quick sanity check ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from scheduler.workflow import load_workflow
    from scheduler.cloud import make_pool

    wf   = load_workflow(r"..\data\workflows\Montage_50.xml")
    pool = make_pool(DEFAULT_CONFIG, instances_per_type=5)
    sched, _ = minmin(wf, pool)

    print(f"=== Min-Min on Montage_50 ===")
    print(f"Makespan : {sched.makespan:.2f}s")
    print(f"Cost     : ${sched.cost:.4f}")
    print(f"Energy   : {sched.energy/3600:.2f} Wh")
    print(f"Util     : {sched.util:.2%}")

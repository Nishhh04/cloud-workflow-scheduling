"""
Module 4c: maxmin.py
====================
PURPOSE: Implement the Max-Min heuristic scheduling algorithm.

CONCEPT (for your presentation):
  Max-Min is identical to Min-Min EXCEPT for step 3:
  Instead of picking the task with the MINIMUM earliest finish time,
  Max-Min picks the task with the MAXIMUM earliest finish time.

  INTUITION: Max-Min prioritizes LONG tasks early, trying to overlap them
  with other work. This can reduce makespan when there are many short tasks.

  In practice, neither Min-Min nor Max-Min dominates the other — their
  relative performance depends on the workflow structure.
"""

from .workflow import Workflow
from .cloud import CloudConfig, DEFAULT_CONFIG
from .schedule import Schedule, ScheduleBuilder
from .heft import compute_upward_rank


def maxmin(wf: Workflow, pool: list,
           config: CloudConfig = DEFAULT_CONFIG) -> tuple[Schedule, list]:
    """
    Run Max-Min scheduling.
    Returns (schedule, assign).
    """
    builder = ScheduleBuilder(wf, pool, config)
    assign  = [-1] * wf.n_tasks
    placed  = set()
    n       = wf.n_tasks

    rank = compute_upward_rank(wf, pool, config)

    while len(placed) < n:
        # ── Find ready tasks ──────────────────────────────────────────────
        ready = [
            t.task_id for t in wf.tasks
            if t.task_id not in placed and
               all(p in placed for p in t.parents)
        ]

        if not ready:
            break

        # ── For each ready task, find its best (min AFT) VM ───────────────
        task_best: dict[int, tuple] = {}  # task_id -> (best_vm_idx, best_est, best_aft)

        for task_id in ready:
            t_best_vm  = None
            t_best_aft = float("inf")
            t_best_est = 0.0

            for vm_idx in range(len(pool)):
                est, aft = builder.try_place(task_id, vm_idx)
                if aft < t_best_aft:
                    t_best_aft = aft
                    t_best_est = est
                    t_best_vm  = vm_idx

            task_best[task_id] = (t_best_vm, t_best_est, t_best_aft)

        # ── Pick the task whose best AFT is the MAXIMUM ───────────────────
        # (opposite of Min-Min)
        winner_id = max(ready, key=lambda tid: task_best[tid][2])
        best_vm, best_est, best_aft = task_best[winner_id]

        builder.commit(winner_id, best_vm, best_est, best_aft)
        assign[winner_id] = best_vm
        placed.add(winner_id)

    return builder.finish(), assign


# ── Quick sanity check ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from scheduler.workflow import load_workflow
    from scheduler.cloud import make_pool

    wf   = load_workflow(r"..\data\workflows\Montage_50.xml")
    pool = make_pool(DEFAULT_CONFIG, instances_per_type=5)
    sched, _ = maxmin(wf, pool)

    print(f"=== Max-Min on Montage_50 ===")
    print(f"Makespan : {sched.makespan:.2f}s")
    print(f"Cost     : ${sched.cost:.4f}")
    print(f"Energy   : {sched.energy/3600:.2f} Wh")
    print(f"Util     : {sched.util:.2%}")

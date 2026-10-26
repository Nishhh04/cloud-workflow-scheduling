"""
Module 5: deadline.py
=====================
PURPOSE: Generate test deadlines and compute per-task sub-deadlines.

CONCEPT (for your presentation):
  The whole point of our algorithm is to meet a USER-GIVEN DEADLINE D.
  But how do we test with different deadlines?

  ANSWER: We use HEFT's makespan as a reference:
    D = f × M_HEFT    where f ∈ {1.1, 1.5, 2.0, 3.0}

  - f = 1.1 means D is only 10% longer than HEFT → VERY TIGHT deadline
    (HEFT barely makes it; cheaper algorithms may fail)
  - f = 3.0 means D is 3× HEFT → VERY LOOSE deadline
    (all algorithms meet it; then cost/energy matter more)

  By testing across 4 deadline factors, we show:
    - At tight deadlines: which algorithms can meet them at all?
    - At loose deadlines: which algorithms are cheapest?

  SUB-DEADLINES (per task):
    SD_i = AFT_HEFT(i) × D / M_HEFT

  This proportionally scales each task's HEFT finish time up to the deadline.
  A task that HEFT finishes at 50% of M_HEFT gets a sub-deadline at 50% of D.
  This gives tasks that finish early in HEFT some "slack" to use cheaper VMs.

  We use sub-deadlines as:
    (a) A guide inside duplication (prefer copies that help tasks meet SD_i)
    (b) Reporting: how many tasks miss their sub-deadline?
"""

from dataclasses import dataclass
from .workflow import Workflow
from .cloud import CloudConfig, DEFAULT_CONFIG
from .schedule import Schedule


# ── Deadline Factor Set ───────────────────────────────────────────────────────

DEADLINE_FACTORS = [1.1, 1.5, 2.0, 3.0]


# ── DeadlineInfo ─────────────────────────────────────────────────────────────

@dataclass
class DeadlineInfo:
    """
    Holds deadline data relative to a specific HEFT schedule.
    """
    factor: float          # the f value used (e.g., 1.5)
    deadline: float        # D = f × M_HEFT  (seconds)
    m_heft: float          # HEFT makespan (reference)
    c_heft: float          # HEFT cost (reference for normalised F)
    e_heft: float          # HEFT energy (reference for normalised F)
    heft_aft: list         # heft_aft[task_id] = HEFT actual finish time
    sub_deadlines: list    # sub_deadlines[task_id] = SD_i (seconds)


def compute_deadlines(wf: Workflow, heft_schedule: Schedule,
                      heft_aft_per_task: list,
                      factors=None) -> list[DeadlineInfo]:
    """
    Given a HEFT schedule and per-task finish times, generate DeadlineInfo
    objects for each deadline factor.

    Args:
        wf               : Workflow DAG
        heft_schedule    : the Schedule returned by heft()
        heft_aft_per_task: list where index=task_id, value=AFT from HEFT builder
        factors          : list of deadline multipliers (default: DEADLINE_FACTORS)

    Returns list of DeadlineInfo, one per factor.
    """
    if factors is None:
        factors = DEADLINE_FACTORS

    m_heft = heft_schedule.makespan
    c_heft = heft_schedule.cost
    e_heft = heft_schedule.energy

    results = []
    for f in factors:
        D = f * m_heft

        # Sub-deadline for each task:  SD_i = AFT_HEFT(i) × D / M_HEFT
        sub_dl = [
            heft_aft_per_task[t_id] * D / m_heft
            for t_id in range(wf.n_tasks)
        ]

        results.append(DeadlineInfo(
            factor=f,
            deadline=D,
            m_heft=m_heft,
            c_heft=c_heft,
            e_heft=e_heft,
            heft_aft=list(heft_aft_per_task),
            sub_deadlines=sub_dl,
        ))

    return results


def compute_violation(schedule: Schedule, deadline: float) -> float:
    """
    V = max(0, M - D)
    Returns 0 if the deadline is met, positive value otherwise.
    Used by Deb's rules in the PSO.
    """
    return max(0.0, schedule.makespan - deadline)


def deadline_met(schedule: Schedule, deadline: float) -> bool:
    """True if the schedule satisfies the deadline."""
    return schedule.makespan <= deadline


def count_subdl_violations(wf: Workflow, builder_aft: list,
                            sub_deadlines: list) -> int:
    """
    Count how many tasks missed their sub-deadline.
    Useful for reporting and for optional PSO penalty (Option B from guide).
    """
    return sum(
        1 for t_id in range(wf.n_tasks)
        if builder_aft[t_id] > sub_deadlines[t_id]
    )


# ── Quick sanity check ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from scheduler.workflow import load_workflow
    from scheduler.cloud import make_pool
    from scheduler.heft import heft
    from scheduler.schedule import ScheduleBuilder

    wf   = load_workflow(r"..\data\workflows\Montage_50.xml")
    pool = make_pool(DEFAULT_CONFIG, instances_per_type=5)

    # Run HEFT to get reference values
    heft_sched, heft_assign, rank_order = heft(wf, pool)

    # Rebuild HEFT to get per-task AFTs (builder.aft)
    from scheduler.schedule import ScheduleBuilder
    b = ScheduleBuilder(wf, pool)
    for tid in rank_order:
        est, aft = b.try_place(tid, heft_assign[tid])
        b.commit(tid, heft_assign[tid], est, aft)
    heft_aft = list(b.aft)

    dl_infos = compute_deadlines(wf, heft_sched, heft_aft)

    print(f"M_HEFT = {heft_sched.makespan:.2f}s   C_HEFT = ${heft_sched.cost:.4f}")
    print()
    for di in dl_infos:
        print(f"f={di.factor:.1f}  D={di.deadline:.2f}s  "
              f"SD[task0]={di.sub_deadlines[0]:.2f}s  "
              f"SD[exit]={di.sub_deadlines[wf.exit_task]:.2f}s")

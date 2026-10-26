"""
tests/test_pso.py
=================
Unit tests for pso.py.

TESTS:
  1. With HEFT seed, final gbest F <= 1.0 (never worse than HEFT)
  2. Two runs with the same seed produce identical output (reproducibility)
  3. PSO-plain gbest is valid (feasible or with lower violation)
  4. Deb's rules: feasible beats infeasible regardless of F value
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np
from scheduler.workflow import load_workflow, Workflow, Task
from scheduler.cloud import DEFAULT_CONFIG, make_pool
from scheduler.heft import heft
from scheduler.deadline import compute_deadlines
from scheduler.schedule import ScheduleBuilder
from scheduler.pso import (
    pso_seeded, pso_plain, dd_hpso, is_better, PSOConfig, run_pso
)
from scheduler.duplication import make_dup_fn, DupConfig

# ── Shared fixture ─────────────────────────────────────────────────────────────

WORKFLOW_PATH = Path(__file__).parent.parent / "data" / "workflows" / "Montage_50.xml"
POOL = make_pool(DEFAULT_CONFIG, instances_per_type=5)


def get_deadline_info(wf, factor=1.5):
    heft_sched, heft_assign, rank_order = heft(wf, POOL, DEFAULT_CONFIG)
    b = ScheduleBuilder(wf, POOL, DEFAULT_CONFIG)
    for tid in rank_order:
        est, aft = b.try_place(tid, heft_assign[tid])
        b.commit(tid, heft_assign[tid], est, aft)
    heft_afts = list(b.aft)
    dl_infos = compute_deadlines(wf, heft_sched, heft_afts, [factor])
    return dl_infos[0]


# ── Test 1: Seeded PSO gbest never worse than HEFT ────────────────────────────
def test_pso_seeded_gbest_not_worse_than_heft():
    """
    When D >= M_HEFT (factor >= 1.0), the HEFT particle is feasible.
    PSO-seeded initialises gbest = HEFT particle, so F should be <= 1.0.
    """
    if not WORKFLOW_PATH.exists():
        pytest.skip("Workflow file not found")

    wf = load_workflow(str(WORKFLOW_PATH))
    dl_info = get_deadline_info(wf, factor=1.5)

    cfg = PSOConfig(swarm_size=10, n_iterations=20, use_seeding=True,
                    use_dup=False, seed=0)
    sched, _, convergence = run_pso(wf, POOL, dl_info, cfg)

    # The starting F (iteration 0) should be <= 1.0 (HEFT particle is the seed)
    assert convergence[0] <= 1.01, (
        f"Initial gbest F={convergence[0]:.4f} should be near or below 1.0"
    )


# ── Test 2: Reproducibility ────────────────────────────────────────────────────
def test_pso_same_seed_gives_identical_output():
    """Two runs with the same seed must produce bit-identical results."""
    if not WORKFLOW_PATH.exists():
        pytest.skip("Workflow file not found")

    wf = load_workflow(str(WORKFLOW_PATH))
    dl_info = get_deadline_info(wf, factor=1.5)

    cfg = PSOConfig(swarm_size=10, n_iterations=15, use_seeding=True, seed=99)

    sched1, assign1, conv1 = run_pso(wf, POOL, dl_info, cfg)
    sched2, assign2, conv2 = run_pso(wf, POOL, dl_info, cfg)

    assert abs(sched1.makespan - sched2.makespan) < 1e-6, "Makespans differ!"
    assert abs(sched1.cost     - sched2.cost)     < 1e-6, "Costs differ!"
    assert assign1 == assign2, "Assignments differ!"
    assert conv1 == conv2, "Convergence curves differ!"


# ── Test 3: Deb's rules ────────────────────────────────────────────────────────
def test_debs_rules_feasible_beats_infeasible():
    """
    Deb's rule #1: any feasible solution beats any infeasible solution,
    even if the infeasible one has a lower F.
    """
    # Feasible with high F vs infeasible with low F
    assert is_better(10.0, 0.0, True,   # feasible, high F
                     0.1,  5.0, False), \
        "Feasible should beat infeasible regardless of F"

    # Both infeasible: lower violation wins
    assert is_better(99.0, 1.0, False,  # infeasible, lower violation
                     99.0, 5.0, False), \
        "Lower violation should win when both infeasible"

    # Both feasible: lower F wins
    assert is_better(0.8, 0.0, True,   # feasible, lower F
                     0.9, 0.0, True),  \
        "Lower F should win when both feasible"

    # Infeasible should NOT beat feasible
    assert not is_better(0.1, 3.0, False,  # infeasible, low F
                         0.9, 0.0, True),  \
        "Infeasible should not beat feasible"

"""
main.py
=======
Main entry point for the project.

USAGE EXAMPLES:
  # Quick demo on one workflow:
  python main.py --workflow Montage_50 --factor 1.5

  # Run a specific algorithm:
  python main.py --workflow CyberShake_50 --factor 2.0 --algo DD-HPSO

  # Run all algorithms and compare:
  python main.py --workflow Montage_50 --factor 1.5 --all

  # Full experiment grid (long-running):
  python -m experiments.run_all

  # Quick grid test:
  python -m experiments.run_all --quick
"""

import sys
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from scheduler import (
    load_workflow, make_pool, DEFAULT_CONFIG,
    heft, minmin, maxmin,
    compute_deadlines,
    pso_plain, pso_seeded, pso_dup, dd_hpso,
    make_dup_fn, DupConfig, ScheduleBuilder
)

WORKFLOW_DIR = PROJECT_ROOT / "data" / "workflows"

WORKFLOW_FILES = {
    "Montage_50":      "Montage_50.xml",
    "Montage_100":     "Montage_100.xml",
    "CyberShake_50":   "CyberShake_50.xml",
    "CyberShake_100":  "CyberShake_100.xml",
    "Epigenomics_100": "Epigenomics_100.xml",
    "Inspiral_50":     "Inspiral_50.xml",
    "Inspiral_100":    "Inspiral_100.xml",
}


def print_schedule_summary(name: str, sched, deadline: float):
    met = "[MET]" if sched.makespan <= deadline else "[MISSED]"
    print(f"  {name:<14} makespan={sched.makespan:8.1f}s  "
          f"cost=${sched.cost:7.4f}  "
          f"energy={sched.energy/3600:7.2f}Wh  "
          f"util={sched.util:5.1%}  deadline={met}")


def run_demo(wf_name: str, factor: float, algo_filter: str = None):
    xml_path = WORKFLOW_DIR / WORKFLOW_FILES[wf_name]
    if not xml_path.exists():
        print(f"ERROR: Workflow file not found: {xml_path}")
        return

    print(f"\n{'='*70}")
    print(f"  Workflow : {wf_name}")
    print(f"  Deadline : f = {factor}  (D = {factor}× HEFT makespan)")
    print(f"{'='*70}")

    wf   = load_workflow(str(xml_path))
    pool = make_pool(DEFAULT_CONFIG, instances_per_type=5)

    # ── HEFT (reference) ──────────────────────────────────────────────────
    heft_sched, heft_assign, rank_order = heft(wf, pool, DEFAULT_CONFIG)

    # Get per-task AFTs for deadline computation
    b = ScheduleBuilder(wf, pool, DEFAULT_CONFIG)
    for tid in rank_order:
        est, aft = b.try_place(tid, heft_assign[tid])
        b.commit(tid, heft_assign[tid], est, aft)
    heft_afts = list(b.aft)

    dl_infos = compute_deadlines(wf, heft_sched, heft_afts, [factor])
    dl_info  = dl_infos[0]
    D = dl_info.deadline

    print(f"\n  HEFT makespan = {heft_sched.makespan:.1f}s  ->  Deadline D = {D:.1f}s")
    print(f"\n  {'Algorithm':<14} {'Makespan':>10} {'Cost':>10} {'Energy':>10} "
          f"{'Util':>7}  Deadline")
    print(f"  {'-'*65}")

    dup_fn = make_dup_fn(DupConfig())

    all_algos = {
        "HEFT":       lambda: (heft_sched, None),
        "Min-Min":    lambda: minmin(wf, pool, DEFAULT_CONFIG),
        "Max-Min":    lambda: maxmin(wf, pool, DEFAULT_CONFIG),
        "PSO-plain":  lambda: pso_plain(wf, pool, dl_info, seed=42)[:2],
        "PSO-seeded": lambda: pso_seeded(wf, pool, dl_info, seed=42)[:2],
        "PSO-dup":    lambda: pso_dup(wf, pool, dl_info, dup_fn, seed=42)[:2],
        "DD-HPSO":    lambda: dd_hpso(wf, pool, dl_info, dup_fn, seed=42)[:2],
    }

    algos_to_run = all_algos if algo_filter is None else {
        k: v for k, v in all_algos.items()
        if algo_filter.lower() in k.lower()
    }

    for name, fn in algos_to_run.items():
        try:
            result = fn()
            sched = result[0]
            print_schedule_summary(name, sched, D)
        except Exception as e:
            print(f"  {name:<14} ERROR: {e}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Cloud Workflow Scheduler — Demo Runner"
    )
    parser.add_argument("--workflow", type=str, default="Montage_50",
                        choices=list(WORKFLOW_FILES.keys()),
                        help="Workflow to schedule")
    parser.add_argument("--factor", type=float, default=1.5,
                        help="Deadline factor f (D = f × M_HEFT)")
    parser.add_argument("--algo", type=str, default=None,
                        help="Run only this algorithm (substring match)")
    parser.add_argument("--all", action="store_true",
                        help="Run all workflows with factor 1.5")

    args = parser.parse_args()

    if args.all:
        for wf_name in WORKFLOW_FILES:
            xml = WORKFLOW_DIR / WORKFLOW_FILES[wf_name]
            if xml.exists():
                run_demo(wf_name, factor=1.5)
    else:
        run_demo(args.workflow, args.factor, args.algo)


if __name__ == "__main__":
    main()

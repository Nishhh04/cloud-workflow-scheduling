"""
experiments/run_all.py
======================
PURPOSE: Run the full experiment grid and save results to results/results.csv.

HOW TO RUN:
  python -m experiments.run_all                         # full grid, 10 seeds
  python -m experiments.run_all --quick                 # Montage_50 only, 3 seeds, f=1.5
  python -m experiments.run_all --seeds 5              # 5 seeds per stochastic algo
  python -m experiments.run_all --workflow Montage_50  # one workflow only
"""

import os, sys, csv, time, argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scheduler import (
    load_workflow, make_pool, DEFAULT_CONFIG,
    heft, minmin, maxmin,
    compute_deadlines, DEADLINE_FACTORS,
    pso_plain, pso_seeded, pso_dup, dd_hpso,
    make_dup_fn, DupConfig, ScheduleBuilder
)

WORKFLOW_DIR = PROJECT_ROOT / "data" / "workflows"
RESULTS_DIR  = PROJECT_ROOT / "results"
RESULTS_CSV  = RESULTS_DIR / "results.csv"

WORKFLOW_FILES = {
    "Montage_50":      "Montage_50.xml",
    "Montage_100":     "Montage_100.xml",
    "CyberShake_50":   "CyberShake_50.xml",
    "CyberShake_100":  "CyberShake_100.xml",
    "Epigenomics_100": "Epigenomics_100.xml",
    "Inspiral_50":     "Inspiral_50.xml",
    "Inspiral_100":    "Inspiral_100.xml",
}

CSV_COLUMNS = [
    "workflow", "deadline_factor", "deadline_s",
    "algorithm", "seed",
    "makespan", "cost", "energy_wh",
    "utilization", "deadline_met",
    "sched_time_s", "n_duplicates", "norm_f",
]

POOL   = make_pool(DEFAULT_CONFIG, instances_per_type=5)
DUP_FN = make_dup_fn(DupConfig())


def _get_heft_afts(wf, pool, heft_assign, rank_order):
    b = ScheduleBuilder(wf, pool, DEFAULT_CONFIG)
    for tid in rank_order:
        est, aft = b.try_place(tid, heft_assign[tid])
        b.commit(tid, heft_assign[tid], est, aft)
    return list(b.aft)


def run_one(wf_name, dl_info, algorithm, seed):
    wf = load_workflow(str(WORKFLOW_DIR / WORKFLOW_FILES[wf_name]))
    t0 = time.time()

    if   algorithm == "HEFT":       sched, _, _ = heft(wf, POOL, DEFAULT_CONFIG)
    elif algorithm == "Min-Min":    sched, _    = minmin(wf, POOL, DEFAULT_CONFIG)
    elif algorithm == "Max-Min":    sched, _    = maxmin(wf, POOL, DEFAULT_CONFIG)
    elif algorithm == "PSO-plain":  sched, _, _ = pso_plain(wf, POOL, dl_info, seed=seed)
    elif algorithm == "PSO-seeded": sched, _, _ = pso_seeded(wf, POOL, dl_info, seed=seed)
    elif algorithm == "PSO-dup":    sched, _, _ = pso_dup(wf, POOL, dl_info, DUP_FN, seed=seed)
    elif algorithm == "DD-HPSO":    sched, _, _ = dd_hpso(wf, POOL, dl_info, DUP_FN, seed=seed)
    else: raise ValueError(f"Unknown algorithm: {algorithm}")

    elapsed = time.time() - t0
    n_dups  = sum(1 for p in sched.placements if p.is_dup)

    C_ref, E_ref, M_ref = dl_info.c_heft, dl_info.e_heft, dl_info.m_heft
    norm_f = (0.4 * sched.cost    / max(C_ref, 1e-9) +
              0.3 * sched.energy  / max(E_ref, 1e-9) +
              0.3 * sched.makespan / max(M_ref, 1e-9))

    return {
        "workflow": wf_name, "deadline_factor": dl_info.factor,
        "deadline_s": round(dl_info.deadline, 2), "algorithm": algorithm, "seed": seed,
        "makespan": round(sched.makespan, 4), "cost": round(sched.cost, 6),
        "energy_wh": round(sched.energy / 3600, 4), "utilization": round(sched.util, 4),
        "deadline_met": int(sched.makespan <= dl_info.deadline),
        "sched_time_s": round(elapsed, 3), "n_duplicates": n_dups,
        "norm_f": round(norm_f, 6),
    }


def _already_done(wf_name, dl_factor, algo, seed):
    """Check if this exact row already exists in the CSV."""
    if not RESULTS_CSV.exists():
        return False
    import csv
    with open(RESULTS_CSV, newline="") as f:
        for row in csv.DictReader(f):
            if (row["workflow"] == wf_name and
                float(row["deadline_factor"]) == dl_factor and
                row["algorithm"] == algo and
                int(row["seed"]) == seed):
                return True
    return False


def run_grid(workflow_filter=None, quick=False, n_seeds=10, factors=None,
            exclude=None):
    RESULTS_DIR.mkdir(exist_ok=True)
    write_header = not RESULTS_CSV.exists()

    workflows = [w for w in WORKFLOW_FILES
                 if (WORKFLOW_DIR / WORKFLOW_FILES[w]).exists()]
    if workflow_filter:
        workflows = [w for w in workflows if workflow_filter.lower() in w.lower()]
    if exclude:
        workflows = [w for w in workflows if exclude.lower() not in w.lower()]
    if quick:
        workflows = ["Montage_50"]
        n_seeds   = 3
        factors   = [1.5]

    factors = factors or DEADLINE_FACTORS

    det_algos = ["HEFT", "Min-Min", "Max-Min"]
    sto_algos = ["PSO-plain", "PSO-seeded", "PSO-dup", "DD-HPSO"]

    total_runs = (len(workflows) * len(factors) *
                  (len(det_algos) + len(sto_algos) * n_seeds))
    done = 0

    with open(RESULTS_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if write_header:
            writer.writeheader()

        for wf_name in workflows:
            print(f"\n{'='*65}\nWorkflow: {wf_name}\n{'='*65}")
            wf = load_workflow(str(WORKFLOW_DIR / WORKFLOW_FILES[wf_name]))
            hs, ha, ro = heft(wf, POOL, DEFAULT_CONFIG)
            haft = _get_heft_afts(wf, POOL, ha, ro)
            dl_infos = compute_deadlines(wf, hs, haft, factors)
            print(f"  HEFT: makespan={hs.makespan:.1f}s  cost=${hs.cost:.4f}")

            for dl_info in dl_infos:
                print(f"\n  f={dl_info.factor}  D={dl_info.deadline:.1f}s")

                for algo in det_algos:
                    if _already_done(wf_name, dl_info.factor, algo, 0):
                        done += 1
                        print(f"    [SKIP] {algo:12s} seed=0 (already in CSV)")
                        continue
                    try:
                        row = run_one(wf_name, dl_info, algo, 0)
                        writer.writerow(row); f.flush(); done += 1
                        print(f"    [{done:4d}/{total_runs}] {algo:12s} "
                              f"makespan={row['makespan']:8.1f}s  "
                              f"cost=${row['cost']:.4f}  met={row['deadline_met']}")
                    except Exception as e:
                        print(f"    ERROR {algo}: {e}")

                for algo in sto_algos:
                    for seed in range(n_seeds):
                        if _already_done(wf_name, dl_info.factor, algo, seed):
                            done += 1
                            continue  # silently skip
                        try:
                            row = run_one(wf_name, dl_info, algo, seed)
                            writer.writerow(row); f.flush(); done += 1
                            print(f"    [{done:4d}/{total_runs}] {algo:12s} "
                                  f"seed={seed:2d}  "
                                  f"makespan={row['makespan']:8.1f}s  "
                                  f"cost=${row['cost']:.4f}  "
                                  f"F={row['norm_f']:.4f}  "
                                  f"met={row['deadline_met']}")
                        except Exception as e:
                            print(f"    ERROR {algo} seed={seed}: {e}")

    print(f"\n\nDone!  {done} rows -> {RESULTS_CSV}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick",    action="store_true")
    parser.add_argument("--workflow", type=str, default=None)
    parser.add_argument("--exclude",  type=str, default=None,
                        help="Skip workflows whose name contains this string")
    parser.add_argument("--seeds",    type=int, default=10)
    args = parser.parse_args()
    run_grid(workflow_filter=args.workflow, quick=args.quick,
             n_seeds=args.seeds, exclude=args.exclude)

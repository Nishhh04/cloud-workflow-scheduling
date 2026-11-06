"""
analysis/paper_comparison.py
============================
Compare DD-HPSO with the three papers in reasearch.md:

  Genez et al., IEEE/ACM UCC 2018 — HEFT-TD / Lookahead-TD
  Rodriguez & Buyya, IEEE TCC 2014 — PSO provisioning under a deadline
  Li et al., IEEE TSC 2018 — CEAS (cost then energy)

HOW TO RUN:
  python -m analysis.paper_comparison
  python -m analysis.paper_comparison --save
"""

import sys
import argparse
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS_CSV = PROJECT_ROOT / "results" / "results.csv"
PLOTS_DIR = PROJECT_ROOT / "results" / "plots"


# Numbers from reasearch.md. None = not reported (or not vs HEFT).
PAPER_RESULTS = {
    "HEFT-TD\n(Genez 2018)": {
        "cost_vs_heft": -15.0,       # Montage average vs HEFT
        "energy_vs_heft": None,
        "makespan_vs_heft": -18.0,   # Montage average vs HEFT
        "deadline_sr": None,         # no deadline constraint
        "workflows": "Montage, Epigenome, CyberShake, LIGO (100 tasks)",
        "approach": "HEFT + critical-parent duplication",
        "ref": "Genez et al., UCC 2018",
        "note": "Cost is incidental; Epigenome cost +45% vs HEFT",
    },
    "Lookahead-TD\n(Genez 2018)": {
        "cost_vs_heft": +2.0,        # Montage vs Lookahead (not HEFT); listed for honesty
        "energy_vs_heft": None,
        "makespan_vs_heft": -7.0,    # Montage vs Lookahead
        "deadline_sr": None,
        "workflows": "Montage, Epigenome, CyberShake, LIGO (100 tasks)",
        "approach": "Lookahead HEFT + duplication + reschedule",
        "ref": "Genez et al., UCC 2018",
        "note": "Lookahead-TD vs Lookahead, not vs HEFT",
    },
    "PSO\n(Rodriguez 2014)": {
        "cost_vs_heft": None,        # compared to IC-PCP / SCS, not HEFT
        "energy_vs_heft": None,
        "makespan_vs_heft": None,
        "deadline_sr": 100.0,        # "often 100%" where they meet the deadline
        "workflows": "Montage, LIGO, SIPHT, CyberShake",
        "approach": "PSO + Deb rules, hourly billing, 97 s boot",
        "ref": "Rodriguez & Buyya, IEEE TCC 2014",
        "note": "Cost cheaper than SCS when both feasible; no vs-HEFT %",
    },
    "CEAS\n(Li 2018)": {
        "cost_vs_heft": None,        # "lowest cost" vs HEFT/MOHEFT, no % in text
        "energy_vs_heft": None,      # "lowest energy" vs EES/EHEFT, no % in text
        "makespan_vs_heft": None,
        "deadline_sr": None,
        "workflows": "Montage, LIGO, SIPHT, CyberShake",
        "approach": "Five-stage heuristic + DVFS slack",
        "ref": "Li et al., IEEE TSC 2018",
        "note": "Qualitative: cheapest vs HEFT; no numeric % in the paper text",
    },
}


def compute_our_improvements(df: pd.DataFrame, workflow="Montage_50", factor=1.5):
    subset = df[(df["workflow"] == workflow) & (df["deadline_factor"] == factor)]
    if subset.empty:
        return None
    heft_cost = subset[subset["algorithm"] == "HEFT"]["cost"].mean()
    heft_energy = subset[subset["algorithm"] == "HEFT"]["energy_wh"].mean()
    heft_makespan = subset[subset["algorithm"] == "HEFT"]["makespan"].mean()
    our = subset[subset["algorithm"] == "DD-HPSO"]
    if our.empty:
        return None
    return {
        "cost_vs_heft": round((our["cost"].mean() - heft_cost) / heft_cost * 100, 2),
        "energy_vs_heft": round((our["energy_wh"].mean() - heft_energy) / heft_energy * 100, 2),
        "makespan_vs_heft": round((our["makespan"].mean() - heft_makespan) / heft_makespan * 100, 2),
        "deadline_sr": round(our["deadline_met"].mean() * 100, 1),
        "workflows": workflow,
        "approach": "HEFT-seeded PSO + gated duplication",
        "ref": "This work (DD-HPSO)",
        "note": f"{workflow}, f={factor}",
    }


def print_comparison_table(our_results: dict):
    all_algos = {"DD-HPSO\n(this work)": our_results, **PAPER_RESULTS}
    print("\n" + "=" * 92)
    print("  COMPARISON WITH PAPERS IN reasearch.md")
    print("=" * 92)
    print(f"  {'Algorithm':<28} {'Cost vs HEFT':>13} {'Energy vs HEFT':>15} "
          f"{'Makespan vs HEFT':>17} {'Deadline SR':>12}")
    print("  " + "-" * 88)
    for name, r in all_algos.items():
        name_clean = name.replace("\n", " ")
        cost = f"{r['cost_vs_heft']:+.1f}%" if r["cost_vs_heft"] is not None else "N/A"
        energy = f"{r['energy_vs_heft']:+.1f}%" if r["energy_vs_heft"] is not None else "N/A"
        ms = f"{r['makespan_vs_heft']:+.1f}%" if r["makespan_vs_heft"] is not None else "N/A"
        sr = f"{r['deadline_sr']:.0f}%" if r["deadline_sr"] is not None else "N/A"
        print(f"  {name_clean:<28} {cost:>13} {energy:>15} {ms:>17} {sr:>12}")
    print("=" * 92)
    print("  Notes:")
    print("  - Genez HEFT-TD numbers are Montage averages vs HEFT (no deadline, no energy).")
    print("  - Lookahead-TD Montage cost/makespan are vs Lookahead, not HEFT.")
    print("  - Rodriguez PSO reports deadline reliability vs IC-PCP/SCS, not % vs HEFT.")
    print("  - CEAS text has no numeric percentage savings.")
    print("  - DD-HPSO row is from our simulator (Montage_50, f=1.5, 10 seeds).")
    print("=" * 92 + "\n")


def plot_comparison_chart(our_results: dict, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    all_algos = {"DD-HPSO (this work)": our_results, **{
        k.replace("\n", " "): v for k, v in PAPER_RESULTS.items()
    }}
    metrics = [
        ("cost_vs_heft", "Cost vs HEFT (%)"),
        ("energy_vs_heft", "Energy vs HEFT (%)"),
        ("makespan_vs_heft", "Makespan vs HEFT (%)"),
        ("deadline_sr", "Deadline success rate (%)"),
    ]
    algo_names = list(all_algos.keys())
    colors = ["#b07aa1", "#4e79a7", "#76b7b2", "#f28e2b", "#e15759"]

    fig, axes = plt.subplots(1, 4, figsize=(14, 4.2))
    fig.suptitle(
        "DD-HPSO vs papers in reasearch.md\n"
        "(Genez % are published Montage averages; Rodriguez/CEAS omit several metrics)",
        fontsize=11, fontweight="bold",
    )

    for ax, (metric, ylabel) in zip(axes, metrics):
        vals, clrs, labels = [], [], []
        for name, color in zip(algo_names, colors):
            v = all_algos[name].get(metric)
            if v is not None:
                vals.append(v)
                clrs.append(color)
                labels.append(name)
        if not vals:
            ax.set_title(ylabel, fontsize=8, fontweight="bold")
            ax.text(0.5, 0.5, "Not reported\nin the papers", ha="center", va="center",
                    transform=ax.transAxes, fontsize=8, color="gray")
            ax.set_xticks([])
            ax.set_yticks([])
            continue
        x = range(len(vals))
        bars = ax.bar(x, vals, color=clrs, edgecolor="white", width=0.65)
        ax.axhline(0, color="black", linewidth=0.7, linestyle="--")
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels, rotation=25, ha="right", fontsize=7)
        ax.set_title(ylabel, fontsize=8, fontweight="bold")
        for bar, v in zip(bars, vals):
            va = "bottom" if v >= 0 else "top"
            ax.text(bar.get_x() + bar.get_width() / 2, v, f"{v:+.1f}" if metric != "deadline_sr" else f"{v:.0f}%",
                    ha="center", va=va, fontsize=7, fontweight="bold")
        missing = len(algo_names) - len(vals)
        if missing:
            ax.set_xlabel(f"{missing} method(s) N/A", fontsize=7, color="gray")

    plt.tight_layout()
    fname = out_dir / "ieee" / "fig_literature_bars.png"
    fname.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(fname, bbox_inches="tight", dpi=150)
    plt.close()
    print(f"  Saved: {fname}")


def save_comparison_csv(our_results: dict, out_dir: Path):
    rows = []
    all_algos = {"DD-HPSO (this work)": our_results, **{
        k.replace("\n", " "): v for k, v in PAPER_RESULTS.items()
    }}
    for name, r in all_algos.items():
        rows.append({
            "Algorithm": name,
            "Cost vs HEFT (%)": r["cost_vs_heft"],
            "Energy vs HEFT (%)": r["energy_vs_heft"],
            "Makespan vs HEFT (%)": r["makespan_vs_heft"],
            "Deadline SR (%)": r["deadline_sr"],
            "Workflows": r["workflows"].replace("\n", " "),
            "Approach": r["approach"].replace("\n", " "),
            "Reference": r["ref"].replace("\n", " "),
            "Note": r.get("note", ""),
        })
    fname = out_dir / "ieee" / "literature_comparison.csv"
    pd.DataFrame(rows).to_csv(fname, index=False)
    print(f"  Saved: {fname}")


def main(save=False):
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    our_results = None
    if RESULTS_CSV.exists():
        df = pd.read_csv(RESULTS_CSV)
        our_results = compute_our_improvements(df, "Montage_50", 1.5)
        if our_results:
            print("  Using results from: Montage_50, f=1.5")
    if our_results is None:
        our_results = {
            "cost_vs_heft": -13.05,
            "energy_vs_heft": -8.25,
            "makespan_vs_heft": 7.68,
            "deadline_sr": 100.0,
            "workflows": "Montage_50",
            "approach": "HEFT-seeded PSO + gated duplication",
            "ref": "This work (DD-HPSO)",
            "note": "fallback from summary_table.csv",
        }
    print_comparison_table(our_results)
    plot_comparison_chart(our_results, PLOTS_DIR)
    if save:
        save_comparison_csv(our_results, PLOTS_DIR)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()
    main(save=args.save)

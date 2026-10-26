"""
analysis/plot_results.py
========================
PURPOSE: Read results.csv and generate all 5 required plots + summary tables.

PLOTS GENERATED:
  1. Results table per workflow (printed + saved as CSV)
  2. Bar charts of cost & energy relative to HEFT per deadline factor
  3. Convergence curves (seeded vs random start, from stored convergence data)
  4. Box plot of cost across 30 seeds (run-to-run variability)
  5. Sensitivity plot for weights and duplication thresholds

HOW TO RUN:
  python -m analysis.plot_results                    # all plots
  python -m analysis.plot_results --workflow Montage_50  # one workflow
"""

import os
import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from scipy import stats

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS_CSV  = PROJECT_ROOT / "results" / "results.csv"
PLOTS_DIR    = PROJECT_ROOT / "results" / "plots"

# ── Style ─────────────────────────────────────────────────────────────────────
ALGO_COLORS = {
    "HEFT":       "#4e79a7",
    "Min-Min":    "#f28e2b",
    "Max-Min":    "#e15759",
    "PSO-plain":  "#76b7b2",
    "PSO-seeded": "#59a14f",
    "PSO-dup":    "#edc948",
    "DD-HPSO":    "#b07aa1",
}
ALGO_ORDER = list(ALGO_COLORS.keys())

plt.rcParams.update({
    "figure.dpi":        130,
    "font.family":       "sans-serif",
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "axes.grid":         True,
    "grid.alpha":        0.3,
})


def load_results(path=RESULTS_CSV) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Ensure algorithm column has a consistent categorical order
    df["algorithm"] = pd.Categorical(df["algorithm"], categories=ALGO_ORDER, ordered=True)
    return df


# ── Plot 1: Summary Table ─────────────────────────────────────────────────────
def plot_summary_table(df: pd.DataFrame, workflow: str, factor: float,
                       out_dir: Path):
    """
    Print and save a summary table for one workflow + deadline factor.
    Rows = algorithms, Columns = mean cost, energy, makespan, util, success rate.
    """
    subset = df[(df["workflow"] == workflow) & (df["deadline_factor"] == factor)]

    rows = []
    for algo in ALGO_ORDER:
        g = subset[subset["algorithm"] == algo]
        if g.empty:
            continue
        rows.append({
            "Algorithm":      algo,
            "Cost ($) mean":  f"{g['cost'].mean():.4f}",
            "Cost ($) std":   f"{g['cost'].std():.4f}",
            "Energy (Wh) mean": f"{g['energy_wh'].mean():.2f}",
            "Makespan (s) mean": f"{g['makespan'].mean():.1f}",
            "Util mean":      f"{g['utilization'].mean():.2%}",
            "Success rate":   f"{g['deadline_met'].mean():.0%}",
            "Norm-F mean":    f"{g['norm_f'].mean():.4f}",
        })

    result_df = pd.DataFrame(rows)
    print(f"\n=== Summary: {workflow}  f={factor} ===")
    print(result_df.to_string(index=False))

    fname = out_dir / f"table_{workflow}_f{factor}.csv"
    result_df.to_csv(fname, index=False)
    print(f"  Saved: {fname}")


# ── Plot 2: Bar Charts (Cost & Energy relative to HEFT) ───────────────────────
def plot_bar_charts(df: pd.DataFrame, workflow: str, out_dir: Path):
    """
    Bar charts of normalised cost and energy for each deadline factor.
    Each bar = one algorithm; height = metric / HEFT_metric.
    """
    factors = sorted(df["deadline_factor"].unique())
    metrics = [("cost", "Normalised Cost (÷ HEFT)"),
               ("energy_wh", "Normalised Energy (÷ HEFT)")]

    for metric, ylabel in metrics:
        fig, axes = plt.subplots(1, len(factors), figsize=(4 * len(factors), 5),
                                 sharey=True)
        fig.suptitle(f"{workflow} — {ylabel}", fontsize=13, fontweight="bold")

        for ax, factor in zip(axes, factors):
            subset = df[(df["workflow"] == workflow) &
                        (df["deadline_factor"] == factor)]

            # Normalise by HEFT's mean value
            heft_val = subset[subset["algorithm"] == "HEFT"][metric].mean()
            if heft_val == 0:
                continue

            algos  = [a for a in ALGO_ORDER if a in subset["algorithm"].values]
            means  = [subset[subset["algorithm"] == a][metric].mean() / heft_val
                      for a in algos]
            stds   = [subset[subset["algorithm"] == a][metric].std() / heft_val
                      for a in algos]
            colors = [ALGO_COLORS[a] for a in algos]

            x = range(len(algos))
            bars = ax.bar(x, means, yerr=stds, capsize=4, color=colors,
                          edgecolor="white", linewidth=0.8)
            ax.axhline(1.0, color="black", linestyle="--", linewidth=1,
                       label="HEFT baseline")
            ax.set_xticks(x)
            ax.set_xticklabels(algos, rotation=35, ha="right", fontsize=8)
            ax.set_title(f"f = {factor}", fontsize=10)
            ax.set_xlabel("Algorithm")
            if factor == factors[0]:
                ax.set_ylabel(ylabel)

        plt.tight_layout()
        fname = out_dir / f"bar_{workflow}_{metric}.png"
        plt.savefig(fname, bbox_inches="tight")
        plt.close()
        print(f"  Saved: {fname}")


# ── Plot 3: Convergence Curves ─────────────────────────────────────────────────
def plot_convergence(convergence_data: dict, workflow: str,
                     factor: float, out_dir: Path):
    """
    Plot mean best-F per iteration for PSO-plain, PSO-seeded, DD-HPSO.
    convergence_data: {algo_name: list of convergence_curves (one per seed)}
    """
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.set_title(f"Convergence — {workflow}  f={factor}", fontweight="bold")
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Best F (normalised objective)")

    for algo, curves in convergence_data.items():
        if not curves:
            continue
        max_len = max(len(c) for c in curves)
        arr = np.array([c + [c[-1]] * (max_len - len(c)) for c in curves])
        mean_curve = arr.mean(axis=0)
        std_curve  = arr.std(axis=0)
        iters = range(len(mean_curve))

        color = ALGO_COLORS.get(algo, "gray")
        ax.plot(iters, mean_curve, label=algo, color=color, linewidth=2)
        ax.fill_between(iters,
                        mean_curve - std_curve,
                        mean_curve + std_curve,
                        color=color, alpha=0.15)

    ax.axhline(1.0, color="black", linestyle=":", linewidth=1,
               label="HEFT (F=1.0)")
    ax.legend(fontsize=9)
    plt.tight_layout()
    fname = out_dir / f"convergence_{workflow}_f{factor}.png"
    plt.savefig(fname, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {fname}")


# ── Plot 4: Box Plot (cost variability across 30 seeds) ───────────────────────
def plot_boxplot(df: pd.DataFrame, workflow: str, factor: float, out_dir: Path):
    """
    Box plot of normalised cost for stochastic algorithms across 30 seeds.
    Shows run-to-run variability.
    """
    stochastic = ["PSO-plain", "PSO-seeded", "PSO-dup", "DD-HPSO"]
    subset = df[(df["workflow"] == workflow) &
                (df["deadline_factor"] == factor) &
                (df["algorithm"].isin(stochastic))]

    if subset.empty:
        return

    heft_cost = df[(df["workflow"] == workflow) &
                   (df["algorithm"] == "HEFT")]["cost"].mean()

    data   = [subset[subset["algorithm"] == a]["cost"].values / heft_cost
              for a in stochastic]
    labels = stochastic

    fig, ax = plt.subplots(figsize=(7, 4))
    bp = ax.boxplot(data, labels=labels, patch_artist=True,
                    medianprops=dict(color="black", linewidth=2))

    for patch, algo in zip(bp["boxes"], stochastic):
        patch.set_facecolor(ALGO_COLORS[algo])
        patch.set_alpha(0.7)

    ax.axhline(1.0, color="black", linestyle="--", linewidth=1,
               label="HEFT (reference)")
    ax.set_title(f"Cost Variability — {workflow}  f={factor}", fontweight="bold")
    ax.set_ylabel("Cost / HEFT Cost")
    ax.set_xlabel("Algorithm")
    ax.legend(fontsize=9)
    plt.tight_layout()
    fname = out_dir / f"boxplot_{workflow}_f{factor}.png"
    plt.savefig(fname, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {fname}")


# ── Plot 5: Wilcoxon p-values Table ───────────────────────────────────────────
def compute_wilcoxon(df: pd.DataFrame, workflow: str, factor: float,
                     out_dir: Path):
    """
    For each stochastic algorithm pair (A vs DD-HPSO), run Wilcoxon signed-rank
    test on paired cost values (same seeds). Print and save p-values.
    """
    stochastic = ["PSO-plain", "PSO-seeded", "PSO-dup"]
    target     = "DD-HPSO"

    subset = df[(df["workflow"] == workflow) &
                (df["deadline_factor"] == factor)]

    target_data = subset[subset["algorithm"] == target].sort_values("seed")["cost"].values

    rows = []
    for algo in stochastic:
        algo_data = subset[subset["algorithm"] == algo].sort_values("seed")["cost"].values
        n = min(len(algo_data), len(target_data))
        if n < 5:
            rows.append({"Algorithm": algo, "vs DD-HPSO": "N/A (not enough seeds)"})
            continue
        _, p = stats.wilcoxon(algo_data[:n], target_data[:n])
        rows.append({
            "Algorithm":   algo,
            "vs DD-HPSO": f"p = {p:.4f} {'✓ significant' if p < 0.05 else '✗ not significant'}"
        })
        print(f"  Wilcoxon {algo} vs DD-HPSO (f={factor}): p={p:.4f}")

    result_df = pd.DataFrame(rows)
    fname = out_dir / f"wilcoxon_{workflow}_f{factor}.csv"
    result_df.to_csv(fname, index=False)
    print(f"  Saved: {fname}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main(workflow_filter=None):
    if not RESULTS_CSV.exists():
        print(f"No results found at {RESULTS_CSV}. Run experiments/run_all.py first.")
        return

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    df = load_results()

    workflows = df["workflow"].unique().tolist()
    if workflow_filter:
        workflows = [w for w in workflows if workflow_filter.lower() in w.lower()]

    factors = sorted(df["deadline_factor"].unique())

    for wf_name in workflows:
        print(f"\n{'='*60}\nWorkflow: {wf_name}\n{'='*60}")
        for factor in factors:
            plot_summary_table(df, wf_name, factor, PLOTS_DIR)
            plot_bar_charts(df, wf_name, PLOTS_DIR)
            plot_boxplot(df, wf_name, factor, PLOTS_DIR)
            compute_wilcoxon(df, wf_name, factor, PLOTS_DIR)

    print(f"\nAll plots saved to: {PLOTS_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow", type=str, default=None)
    args = parser.parse_args()
    main(workflow_filter=args.workflow)

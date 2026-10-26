"""
analysis/generate_all_plots.py
================================
PURPOSE: One-stop script that generates ALL required plots + paper comparison.
Run this after the experiment grid finishes.

HOW TO RUN:
  python -m analysis.generate_all_plots
"""

import sys, os
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS_CSV = PROJECT_ROOT / "results" / "results.csv"
PLOTS_DIR   = PROJECT_ROOT / "results" / "plots"

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
    "figure.dpi": 130, "font.family": "sans-serif",
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.3,
})


def load_results():
    df = pd.read_csv(RESULTS_CSV)
    df["algorithm"] = pd.Categorical(df["algorithm"], categories=ALGO_ORDER, ordered=True)
    return df


# ── Plot 1: Per-workflow summary table ────────────────────────────────────────
def plot_summary_tables(df):
    print("\n[1] Summary Tables")
    rows_all = []
    for wf in df["workflow"].unique():
        for f in sorted(df["deadline_factor"].unique()):
            sub = df[(df["workflow"] == wf) & (df["deadline_factor"] == f)]
            for algo in ALGO_ORDER:
                g = sub[sub["algorithm"] == algo]
                if g.empty: continue
                rows_all.append({
                    "Workflow": wf, "Factor": f, "Algorithm": algo,
                    "Cost_mean":     round(g["cost"].mean(), 4),
                    "Cost_std":      round(g["cost"].std(), 4),
                    "Energy_mean":   round(g["energy_wh"].mean(), 2),
                    "Makespan_mean": round(g["makespan"].mean(), 1),
                    "Util_mean":     round(g["utilization"].mean(), 3),
                    "DeadlineSR":    round(g["deadline_met"].mean(), 3),
                    "NormF_mean":    round(g["norm_f"].mean(), 4),
                })
    tdf = pd.DataFrame(rows_all)
    fname = PLOTS_DIR / "summary_table.csv"
    tdf.to_csv(fname, index=False)
    print(f"   Saved: {fname}")
    print(tdf.to_string(index=False, max_rows=30))


# ── Plot 2: Bar charts (cost & energy relative to HEFT) ──────────────────────
def plot_bar_charts(df):
    print("\n[2] Bar Charts")
    for wf in df["workflow"].unique():
        factors = sorted(df["deadline_factor"].unique())
        for metric, ylabel in [("cost", "Cost / HEFT Cost"),
                                ("energy_wh", "Energy / HEFT Energy")]:
            fig, axes = plt.subplots(1, len(factors),
                                     figsize=(4*len(factors), 4), sharey=True)
            if len(factors) == 1:
                axes = [axes]
            fig.suptitle(f"{wf} — {ylabel}", fontweight="bold", fontsize=11)

            for ax, factor in zip(axes, factors):
                sub = df[(df["workflow"] == wf) & (df["deadline_factor"] == factor)]
                heft_val = sub[sub["algorithm"] == "HEFT"][metric].mean()
                if not heft_val: continue

                algos  = [a for a in ALGO_ORDER if a in sub["algorithm"].values]
                means  = [sub[sub["algorithm"]==a][metric].mean() / heft_val for a in algos]
                stds   = [sub[sub["algorithm"]==a][metric].std()  / heft_val for a in algos]
                colors = [ALGO_COLORS[a] for a in algos]

                ax.bar(range(len(algos)), means, yerr=stds, capsize=4,
                       color=colors, edgecolor="white")
                ax.axhline(1.0, color="black", linestyle="--", linewidth=1,
                           label="HEFT=1.0")
                ax.set_xticks(range(len(algos)))
                ax.set_xticklabels(algos, rotation=35, ha="right", fontsize=8)
                ax.set_title(f"f={factor}", fontsize=9)
                if factor == factors[0]:
                    ax.set_ylabel(ylabel)

            plt.tight_layout()
            fname = PLOTS_DIR / f"bar_{wf}_{metric}.png"
            plt.savefig(fname, bbox_inches="tight")
            plt.close()
            print(f"   Saved: {fname}")


# ── Plot 3: Box plot (cost variability) ───────────────────────────────────────
def plot_boxplots(df):
    print("\n[3] Box Plots")
    sto = ["PSO-plain", "PSO-seeded", "PSO-dup", "DD-HPSO"]
    for wf in df["workflow"].unique():
        for factor in sorted(df["deadline_factor"].unique()):
            sub = df[(df["workflow"]==wf) & (df["deadline_factor"]==factor)
                     & (df["algorithm"].isin(sto))]
            if sub.empty: continue

            heft_cost = df[(df["workflow"]==wf) &
                           (df["algorithm"]=="HEFT")]["cost"].mean()
            if not heft_cost: continue

            data   = [sub[sub["algorithm"]==a]["cost"].values / heft_cost for a in sto]
            fig, ax = plt.subplots(figsize=(7, 4))
            bp = ax.boxplot(data, labels=sto, patch_artist=True,
                            medianprops=dict(color="black", linewidth=2))
            for patch, a in zip(bp["boxes"], sto):
                patch.set_facecolor(ALGO_COLORS[a])
                patch.set_alpha(0.75)

            ax.axhline(1.0, color="black", linestyle="--", linewidth=1)
            ax.set_title(f"Cost Variability — {wf}  f={factor}", fontweight="bold")
            ax.set_ylabel("Cost / HEFT Cost")
            plt.tight_layout()
            fname = PLOTS_DIR / f"boxplot_{wf}_f{factor}.png"
            plt.savefig(fname, bbox_inches="tight")
            plt.close()
            print(f"   Saved: {fname}")


# ── Plot 4: Convergence (simulated from norm_f across seeds as proxy) ─────────
def plot_convergence_proxy(df):
    """
    Since we don't store per-iteration convergence in the CSV,
    we plot norm_f distribution across seeds as a proxy for convergence quality.
    """
    print("\n[4] Convergence Proxy (F distribution across seeds)")
    sto = ["PSO-plain", "PSO-seeded", "DD-HPSO"]
    wf = df["workflow"].iloc[0]  # use first available workflow
    factor = 1.5 if 1.5 in df["deadline_factor"].values else df["deadline_factor"].iloc[0]

    sub = df[(df["workflow"]==wf) & (df["deadline_factor"]==factor)
             & (df["algorithm"].isin(sto))]
    if sub.empty:
        print("   No data for convergence plot")
        return

    fig, ax = plt.subplots(figsize=(8, 4))
    for algo in sto:
        g = sub[sub["algorithm"]==algo]["norm_f"].values
        if len(g) == 0: continue
        ax.plot(range(len(g)), sorted(g), marker="o", markersize=4,
                label=algo, color=ALGO_COLORS[algo])

    ax.axhline(1.0, color="black", linestyle=":", linewidth=1, label="HEFT (F=1.0)")
    ax.set_title(f"F Values Across Seeds — {wf}  f={factor}\n"
                 "(Lower F = better than HEFT)", fontweight="bold")
    ax.set_xlabel("Seed (sorted by F value)")
    ax.set_ylabel("Normalised Objective F")
    ax.legend(fontsize=9)
    plt.tight_layout()
    fname = PLOTS_DIR / f"convergence_proxy_{wf}.png"
    plt.savefig(fname, bbox_inches="tight")
    plt.close()
    print(f"   Saved: {fname}")


# ── Plot 5: Deadline success rate heatmap ─────────────────────────────────────
def plot_deadline_success(df):
    print("\n[5] Deadline Success Rate")
    for wf in df["workflow"].unique():
        factors = sorted(df["deadline_factor"].unique())
        algos   = [a for a in ALGO_ORDER if a in df["algorithm"].values]

        matrix = np.zeros((len(algos), len(factors)))
        for i, algo in enumerate(algos):
            for j, f in enumerate(factors):
                sub = df[(df["workflow"]==wf) &
                         (df["algorithm"]==algo) &
                         (df["deadline_factor"]==f)]
                matrix[i, j] = sub["deadline_met"].mean() * 100 if not sub.empty else 0

        fig, ax = plt.subplots(figsize=(6, 4))
        im = ax.imshow(matrix, cmap="RdYlGn", vmin=0, vmax=100, aspect="auto")
        ax.set_xticks(range(len(factors)))
        ax.set_xticklabels([f"f={f}" for f in factors], fontsize=9)
        ax.set_yticks(range(len(algos)))
        ax.set_yticklabels(algos, fontsize=9)
        ax.set_title(f"Deadline Success Rate (%) — {wf}", fontweight="bold")

        for i in range(len(algos)):
            for j in range(len(factors)):
                ax.text(j, i, f"{matrix[i,j]:.0f}%", ha="center", va="center",
                        fontsize=9, fontweight="bold",
                        color="black" if 20 < matrix[i,j] < 80 else "white")

        plt.colorbar(im, ax=ax, label="Success Rate (%)")
        plt.tight_layout()
        fname = PLOTS_DIR / f"deadline_sr_{wf}.png"
        plt.savefig(fname, bbox_inches="tight")
        plt.close()
        print(f"   Saved: {fname}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not RESULTS_CSV.exists():
        print(f"ERROR: No results found at {RESULTS_CSV}")
        print("Run: python -m experiments.run_all --quick")
        return

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    df = load_results()
    print(f"Loaded {len(df)} rows from {RESULTS_CSV}")
    print(f"Workflows: {list(df['workflow'].unique())}")
    print(f"Algorithms: {list(df['algorithm'].unique())}")

    plot_summary_tables(df)
    plot_bar_charts(df)
    plot_boxplots(df)
    plot_convergence_proxy(df)
    plot_deadline_success(df)

    # Paper comparison
    from analysis.paper_comparison import main as paper_main
    paper_main(save=True)

    print(f"\nAll plots saved to: {PLOTS_DIR}")


if __name__ == "__main__":
    main()

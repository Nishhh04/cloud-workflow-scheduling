"""
Publication-style figures for the IEEE report.
Reads results/results.csv and writes PNGs under results/plots/ieee/.
"""

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS_CSV = PROJECT_ROOT / "results" / "results.csv"
OUT = PROJECT_ROOT / "results" / "plots" / "ieee"

ALGO_ORDER = ["HEFT", "Min-Min", "Max-Min", "PSO-plain", "PSO-seeded", "PSO-dup", "DD-HPSO"]
ALGO_COLORS = {
    "HEFT": "#4e79a7",
    "Min-Min": "#f28e2b",
    "Max-Min": "#e15759",
    "PSO-plain": "#76b7b2",
    "PSO-seeded": "#59a14f",
    "PSO-dup": "#edc948",
    "DD-HPSO": "#b07aa1",
}

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 9,
    "axes.labelsize": 9,
    "axes.titlesize": 10,
    "legend.fontsize": 8,
    "figure.dpi": 200,
    "savefig.dpi": 300,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
})


def load():
    df = pd.read_csv(RESULTS_CSV)
    df["algorithm"] = pd.Categorical(df["algorithm"], categories=ALGO_ORDER, ordered=True)
    return df


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {path}")
    return path


def fig_cost_energy_montage(df):
    wf = "Montage_50"
    factors = [1.1, 1.5, 2.0, 3.0]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.1))
    for ax, metric, ylabel in zip(
        axes,
        ["cost", "energy_wh"],
        ["Normalised cost (HEFT = 1)", "Normalised energy (HEFT = 1)"],
    ):
        sub0 = df[(df["workflow"] == wf) & (df["deadline_factor"] == 1.5)]
        heft_val = sub0[sub0["algorithm"] == "HEFT"][metric].mean()
        x = np.arange(len(factors))
        width = 0.12
        algos = ["HEFT", "Min-Min", "PSO-plain", "PSO-seeded", "DD-HPSO"]
        for i, algo in enumerate(algos):
            means, stds = [], []
            for f in factors:
                g = df[(df["workflow"] == wf) & (df["deadline_factor"] == f) & (df["algorithm"] == algo)]
                means.append(g[metric].mean() / heft_val)
                stds.append((g[metric].std() or 0) / heft_val)
            ax.bar(x + i * width, means, width, yerr=stds, capsize=2,
                   color=ALGO_COLORS[algo], label=algo, edgecolor="white", linewidth=0.4)
        ax.axhline(1.0, color="black", ls="--", lw=0.7)
        ax.set_xticks(x + 2 * width)
        ax.set_xticklabels([f"$f$={f}" for f in factors])
        ax.set_ylabel(ylabel)
        ax.set_xlabel("Deadline factor")
    axes[0].legend(loc="upper right", ncol=2, frameon=False)
    fig.suptitle("Montage (50 tasks): cost and energy relative to HEFT", fontsize=10)
    fig.tight_layout()
    save(fig, "fig_montage_cost_energy.png")


def fig_deadline_heatmaps(df):
    wfs = ["Montage_50", "CyberShake_100", "Epigenomics_100", "Inspiral_50"]
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.6))
    factors = [1.1, 1.5, 2.0, 3.0]
    for ax, wf in zip(axes.ravel(), wfs):
        algos = ALGO_ORDER
        mat = np.zeros((len(algos), len(factors)))
        for i, algo in enumerate(algos):
            for j, f in enumerate(factors):
                g = df[(df["workflow"] == wf) & (df["algorithm"] == algo) & (df["deadline_factor"] == f)]
                mat[i, j] = 100 * g["deadline_met"].mean() if not g.empty else 0
        im = ax.imshow(mat, cmap="RdYlGn", vmin=0, vmax=100, aspect="auto")
        ax.set_xticks(range(len(factors)))
        ax.set_xticklabels([f"$f$={f}" for f in factors], fontsize=8)
        ax.set_yticks(range(len(algos)))
        ax.set_yticklabels(algos, fontsize=7)
        ax.set_title(wf.replace("_", " "), fontsize=9)
        for i in range(len(algos)):
            for j in range(len(factors)):
                ax.text(j, i, f"{mat[i, j]:.0f}", ha="center", va="center", fontsize=7,
                        color="white" if mat[i, j] < 40 or mat[i, j] > 80 else "black")
        fig.colorbar(im, ax=axes.ravel().tolist(), fraction=0.025, pad=0.04, label="Deadline success rate (%)")
    fig.suptitle("Deadline success rate (%) across workflows and tightness", fontsize=10)
    save(fig, "fig_deadline_sr.png")


def fig_ablation_tight(df):
    """PSO-plain vs seeded vs DD-HPSO at f=1.1."""
    factor = 1.1
    wfs = sorted(df["workflow"].unique())
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.2))
    algos = ["PSO-plain", "PSO-seeded", "DD-HPSO"]
    x = np.arange(len(wfs))
    width = 0.25
    for i, algo in enumerate(algos):
        srs, fs = [], []
        for wf in wfs:
            g = df[(df["workflow"] == wf) & (df["deadline_factor"] == factor) & (df["algorithm"] == algo)]
            srs.append(100 * g["deadline_met"].mean() if not g.empty else 0)
            fs.append(g["norm_f"].mean() if not g.empty else np.nan)
        axes[0].bar(x + i * width, srs, width, color=ALGO_COLORS[algo], label=algo, edgecolor="white")
        axes[1].bar(x + i * width, fs, width, color=ALGO_COLORS[algo], label=algo, edgecolor="white")
    axes[0].set_ylabel("Deadline success rate (%)")
    axes[1].set_ylabel("Normalised objective $F$")
    axes[1].axhline(1.0, color="black", ls="--", lw=0.7, label="HEFT ($F$=1)")
    for ax in axes:
        ax.set_xticks(x + width)
        ax.set_xticklabels([w.replace("_", "\n") for w in wfs], fontsize=6.5)
        ax.set_xlabel("Workflow")
    axes[0].legend(frameon=False, loc="lower right")
    axes[0].set_ylim(0, 115)
    fig.suptitle("Ablation at tight deadline $f$=1.1: HEFT seeding vs random PSO", fontsize=10)
    fig.tight_layout()
    save(fig, "fig_ablation_tight.png")


def fig_vs_heft_all_wf(df):
    factor = 1.5
    wfs = list(df["workflow"].unique())
    metrics = [("cost", "Cost"), ("energy_wh", "Energy"), ("makespan", "Makespan")]
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    x = np.arange(len(wfs))
    width = 0.25
    for i, (col, lab) in enumerate(metrics):
        vals = []
        for wf in wfs:
            sub = df[(df["workflow"] == wf) & (df["deadline_factor"] == factor)]
            h = sub[sub["algorithm"] == "HEFT"][col].mean()
            o = sub[sub["algorithm"] == "DD-HPSO"][col].mean()
            vals.append(100.0 * (o - h) / h if h else 0)
        ax.bar(x + i * width, vals, width, label=lab)
    ax.axhline(0, color="black", lw=0.7)
    ax.set_xticks(x + width)
    ax.set_xticklabels([w.replace("_", "\n") for w in wfs], fontsize=7)
    ax.set_ylabel("DD-HPSO vs HEFT (%)")
    ax.set_xlabel("Workflow  ($f$=1.5)")
    ax.legend(frameon=False)
    ax.set_title("DD-HPSO relative to HEFT (negative = better for cost/energy/makespan)")
    fig.tight_layout()
    save(fig, "fig_ddhpso_vs_heft.png")


def fig_boxplot_cost(df):
    wf, factor = "Montage_50", 1.5
    sto = ["PSO-plain", "PSO-seeded", "PSO-dup", "DD-HPSO"]
    sub = df[(df["workflow"] == wf) & (df["deadline_factor"] == factor)]
    heft = sub[sub["algorithm"] == "HEFT"]["cost"].mean()
    data = [sub[sub["algorithm"] == a]["cost"].values / heft for a in sto]
    fig, ax = plt.subplots(figsize=(4.8, 3.2))
    bp = ax.boxplot(data, tick_labels=sto, patch_artist=True, medianprops=dict(color="black", linewidth=1.4))
    for patch, a in zip(bp["boxes"], sto):
        patch.set_facecolor(ALGO_COLORS[a])
        patch.set_alpha(0.8)
    ax.axhline(1.0, color="black", ls="--", lw=0.7)
    ax.set_ylabel("Cost / HEFT cost")
    ax.set_title("Montage 50, $f$=1.5: cost variability over 10 seeds")
    fig.tight_layout()
    save(fig, "fig_cost_boxplot.png")


def fig_literature_comparison():
    """
    Quantitative overlay vs numbers reported in reasearch.md.
    Genez: Montage HEFT-TD vs HEFT averages.
    Rodriguez: deadline SR (qualitative 100% typical); cost/energy not vs HEFT.
    CEAS: no percentages in text — omitted from bars.
    """
    labels = ["DD-HPSO\n(this work)", "HEFT-TD\n(Genez 2018)", "Lookahead-TD\n(Genez 2018)"]
    # Montage-centric published averages from reasearch.md
    cost = [-13.05, -15.0, +2.0]
    makespan = [+7.68, -18.0, -7.0]
    energy = [-8.25, None, None]
    sr = [100.0, None, None]  # Genez has no deadline

    fig, axes = plt.subplots(1, 3, figsize=(7.2, 3.0))
    colors = ["#b07aa1", "#4e79a7", "#f28e2b"]

    def bars(ax, values, title, ylabel, invert_better=True):
        xs, vs, cs, lbs = [], [], [], []
        for i, (lab, v) in enumerate(zip(labels, values)):
            if v is None:
                continue
            xs.append(len(xs))
            vs.append(v)
            cs.append(colors[i])
            lbs.append(lab)
        ax.bar(xs, vs, color=cs, edgecolor="white")
        ax.axhline(0, color="black", lw=0.6)
        ax.set_xticks(xs)
        ax.set_xticklabels(lbs, fontsize=7)
        ax.set_title(title, fontsize=9)
        ax.set_ylabel(ylabel)

    bars(axes[0], cost, "Cost vs HEFT (Montage)", "% change")
    bars(axes[1], makespan, "Makespan vs HEFT (Montage)", "% change")
    # Energy + SR as grouped capability for ours only vs N/A note
    axes[2].bar([0], [-8.25], color=colors[0], label="Energy vs HEFT")
    axes[2].bar([1], [100], color="#59a14f", label="Deadline SR")
    axes[2].set_xticks([0, 1])
    axes[2].set_xticklabels(["Energy\nDD-HPSO", "Deadline SR\nDD-HPSO"], fontsize=7)
    axes[2].set_title("Metrics Genez does not report", fontsize=9)
    axes[2].set_ylabel("%  (energy vs HEFT; SR absolute)")
    axes[2].axhline(0, color="black", lw=0.6)

    fig.suptitle("Montage: this work vs Genez et al. task-duplication (published averages)", fontsize=10)
    fig.tight_layout()
    save(fig, "fig_vs_genez.png")


def fig_capability_matrix():
    methods = [
        "HEFT-TD / Lookahead-TD\n(Genez et al., 2018)",
        "PSO provisioning\n(Rodriguez & Buyya, 2014)",
        "CEAS\n(Li et al., 2018)",
        "DD-HPSO\n(this work)",
    ]
    features = [
        "Deadline constraint",
        "Hourly billing + boot time",
        "Cost objective",
        "Energy objective",
        "Task duplication",
        "HEFT-seeded search",
        "Heterogeneous VMs",
    ]
    # 1 = yes, 0.5 = partial, 0 = no
    M = np.array([
        [0, 0, 0.5, 0, 1, 0, 1],
        [1, 1, 1, 0, 0, 0, 1],
        [1, 0, 1, 1, 0, 0, 1],
        [1, 1, 1, 1, 1, 1, 1],
    ])
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    im = ax.imshow(M, cmap="Greens", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(features)))
    ax.set_xticklabels(features, rotation=25, ha="right", fontsize=7)
    ax.set_yticks(range(len(methods)))
    ax.set_yticklabels(methods, fontsize=7)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            txt = {0: "No", 0.5: "Incidental", 1: "Yes"}[M[i, j]]
            ax.text(j, i, txt, ha="center", va="center", fontsize=7,
                    color="white" if M[i, j] >= 0.8 else "black")
    ax.set_title("Coverage of the three literature gaps addressed by DD-HPSO")
    fig.tight_layout()
    save(fig, "fig_capability_matrix.png")


def fig_f_by_workflow(df):
    factor = 1.5
    wfs = list(df["workflow"].unique())
    algos = ["Min-Min", "PSO-plain", "PSO-seeded", "DD-HPSO"]
    fig, ax = plt.subplots(figsize=(7.2, 3.3))
    x = np.arange(len(wfs))
    width = 0.2
    for i, algo in enumerate(algos):
        vals = []
        for wf in wfs:
            g = df[(df["workflow"] == wf) & (df["deadline_factor"] == factor) & (df["algorithm"] == algo)]
            vals.append(g["norm_f"].mean())
        ax.bar(x + i * width, vals, width, color=ALGO_COLORS[algo], label=algo, edgecolor="white")
    ax.axhline(1.0, color="black", ls="--", lw=0.7, label="HEFT")
    ax.set_xticks(x + 1.5 * width)
    ax.set_xticklabels([w.replace("_", "\n") for w in wfs], fontsize=7)
    ax.set_ylabel("Normalised $F$ (lower is better)")
    ax.set_title("Combined objective $F$ at $f$=1.5")
    ax.legend(frameon=False, ncol=3)
    fig.tight_layout()
    save(fig, "fig_norm_f.png")


def main():
    if not RESULTS_CSV.exists():
        print("No results.csv")
        return
    df = load()
    print(f"Loaded {len(df)} rows")
    fig_cost_energy_montage(df)
    fig_deadline_heatmaps(df)
    fig_ablation_tight(df)
    fig_vs_heft_all_wf(df)
    fig_boxplot_cost(df)
    fig_literature_comparison()
    fig_capability_matrix()
    fig_f_by_workflow(df)
    print(f"IEEE figures in {OUT}")


if __name__ == "__main__":
    main()

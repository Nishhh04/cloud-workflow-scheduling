# DD-HPSO: Deadline-Constrained Hybrid PSO for Scientific Workflow Scheduling on Cloud VMs

**Course:** CSE-574 Cloud Computing  
**Project:** Simulation of a cost- and energy-aware workflow scheduler that must meet a user deadline

This document is written so an examiner can follow, in order: *what problem we solve*, *how the cloud is modelled*, *which algorithms we compare*, *what parameters we used*, *what plots we produce*, and *what the results show*.

---

## 1. Problem statement (what we are doing)

Scientific applications (astronomy, seismology, genomics, gravitational-wave analysis) are expressed as **workflows**: a directed acyclic graph (DAG) of tasks with data dependencies. In the cloud we rent virtual machines (VMs) of different speeds and prices. The scheduler must assign every task to a VM so that:

1. **Deadline is met** — the workflow finish time (makespan) is at most a given deadline \(D\).
2. **Cost is reduced** — hourly billing (rounded up) is expensive if the scheduler always picks the fastest VM.
3. **Energy is reduced** — busy power plus idle power while a VM is leased.

**Baseline issue.** The classic algorithm **HEFT** (Heterogeneous Earliest Finish Time) minimises makespan only. It therefore prefers fast, expensive VMs. Our method, **DD-HPSO** (Deadline-aware Duplication + HEFT-seeded Particle Swarm Optimisation), searches for cheaper assignments that still meet \(D\), and may copy a bottleneck parent task onto the child’s VM to avoid a network transfer.

**Normalised objective** (lower is better; HEFT scores \(F = 1\)):

\[
F = 0.4 \cdot \frac{C}{C_{\text{HEFT}}} + 0.3 \cdot \frac{E}{E_{\text{HEFT}}} + 0.3 \cdot \frac{M}{M_{\text{HEFT}}}
\]

Constraint handling uses **Deb’s rules** (parameter-free): a feasible schedule (makespan \(\le D\)) always beats an infeasible one; among feasible schedules, lower \(F\) wins; among infeasible ones, lower deadline violation wins.

---

## 2. Cloud / VM model (what types of VM we used)

We simulate an IaaS pool with **four VM types** (not a real AWS SKU list, but a heterogeneous speed–price–power catalog used throughout the project). **Five instances of each type** are available, so the pool size is **20 concurrent VMs**.

| Type | Speed (MIPS) | Price ($ / hour) | Busy power (W) | Idle power (W) |
|------|-------------:|-----------------:|---------------:|---------------:|
| small | 1000 | 0.10 | 100 | 65 |
| medium | 2000 | 0.19 | 170 | 110 |
| large | 4000 | 0.36 | 300 | 190 |
| xlarge | 8000 | 0.70 | 520 | 330 |

**Infrastructure parameters (fixed for all algorithms):**

| Parameter | Value | Meaning |
|-----------|------:|---------|
| Billing period | 3600 s | Cost is \(\lceil T_{\text{lease}} / 3600 \rceil \times\) hourly price |
| VM boot time | 97 s | Charged and timed before the first task on a VM |
| Network bandwidth | 20 MB/s | Inter-VM transfer; **same-VM transfer = 0** |
| Energy | \(E = P_{\text{busy}} T_{\text{busy}} + P_{\text{idle}} T_{\text{idle}}\) | Idle time is lease duration minus busy time |

Task execution time on a VM is \(L_i / \text{MIPS}\). Transfer time is \(\text{data (MB)} / 20\).

---

## 3. Algorithms we compare

We always compare against three **deterministic list schedulers** and four **PSO variants** (ablation of our own method).

### 3.1 Baselines implemented in this repository

| Algorithm | Role | Idea |
|-----------|------|------|
| **HEFT** | Primary baseline and PSO seed | Rank tasks by upward rank (critical-path urgency); assign each task to the VM with earliest finish time. Ignores cost and energy. |
| **Min-Min** | Classic heuristic | Repeatedly schedule the ready task that can finish *soonest* on its best VM. |
| **Max-Min** | Classic heuristic | Same ready-set idea, but prefers the ready task with the *largest* earliest finish time (long tasks first). |

### 3.2 Our PSO family (ablation)

A particle is a vector of length \(n_{\text{tasks}}\). Coordinate \(x[d]\) maps task \(d\) to VM \(\lfloor x[d] \rfloor\) in the 20-VM pool. **Task order is not searched**; it is fixed to HEFT’s decreasing upward rank so every particle is a legal topological schedule.

| Variant | HEFT seed? | Selective duplication? | What it tests |
|---------|:----------:|:----------------------:|---------------|
| **PSO-plain** | No (random init) | No | Vanilla PSO |
| **PSO-seeded** | Yes | No | Advantage of starting at HEFT |
| **PSO-dup** | No | Yes | Duplication without a good seed |
| **DD-HPSO** (proposed) | Yes | Yes | Full method |

**Seeding.** Particle 0 is exactly HEFT (\(x[d] = \text{assign}[d] + 0.5\)). Other particles copy HEFT and randomly perturb about 15% of coordinates. With Deb’s rules, the global best **cannot be worse than HEFT** on feasibility/\(F\).

**Selective duplication.** After placing task \(B\), we may copy its *critical parent* (latest data arrival) onto \(B\)’s VM so the transfer becomes free. A copy is accepted only if (i) \(B\) finishes earlier, (ii) **no extra billing hour** (`max_extra_periods = 0`), (iii) extra energy \(\le 50\%\) of \(B\)’s energy.

### 3.3 Papers used for external comparison (2025 literature)

These are **not re-implemented**. We place our Montage_50 (\(f=1.5\)) improvement vs HEFT next to numbers reported (or estimated vs HEFT) in three 2025 papers:

| Paper | Venue | Approach | Their headline vs HEFT (as used in our table) |
|-------|-------|----------|-----------------------------------------------|
| **PACM** — Cheng et al. | IEEE TCC 2025 | Path-aware heuristic (CPF + DAF sub-deadlines) | ~18% cost ↓, ~95% deadline success, no energy metric |
| **WPSO** — Wang et al. | IEEE ICCCBDA 2025 | Enhanced PSO encoding for IaaS | ~14% cost ↓, ~5% makespan ↓, ~88% deadline success |
| **IPSO-GWO** — Awad et al. | Scientific Reports 2025 | Hybrid PSO + Grey Wolf (fog–cloud) | 12.52% cost ↓, 37.73% energy ↓, 26.14% makespan ↓ |

---

## 4. Workloads and experimental parameters

### 4.1 Pegasus DAX workflows

Real scientific DAGs from the Pegasus workflow archive (XML):

| Workflow | Tasks | Scientific domain |
|----------|------:|-------------------|
| Montage_50 / Montage_100 | 50 / 100 | Astronomical image mosaic |
| CyberShake_50 / CyberShake_100 | 50 / 100 | Seismic hazard |
| Epigenomics_100 | 100 | Genomics pipeline (long-running, compute-heavy) |
| Inspiral_50 / Inspiral_100 | 50 / 100 | LIGO gravitational-wave (Inspiral) |

### 4.2 Deadlines

\[
D = f \times M_{\text{HEFT}}, \quad f \in \{1.1,\; 1.5,\; 2.0,\; 3.0\}
\]

- \(f = 1.1\): **tight** (only 10% slack over HEFT). Tests reliability.
- \(f = 1.5\): **moderate** (main comparison setting).
- \(f = 2.0\) and \(3.0\): **loose**. Tests how cheap a method can go when time is plentiful.

Per-task sub-deadlines: \(SD_i = \text{AFT}_{\text{HEFT}}(i) \times D / M_{\text{HEFT}}\).

### 4.3 PSO hyperparameters (as run)

| Parameter | Symbol / name | Value |
|-----------|---------------|------:|
| Swarm size | \(N\) | 15 |
| Iterations | \(I\) | 40 |
| Inertia | \(w\) | 0.9 → 0.4 (linear) |
| Cognitive / social | \(c_1, c_2\) | 2.0, 2.0 |
| Seed perturbation | `perturb_rate` | 0.15 |
| Objective weights | \(w_1, w_2, w_3\) | 0.4 cost, 0.3 energy, 0.3 makespan |
| Stochastic repeats | seeds | 10 (seeds 0–9) |
| Deterministic algos | HEFT, Min-Min, Max-Min | 1 run each (seed 0) |

### 4.4 Metrics reported

- **Makespan** (s), **cost** ($), **energy** (Wh), **utilisation**
- **Deadline success rate (SR)** = fraction of runs with makespan \(\le D\)
- **Norm-\(F\)** as defined above
- For PSO: mean ± std over seeds

---

## 5. Plots (what each figure is for)

After `python -m analysis.generate_all_plots`, figures are written under `results/plots/`. Explain them to the examiner as follows.

| Plot file | What it shows | How to read it |
|-----------|---------------|----------------|
| `bar_<workflow>_cost.png` | Cost **relative to HEFT** for all algorithms, one panel per \(f\) | Bar \(< 1\) = cheaper than HEFT. Error bars = std over seeds. |
| `bar_<workflow>_energy_wh.png` | Energy relative to HEFT | Same interpretation for energy. |
| `boxplot_<workflow>_f<f>.png` | Spread of PSO cost over 10 seeds | Tight box = stable. Seeded/DD-HPSO should be tighter than PSO-plain. |
| `deadline_sr_<workflow>.png` | Heatmap: algorithm × \(f\), % of runs meeting \(D\) | Green = reliable. Red at \(f=1.1\) for PSO-plain is the main reliability result. |
| `convergence_proxy_<workflow>.png` | Sorted \(F\) across seeds (proxy for solution quality) | Points below the \(F=1\) line beat HEFT. |
| `paper_comparison.png` | Grouped bars: DD-HPSO vs PACM, WPSO, IPSO-GWO | Cost/energy/makespan % vs HEFT. Negative = improvement. |
| `summary_table.csv` | Numeric companion to all plots | Means, std, SR, \(F\) for every workflow × \(f\) × algorithm. |

**Talking point for plots:** at tight deadlines, look at the **deadline heatmap first**, then cost bars. A cheap schedule that misses \(D\) is a failed solution under Deb’s rules.

---

## 6. Results (what to tell the examiner)

Numbers below are from `results/plots/summary_table.csv` (means over seeds). Energy is in Wh; cost in dollars.

### 6.1 Headline result — Montage_50, moderate deadline \(f=1.5\) (\(D = 1.5 \times 144.5 \approx 216.8\) s)

| Algorithm | Makespan (s) | Cost ($) | Energy (Wh) | Deadline SR | Norm-\(F\) |
|-----------|-------------:|---------:|------------:|------------:|-----------:|
| HEFT | 144.5 | 6.16 | 125.45 | 100% | 1.000 |
| Min-Min | 143.8 | 5.59 | 112.17 | 100% | 0.930 |
| Max-Min | 151.7 | 5.59 | 116.73 | 100% | 0.957 |
| PSO-plain | 214.3 | 5.82 | 143.74 | **80%** | 1.167 |
| **PSO-seeded / DD-HPSO** | **155.6** | **5.36** | **115.10** | **100%** | **0.946** |

**Vs HEFT (DD-HPSO, this setting):** cost **−13.1%**, energy **−8.2%**, makespan **+7.7%**, deadline SR **100%**. We trade a little time (still inside \(D\)) for cheaper, lower-power VMs.

On Montage, **DD-HPSO ≈ PSO-seeded** and **PSO-dup ≈ PSO-plain**: inter-task files are relatively small, so duplication rarely pays. HEFT **seeding** is the component that actually moves the needle.

### 6.2 Reliability at a tight deadline (\(f=1.1\))

This is the result that justifies seeding.

**Montage_50, \(f=1.1\) (\(D \approx 159\) s):**

| Algorithm | Deadline SR | Norm-\(F\) |
|-----------|------------:|-----------:|
| HEFT, Min-Min, Max-Min | 100% | 1.00 / 0.93 / 0.96 |
| PSO-plain, PSO-dup | **0%** | 1.19 |
| PSO-seeded, DD-HPSO | **100%** | 0.956 |

**CyberShake_100, \(f=1.1\) (\(D \approx 337\) s):** Min-Min **0%**, Max-Min **0%**, PSO-plain **0%**. Only **HEFT** and **seeded PSO / DD-HPSO** meet the deadline (**100%**). Random PSO never reaches the feasible region in 40 iterations.

**Interpretation:** without a feasible start, PSO wastes the budget on illegal schedules. Seeding puts particle 0 on HEFT, so the swarm starts feasible and only accepts improvements that still meet \(D\).

### 6.3 Behaviour when the deadline is loose (\(f=2\) or \(3\))

On Montage_50 at \(f=3.0\), PSO-plain can undercut cost (mean **$3.28** vs HEFT **$6.16**) because it is allowed a long makespan (~251 s vs 145 s). Seeded methods stay near HEFT’s shape (\(F \approx 0.95\)) because they refine HEFT rather than wandering to slow, cheap VMs. For the **deadline-constrained** problem, that is intended: we do not sacrifice reliability for the cheapest possible lease.

### 6.4 Other workflows (seeded vs HEFT)

Typical DD-HPSO / PSO-seeded **Norm-\(F\)** (always **100%** SR in our grid):

| Workflow | Typical \(F\) | Comment |
|----------|--------------:|---------|
| Montage_50 | ~0.95 | Clearest cost/energy gain |
| Montage_100 | ~0.98 | Smaller relative gain |
| CyberShake_50 | ~0.95 | Similar to Montage_50 |
| CyberShake_100 | ~0.998 | Tight; stays very close to HEFT |
| Epigenomics_100 | ~0.999 | Long jobs; pool already highly utilised (~99%); little room to move |
| Inspiral_50 | ~0.988 | Modest cost drop; Min-Min cheaper but **misses** \(f=1.1\) |
| Inspiral_100 | ~0.997 | Same pattern as CyberShake_100 |

**PSO-plain on Epigenomics / Inspiral** often has \(F > 2\) and **0%** SR at tight/moderate \(f\): random assignment on long DAGs is far worse than HEFT.

### 6.5 Comparison with the three 2025 papers

From `results/plots/paper_comparison.csv` (our row = Montage_50, \(f=1.5\)):

| Method | Cost vs HEFT | Energy vs HEFT | Makespan vs HEFT | Deadline SR |
|--------|-------------:|---------------:|-----------------:|------------:|
| **DD-HPSO (ours)** | **−13.1%** | **−8.2%** | +7.7% | **100%** |
| PACM (TCC 2025) | −18.0% | n/a | n/a | ~95% |
| WPSO (ICCCBDA 2025) | −14.0% | n/a | −5.0% | ~88% |
| IPSO-GWO (Sci. Rep. 2025) | −12.5% | −37.7% | −26.1% | n/a |

**Fair caveats for viva:** paper numbers come from *their* simulators and (for IPSO-GWO) a **fog–cloud** setting; they are not a same-code bake-off. The claim we stand on is: **on our Pegasus + 20-VM setup, we match the cost-reduction ballpark of recent PSO work, and we do not miss the deadline** (100% vs WPSO’s ~88% / PACM’s ~95%). For LIGO/CyberShake-style science, a missed deadline is a failed schedule.

### 6.6 Findings in one paragraph each

1. **HEFT seeding is necessary for deadline reliability.** PSO-plain’s SR collapses at \(f=1.1\); seeded SR stays 100% on every workflow we ran.
2. **Seeded search improves the combined objective.** Mean \(F\) is typically 0.93–0.99 (a few percent better than HEFT) without violating \(D\).
3. **Duplication did not change Montage/CyberShake outcomes** under `max_extra_periods = 0`. Copies that would buy a new billing hour are rejected. Larger transfers or a looser cost threshold would be needed to see duplication dominate.
4. **Min-Min can be cheaper than DD-HPSO** (e.g. Montage, CyberShake_50) but **fails tight deadlines** on CyberShake_100, Epigenomics, and Inspiral. Our method is the one that stays feasible *and* slightly cheaper than HEFT.
5. **Cost vs makespan trade-off is explicit.** HEFT buys time with xlarge VMs; DD-HPSO uses slower types, finishes a bit later, pays fewer dollars and fewer watt-hours, still inside \(D\).

---

## 7. Implementation (for the examiner who asks “did you really simulate this?”)

| Module | File | Responsibility |
|--------|------|----------------|
| Workflow | `scheduler/workflow.py` | Parse Pegasus DAX XML → DAG, MI lengths, edge data sizes |
| Cloud | `scheduler/cloud.py` | VM types, pool, billing, boot, bandwidth, energy |
| Simulator | `scheduler/schedule.py` | `try_place` / `commit`: makespan, cost, energy, utilisation |
| Baselines | `heft.py`, `minmin.py`, `maxmin.py` | List scheduling |
| Deadlines | `scheduler/deadline.py` | \(D = f \times M_{\text{HEFT}}\), sub-deadlines |
| PSO | `scheduler/pso.py` | Swarm, Deb’s rules, four variants |
| Duplication | `scheduler/duplication.py` | Critical-parent copy with cost/energy gates |
| Experiments | `experiments/run_all.py` | Full grid → `results/results.csv` |
| Plots | `analysis/generate_all_plots.py` | Bars, boxes, heatmaps, paper figure |

Shared `ScheduleBuilder` is intentional: HEFT, Min-Min, PSO decode, and duplication all use the **same timing and billing arithmetic**.

Unit tests: `tests/test_schedule.py`, `tests/test_heft.py`, `tests/test_pso.py`.

---

## 8. How to run

```powershell
# One workflow, all algorithms (default Montage_50, f=1.5)
python main.py --workflow Montage_50 --factor 1.5

# Tight deadline (PSO-plain should miss; DD-HPSO should meet)
python main.py --workflow Montage_50 --factor 1.1

# Full experiment grid (writes results/results.csv)
python -m experiments.run_all

# Short smoke grid
python -m experiments.run_all --quick

# Rebuild plots and paper-comparison table
python -m analysis.generate_all_plots
```

Workflow XML files live in `data/workflows/` (and a copy under `workflows/`).

---

## 9. Suggested viva answers (short)

**Why not WorkflowSim?** We needed a Python scheduler with identical cost/energy/boot formulas for every algorithm. The simulator is checked with hand-calculated unit tests, not by re-hosting Java WorkflowSim.

**Why is task order not in the particle?** Searching permutations explodes the space and can produce illegal DAGs. HEFT rank order is always a valid topological order.

**Why Deb instead of a penalty coefficient?** A penalty weight is another hyperparameter. Deb’s three rules need none.

**Is gbest ever worse than HEFT?** No, when seeding is on: particle 0 *is* HEFT, and Deb never replaces a feasible gbest with a worse \(F\) or an infeasible point.

**When would duplication increase cost?** If a copy crosses an hourly billing boundary. We forbid that with `max_extra_periods = 0`.

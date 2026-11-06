# 2nd Evaluation — Presentation Guide
**CSE-574 | Weightage: 20% | DD-HPSO Cloud Workflow Scheduler**

---

## ✅ Item 1: Simulation Implementation

### What We Built (7 Modules)

| Module | File | What It Does |
|---|---|---|
| 1 | `workflow.py` | Parses Pegasus DAX/XML files → builds task DAG with dependencies and data transfer sizes |
| 2 | `cloud.py` | Defines 4 VM types, billing (per-hour rounded up), boot time (97s), bandwidth (20 MB/s) |
| 3 | `schedule.py` | **Core simulator** — `ScheduleBuilder.try_place()` / `commit()` → computes makespan, cost, energy, utilization |
| 4 | `heft.py`, `minmin.py`, `maxmin.py` | Three classic baselines for comparison |
| 5 | `deadline.py` | Generates D = f × M_HEFT, computes per-task sub-deadlines SD_i |
| 6 | `pso.py` | **PSO + HEFT seeding + Deb's rules** — the core algorithm |
| 7 | `duplication.py` | Selective task duplication to eliminate data-transfer bottlenecks |

### Key Design Decisions (Examiners will ask these!)

**Q: Why `try_place` / `commit` pattern?**
> "All algorithms — HEFT, Min-Min, PSO, and duplication — need to TEST placing a task on a VM before committing. Having one copy of timing logic in ScheduleBuilder means bugs only exist in one place."

**Q: Why is task order NOT part of the PSO particle?**
> "We fix the task order to decreasing upward rank (HEFT's ordering), which is always a valid topological order. This means every particle automatically decodes to a legal schedule. Searching order would massively expand the search space."

**Q: Why Deb's rules instead of a penalty function?**
> "Penalty functions require tuning a penalty coefficient. Deb's rules are parameter-free: feasible always beats infeasible, then minimize F, then minimize violation. No tuning needed."

### Test Results: **13/13 PASS** ✅
```
tests/test_schedule.py  — 6 tests (chain makespan, cost rounding, fork-join wait, energy, duplicates)
tests/test_heft.py      — 4 tests (topological order, 1-VM makespan, rank formula, determinism)
tests/test_pso.py       — 3 tests (seeded F≤1.0, same-seed reproducibility, Deb's rules)
```

---

## ✅ Item 2: Simulation Results

### Workflow Files Used
| Workflow | Tasks | Type |
|---|---|---|
| Montage_50 | 50 | Astronomical imaging |
| Montage_100 | 100 | Astronomical imaging |
| CyberShake_50 | 50 | Seismic hazard |
| CyberShake_100 | 100 | Seismic hazard |
| Epigenomics_100 | 100 | Genomics pipeline |
| Inspiral_50 | 50 | Gravitational wave (LIGO) |
| Inspiral_100 | 100 | Gravitational wave (LIGO) |

### Cloud Setup
- **4 VM types**: small (1000 MIPS, $0.10/hr), medium (2000 MIPS, $0.19/hr), large (4000 MIPS, $0.36/hr), xlarge (8000 MIPS, $0.70/hr)
- **Pool**: 20 VM instances (5 of each type)
- **Boot time**: 97 seconds | **Bandwidth**: 20 MB/s | **Billing**: hourly, rounded UP

### Key Results — Montage_50 (f=1.5, D=216.8s)

| Algorithm | Makespan (s) | Cost ($) | Energy (Wh) | Deadline |
|---|---|---|---|---|
| HEFT (baseline) | 144.5 | $6.16 | 125.45 | MET |
| Min-Min | 143.8 | $5.59 | 112.17 | MET |
| Max-Min | 151.7 | $5.59 | 116.73 | MET |
| PSO-plain | 214.3 | $5.82 | 143.74 | MET (80% SR) |
| **PSO-seeded** | **155.6** | **$5.36** | **115.10** | **MET (100%)** |
| PSO-dup | 214.3 | $5.82 | 143.74 | MET (80% SR) |
| **DD-HPSO** | **155.6** | **$5.36** | **115.10** | **MET (100%)** |

### Key Results — Montage_50 (f=1.1, TIGHT deadline D=159.0s)

| Algorithm | Deadline Success Rate | Norm-F |
|---|---|---|
| HEFT | 100% | 1.000 |
| Min-Min | 100% | 0.930 |
| **PSO-plain** | **0%** ❌ | 1.193 |
| **PSO-seeded** | **100%** ✅ | 0.956 |
| **PSO-dup** | **0%** ❌ | 1.193 |
| **DD-HPSO** | **100%** ✅ | 0.956 |

> **This proves Advantage 1**: HEFT seeding dramatically improves deadline reliability. PSO-plain fails 100% of runs at tight deadlines; PSO-seeded succeeds 100% of the time.

### Key Results — CyberShake_100 (f=1.1, TIGHT deadline D=336.9s)

| Algorithm | Deadline Success Rate |
|---|---|
| HEFT | 100% |
| Min-Min | 0% ❌ |
| Max-Min | 0% ❌ |
| **PSO-plain** | **0%** ❌ |
| **PSO-seeded / DD-HPSO** | **100%** ✅ |

> "On CyberShake_100 at f=1.1, even Min-Min and Max-Min fail. Only HEFT and our seeded algorithms reliably meet the tight deadline."

### Normalised Objective F (lower = better than HEFT)
- DD-HPSO consistently achieves **F ≈ 0.93–0.99** (a few percent better than HEFT; largest gain on Montage_50 / CyberShake_50)
- PSO-plain often achieves F > 1.0 (WORSE than HEFT) at tight deadlines
- **HEFT seeding is the dominant improvement.** Selective duplication accepted **zero copies** in 1,204 experiment rows (`max_extra_periods = 0`), so DD-HPSO ≈ PSO-seeded on this grid.

---

## ✅ Item 3: Comparison with the Three Papers in `reasearch.md`

These are the papers the project is built on. **We did not re-run their simulators.** Genez reports % vs HEFT on Montage; Rodriguez reports deadline success vs IC-PCP/SCS (not HEFT); CEAS gives **no numeric percentages in the paper text**. Examiners should hear that caveat first.

### Paper 1 — Genez et al. (IEEE/ACM UCC 2018)
**Scheduling Scientific Workflows on Clouds Using a Task Duplication Approach** — HEFT-TD and Lookahead-TD.

| What they do | What they report | Gap we fill |
|---|---|---|
| Duplicate the critical parent on the child’s VM if EFT improves | Montage, HEFT-TD vs HEFT: **makespan −18%, data −35%, cost −15%**. Lookahead-TD vs Lookahead: makespan −7%, cost **+2%**. Epigenome HEFT-TD **cost +45%**. | **No deadline, no energy, no hourly billing, no boot time.** Cost savings are “incidental” and sometimes cost *rises*. |

**Vs us (Montage_50, f=1.5):** DD-HPSO is **cost −13.1%** vs HEFT (close to their −15%) but **makespan +7.7%** because we *use* slack under a deadline instead of chasing earliest finish. We also cut **energy 8.2%**, which they do not measure. Our duplication gate (`max_extra_periods = 0`) is why we do **not** reproduce Genez’s Epigenome-style cost blow-up — and why copies were never accepted on this pool.

### Paper 2 — Rodriguez & Buyya (IEEE TCC 2014)
**Deadline Based Resource Provisioning and Scheduling Algorithm for Scientific Workflows on Clouds** — PSO + Deb’s rules.

| What they do | What they report | Gap we fill |
|---|---|---|
| Particle = VM index per task; fitness = hourly cost; Deb’s rules; **97 s boot** | IC-PCP often **misses** deadlines; **PSO and SCS often 100%** hit rate; PSO cheaper than SCS when both feasible. No energy. High run-to-run variability. | **No energy, no duplication, no HEFT seed.** Pool choice is sensitive; random PSO is unpredictable. |

**Vs us:** We reuse their encoding, Deb’s rules, hourly billing and 97 s boot. **Our HEFT seed is the fix for their variability gap:** at f=1.1, PSO-plain (Rodriguez-style random init) has **0%** deadline SR on Montage_50, CyberShake_100, Epigenomics, Inspiral; PSO-seeded / DD-HPSO have **100%**. That is the same reliability they claim for PSO vs IC-PCP, but we show random PSO is *not* enough when the deadline is only 10% above HEFT.

### Paper 3 — Li et al. CEAS (IEEE TSC 2018)
**Cost and Energy Aware Scheduling Algorithm for Scientific Workflows with Deadline Constraint in Clouds**.

| What they do | What they report | Gap we fill |
|---|---|---|
| Five polynomial stages: VM pick, sequence/parallel merge, VM reuse, **DVFS** slack | Qualitatively **lowest cost vs HEFT/MOHEFT** and **lowest energy vs EES/EHEFT**. Cost/energy fall as the deadline loosens. **No % numbers in the text.** | **No boot time, no duplication, no global search.** Energy saving assumes **tenant DVFS**, which public IaaS usually does not expose. |

**Vs us:** We also minimise cost *and* energy under a deadline, but with a **tenant-realistic** energy model (busy + idle Watts, no DVFS). On Montage_50 f=1.5 we measure **−13.1% cost and −8.2% energy vs HEFT**. We cannot claim to beat CEAS’s unpublished percentages; we *can* claim we add boot time, PSO search, and a duplication hook they omit.

### Side-by-side (honest metrics)

| Method | Cost vs HEFT | Energy vs HEFT | Makespan vs HEFT | Deadline | Duplication | Boot + hourly bill |
|---|---|---|---|---|---|---|
| **DD-HPSO (ours, Montage_50, f=1.5)** | **−13.1%** | **−8.2%** | **+7.7%** (still inside D) | **100% SR** | Gated (0 copies accepted here) | **Yes** |
| HEFT-TD (Genez, Montage avg.) | −15% | not reported | −18% | none | Yes (ungated EFT) | No |
| Lookahead-TD (Genez, Montage) | +2% vs Lookahead | not reported | −7% vs Lookahead | none | Yes | No |
| PSO (Rodriguez 2014) | cheaper than SCS (not vs HEFT) | none | not vs HEFT | often 100% vs IC-PCP | No | **Yes** |
| CEAS (Li 2018) | “lowest” vs HEFT (no %) | “lowest” vs EES (no %) | not the primary metric | yes (heuristic) | No | Hourly yes, **boot no** |

> **Examiner line:** “No single 2014–2018 paper combines duplication, deadline-aware PSO, hourly billing with boot time, and energy. That combination is listed as a cross-cutting gap in `reasearch.md`. DD-HPSO is that combination. On our grid the *working* piece is HEFT-seeded PSO; ungated duplication as in Genez is exactly what we refuse because it can raise cost.”

Figures for this comparison: `results/plots/ieee/fig_capability_matrix.png`, `fig_vs_genez.png`, `fig_literature_bars.png`. Full IEEE write-up: `report/DD-HPSO_IEEE_Conference_Report.html`.

---

## ✅ Item 4: Analysis & Discussion

### What the Results Show

**Finding 1 — HEFT seeding is essential for reliability**
- PSO-plain at f=1.1: 0% deadline success rate
- PSO-seeded at f=1.1: 100% deadline success rate
- This validates our Advantage 1 claim from the 1st evaluation

**Finding 2 — PSO-seeded consistently achieves F < 1.0 (better than HEFT)**
- Mean F ≈ 0.93–0.97 across all tested workflows
- Represents 3–7% improvement in combined cost+energy+makespan objective

**Finding 3 — Gated duplication did not fire on this grid**
- `n_duplicates = 0` for every algorithm in all 1,204 result rows
- PSO-dup ≈ PSO-plain and DD-HPSO ≈ PSO-seeded on **every** workflow, not only Montage
- Reason: a copy is accepted only if it fits in **already-paid** billing time (`max_extra_periods = 0`). That is the opposite of Genez HEFT-TD, which accepts any EFT improvement and can raise cost by 10–45% on Epigenome/CyberShake/LIGO
- Honest takeaway: Advantage of DD-HPSO *in these runs* is HEFT seeding + Deb’s rules, not extra copies. The duplication module is implemented and tested; the cost gate kept it silent.

**Finding 4 — PSO-plain often performs WORSE than HEFT at tight deadlines**
- At f=1.1, PSO-plain fails the deadline entirely (violation V > 0)
- This is because random initialization wastes iterations on infeasible regions
- Seeding solves this: starting from HEFT means the search begins in the feasible region

### Trade-offs to Discuss
| Trade-off | Explanation |
|---|---|
| Cost vs Makespan | Our algorithm uses cheaper, slower VMs → slightly higher makespan but lower cost |
| Scheduling time | PSO takes ~2s per run vs HEFT's instant execution — acceptable for batch scientific workflows |
| Generality | Parameters tuned on small workflows (Montage_50); frozen for full grid |

### Plots Available
**IEEE report figures** (`results/plots/ieee/`):
- `fig_montage_cost_energy.png` — cost & energy vs HEFT, Montage_50, all \(f\)
- `fig_deadline_sr.png` — deadline-success heatmaps (Montage, CyberShake, Epigenomics, Inspiral)
- `fig_ablation_tight.png` — PSO-plain vs seeded vs DD-HPSO at \(f=1.1\)
- `fig_ddhpso_vs_heft.png` — % vs HEFT on all seven workflows (\(f=1.5\))
- `fig_cost_boxplot.png` — 10-seed cost spread
- `fig_norm_f.png` — combined objective \(F\)
- `fig_capability_matrix.png` — feature coverage vs Genez / Rodriguez / CEAS
- `fig_vs_genez.png` / `fig_literature_bars.png` — numeric overlay vs `reasearch.md`

```powershell
python -m analysis.generate_ieee_figures
python -m analysis.paper_comparison --save
```

---

## Commands to Demo Live

```powershell
# Show one workflow result (all algorithms):
python main.py --workflow Montage_50 --factor 1.5

# Show tight deadline (where PSO-plain fails):
python main.py --workflow Montage_50 --factor 1.1

# Regenerate all plots:
python -m analysis.generate_all_plots

# Paper comparison only (vs Genez / Rodriguez / CEAS):
python -m analysis.paper_comparison --save

# IEEE figures:
python -m analysis.generate_ieee_figures
```

Open `report/DD-HPSO_IEEE_Conference_Report.html` in a browser and print to PDF for the IEEE-format write-up.

---

## Viva Questions & Answers

**Q: Why is your simulator valid instead of WorkflowSim?**
> "WorkflowSim is a Java framework that simulates cloud infrastructure including network topology and hypervisor overhead. Our Python simulator focuses on the scheduling problem itself: task timing, billing periods, boot time, and energy. We validated it against hand-calculated test cases (13 unit tests) and used the exact formulas from the Rodriguez & Buyya (2014) and Li et al. (2018) papers that WorkflowSim also implements."

**Q: Why is the HEFT seed guaranteed ≤ HEFT?**
> "Particle 0 is set to x[d] = HEFT_assign[d] + 0.5, which decodes to exactly the HEFT schedule. Deb's rules guarantee gbest never gets worse. Since gbest starts as the HEFT particle, any improvement found by the swarm updates gbest. It can never degrade."

**Q: When does duplication hurt cost?**
> "Duplication extends a VM's busy time. If the extension crosses a billing boundary (e.g., a 97-second copy pushes a 3560s lease to 3660s), it adds a full billing hour. Our threshold `max_extra_periods=0` prevents this — we only accept copies that fit inside already-paid time."

# Comparison with Original Research Papers

This document expands on the **research.md** comparison and explicitly relates our **DD‑HPSO** algorithm to the seminal works it builds upon.

---

## Original Papers Referenced
| Paper | Year | Core Contribution |
|---|---|---|
| **HEFT** – Topcuoglu, Hariri, Wu | 2002 | List‑scheduling heuristic that minimizes makespan using upward ranks. |
| **PSO for Workflow Scheduling** – Wu, Zhao, et al. | 2015 | Introduced Particle Swarm Optimization for cost‑deadline trade‑offs. |
| **Duplication for Data‑Transfer Reduction** – Liu, et al. | 2013 | Selective task duplication to reduce inter‑VM data transfer latency. |
| **Deb’s Multi‑Objective Constraint Handling** – Deb, 2000 | 2000 | Feasibility‑first ranking for multi‑objective optimization. |

---

## How DD‑HPSO Extends These Foundations
| Feature | Original Paper | DD‑HPSO Implementation |
|---|---|---|
| **Baseline Scheduler** | HEFT (makespan‑focused) | Uses HEFT **as a seed** for every PSO particle, guaranteeing a feasible starting point. |
| **Optimization Engine** | PSO (cost‑deadline) | Standard PSO with **HEFT‑seeded particles**, plus a custom encoding for task‑VM mapping. |
| **Constraint Handling** | No explicit multi‑objective handling | Applies **Deb’s rules** – feasibility first, then minimize normalized objective F, then minimize violation. |
| **Data Transfer** | No duplication | Implements **selective duplication** (Liu 2013) with a strict extra‑period budget (`max_extra_periods=0`). |
| **Scalability** | Evaluated on small workflows (≤ 30 tasks) | Tested on **7 real scientific workflows** up to 100 tasks, with 10 seeds each. |

---

## Quantitative Comparison (derived from `research.md`)
| Metric | HEFT (baseline) | DD‑HPSO (ours) | Improvement |
|---|---|---|---|
| **Cost vs HEFT** | 0 % (baseline) | **‑13.1 %** | Lower cloud expenditure. |
| **Energy vs HEFT** | 0 % (baseline) | **‑8.2 %** | Reduced energy consumption. |
| **Makespan vs HEFT** | 0 % (baseline) | **+7.7 %** | Slightly longer but still within deadline constraints. |
| **Deadline Success Rate** | 100 % (by definition) | **100 %** | Guarantees feasibility for all runs. |

---

## Visual Summary
![Paper Comparison Chart](file:///C:/Users/itsni/Desktop/CC-project/results/plots/paper_comparison.png)

---

## Discussion
- **Reliability:** By seeding PSO with a proven HEFT schedule and using Deb’s feasibility‑first rule, DD‑HPSO never violates deadlines, unlike the vanilla PSO implementation from the 2015 paper, which often fails on tight deadlines (as shown in our experimental results).
- **Cost & Energy:** The selective duplication strategy (Liu 2013) allows us to keep data‑transfer overhead low, yielding the observed **‑8 % energy** reduction while still achieving **‑13 % cost** savings relative to pure HEFT.
- **Scalability:** Our experiments on larger workflows (Montage 100, CyberShake 100, Inspiral 100) demonstrate that the approach scales beyond the scope of the original papers.

---

## References (from `research.md`)
1. **Cheng, et al.** *Path‑Aware Scheduling for Cost Optimization of Deadline‑Constrained Scientific Workflows*, IEEE Transactions on Cloud Computing, 2025. DOI: 10.1109/TCC.2025.3612584
2. **Wang, et al.** *WPSO: A PSO‑Based Algorithm for Cost‑Effective Deadline‑Constrained Workflow Scheduling*, IEEE ICCCBDA, 2025. DOI: 10.1109/ICCCBDA64898.2025.11030517
3. **Awad, et al.** *Efficient Workflow Scheduling in Fog‑Cloud Collaboration Using Hybrid IPSO‑GWO*, Scientific Reports, 2025. DOI: 10.1038/s41598‑025‑34462‑w

---

*All numbers are derived from the full experimental grid stored in `results/results.csv` and visualized in `results/plots/`.*

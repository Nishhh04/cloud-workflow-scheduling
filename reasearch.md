# Scientific Workflow Scheduling on Clouds: Summary of Three Papers

This document summarises three papers on scheduling scientific workflows (DAGs) on cloud infrastructure. For each paper it covers the problem, the approach, the main results, and the gaps that remain.

| # | Paper | Venue | Core idea |
|---|-------|-------|-----------|
| 1 | Genez et al., *Scheduling Scientific Workflows on Clouds Using a Task Duplication Approach* | IEEE/ACM UCC 2018 | Duplicate critical parent tasks to trade communication for computation (HEFT-TD, Lookahead-TD) |
| 2 | Rodriguez & Buyya, *Deadline Based Resource Provisioning and Scheduling Algorithm for Scientific Workflows on Clouds* | IEEE Trans. Cloud Computing, 2014 | Particle Swarm Optimization (PSO) to minimise cost under a deadline, jointly deciding provisioning and scheduling |
| 3 | Li et al., *Cost and Energy Aware Scheduling Algorithm for Scientific Workflows with Deadline Constraint in Clouds* (CEAS) | IEEE Trans. Services Computing, 2018 | Five-stage heuristic (VM selection, task merging, VM reuse, DVFS slack reclamation) to cut cost and energy under a deadline |

---

## 1. Task Duplication for Workflow Scheduling (Genez et al., 2018)

### Problem
Data transfers between dependent tasks leave cloud VMs idle, which stretches the makespan and the rental period, and therefore raises cost. Existing work mostly tries to detect network conditions or manipulate bandwidth information. It does not exploit task duplication to avoid the transfers.

### Approach
- Extends **HEFT** and its **Lookahead** variant with task duplication, giving **HEFT-TD** and **Lookahead-TD**.
- For each task, the algorithm temporarily duplicates its *critical parent* (the parent with the highest upward rank) on each candidate VM. It keeps the duplicate only if the task's earliest finish time (EFT) improves.
- In Lookahead-TD, the decision is judged on the maximum EFT of the task's *children*, so a duplicate that helps the task but delays its children is rejected.
- A **rescheduling step** removes the original parent when all its children have been served by duplicates.
- Evaluation: in-house Java simulator, 100-task synthetic Montage, Epigenome, CyberShake and LIGO workflows, 5–30 heterogeneous single-core VMs, CCR from 0.5 to 10, 500 runs.
- Cost model: price is proportional to VM processing capacity, charged per unit of time used.

### Key results (averages across all CCR and VM counts)

| Workflow | Algorithm | Makespan | Data transferred | Monetary cost |
|---|---|---|---|---|
| Montage | HEFT-TD vs HEFT | −18% | −35% | −15% |
| Montage | Lookahead-TD vs Lookahead | −7% | −12% | +2% |
| Epigenome | HEFT-TD vs HEFT | −11% | −22% | +45% |
| Epigenome | Lookahead-TD vs Lookahead | −9% | −36% | +26% |
| CyberShake | HEFT-TD vs HEFT | −4% | −12% | +37% |
| CyberShake | Lookahead-TD vs Lookahead | −10% | −30% | −5% |
| LIGO | HEFT-TD vs HEFT | −4% | about 7× more | +10% |
| LIGO | Lookahead-TD vs Lookahead | −22% | +65% | −25% |

Overall, HEFT-TD cut makespan by about 9% on average and Lookahead-TD by about 12%. Lookahead-TD was clearly the stronger of the two. Gains grow with CCR on communication-heavy workflows such as Montage, and are small when CCR is low.

### What it lacks / open gaps
- **No deadline or budget constraint.** Both base algorithms are makespan-driven and not cost-aware. Cost savings are described as "incidental", and for Epigenome, CyberShake and LIGO under HEFT-TD, cost actually rises (+10% to +45%).
- **Inconsistent benefit across workflow types.** Duplication does not pay off for LIGO under HEFT-TD (7× more data transferred), nor for Epigenome at high CCR.
- **Large runtime overhead.** The authors report the algorithms running roughly 10 to 100 times slower than the standard versions. Lookahead-TD takes around 100 seconds for a 100-task workflow, and scalability to 1,000+ tasks is not shown.
- **Simplified cloud model.**
  - Fixed pool of VMs, with no elastic provisioning decisions.
  - Single-core VMs only.
  - Dedicated resources, so no performance variability.
  - No VM boot time.
  - No hourly billing granularity.
  - Cost is only an approximation based on resource usage time.
- **Synthetic, simulation-only evaluation**, with a single workflow size (100 tasks).
- **Duplicates are chosen reactively** during scheduling. The authors suggest identifying beneficial duplicates in advance as future work.
- Minor inconsistency: the motivating example reports data-transfer figures of 192 vs 208 in the text, while Fig. 2 shows 175 vs 208.

---

## 2. PSO-Based Provisioning and Scheduling (Rodriguez & Buyya, 2014)

### Problem
Grid/cluster scheduling algorithms assume a static resource pool and focus on makespan. IaaS clouds differ in several ways: resources are elastic, heterogeneous and billed per time interval, VMs take time to boot, and performance varies (the paper cites about 24% CPU variability on EC2). The goal is to **minimise total execution cost while meeting a deadline**, deciding *which* VMs to lease, *when* to lease and release them, and *where* each task runs.

### Approach
- Models provisioning and scheduling jointly as a constrained optimisation problem solved by **Particle Swarm Optimization**.
- **Encoding:** a particle has one dimension per task, and the integer part of each coordinate is the VM index assigned to that task.
- **Initial resource pool:** one VM of each type for each task in the maximum parallel set, which limits the search space while preserving heterogeneity.
- **Fitness:** total execution cost (TEC) under hourly billing. The deadline is enforced with Deb's constraint-handling rules, which prefer feasible solutions over infeasible ones, and among infeasible ones the one with the smaller violation.
- A schedule-generation algorithm converts a particle into a full schedule, including lease start and end times, boot time (97 s), and data transfer waits.
- Variants: **PSO** (heterogeneous VMs) and **PSO_HOM** (single VM type).
- Evaluation: CloudSim with Montage, LIGO, SIPHT and CyberShake. Six EC2-like VM types, four deadline intervals, performance degradation of up to 24%, bandwidth degradation of up to 19%, and 10% task-size noise. Compared against **IC-PCP** (static) and **SCS** (dynamic).
- Parameters used: c1 = c2 = 2.0, inertia 0.5, 100 particles.

### Key results
- **IC-PCP** often misses deadlines (0% hit rate on early intervals for LIGO, and under 50% in most cases for CyberShake). The authors attribute this to it ignoring boot time and performance variation, even though it tends to produce the cheapest schedules.
- **PSO and SCS** meet deadlines in most cases (often 100%).
- Where both PSO and SCS meet the deadline, **PSO is cheaper**, and sometimes also faster.
- PSO beats PSO_HOM, which shows that heterogeneity matters.
- Performance is best on smaller workflows. The initial pool selection strategy has a significant impact.

### What it lacks / open gaps
- **Offline/static only.** The schedule is produced up front, so it cannot react at runtime to changing conditions (an advantage SCS holds).
- **Scalability and runtime.** The complexity is O(N·T²·R) per iteration. The paper also describes PSO as having exponential complexity overall, versus polynomial for the heuristics. Performance degrades on larger workflows, and no execution-time comparison is shown.
- **High variability in results.** Makespans vary more between runs than for the heuristics, which is less predictable for users.
- **Sensitivity to the initial VM pool**, which is acknowledged as an open problem. A pool of one VM per type per task performed worse.
- **Cost/makespan trade-off is not controllable.** The solution sometimes yields lower makespans at higher cost, while some users may prefer finishing close to the deadline at lower cost.
- **Model simplifications.**
  - Single data centre or region, with uniform bandwidth.
  - No data transfer costs.
  - No check that a VM has enough memory for a task.
  - Task sizes and runtimes assumed known in advance.
- **No energy awareness** and no task duplication or merging.
- **Limited baselines** (two algorithms) and simulation-only validation. Implementation in a real workflow engine is listed as future work, as is comparison with other meta-heuristics such as genetic algorithms.

---

## 3. CEAS: Cost and Energy Aware Scheduling (Li et al., 2018)

### Problem
Big-data scientific workflows can run for hours and are billed per whole hour on commercial clouds, so partially used VM hours are wasted money. Data centres also consume substantial energy (the paper cites about 0.5% of world power use). List schedulers such as HEFT, MOHEFT, EES and EHEFT reserve VMs for the whole makespan, which wastes cost and energy. The goal is to **minimise monetary cost and then reduce energy, subject to a deadline**.

### Approach
CEAS chains five polynomial-time sub-algorithms:

1. **VM selection** (O(Kn²(n+e))). Each task gets a *sub-makespan*, which is the deadline distributed in proportion to its fastest runtime. A *cost utility* (workload per unit of cost under hourly billing) picks the best VM type that fits within that sub-makespan.
2. **Sequence task merging** (O(Kn)). Chains of one-parent/one-child tasks are merged onto one VM when this is not more expensive, which also removes data transfer.
3. **Parallel task merging** (O(n² log n)). Sibling tasks with identical predecessors and successors are merged if the merged runtime stays within the group's maximum sub-makespan.
4. **VM reuse** (O(nL)). Idle time in already-leased VM hours is used for ready tasks when that is cheaper than leasing a new VM.
5. **Task slacking** (O(n²)). Slack time of non-critical tasks is reclaimed by lowering CPU voltage and frequency (DVFS), which reduces dynamic energy.

- Evaluation: CloudSim with Montage, LIGO, SIPHT and CyberShake. Ten VM types with infinite instances, a constant 1 GB bandwidth, and deadlines of 5.5 to 10 hours (minimum makespan about 5 hours). Compared against HEFT and MOHEFT on cost, and against EES and EHEFT on energy.

### Key results
- Each added sub-algorithm lowers cost or energy further than the one before it (the self-comparison ablation).
- CEAS has the lowest cost among CEAS, MOHEFT and HEFT. HEFT is the most expensive and flat across deadlines, because it always picks the fastest VM.
- CEAS has the lowest energy among CEAS, EHEFT and EES. Cost and energy fall as the deadline is relaxed.
- All five sub-algorithms are polynomial.

### What it lacks / open gaps
- **Results are shown only in plots.** The text gives no numerical percentage savings, no confidence intervals and no repeated-run statistics.
- **Narrow and dated baselines.** The comparison uses HEFT-family and slack-based energy schedulers. It does not compare against other deadline-constrained cloud algorithms (such as the PSO approach it cites, or IC-PCP, SCS), even though those are the closest competitors. The MOHEFT comparison is somewhat unfavourable because MOHEFT is modelled with per-second billing and whole-makespan leasing.
- **Idealised cloud model.**
  - No VM boot time.
  - No performance variability.
  - Constant bandwidth.
  - Data transfer cost ignored.
  - Perfectly known workloads.
  - A single entry and a single exit task assumed.
  - Synthetic workloads and data sizes.
- **Strong assumption on DVFS.** It assumes that tenants can control per-VM CPU frequency and that frequency scales proportionally with computing capacity. Public IaaS providers generally do not expose this to users. The energy saving is therefore mainly relevant to the provider's scheduler.
- **Simplified energy model.** Only dynamic CPU energy is modelled. Static power, memory and disk energy are omitted (listed as future work), and electricity cost is not modelled.
- **Greedy heuristics with no optimality guarantee**, and decisions made step by step (for example, random task selection in VM reuse), which could miss better global solutions.
- **No duplication, and no adaptation to runtime deviations** from the estimated runtimes.
- The paper claims users can verify the scheduler's honesty from the pricing model, but gives no mechanism for this.

---

## Side-by-Side Comparison

| Aspect | Genez et al. (Task Duplication) | Rodriguez & Buyya (PSO) | Li et al. (CEAS) |
|---|---|---|---|
| Primary objective | Makespan (plus lower data transfers) | Minimise cost | Minimise cost, then energy |
| Constraint | None | Deadline | Deadline |
| Technique | List scheduling (HEFT/Lookahead) + duplication | Meta-heuristic (PSO) | Multi-stage heuristic |
| Provisioning decided? | No (fixed VM pool) | Yes (VM number, type, lease times) | Yes (VM type per task, reuse) |
| Billing model | Pay per unit time, proportional to capacity | Per billing period (hourly) | Hourly |
| Heterogeneous VMs | Yes | Yes | Yes |
| VM boot time | No | Yes | No |
| Performance variability | No | Yes | No |
| Data-transfer handling | Reduced via duplication | Modelled as transfer time | Reduced via merging |
| Energy | No | No | Yes (DVFS) |
| Static or dynamic | Static | Static | Static |
| Baselines | HEFT, Lookahead | IC-PCP, SCS | HEFT, MOHEFT, EES, EHEFT |
| Main weakness | Cost-unaware, uneven gains, slow | Slow, variable, pool-sensitive | Idealised model, DVFS assumption, no numbers in text |

---

## Cross-Cutting Gaps and Research Opportunities

1. **No paper combines duplication, deadline-aware cost minimisation, and hourly billing.** Duplication reduces data transfer but may add paid compute time. How this interacts with deadlines and billing intervals is unexplored.
2. **Realism of the cloud model.** Only the PSO paper accounts for boot time and performance variability. None of the three models inter-region data transfer cost, memory constraints, spot or preemptible instances, or failures.
3. **Static plans in dynamic environments.** All three produce offline schedules. Hybrid approaches, with a static plan plus runtime re-planning, are not addressed.
4. **Multi-objective trade-offs.** Cost, makespan, data movement and energy are each treated mostly separately. Pareto-style or user-tunable trade-offs (for example, finish earlier at higher cost versus closer to the deadline at lower cost) are not covered.
5. **Scalability.** The tested workflows are small (about 100 tasks). The authors of the first two papers note runtime and search-space issues. Behaviour on 1,000+ task workflows with the heavier algorithms is unclear.
6. **Validation.** All results come from simulation with synthetic or generated workflows. There is no deployment on a real cloud or in a workflow engine.
7. **Practicality of energy control.** Energy-aware DVFS is feasible for providers, but tenant-side scheduling cannot control it on public IaaS. How a tenant-side and a provider-side scheduler should cooperate is open.
8. **Stronger comparisons.** None of the papers benchmarks against the others' families of approaches under common conditions, so their reported gains are not directly comparable.
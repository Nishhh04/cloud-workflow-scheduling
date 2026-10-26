"""
Module 6: pso.py
================
PURPOSE: Implement PSO (Particle Swarm Optimization) for workflow scheduling,
         with HEFT seeding and Deb's constraint-handling rules.

CONCEPT (for your presentation):
  PSO is a nature-inspired search algorithm. Imagine a swarm of birds looking
  for food — each bird remembers the best spot IT found (pbest) and knows the
  best spot ANY bird found (gbest). Birds fly toward both.

  IN SCHEDULING:
    - A "particle" = one complete task-to-VM assignment (one schedule)
    - A particle is a vector of length n_tasks.
      x[d] in [0, pool_size) → task d runs on VM floor(x[d])
    - We run N particles for I iterations, updating positions with:
        v(t+1) = w·v(t) + c1·r1·(pbest - x) + c2·r2·(gbest - x)
        x(t+1) = x(t) + v(t+1)

  KEY INNOVATIONS vs plain PSO:
  1. HEFT SEEDING: Particle 0 = HEFT's assignment (x[d] = assign[d] + 0.5)
     Particles 1..N-1 = HEFT + random 10-20% perturbation
     → Guaranteed: gbest is never worse than HEFT (Deb's rules ensure this)
     → Reduces convergence time and run-to-run variability

  2. DEB'S RULES (constraint handling):
     - Feasible solution (meets deadline D) always beats infeasible
     - Both feasible: lower F (normalised objective) wins
     - Both infeasible: lower V (deadline violation) wins
     This is smarter than penalizing infeasible solutions with a big number.

  3. ADAPTIVE INERTIA: w decreases linearly from w_max to w_min.
     High w early = explore broadly; low w late = refine around good solutions.

  FITNESS FUNCTION:
    F = w1·(C/C_ref) + w2·(E/E_ref) + w3·(M/M_ref)
    where C_ref, E_ref, M_ref come from the HEFT schedule (so F=1.0 = same as HEFT).
    We want F < 1.0 (better than HEFT).

VARIANTS (ablation study):
  - PSO_PLAIN   : random initialization, no duplication
  - PSO_SEEDED  : HEFT seeding, no duplication
  - PSO_DUP     : random initialization, with duplication
  - DD_HPSO     : HEFT seeding + duplication (the full algorithm)
"""

import random
import math
import numpy as np
from dataclasses import dataclass, field

from .workflow import Workflow
from .cloud import CloudConfig, DEFAULT_CONFIG
from .schedule import Schedule, ScheduleBuilder, evaluate
from .heft import heft, get_rank_order
from .deadline import DeadlineInfo, compute_violation


# ── PSO Configuration ─────────────────────────────────────────────────────────

@dataclass
class PSOConfig:
    """All tunable PSO hyperparameters in one place.

    SPEED GUIDE:
      - Quick/demo  : swarm_size=15, n_iterations=40   (~2s per run)
      - Standard    : swarm_size=20, n_iterations=80   (~8s per run)
      - Final/paper : swarm_size=40, n_iterations=150  (~30s per run)
    """
    swarm_size:    int   = 15       # N: particles (scale up for final runs)
    n_iterations:  int   = 40       # I: iterations (scale up for final runs)
    w_max:         float = 0.9      # inertia weight start (explore)
    w_min:         float = 0.4      # inertia weight end   (exploit)
    c1:            float = 2.0      # cognitive coefficient (pull to pbest)
    c2:            float = 2.0      # social coefficient   (pull to gbest)
    perturb_rate:  float = 0.15     # fraction of coords to randomize in seed copies
    w1:            float = 0.4      # weight for cost in F
    w2:            float = 0.3      # weight for energy in F
    w3:            float = 0.3      # weight for makespan in F
    use_seeding:   bool  = True     # True = HEFT seeding; False = random init
    use_dup:       bool  = False    # True = apply selective duplication per decode
    seed:          int   = 42       # random seed for reproducibility


DEFAULT_PSO_CONFIG = PSOConfig()


# ── Particle State ────────────────────────────────────────────────────────────

@dataclass
class Particle:
    x:       np.ndarray   # position vector [0, pool_size)
    v:       np.ndarray   # velocity vector
    pbest_x: np.ndarray   # best position this particle ever found
    pbest_f: float = float("inf")   # fitness at pbest
    pbest_v: float = float("inf")   # violation at pbest
    pbest_feasible: bool = False


# ── Deb's Constraint-Handling Rules ──────────────────────────────────────────

def is_better(a_f, a_v, a_feas, b_f, b_v, b_feas) -> bool:
    """
    Return True if solution A is better than solution B using Deb's rules.

    Rules (in order of priority):
    1. Feasible > Infeasible
    2. Both feasible: lower F wins
    3. Both infeasible: lower V (violation) wins
    """
    if a_feas and not b_feas:   return True   # A feasible, B not
    if not a_feas and b_feas:   return False  # B feasible, A not
    if a_feas and b_feas:       return a_f < b_f   # both feasible: lower cost
    return a_v < b_v            # both infeasible: lower violation


# ── Decode Particle to Schedule ───────────────────────────────────────────────

def decode_particle(x: np.ndarray, wf: Workflow, pool: list,
                    rank_order: list, config: CloudConfig,
                    dup_fn=None) -> tuple[Schedule, list]:
    """
    Convert a PSO particle position to a Schedule.

    The particle encodes WHICH VM each task runs on:
        vm_idx = floor(x[d])  clamped to [0, pool_size-1]

    Task ORDER is fixed to rank_order (decreasing upward rank),
    so every particle decodes to a VALID topological schedule.
    This is why task order is NOT part of the particle.

    Returns (schedule, assign_array).
    """
    pool_size = len(pool)
    assign = [int(np.clip(np.floor(x[d]), 0, pool_size - 1))
              for d in range(wf.n_tasks)]

    schedule = evaluate(wf, pool, rank_order, assign, config, dup_fn)
    return schedule, assign


# ── Fitness Evaluation ────────────────────────────────────────────────────────

def compute_fitness(schedule: Schedule, deadline_info: DeadlineInfo,
                    pso_cfg: PSOConfig) -> tuple[float, float, bool]:
    """
    Compute (F, V, feasible) for one schedule.

    F = w1·(C/C_ref) + w2·(E/E_ref) + w3·(M/M_ref)
    V = max(0, M - D)
    feasible = (M <= D)
    """
    C_ref = deadline_info.c_heft
    E_ref = deadline_info.e_heft
    M_ref = deadline_info.m_heft
    D     = deadline_info.deadline

    # Normalised objective
    F = (pso_cfg.w1 * schedule.cost    / max(C_ref, 1e-9) +
         pso_cfg.w2 * schedule.energy  / max(E_ref, 1e-9) +
         pso_cfg.w3 * schedule.makespan / max(M_ref, 1e-9))

    V = max(0.0, schedule.makespan - D)
    feasible = (V == 0.0)
    return F, V, feasible


# ── PSO Main Loop ─────────────────────────────────────────────────────────────

def run_pso(wf: Workflow, pool: list, deadline_info: DeadlineInfo,
            pso_cfg: PSOConfig = DEFAULT_PSO_CONFIG,
            config: CloudConfig = DEFAULT_CONFIG,
            dup_fn=None) -> tuple[Schedule, list, list]:
    """
    Run PSO and return (best_schedule, best_assign, convergence_curve).

    convergence_curve[iteration] = best F value seen so far
    (used for convergence plots in the report).
    """
    rng = random.Random(pso_cfg.seed)
    np.random.seed(pso_cfg.seed)

    n_tasks   = wf.n_tasks
    pool_size = len(pool)

    # ── Get HEFT schedule and rank order ──────────────────────────────────
    heft_sched, heft_assign, rank_order = heft(wf, pool, config)

    # ── Initialize swarm ──────────────────────────────────────────────────
    vel_clamp = pool_size / 4.0  # velocity clamped to ±V/4

    particles: list[Particle] = []

    for i in range(pso_cfg.swarm_size):
        if pso_cfg.use_seeding and i == 0:
            # Particle 0 = exact HEFT assignment (+ 0.5 to keep floor stable)
            x = np.array([heft_assign[d] + 0.5 for d in range(n_tasks)],
                         dtype=float)
        elif pso_cfg.use_seeding and i > 0:
            # Particles 1..N-1 = HEFT + perturb random fraction of coords
            x = np.array([heft_assign[d] + 0.5 for d in range(n_tasks)],
                         dtype=float)
            n_perturb = max(1, int(pso_cfg.perturb_rate * n_tasks))
            perturb_dims = rng.sample(range(n_tasks), n_perturb)
            for d in perturb_dims:
                x[d] = rng.uniform(0, pool_size)
        else:
            # Fully random initialization (PSO-plain)
            x = np.random.uniform(0, pool_size, n_tasks)

        # Clip to valid range
        x = np.clip(x, 0, pool_size - 0.001)

        # Initial velocity = 0 (or small random)
        v = np.zeros(n_tasks)

        p = Particle(x=x, v=v, pbest_x=x.copy())
        particles.append(p)

    # ── Evaluate initial swarm ────────────────────────────────────────────
    gbest_x     = None
    gbest_f     = float("inf")
    gbest_v     = float("inf")
    gbest_feas  = False
    gbest_sched = None
    gbest_assign = None

    for p in particles:
        sched, assign = decode_particle(p.x, wf, pool, rank_order, config, dup_fn)
        F, V, feas    = compute_fitness(sched, deadline_info, pso_cfg)

        p.pbest_f       = F
        p.pbest_v       = V
        p.pbest_feasible = feas

        if is_better(F, V, feas, gbest_f, gbest_v, gbest_feas):
            gbest_x      = p.x.copy()
            gbest_f      = F
            gbest_v      = V
            gbest_feas   = feas
            gbest_sched  = sched
            gbest_assign = assign

    convergence = [gbest_f]  # track gbest F per iteration for plots

    # ── Main PSO loop ─────────────────────────────────────────────────────
    for iteration in range(pso_cfg.n_iterations):
        # Linearly decreasing inertia: explore early, exploit late
        w = pso_cfg.w_max - (pso_cfg.w_max - pso_cfg.w_min) * iteration / pso_cfg.n_iterations

        for p in particles:
            r1 = np.random.rand(n_tasks)
            r2 = np.random.rand(n_tasks)

            # Velocity update
            p.v = (w * p.v
                   + pso_cfg.c1 * r1 * (p.pbest_x - p.x)
                   + pso_cfg.c2 * r2 * (gbest_x   - p.x))

            # Clamp velocity to [-vel_clamp, +vel_clamp]
            p.v = np.clip(p.v, -vel_clamp, vel_clamp)

            # Position update + wrap to valid range
            p.x = np.clip(p.x + p.v, 0, pool_size - 0.001)

            # Evaluate new position
            sched, assign = decode_particle(p.x, wf, pool, rank_order, config, dup_fn)
            F, V, feas    = compute_fitness(sched, deadline_info, pso_cfg)

            # Update personal best (pbest)
            if is_better(F, V, feas, p.pbest_f, p.pbest_v, p.pbest_feasible):
                p.pbest_x       = p.x.copy()
                p.pbest_f       = F
                p.pbest_v       = V
                p.pbest_feasible = feas

            # Update global best (gbest)
            if is_better(F, V, feas, gbest_f, gbest_v, gbest_feas):
                gbest_x      = p.x.copy()
                gbest_f      = F
                gbest_v      = V
                gbest_feas   = feas
                gbest_sched  = sched
                gbest_assign = assign

        convergence.append(gbest_f)

    return gbest_sched, gbest_assign, convergence


# ── Named variants for the ablation study ────────────────────────────────────

def pso_plain(wf, pool, deadline_info, seed=42, config=DEFAULT_CONFIG):
    """PSO-plain: random start, no duplication."""
    cfg = PSOConfig(use_seeding=False, use_dup=False, seed=seed)
    return run_pso(wf, pool, deadline_info, cfg, config, dup_fn=None)


def pso_seeded(wf, pool, deadline_info, seed=42, config=DEFAULT_CONFIG):
    """PSO-seeded: HEFT seed, no duplication."""
    cfg = PSOConfig(use_seeding=True, use_dup=False, seed=seed)
    return run_pso(wf, pool, deadline_info, cfg, config, dup_fn=None)


def pso_dup(wf, pool, deadline_info, dup_fn, seed=42, config=DEFAULT_CONFIG):
    """PSO-dup: random start, with duplication."""
    cfg = PSOConfig(use_seeding=False, use_dup=True, seed=seed)
    return run_pso(wf, pool, deadline_info, cfg, config, dup_fn=dup_fn)


def dd_hpso(wf, pool, deadline_info, dup_fn, seed=42, config=DEFAULT_CONFIG):
    """DD-HPSO (full algorithm): HEFT seed + duplication."""
    cfg = PSOConfig(use_seeding=True, use_dup=True, seed=seed)
    return run_pso(wf, pool, deadline_info, cfg, config, dup_fn=dup_fn)


# ── Quick sanity check ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from scheduler.workflow import load_workflow
    from scheduler.cloud import make_pool
    from scheduler.deadline import compute_deadlines
    from scheduler.schedule import ScheduleBuilder

    wf   = load_workflow(r"..\data\workflows\Montage_50.xml")
    pool = make_pool(DEFAULT_CONFIG, instances_per_type=5)

    # Get HEFT as reference
    heft_sched, heft_assign, rank_order = heft(wf, pool)

    # Rebuild builder to get per-task AFTs
    b = ScheduleBuilder(wf, pool)
    for tid in rank_order:
        est, aft = b.try_place(tid, heft_assign[tid])
        b.commit(tid, heft_assign[tid], est, aft)

    dl_infos = compute_deadlines(wf, heft_sched, list(b.aft))
    dl_info  = dl_infos[1]  # f=1.5

    print(f"Deadline: {dl_info.deadline:.2f}s  (f={dl_info.factor})")
    print(f"HEFT: makespan={heft_sched.makespan:.2f}s  cost=${heft_sched.cost:.4f}")
    print()

    print("Running PSO-seeded ...")
    sched, _, conv = pso_seeded(wf, pool, dl_info, seed=42)
    print(f"PSO-seeded: makespan={sched.makespan:.2f}s  cost=${sched.cost:.4f}  "
          f"energy={sched.energy/3600:.2f}Wh  "
          f"met_deadline={sched.makespan <= dl_info.deadline}")
    print(f"Convergence: start_F={conv[0]:.4f} -> end_F={conv[-1]:.4f}")

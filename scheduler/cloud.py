"""
Module 2: cloud.py
==================
PURPOSE: Define the cloud environment — what types of VMs exist and their properties.

CONCEPT (for your presentation):
  - In a real cloud (like AWS/Azure), you can rent different "instance types".
  - Each type has a different processing speed, cost per hour, and power usage.
  - We model 4 VM types: small, medium, large, xlarge.
  - Key insight: billing is per HOUR (rounded UP), so a task that uses a VM for
    3601 seconds costs 2 billing periods, not 1. This is the "billing rounding" effect.
  - VMs also take 97 seconds to BOOT before they can run any task.
  - A VM sitting idle between tasks still consumes idle power (P_idle).

WHY THIS MATTERS for our algorithm:
  - HEFT ignores cost → it picks the FASTEST VM → expensive!
  - Our algorithm (PSO-based) finds VMs that are fast ENOUGH but cheaper.
  - The energy model: E = P_busy × time_running + P_idle × time_waiting
"""

from dataclasses import dataclass


# ── VM Type Definition ───────────────────────────────────────────────────────

@dataclass(frozen=True)  # frozen=True makes it immutable (safe to use as dict key)
class VMType:
    """Represents one class of cloud VM (e.g., 'm5.large' on AWS)."""
    name: str           # human-readable label
    mips: float         # processing speed in Million Instructions Per Second
    price_per_period: float  # cost in $ per billing period (1 hour)
    power_busy: float   # Watts when actively running a task
    power_idle: float   # Watts when booted but waiting (idle)


# ── The VM Catalog ────────────────────────────────────────────────────────────
# These values come directly from the implementation guide (slide 9 / Section 1).
# We use exactly 4 types to keep the search space manageable.

VM_TYPES = [
    VMType(name="small",  mips=1000, price_per_period=0.10, power_busy=100, power_idle=65),
    VMType(name="medium", mips=2000, price_per_period=0.19, power_busy=170, power_idle=110),
    VMType(name="large",  mips=4000, price_per_period=0.36, power_busy=300, power_idle=190),
    VMType(name="xlarge", mips=8000, price_per_period=0.70, power_busy=520, power_idle=330),
]

NUM_VM_TYPES = len(VM_TYPES)  # = 4; PSO particles use values in [0, NUM_VM_TYPES)


# ── Cloud Configuration ───────────────────────────────────────────────────────

@dataclass
class CloudConfig:
    """
    Global cloud parameters shared by all algorithms.
    Making these a single object means you can pass one thing around
    instead of 5 separate constants.
    """
    billing_period: float = 3600.0   # seconds per billing period (1 hour)
    boot_time: float      = 97.0     # seconds to boot a VM before it's usable
    bandwidth: float      = 20.0     # MB/s inter-VM network bandwidth
                                     # (intra-VM = ∞, i.e., transfer time = 0)
    vm_types: list = None            # list of VMType objects

    def __post_init__(self):
        if self.vm_types is None:
            self.vm_types = VM_TYPES


# The default config used everywhere in the project
DEFAULT_CONFIG = CloudConfig()


# ── Pool: a list of VM instances ─────────────────────────────────────────────
# In our simulator, the "pool" is simply an ordered list of VMType objects.
# Index i in the pool = one VM instance of that type.
# PSO particle dimension d -> floor(x[d]) selects the pool index.
#
# We create a pool with multiple instances of each type so the PSO has
# enough choices. A pool of 20 means 20 concurrent VMs available.

def make_pool(config: CloudConfig = DEFAULT_CONFIG, instances_per_type: int = 5) -> list:
    """
    Create a flat list of VM instances (repeating each type).
    e.g., [small, small, small, small, small, medium, medium, ...] with 5 of each.

    WHY: PSO encodes each task as an index into this pool.
         floor(particle[task_d]) in [0, pool_size) -> which VM to use.
    """
    pool = []
    for vm_type in config.vm_types:
        for _ in range(instances_per_type):
            pool.append(vm_type)
    return pool


# ── Helper Formulas ───────────────────────────────────────────────────────────

def execution_time(task_length_mi: float, vm: VMType) -> float:
    """
    ET(i, k) = L_i / s_k
    How many seconds does task i take on VM type k?
    L_i = task length in MI, s_k = VM speed in MIPS.
    """
    return task_length_mi / vm.mips


def transfer_time(data_mb: float, config: CloudConfig = DEFAULT_CONFIG) -> float:
    """
    TT(i, j) = d_ij / B   (0 if tasks are on the same VM)
    How many seconds to send data_mb MB over the network?
    """
    if data_mb <= 0:
        return 0.0
    return data_mb / config.bandwidth


def billing_cost(lease_duration_s: float, vm: VMType,
                 config: CloudConfig = DEFAULT_CONFIG) -> float:
    """
    C_k = ceil(lease_duration / billing_period) × price_per_period
    Cost is rounded UP to the nearest billing period per VM.
    This is the key difference from real-time cost — even 1 extra second
    costs a full hour!
    """
    import math
    periods = math.ceil(lease_duration_s / config.billing_period)
    return periods * vm.price_per_period


def energy_consumption(busy_time_s: float, lease_duration_s: float,
                       vm: VMType) -> float:
    """
    E_k = P_busy × T_busy + P_idle × T_idle
    where T_idle = lease_duration - T_busy
    Returns energy in Watt-seconds (Joules). Divide by 3600 for Wh.
    """
    idle_time = max(0.0, lease_duration_s - busy_time_s)
    return vm.power_busy * busy_time_s + vm.power_idle * idle_time


# ── Quick sanity check ────────────────────────────────────────────────────────

if __name__ == "__main__":
    cfg = DEFAULT_CONFIG
    pool = make_pool(cfg, instances_per_type=5)
    print(f"Pool size: {len(pool)} VM instances")
    print(f"Boot time: {cfg.boot_time}s | Billing period: {cfg.billing_period}s | Bandwidth: {cfg.bandwidth} MB/s\n")
    print(f"{'Type':<10} {'MIPS':>6} {'$/hr':>6} {'P_busy':>8} {'P_idle':>8}")
    print("-" * 44)
    for vm in cfg.vm_types:
        print(f"{vm.name:<10} {vm.mips:>6} {vm.price_per_period:>6.2f} "
              f"{vm.power_busy:>8} {vm.power_idle:>8}")

    # Example calculation
    print("\n--- Example: 1000 MI task on 'medium' VM ---")
    vm = VM_TYPES[1]  # medium
    et = execution_time(1000, vm)
    print(f"  Execution time : {et:.2f}s")
    print(f"  Transfer 50MB  : {transfer_time(50, cfg):.2f}s")
    print(f"  Billing 3700s  : ${billing_cost(3700, vm, cfg):.2f} (2 periods)")
    print(f"  Energy 3600s   : {energy_consumption(et, 3600, vm):.0f} W·s")

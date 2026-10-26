"""
Module 1: workflow.py
=====================
PURPOSE: Parse a Pegasus DAX/XML workflow file and build a Directed Acyclic Graph (DAG).

CONCEPT (for your presentation):
  - A workflow is a set of tasks (jobs) with dependencies between them.
  - If task B needs the output of task A, then B cannot start until A finishes.
  - This forms a DAG: nodes = tasks, directed edges = data dependencies.
  - Each edge has a "weight" = how much data flows from parent to child (in MB).
  - We convert runtime_seconds -> MI (Million Instructions) using mean MIPS so
    the task length is hardware-independent (the scheduler decides which VM runs it).

XML STRUCTURE we're parsing:
  <job id="ID00000" runtime="13.08">          <- task node
    <uses file="X" link="input"  size=".."/>  <- input file consumed by this task
    <uses file="Y" link="output" size=".."/>  <- output file produced by this task
  </job>
  <child ref="ID00005">                       <- dependency edge
    <parent ref="ID00000"/>                   <- ID00000 must finish before ID00005 starts
  </child>
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


# ── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class Task:
    """Represents one node in the workflow DAG."""
    task_id: int          # integer index (0-based) for fast array indexing
    name: str             # original string ID like "ID00000"
    runtime: float        # execution time in seconds (from XML attribute)
    length_mi: float      # length in Million Instructions = runtime × mean_MIPS
                          # This makes scheduling hardware-independent
    parents: list = field(default_factory=list)   # list of parent task_ids
    children: list = field(default_factory=list)  # list of child task_ids
    output_files: dict = field(default_factory=dict)  # filename -> size in bytes


@dataclass
class Workflow:
    """The full workflow: all tasks + edges + data sizes."""
    name: str
    tasks: list          # list of Task objects, indexed by task_id
    n_tasks: int
    # data_size[(i, j)] = MB transferred from task i to task j when on different VMs
    data_size: dict = field(default_factory=dict)
    entry_task: int = 0   # task with no parents (the start)
    exit_task: int = 0    # task with no children (the end)


# ── Constants ─────────────────────────────────────────────────────────────────

# Mean MIPS across all VM types to convert seconds -> MI (hardware-neutral)
# VM types: small=1000, medium=2000, large=4000, xlarge=8000
# Mean = (1000+2000+4000+8000)/4 = 3750 MIPS
MEAN_MIPS = 3750.0
BYTES_PER_MB = 1_048_576  # 1 MB = 2^20 bytes


# ── Parser ────────────────────────────────────────────────────────────────────

def load_workflow(xml_path: str) -> Workflow:
    """
    Parse a Pegasus DAX XML file and return a Workflow object.

    Steps:
    1. Parse all <job> tags -> create Task objects
    2. Parse all <child>/<parent> tags -> build adjacency lists
    3. Compute data sizes per edge (parent's total output, in MB)
    4. Identify entry and exit tasks; add virtual nodes if needed
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # XML namespace used by Pegasus DAX 2.x files
    ns = {"dax": "http://pegasus.isi.edu/schema/DAX"}

    # ── Step 1: Parse all jobs ─────────────────────────────────────────────
    id_to_idx: dict[str, int] = {}  # "ID00000" -> 0
    tasks: list[Task] = []

    for job_elem in root.findall("dax:job", ns):
        str_id  = job_elem.get("id")
        runtime = float(job_elem.get("runtime", 1.0))  # seconds
        length_mi = runtime * MEAN_MIPS                 # convert to MI

        idx = len(tasks)
        id_to_idx[str_id] = idx

        # Collect output files and their byte sizes
        output_files = {}
        for uses in job_elem.findall("dax:uses", ns):
            if uses.get("link") == "output":
                fname = uses.get("file")
                size_bytes = int(uses.get("size", 0))
                output_files[fname] = size_bytes

        tasks.append(Task(
            task_id=idx,
            name=str_id,
            runtime=runtime,
            length_mi=length_mi,
            output_files=output_files,
        ))

    n_tasks = len(tasks)
    workflow_name = root.get("name", xml_path.replace("\\", "/").split("/")[-1])

    # ── Step 2: Parse dependencies and compute edge data sizes ────────────
    # <child ref="ID00005">
    #   <parent ref="ID00000"/>
    # </child>
    # => edge: ID00000 -> ID00005
    data_size: dict[tuple, float] = {}  # (parent_idx, child_idx) -> MB

    for child_elem in root.findall("dax:child", ns):
        child_str = child_elem.get("ref")
        child_idx = id_to_idx[child_str]
        child_task = tasks[child_idx]

        for parent_elem in child_elem.findall("dax:parent", ns):
            parent_str = parent_elem.get("ref")
            parent_idx = id_to_idx[parent_str]
            parent_task = tasks[parent_idx]

            # Link the two tasks
            parent_task.children.append(child_idx)
            child_task.parents.append(parent_idx)

            # ── Step 3: Edge data size ─────────────────────────────────
            # Use the parent's total output byte size as the transfer amount.
            # If tasks are on the same VM, transfer cost = 0 (handled in schedule.py).
            total_output = sum(parent_task.output_files.values())
            edge_mb = total_output / BYTES_PER_MB if total_output > 0 else 0.001
            data_size[(parent_idx, child_idx)] = edge_mb

    # ── Step 4: Virtual entry / exit nodes ────────────────────────────────
    # Some workflows have multiple independent entry tasks (no parents).
    # HEFT and PSO expect exactly one entry and one exit for clean rank computation.
    entry_tasks = [t.task_id for t in tasks if not t.parents]
    exit_tasks  = [t.task_id for t in tasks if not t.children]

    if len(entry_tasks) > 1:
        ve = Task(task_id=n_tasks, name="VIRTUAL_ENTRY", runtime=0.0,
                  length_mi=0.0, children=list(entry_tasks))
        for t_idx in entry_tasks:
            tasks[t_idx].parents.append(n_tasks)
            data_size[(n_tasks, t_idx)] = 0.0
        tasks.append(ve)
        n_tasks += 1
        entry_task_idx = ve.task_id
    else:
        entry_task_idx = entry_tasks[0]

    if len(exit_tasks) > 1:
        vx = Task(task_id=n_tasks, name="VIRTUAL_EXIT", runtime=0.0,
                  length_mi=0.0, parents=list(exit_tasks))
        for t_idx in exit_tasks:
            tasks[t_idx].children.append(n_tasks)
            data_size[(t_idx, n_tasks)] = 0.0
        tasks.append(vx)
        n_tasks += 1
        exit_task_idx = vx.task_id
    else:
        exit_task_idx = exit_tasks[0]

    return Workflow(
        name=workflow_name,
        tasks=tasks,
        n_tasks=n_tasks,
        data_size=data_size,
        entry_task=entry_task_idx,
        exit_task=exit_task_idx,
    )


def get_data_mb(wf: Workflow, parent_idx: int, child_idx: int) -> float:
    """Return MB of data flowing from parent to child (0 if no edge)."""
    return wf.data_size.get((parent_idx, child_idx), 0.0)


# ── Quick sanity check ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else r"..\data\workflows\Montage_50.xml"
    wf = load_workflow(path)
    print(f"Workflow : {wf.name}")
    print(f"Tasks    : {wf.n_tasks}")
    print(f"Edges    : {len(wf.data_size)}")
    print(f"Entry    : {wf.tasks[wf.entry_task].name}")
    print(f"Exit     : {wf.tasks[wf.exit_task].name}")
    print(f"\nFirst 5 tasks:")
    for t in wf.tasks[:5]:
        print(f"  {t.name}  runtime={t.runtime:.2f}s  MI={t.length_mi:.0f}  "
              f"parents={t.parents}  children={t.children}")

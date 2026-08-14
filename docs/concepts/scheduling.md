# Scheduling Algorithms

ncsim supports 22 SAGA static batch schedulers with SAGA 2.0.4, plus PEFT
when SAGA 2.1.0 is installed, and two built-in schedulers. These schedulers
decide **where** each task runs. The scheduler receives a DAG and a snapshot of the network
(node capacities, link bandwidths), and returns a `PlacementPlan`
mapping every task to a node. The execution engine then decides
**when** tasks run based on event ordering and node availability.

Select a scheduler via CLI:

```bash
ncsim --scenario scenario.yaml --output results/ --scheduler heft
```

Or in the scenario YAML:

```yaml
config:
  scheduler: wba
  scheduler_options:
    alpha: 0.75
```

With SAGA 2.0.4 installed, ncsim registers `bil`, `brute_force`, `cpop`, `dps`, `duplex`,
`etf`, `fastest_node`, `fcp`, `flb`, `gdl`, `hbmct`, `heft`, `maxmin`,
`mct`, `met`, `minmin`, `msbc`, `mst`, `olb`, `smt`, `sufferage`,
and `wba`. SAGA 2.1.0 adds `peft`. These algorithms produce a static placement for each injected DAG;
ncsim's execution engine controls actual run and transfer timing.

## HEFT (Heterogeneous Earliest Finish Time)

HEFT is a list-scheduling heuristic designed for heterogeneous computing
environments. It is the default scheduler in ncsim and generally produces
the best makespans.

### Algorithm

1. **Compute upward rank** for each task. The upward rank is the longest
   path (by computation + communication cost) from the task to any exit
   task in the DAG. Tasks with higher upward rank are scheduled first.

2. **Sort tasks** by decreasing upward rank. This ordering ensures that
   tasks on the critical path are considered before less important tasks.

3. **For each task** (in rank order), evaluate every node and select the
   one that gives the **earliest finish time (EFT)**. The finish time
   accounts for:
    - The task's execution time on that node (`compute_cost / compute_capacity`).
    - The data transfer time for all incoming edges from predecessor tasks
      already placed on other nodes.
    - The node's availability (when it becomes idle after finishing its
      currently assigned workload).

!!! info "Communication awareness"
    HEFT accounts for the cost of data transfers between nodes. If two
    communicating tasks are placed on the same node, the transfer cost
    is zero. This means HEFT will naturally co-locate tightly coupled
    tasks when the communication cost outweighs the benefit of faster
    remote execution.

### When to Use HEFT

- General-purpose default for heterogeneous networks.
- Networks where nodes have different compute capacities.
- DAGs with mixed computation and communication requirements.

## CPOP (Critical Path on a Processor)

CPOP is a variant of list scheduling that identifies the DAG's critical
path and concentrates those tasks on the single fastest processor.

### Algorithm

1. **Compute upward rank and downward rank** for each task. The downward
   rank is the longest path from the entry task to the current task.

2. **Compute priority** as the sum of upward and downward rank. Tasks on
   the critical path all share the same maximum priority value.

3. **Identify critical-path tasks** -- tasks whose priority equals the
   maximum.

4. **Assign critical-path tasks** to the single processor (node) that
   minimizes the total critical-path execution time.

5. **Assign non-critical tasks** using the EFT heuristic (same as HEFT).

### When to Use CPOP

- DAGs with a dominant critical path (one long chain of dependent tasks).
- Networks with one node significantly faster than the others, where
  running the critical path entirely on that node avoids inter-node
  transfer overhead.

!!! warning "CPOP can underperform HEFT"
    If the DAG has multiple paths of similar length, CPOP's strategy
    of concentrating on a single critical path may leave the fast
    processor overloaded while other nodes sit idle. In such cases,
    HEFT's per-task EFT approach tends to produce better makespans.

## Round Robin

Round Robin assigns tasks to nodes in simple cyclic order. It is
communication-unaware and heterogeneity-unaware.

### Algorithm

1. **Order tasks** topologically (predecessors before successors).
2. **Cycle through nodes**: task 0 goes to node 0, task 1 to node 1,
   task 2 to node 0, and so on.

!!! warning "Baseline only"
    Round Robin ignores compute capacities, data dependencies, and
    transfer costs. It exists solely as a baseline for comparing
    against intelligent schedulers. Do not use it for performance-
    sensitive simulations.

## Comparison

| Feature | HEFT | CPOP | Round Robin |
|---|---|---|---|
| Task ordering | Upward rank (descending) | Priority = upward + downward rank | Topological (insertion order) |
| Node selection | Earliest Finish Time (EFT) across all nodes | Critical-path tasks to fastest node; others to min EFT | Cyclic assignment |
| Communication-aware | Yes | Yes | No |
| Heterogeneity-aware | Yes | Yes | No |
| Best for | General case | Dominant critical path + one fast node | Baseline comparisons |
| Library | anrg-saga | anrg-saga | Built-in |

## Manual Assignment (pinned_to)

Tasks can be pinned to specific nodes using the `pinned_to` field in the
scenario YAML. This bypasses the scheduler's decision for that task.

```yaml
dags:
  - id: dag_1
    tasks:
      - id: T0
        compute_cost: 100
        pinned_to: n0        # Force T0 onto node n0
      - id: T1
        compute_cost: 200
        pinned_to: n1        # Force T1 onto node n1
      - id: T2
        compute_cost: 150    # No pin -- scheduler decides
    edges:
      - { from: T0, to: T2, data_size: 10 }
      - { from: T1, to: T2, data_size: 20 }
```

Pinned tasks work with **any** scheduler:

- With `--scheduler manual`, all tasks must have `pinned_to` set (tasks
  without it are assigned to the first node with a warning).
- With `--scheduler heft` or `--scheduler cpop`, pinned tasks override
  the scheduler's choice. Unpinned tasks are scheduled normally.
- With `--scheduler round_robin`, pinned tasks override the cyclic
  assignment.

!!! tip "Testing specific placements"
    Manual assignment is useful for validating simulation correctness
    against hand-calculated expected results, or for testing how a
    specific placement performs under different interference or routing
    models.

## Example: Same DAG, Different Schedulers

Consider a diamond-shaped DAG with four tasks on a two-node network:

```yaml
scenario:
  name: "Diamond DAG"
  network:
    nodes:
      - id: fast
        compute_capacity: 100
      - id: slow
        compute_capacity: 50
    links:
      - id: link_fs
        from: fast
        to: slow
        bandwidth: 10
        latency: 0.001
      - id: link_sf
        from: slow
        to: fast
        bandwidth: 10
        latency: 0.001

  dags:
    - id: diamond
      tasks:
        - { id: A, compute_cost: 100 }   # Entry
        - { id: B, compute_cost: 200 }   # Left branch
        - { id: C, compute_cost: 200 }   # Right branch
        - { id: D, compute_cost: 100 }   # Exit (merge)
      edges:
        - { from: A, to: B, data_size: 5 }
        - { from: A, to: C, data_size: 5 }
        - { from: B, to: D, data_size: 5 }
        - { from: C, to: D, data_size: 5 }
```

### HEFT Placement

HEFT computes upward ranks and assigns each task to the node giving the
earliest finish time:

| Task | Upward Rank | Assignment | Rationale |
|---|---|---|---|
| A | highest | fast | Fastest execution for the entry task |
| B | mid | fast | Co-locating with A avoids transfer cost |
| C | mid | slow | Runs in parallel with B on the other node |
| D | lowest | fast | Fastest node for the exit merge |

Because B and C can run in parallel on different nodes, HEFT overlaps
their execution. The makespan is dominated by the critical path
A -> B -> D (or A -> C -> D, whichever is longer after accounting for
transfer times).

### CPOP Placement

CPOP identifies the critical path (e.g., A -> B -> D) and assigns all
three to `fast`. Task C (non-critical) goes to `slow` via EFT.

| Task | On Critical Path | Assignment |
|---|---|---|
| A | Yes | fast |
| B | Yes | fast |
| C | No | slow |
| D | Yes | fast |

This avoids transfers along the critical path (A, B, D all on the same
node), but C must transfer its output to D across the network.

### Round Robin Placement

Round Robin simply cycles: A -> fast, B -> slow, C -> fast, D -> slow.

| Task | Assignment | Rationale |
|---|---|---|
| A | fast | First in cycle |
| B | slow | Second in cycle |
| C | fast | Third in cycle (wraps) |
| D | slow | Fourth in cycle |

This placement is communication-unaware. Every edge in the DAG requires a
network transfer, and the slow node bottlenecks task execution. The
resulting makespan is significantly worse than HEFT or CPOP.

### Makespan Comparison

Running the three schedulers on the diamond scenario above produces
different makespans. The exact values depend on bandwidth and latency
parameters, but the relative ranking is consistent:

```bash
# Run with each scheduler
ncsim --scenario diamond.yaml --output out/heft --scheduler heft
ncsim --scenario diamond.yaml --output out/cpop --scheduler cpop
ncsim --scenario diamond.yaml --output out/rr   --scheduler round_robin
```

| Scheduler | Typical Makespan Ranking |
|---|---|
| HEFT | Best (parallelism + communication-aware) |
| CPOP | Close to HEFT (critical path optimized) |
| Round Robin | Worst (no optimization) |

## SAGA Library Integration

The registered static batch schedulers are implemented via the
[anrg-saga](https://pypi.org/project/anrg-saga/) library. ncsim's
`SagaScheduler` adapter translates between ncsim's data model and SAGA's:

1. **Network translation** -- SAGA requires a fully-connected graph. The
   adapter creates edges for all node pairs: `LOCAL_SPEED` (10000 MB/s)
   for same-node, actual link bandwidth for connected pairs, widest-path
   bandwidth for multi-hop pairs (when `--routing widest_path` or
   `--routing shortest_path` is active), and `DISCONNECTED_SPEED`
   (0.001 MB/s) for unreachable pairs.

2. **Task graph translation** -- DAG tasks become `TaskGraphNode` objects
   with `cost = compute_cost`. DAG edges become `TaskGraphEdge` objects
   with `size = data_size`.

3. **Result extraction** -- SAGA's schedule maps internal node names
   (`node_0`, `node_1`) to task lists. The adapter maps these back to
   actual node IDs.

!!! note "Install requirement"
    The 22 schedulers listed above work with SAGA 2.0.4 from PyPI:
    ```
    pip install "anrg-saga>=2.0.4"
    ```
    To add PEFT, install the tagged SAGA 2.1.0 source:
    ```
    pip install "anrg-saga @ git+https://github.com/ANRGUSC/saga.git@v2.1.0"
    ```
    ncsim reports a clear error when a requested scheduler is unavailable or
    receives an unsupported option; it does not silently substitute another
    algorithm.

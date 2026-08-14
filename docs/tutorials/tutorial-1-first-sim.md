# Tutorial 1: Your First Simulation

This tutorial walks you through installing ncsim, running your first simulation,
understanding the output, and comparing different scheduler configurations.

---

## What You Will Learn

- Install ncsim from source
- Run a simulation from the command line
- Understand the output files (trace, metrics, scenario copy)
- Analyze trace data with the built-in analysis tool
- Compare different scheduler settings and observe their effects

## Prerequisites

- Python 3.12 or later
- pip (included with Python)
- git

---

## Step 1: Install ncsim

Clone the repository and install in editable (development) mode:

```bash
git clone https://github.com/ANRGUSC/ncsim.git
cd ncsim
pip install -e .
```

Verify the installation:

```bash
ncsim --version
```

Expected output:

```
ncsim 1.1.0
```

!!! info "Dependencies"
    Installing ncsim automatically pulls in its dependencies:

    - **anrg-saga** (>=2.0.4) -- 22 SAGA static batch scheduling algorithms (SAGA 2.1.0 also exposes PEFT)
    - **networkx** (>=3.0) -- graph algorithms for routing
    - **pyyaml** (>=6.0) -- YAML scenario parsing

---

## Step 2: Run the Demo Scenario

ncsim ships with several built-in scenarios in the `scenarios/` directory.
Start with the simplest one:

```bash
ncsim --scenario scenarios/demo_simple.yaml --output results/tutorial1/demo
```

You should see output like this:

```
=== Simulation Complete ===
Scenario: Simple Demo
Scheduler: heft
Routing: direct
Interference: proximity
  radius=15.0
Seed: 42
Makespan: 3.000000 seconds
Total events: 7
Status: completed
```

### What Just Happened?

The `demo_simple.yaml` scenario defines:

- **2 nodes**: `n0` (compute capacity 100) and `n1` (compute capacity 50)
- **1 link**: `l01` from `n0` to `n1` (bandwidth 100 MB/s, latency 1 ms)
- **2 tasks**: `T0` (compute cost 100) and `T1` (compute cost 200), with `T0 -> T1` dependency and a 50 MB data transfer

The HEFT scheduler assigned both tasks to `n0` (the faster node). Since both tasks
run on the same node, no network transfer is needed -- the data stays local.

| Task | Node | Compute Cost | Capacity | Duration |
|------|------|-------------|----------|----------|
| T0   | n0   | 100         | 100 cu/s | 1.0s     |
| T1   | n0   | 200         | 100 cu/s | 2.0s     |

T0 runs from t=0.0 to t=1.0, then T1 runs from t=1.0 to t=3.0.
Total makespan: **3.0 seconds**.

!!! note "Why no transfer?"
    HEFT placed both tasks on `n0` because `n0` is twice as fast as `n1`.
    Running T1 on `n0` (2.0s) is faster than transferring 50 MB over the link
    (0.5s + 0.001s latency) and running T1 on `n1` (200/50 = 4.0s).

---

## Step 3: Examine the Output Files

ncsim creates three files in the output directory:

```bash
ls results/tutorial1/demo/
```

```
metrics.json
scenario.yaml
trace.jsonl
```

### 3a: The Scenario Copy

ncsim copies the input scenario into the output directory for reproducibility:

```bash
cat results/tutorial1/demo/scenario.yaml
```

```yaml
# Demo Simple Scenario
# Two nodes, one link, simple 2-task DAG

scenario:
  name: "Simple Demo"

  network:
    nodes:
      - id: n0
        compute_capacity: 100
        position: {x: 0, y: 0}
      - id: n1
        compute_capacity: 50
        position: {x: 10, y: 0}
    links:
      - id: l01
        from: n0
        to: n1
        bandwidth: 100
        latency: 0.001

  dags:
    - id: dag_1
      inject_at: 0.0
      tasks:
        - id: T0
          compute_cost: 100
        - id: T1
          compute_cost: 200
      edges:
        - from: T0
          to: T1
          data_size: 50

  config:
    scheduler: heft
    seed: 42
```

### 3b: The Trace File

The trace file is a JSONL file (one JSON object per line) recording every simulation
event in chronological order:

```bash
cat results/tutorial1/demo/trace.jsonl
```

Here is each event, explained:

**Event 0 -- `sim_start`**: Marks the beginning of the simulation.

```json
{"sim_time":0.0,"type":"sim_start","trace_version":"1.0","seed":42,
 "scenario":"demo_simple.yaml","scenario_hash":"7c96514022196f2f","seq":0}
```

**Event 1 -- `dag_inject`**: The DAG is injected at time 0.0 with its two tasks.

```json
{"sim_time":0.0,"type":"dag_inject","dag_id":"dag_1",
 "task_ids":["T0","T1"],"seq":1}
```

**Event 2 -- `task_scheduled`**: HEFT assigns T0 to node n0.

```json
{"sim_time":0.0,"type":"task_scheduled","dag_id":"dag_1",
 "task_id":"T0","node_id":"n0","seq":2}
```

**Event 3 -- `task_start`**: T0 begins executing on n0.

```json
{"sim_time":0.0,"type":"task_start","dag_id":"dag_1",
 "task_id":"T0","node_id":"n0","seq":3}
```

**Event 4 -- `task_complete`**: T0 finishes after 1.0 second (cost 100 / capacity 100).

```json
{"sim_time":1.0,"type":"task_complete","dag_id":"dag_1",
 "task_id":"T0","node_id":"n0","duration":1.0,"seq":4}
```

**Event 5 -- `task_scheduled`**: T1 is assigned to n0 (same node, so no transfer needed).

```json
{"sim_time":1.0,"type":"task_scheduled","dag_id":"dag_1",
 "task_id":"T1","node_id":"n0","seq":5}
```

**Event 6 -- `task_start`**: T1 begins executing immediately.

```json
{"sim_time":1.0,"type":"task_start","dag_id":"dag_1",
 "task_id":"T1","node_id":"n0","seq":6}
```

**Event 7 -- `task_complete`**: T1 finishes after 2.0 seconds (cost 200 / capacity 100).

```json
{"sim_time":3.0,"type":"task_complete","dag_id":"dag_1",
 "task_id":"T1","node_id":"n0","duration":2.0,"seq":7}
```

**Event 8 -- `sim_end`**: Simulation complete.

```json
{"sim_time":3.0,"type":"sim_end","status":"completed",
 "makespan":3.0,"total_events":8,"seq":8}
```

!!! tip "Event Types"
    | Event Type | Meaning |
    |---|---|
    | `sim_start` | Simulation begins |
    | `dag_inject` | A DAG enters the system |
    | `task_scheduled` | Scheduler assigns a task to a node |
    | `task_start` | Task begins executing on its assigned node |
    | `task_complete` | Task finishes executing |
    | `transfer_start` | Data transfer begins on a network link |
    | `transfer_complete` | Data transfer finishes |
    | `sim_end` | Simulation ends |

### 3c: The Metrics File

The metrics file is a JSON summary of the simulation results:

```bash
cat results/tutorial1/demo/metrics.json
```

```json
{
  "scenario": "demo_simple.yaml",
  "seed": 42,
  "makespan": 3.0,
  "total_tasks": 2,
  "total_transfers": 1,
  "total_events": 7,
  "status": "completed",
  "node_utilization": {
    "n0": 1.0,
    "n1": 0.0
  },
  "link_utilization": {
    "l01": 0.0
  }
}
```

| Metric | Value | Meaning |
|--------|-------|---------|
| `makespan` | 3.0 | Total wall-clock time from first task to last task completion |
| `node_utilization` n0 | 1.0 | n0 was busy 100% of the time (3s busy / 3s total) |
| `node_utilization` n1 | 0.0 | n1 was never used |
| `link_utilization` l01 | 0.0 | No data was transferred over the link |

---

## Step 4: Try Different Schedulers

The `--scheduler` flag overrides the scenario's default scheduler. Try CPOP and round-robin:

```bash
ncsim --scenario scenarios/demo_simple.yaml \
      --output results/tutorial1/cpop \
      --scheduler cpop

ncsim --scenario scenarios/demo_simple.yaml \
      --output results/tutorial1/rr \
      --scheduler round_robin
```

### Comparing the Results

| Scheduler | Makespan | T0 Node | T1 Node | Transfer? |
|-----------|----------|---------|---------|-----------|
| **heft** | 3.000s | n0 | n0 | No (local) |
| **cpop** | 3.000s | n0 | n0 | No (local) |
| **round_robin** | 5.501s | n0 | n1 | Yes (50 MB over l01) |

!!! info "Why does round-robin produce a longer makespan?"
    Round-robin assigns tasks to nodes in rotation: T0 goes to n0, T1 goes to n1.
    Since T1 depends on T0, a 50 MB data transfer must occur over link l01 before
    T1 can start. The transfer takes 50/100 + 0.001 = 0.501 seconds. Then T1 runs
    on n1, the slower node: 200/50 = 4.0 seconds. Total: 1.0 + 0.501 + 4.0 = 5.501s.

    HEFT and CPOP are smarter -- they recognize that keeping both tasks on the fast
    node avoids the transfer penalty entirely.

The round-robin trace includes transfer events that are absent from the HEFT trace.
You can see them by examining the trace:

```bash
cat results/tutorial1/rr/trace.jsonl
```

Look for the `transfer_start` and `transfer_complete` events at t=1.0 and t=1.501.

---

## Step 5: Try a Larger Scenario

Now try a scenario with more tasks and nodes:

```bash
ncsim --scenario scenarios/parallel_spread.yaml \
      --output results/tutorial1/spread
```

Expected output:

```
=== Simulation Complete ===
Scenario: Parallel Spread (Bidirectional)
Scheduler: heft
Routing: direct
Interference: proximity
  radius=15.0
Seed: 42
Makespan: 35.348333 seconds
Total events: 51
Status: completed
```

This scenario has:

- **5 nodes** in a line: n0 through n4 with capacities 80, 90, 100, 90, 80
- **8 bidirectional links** connecting adjacent nodes (500 MB/s each)
- **10 tasks**: a fan-out/fan-in DAG with T_root -> {P0..P7} -> T_sink

HEFT distributes the 8 parallel tasks across 3 nodes (n1, n2, n3), placing 3 tasks
on n2 (fastest), 3 on n1, and 2 on n3.

---

## Step 6: Analyze the Trace

ncsim includes `analyze_trace.py` for quick trace analysis. It supports three output
modes.

### Gantt Chart

```bash
python analyze_trace.py results/tutorial1/spread/trace.jsonl --gantt
```

```
=== Execution Gantt Chart ===

Time: 0                                                        35.35s
       |============================================================|
n1     | ###################                                        | P3 (11.111s)
n1     |                    ###################                     | P4 (11.111s)
n1     |                                       ###################  | P7 (11.111s)
n2     |#                                                           | T_root (1.000s)
n2     | #################                                          | P0 (10.000s)
n2     |                  #################                         | P2 (10.000s)
n2     |                                   #################        | P5 (10.000s)
n2     |                                                          ##| T_sink (1.000s)
n3     | ###################                                        | P1 (11.111s)
n3     |                    ###################                     | P6 (11.111s)
       |------------------------------------------------------------|
l12    |                    ~                                       | P3->T_sink (0.003s)
l21    | ~                                                          | T_root->P3 (0.012s)
l23    | ~                                                          | T_root->P1 (0.009s)
l32    |                    ~                                       | P1->T_sink (0.003s)
       |============================================================|

Legend: # = task execution, ~ = data transfer
```

The Gantt chart shows:

- `#` marks indicate task execution on each node
- `~` marks indicate data transfers on each link
- Tasks are grouped by the node they run on
- You can see that n2 runs 3 parallel tasks sequentially (P0, P2, P5) plus T_root and T_sink

### Timeline

```bash
python analyze_trace.py results/tutorial1/spread/trace.jsonl --timeline
```

This prints every event in chronological order with details:

```
[  0.0000] sim_start            scenario=parallel_spread.yaml
[  0.0000] dag_inject           dag=dag1, tasks=['T_root', 'P0', ...]
[  0.0000] task_scheduled       T_root on n2
[  0.0000] task_start           T_root on n2
[  1.0000] task_complete        T_root on n2 (duration=1.0)
[  1.0000] task_scheduled       P0 on n2
[  1.0000] task_start           P0 on n2
[  1.0000] transfer_start       T_root->P1 via l23 (1.0 MB)
...
[ 35.3483] task_complete        T_sink on n2 (duration=1.0)
[ 35.3483] sim_end              makespan=35.348333
```

### Task Details

```bash
python analyze_trace.py results/tutorial1/spread/trace.jsonl --tasks
```

This prints per-task information including scheduling, start, and completion times:

```
P0:
  Node: n2
  Scheduled: 1.0
  Started: 1.0
  Completed: 11.0
  Duration: 10.000000s

P3:
  Node: n1
  Scheduled: 1.012
  Started: 1.012
  Completed: 12.123111
  Duration: 11.111111s
...
```

!!! tip "Default mode"
    Running `python analyze_trace.py <trace.jsonl>` without flags shows both
    the summary statistics and the Gantt chart.

---

## Step 7: Verify Determinism

ncsim is fully deterministic given the same seed. You can verify this:

```bash
ncsim --scenario scenarios/demo_simple.yaml --seed 42 \
      --output results/tutorial1/run_a

ncsim --scenario scenarios/demo_simple.yaml --seed 42 \
      --output results/tutorial1/run_b

diff results/tutorial1/run_a/trace.jsonl results/tutorial1/run_b/trace.jsonl
```

No output from `diff` means the traces are identical. This is essential for
reproducible research -- the same scenario and seed always produce the same results.

!!! warning "Changing the seed"
    The seed primarily affects scheduling decisions in algorithms that use
    randomness. For deterministic schedulers like HEFT and CPOP, the seed has
    no effect on task placement. It does affect shadow fading values in WiFi
    scenarios (Tutorial 3).

---

## Summary

In this tutorial you learned how to:

1. **Install** ncsim from source with `pip install -e .`
2. **Run** a simulation with `ncsim --scenario <file> --output <dir>`
3. **Read** the three output files: `scenario.yaml`, `trace.jsonl`, `metrics.json`
4. **Compare** three representative schedulers: HEFT and CPOP make communication-aware placement decisions; round-robin provides a simple baseline
5. **Analyze** traces with `analyze_trace.py` using `--gantt`, `--timeline`, and `--tasks`
6. **Verify** determinism by running the same scenario twice with the same seed

## What's Next

| Tutorial | Topic |
|----------|-------|
| [Tutorial 2: Custom Scenario](tutorial-2-custom-scenario.md) | Build your own 4-node mesh network and fork-join DAG from scratch |
| [Tutorial 3: WiFi Experiment](tutorial-3-wifi-experiment.md) | Explore CSMA/CA interference with the Bianchi model |
| [Tutorial 4: Compare Schedulers](tutorial-4-compare-schedulers.md) | Systematic scheduler comparison across scenarios |

# Quick Start

Run your first ncsim simulation in five minutes. This guide assumes you have already completed the [Installation](installation.md) steps.

---

## Step 1: Run Your First Simulation

The repository includes several example scenarios in the `scenarios/` directory. Start with the simplest one -- a two-node network with a two-task DAG:

```bash
ncsim --scenario scenarios/demo_simple.yaml --output results/demo
```

You should see the following terminal output:

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

!!! tip "What just happened?"
    ncsim loaded the scenario, used the HEFT scheduler to assign two tasks to nodes, ran a discrete-event simulation, and produced output files with the full event trace and summary metrics. The **makespan** (3.0 seconds) is the total time from the start of the first task to the completion of the last task.

---

## Step 2: Examine the Output Files

Every simulation run produces three files in the output directory:

```bash
ls results/demo/
```

```
metrics.json    scenario.yaml    trace.jsonl
```

| File | Format | Contents |
|------|--------|----------|
| `scenario.yaml` | YAML | Copy of the input scenario (for reproducibility) |
| `trace.jsonl` | JSONL | Every simulation event, one JSON object per line |
| `metrics.json` | JSON | Summary metrics: makespan, utilization, task/transfer counts |

### Trace File (`trace.jsonl`)

The trace file records every event in chronological order. Each line is a self-contained JSON object with a sequence number, simulation time, and event type:

```json
{"sim_time":0.0,"type":"sim_start","trace_version":"1.0","seed":42,"scenario":"demo_simple.yaml","seq":0}
{"sim_time":0.0,"type":"dag_inject","dag_id":"dag_1","task_ids":["T0","T1"],"seq":1}
{"sim_time":0.0,"type":"task_scheduled","dag_id":"dag_1","task_id":"T0","node_id":"n0","seq":2}
{"sim_time":0.0,"type":"task_start","dag_id":"dag_1","task_id":"T0","node_id":"n0","seq":3}
{"sim_time":1.0,"type":"task_complete","dag_id":"dag_1","task_id":"T0","node_id":"n0","duration":1.0,"seq":4}
{"sim_time":1.0,"type":"task_scheduled","dag_id":"dag_1","task_id":"T1","node_id":"n0","seq":5}
{"sim_time":1.0,"type":"task_start","dag_id":"dag_1","task_id":"T1","node_id":"n0","seq":6}
{"sim_time":3.0,"type":"task_complete","dag_id":"dag_1","task_id":"T1","node_id":"n0","duration":2.0,"seq":7}
{"sim_time":3.0,"type":"sim_end","status":"completed","makespan":3.0,"total_events":8,"seq":8}
```

The event types you will encounter are:

| Event Type | Description |
|------------|-------------|
| `sim_start` | Simulation begins; records scenario name, seed, trace version |
| `dag_inject` | A DAG is injected into the simulation with its list of task IDs |
| `task_scheduled` | A task is assigned to a specific node by the scheduler |
| `task_start` | A task begins executing on its assigned node |
| `task_complete` | A task finishes executing; includes duration |
| `transfer_start` | A data transfer begins between tasks across a link |
| `transfer_complete` | A data transfer finishes; includes duration |
| `sim_end` | Simulation ends; records final status and makespan |

### Metrics File (`metrics.json`)

The metrics file provides a high-level summary of the simulation run:

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

!!! note "Utilization"
    **Node utilization** is the fraction of the makespan during which a node is actively executing a task. **Link utilization** is the fraction of the makespan during which a link is carrying data. In this example, HEFT assigned both tasks to node `n0`, so `n0` has 100% utilization, `n1` has 0%, and link `l01` was never used.

---

## Step 3: Override Settings from the CLI

Scenario YAML files define default settings (scheduler, routing, seed), but you can override any of them from the command line. Try running the same scenario with a different scheduler, routing algorithm, and seed:

```bash
ncsim --scenario scenarios/demo_simple.yaml --output results/demo-cpop \
      --scheduler cpop --routing widest_path --seed 123
```

```
=== Simulation Complete ===
Scenario: Simple Demo
Scheduler: cpop
Routing: widest_path
Interference: proximity
  radius=15.0
Seed: 123
Makespan: 3.000000 seconds
Total events: 7
Status: completed
```

In this simple two-node case, both HEFT and CPOP produce the same makespan because the optimal strategy is to run both tasks on the faster node. The differences become significant on larger topologies.

The full set of CLI overrides:

| Flag | Values | Description |
|------|--------|-------------|
| `--scheduler` | `heft`, `cpop`, `round_robin`, `manual` | Scheduling algorithm |
| `--routing` | `direct`, `widest_path`, `shortest_path` | Routing algorithm |
| `--interference` | `none`, `proximity`, `csma_clique`, `csma_bianchi` | Interference model |
| `--interference-radius` | float | Radius for proximity interference (meters) |
| `--seed` | integer | Random seed for deterministic results |
| `--wifi-standard` | `n`, `ac`, `ax` | WiFi standard for MCS rate tables |
| `--tx-power` | float (dBm) | WiFi transmit power |
| `--freq` | float (GHz) | WiFi carrier frequency |
| `--path-loss-exponent` | float | Path loss exponent |
| `--rts-cts` | flag | Enable RTS/CTS mechanism |
| `--verbose` / `-v` | flag | Enable debug-level logging |

---

## Step 4: Try a More Complex Scenario

The `parallel_spread.yaml` scenario demonstrates the impact of routing on a multi-node topology. It defines 5 nodes in a line with 8 parallel tasks:

```bash
ncsim --scenario scenarios/parallel_spread.yaml --output results/ps-direct
```

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

Now run the same scenario with widest-path routing, which enables the scheduler to spread tasks across all 5 nodes via multi-hop paths:

```bash
ncsim --scenario scenarios/parallel_spread.yaml --output results/ps-widest \
      --routing widest_path
```

```
=== Simulation Complete ===
Scenario: Parallel Spread (Bidirectional)
Scheduler: heft
Routing: widest_path
Interference: proximity
  radius=15.0
Seed: 42
Makespan: 24.246722 seconds
Total events: 55
Status: completed
```

!!! tip "31% faster with widest-path routing"
    With direct routing, HEFT can only assign tasks to nodes that have a direct link to the task's data source, limiting it to 3 adjacent nodes. Widest-path routing enables multi-hop transfers, so HEFT can spread the 8 parallel tasks across all 5 nodes -- reducing the makespan from 35.3s to 24.2s.

---

## Step 5: Analyze the Trace

The included `analyze_trace.py` script provides quick text-based analysis of trace files. Use the `--timeline` flag for a chronological event log and `--gantt` flag for an ASCII Gantt chart:

```bash
python analyze_trace.py results/demo/trace.jsonl --gantt --timeline
```

```
=== Event Timeline ===

[  0.0000] sim_start            scenario=demo_simple.yaml
[  0.0000] dag_inject           dag=dag_1, tasks=['T0', 'T1']
[  0.0000] task_scheduled       T0 on n0
[  0.0000] task_start           T0 on n0
[  1.0000] task_complete        T0 on n0 (duration=1.0)
[  1.0000] task_scheduled       T1 on n0
[  1.0000] task_start           T1 on n0
[  3.0000] task_complete        T1 on n0 (duration=2.0)
[  3.0000] sim_end              makespan=3.0

=== Execution Gantt Chart ===

Time: 0                                                        3.00s
       |============================================================|
n0     |####################                                        | T0 (1.000s)
n0     |                    ########################################| T1 (2.000s)
       |============================================================|

Legend: # = task execution, ~ = data transfer
```

The analysis script supports three views:

| Flag | Description |
|------|-------------|
| `--timeline` | Chronological event log with timestamps |
| `--gantt` | ASCII Gantt chart showing task execution and data transfers |
| `--tasks` | Per-task detail: scheduled time, start time, completion time, duration, wait time |

You can combine flags, or run with no flags to get a default summary plus Gantt chart.

---

## What's Next?

Now that you have run your first simulations, explore the rest of the documentation:

- **[Core Concepts: Architecture](../concepts/architecture.md)** -- understand the simulation engine, event queue, and execution model
- **[Core Concepts: Scheduling](../concepts/scheduling.md)** -- explore the version-aware SAGA registry plus round-robin and manual assignment
- **[Scenarios: YAML Reference](../scenarios/yaml-reference.md)** -- full specification of the scenario file format for writing your own scenarios
- **[Scenarios: Scenario Gallery](../scenarios/scenario-gallery.md)** -- browse the 10 included example scenarios with descriptions and expected results
- **[Visualization: Overview](../viz/viz-overview.md)** -- set up the web UI and explore results interactively with Gantt charts, animated replay, and network topology views
- **[Tutorial 2: Custom Scenario](../tutorials/tutorial-2-custom-scenario.md)** -- build a scenario from scratch
- **[Tutorial 3: WiFi Experiment](../tutorials/tutorial-3-wifi-experiment.md)** -- configure 802.11 interference models
- **[Tutorial 4: Compare Schedulers](../tutorials/tutorial-4-compare-schedulers.md)** -- run batch experiments comparing scheduling algorithms

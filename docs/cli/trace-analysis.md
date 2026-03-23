# Trace Analysis

ncsim ships with `analyze_trace.py`, a standalone script for inspecting and
visualizing trace files from the command line. It supports summary statistics,
chronological timelines, ASCII Gantt charts, and per-task breakdowns.

---

## analyze_trace.py

### Usage

```bash
python analyze_trace.py <trace.jsonl> [--timeline] [--gantt] [--tasks]
```

| Flag | Description |
|---|---|
| *(no flags)* | Show summary statistics and ASCII Gantt chart (default) |
| `--timeline` | Show chronological event timeline with timestamps |
| `--gantt` | Show ASCII Gantt chart of task execution and data transfers |
| `--tasks` | Show per-task details (node, timing, wait time) |
| `--summary` | Show summary statistics only |

Flags can be combined. For example, `--timeline --tasks` shows both the timeline
and per-task details.

---

## Default Output (Summary + Gantt)

When run with no flags, the script prints summary statistics followed by an
ASCII Gantt chart.

```bash
python analyze_trace.py output/basic/trace.jsonl
```

```
=== Trace Summary ===

Scenario: demo_simple.yaml
Seed: 42
Status: completed
Makespan: 3.501000 seconds
Total events: 11

Event counts:
  dag_inject: 1
  sim_end: 1
  sim_start: 1
  task_complete: 2
  task_scheduled: 2
  task_start: 2
  transfer_complete: 1
  transfer_start: 1

=== Execution Gantt Chart ===

Time: 0                                                    3.50s
       |============================================================|
    n0 |##################                                          | T0 (1.000s)
    n0 |                  ##########################################| T1 (2.000s)
       |------------------------------------------------------------|
   l01 |                  ~~~~~                                     | T0->T1 (0.501s)
       |============================================================|

Legend: # = task execution, ~ = data transfer
```

!!! info "Reading the Gantt chart"
    - `#` characters represent task execution time on a compute node.
    - `~` characters represent data transfer time on a network link.
    - Each row is labeled with the node ID (for tasks) or link ID (for transfers).
    - The time axis spans from 0 to the makespan, scaled to fit a 60-character
      width.

---

## --timeline Flag

Shows every event in chronological order with simulation timestamps:

```bash
python analyze_trace.py output/basic/trace.jsonl --timeline
```

```
=== Event Timeline ===

[  0.0000] sim_start            scenario=demo_simple.yaml
[  0.0000] dag_inject           dag=dag_1, tasks=['T0', 'T1']
[  0.0000] task_scheduled       T0 on n0
[  0.0000] task_start           T0 on n0
[  0.0000] task_scheduled       T1 on n0
[  1.0000] task_complete        T0 on n0 (duration=1.0)
[  1.0000] transfer_start       T0->T1 via l01 (50 MB)
[  1.5010] transfer_complete    T0->T1 (duration=0.501)
[  1.5010] task_start           T1 on n0
[  3.5010] task_complete        T1 on n0 (duration=2.0)
[  3.5010] sim_end              makespan=3.501
```

The timeline format is useful for understanding the exact sequence of events
and debugging scheduling or transfer ordering issues.

---

## --gantt Flag

Shows only the ASCII Gantt chart without summary statistics:

```bash
python analyze_trace.py output/basic/trace.jsonl --gantt
```

```
=== Execution Gantt Chart ===

Time: 0                                                    3.50s
       |============================================================|
    n0 |##################                                          | T0 (1.000s)
    n0 |                  ##########################################| T1 (2.000s)
       |------------------------------------------------------------|
   l01 |                  ~~~~~                                     | T0->T1 (0.501s)
       |============================================================|

Legend: # = task execution, ~ = data transfer
```

For scenarios with multiple nodes and parallel tasks, the chart reveals
scheduling patterns at a glance:

```
Time: 0                                                    2.50s
       |============================================================|
    n0 |##############################                              | T0 (1.000s)
    n0 |                              ##############################| T2 (1.000s)
    n1 |##############################                              | T1 (1.000s)
    n1 |                              ##############################| T3 (1.000s)
       |------------------------------------------------------------|
   l01 |                              ~~~~~                         | T0->T2 (0.400s)
   l10 |                              ~~~~~                         | T1->T3 (0.400s)
       |============================================================|

Legend: # = task execution, ~ = data transfer
```

---

## --tasks Flag

Shows detailed information about each task, including node assignment,
scheduling, start, and completion times:

```bash
python analyze_trace.py output/basic/trace.jsonl --tasks
```

```
=== Task Details ===

T0:
  Node: n0
  Scheduled: 0.0
  Started: 0.0
  Completed: 1.0
  Duration: 1.000000s

T1:
  Node: n0
  Scheduled: 0.0
  Started: 1.501
  Completed: 3.501
  Duration: 2.000000s
  Wait time: 1.501000s
```

!!! info "Wait time"
    Wait time is the gap between when a task is scheduled and when it actually
    starts executing. A non-zero wait time indicates the task was blocked waiting
    for data dependencies (transfers from predecessor tasks) to complete.

---

## Combining Flags

Flags can be combined to show multiple views in a single invocation:

```bash
# Show timeline and per-task details together
python analyze_trace.py output/basic/trace.jsonl --timeline --tasks

# Show everything
python analyze_trace.py output/basic/trace.jsonl --timeline --gantt --tasks
```

---

## Custom Analysis

The trace file is standard JSON Lines, making it straightforward to write
custom analysis scripts in Python.

### Extracting makespan from multiple runs

```python
import json
from pathlib import Path

results = {}
for trace_path in sorted(Path("output/sweep").rglob("trace.jsonl")):
    with open(trace_path) as f:
        for line in f:
            event = json.loads(line)
            if event["type"] == "sim_end":
                run_name = trace_path.parent.name
                results[run_name] = event["makespan"]
                break

for run, makespan in sorted(results.items()):
    print(f"{run}: {makespan:.4f}s")
```

### Comparing scheduler performance

```python
import json
from pathlib import Path
from collections import defaultdict

# Collect makespans grouped by scheduler
scheduler_makespans = defaultdict(list)

for metrics_path in Path("output/sweep").rglob("metrics.json"):
    with open(metrics_path) as f:
        m = json.load(f)
    # Assumes directory names like "heft_s1", "cpop_s3", etc.
    scheduler = metrics_path.parent.name.rsplit("_s", 1)[0]
    scheduler_makespans[scheduler].append(m["makespan"])

# Print comparison
print(f"{'Scheduler':<15} {'Mean':>8} {'Std':>8} {'Min':>8} {'Max':>8}")
print("-" * 55)
for sched in sorted(scheduler_makespans):
    vals = scheduler_makespans[sched]
    mean = sum(vals) / len(vals)
    std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
    print(f"{sched:<15} {mean:>8.4f} {std:>8.4f} {min(vals):>8.4f} {max(vals):>8.4f}")
```

### Computing transfer overhead percentage

Measure how much of the total execution time is spent on data transfers versus
computation:

```python
import json

def compute_overhead(trace_path):
    """Compute transfer overhead as a percentage of total active time."""
    total_compute = 0.0
    total_transfer = 0.0

    with open(trace_path) as f:
        for line in f:
            event = json.loads(line)
            if event["type"] == "task_complete":
                total_compute += event.get("duration", 0.0)
            elif event["type"] == "transfer_complete":
                total_transfer += event.get("duration", 0.0)

    total = total_compute + total_transfer
    if total == 0:
        return 0.0
    return (total_transfer / total) * 100

overhead = compute_overhead("output/basic/trace.jsonl")
print(f"Transfer overhead: {overhead:.1f}%")
```

### Extracting per-node task counts

```python
import json
from collections import Counter

node_tasks = Counter()

with open("output/basic/trace.jsonl") as f:
    for line in f:
        event = json.loads(line)
        if event["type"] == "task_start":
            node_tasks[event["node_id"]] += 1

print("Tasks per node:")
for node, count in node_tasks.most_common():
    print(f"  {node}: {count}")
```

### Building a timeline DataFrame

For more advanced analysis, convert trace events into a pandas DataFrame:

```python
import json
import pandas as pd

events = []
with open("output/basic/trace.jsonl") as f:
    for line in f:
        events.append(json.loads(line))

df = pd.DataFrame(events)

# Filter to task events and compute busy intervals
tasks = df[df["type"].isin(["task_start", "task_complete"])]
print(tasks[["sim_time", "type", "task_id", "node_id"]].to_string(index=False))
```

!!! tip "Visualization"
    For graphical Gantt charts, network topology views, and interactive
    timeline exploration, see the [Visualization Overview](../viz/viz-overview.md)
    section. The built-in web visualization tool can load trace files directly
    and provides a richer interactive experience than the CLI analysis script.

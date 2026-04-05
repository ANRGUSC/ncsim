# Output Files

Every ncsim run produces three files in the `--output` directory. Together,
these files form a self-contained record that can fully reproduce and analyze
any simulation run.

```
output/
  scenario.yaml      # Copy of input scenario with all defaults filled in
  trace.jsonl         # One JSON object per line for every discrete event
  metrics.json        # Summary statistics for the run
```

---

## scenario.yaml

A verbatim copy of the input scenario YAML file, placed in the output directory
for convenience. This ensures that every output folder is self-contained -- you
can re-run the exact same simulation from the output directory alone.

```bash
# Re-run from a previous output folder
ncsim --scenario output/my_run/scenario.yaml --output output/my_run_v2
```

!!! tip "Self-contained output folders"
    Copying the scenario into the output directory means you never lose track of
    which configuration produced a given set of results, even if you later modify
    the original scenario file.

---

## trace.jsonl

The trace file records every discrete event that occurred during the simulation,
one JSON object per line (JSON Lines format). Events are written in
chronological order with monotonically increasing sequence numbers.

### Example Trace

```jsonl
{"seq":0,"sim_time":0.0,"type":"sim_start","trace_version":"1.0","seed":42,"scenario":"demo_simple.yaml"}
{"seq":1,"sim_time":0.0,"type":"dag_inject","dag_id":"dag_1","task_ids":["T0","T1"]}
{"seq":2,"sim_time":0.0,"type":"task_scheduled","dag_id":"dag_1","task_id":"T0","node_id":"n0"}
{"seq":3,"sim_time":0.0,"type":"task_start","dag_id":"dag_1","task_id":"T0","node_id":"n0"}
{"seq":4,"sim_time":0.0,"type":"task_scheduled","dag_id":"dag_1","task_id":"T1","node_id":"n0"}
{"seq":5,"sim_time":1.0,"type":"task_complete","dag_id":"dag_1","task_id":"T0","node_id":"n0","duration":1.0}
{"seq":6,"sim_time":1.0,"type":"transfer_start","dag_id":"dag_1","from_task":"T0","to_task":"T1","link_id":"l01","data_size":50}
{"seq":7,"sim_time":1.501,"type":"transfer_complete","dag_id":"dag_1","from_task":"T0","to_task":"T1","link_id":"l01","duration":0.501}
{"seq":8,"sim_time":1.501,"type":"task_start","dag_id":"dag_1","task_id":"T1","node_id":"n0"}
{"seq":9,"sim_time":3.501,"type":"task_complete","dag_id":"dag_1","task_id":"T1","node_id":"n0","duration":2.0}
{"seq":10,"sim_time":3.501,"type":"sim_end","status":"completed","makespan":3.501,"total_events":10}
```

### Event Type Reference

| Event Type | Key Fields | Description |
|---|---|---|
| `sim_start` | `trace_version`, `seed`, `scenario`, `scenario_hash` | Simulation begins. Always the first event (`seq: 0`). |
| `dag_inject` | `dag_id`, `task_ids` | A DAG is injected into the simulation at the specified `sim_time`. |
| `task_scheduled` | `dag_id`, `task_id`, `node_id` | The scheduler assigns a task to a compute node. |
| `task_start` | `dag_id`, `task_id`, `node_id` | A task begins executing on its assigned node. |
| `task_complete` | `dag_id`, `task_id`, `node_id`, `duration` | A task finishes execution. `duration` is wall-clock compute time. |
| `transfer_start` | `dag_id`, `from_task`, `to_task`, `link_id`, `data_size` | A data transfer begins between two tasks. `data_size` is in MB. May include `route` for multi-hop paths. |
| `transfer_complete` | `dag_id`, `from_task`, `to_task`, `link_id`, `duration` | A data transfer finishes. `duration` is total transfer time in seconds. May include `route` for multi-hop paths. |
| `sim_end` | `status`, `makespan`, `total_events` | Simulation complete. Always the last event. |

### Common Fields

Every event includes these fields:

| Field | Type | Description |
|---|---|---|
| `seq` | int | Monotonically increasing sequence number, starting at 0 |
| `sim_time` | float | Simulation time in seconds when the event occurred |
| `type` | string | Event type identifier (see table above) |

!!! note "Time precision"
    All `sim_time` and `duration` values are rounded to microsecond precision
    (6 decimal places) to avoid floating-point drift across long simulations.

---

## metrics.json

A JSON file containing summary statistics for the simulation run.

### Example

```json
{
  "scenario": "demo_simple.yaml",
  "seed": 42,
  "makespan": 3.501,
  "total_tasks": 2,
  "total_transfers": 1,
  "total_events": 10,
  "status": "completed",
  "node_utilization": {
    "n0": 0.857,
    "n1": 0.0
  },
  "link_utilization": {
    "l01": 0.143
  }
}
```

### Field Reference

| Field | Type | Description |
|---|---|---|
| `scenario` | string | Name of the input scenario YAML file |
| `seed` | int | Random seed used for this run |
| `makespan` | float | Total simulation time from first event to last task completion (seconds) |
| `total_tasks` | int | Number of tasks across all DAGs |
| `total_transfers` | int | Number of data-dependency edges across all DAGs |
| `total_events` | int | Total number of discrete events in the trace |
| `status` | string | `"completed"` on success, `"error"` on failure |
| `node_utilization` | object | Per-node utilization ratio (0.0--1.0). Computed as total busy time divided by makespan. |
| `link_utilization` | object | Per-link utilization ratio (0.0--1.0). Computed as total transfer time divided by makespan. |
| `error_message` | string | Present only when `status` is `"error"`. Describes the failure. |

When the WiFi interference model (`csma_clique` or `csma_bianchi`) is active,
additional fields are included:

| Field | Type | Description |
|---|---|---|
| `rf_config` | object | Full RF configuration used (tx power, frequency, path loss exponent, etc.) |
| `carrier_sensing_range_m` | float | Computed carrier sensing range in meters |
| `link_phy_rates_MBps` | object | Per-link PHY data rate in MB/s before contention adjustment |
| `max_clique_sizes` | object | Per-link maximum clique size from the conflict graph |

---

## Working with Output Files

### Loading trace.jsonl in Python

```python
import json

def load_trace(path):
    """Load all events from a trace file."""
    events = []
    with open(path) as f:
        for line in f:
            events.append(json.loads(line))
    return events

events = load_trace("output/my_run/trace.jsonl")
print(f"Total events: {len(events)}")
print(f"Makespan: {events[-1]['makespan']}")
```

### Filtering events by type

```python
events = load_trace("output/my_run/trace.jsonl")

# Get all task completion events
completions = [e for e in events if e["type"] == "task_complete"]
for c in completions:
    print(f"  {c['task_id']} on {c['node_id']}: {c['duration']:.3f}s")
```

### Loading metrics.json in Python

```python
import json

with open("output/my_run/metrics.json") as f:
    metrics = json.load(f)

print(f"Makespan: {metrics['makespan']:.3f}s")
print(f"Status: {metrics['status']}")

# Print node utilization
for node, util in metrics["node_utilization"].items():
    print(f"  {node}: {util:.1%}")
```

### Comparing two runs

```python
import json

def load_metrics(path):
    with open(path) as f:
        return json.load(f)

m1 = load_metrics("output/heft_run/metrics.json")
m2 = load_metrics("output/cpop_run/metrics.json")

speedup = m1["makespan"] / m2["makespan"]
print(f"HEFT makespan:  {m1['makespan']:.3f}s")
print(f"CPOP makespan:  {m2['makespan']:.3f}s")
print(f"CPOP speedup:   {speedup:.2f}x")
```

### Computing transfer overhead from trace

```python
events = load_trace("output/my_run/trace.jsonl")

total_compute = sum(
    e["duration"] for e in events if e["type"] == "task_complete"
)
total_transfer = sum(
    e["duration"] for e in events if e["type"] == "transfer_complete"
)

overhead = total_transfer / (total_compute + total_transfer) * 100
print(f"Compute time:    {total_compute:.3f}s")
print(f"Transfer time:   {total_transfer:.3f}s")
print(f"Transfer overhead: {overhead:.1f}%")
```

!!! warning "Large trace files"
    For scenarios with many DAGs or tasks, trace files can grow large. Consider
    streaming the JSONL file line-by-line rather than loading the entire file
    into memory:

    ```python
    import json

    with open("output/big_run/trace.jsonl") as f:
        for line in f:
            event = json.loads(line)
            if event["type"] == "task_complete":
                # Process incrementally
                pass
    ```

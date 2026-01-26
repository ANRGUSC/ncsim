# ncsim Development Notes

This document contains development tips and common pitfalls when working with the ncsim codebase.

> **IMPORTANT**: When you complete a checkpoint or learn something new about ncsim development, add it to the "Lessons Learned" section at the bottom of this file. This helps future development sessions avoid repeating mistakes.

## Project Structure

```
ncsim/
├── pyproject.toml              # Package configuration and dependencies
├── ncsim/
│   ├── __init__.py             # Package exports
│   ├── __main__.py             # Entry point for `python -m ncsim`
│   ├── main.py                 # CLI implementation
│   ├── core/
│   │   ├── event_queue.py      # Priority queue for DES events
│   │   ├── execution_engine.py # Task/transfer handlers
│   │   ├── simulation.py       # Main simulation loop
│   │   └── telemetry.py        # State collection for analysis
│   ├── models/
│   │   ├── network.py          # Node, Link, Network + LinkModel ABC
│   │   ├── task.py             # Task, TaskState + QueueModel ABC
│   │   ├── dag.py              # DAG, Edge + DAGSource ABC
│   │   ├── routing.py          # RoutingModel ABC + DirectLinkRouting
│   │   └── disruptions.py      # DisruptionModel ABC + NoDisruptions
│   ├── scheduler/
│   │   ├── base.py             # Scheduler ABC, PlacementPlan
│   │   └── saga_adapter.py     # HEFT/CPOP via anrg-saga
│   └── io/
│       ├── scenario_loader.py  # YAML scenario parsing
│       ├── trace_writer.py     # JSONL trace output
│       └── results_writer.py   # metrics.json output
├── tests/                      # pytest test suite
└── scenarios/                  # Example scenario files
```

## Installation

```bash
cd ncsim
pip install -e .           # Install in editable mode
pip install -e ".[dev]"    # Include dev dependencies (pytest)
```

## Running

```bash
# Via installed entry point
ncsim --scenario scenarios/demo_simple.yaml --output /tmp/test

# Via module
python -m ncsim --scenario scenarios/demo_simple.yaml --output /tmp/test

# With options
ncsim --scenario demo.yaml --output out/ --seed 42 --scheduler heft -v
```

## Testing

```bash
cd ncsim
python -m pytest tests/ -v           # Run all tests
python -m pytest tests/ -v -k heft   # Run tests matching 'heft'
python -m pytest tests/ --cov=ncsim  # With coverage
```

## Key Design Decisions

### Extensibility Architecture

ncsim uses Abstract Base Classes (ABCs) to enable future extensions without modifying core code:

| Dimension | Phase 2 Implementation | Future Options |
|-----------|------------------------|----------------|
| Link bandwidth | `StaticLinkModel` | Position-based, interference, TDMA |
| Scheduling | `SagaScheduler` (HEFT) | RL policies, preemptive |
| Task execution | Run-to-completion | Preemptible, checkpointed |
| DAG arrival | `SingleDAGSource` | Multiple, periodic |
| Node queues | `FIFOQueueModel` | Priority, multi-slot |
| Routing | `DirectLinkRouting` | Multi-hop, multi-path |
| Disruptions | `NoDisruptions` | Jamming, failures |

### Time Precision

All simulation times use microsecond precision (6 decimal places):

```python
def round_time(t: float) -> float:
    return round(t, 6)
```

This ensures deterministic behavior by avoiding floating-point precision issues.

### Event Priority

Events at the same simulation time are processed in this order:
1. DAG_INJECT (priority 0)
2. TASK_COMPLETE (priority 1)
3. TRANSFER_COMPLETE (priority 2)
4. TASK_READY (priority 3)
5. TASK_START (priority 4)
6. TRANSFER_START (priority 5)

Within same time and priority, events are processed in FIFO order (by event_id).

### Bandwidth Sharing

When N transfers share a link simultaneously:
- Each gets `bandwidth / N` effective bandwidth
- Completion times are recalculated when transfers start/complete
- Old completion events are cancelled, new ones scheduled

## Common Errors

### "No module named ncsim.__main__"

**Cause:** Missing `__main__.py` file for module execution.

**Solution:** Create `ncsim/__main__.py`:
```python
from ncsim.main import main

if __name__ == "__main__":
    main()
```

### "SAGA library not available"

**Cause:** anrg-saga not installed or import error.

**Solution:**
```bash
pip install anrg-saga
# If pygraphviz fails (Windows), install without it:
pip install anrg-saga --no-deps
pip install networkx numpy scipy pandas pydantic tqdm
```

### Event Queue Non-Determinism

**Cause:** Events at same time processed in wrong order.

**Solution:** Always use the three-tuple sort key:
```python
sort_key = (round_time(sim_time), event_type.value, event_id)
```

### "to_node 'X' not found"

**Cause:** Link references a node that doesn't exist in the network.

**Solution:** Ensure all node IDs in links exist in the nodes dict. The Network class validates this in `__post_init__`.

## Trace Format

Output is JSONL (one JSON object per line):

```jsonl
{"seq":0,"sim_time":0.0,"type":"sim_start","trace_version":"1.0","seed":42,"scenario":"demo.yaml"}
{"seq":1,"sim_time":0.0,"type":"dag_inject","dag_id":"dag_1","task_ids":["T0","T1"]}
{"seq":2,"sim_time":0.0,"type":"task_scheduled","dag_id":"dag_1","task_id":"T0","node_id":"n0"}
...
{"seq":10,"sim_time":3.501,"type":"sim_end","status":"completed","makespan":3.501}
```

## SAGA Integration

ncsim wraps the anrg-saga library for HEFT/CPOP scheduling:

```python
from ncsim.scheduler.saga_adapter import create_scheduler

scheduler = create_scheduler("heft")  # or "cpop" or "round_robin"
```

**Key patterns from saga-service:**
- SAGA requires a fully-connected graph
- Use `DISCONNECTED_SPEED=0.001` for non-connected pairs
- Use `LOCAL_SPEED=10000.0` for same-node transfers
- Node names use format `node_0`, `node_1`, etc.

---

## Lessons Learned

### Initial Implementation: __main__.py Required (2026-01-25)

**Problem:** Running `python -m ncsim` failed with "No module named ncsim.__main__"

**Cause:** Python module execution requires `__main__.py` entry point.

**Solution:** Created `ncsim/__main__.py`:
```python
from ncsim.main import main

if __name__ == "__main__":
    main()
```

**Lesson:** When creating a Python package with CLI, always create `__main__.py` that imports and calls the main function. This enables both:
- `python -m ncsim ...` (module execution)
- `ncsim ...` (entry point from pyproject.toml)

### Bug Fix: Multiple Tasks Starting on Same Node (2026-01-25)

**Problem:** When two TASK_READY events occurred at the same simulation time for tasks assigned to the same node, both would "start immediately" instead of one being queued.

**Root Cause:** In `_handle_task_ready`, when deciding to start a task (node is idle), we scheduled TASK_START but didn't mark the node as busy until TASK_START was processed. Since TASK_READY has higher priority than TASK_START, all TASK_READY events at the same time were processed first, and all saw the node as idle.

**Fix:** Set `node_state.current_task = task_state` immediately in TASK_READY when scheduling TASK_START, not in TASK_START.

```python
# In _handle_task_ready:
if node_state.is_idle():
    # Mark node as busy NOW to prevent other TASK_READY events
    # at same time from also starting
    node_state.current_task = task_state
    self.event_queue.schedule(...)
```

**Lesson:** When state changes affect future event processing at the same simulation time, update state immediately rather than deferring to a later event.

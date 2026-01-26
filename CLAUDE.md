# iobt-ncsim
## Immersive Networked Compute Simulator
### Project Specification for Claude Code

---

## 1. HIGH-LEVEL VISION

Build a research and demonstration platform for networked computing:

| Component | Purpose | Status |
|-----------|---------|--------|
| **iobt-viz + saga-service** | Interactive demos with RTS-style visualization | ✅ MVP Complete |
| **ncsim** | Headless DES for research experiments | 🔨 Phase 2 |
| **Trace playback** | Visualize ncsim results in iobt-viz | 📋 Phase 3 |

**Design Philosophy**: 
- **iobt-viz owns time in demos**: Acts as "the world" that algorithms react to
- **ncsim is headless-first**: Optimized for speed and reproducibility
- **saga-service is the brain**: Scheduling algorithms plug in here (HEFT, CPOP, future RL policies)

```
DEMO MODE (MVP Complete):               RESEARCH MODE (Phase 2):
┌──────────────┐                        ┌──────────────┐
│   iobt-viz   │ ◄─TCP─► saga-service   │    ncsim     │ → trace.jsonl
│ (owns time)  │         (HEFT/CPOP)    │  (headless)  │ → metrics.json
└──────────────┘                        └──────────────┘
```

**Future Work** (not in current scope): Gymnasium RL environment, trained policy deployment.

---

## 2. GLOSSARY AND TIMING MODELS

**This section is authoritative. All implementations must follow these definitions.**

### 2.1 Units

| Quantity | Unit | Type | Example |
|----------|------|------|---------|
| `sim_time` | seconds | float | 10.5 |
| `compute_capacity` | compute_units/second | float | 100.0 |
| `compute_cost` | compute_units | float | 500.0 |
| `bandwidth` | MB/second | float | 100.0 |
| `latency` | seconds | float | 0.005 |
| `data_size` | MB | float | 200.0 |

### 2.2 Compute Time Model

```
task_runtime_sec = compute_cost / node.compute_capacity
```

Example: Task with `compute_cost=500` on node with `compute_capacity=100` runs for 5.0 seconds.

### 2.3 Node Execution Model

**Single-server FIFO queue per node:**
- Each node executes at most one task at a time
- Tasks wait in a FIFO queue if the node is busy
- No preemption: once a task starts, it runs to completion
- Queue has unlimited capacity

### 2.4 Network Transfer Model

**Single-hop direct links only:**
- Transfers occur only on explicitly declared links
- No multi-hop routing
- If no direct link exists between source and destination nodes, the transfer fails

```
transfer_time_sec = (data_size / link.bandwidth) + link.latency
```

Example: 200 MB transfer on link with `bandwidth=100` MB/s and `latency=0.005` takes 2.005 seconds.

### 2.5 Bandwidth Sharing Model

**Fair share among concurrent flows:**
- If N transfers share a link simultaneously, each gets `bandwidth / N`
- Transfer times are recalculated when flows start or complete
- Transfers in progress have their completion times updated dynamically

```python
effective_bandwidth = link.bandwidth / num_concurrent_transfers
remaining_data = original_data_size - data_already_transferred
new_completion_time = current_time + (remaining_data / effective_bandwidth)
```

### 2.6 Time Precision

**All simulation times are rounded to microsecond precision (6 decimal places):**

```python
def round_time(t: float) -> float:
    return round(t, 6)
```

This applies at event scheduling, event completion, and any time comparison.

---

## 3. NCSIM CORE SPECIFICATION

### 3.1 Task Mapper Interface

```python
from abc import ABC, abstractmethod
from typing import List, Dict
from dataclasses import dataclass

@dataclass
class PlacementPlan:
    """Output of Task Mapper."""
    assignments: Dict[str, str]  # task_id → node_id

@dataclass 
class NetworkSnapshot:
    """Current network state."""
    nodes: Dict[str, 'NodeState']
    links: Dict[str, 'LinkState']
    timestamp: float

class TaskMapper(ABC):
    @abstractmethod
    def compute_placement(
        self,
        dag: 'DAG',
        network: NetworkSnapshot,
    ) -> PlacementPlan:
        """Compute task-to-node assignments for a DAG."""
        pass
```

### 3.2 Task Mapper Semantics (AUTHORITATIVE)

**The Task Mapper decides WHERE. The Execution Engine decides WHEN.**

| Responsibility | Task Mapper | Execution Engine |
|----------------|-------------|------------------|
| Which node runs each task | ✓ Decides | Follows plan |
| When tasks start | ✗ | ✓ Based on readiness + queues |
| Transfer timing | ✗ | ✓ Based on bandwidth/contention |
| Handling failures | ✗ | ✓ Logs and continues |

**When `compute_placement` is called:**
- DAG injected: ✓ Called once
- Task/transfer completed: ✗ Not called (no rescheduling in Phase 2)
- Topology changed: ✗ Not called (static topology in Phase 2)

### 3.3 Execution Engine Behavior

When a DAG is injected:
1. Call `task_mapper.compute_placement(dag, network_snapshot)`
2. For each task with no predecessors, schedule `TASK_READY` event at current sim_time
3. Process events in priority order (see §3.5)

When a task becomes READY:
1. If assigned node is idle: start task immediately, schedule `TASK_COMPLETE`
2. If assigned node is busy: add to node's FIFO queue

When a task completes:
1. For each outgoing edge: schedule `TRANSFER_START`
2. If node has queued tasks: start next task

When a transfer starts:
1. Recalculate all concurrent transfers on that link (bandwidth sharing)
2. Schedule `TRANSFER_COMPLETE` based on effective bandwidth

When a transfer completes:
1. Recalculate remaining transfers on that link
2. Check if destination task has all inputs → schedule `TASK_READY`

### 3.4 Event Types

| Event Type | Priority | Description |
|------------|----------|-------------|
| `DAG_INJECT` | 0 | New DAG arrives |
| `TASK_COMPLETE` | 1 | Task finishes execution |
| `TRANSFER_COMPLETE` | 2 | Data transfer finishes |
| `TASK_READY` | 3 | Task ready to execute |
| `TASK_START` | 4 | Task begins execution |
| `TRANSFER_START` | 5 | Data transfer begins |

### 3.5 Event Ordering (AUTHORITATIVE)

```python
def event_sort_key(event):
    return (
        round(event.sim_time, 6),  # Primary: time (microsecond precision)
        event.priority,             # Secondary: event type priority
        event.event_id              # Tertiary: insertion order (FIFO)
    )
```

**Determinism guarantee:** Same inputs + same seed = identical event sequence.

---

## 4. TRACE FORMAT SPECIFICATION

### 4.1 Format

**File:** `{run_id}_trace.jsonl` (JSON Lines, UTF-8)

**Every line is a JSON object with these required fields:**

| Field | Type | Description |
|-------|------|-------------|
| `seq` | int | Monotonically increasing sequence number (0, 1, 2, ...) |
| `sim_time` | float | Simulation time in seconds (6 decimal precision) |
| `type` | string | Event type (see below) |

### 4.2 Event Schemas

**`sim_start` (seq=0, always first):**
```json
{"seq": 0, "sim_time": 0.0, "type": "sim_start", "trace_version": "1.0", "seed": 42, "scenario": "demo.yaml", "scenario_hash": "a1b2c3d4"}
```

**`dag_inject`:**
```json
{"seq": 1, "sim_time": 0.0, "type": "dag_inject", "dag_id": "dag_1", "task_ids": ["T0", "T1", "T2"]}
```

**`task_scheduled`:**
```json
{"seq": 2, "sim_time": 0.0, "type": "task_scheduled", "dag_id": "dag_1", "task_id": "T0", "node_id": "n0"}
```

**`task_start`:**
```json
{"seq": 3, "sim_time": 0.0, "type": "task_start", "dag_id": "dag_1", "task_id": "T0", "node_id": "n0"}
```

**`task_complete`:**
```json
{"seq": 4, "sim_time": 5.0, "type": "task_complete", "dag_id": "dag_1", "task_id": "T0", "node_id": "n0", "duration": 5.0}
```

**`transfer_start`:**
```json
{"seq": 5, "sim_time": 5.0, "type": "transfer_start", "dag_id": "dag_1", "from_task": "T0", "to_task": "T1", "link_id": "l01", "data_size": 200.0}
```

**`transfer_complete`:**
```json
{"seq": 6, "sim_time": 7.005, "type": "transfer_complete", "dag_id": "dag_1", "from_task": "T0", "to_task": "T1", "link_id": "l01", "duration": 2.005}
```

**`sim_end` (always last):**
```json
{"seq": 10, "sim_time": 15.0, "type": "sim_end", "status": "completed", "makespan": 15.0, "total_events": 10}
```

### 4.3 Required Fields Per Event Type

| Event Type | Required Fields (besides seq, sim_time, type) |
|------------|----------------------------------------------|
| `sim_start` | `trace_version`, `seed`, `scenario` |
| `sim_end` | `status`, `makespan` |
| `dag_inject` | `dag_id`, `task_ids` |
| `task_scheduled` | `dag_id`, `task_id`, `node_id` |
| `task_start` | `dag_id`, `task_id`, `node_id` |
| `task_complete` | `dag_id`, `task_id`, `node_id`, `duration` |
| `transfer_start` | `dag_id`, `from_task`, `to_task`, `link_id`, `data_size` |
| `transfer_complete` | `dag_id`, `from_task`, `to_task`, `link_id`, `duration` |

---

## 5. PHASE 1: DEMO STACK (✅ COMPLETE)

**Status:** MVP implemented and functional.

**Components:**
- **iobt-viz**: OpenRA-derived visualization with network overlay, DAG visualization, task states
- **saga-service**: TCP wrapper (port 9999) for anrg-saga HEFT/CPOP schedulers
- **Configuration GUI**: Set node count, comm range, DAG structure

**Running the demo:**
```bash
# Terminal 1: Start scheduler
.\runsched

# Terminal 2: Configure and run
runconfig   # Set parameters
runiobt     # Launch visualization
```

**Hotkeys:** N (toggle network overlay), Escape (menu)

---

## 6. PHASE 2: NCSIM CORE ENGINE

### 6.1 Scope (EXACTLY THIS)

**Included:**
- Static topology (no mobility, no link up/down)
- Single DAG injected at t=0
- Deterministic event queue with trace writer
- Single-server FIFO queue per node
- Single-hop transfers only (no routing)
- Fair bandwidth sharing
- SAGA integration (HEFT scheduler)
- CLI: `ncsim --scenario X.yaml --output dir/`

**Explicitly NOT included (future work):**
- Mobility / node movement
- Link up/down events / jammers
- Multiple DAGs / rescheduling
- Multi-hop routing
- Gymnasium environment / RL

### 6.2 Checkpoints

#### 6.2.1 Project Setup
- [ ] Create `ncsim/` directory structure
- [ ] `pyproject.toml` with dependencies: `anrg-saga`, `networkx`, `pyyaml`
- [ ] Verify: `python -c "from saga import HeftScheduler"` works
- [ ] Commit: "ncsim: initial project structure"

#### 6.2.2 Event Queue
- [ ] Priority queue with `heapq`
- [ ] `event_sort_key()` per §3.5
- [ ] `schedule(time, event) -> event_id`
- [ ] `pop() -> event`
- [ ] Unit test: events at same time ordered by priority then event_id
- [ ] Commit: "ncsim: event queue"

#### 6.2.3 Data Models
- [ ] `Node`: id, compute_capacity, position
- [ ] `Link`: id, from_node, to_node, bandwidth, latency
- [ ] `Network`: nodes dict, links dict
- [ ] `Task`: id, compute_cost, dag_id
- [ ] `DAG`: id, tasks dict, edges list
- [ ] `Edge`: from_task, to_task, data_size
- [ ] Unit tests for model creation
- [ ] Commit: "ncsim: data models"

#### 6.2.4 Scenario Loader
- [ ] Parse YAML per §7.1 schema
- [ ] Return `Scenario` object with network + dags
- [ ] Unit test with `demo_simple.yaml`
- [ ] Commit: "ncsim: scenario loader"

#### 6.2.5 SAGA Integration
- [ ] `SagaTaskMapper` implements `TaskMapper`
- [ ] Convert `Network` → SAGA network format
- [ ] Convert `DAG` → SAGA taskgraph format
- [ ] Extract assignments from SAGA schedule
- [ ] Unit test: HEFT produces valid assignments
- [ ] Commit: "ncsim: SAGA integration"

#### 6.2.6 Execution Engine
- [ ] Node state: current_task, queue
- [ ] Link state: active_transfers list
- [ ] `handle_dag_inject()`: call mapper, schedule initial TASK_READY events
- [ ] `handle_task_ready()`: start or queue
- [ ] `handle_task_complete()`: schedule transfers, start queued task
- [ ] `handle_transfer_start()`: recalc bandwidth, schedule complete
- [ ] `handle_transfer_complete()`: recalc bandwidth, check successors ready
- [ ] Bandwidth sharing per §2.5
- [ ] Unit tests for each handler
- [ ] Commit: "ncsim: execution engine"

#### 6.2.7 Simulation Loop
- [ ] `Simulation.run()`: pop events until queue empty
- [ ] Inject DAG at t=0
- [ ] Compute makespan (last task_complete time)
- [ ] Integration test: simple DAG runs correctly
- [ ] Commit: "ncsim: simulation loop"

#### 6.2.8 Trace Writer
- [ ] Write JSONL per §4 spec
- [ ] `sim_start` with trace_version, seed, scenario, scenario_hash
- [ ] All events with required fields
- [ ] `sim_end` with makespan
- [ ] Unit test: trace file matches schema
- [ ] Commit: "ncsim: trace writer"

#### 6.2.9 CLI
- [ ] `ncsim --scenario PATH --output DIR [--seed N]`
- [ ] Write `trace.jsonl` and `metrics.json` to output dir
- [ ] Commit: "ncsim: CLI"

### 6.3 Acceptance Tests (MUST PASS)

#### Test 1: Golden Trace
```bash
ncsim --scenario scenarios/demo_simple.yaml --seed 42 --output /tmp/test1/
diff /tmp/test1/trace.jsonl golden/demo_simple_seed42.jsonl
# Must be identical
```

#### Test 2: Determinism
```bash
ncsim --scenario scenarios/demo_simple.yaml --seed 42 --output /tmp/test2a/
ncsim --scenario scenarios/demo_simple.yaml --seed 42 --output /tmp/test2b/
diff /tmp/test2a/trace.jsonl /tmp/test2b/trace.jsonl
# Must be identical
```

#### Test 3: Dependency Ordering
```python
def test_dependency_ordering(trace, dag):
    """No task_start before all predecessor transfer_complete."""
    completed_transfers = set()
    for event in trace:
        if event['type'] == 'transfer_complete':
            completed_transfers.add((event['from_task'], event['to_task']))
        if event['type'] == 'task_start':
            task_id = event['task_id']
            for edge in dag.edges:
                if edge.to_task == task_id:
                    assert (edge.from_task, task_id) in completed_transfers
```

#### Test 4: Bandwidth Contention
```yaml
# Two transfers on same link should each take 2 sec (not 1 sec)
# See scenarios/bandwidth_contention.yaml
```

#### Test 5: Makespan Calculation
```python
def test_makespan(trace, metrics):
    task_completes = [e for e in trace if e['type'] == 'task_complete']
    expected = max(e['sim_time'] for e in task_completes)
    assert metrics['makespan'] == expected
```

### 6.4 Demo Scenario

```yaml
# scenarios/demo_simple.yaml
scenario:
  name: "Simple Demo"
  
  network:
    nodes:
      - {id: n0, compute_capacity: 100, position: {x: 0, y: 0}}
      - {id: n1, compute_capacity: 50, position: {x: 10, y: 0}}
    links:
      - {id: l01, from: n0, to: n1, bandwidth: 100, latency: 0.001}
  
  dags:
    - id: dag_1
      inject_at: 0.0
      tasks:
        - {id: T0, compute_cost: 100}
        - {id: T1, compute_cost: 200}
      edges:
        - {from: T0, to: T1, data_size: 50}
  
  config:
    scheduler: heft
    seed: 42
```

**Expected (HEFT assigns both to n0):** T0 runs 0→1s, transfer 1→1.501s, T1 runs 1.501→3.501s. Makespan: 3.501

---

## 7. PHASE 3: TRACE PLAYBACK IN IOBT-VIZ

### 7.1 Goal

Visualize ncsim experiment results by playing back trace files in iobt-viz.

### 7.2 Approach

Lua script in iobt-viz that:
1. Loads `trace.jsonl` file
2. Maps trace events to visualization overlay commands
3. Provides playback controls (play, pause, speed, seek)

### 7.3 Event Mapping

| Trace Event | Visualization Action |
|-------------|---------------------|
| `task_start` | Highlight node, show task indicator |
| `task_complete` | Update task state, clear indicator |
| `transfer_start` | Highlight link, show transfer animation |
| `transfer_complete` | Clear link highlight |

### 7.4 Checkpoints

- [ ] Define trace player Lua script structure
- [ ] Parse trace.jsonl in Lua (or load pre-converted format)
- [ ] Map trace events to existing overlay commands
- [ ] Implement playback controls (play, pause, 1x/2x/0.5x speed)
- [ ] Implement seek/scrub to arbitrary sim_time
- [ ] Test with demo_simple trace
- [ ] Commit: "iobt-viz: trace playback mode"

### 7.5 Exit Criteria

- [ ] Can load trace file and play back visualization
- [ ] Visual output matches ncsim computation
- [ ] Speed controls work correctly
- [ ] Can pause and resume

---

## 8. DATA SCHEMAS

### 8.1 Scenario YAML Schema

```yaml
scenario:
  name: string              # Human-readable name
  
  network:
    nodes:
      - id: string          # Unique node identifier
        compute_capacity: float  # compute_units/second
        position: {x: float, y: float}  # For visualization
    links:
      - id: string          # Unique link identifier
        from: string        # Source node id
        to: string          # Destination node id
        bandwidth: float    # MB/second
        latency: float      # seconds
  
  dags:
    - id: string            # Unique DAG identifier
      inject_at: float      # sim_time to inject (0.0 for Phase 2)
      tasks:
        - id: string        # Unique within DAG
          compute_cost: float
          pinned_to: string  # Optional: force assignment to this node
      edges:
        - from: string      # Source task id
          to: string        # Destination task id
          data_size: float  # MB
  
  config:
    scheduler: string       # "heft" | "cpop" | "round_robin"
    seed: int               # Random seed for reproducibility
```

### 8.2 Metrics JSON Schema

```json
{
  "scenario": "demo_simple.yaml",
  "seed": 42,
  "makespan": 3.501,
  "total_tasks": 2,
  "total_transfers": 1,
  "total_events": 8,
  "node_utilization": {
    "n0": 0.856,
    "n1": 0.0
  },
  "link_utilization": {
    "l01": 0.143
  }
}
```

---

## 9. REPOSITORY STRUCTURE

```
iobt-ncsim/
├── CLAUDE.md                       # This file
├── README.md                       # User-facing overview
├── runsched.bat                    # Start saga-service
├── runconfig.bat                   # Configuration GUI
├── runiobt.bat                     # Launch visualization
│
├── reference/                      # READ-ONLY OpenRA reference
│
├── iobt-viz/                       # Visualization (C#, ✅ MVP)
│
├── saga-service/                   # TCP scheduler wrapper (✅ MVP)
│   ├── scheduler_service.py
│   └── requirements.txt
│
├── ncsim/                          # Headless simulator (Phase 2)
│   ├── pyproject.toml
│   ├── ncsim/
│   │   ├── __init__.py
│   │   ├── main.py                 # CLI entry point
│   │   ├── core/
│   │   │   ├── simulation.py
│   │   │   ├── event_queue.py
│   │   │   └── execution_engine.py
│   │   ├── models/
│   │   │   ├── network.py
│   │   │   ├── task.py
│   │   │   └── dag.py
│   │   ├── scheduler/
│   │   │   ├── base.py
│   │   │   └── saga_adapter.py
│   │   └── io/
│   │       ├── scenario_loader.py
│   │       ├── trace_writer.py
│   │       └── results_writer.py
│   ├── tests/
│   │   ├── test_event_queue.py
│   │   ├── test_execution_engine.py
│   │   ├── test_saga_adapter.py
│   │   └── test_acceptance.py
│   └── scenarios/
│       ├── demo_simple.yaml
│       └── bandwidth_contention.yaml
│
├── golden/                         # Expected outputs for tests
│   └── demo_simple_seed42.jsonl
│
└── scenarios/                      # Shared scenarios
```

---

## 10. FUTURE WORK (NOT IN CURRENT SCOPE)

The following are planned for future phases but explicitly out of scope for Phase 2-3:

- **Gymnasium RL environment**: Wrap ncsim as `gym.Env` for RL training
- **RL policy training**: Train scheduling policies with PPO/similar
- **Policy deployment**: Load trained policies into saga-service for demos
- **Mobility**: Node movement during simulation
- **Dynamic topology**: Link up/down, jammers, disruptions
- **Multi-DAG**: Multiple DAGs with rescheduling
- **Multi-hop routing**: Shortest-path routing across network

---

## APPENDIX A: SAGA-SERVICE PROTOCOL

**Port:** 9999 (TCP)

**Request:**
```json
{
  "type": "schedule_request",
  "nodes": [{"id": "n0", "compute_capacity": 100}, ...],
  "links": [{"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100, "latency": 0.001}, ...],
  "dag": {
    "id": "dag_1",
    "tasks": [{"id": "T0", "compute_cost": 100}, ...],
    "edges": [{"from": "T0", "to": "T1", "data_size": 50}, ...]
  }
}
```

**Response:**
```json
{
  "type": "schedule_response",
  "assignments": {"T0": "n0", "T1": "n0"}
}
```

---

## APPENDIX B: DEVELOPMENT NOTES

### B.1 Python Environment

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r saga-service/requirements.txt
pip install -e ncsim/  # After Phase 2
```

### B.2 Reference Copies

`reference/` is READ-ONLY. Consult to understand OpenRA patterns before modifying `iobt-viz/`.

---

## Author

**Bhaskar Krishnamachari** (USC), 2025-2026
Autonomous Networks Research Group (ANRG)
University of Southern California

# iobt-ncsim
## Immersive Networked Compute Simulator
### Project Specification for Claude Code

---

## 1. HIGH-LEVEL VISION

Build a research and demonstration platform for networked computing:

| Component | Purpose | Status |
|-----------|---------|--------|
| **iobt-viz + saga-service** | Interactive demos with RTS-style visualization | ✅ Complete (code removed from this branch) |
| **iobt-viz resilience modes** | Partition-resilient DAG execution demo | ✅ Complete (code removed from this branch) |
| **ncsim** | Headless DES for research experiments | ✅ Phase 2 Complete |
| **viz/ web UI** | Topology, Gantt, animated replay | ✅ Complete |

**Design Philosophy**:
- **ncsim is headless-first**: Optimized for speed and reproducibility
- **viz/ web UI**: React + FastAPI for interactive experiment configuration and trace visualization

```
RESEARCH + VISUALIZATION:
┌──────────────┐     ┌──────────────┐
│    ncsim     │ →   │   viz/ UI    │
│  (headless)  │     │ (React+API)  │
│              │ →   │              │
│ trace.jsonl  │     │ topology,    │
│ metrics.json │     │ Gantt, replay│
└──────────────┘     └──────────────┘
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

**Fair share among concurrent flows (composes with interference, see §2.7):**
- If N transfers share a link simultaneously, each gets `base_bandwidth / N`
- `base_bandwidth` = `link.bandwidth * interference_factor` (see §2.7)
- **Note:** Interference is enabled by default (`proximity` model, radius=15), so `interference_factor < 1.0` whenever nearby links are active
- Transfer times are recalculated when flows start or complete
- Transfers in progress have their completion times updated dynamically

```python
base_bandwidth = link.bandwidth * interference_factor  # §2.7, default=1.0
effective_bandwidth = base_bandwidth / num_concurrent_transfers
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

### 2.7 Inter-Link Interference Model

**Modular, orthogonal to per-link fair sharing.**

Inter-link interference models reduce a link's effective base bandwidth when nearby links are simultaneously active (e.g., wireless spectrum contention). This is composed with per-link fair sharing:

```
effective_per_flow = (link.bandwidth * interference_factor) / num_flows_on_link
```

**Interface** (`ncsim/ncsim/models/interference.py`):

```python
class InterferenceModel(ABC):
    def get_interference_factor(self, link_id, active_link_ids, network) -> float:
        """Returns multiplier in (0, 1.0]. 1.0 = no interference."""

    def get_affected_links(self, changed_link_id, active_link_ids, network) -> Set[str]:
        """Returns other active links whose factor changed (for recalculation)."""
```

**Built-in models:**

| Model | Class | Behavior | Default |
|-------|-------|----------|---------|
| `none` | `NoInterference` | Always returns 1.0, no cross-link effects | |
| `proximity` | `ProximityInterference(radius)` | Counts k active links within radius of link midpoint, returns 1/k | **Yes (radius=15)** |

**How proximity interference works:**
1. Compute midpoint of each link from its endpoint node positions
2. Count k = number of active links (including self) whose midpoints are within `interference_radius`
3. Each interfering link gets bandwidth multiplied by 1/k
4. When a transfer starts/completes, nearby links are recalculated via `_recalculate_interfered_transfers()`

**Example:** Two parallel links with midpoints 5 units apart, radius=15:
- Both active simultaneously → k=2 → each gets bandwidth/2
- Transfers take 2x longer than without interference

**Configuration:**
- CLI: `--interference {none,proximity} --interference-radius N`
- YAML: `config.interference` and `config.interference_radius`
- Default (when unspecified): `proximity` with `radius=15`

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
3. Recalculate transfers on interfered links (§2.7 cross-link effects)

When a transfer completes:
1. Recalculate remaining transfers on that link
2. Recalculate transfers on interfered links (§2.7 cross-link effects)
3. Check if destination task has all inputs → schedule `TASK_READY`

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

## 5. PHASE 1: DEMO STACK (✅ COMPLETE — code removed)

> **Note:** Phase 1 implementation (iobt-viz, saga-service, batch files) has been removed from this branch. The spec below is retained as historical reference. See the `main` branch history for the original code.

**Components (removed):**
- **iobt-viz**: OpenRA-derived visualization with network overlay, DAG visualization, task states
- **saga-service**: TCP wrapper (port 9999) for anrg-saga HEFT/CPOP schedulers
- **Configuration GUI**: Set node count, comm range, DAG structure

---

## 5A. PHASE 1A: RESILIENCE MODES (✅ COMPLETE — code removed)

> **Note:** Phase 1A implementation has been removed along with iobt-viz. The spec below is retained as historical reference.

**Status:** Implemented. Three switchable DAG execution modes for partition resilience demos.

### 5A.1 Modes

| Mode | Hotkey | Behavior |
|------|--------|----------|
| **Baseline** | B | Current behavior. Tasks stall on partition, wait for reconnection. |
| **Resilient** | R | On partition, restart entire DAG on largest connected component. |
| **Smart-Resilient** | S | On partition, preserve completed in-partition tasks, redeploy only remaining tasks. |

### 5A.2 How It Works

1. **Partition detection**: When tasks stall due to disconnected nodes, the connectivity monitor triggers redeployment (in Resilient/Smart-Resilient modes).
2. **Largest component selection**: BFS over compute nodes using `AreNodesConnected()` finds the largest connected component.
3. **Resilient redeployment**: Clears all task state, re-requests SAGA schedule (or round-robin) for all tasks on partition nodes.
4. **Smart-Resilient redeployment**: Identifies completed tasks whose assigned node is in the partition (results locally available). Only redeploys remaining tasks.
5. **Makespan tracking**: Per-mode makespans are recorded and displayed in the status panel for comparison.

### 5A.3 Hotkeys

| Key | Action |
|-----|--------|
| B | Switch to Baseline mode (restarts DAG) |
| R | Switch to Resilient mode (restarts DAG) |
| S | Switch to Smart-Resilient mode (restarts DAG) |
| N | Toggle network overlay |

### 5A.4 Status Panel

The status panel shows:
- Current mode name: `Mode: Baseline [B/R/S]`
- Current/last makespan
- Per-mode makespan comparison: `B: 12.5s | R: 8.2s | S-R: 6.1s`

### 5A.5 Files Modified

| File | Changes |
|------|---------|
| `iobt-viz/.../IoBTNetworkOverlay.cs` | Resilience mode state, `ClearDagDisplay()`, per-mode makespan storage, status panel rendering |
| `iobt-viz/.../IoBTScriptProperties.cs` | Lua API: `GetResilienceMode()`, `ConsumeResilienceModeChanged()`, `ClearDagDisplay()` |
| `iobt-viz/.../IoBTNetworkOverlayHotkeyLogic.cs` | B/R/S hotkey handlers |
| `iobt-viz/.../iobt-main.lua` | Partition finding, resilient/smart-resilient handlers, mode-aware connectivity monitor |

---

## 6. PHASE 2: NCSIM CORE ENGINE

**Architecture overview:** See [`ncsim/architecture.html`](https://htmlpreview.github.io/?https://github.com/ANRGUSC/iobt-ncsim/blob/master/ncsim/architecture.html) for a visual diagram of the engine components and data flow.

### 6.1 Scope (EXACTLY THIS)

**Included:**
- Static topology (no mobility, no link up/down)
- Single DAG injected at t=0
- Deterministic event queue with trace writer
- Single-server FIFO queue per node
- Multi-hop routing (direct, widest-path, shortest-path)
- Fair bandwidth sharing with inter-link interference (§2.7)
- SAGA integration (HEFT scheduler)
- CLI: `ncsim --scenario X.yaml --output dir/`

**Explicitly NOT included (future work):**
- Mobility / node movement
- Link up/down events / jammers
- Multiple DAGs / rescheduling
- Gymnasium environment / RL

### 6.2 Checkpoints

#### 6.2.1 Project Setup
- [x] Create `ncsim/` directory structure
- [x] `pyproject.toml` with dependencies: `anrg-saga`, `networkx`, `pyyaml`
- [x] Verify: `python -c "from saga import HeftScheduler"` works
- [x] Commit: "ncsim: initial project structure"

#### 6.2.2 Event Queue
- [x] Priority queue with `heapq`
- [x] `event_sort_key()` per §3.5
- [x] `schedule(time, event) -> event_id`
- [x] `pop() -> event`
- [x] Unit test: events at same time ordered by priority then event_id
- [x] Commit: "ncsim: event queue"

#### 6.2.3 Data Models
- [x] `Node`: id, compute_capacity, position
- [x] `Link`: id, from_node, to_node, bandwidth, latency
- [x] `Network`: nodes dict, links dict
- [x] `Task`: id, compute_cost, dag_id
- [x] `DAG`: id, tasks dict, edges list
- [x] `Edge`: from_task, to_task, data_size
- [x] Unit tests for model creation
- [x] Commit: "ncsim: data models"

#### 6.2.4 Scenario Loader
- [x] Parse YAML per §7.1 schema
- [x] Return `Scenario` object with network + dags
- [x] Unit test with `demo_simple.yaml`
- [x] Commit: "ncsim: scenario loader"

#### 6.2.5 SAGA Integration
- [x] `SagaTaskMapper` implements `TaskMapper`
- [x] Convert `Network` → SAGA network format
- [x] Convert `DAG` → SAGA taskgraph format
- [x] Extract assignments from SAGA schedule
- [x] Unit test: HEFT produces valid assignments
- [x] Commit: "ncsim: SAGA integration"

#### 6.2.6 Execution Engine
- [x] Node state: current_task, queue
- [x] Link state: active_transfers list
- [x] `handle_dag_inject()`: call mapper, schedule initial TASK_READY events
- [x] `handle_task_ready()`: start or queue
- [x] `handle_task_complete()`: schedule transfers, start queued task
- [x] `handle_transfer_start()`: recalc bandwidth, schedule complete
- [x] `handle_transfer_complete()`: recalc bandwidth, check successors ready
- [x] Bandwidth sharing per §2.5
- [x] Unit tests for each handler
- [x] Commit: "ncsim: execution engine"

#### 6.2.7 Simulation Loop
- [x] `Simulation.run()`: pop events until queue empty
- [x] Inject DAG at t=0
- [x] Compute makespan (last task_complete time)
- [x] Integration test: simple DAG runs correctly
- [x] Commit: "ncsim: simulation loop"

#### 6.2.8 Trace Writer
- [x] Write JSONL per §4 spec
- [x] `sim_start` with trace_version, seed, scenario, scenario_hash
- [x] All events with required fields
- [x] `sim_end` with makespan
- [x] Unit test: trace file matches schema
- [x] Commit: "ncsim: trace writer"

#### 6.2.9 CLI
- [x] `ncsim --scenario PATH --output DIR [--seed N]`
- [x] Write `trace.jsonl` and `metrics.json` to output dir
- [x] Commit: "ncsim: CLI"

### 6.3 Acceptance Tests (MUST PASS)

#### Test 1: Determinism
```bash
ncsim --scenario ncsim/scenarios/demo_simple.yaml --seed 42 --output /tmp/test1a/
ncsim --scenario ncsim/scenarios/demo_simple.yaml --seed 42 --output /tmp/test1b/
diff /tmp/test1a/trace.jsonl /tmp/test1b/trace.jsonl
# Must be identical
```

#### Test 2: Dependency Ordering
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

#### Test 3: Bandwidth Contention
```yaml
# Two transfers on same link should each take 2 sec (not 1 sec)
# See ncsim/scenarios/bandwidth_contention.yaml
```

#### Test 4: Makespan Calculation
```python
def test_makespan(trace, metrics):
    task_completes = [e for e in trace if e['type'] == 'task_complete']
    expected = max(e['sim_time'] for e in task_completes)
    assert metrics['makespan'] == expected
```

### 6.4 Demo Scenario

```yaml
# ncsim/scenarios/demo_simple.yaml
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

## 7. PHASE 3: TRACE PLAYBACK / VISUALIZATION

> **Note:** The original plan was iobt-viz trace playback (Lua-based). With iobt-viz removed, visualization is now handled by the `viz/` web UI (React + FastAPI). The spec below is retained as historical reference for the event mapping design.

### 7.1 Goal

Visualize ncsim experiment results by playing back trace files.

### 7.2 Approach (current: viz/ web UI)

The `viz/` web UI provides topology visualization, Gantt charts, and animated trace replay. See [viz/README.md](viz/README.md).

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
    routing: string         # "direct" | "widest_path" | "shortest_path"
    interference: string    # "none" | "proximity" (default: "proximity")
    interference_radius: float  # Radius for proximity model (default: 15.0)
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
ncsim/
├── CLAUDE.md                       # This file
├── README.md                       # User-facing overview
├── pyproject.toml                  # Python package config
│
├── ncsim/                          # Python package — headless DES engine
│   ├── __init__.py
│   ├── main.py                     # CLI entry point
│   ├── core/
│   │   ├── simulation.py
│   │   ├── event_queue.py
│   │   └── execution_engine.py
│   ├── models/
│   │   ├── network.py
│   │   ├── dag.py
│   │   ├── routing.py
│   │   ├── interference.py
│   │   └── wifi.py
│   ├── scheduler/
│   │   ├── base.py
│   │   └── saga_adapter.py
│   └── io/
│       ├── scenario_loader.py
│       ├── trace_writer.py
│       └── results_writer.py
│
├── viz/                            # Web visualization (React + FastAPI)
│   ├── src/                        # React frontend
│   ├── server/                     # FastAPI backend
│   └── public/                     # Sample experiment runs
│
├── scenarios/                      # Example scenario YAML files
├── tests/                          # Unit and integration tests
├── docs/                           # Architecture diagrams
├── reference/                      # READ-ONLY OpenRA SDK reference
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
- **Additional interference models**: TDMA, SINR-based, or learned interference patterns

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
pip install -e ".[dev]"
```

### B.2 Reference Copies

`reference/` is READ-ONLY. Retained as historical OpenRA SDK reference.

---

## Author

**Bhaskar Krishnamachari** (USC), 2025-2026
Autonomous Networks Research Group (ANRG)
University of Southern California

# ncsim Modularity Assessment

**Date:** 2026-02-14 (updated from ncsim-mg assessment of 2026-02-12)
**Overall Score:** 8.5/10
**Verdict:** Strong modular architecture with well-designed abstractions for scheduling, routing, and interference modeling. The 802.11 WiFi PHY/MAC model demonstrates the architecture's extensibility---it was added with zero execution engine changes. Remaining gaps are bandwidth sharing policy and multi-core node support.

---

## Change Log from Prior Assessment

The original assessment (2026-02-12, scored 7.5/10) identified several gaps. Here is what has been addressed:

| Prior Gap | Status | What Changed |
|-----------|--------|--------------|
| **Link Model bypassed** (5/10) | **Resolved** | `InterferenceModel` now modulates `link.bandwidth` via `_get_link_bandwidth()`. WiFi model overwrites `link.bandwidth` at setup with RF-derived PHY rates. |
| **No interference/spectrum model** (not scored) | **Resolved** | Four interference models: `NoInterference`, `ProximityInterference`, `CsmaCliqueInterference`, `CsmaBianchiInterference`. Full 802.11 PHY layer in `wifi.py`. |
| **Bandwidth sharing hardcoded** (2/10) | **Partially improved** | Interference factor is now multiplicative (`bw * factor / N`), decoupling inter-link effects from per-link fair-share. But fair-share policy itself remains hardcoded. |
| **Routing limited** (9/10) | **Improved** | Added `ShortestPathRouting` (min-latency Dijkstra) alongside `WidestPathRouting`. |
| **Disruptions not wired** (4/10) | **Unchanged** | `DisruptionModel` ABC and event types still defined but not connected. |

Score improvement: 7.5 -> 8.5 (interference model is a major extensibility win).

---

## Architecture Overview

```
scenario.yaml ──> ScenarioLoader ──> Scheduler (HEFT/CPOP/RR)
                       │                      │
                       ▼                      ▼
                  ┌──────────────────────────────────┐
                  │        Execution Engine           │
                  │                                   │
                  │  EventQueue   NodeState[]          │
                  │  RoutingModel  LinkState[]         │
                  │  InterferenceModel (optional)      │
                  │                                   │
                  │  B_eff = link.bw × factor / N     │
                  └──────────┬───────────────────────┘
                             │
                   ┌─────────┼─────────┐
                   ▼         ▼         ▼
             trace.jsonl  metrics.json  stdout
```

---

## Well-Abstracted Components (Easy to Swap)

### Scheduling --- 10/10

- **Interface:** `Scheduler` ABC in `scheduler/base.py`
- **Core method:** `on_dag_inject(dag, network_snapshot) -> PlacementPlan`
- **Future hooks already defined:** `on_task_complete()`, `on_network_change()`
- **Implementations:** `RoundRobinScheduler`, `SagaScheduler` (wraps HEFT/CPOP)
- **Config-driven:** YAML (`config.scheduler`) + CLI (`--scheduler`)
- **Adding a new scheduler:** Subclass `Scheduler`, add to factory in `saga_adapter.py`, set in YAML

### Routing --- 9.5/10

- **Interface:** `RoutingModel` ABC in `models/routing.py`
- **Core method:** `get_path(src, dst, network, network_state) -> Optional[List[str]]`
- **Implementations:** `DirectLinkRouting` (single-hop), `WidestPathRouting` (max-min bandwidth Dijkstra), `ShortestPathRouting` (min-latency Dijkstra)
- **Config-driven:** YAML (`config.routing`) + CLI (`--routing`)
- **Coupling:** Minimal --- injected into engine, used only in `_schedule_transfer_start()`
- **Minor gap:** No YAML extensibility for algorithm-specific parameters (e.g., k for k-shortest-paths)

### Interference Modeling --- 9/10 (NEW)

- **Interface:** `InterferenceModel` ABC in `models/interference.py`
- **Core methods:**
  - `get_interference_factor(link_id, active_links, network) -> float` (multiplier in (0, 1])
  - `get_affected_links(changed_link, active_links, network) -> Set[str]` (trigger recalculation)
- **Implementations:**
  - `NoInterference` --- factor = 1.0 always
  - `ProximityInterference(radius)` --- 1/k for k nearby active links
  - `CsmaCliqueInterference` --- static: bandwidth = PHY_rate / max_clique_size
  - `CsmaBianchiInterference` --- dynamic: SINR + Bianchi MAC efficiency
- **Config-driven:** YAML (`config.interference`) + CLI (`--interference`)
- **Engine integration:** `_get_link_bandwidth()` multiplies `link.bandwidth * factor`. Zero engine code changes were needed to add the WiFi model.
- **Adding a new model:** Subclass `InterferenceModel`, add to `create_interference_model()` factory

### 802.11 WiFi PHY Layer --- 9/10 (NEW)

Fully contained in `models/wifi.py` (~560 LOC). Pure physics computations with no simulation state dependency.

| Component | Function | Description |
|-----------|----------|-------------|
| Path loss | `path_loss_dB()` | Log-distance model with Friis reference at d0=1m |
| Received power | `received_power_dBm()` | P_tx - PL(d) - shadow_fading |
| SNR/SINR | `snr_dB()`, `sinr_dB()` | Linear-domain interference aggregation |
| MCS adaptation | `snr_to_rate_mbps()` | Tables for 802.11n/ac/ax (1SS, 20MHz base) |
| MAC efficiency | `bianchi_efficiency(n)` | Bianchi (2000) saturation throughput, lazy LUT |
| Conflict graph | `build_conflict_graph()` | Protocol model with/without RTS/CTS |
| Max clique | `_compute_max_clique_sizes()` | Bron-Kerbosch (exact) or greedy approximation |
| Shadow fading | `generate_shadow_fading_map()` | Symmetric, seeded, per-node-pair Gaussian |
| PHY rates | `compute_link_phy_rates()` | Distance -> SNR -> MCS -> MB/s per link |

**Key design property:** The WiFi module only runs at setup time (before simulation starts). It overwrites `link.bandwidth` with RF-derived rates and constructs the `InterferenceModel`. The execution engine is unaware of WiFi specifics.

**RF configuration:** `RFConfig` frozen dataclass with 9 parameters (tx_power, freq, path_loss_exponent, noise_floor, cca_threshold, channel_width, wifi_standard, shadow_fading_sigma, rts_cts). Configurable via YAML `config.rf:` section and CLI flags.

### Task Queueing --- 10/10 interface, 7/10 config

- **Interface:** `QueueModel` ABC in `models/task.py`
- **Methods:** `enqueue()`, `dequeue()`, `peek()`, `is_empty()`, `can_start_task()`
- **Implementation:** `FIFOQueueModel` (single-task, no preemption)
- **Engine uses abstract interface** --- ready for priority queues, multi-slot execution, preemption
- **Gap:** Queue model is hardcoded in `execution_engine.py`, not configurable via YAML

### Telemetry --- 8/10

- **Interface:** `TelemetryCollector` ABC in `core/telemetry.py`
- **Hook:** `on_event(event, engine)` --- called after each event via listener pattern
- **Implementations:** `TraceOnlyCollector` (lightweight), `FullStateCollector` (detailed snapshots)
- **Gap:** Hardcoded to `TraceOnlyCollector` in `simulation.py`, no YAML config

### DAG Injection --- 9/10

- **Interface:** `DAGSource` ABC
- **Implementations:** `SingleDAGSource` (one DAG at t=0), `MultiDAGSource` (scheduled times)
- **Extensible to:** Poisson arrivals, bursty workloads via subclass

### Event System --- 9/10

- **Extensible `EventType` enum** in `event_queue.py` with priority values
- **Dispatch pattern** in `execution_engine.py` --- handler dict maps type to method
- **Placeholder event types already defined:** `MOBILITY_UPDATE`, `LINK_STATE_CHANGE`, `RESCHEDULE_TRIGGER`
- **Adding new event type:** Add to enum, add handler to dict, implement handler

---

## Remaining Gaps

### Bandwidth Sharing Policy --- 3/10

Still the biggest modularity gap, though improved from 2/10.

Fair-share policy (`bw / N`) is baked into the execution engine (~140 LOC across `_handle_transfer_start()` and `_recalculate_link_transfers()`). The interference model now provides an inter-link multiplier, so the effective formula is:

```
effective_per_flow = (link.bandwidth * interference_factor) / N
```

This cleanly separates inter-link effects (interference) from intra-link effects (flow sharing). But the intra-link policy itself (equal fair share) cannot be swapped without editing engine code.

**Missing abstraction:**
```python
class BandwidthSharingModel(ABC):
    @abstractmethod
    def allocate_bandwidth(self, link: Link, transfers: List[ActiveTransfer],
                           link_state: LinkState) -> Dict[ActiveTransfer, float]:
        """Return per-transfer bandwidth allocations."""
        pass
```

This would enable: TDMA, priority queues, weighted fair queueing, proportional fairness.

### Disruptions / Mobility --- 4/10

Defined but not wired up:
- `DisruptionModel` ABC exists in `models/disruptions.py`
- `DisruptionEvent` dataclass exists with time, target, type, duration, parameters
- Event types are defined: `MOBILITY_UPDATE`, `LINK_STATE_CHANGE`
- **But:** Simulation doesn't accept `DisruptionModel`, engine has no handlers

To integrate requires ~30-50 LOC across 2 files.

### Multi-Core Nodes --- 2/10

- `NodeState.current_task` is a single slot
- No way to model parallel execution without restructuring
- `QueueModel.can_start_task()` exists as a future hook but isn't enough alone

---

## How the WiFi Model Validates the Architecture

The 802.11 WiFi model (added 2026-02-13, ~900 LOC across `wifi.py` + `interference.py`) serves as a strong validation of the architecture's modularity:

1. **Zero execution engine changes.** The engine's `_get_link_bandwidth()` already supported `link.bandwidth * factor`. The WiFi model slots in by:
   - Overwriting `link.bandwidth` with PHY rates at setup time
   - Providing an `InterferenceModel` that computes the dynamic factor

2. **Clean separation of concerns.**
   - `wifi.py` handles pure RF physics (no simulation state)
   - `interference.py` handles dynamic state (which links are active)
   - `main.py` handles wiring (build RFConfig, create model, overwrite bandwidths)

3. **Two variants, same interface.** `CsmaCliqueInterference` (static, factor=1.0) and `CsmaBianchiInterference` (dynamic, SINR+Bianchi) both implement `InterferenceModel` identically. Switching between them is a single YAML field.

4. **Backward compatible.** Existing scenarios without `rf:` config work unchanged. Links with explicit bandwidth are preserved.

This is exactly the kind of extensibility a good architecture should enable: a research-grade wireless model added without touching the simulation core.

---

## Coupling Analysis

### Execution Engine Dependencies

```python
from ncsim.models.network import Network, Link          # abstractions
from ncsim.models.dag import DAG, Edge                   # data models
from ncsim.models.task import Task, TaskState, FIFOQueueModel  # concrete!
from ncsim.models.routing import DirectLinkRouting, RoutingModel  # both
from ncsim.models.interference import InterferenceModel  # abstraction
from ncsim.scheduler.base import Scheduler, PlacementPlan  # abstractions
```

**Good:** Depends on abstractions (`RoutingModel`, `Scheduler`, `InterferenceModel`) for major components.
**Good:** `InterferenceModel` is Optional --- engine works without it.
**Bad:** Imports concrete `FIFOQueueModel` instead of abstract `QueueModel`.
**Acceptable:** Directly accesses `link.bandwidth` but via `_get_link_bandwidth()` which applies interference. The WiFi model overwrites `link.bandwidth` at setup, which works within this pattern.

### Simulation Dependencies

```python
from ncsim.core.execution_engine import ExecutionEngine
from ncsim.models.routing import RoutingModel
from ncsim.models.interference import InterferenceModel
from ncsim.scheduler.base import Scheduler
```

Excellent --- all abstract types, interference model properly injected via DI.

---

## Hardcoded Assumptions

1. **Bandwidth sharing policy** (`execution_engine.py`): Fair-share `bw * factor / N` --- interference is modular, sharing is not
2. **Single-task-per-node** (`execution_engine.py`): Cannot model multi-core or GPU
3. **Store-and-forward transfers** (`execution_engine.py`): `time = data/bw + latency`, no pipelining
4. **No packet-level simulation**: Transfers are atomic, no buffer modeling (acceptable for DES abstraction level)

---

## Refactoring Roadmap

### Priority 1: High Impact, Low Effort

**1a. Integrate DisruptionModel** (~30-50 LOC)
- Accept `DisruptionModel` in `Simulation.__init__()`
- Schedule disruption events in simulation loop
- Add handlers in `ExecutionEngine.handle_event()`
- Trigger `scheduler.on_network_change()`

**1b. Add YAML config for telemetry** (~10 LOC)
- `config.telemetry: "trace_only" | "full_state"`
- Factory in main.py

**1c. Add YAML config for queue_model** (~15 LOC)
- Per-node configuration: `queue_model: fifo | priority | multi_slot`
- Factory in scenario loader

### Priority 2: High Impact, Medium Effort

**2a. Extract BandwidthSharingModel** (~80-100 LOC refactor)
- Define `BandwidthSharingModel` ABC
- Extract fair-share logic into `FairShareBandwidth` class
- Inject via DI, add YAML config
- Enables: TDMA, priority queues, weighted fair queueing

### Priority 3: Future Extensibility

**3a. NodeExecutionModel abstraction** --- for multi-core, heterogeneous (CPU+GPU)
**3b. TransferModel abstraction** --- for pipelining, circuit-switching
**3c. Plugin system** --- dynamic loading of custom models via YAML `plugins:` section

---

## Summary Table

| Component | Interface | Wired Up? | Config? | Swap Effort | Score |
|-----------|-----------|-----------|---------|-------------|-------|
| Scheduling | `Scheduler` ABC | Yes | YAML+CLI | Subclass + factory | 10/10 |
| Routing | `RoutingModel` ABC | Yes | YAML+CLI | Subclass + factory | 9.5/10 |
| **Interference** | **`InterferenceModel` ABC** | **Yes** | **YAML+CLI** | **Subclass + factory** | **9/10** |
| **WiFi PHY** | **`wifi.py` module** | **Yes (setup)** | **YAML+CLI** | **Extend tables/models** | **9/10** |
| Task Queueing | `QueueModel` ABC | Yes | No | Subclass only | 8/10 |
| Telemetry | `TelemetryCollector` ABC | Yes | No | Subclass only | 8/10 |
| DAG Injection | `DAGSource` ABC | Yes | Partial | Subclass only | 9/10 |
| Event System | `EventType` enum | Yes | N/A | Add to enum + handler | 9/10 |
| Disruptions | `DisruptionModel` ABC | **No (disconnected)** | No | ~30-50 LOC integration | 4/10 |
| Bandwidth Sharing | **None** | N/A | No | ~100 LOC new abstraction | 3/10 |
| Multi-Core Nodes | **None** | N/A | No | Structural refactor | 2/10 |

---

## Test Coverage

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_event_queue.py` | 29 | Event ordering, cancellation, priority, time rounding |
| `test_models.py` | 25 | Node, Link, Network, Task, DAG dataclass creation |
| `test_routing.py` | 23 | DirectLink, WidestPath, ShortestPath routing |
| `test_saga_adapter.py` | 10 | SAGA HEFT/CPOP integration, model conversion |
| `test_scenario_loader.py` | 9 | YAML parsing, config defaults, validation |
| `test_execution_engine.py` | 12 | Event handlers, bandwidth sharing, node queuing |
| `test_acceptance.py` | 9 | End-to-end: determinism, dependencies, contention |
| **`test_wifi.py`** | **43** | **Path loss, SNR/SINR, MCS, Bianchi, conflict graph, shadow fading** |
| **Total** | **178** | |

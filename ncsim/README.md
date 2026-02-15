# ncsim

**Headless Discrete Event Simulator for Networked Computing Research**

ncsim is a fast, deterministic simulator for evaluating task scheduling algorithms on networked computing systems. It models compute nodes, network links, DAG task graphs, and produces detailed traces for analysis.

## Features

- **Deterministic simulation**: Same inputs + same seed = identical results
- **HEFT/CPOP scheduling**: Integrated with [anrg-saga](https://github.com/ANRGUSC/saga) schedulers
- **Multi-hop routing**: Direct, widest-path (max-min bandwidth), and shortest-path (min-latency) Dijkstra routing
- **802.11 WiFi PHY/MAC modeling**: Log-distance path loss, SNR-based MCS rate adaptation (802.11n/ac/ax), shadow fading
- **Interference models**: Proximity, CSMA/CA clique-based (static), and CSMA/CA Bianchi (dynamic SINR + MAC efficiency)
- **Bandwidth sharing**: Fair share model when multiple transfers share a link
- **Single-server queues**: FIFO task queuing at each node
- **Trace output**: JSONL event traces for analysis and visualization
- **Metrics**: Makespan, node utilization, link utilization
- **178 unit/integration tests** with full coverage of WiFi physics, routing, and scheduling

## Installation

```bash
cd ncsim
pip install -e .

# For development (includes pytest)
pip install -e ".[dev]"
```

### Dependencies

- Python 3.10+
- anrg-saga >= 2.0.0
- networkx >= 3.0
- pyyaml >= 6.0

## Usage

### Basic Simulation

```bash
python -m ncsim --scenario scenarios/demo_simple.yaml --output results/
```

### CLI Options

```
ncsim --scenario PATH --output DIR [options]

Options:
  --scenario PATH       Scenario YAML file (required)
  --output DIR          Output directory for results (required)
  --seed N              Random seed (default: from scenario or 42)
  --scheduler ALGO      heft | cpop | round_robin (default: from scenario)
  --routing ROUTING     direct | widest_path | shortest_path (default: from scenario or direct)
  --interference MODEL  none | proximity | csma_clique | csma_bianchi (default: from scenario or none)
  --verbose             Enable verbose logging

WiFi / RF Options (used with csma_clique or csma_bianchi interference):
  --tx-power DBM        Transmit power in dBm (default: 20)
  --freq GHZ            Carrier frequency in GHz (default: 5.0)
  --path-loss-exp N     Path loss exponent (default: 3.0)
  --wifi-standard STD   n | ac | ax (default: ax)
  --rts-cts             Enable RTS/CTS (extends conflict zone to protect receivers)
```

### Output Files

| File | Description |
|------|-------------|
| `trace.jsonl` | Event trace (JSON Lines format) |
| `metrics.json` | Summary metrics (makespan, utilization) |

## Scenario Format

Scenarios are defined in YAML:

```yaml
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

### WiFi Scenario (RF-derived bandwidth)

When using WiFi interference models, link bandwidth is derived from RF physics rather than specified manually. Omit `bandwidth` from links and add an `rf` config section:

```yaml
scenario:
  name: "WiFi Test"

  network:
    nodes:
      - {id: n0, compute_capacity: 100, position: {x: 0, y: 0}}
      - {id: n1, compute_capacity: 100, position: {x: 30, y: 0}}
      - {id: n2, compute_capacity: 100, position: {x: 0, y: 30}}
      - {id: n3, compute_capacity: 100, position: {x: 30, y: 30}}
    links:
      - {id: l01, from: n0, to: n1, latency: 0.0}   # bandwidth derived from distance
      - {id: l23, from: n2, to: n3, latency: 0.0}

  dags:
    - id: dag_1
      inject_at: 0.0
      tasks:
        - {id: T0, compute_cost: 1, pinned_to: n0}
        - {id: T1, compute_cost: 1, pinned_to: n1}
        - {id: T2, compute_cost: 1, pinned_to: n2}
        - {id: T3, compute_cost: 1, pinned_to: n3}
      edges:
        - {from: T0, to: T1, data_size: 100}
        - {from: T2, to: T3, data_size: 100}

  config:
    scheduler: round_robin
    interference: csma_bianchi
    rf:
      tx_power_dBm: 20
      freq_ghz: 5.0
      path_loss_exponent: 3.0
      noise_floor_dBm: -95
      cca_threshold_dBm: -82
      channel_width_mhz: 20
      wifi_standard: "ax"
      shadow_fading_sigma: 0.0
      rts_cts: false
    seed: 42
```

The WiFi model computes link rates via: distance → path loss → SNR → MCS table → PHY rate (MB/s). At runtime, interference between co-channel links reduces effective throughput based on SINR and MAC contention.

### Scenario Fields

**Network:**
- `nodes[].compute_capacity`: Compute units per second
- `nodes[].position`: x, y coordinates in meters (used for RF calculations)
- `links[].bandwidth`: MB/second (optional when using WiFi models — derived from RF if omitted)
- `links[].latency`: Seconds (added to each transfer)

**Tasks:**
- `tasks[].compute_cost`: Total compute units required
- `tasks[].pinned_to`: Optional node ID to force assignment
- `edges[].data_size`: MB to transfer between tasks

**Config:**
- `scheduler`: `heft` | `cpop` | `round_robin`
- `routing`: `direct` | `widest_path` | `shortest_path`
- `interference`: `none` | `proximity` | `csma_clique` | `csma_bianchi`
- `rf`: RF configuration (see WiFi scenario above)
- `seed`: Random seed for deterministic simulation

**Timing:**
- `task_runtime = compute_cost / node.compute_capacity`
- `transfer_time = (data_size / effective_bandwidth) + latency`
- `effective_bandwidth = link.bandwidth * interference_factor / concurrent_flows`

## Example Scenarios

### demo_simple.yaml

Two nodes, two tasks with a dependency:
- T0 runs on n0, T1 depends on T0's output
- Tests basic scheduling and transfer

### bandwidth_contention.yaml

Tests fair bandwidth sharing:
- Multiple concurrent transfers on the same link
- Each transfer gets `bandwidth / num_concurrent_transfers`

### multi_hop_forced.yaml / multi_hop_test.yaml

Three nodes in a line (n0─n1─n2) with no direct n0─n2 link:
- `multi_hop_forced`: Tasks pinned to n0 and n2, forces multi-hop transfer
- `multi_hop_test`: Tasks unpinned, scheduler decides placement

### multihop_advantage.yaml

Heterogeneous nodes: n_src(10 cu/s) → n_relay(10) → n_fast(1000).
Demonstrates that multi-hop routing enables reaching a 100x faster node:
- Without multi-hop: both tasks on slow node → 200s
- With widest-path: T1 reaches n_fast → 101.12s (49% faster)

### parallel_spread.yaml

Five nodes in a bidirectional line, 8 parallel tasks in fan-out/fan-in DAG.
Key scenario for HEFT + multi-hop advantage:
- HEFT + direct routing: uses 3 adjacent nodes → 35.3s
- HEFT + widest-path: spreads across all 5 nodes → 24.2s (31% faster)

### wifi_test.yaml

Two parallel links (n0→n1, n2→n3) at 30m spacing with `csma_bianchi` interference.
Bandwidth derived from 802.11ax PHY rates via log-distance path loss and SNR→MCS lookup.
Demonstrates dynamic SINR degradation and Bianchi MAC contention between co-channel links.

### wifi_clique_test.yaml

Same topology as wifi_test but with `csma_clique` interference (static, simpler).
Link bandwidth pre-divided by max clique size at setup. Useful for comparing static vs. dynamic interference modeling.

## Interference Models

| Model | Type | Description |
|-------|------|-------------|
| `none` | — | No interference (default) |
| `proximity` | Static | 1/k factor for k active links within a configurable radius |
| `csma_clique` | Static | PHY rate / max_clique_size; conflict graph from carrier sensing range |
| `csma_bianchi` | Dynamic | SINR-based MCS re-selection + Bianchi MAC efficiency η(n) |

The **csma_clique** and **csma_bianchi** models use the 802.11 WiFi PHY layer to compute:
1. **Link rates** from distance via log-distance path loss → SNR → MCS table (802.11n/ac/ax)
2. **Conflict graph** from carrier sensing range (protocol model, with optional RTS/CTS)
3. **Contention reduction** — static (clique) or dynamic (SINR + Bianchi saturation throughput)

For full mathematical details, see [`docs/wifi_interference_model.pdf`](docs/wifi_interference_model.pdf).

## Trace Format

The trace file contains one JSON object per line:

```jsonl
{"seq": 0, "sim_time": 0.0, "type": "sim_start", "trace_version": "1.0", "seed": 42, "scenario": "demo_simple.yaml"}
{"seq": 1, "sim_time": 0.0, "type": "dag_inject", "dag_id": "dag_1", "task_ids": ["T0", "T1"]}
{"seq": 2, "sim_time": 0.0, "type": "task_scheduled", "dag_id": "dag_1", "task_id": "T0", "node_id": "n0"}
{"seq": 3, "sim_time": 0.0, "type": "task_start", "dag_id": "dag_1", "task_id": "T0", "node_id": "n0"}
{"seq": 4, "sim_time": 1.0, "type": "task_complete", "dag_id": "dag_1", "task_id": "T0", "node_id": "n0", "duration": 1.0}
...
{"seq": 10, "sim_time": 5.0, "type": "sim_end", "status": "completed", "makespan": 5.0}
```

See the project specification for the complete trace format.

## Running Tests

### Unit & Integration Tests

```bash
cd ncsim
python -m pytest tests/ -v

# With coverage
python -m pytest tests/ --cov=ncsim --cov-report=term-missing
```

### Routing Comparison (Full Test Suite)

Runs all unit tests, then executes every scenario with `direct`, `widest_path`,
and `shortest_path` routing, prints a makespan comparison table, and generates
ASCII Gantt charts:

```bash
cd ncsim
bash run_routing_comparison.sh            # output to /tmp/ncsim_routing_comparison/
bash run_routing_comparison.sh ./results  # or specify output directory
```

Expected output summary:

```
Scenario                           Direct WidestPath ShortestPath    WP vs D    SP vs D
--------                           ------ ---------- ------------    -------    -------
A: demo_simple                     3.000s     3.000s       3.000s       same       same
B: bandwidth_contention            2.010s     2.010s       2.010s       same       same
C: multi_hop_forced                2.000s     2.520s       2.520s     -26.0%     -26.0%
D: multi_hop_test                  2.000s     2.000s       2.000s       same       same
E: multihop_advantage            101.000s   101.120s     101.120s      -0.1%      -0.1%
F: parallel_spread                35.343s    24.232s      24.232s      31.4%      31.4%
```

- **A, B, D**: Direct links exist, all three modes produce identical results
- **C**: Direct routing silently skips the transfer (incorrect); widest-path and shortest-path are slower but correct
- **E**: Pinned tasks on heterogeneous nodes; direct skips the multi-hop transfer
- **F**: HEFT + multi-hop routing spreads 8 parallel tasks across 5 nodes instead of 3, yielding a 31% speedup
- **WP vs SP**: Widest-path maximizes bottleneck bandwidth; shortest-path minimizes total latency. They diverge on networks with bandwidth/latency tradeoffs

### Trace Analysis

Inspect any trace with the built-in analyzer:

```bash
python analyze_trace.py results/trace.jsonl --gantt --timeline --tasks
```

## Architecture

For a detailed interactive overview, see [architecture.html](https://htmlpreview.github.io/?https://github.com/ANRGUSC/ncsim-mg/blob/main/ncsim/architecture.html).

```
ncsim/
├── ncsim/
│   ├── main.py              # CLI entry point
│   ├── core/
│   │   ├── simulation.py    # Main simulation loop
│   │   ├── event_queue.py   # Priority queue with deterministic ordering
│   │   ├── execution_engine.py  # Task/transfer execution logic
│   │   └── telemetry.py     # Event telemetry collection
│   ├── models/
│   │   ├── network.py       # Node, Link, Network
│   │   ├── task.py          # Task, QueueModel
│   │   ├── dag.py           # DAG, Edge
│   │   ├── routing.py       # Direct, WidestPath, ShortestPath routing
│   │   ├── interference.py  # Interference models (Proximity, CSMA Clique, CSMA Bianchi)
│   │   └── wifi.py          # 802.11 WiFi PHY/MAC (path loss, MCS, Bianchi, conflict graph)
│   ├── scheduler/
│   │   ├── base.py          # Scheduler interface
│   │   └── saga_adapter.py  # SAGA HEFT/CPOP integration
│   └── io/
│       ├── scenario_loader.py   # YAML parsing (incl. RF config)
│       ├── trace_writer.py      # JSONL trace output
│       └── results_writer.py    # Metrics JSON output (incl. RF metrics)
├── scenarios/               # Example scenarios (incl. WiFi)
├── tests/                   # 178 unit/integration tests
├── docs/                    # LaTeX documentation
│   └── wifi_interference_model.tex/pdf  # WiFi model mathematical specification
├── analyze_trace.py         # Trace analysis tool (Gantt, timeline, stats)
└── run_routing_comparison.sh  # Full routing comparison test suite
```

See also: [MODULARITY_ASSESSMENT.md](MODULARITY_ASSESSMENT.md) for a detailed modularity analysis (8.5/10).

## License

See [LICENSE](../LICENSE) for license details.

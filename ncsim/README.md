# ncsim

**Headless Discrete Event Simulator for Networked Computing Research**

ncsim is a fast, deterministic simulator for evaluating task scheduling algorithms on networked computing systems. It models compute nodes, network links, DAG task graphs, and produces detailed traces for analysis.

## Features

- **Deterministic simulation**: Same inputs + same seed = identical results
- **HEFT/CPOP scheduling**: Integrated with [anrg-saga](https://github.com/ANRGUSC/saga) schedulers
- **Bandwidth sharing**: Fair share model when multiple transfers share a link
- **Single-server queues**: FIFO task queuing at each node
- **Trace output**: JSONL event traces for analysis and visualization
- **Metrics**: Makespan, node utilization, link utilization

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
ncsim --scenario PATH --output DIR [--seed N] [--scheduler ALGO] [--routing ROUTING] [--verbose]

Options:
  --scenario PATH       Scenario YAML file (required)
  --output DIR          Output directory for results (required)
  --seed N              Random seed (default: from scenario or 42)
  --scheduler ALGO      heft | cpop | round_robin (default: from scenario)
  --routing ROUTING     direct | widest_path (default: from scenario or direct)
  --verbose             Enable verbose logging
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

### Scenario Fields

**Network:**
- `nodes[].compute_capacity`: Compute units per second
- `links[].bandwidth`: MB/second
- `links[].latency`: Seconds (added to each transfer)

**Tasks:**
- `tasks[].compute_cost`: Total compute units required
- `edges[].data_size`: MB to transfer between tasks

**Timing:**
- `task_runtime = compute_cost / node.compute_capacity`
- `transfer_time = (data_size / bandwidth) + latency`

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

Runs all 121 unit tests, then executes every scenario with both `direct` and
`widest_path` routing, prints a summary table, and generates ASCII Gantt charts:

```bash
cd ncsim
bash run_routing_comparison.sh            # output to /tmp/ncsim_routing_comparison/
bash run_routing_comparison.sh ./results  # or specify output directory
```

Expected output summary:

```
Scenario                           Direct WidestPath    Speedup
--------                           ------ ----------    -------
A: demo_simple                     3.000s     3.000s       same
B: bandwidth_contention            2.010s     2.010s       same
C: multi_hop_forced                2.000s     2.520s     -26.0%
D: multi_hop_test                  2.000s     2.000s       same
E: multihop_advantage            101.000s   101.120s      -0.1%
F: parallel_spread                35.343s    24.232s      31.4%
```

- **A, B, D**: Direct links exist, both modes produce identical results
- **C**: Direct routing silently skips the transfer (incorrect); widest-path is slower but correct
- **E**: Pinned tasks on heterogeneous nodes; direct skips the multi-hop transfer
- **F**: HEFT + widest-path spreads 8 parallel tasks across 5 nodes instead of 3, yielding a 31% speedup

### Trace Analysis

Inspect any trace with the built-in analyzer:

```bash
python analyze_trace.py results/trace.jsonl --gantt --timeline --tasks
```

## Architecture

```
ncsim/
├── ncsim/
│   ├── main.py              # CLI entry point
│   ├── core/
│   │   ├── simulation.py    # Main simulation loop
│   │   ├── event_queue.py   # Priority queue with deterministic ordering
│   │   └── execution_engine.py  # Task/transfer execution logic
│   ├── models/
│   │   ├── network.py       # Node, Link, Network
│   │   ├── task.py          # Task
│   │   ├── dag.py           # DAG, Edge
│   │   └── routing.py       # DirectLinkRouting, WidestPathRouting
│   ├── scheduler/
│   │   ├── base.py          # Scheduler interface
│   │   └── saga_adapter.py  # SAGA HEFT/CPOP integration
│   └── io/
│       ├── scenario_loader.py   # YAML parsing
│       ├── trace_writer.py      # JSONL trace output
│       └── results_writer.py    # Metrics JSON output
├── scenarios/               # Example scenarios
├── tests/                   # Test suite
├── analyze_trace.py         # Trace analysis tool (Gantt, timeline, stats)
└── run_routing_comparison.sh  # Full routing comparison test suite
```

## License

See [LICENSE](../LICENSE) for license details.

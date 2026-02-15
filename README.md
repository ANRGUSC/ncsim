# ncsim

**Networked Compute Simulator** — a headless discrete-event simulator for evaluating task scheduling algorithms on heterogeneous networked systems.

ncsim models compute nodes, network links with WiFi interference, and DAG task graphs. It produces detailed JSONL traces and JSON metrics for analysis. An interactive web UI ([viz/](viz/)) provides topology visualization, Gantt charts, animated replay, and a "Configure & Run" interface.

## Features

- **Deterministic simulation**: Same inputs + same seed = identical results
- **HEFT/CPOP scheduling**: Integrated with [anrg-saga](https://github.com/ANRGUSC/saga) schedulers
- **Multi-hop routing**: Direct, widest-path (max-min bandwidth), and shortest-path (min-latency)
- **802.11 WiFi PHY/MAC**: Log-distance path loss, SNR-based MCS rate adaptation (802.11n/ac/ax)
- **Interference models**: Proximity, CSMA/CA clique-based, and CSMA/CA Bianchi (dynamic SINR)
- **Fair bandwidth sharing** when multiple transfers share a link
- **Web visualization** with topology, DAG, Gantt, and animated replay ([viz/](viz/))

## Quick Start

### Install ncsim

```bash
pip install -e .

# For development (includes pytest)
pip install -e ".[dev]"
```

Requires Python 3.10+ and [anrg-saga](https://github.com/ANRGUSC/saga) >= 2.0.0.

### Run a simulation

```bash
python -m ncsim --scenario scenarios/demo_simple.yaml --output results/
```

Output: three files needed as inputs to the [viz/](viz/) web UI:
- `results/trace.jsonl` — event trace
- `results/metrics.json` — summary metrics
- `results/scenario.yaml` — copy of the input scenario

### CLI options

```
ncsim --scenario PATH --output DIR [options]

Options:
  --seed N              Random seed (default: from scenario or 42)
  --scheduler ALGO      heft | cpop | round_robin
  --routing ROUTING     direct | widest_path | shortest_path
  --interference MODEL  none | proximity | csma_clique | csma_bianchi
  --verbose             Enable verbose logging

WiFi / RF options (for csma_clique or csma_bianchi):
  --tx-power DBM        Transmit power in dBm (default: 20)
  --freq GHZ            Carrier frequency in GHz (default: 5.0)
  --path-loss-exp N     Path loss exponent (default: 3.0)
  --wifi-standard STD   n | ac | ax (default: ax)
  --rts-cts             Enable RTS/CTS
```

### Launch the web UI

```bash
# Terminal 1: Backend API server
cd viz/server && pip install -r requirements.txt && python run.py

# Terminal 2: Frontend dev server
cd viz && npm install && npm run dev
```

Open **http://localhost:5173** to configure experiments, run simulations, and visualize results interactively. See [viz/README.md](viz/README.md) for full documentation.

## Scenario Format

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

See [scenarios/](scenarios/) for more examples including WiFi interference, multi-hop routing, and parallel spread topologies.

## Trace Analysis

```bash
python analyze_trace.py results/trace.jsonl --gantt --timeline --tasks
```

## Running Tests

```bash
python -m pytest tests/ -v
```

178 tests covering event queue, execution engine, scheduling, routing, WiFi physics, and acceptance criteria.

## Architecture

For a detailed interactive overview, see [docs/architecture.html](https://htmlpreview.github.io/?https://github.com/ANRGUSC/ncsim/blob/main/docs/architecture.html).

```
ncsim/                  # Python package
├── main.py             # CLI entry point
├── core/
│   ├── simulation.py   # Main simulation loop
│   ├── event_queue.py  # Priority queue with deterministic ordering
│   └── execution_engine.py
├── models/
│   ├── network.py      # Node, Link, Network
│   ├── dag.py          # DAG, Edge, Task
│   ├── routing.py      # Direct, WidestPath, ShortestPath
│   ├── interference.py # Proximity, CSMA Clique, CSMA Bianchi
│   └── wifi.py         # 802.11 PHY/MAC
├── scheduler/
│   ├── base.py         # Scheduler interface
│   └── saga_adapter.py # SAGA HEFT/CPOP integration
└── io/
    ├── scenario_loader.py
    ├── trace_writer.py
    └── results_writer.py

viz/                    # Web visualization (React + FastAPI)
├── src/                # React frontend
├── server/             # FastAPI backend
└── public/             # Sample experiment runs

scenarios/              # Example scenario YAML files
tests/                  # Unit and integration tests
docs/                   # Architecture diagrams
```

## License

[PolyForm Noncommercial 1.0.0](LICENSE)

## Contributors

- **Bhaskar Krishnamachari** — [Autonomous Networks Research Group (ANRG)](https://anrg.usc.edu/), University of Southern California
- **Maya Gutierrez** — [Autonomous Networks Research Group (ANRG)](https://anrg.usc.edu/), University of Southern California

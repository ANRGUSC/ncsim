# ncsim

[![PyPI](https://img.shields.io/pypi/v/anrg-ncsim)](https://pypi.org/project/anrg-ncsim/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19138224.svg)](https://doi.org/10.5281/zenodo.19138224)
[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/ANRGUSC/ncsim?quickstart=1)

[Why ncsim?](https://anrgusc.github.io/ncsim/intro.html) · [Documentation](https://anrgusc.github.io/ncsim/) · [Codespaces](https://codespaces.new/ANRGUSC/ncsim?quickstart=1) · [Paper](https://arxiv.org/abs/2605.01094) · [Software DOI](https://doi.org/10.5281/zenodo.19138224)

> **Codespaces:** The web UI should open automatically. If it does not, type `start-viz` in the terminal, then open port **5173** from the **Ports** tab. Port 8000 is the internal API and is not the UI.

**ncsim** is a lightweight simulator for DAG scheduling over heterogeneous networked systems with multi-hop routing and realistic Wi-Fi interference modeling.

ncsim models compute nodes, network links with WiFi interference, and DAG task graphs. It produces detailed JSONL traces and JSON metrics for analysis.

## Features

Current manuscript sources and curated results are on the `paper` branch in
[`artifacts/arxiv-2605.01094/`](https://github.com/ANRGUSC/ncsim/tree/paper/artifacts/arxiv-2605.01094).
The earlier manuscript tree is archived separately as
[`arxiv-old/`](https://github.com/ANRGUSC/ncsim/tree/paper/arxiv-old).
See [wireless modes and fixed capture](docs/concepts/wireless-modes.md) for
the optional model's scope and regression commands.

- **Deterministic simulation**: Same inputs + same seed = identical results
- **22+ SAGA static batch schedulers**: HEFT, CPOP, Min-Min, Sufferage, and more; PEFT is added automatically with SAGA 2.1.0, alongside built-in round-robin and manual assignment
- **Multi-hop routing**: Direct, widest-path (max-min bandwidth), and shortest-path (min-latency)
- **802.11 WiFi PHY/MAC**: Log-distance path loss, SNR-based MCS rate adaptation (802.11n/ac/ax)
- **Interference models**: Proximity, CSMA/CA clique-based, and CSMA/CA Bianchi (capture-aware)
- **Fair bandwidth sharing** when multiple transfers share a link
- **Experiment scripts** for interference verification and routing comparison
- **Documentation**: [installation guide](https://anrgusc.github.io/ncsim/getting-started/installation/), [quick start](https://anrgusc.github.io/ncsim/getting-started/quickstart/), [architecture overview](https://anrgusc.github.io/ncsim/concepts/architecture/), and [Wi-Fi interference model](docs/wifi_interference_model.pdf)

## Try in GitHub Codespaces

[Open ncsim in GitHub Codespaces](https://codespaces.new/ANRGUSC/ncsim?quickstart=1) for a ready-to-use environment with **both the web UI and CLI**. The UI starts automatically on port 5173, while the `ncsim` CLI is ready in the terminal. A demo simulation is also run during setup; inspect its raw `scenario.yaml`, `trace.jsonl`, and `metrics.json` files under `results/codespaces-demo/`.

Rerun the demo and analyze its trace from the terminal:

```bash
ncsim --scenario scenarios/demo_simple.yaml --output results/codespaces-demo
python analyze_trace.py results/codespaces-demo/trace.jsonl --gantt --timeline --tasks
```

If the UI does not open automatically, start or restart it with:

```bash
start-viz
```

Then select the **Ports** tab at the bottom of Codespaces, hover over port 5173, and select the globe (**Open in Browser**).

## Installation

**Recommended:** Clone the repository to get started. The repo includes example scenarios, experiment scripts, documentation, and the [web visualization UI](#web-visualization-ncsim-viz) — all useful for learning and exploring ncsim:

```bash
git clone https://github.com/ANRGUSC/ncsim.git
cd ncsim
pip install -e .

# For development (includes pytest)
pip install -e ".[dev]"
```

Alternatively, `pip install anrg-ncsim` installs just the core simulator and `ncsim` CLI. This is suitable if you want to use ncsim as a library in your own project and will write your own scenario YAML files. It does not include the example scenarios, experiment scripts, visualization UI, or documentation.

Requires Python 3.12+ and [anrg-saga](https://github.com/ANRGUSC/saga) >= 2.0.4. The PyPI release of SAGA provides 22 directly compatible schedulers. To add PEFT as the 23rd scheduler, install SAGA 2.1.0 from its tagged source:

```bash
python -m pip install "anrg-saga @ git+https://github.com/ANRGUSC/saga.git@v2.1.0"
```

## Quick Start

```bash
ncsim --scenario scenarios/demo_simple.yaml --output results/
```

Output:
- `results/trace.jsonl` — event trace
- `results/metrics.json` — summary metrics
- `results/scenario.yaml` — copy of the input scenario

### CLI Options

```
ncsim --scenario PATH --output DIR [options]

Options:
  --seed N              Random seed (default: from scenario or 42)
  --scheduler ALGO      SAGA scheduler, round_robin, or manual
  --scheduler-option K=V
                        Scheduler constructor option (repeatable)
  --routing ROUTING     direct | widest_path | shortest_path
  --interference MODEL  none | proximity | csma_clique | csma_bianchi
  --verbose             Enable verbose logging

WiFi / RF options (for csma_clique or csma_bianchi):
  --tx-power DBM        Transmit power in dBm (default: 20)
  --freq GHZ            Carrier frequency in GHz (default: 5.0)
  --path-loss-exponent N
                        Path loss exponent (default: 3.0)
  --wifi-standard STD   n | ac | ax (default: ax)
  --rts-cts             Enable RTS/CTS
```

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
    scheduler: wba
    scheduler_options:
      alpha: 0.75
    seed: 42
```

Tasks can include `pinned_to: node_id` for use with `--scheduler manual`.
Run `ncsim --help` for the scheduler list provided by the installed SAGA version. SAGA scheduler options
currently available are `fcp.priority_queue_size`, `gdl.dynamic_level`,
`smt.epsilon`, `smt.solver_name`, and `wba.alpha`; all have SAGA defaults.

See [scenarios/](scenarios/) for more examples including WiFi interference, multi-hop routing, and parallel spread topologies.

## Experiment Scripts

The paper-specific scenarios, recorded results, and reproduction instructions
for the IEEE MILCOM 2026 study are in
[`experiments/milcom26/`](experiments/milcom26/).

Two standalone scripts for running structured experiments:

```bash
# Validate WiFi interference model against analytical predictions
python run_interference_verification.py

# Compare widest_path vs shortest_path routing on grid topologies
python run_routing_comparison.py
python visualize_routing_comparison.py  # Generate plots from results
```

## Trace Analysis

```bash
python analyze_trace.py results/trace.jsonl --gantt --timeline --tasks
```

## Running Tests

```bash
python -m pytest tests/ -v
```

An extensive unit and integration suite covers the event queue, execution engine, scheduling, routing, Wi-Fi physics, visualization API, and acceptance criteria.

## Architecture

For a detailed overview, see [the architecture documentation](https://anrgusc.github.io/ncsim/concepts/architecture/).

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
│   └── saga_adapter.py # SAGA static batch scheduler registry and adapter
└── io/
    ├── scenario_loader.py
    ├── trace_writer.py
    └── results_writer.py

scenarios/              # Example scenario YAML files
tests/                  # Unit and integration test suite
docs/                   # MkDocs documentation source
```

---

## Web Visualization (ncsim-viz)

ncsim includes an optional web UI ([viz/](viz/)) for interactive experiment configuration and result visualization. The viz is not included in the PyPI package — clone the repository to use it.

### Setup

```bash
# Terminal 1: Backend API server
cd viz/server && pip install -r requirements.txt && python run.py

# Terminal 2: Frontend dev server
cd viz && npm install && npm run dev
```

Open **http://localhost:5173** to configure experiments, run simulations, and visualize results interactively. See [viz/README.md](viz/README.md) for full documentation.

### Configure & Run

Build a scenario interactively — choose a scheduler, routing strategy, interference model, topology preset (line, star, ring, mesh, grid), and DAG preset (chain, fork-join, diamond, parallel). Edit nodes, links, and tasks in editable tables, then run the experiment with one click.

<p align="center">
  <img src="docs/screenshots/readme-08-configure.png" alt="Configure & Run" width="720">
</p>

### Visualization Tabs

After running or loading an experiment, explore results across six tabs:

| Tab | Description |
|-----|-------------|
| **Overview** | Makespan, task/transfer counts, node and link utilization bars |
| **Network** | Interactive D3 topology with node capacity and bandwidth labels |
| **DAG** | Task dependency graph with tasks colored by assigned node |
| **Schedule** | Gantt chart showing task execution windows across all nodes |
| **Simulation** | Animated replay: synchronized network view + live Gantt + event log |
| **Parameters** | Full scenario config inspector |

<p align="center">
  <img src="docs/screenshots/readme-03-overview.png" alt="Overview" width="720"><br>
  <em>Overview — summary dashboard with node utilization</em>
</p>

<p align="center">
  <img src="docs/screenshots/readme-05-dag.png" alt="DAG" width="720"><br>
  <em>DAG — task dependency graph, colored by node assignment</em>
</p>

<p align="center">
  <img src="docs/screenshots/readme-06-schedule.png" alt="Schedule" width="720"><br>
  <em>Schedule — Gantt chart of task execution across nodes</em>
</p>

<p align="center">
  <img src="docs/screenshots/readme-07-simulation.png" alt="Simulation" width="720"><br>
  <em>Simulation — animated replay with live transfers, Gantt timeline, and event log</em>
</p>

The simulation replay supports keyboard shortcuts: Space (play/pause), arrow keys (step events), +/- (speed 0.25x-10x), and keys 1-6 to switch tabs.

```
viz/                    # Web visualization (React + FastAPI)
├── src/                # React frontend
├── server/             # FastAPI backend
└── public/             # Sample experiment runs
```

---

## Cite ncsim

If you use ncsim in your research, please cite the paper and the software release:

```bibtex
@article{krishnamachari2026ncsimpaper,
  author  = {Krishnamachari, Bhaskar and Gutierrez, Maya and Coleman, Jared},
  title   = {ncsim: A Lightweight Simulator for Networked Edge Computing with Wireless Interference Modeling},
  year    = {2026},
  url     = {https://arxiv.org/abs/2605.01094},
  note    = {arXiv:2605.01094}
}

@software{krishnamachari2026ncsimsoftware,
  author    = {Krishnamachari, Bhaskar and Gutierrez, Maya},
  title     = {ncsim: A Lightweight Simulator for Networked Edge Computing with Wireless Interference Modeling},
  version   = {1.1.0},
  year      = {2026},
  url       = {https://github.com/ANRGUSC/ncsim},
  doi       = {10.5281/zenodo.19138224}
}
```

## Acknowledgements

This work was supported in part by Army Research Laboratory under Cooperative Agreement W911NF-17-2-0196.

## License

[MIT](LICENSE)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, validation, and
pull request guidance. Release history is recorded in
[CHANGELOG.md](CHANGELOG.md).

## Contributors
**Bhaskar Krishnamachari, Maya Gutierrez** — [Autonomous Networks Research Group (ANRG)](https://anrg.usc.edu/), University of Southern California

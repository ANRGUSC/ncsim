# IoBT-NCSim

**Immersive Networked Compute Simulator**

An interactive simulation environment for visualizing and analyzing networked computing systems, featuring RTS-style visualization of compute nodes, network links, data flows, and DAG task execution with HEFT scheduling.

> **Note**: The visualization component (iobt-viz) is based on a modification of [OpenRA](https://github.com/OpenRA/OpenRA), an open-source game engine for classic RTS games.

## Overview

IoBT-NCSim provides two complementary approaches to networked computing simulation:

| Component | Purpose | Status |
|-----------|---------|--------|
| **iobt-viz** | Interactive RTS-style visualization with real-time HEFT scheduling | Functional |
| **saga-service** | TCP wrapper for HEFT/CPOP scheduling algorithms | Functional |
| **ncsim** | Headless discrete-event simulator for research experiments | Functional |

```
DEMO MODE:                              RESEARCH MODE:
┌──────────────┐                        ┌──────────────┐
│   iobt-viz   │ ◄─TCP─► saga-service   │    ncsim     │ → trace.jsonl
│ (real-time)  │         (HEFT/CPOP)    │  (headless)  │ → metrics.json
└──────────────┘                        └──────────────┘
```

## Components

### iobt-viz (Visualization)

Real-time visualization of networked computing with:
- Network topology overlay with distance-based link quality
- DAG task scheduling and execution visualization
- Task-to-task data transfer animations
- Interactive configuration GUI

See [iobt-viz/README.md](iobt-viz/README.md) for details.

### saga-service (Scheduler)

TCP service providing HEFT/CPOP scheduling:
- Network-aware task placement
- Heterogeneous node support
- Real-time scheduling responses

See [saga-service/README.md](saga-service/README.md) for details.

### ncsim (Headless Simulator)

Discrete-event simulator for research:
- Deterministic simulation with reproducible results
- HEFT/CPOP scheduling via SAGA integration
- Fair bandwidth sharing model
- JSONL trace output for analysis

See [ncsim/README.md](ncsim/README.md) for details.

## Quick Start

### Prerequisites

- Windows 10/11
- .NET 8.0 SDK (for iobt-viz)
- Python 3.10+ (for ncsim and saga-service)

### Installation

```bash
git clone https://github.com/ANRGUSC/iobt-ncsim.git
cd iobt-ncsim

# Install Python dependencies
pip install -r saga-service/requirements.txt
pip install -e ncsim/

# Build visualization (optional)
cd iobt-viz && .\make.cmd && cd ..
```

### Running the Visualization Demo

**Terminal 1** - Start the scheduler:
```
.\runsched
```

**Terminal 2** - Configure and run:
```
runconfig    # Set parameters
runiobt      # Launch visualization
```

**Hotkeys:** `N` (network overlay), `Escape` (menu)

### Running Headless Simulations

```bash
cd ncsim
python -m ncsim --scenario scenarios/demo_simple.yaml --output results/
```

Output:
- `results/trace.jsonl` - Event trace
- `results/metrics.json` - Performance metrics

## Project Structure

```
iobt-ncsim/
├── README.md              # This file
├── CLAUDE.md              # Detailed project specification
├── runsched.bat           # Start SAGA scheduler service
├── runconfig.bat          # Open configuration GUI
├── runiobt.bat            # Launch visualization
├── saga-service/          # SAGA scheduler TCP service
│   ├── README.md
│   ├── scheduler_service.py
│   └── requirements.txt
├── iobt-viz/              # RTS-style visualization
│   ├── README.md
│   ├── engine/            # OpenRA engine
│   └── mods/iobt/         # IoBT visualization mod
├── ncsim/                 # Headless simulator
│   ├── README.md
│   ├── ncsim/             # Python package
│   ├── scenarios/         # Example scenarios
│   └── tests/             # Test suite
└── reference/             # Read-only OpenRA reference
```

## Documentation

- [CLAUDE.md](CLAUDE.md) - Complete project specification
- [iobt-viz/README.md](iobt-viz/README.md) - Visualization guide
- [saga-service/README.md](saga-service/README.md) - Scheduler service
- [ncsim/README.md](ncsim/README.md) - Headless simulator
- [ncsim/DEVELOPMENT.md](ncsim/DEVELOPMENT.md) - Development notes

## Author

Developed by **Bhaskar Krishnamachari** (USC), 2025-2026

Autonomous Networks Research Group (ANRG)
University of Southern California

## License

MIT License - See LICENSE file for details.

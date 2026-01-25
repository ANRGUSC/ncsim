# IoBT-NCSim

**Immersive Networked Compute Simulator**

An interactive simulation environment for visualizing and analyzing networked computing systems, featuring RTS-style visualization of compute nodes, network links, data flows, and DAG task execution with HEFT scheduling.

> **Note**: This project is based on a modification of [OpenRA](https://github.com/OpenRA/OpenRA), an open-source game engine for classic RTS games. We leverage OpenRA's rendering, entity management, and Lua scripting capabilities to create an immersive visualization platform for networked computing research.

## Overview

IoBT-NCSim combines:

- **iobt-viz**: High-quality RTS-style visualization (derived from OpenRA) displaying compute nodes, network links, data flows, and DAG task execution
- **saga-service**: SAGA scheduler service providing HEFT/CPOP algorithms for network-aware task scheduling
- **ncsim** (planned): A standalone, headless-capable discrete-event simulation engine for networked computing

## Current Features

### Visualization (iobt-viz)
- Real-time network topology visualization with distance-based link quality
- DAG (Directed Acyclic Graph) task scheduling visualization
- Task-to-task data transfer visualization with highlighted links
- Compute node markers (blue/yellow for high/low CPU)
- Network-aware scheduling with connectivity checks
- Interactive configuration GUI for scenario setup
- Makespan tracking and display

### SAGA Scheduler Integration
- **HEFT** (Heterogeneous Earliest Finish Time) scheduling algorithm
- **CPOP** (Critical Path on Processor) scheduling algorithm
- Network-aware task placement based on actual connectivity
- Real-time link data rates based on node distance
- Automatic fallback to round-robin if scheduler unavailable

### Network Overlay
- Link color coding: green (high bandwidth) → yellow → red (low bandwidth)
- Active transfer highlighting (cyan)
- Status panel showing DAG structure, task states, and active transfers
- Configurable communication range and data rates

## Quick Start

### Prerequisites
- Windows 10/11
- .NET 8.0 SDK
- Python 3.11+

### Installation

1. **Clone the repository**
   ```
   git clone https://github.com/ANRGUSC/iobt-ncsim.git
   cd iobt-ncsim
   ```

2. **Install Python dependencies** (for SAGA scheduler)
   ```
   pip install -r saga-service/requirements.txt
   ```

3. **Build iobt-viz**
   ```powershell
   cd iobt-viz
   .\make.cmd
   ```

### Running (Two Windows Required)

**Window 1 - Start the SAGA scheduler service:**
```
.\runsched
```
This starts the HEFT scheduler listening on port 9999.

**Window 2 - Configure and run the visualization:**
```
runconfig
```
This opens the configuration GUI where you can set:
- Number of nodes (infantry/vehicles)
- Communication range and data rates
- DAG structure (depth, branching factor)
- Task and transfer durations

Then launch the visualization:
```
runiobt
```

### Hotkeys
- **N**: Toggle network overlay
- **Escape**: Open menu (Resume/Settings/Quit)

## Project Structure

```
iobt-ncsim/
├── README.md              # This file
├── CLAUDE.md              # Detailed project specification
├── runsched.bat           # Start SAGA scheduler service
├── runconfig.bat          # Open configuration GUI
├── runiobt.bat            # Launch visualization
├── saga-service/          # SAGA scheduler service (Python)
│   ├── scheduler_service.py   # Main service (HEFT/CPOP)
│   ├── requirements.txt       # Python dependencies
│   └── test_connection.py     # Connection test script
├── iobt-viz/              # Visualization engine (OpenRA-derived)
│   ├── engine/            # OpenRA engine
│   ├── mods/iobt/         # IoBT visualization mod
│   │   ├── chrome/        # UI definitions
│   │   ├── maps/          # Scenario maps
│   │   ├── OpenRA.Mods.IoBT/  # C# mod code
│   │   │   ├── Bridge/    # TCP bridge for SAGA communication
│   │   │   └── ...
│   │   └── tools/         # Python config tools
│   └── ...
└── reference/             # Read-only OpenRA reference copies
```

## Configuration

The configuration GUI (`runconfig`) allows you to customize:

| Parameter | Description | Default |
|-----------|-------------|---------|
| Total Nodes | Number of mobile compute units | 15 |
| Infantry % | Percentage of infantry vs vehicles | 70% |
| Communication Range | Max link distance (cells) | 8 |
| Max/Min Data Rate | Bandwidth range (Mbps) | 100/10 |
| DAG Levels | Depth of task tree | 1 |
| Branches | Children per task | 8 |
| Task Duration | Execution time (ticks) | 75 |
| Transfer Duration | Data transfer visualization (ticks) | 80 |

## Architecture

```
┌─────────────────┐         TCP/9999          ┌─────────────────┐
│   saga-service  │◄────────────────────────►│    iobt-viz     │
│                 │    schedule_request       │                 │
│  HEFT/CPOP      │    schedule_response      │  Visualization  │
│  Scheduler      │    (task assignments)     │  + Lua scripts  │
└─────────────────┘                           └─────────────────┘
                                                      │
                                                      ▼
                                              ┌─────────────────┐
                                              │  Network Overlay │
                                              │  - Link quality  │
                                              │  - Task states   │
                                              │  - Transfers     │
                                              └─────────────────┘
```

## How It Works

1. **Configuration**: `runconfig` generates `iobt-config.lua` with node positions, DAG structure, and network settings

2. **Scheduler Service**: `runsched` starts the SAGA service which listens for scheduling requests

3. **Visualization**: `runiobt` launches iobt-viz which:
   - Spawns compute nodes (mobile units)
   - Connects to SAGA service via TCP bridge
   - Sends DAG + network topology to HEFT scheduler
   - Receives task-to-node assignments
   - Visualizes task execution and data transfers

4. **HEFT Scheduling**: The scheduler considers:
   - Network connectivity between nodes
   - Link data rates (based on distance)
   - Task dependencies (DAG edges)
   - Compute costs

## Documentation

- `CLAUDE.md`: Complete project specification and architecture
- `iobt-viz/DEVELOPMENT.md`: Development notes and common issues

## Requirements

### Python Dependencies (saga-service)
```
anrg-saga>=2.0.0
networkx>=3.0
numpy>=1.24
```

Install with: `pip install -r saga-service/requirements.txt`

### .NET Dependencies
- .NET 8.0 SDK (for building iobt-viz)

## Author

Developed by **Bhaskar Krishnamachari** (USC), 2026

Autonomous Networks Research Group (ANRG)
University of Southern California

## License

MIT License - See LICENSE file for details.

# IoBT-NCSim

**Immersive Networked Compute Simulator**

An interactive simulation environment for visualizing and analyzing networked computing systems, featuring RTS-style visualization of compute nodes, network links, data flows, and task execution.

## Overview

IoBT-NCSim combines:

- **iobt-viz**: High-quality RTS-style visualization (derived from OpenRA) displaying compute nodes, network links, data flows, and DAG task execution
- **ncsim** (planned): A standalone, headless-capable discrete-event simulation engine for networked computing
- **viz-bridge** (planned): A protocol translation layer enabling ncsim to drive any compatible visualizer

## Current Features

### Visualization (iobt-viz)
- Real-time network topology visualization with distance-based link quality
- DAG (Directed Acyclic Graph) task scheduling visualization
- Task-to-task data transfer visualization with highlighted links
- Compute node markers (blue/yellow for high/low CPU)
- Network-aware scheduling with connectivity checks
- Interactive configuration GUI for scenario setup

### Network Overlay
- Link color coding: green (high bandwidth) → yellow → red (low bandwidth)
- Active transfer highlighting (cyan)
- Status panel showing DAG structure, task states, and active transfers
- Configurable communication range and data rates

## Quick Start

### Prerequisites
- Windows 10/11
- .NET 8.0 SDK
- Python 3.11+ (for configuration tools)

### Building
```powershell
cd iobt-viz
.\make.ps1 clean
.\make.ps1 all
```

### Running
1. Configure the simulation:
   ```
   runconfig
   ```
   This opens the configuration GUI where you can set:
   - Number of nodes (infantry/vehicles)
   - Communication range and data rates
   - DAG structure (depth, branching factor)
   - Task and transfer durations

2. Launch the visualization:
   ```
   runiobt
   ```

### Hotkeys
- **N**: Toggle network overlay
- **Escape**: Open menu (Resume/Settings/Quit)

## Project Structure

```
iobt-ncsim/
├── CLAUDE.md              # Detailed project specification
├── iobt-viz/              # Visualization engine (OpenRA-derived)
│   ├── engine/            # OpenRA engine
│   ├── mods/iobt/         # IoBT visualization mod
│   │   ├── chrome/        # UI definitions
│   │   ├── maps/          # Scenario maps
│   │   ├── OpenRA.Mods.IoBT/  # C# mod code
│   │   └── tools/         # Python config tools
│   └── ...
├── reference/             # Read-only OpenRA reference copies
└── README.md
```

## Configuration

The configuration GUI (`runconfig`) allows you to customize:

| Parameter | Description | Default |
|-----------|-------------|---------|
| Total Nodes | Number of mobile units | 50 |
| Infantry % | Percentage of infantry vs vehicles | 70% |
| Communication Range | Max link distance (cells) | 8 |
| Max/Min Data Rate | Bandwidth range (Mbps) | 100/10 |
| DAG Depth | Levels in task tree | 3 |
| Branching Factor | Children per task | 2 |
| Task Duration | Execution time (ticks) | 75 |
| Transfer Duration | Data transfer visualization time (ticks) | 50 |

## Documentation

- `CLAUDE.md`: Complete project specification and architecture
- `iobt-viz/DEVELOPMENT.md`: Development notes and common issues
- `iobt-viz/mods/iobt/NETWORK_OVERLAY.md`: Network overlay Lua API reference

## Author

Developed by **Bhaskar Krishnamachari** (USC), 2026

Autonomous Networks Research Group (ANRG)
University of Southern California

## License

Private repository - All rights reserved.

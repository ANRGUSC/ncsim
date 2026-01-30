# iobt-viz

**RTS-Style Visualization for Networked Computing**

iobt-viz provides an immersive, real-time visualization of networked computing systems using the [OpenRA](https://github.com/OpenRA/OpenRA) game engine. It displays compute nodes as mobile units, network links with quality indicators, and animated task execution with data transfers.

## Features

- **Network Topology Overlay**: Visualize links between nodes with color-coded bandwidth
- **DAG Task Visualization**: See task dependencies and execution state
- **Data Transfer Animation**: Watch data flow between nodes during transfers
- **Interactive Configuration**: GUI to set up scenarios before running
- **HEFT Scheduling Integration**: Real-time scheduling via saga-service

## Prerequisites

- Windows 10/11
- .NET 8.0 SDK
- saga-service running (for scheduling)

## Building

```powershell
cd iobt-viz
.\make.cmd
```

This compiles the C# code and fetches OpenRA engine dependencies.

## Running

### 1. Start the Scheduler Service

In a separate terminal:
```
.\runsched
```

### 2. Configure the Scenario

```
runconfig
```

This opens a GUI where you can set:

| Parameter | Description | Default |
|-----------|-------------|---------|
| Total Nodes | Number of compute units | 15 |
| Infantry % | Percentage infantry vs vehicles | 70% |
| Comm Range | Max link distance (cells) | 8 |
| Max/Min Data Rate | Bandwidth range (Mbps) | 100/10 |
| DAG Levels | Task tree depth | 1 |
| Branches | Children per task | 8 |
| Task Duration | Execution time (ticks) | 75 |
| Transfer Duration | Transfer animation (ticks) | 80 |

### 3. Launch Visualization

```
runiobt
```

## Hotkeys

| Key | Action |
|-----|--------|
| `N` | Toggle network overlay |
| `B` | Switch to Baseline mode (tasks stall on partition) |
| `S` | Switch to Smart mode (reassign stalled tasks to parent partition) |
| `H` | Switch to HEFT-Restart mode (restart DAG on largest partition) |
| `R` | Restart simulation |
| `Q` | Quit application |
| `Escape` | Open menu (Resume/Settings/Quit) |

## Resilience Modes

The visualization supports three modes for handling network partitions (when nodes become disconnected):

### Baseline Mode (`B`)
Tasks stall when their assigned node becomes unreachable. Execution resumes when connectivity is restored. This demonstrates the impact of network partitions on task completion time.

### Smart Mode (`S`)
When a partition occurs, tasks that were assigned to disconnected nodes are reassigned to available nodes in the connected partition. Completed tasks whose results are locally available are preserved - only remaining tasks are redeployed.

### HEFT-Restart Mode (`H`)
When a partition occurs, the entire DAG is restarted on the largest connected component. HEFT scheduling is re-requested for all tasks. This provides a clean restart but loses progress on completed tasks.

### Status Panel

The network overlay status panel shows:
- **Current mode**: Displayed as `Mode: Baseline [B/S/H]`
- **Per-mode makespans**: Compare execution times across modes (e.g., `B: 12.5s | S: 8.2s | H: 6.1s`)

To compare resilience strategies:
1. Run a scenario in Baseline mode, note the makespan
2. Press `S` to switch to Smart mode (DAG restarts automatically)
3. Create the same partition scenario, compare makespan
4. Press `H` to try HEFT-Restart mode

## Network Overlay

When enabled (`N` key), the overlay shows:

- **Link Colors**: Green (high bandwidth) → Yellow → Red (low bandwidth)
- **Active Transfers**: Cyan highlighting during data transfers
- **Status Panel**: DAG structure, task states, and transfer progress

## Architecture

```
iobt-viz/
├── engine/                 # OpenRA game engine
├── mods/iobt/             # IoBT visualization mod
│   ├── chrome/            # UI definitions (YAML)
│   ├── maps/              # Scenario maps
│   ├── OpenRA.Mods.IoBT/  # C# mod code
│   │   ├── Bridge/        # TCP bridge to saga-service
│   │   ├── Traits/        # Entity behaviors
│   │   └── Network/       # Network overlay rendering
│   └── tools/             # Python config tools
└── ...
```

### Key Components

- **SagaBridge**: TCP client connecting to saga-service (port 9999)
- **NetworkOverlay**: Renders links and transfer animations
- **DAGManager**: Tracks task states and dependencies
- **ConfigGenerator**: Produces `iobt-config.lua` from GUI settings

## How It Works

1. **Configuration**: `runconfig` generates `iobt-config.lua` with node positions, DAG structure, and network parameters

2. **Launch**: `runiobt` starts the visualization, spawning compute nodes as mobile units

3. **Scheduling**: When a DAG is submitted:
   - Network topology and DAG sent to saga-service
   - HEFT scheduler returns task-to-node assignments
   - Tasks execute on assigned nodes with animated transfers

4. **Visualization**: The overlay shows real-time:
   - Link quality based on node distance
   - Task execution state (idle/running/complete)
   - Data transfers with progress

## Development

For development notes and common issues, see:
- `DEVELOPMENT.md` in this directory
- [OpenRA Wiki](https://github.com/OpenRA/OpenRA/wiki)

### Useful Commands

```powershell
# Rebuild after changes
.\make.cmd

# Launch with debug logging
.\launch-game.cmd --debug

# Run utility commands
.\utility.cmd --help
```

## License

See [LICENSE](../LICENSE) for license details. Note: The OpenRA engine is licensed under GPLv3.

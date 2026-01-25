# IoBT Network Overlay System

This document describes the network overlay visualization system used in iobt-viz.

## Overview

The network overlay renders:
1. **Network links** between mobile units (color-coded by data rate)
2. **Compute node markers** (circles showing which units are compute nodes)
3. **DAG status panel** (task states, transfers)
4. **Active transfer highlighting** (cyan links for data in flight)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Lua Scripts                               │
│   (iobt-main.lua - drives simulation, calls API methods)        │
└─────────────────────────────────┬───────────────────────────────┘
                                  │ Lua API calls
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                   IoBTScriptProperties.cs                        │
│   (Exposes C# methods to Lua: Blue.AddTaskTransfer(...))        │
└─────────────────────────────────┬───────────────────────────────┘
                                  │ Method calls
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                   IoBTNetworkOverlay.cs                          │
│   (Main trait - manages state, renders visualization)           │
│                                                                  │
│   Key data structures:                                          │
│   - dagTasks: Dict<string, DagTask>    (task definitions)       │
│   - activeLinks: List<ActiveLink>      (current transfers)      │
│   - computeNodes: Dict<Actor, ComputeNodeInfo>                  │
│   - computeNodeList: List<Actor>       (ordered for indexing)   │
└─────────────────────────────────────────────────────────────────┘
```

## Key Files

| File | Purpose |
|------|---------|
| `OpenRA.Mods.IoBT/IoBTNetworkOverlay.cs` | Main overlay trait (rendering + state) |
| `OpenRA.Mods.IoBT/IoBTScriptProperties.cs` | Lua API bindings |
| `OpenRA.Mods.IoBT/IoBTNetworkOverlayHotkeyLogic.cs` | Hotkey handling ('N' to toggle) |
| `maps/iobt-sim/iobt-main.lua` | Example simulation script |

## Lua API Reference

### Task Management

```lua
-- Define a task in the DAG
Blue.AddDagTask(taskId, name, dependencies)
-- Example: Blue.AddDagTask("T1", "Process Data", "T0")
-- dependencies is comma-separated: "T0,T2" or "" for none

-- Assign a task to a compute node
Blue.AssignTask(taskId, nodeIndex)
-- Example: Blue.AssignTask("T1", 2)  -- Assign T1 to compute node C2

-- Mark task as completed
Blue.CompleteTask(taskId)

-- Mark task as stalled (waiting for connectivity)
Blue.StallTask(taskId)
Blue.UnstallTask(taskId)
```

### Data Transfers

```lua
-- Add a task-to-task transfer (RECOMMENDED)
-- Shows "T1→T4" in status panel, highlights link cyan
Blue.AddTaskTransfer(sourceTaskId, destTaskId, label)
-- Example: Blue.AddTaskTransfer("T1", "T4", "output")

-- Add a node-to-node transfer (lower level)
Blue.AddActiveLink(fromNodeIndex, toNodeIndex, label)
-- Example: Blue.AddActiveLink(0, 2, "data")

-- Clear all active transfers
Blue.ClearActiveLinks()

-- Clear entire DAG (tasks + transfers)
Blue.ClearDag()
```

### Network Queries

```lua
-- Get number of available compute nodes
local count = Blue.GetComputeNodeCount()

-- Check if two nodes are in communication range
local connected = Blue.AreNodesConnected(nodeIndex1, nodeIndex2)

-- Get which node a task is assigned to
local nodeIndex = Blue.GetTaskNodeIndex(taskId)

-- Get task dependencies as comma-separated string
local deps = Blue.GetTaskDependencies(taskId)
```

### Overlay Control

```lua
-- Toggle overlay visibility
Blue.ToggleOverlay()

-- Enable/disable specific features
Blue.SetOverlayEnabled(true/false)
Blue.SetLinksEnabled(true/false)
Blue.SetComputeMarkersEnabled(true/false)
Blue.SetDagStatusEnabled(true/false)

-- Adjust network range
Blue.SetNetworkRadius(cells)
```

## Visual Elements

### Link Colors

| Color | Meaning | Data Rate |
|-------|---------|-----------|
| Green | High bandwidth | ~100 Mbps |
| Yellow | Medium bandwidth | ~55 Mbps |
| Red | Low bandwidth | ~10 Mbps |
| Cyan (thick) | Active transfer | Any |

### Compute Node Markers

| Color | Meaning |
|-------|---------|
| Blue circle | High CPU compute node |
| Yellow circle | Low CPU compute node |

### Status Panel (Top-Left)

```
DAG Structure:
  T0: T1, T2
  T1: T3
  T2: T3

Status:
  T0 [Done] C0
  T1 [Run] C1 <--
  T2 [Wait] -
  T3 [Wait] -

Transfers:
  T0→T1 (C0→C1)
```

Task status colors:
- Gray: Pending (waiting)
- Cyan: Running
- Green: Completed
- Yellow: Stalled (network issue)

## Data Rate Calculation

Uses square-root distance degradation:

```
rate = MaxDataRate * (1 - sqrt(distance / range))
```

Where:
- `MaxDataRate` = 100 Mbps (at distance 0)
- `MinDataRate` = 10 Mbps (below this, link not shown)
- `NetworkRadius` = 8 cells (default range)

## Configuration (in rules/world.yaml)

```yaml
IoBTNetworkOverlay:
    NetworkRadius: 8           # Max link distance in cells
    LinkWidth: 1               # Normal link thickness
    ActiveLinkWidth: 3         # Active transfer thickness
    MaxDataRate: 100           # Mbps at zero distance
    MinDataRate: 10            # Mbps threshold for visibility
    ComputeCircleRadius: 150   # Marker size (world units)
    InfantryComputePercent: 15 # % infantry as compute nodes
    VehicleComputePercent: 50  # % vehicles as compute nodes
```

## Example: Task Transfer Flow

```lua
-- 1. Define DAG
Blue.AddDagTask("T0", "Load", "")
Blue.AddDagTask("T1", "Process", "T0")

-- 2. Assign and run T0
Blue.AssignTask("T0", 0)  -- T0 on node C0
-- (wait for execution time)

-- 3. Complete T0, start transfer to T1's node
Blue.CompleteTask("T0")
Blue.AssignTask("T1", 1)  -- T1 will run on node C1
Blue.AddTaskTransfer("T0", "T1", "data")
-- Link C0→C1 turns cyan, status shows "T0→T1 (C0→C1)"

-- 4. After transfer completes
Blue.ClearActiveLinks()
-- (T1 can now start running)
```

## Extending the Overlay

### Adding New Visual Elements

1. Create a new `IRenderable` class (see `IoBTLineRenderable`, `IoBTFilledCircleRenderable`)
2. Yield instances from `RenderAnnotations()` method
3. World-space: use `WPos` coordinates
4. Screen-space: use `IoBTScreenTextRenderable` with `int2` coordinates

### Adding New Lua Methods

1. Add method to `IoBTNetworkOverlay.cs`
2. Add Lua binding in `IoBTScriptProperties.cs` with `[Desc("...")]` attribute
3. Call via `Blue.MethodName()` in Lua

### Modifying Link Colors

Edit `GetLinkColor()` method in `IoBTNetworkOverlay.cs`:
```csharp
Color GetLinkColor(double rate, bool isActive)
{
    if (isActive)
        return Color.Cyan;  // Change active transfer color here

    // Modify the gradient logic for normal links
}
```

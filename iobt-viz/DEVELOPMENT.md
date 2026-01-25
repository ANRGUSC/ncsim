# IoBT-Viz Development Notes

This document contains development tips and common pitfalls when working with the iobt-viz codebase.

> **IMPORTANT**: When you complete a checkpoint or learn something new about iobt-viz development, add it to the "Lessons Learned" section at the bottom of this file. This helps future development sessions avoid repeating mistakes.

## Project Structure

```
iobt-viz/
├── engine/                      # OpenRA engine (copied from reference/OpenRA)
├── mods/
│   ├── iobt/                    # IoBT visualization mod
│   │   ├── chrome/              # UI definitions (YAML)
│   │   ├── maps/                # Map files with Lua scripts
│   │   ├── OpenRA.Mods.IoBT/    # C# mod code
│   │   ├── rules/               # Game rules
│   │   └── mod.yaml             # Mod configuration
│   └── example/                 # Example mod (unused)
├── mod.config                   # Build configuration
└── make.ps1                     # Build script
```

## Building

```powershell
cd iobt-viz
.\make.ps1    # Then type: all
```

### Clean Rebuild

**Always do a clean rebuild when adding new C# files:**

```powershell
.\make.ps1    # Type: clean
.\make.ps1    # Type: all
```

The build system uses incremental compilation and may not detect new .cs files without a clean.

## Running

```powershell
.\launch-game.cmd Game.Mod=iobt
```

## Adding New C# Files

When adding new .cs files to `mods/iobt/OpenRA.Mods.IoBT/`:

1. **Use the correct namespace:**
   ```csharp
   namespace OpenRA.Mods.IoBT
   ```

2. **Include common using directives:**
   ```csharp
   using System;
   using System.Collections.Generic;
   using System.Linq;
   using OpenRA.Graphics;
   using OpenRA.Mods.Common.Traits;
   using OpenRA.Mods.Common.Widgets;
   using OpenRA.Mods.Common.Widgets.Logic;
   using OpenRA.Widgets;
   ```

3. **Do a clean rebuild** (see above)

4. **The .csproj auto-includes all .cs files** via glob pattern - no need to edit it

## Adding New Chrome (UI) Files

1. Create YAML file in `mods/iobt/chrome/`
2. Add reference in `mods/iobt/mod.yaml` under `ChromeLayout:`
3. If using custom Logic class, ensure it exists and builds

## Common Errors

### "Cannot locate type: ClassName"

**Cause:** The DLL wasn't rebuilt after adding the class.

**Solution:** Clean rebuild:
```powershell
.\make.ps1    # Type: clean
.\make.ps1    # Type: all
```

### "The type or namespace name 'X' could not be found"

**Cause:** Missing `using` directive in C# file.

**Solution:** Add the appropriate using statement. Common namespaces:
- `ButtonWidget` → `using OpenRA.Mods.Common.Widgets;`
- `IngameInfoPanel` → `using OpenRA.Mods.Common.Widgets.Logic;`
- `MenuPostProcessEffect` → `using OpenRA.Mods.Common.Traits;`
- `Widget`, `Ui`, `ChromeLogic` → `using OpenRA.Widgets;`

### "Could not find file 'mods/iobt/something'"

**Cause:** mod.yaml references a directory or file that doesn't exist.

**Solution:** Create the missing directory/file, or remove the reference from mod.yaml.

## Component Documentation

| Component | Documentation |
|-----------|---------------|
| Network Overlay | `mods/iobt/NETWORK_OVERLAY.md` - Lua API, visual elements, extending |

## Key Files Reference

| File | Purpose |
|------|---------|
| `mod.yaml` | Mod configuration, asset loading, chrome layout |
| `chrome/ingame-player.yaml` | In-game UI layout |
| `chrome/ingame-menu.yaml` | Escape menu (Resume/Settings/Quit) |
| `chrome/mainmenu.yaml` | Main menu (auto-starts game) |
| `OpenRA.Mods.IoBT/IoBTNetworkOverlay.cs` | Network visualization & DAG display |
| `OpenRA.Mods.IoBT/IoBTMainMenuLogic.cs` | Auto-start logic |
| `OpenRA.Mods.IoBT/IoBTIngameMenuLogic.cs` | Escape menu logic |
| `maps/iobt-sim/iobt-main.lua` | DAG execution & unit movement |

## Hotkeys

| Key | Action |
|-----|--------|
| N | Toggle network overlay |
| Escape | Open menu (Resume/Settings/Quit) |

## Engine Updates

The engine in `iobt-viz/engine/` is a copy from `reference/OpenRA/`. If you need to update:

1. Do NOT enable `AUTOMATIC_ENGINE_MANAGEMENT` in mod.config (downloads from internet)
2. Instead, copy updated engine from reference: `cp -r ../reference/OpenRA ./engine`
3. Clean rebuild

---

## Inheritance Pattern (Important!)

The iobt mod **inherits heavily** from `common` and `ra` mods. In `mod.yaml`:

```yaml
ChromeLayout:
  common|chrome/settings-audio.yaml    # Inherited from common mod
  iobt|chrome/ingame-player.yaml       # Custom iobt override
```

**Key lesson**: Before implementing a feature, check if it's already inherited from common/ra mods.

### Where Inherited Files Actually Live

| Looking for... | NOT in | Actually in |
|----------------|--------|-------------|
| Common chrome files | `mods/common/` | `engine/mods/common/chrome/` |
| Common fluent files | `mods/common/` | `engine/mods/common/fluent/` |
| Settings logic | `mods/` | `engine/OpenRA.Mods.Common/Widgets/Logic/Settings/` |

### How to Check What's Inherited

```bash
# Find what mod.yaml references
grep "common|" mods/iobt/mod.yaml

# Find the actual file
ls engine/mods/common/chrome/settings-audio.yaml

# Search reference for how OpenRA implements something
grep -r "SomeFeature" ../reference/OpenRA/
```

---

## Lessons Learned

### Checkpoint 1.2: Audio Mute Option (2026-01-24)

**Discovery**: The audio mute option was already fully implemented via inheritance.

**What was inherited:**
- `common|chrome/settings-audio.yaml` - UI layout with "Mute Sound" checkbox
- `AudioSettingsLogic.cs` - Logic connecting checkbox to `Game.Sound.MuteAudio()`
- `SoundSettings.Mute = false` - Default setting (audio on)

**Lesson**: Always check `engine/mods/common/` before writing new code. Many features "just work" through the ModSDK inheritance pattern.

### Checkpoint 1.3: Lobby Simplification (2026-01-24)

**Discovery**: The lobby is already bypassed via auto-start.

**How it works:**
- `IoBTMainMenuLogic.cs` runs on launch
- Auto-detects and loads an iobt map (priority: iobt-sim → iobt-demo2 → any iobt map)
- Calls `Game.LoadMap(mapUid)` directly - no lobby UI shown

**Added:** IoBT-viz branding overlay in `ingame-player.yaml`:
- Position: bottom-right corner
- Shows: "IoBT-viz" + "ANRG, USC, 2026"
- Uses `Contrast: true` for readability

**Lesson**: The auto-start design is intentional for a simulation visualizer - zero-click launch to visualization.

### Network Overlay: Task Transfer Display (2026-01-24)

**Added**: Task-to-task transfer visualization.

**New Lua API:**
```lua
Blue.AddTaskTransfer("T1", "T4", "data")  -- Shows "T1→T4" in status panel
```

**What it does:**
- Displays active transfers in the status panel (left side) as "T1→T4 (C0→C2)"
- Highlights the link between nodes in cyan
- Automatically looks up which nodes the tasks are assigned to

**Key files modified:**
- `IoBTNetworkOverlay.cs` - Added `AddTaskTransfer()` method, expanded `ActiveLink` class
- `IoBTScriptProperties.cs` - Added Lua binding

**Documentation:** See `mods/iobt/NETWORK_OVERLAY.md` for full API reference.

### Config Generator: Task Transfer Visualization (2026-01-24)

**Added**: Task transfer visualization to generated DAG execution code.

**What changed in `tools/iobt_config_generator.py`:**
- `generate_dag_execution_lua()` now generates code that shows data transfers between tasks
- When a task completes, `StartDataTransfers()` calls `Blue.AddTaskTransfer()` for each dependent task on a different node
- Transfer duration is `task_duration // 3` (minimum 25 ticks = 1 second)
- `PreAssignTaskNodes()` pre-assigns all tasks to nodes at startup so transfers know destinations

**Workflow reminder**: Changes to `iobt_config_generator.py` don't take effect until you:
1. Run `runconfig.bat` to regenerate `iobt-config.lua`
2. Run `runiobt.bat` to launch with the new config

**Key insight**: The generated `iobt-config.lua` is what actually runs, not `iobt-main.lua` when using the config GUI workflow.

---

## Build from Git Bash (Windows)

```bash
cd iobt-viz
powershell.exe -ExecutionPolicy Bypass -Command "& { cd 'C:\Users\bhask\claude\iobt-ncsim\iobt-viz'; .\make.ps1 all }"
```

### Checkpoint 1.10-1.11: Bridge Server + Trait Integration (2026-01-24)

**Added**: TCP bridge server for external simulator communication (SAGA scheduler, ncsim).

**New Files Created:**
- `OpenRA.Mods.IoBT/Bridge/IoBTBridgeServer.cs` - TCP server on port 9999
- `OpenRA.Mods.IoBT/Bridge/IoBTBridgeTrait.cs` - World trait that starts/stops bridge

**Protocol**: Newline-delimited JSON (for easy testing with netcat)
```bash
# Test connection:
echo '{"type":"ping"}' | nc localhost 9999
```

**Message Types:**
| Type | Direction | Purpose |
|------|-----------|---------|
| `ping` | Client → Bridge | Connectivity test |
| `pong` | Bridge → Client | Ping response |
| `welcome` | Bridge → Client | Sent on connect with server info |
| `get_state` | Client → Bridge | Request current network state |
| `state` | Bridge → Client | Response with node count, connectivity |
| `schedule_request` | Either | Request SAGA scheduling |
| `schedule_response` | Either | Task→node assignments |

**Key Architectural Decisions:**
1. **Threading**: Messages received on socket thread, queued for processing on game thread via `ITick`
2. **Multiple clients**: Supports multiple simultaneous connections (for future use)
3. **Graceful shutdown**: Bridge stopped when World actor is disposed

**Build Note**: When adding new files in subdirectories (like `Bridge/`), the SDK-style .csproj auto-includes them - no manual edits needed.

**Common Error**: Missing `using OpenRA.Graphics;` for `WorldRenderer` in `IWorldLoaded` interface. Always include this for world traits.

**Lua API Added:**
```lua
Blue.IsBridgeRunning()        -- Check if bridge is active
Blue.GetBridgeConnectionCount() -- Number of connected clients
Blue.RequestSchedule(dagJson)  -- Request schedule from SAGA
```

### Checkpoint 1.12: SAGA Scheduler Service (2026-01-24)

**Added**: Python SAGA scheduler service that connects to bridge.

**New Directory**: `saga-service/`
- `scheduler_service.py` - Main service (connects to bridge, calls SAGA)
- `test_connection.py` - Simple connection test script
- `requirements.txt` - Dependencies (anrg-saga, networkx, numpy)
- `pyproject.toml` - Python package config

**Usage:**
```bash
cd saga-service
pip install -r requirements.txt
python scheduler_service.py --host localhost --port 9999 --scheduler heft
```

**Fallback Behavior**: If SAGA library not installed, uses simple round-robin scheduler. This allows testing the protocol without full SAGA setup.

**Protocol Flow:**
1. Service connects to bridge on port 9999
2. Receives `welcome` message with server info
3. Sends `hello` identifying as SAGA scheduler
4. Waits for `schedule_request` messages
5. Calls SAGA HeftScheduler
6. Returns `schedule_response` with task→node assignments

**Key Design Decision**: The scheduler service is a separate process, not embedded in iobt-viz. This allows:
- Running SAGA (Python) alongside OpenRA (C#)
- Easy testing and debugging of scheduler independently
- Future replacement with different schedulers

### Log Channel Error Fix (2026-01-24)

**Error:** `System.ArgumentException: Tried logging to non-existent channel bridge`

**Cause:** Using `Log.Write("bridge", ...)` but OpenRA requires log channels to be pre-registered.

**Solution:** Use existing channels like "debug" instead:
```csharp
// Wrong - causes crash
Log.Write("bridge", "message");

// Correct - use existing channel
Log.Write("debug", "message");
```

**Available channels:** debug, perf, server, nat, geoip, irc, and others defined in OpenRA.

### Network Testing on Windows (2026-01-24)

**Problem:** Network testing commands like `netstat` don't work reliably in Git Bash on Windows.

**Solution:** Always use Python scripts for network testing:
```python
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock.connect(('localhost', 9999))
    print("Connected!")
except ConnectionRefusedError:
    print("Port not open")
```

**Existing test script:** `saga-service/test_connection.py`

### Launching iobt-viz (2026-01-24)

**Rule:** Always ask the user to manually launch iobt-viz rather than trying to launch it programmatically.

**Why:**
- GUI apps launched from scripts may not show properly
- User can confirm when the app is fully loaded
- Avoids race conditions with bridge startup

**Command for user:**
```powershell
cd C:\Users\bhask\claude\iobt-ncsim\iobt-viz
.\launch-game.cmd Game.Mod=iobt
```

### SAGA Library Installation on Windows (2026-01-24)

**Problem:** `pygraphviz` requires native Graphviz libraries that are difficult to install on Windows.

**Solution:** Install SAGA without pygraphviz - it's only needed for visualization, not core scheduling:
```bash
pip install anrg-saga --no-deps
pip install networkx numpy scipy pandas pydantic gitpython tqdm z3-solver pysmt
```

**Note:** Some SAGA imports require `pysmt` even if not using SMT schedulers - the module import loads all schedulers.

### BridgeMessage Constructor (2026-01-24)

**Error:** `'BridgeMessage' does not contain a constructor that takes 1 arguments`

**Cause:** BridgeMessage only has a parameterless constructor.

**Wrong:**
```csharp
var msg = new BridgeMessage("hello_ack");  // No such constructor
```

**Correct:**
```csharp
var msg = new BridgeMessage();
msg.Type = "hello_ack";
msg.Data["key"] = "value";
```

### Alternative Build Methods (2026-01-24)

**Preferred Method:** Use `make.ps1` for building:
```powershell
cd iobt-viz
.\make.ps1    # Type: all
```

**Alternative Method:** Direct `dotnet build` also works for quick rebuilds of the IoBT mod:
```powershell
cd iobt-viz
dotnet build "mods\iobt\OpenRA.Mods.IoBT\OpenRA.Mods.IoBT.csproj"
```

**When to use each:**
- `make.ps1 all` - Full build including engine and all mods (use after clean or major changes)
- `dotnet build` on specific .csproj - Quick rebuild of just the IoBT mod (use for iterating on mod code)

**Note:** Both methods produce the same output. `dotnet build` is faster when only modifying the IoBT mod code, as it skips engine compilation if already built.

### SAGA API Changes (2026-01-24)

**Problem:** SAGA scheduler API changed - using NetworkX graph directly causes errors.

**Error:** `list index out of range` or `BaseModel.__init__() takes 1 positional argument but 2 were given`

**Solution:** SAGA now uses Pydantic models. Correct API:
```python
from saga import Network, TaskGraph, NetworkNode, NetworkEdge, TaskGraphNode, TaskGraphEdge

# Network construction
nodes = frozenset([
    NetworkNode(name="node_0", speed=1.0),
    NetworkNode(name="node_1", speed=1.0),
])
edges = frozenset([
    # IMPORTANT: Self-loops required for local transfers!
    NetworkEdge(source="node_0", target="node_0", speed=float('inf')),
    NetworkEdge(source="node_0", target="node_1", speed=100.0),
])
network = Network(nodes=nodes, edges=edges)

# TaskGraph construction
tasks = frozenset([
    TaskGraphNode(name="T0", cost=10.0),
])
dependencies = frozenset([
    TaskGraphEdge(source="T0", target="T1", size=5.0),
])
taskgraph = TaskGraph(tasks=tasks, dependencies=dependencies)

# Run scheduler
schedule = HeftScheduler().schedule(network, taskgraph)

# Extract assignments from schedule.mapping (Dict[node_name, List[ScheduledTask]])
for node_name, scheduled_tasks in schedule.mapping.items():
    for task in scheduled_tasks:
        print(f"{task.name} -> {node_name}")
```

**Critical:** Include self-loops (`node_0 -> node_0`) for each node - SAGA requires these for modeling local transfers when parent and child tasks are on the same node.

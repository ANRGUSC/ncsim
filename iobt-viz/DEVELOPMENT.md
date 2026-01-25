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

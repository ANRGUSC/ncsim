# iobt-ncsim
## Immersive Networked Compute Simulator
### Project Specification for Claude Code

---

## 1. HIGH-LEVEL VISION

Build an interactive simulation environment that combines:

1. **iobt-viz**: High-quality RTS-style visualization (derived from OpenRA) displaying compute nodes, network links, data flows, and task execution
2. **ncsim**: A standalone, headless-capable discrete-event simulation engine modeling networked computing (nodes, links, flows, compute resources, task DAGs, scheduling, routing, mobility)
3. **ncsim-deck**: A control-and-observability application for scenario setup, simulation control, and performance dashboards
4. **viz-bridge**: A protocol translation layer enabling ncsim to drive any compatible visualizer (iobt-viz being the primary target)

**End State**: A compelling, demo-friendly and research-friendly platform where users can watch a battlefield-style visualization while the underlying system models compute + network behavior and produces time-series metrics.

**Design Philosophy**: 
- **ncsim** should be a fully capable standalone simulator (like ns-3) that can run headless for batch experiments
- **iobt-viz** should be modular enough to visualize other simulations beyond ncsim
- **viz-bridge** provides clean separation so either side can be swapped

---

## 2. COMPONENT OVERVIEW

| Component | Purpose | Language | Standalone? |
|-----------|---------|----------|-------------|
| **iobt-ncsim** | Umbrella project | — | — |
| **iobt-viz** | Visualization engine (OpenRA-derived) | C# (.NET 8.0) | Yes (with any viz-bridge client) |
| **ncsim** | Network-compute discrete-event simulator | Python 3.11+ | Yes (headless batch mode) |
| **ncsim-deck** | Control app with dashboards | Python 3.11+ | Yes (can mock data) |
| **viz-bridge** | Protocol adapter between ncsim and visualizers | Python 3.11+ | Yes (separate package) |

**Packaging decision:** viz-bridge is a **separate installable package** (not a submodule of ncsim). This allows:
- ncsim to depend on viz-bridge (not vice versa)
- Other simulators to use viz-bridge independently
- Clear dependency direction: `ncsim → viz-bridge → (TCP) → iobt-viz`

### 2.1 Dual-Backend Architecture

iobt-viz supports **two execution backends** that drive the same visualization overlays:

```
┌─────────────────────────────────────────────────────────────────────┐
│                           iobt-viz                                  │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              Shared Visualization Layer                       │   │
│  │   (overlays, entity rendering, link visualization, UI)        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              ▲                                      │
│                              │ VizState / VizDelta                  │
│                              │                                      │
│     ┌────────────────────────┴────────────────────────┐            │
│     │                                                  │            │
│  ┌──┴───────────────┐                    ┌────────────┴──────────┐ │
│  │  LuaSimBackend   │                    │    BridgeBackend      │ │
│  │  (standalone)    │                    │    (ncsim-connected)  │ │
│  │                  │                    │                        │ │
│  │  • Runs in Lua   │                    │  • Receives step      │ │
│  │  • Local sim     │                    │    frames from        │ │
│  │  • Demo/teaching │                    │    viz-bridge         │ │
│  │  • Interactive   │                    │  • Research-grade     │ │
│  └──────────────────┘                    │  • Reproducible       │ │
│                                          └───────────┬────────────┘ │
└──────────────────────────────────────────────────────┼──────────────┘
                                                       │ TCP/9999
                                                       ▼
                                              ┌─────────────────┐
                                              │   viz-bridge    │
                                              └────────┬────────┘
                                                       │
                                                       ▼
                                              ┌─────────────────┐
                                              │     ncsim       │
                                              └─────────────────┘
```

| Backend | Purpose | Authoritative? | Use Case |
|---------|---------|----------------|----------|
| **LuaSimBackend** | iobt-viz standalone execution | Self-contained | Demos, teaching, intuition-building |
| **BridgeBackend** | ncsim-connected execution | ncsim owns time/state | Research, experiments, validation |

**Key principle:** Both backends produce the same **VizState/VizDelta** data model, so the overlay layer doesn't know or care which backend is active. This prevents duplication and drift.

#### VizState / VizDelta Abstraction

Both backends emit updates in a common format consumed by the visualization layer:

| Data | Contents |
|------|----------|
| **Entities** | position, role, compute capability, mobile flag |
| **Links** | up/down, bandwidth, utilization, latency |
| **Tasks** | state (waiting/running/complete), assigned node |
| **Transfers** | state (active/stalled/complete), progress, link |

The overlay layer reads only VizState/VizDelta — this is the key abstraction.

#### LuaSimBackend (Standalone Mode)

**What it is:**
- Runs entirely inside iobt-viz using Lua (no external processes)
- Uses existing mod code for DAG definition, execution, task state, connectivity
- No external processes or bridge required

**Capabilities:**
- Single continuous DAG configured and executed
- Task execution and transfers shown live via overlays
- Mouse-driven troop movement changes network topology
- Transfers stall/resume when nodes disconnect/reconnect

**Limitations (explicit non-goals):**
- Not intended for research accuracy
- No trace replay
- No exact numerical matching with ncsim
- Limited scenario feature set (subset of ncsim)
- Semantics are qualitative, not quantitatively validated

**Implementation note:** The LuaSimBackend already exists in some form in the current mod. The coding agent must **read and understand the existing implementation first**, then wrap/stabilize it — not rewrite from scratch.

#### BridgeBackend (ncsim-Connected Mode)

**What it is:**
- Uses OpenRA purely as an interactive front-end
- User actions sent to ncsim via viz-bridge
- Step frames from ncsim drive visualization updates

**ncsim is authoritative for:**
- Time (sim_time)
- Scheduling decisions
- Transfer timing and dynamics
- Metrics, traces, reproducibility

**This is the research-grade path** for experiments, parameter sweeps, and publications.

#### Mode Selection

iobt-viz provides a simple mode switch:

```yaml
# In mod.yaml or game config
backend: lua_sim   # or: bridge
```

Or via:
- Config flag at startup
- Dev hotkey (F12 to toggle)
- Menu option in lobby

From the user's perspective, **both modes feel the same** — selection, right-click movement, overlays all work identically.

---

## 3. REPOSITORY STRUCTURE

```
iobt-ncsim/
├── CLAUDE.md                       # This file - project specification
├── README.md                       # Project overview and quickstart
│
├── reference/                      # READ-ONLY reference copies (never modify)
│   ├── OpenRA/                     # Pristine OpenRA engine source
│   │   ├── OpenRA.sln
│   │   ├── OpenRA.Game/
│   │   ├── OpenRA.Mods.Common/
│   │   └── ...
│   └── OpenRAModSDK/               # Pristine ModSDK
│       ├── ExampleMod.sln
│       ├── engine/
│       ├── mods/
│       └── ...
│
├── iobt-viz/                       # WORKING COPY - evolves from OpenRA/ModSDK
│   │                               # (starts as modified copy, gradually transforms)
│   ├── OpenRA.sln                  # Initially from OpenRA, renamed later
│   ├── OpenRA.Game/                # Core engine (becomes IoBTViz.Core later)
│   ├── OpenRA.Mods.Common/         # Shared code (becomes IoBTViz.Renderer later)
│   ├── OpenRA.Mods.IoBT/           # IoBT-specific code (our main work area)
│   ├── mods/
│   │   └── iobt/                   # IoBT visualization mod
│   │       ├── mod.yaml
│   │       ├── chrome/             # UI definitions (gradually simplified)
│   │       ├── rules/              # Entity definitions
│   │       └── maps/
│   ├── glsl/                       # Shaders
│   └── Makefile
│
├── ncsim/                          # Simulation engine (Python) - NEW CODE
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── ncsim/
│   │   ├── __init__.py
│   │   ├── main.py                 # CLI entry point
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── simulation.py       # Main DES loop
│   │   │   ├── event_queue.py      # Priority queue
│   │   │   └── clock.py            # Simulation time management
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── network.py          # Network graph (nodes, links)
│   │   │   ├── compute.py          # Compute node model
│   │   │   ├── task.py             # Task and DAG model
│   │   │   ├── flow.py             # Data flow / transfer model
│   │   │   └── mobility.py         # Node movement model
│   │   ├── scheduler/
│   │   │   ├── __init__.py
│   │   │   ├── base.py             # Scheduler interface
│   │   │   ├── saga_adapter.py     # Wraps SAGA schedulers for ncsim
│   │   │   ├── converters.py       # ncsim ↔ SAGA model conversion
│   │   │   └── custom/             # Custom schedulers (optional)
│   │   │       └── __init__.py
│   │   ├── routing/
│   │   │   ├── __init__.py
│   │   │   ├── base.py             # Router interface
│   │   │   └── shortest_path.py    # Dijkstra-based routing
│   │   ├── metrics/
│   │   │   ├── __init__.py
│   │   │   ├── collector.py        # Metrics aggregation
│   │   │   └── timeseries.py       # Time series storage
│   │   └── io/
│   │       ├── __init__.py
│   │       ├── scenario_loader.py  # YAML scenario parsing
│   │       └── results_writer.py   # Output formatting
│   ├── tests/
│   └── scenarios/
│
├── viz-bridge/                     # Protocol adapter (Python) - NEW CODE
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── viz_bridge/
│   │   ├── __init__.py
│   │   ├── protocol.py             # Message definitions
│   │   ├── encoder.py              # ncsim state → wire format
│   │   ├── decoder.py              # wire format → ncsim events
│   │   ├── connection.py           # TCP client management
│   │   ├── frame_buffer.py         # Step frame buffering
│   │   └── adapters/
│   │       ├── __init__.py
│   │       ├── base.py             # Adapter interface
│   │       └── iobt_viz.py         # iobt-viz specific translations
│   └── tests/
│
├── ncsim-deck/                     # Control application (Python) - NEW CODE
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── ncsim_deck/
│   │   ├── __init__.py
│   │   ├── main.py                 # Application entry point
│   │   ├── ui/
│   │   │   ├── __init__.py
│   │   │   ├── main_window.py
│   │   │   ├── control_panel.py
│   │   │   ├── scenario_panel.py
│   │   │   ├── dashboard.py
│   │   │   └── widgets/
│   │   ├── connection/
│   │   └── mock/
│   └── tests/
│
├── docs/
│   ├── architecture.md
│   ├── viz-bridge-protocol.md
│   └── api/
│
└── examples/
    ├── headless_batch.py
    ├── custom_scheduler.py
    └── scenarios/
```

### 3.1 The Dual-Copy Strategy

**Why keep reference copies?**

iobt-viz evolves FROM OpenRA — it doesn't start from scratch. We maintain pristine reference copies to:

1. **Safe refactoring**: Always have original code to consult when modifying/removing features
2. **Understanding**: Grep/search reference to understand how something works before changing it
3. **Diffing**: Compare working copy against reference to see cumulative changes
4. **Recovery**: If something breaks badly, the original is right there
5. **Documentation**: The delta between `reference/` and `iobt-viz/` documents all customizations

**Rules:**
- `reference/` is **READ-ONLY** — never modify these files
- `iobt-viz/` is the **WORKING COPY** — all modifications happen here
- When unsure how OpenRA implements something, check `reference/` first
- Periodically document major deltas in `docs/openra-changes.md`

---

## 4. ARCHITECTURE OVERVIEW

### 4.1 Component Interaction Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ncsim-deck                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │ Scenario Setup  │  │ Speed Control   │  │ Metrics Dashboard           │  │
│  │ - Load scenario │  │ - Pause/Resume  │  │ - Throughput charts         │  │
│  │ - Select policy │  │ - 1x/2x/5x/Max  │  │ - Utilization graphs        │  │
│  │ - Configure     │  │ - Step mode     │  │ - Gantt chart               │  │
│  └────────┬────────┘  └────────┬────────┘  └─────────────▲───────────────┘  │
└───────────┼────────────────────┼─────────────────────────┼──────────────────┘
            │ Commands           │ Commands                │ Metrics stream
            ▼                    ▼                         │
┌───────────────────────────────────────────────────────────────────────────┐
│                               ncsim                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ Simulation Core (Discrete Event Simulation)                          │  │
│  │ - Event queue with sim_time                                          │  │
│  │ - Single authoritative clock                                         │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐  │
│  │   Network    │ │   Compute    │ │  Task/DAG    │ │    Mobility      │  │
│  │    Model     │ │    Model     │ │    Model     │ │     Model        │  │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────────┘  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                       │
│  │  Scheduler   │ │   Router     │ │   Metrics    │                       │
│  │   (HEFT+)    │ │ (Shortest)   │ │  Collector   │                       │
│  └──────────────┘ └──────────────┘ └──────────────┘                       │
│                            │                                               │
│                            │ State changes                                 │
│                            ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                         viz-bridge                                   │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │  │
│  │  │  Encoder    │  │   Frame     │  │ Connection  │                  │  │
│  │  │ (state→msg) │  │   Buffer    │  │  Manager    │                  │  │
│  │  └─────────────┘  └─────────────┘  └──────┬──────┘                  │  │
│  │                                           │                          │  │
│  │  ┌─────────────────────────────────────────────────────────────┐    │  │
│  │  │              Adapter: iobt-viz                               │    │  │
│  │  │  Translates generic viz commands to iobt-viz protocol        │    │  │
│  │  └─────────────────────────────────────────────────────────────┘    │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ TCP/JSON (port 9999)
                                    │ Step frames + Acks
                                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                              iobt-viz                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ Bridge Server (C#)                                                   │  │
│  │ - TCP listener on port 9999                                          │  │
│  │ - JSON message parsing                                               │  │
│  │ - Command dispatch to renderer                                       │  │
│  │ - Event emission (selections, toggles)                               │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ Renderer                                                             │  │
│  │ - Compute nodes as structures                                        │  │
│  │ - Network links with utilization coloring                            │  │
│  │ - Animated data transfers                                            │  │
│  │ - Task state overlays                                                │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Deployment Configurations

**Configuration A: Full Interactive (Two Monitors)**
```
Monitor 1: iobt-viz (fullscreen battlefield view)
Monitor 2: ncsim-deck (mission control dashboard)
Background: ncsim (simulation engine process)
```

**Configuration B: Development (Single Monitor)**
```
Window 1: iobt-viz (resizable)
Window 2: ncsim-deck (side panel)
Terminal: ncsim with debug logging
```

**Configuration C: Headless Batch**
```
Terminal only: ncsim --headless --scenario batch_experiment.yaml
Output: results.json, metrics.csv
```

**Configuration D: Alternative Visualizer**
```
Any visualizer implementing viz-bridge protocol
ncsim connects via viz-bridge adapter for that visualizer
```

---

## 5. EVOLUTIONARY DEVELOPMENT APPROACH

### 5.1 Core Principle: Incremental Transformation

**iobt-viz is NOT built from scratch.** It evolves from OpenRA through systematic, incremental modifications:

```
OpenRA + OpenRAModSDK
        │
        │  Copy to iobt-viz/
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 1: Working visualization                                  │
│  - Add audio mute option (audio on by default)                  │
│  - Remove fog of war ✓ (already done)                           │
│  - Simplify game lobby                                          │
│  - Modify escape menu options                                   │
│  - Strip production tabs from chrome                            │
│  - Add bridge server skeleton                                   │
│  - ... (many small checkpoints)                                 │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phases 2-5: Add ncsim, viz-bridge, ncsim-deck                  │
│  - iobt-viz continues to evolve in parallel                     │
│  - More chrome simplification                                   │
│  - Bridge becomes fully functional                              │
│  - Remove unused traits gradually                               │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 6: Major cleanup and rename                              │
│  - Remove combat system                                         │
│  - Remove economy system                                        │
│  - Remove unused mods (ra, cnc, d2k, ts)                        │
│  - Rename OpenRA.* → IoBTViz.*                                  │
│  - Streamline build                                             │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
   Clean iobt-viz engine
```

### 5.2 Fine-Grained Checkpoints

**Each phase contains many small, testable steps — NOT one big change.**

Example breakdown for Phase 1 UI simplification:

```
Phase 1, Checkpoint 1.1: Add audio mute option
  - Add mute toggle to settings/UI
  - Audio stays on by default
  - Test: Launch game, verify audio plays, verify mute works
  - Commit: "iobt-viz: add audio mute option"

Phase 1, Checkpoint 1.2: Simplify game lobby  
  - Identify lobby chrome files in reference/
  - Create minimal lobby chrome in iobt-viz/
  - Test: Can still start a game
  - Commit: "iobt-viz: simplify game lobby"

Phase 1, Checkpoint 1.3: Modify escape menu
  - Find ingame menu in chrome/ files
  - Remove "Surrender" option
  - Remove "Diplomacy" option  
  - Keep only: Resume, Settings, Exit
  - Test: Escape menu works with reduced options
  - Commit: "iobt-viz: simplify escape menu"

Phase 1, Checkpoint 1.4: Remove production sidebar
  - Identify production tab chrome
  - Remove from ingame-iobt.yaml
  - Test: Game runs without sidebar
  - Commit: "iobt-viz: remove production sidebar"

... and so on
```

### 5.3 Development Rules

1. **One logical change per commit**
   - Not "Phase 1 complete" — rather "remove diplomacy menu option"
   - Each commit should be independently testable

2. **Test after every change**
   - Does iobt-viz still launch?
   - Does the specific feature work as intended?
   - No regressions in existing functionality?

3. **Consult reference/ before modifying**
   - Understand how OpenRA implements the feature
   - Find all files that need to change
   - Understand dependencies

4. **Document non-obvious changes**
   - Why was this removed?
   - What did it depend on?
   - Add comments in code or docs/

5. **Checkpoint tasks may be discovered during development**
   - The lists in this document are not exhaustive
   - New sub-tasks will emerge — that's expected
   - Add them to the plan as they're discovered

### 5.4 Current State (Already Completed)

Some modifications have already been made to the IoBT mod:

- [x] Fog of war disabled
- [x] Basic IoBT mod structure created
- [x] Initial map setup
- [x] Audio mute option available (inherited from OpenRA common mod)
- [x] Lobby bypassed via auto-start (IoBTMainMenuLogic.cs)
- [x] IoBT-viz branding overlay added (bottom-right)
- [ ] Escape menu simplified (to do)
- [ ] Production sidebar removed (to do)
- [ ] Bridge server skeleton (to do)

### 5.5 Working with the Reference Copies

**When to consult reference/:**

| Situation | Action |
|-----------|--------|
| Need to remove a feature | Search reference/ to find all related files |
| Confused how something works | Read the reference/ implementation |
| Something broke after a change | Diff against reference/ to see what changed |
| Adding new functionality | Check if OpenRA has similar patterns to follow |

**Example workflow:**

```bash
# Want to simplify the escape menu
# Step 1: Find the relevant files in reference
grep -r "Escape" reference/OpenRA/mods/common/chrome/
grep -r "ingame-menu" reference/OpenRA/mods/ra/chrome/

# Step 2: Understand the structure
cat reference/OpenRA/mods/ra/chrome/ingame-player.yaml

# Step 3: Make targeted changes in iobt-viz/
# (only modify what's needed, keep the rest)

# Step 4: Test
cd iobt-viz && make && ./launch-game.sh Game.Mod=iobt

# Step 5: Commit
git add -A && git commit -m "iobt-viz: simplify escape menu"
```

---

## 6. viz-bridge SPECIFICATION

The viz-bridge is the critical decoupling layer. It defines how simulation state becomes visualization commands.

### 6.1 Design Principles

1. **ncsim knows nothing about rendering** — it emits abstract state changes
2. **viz-bridge translates** — converts state changes to visualizer-specific commands  
3. **Adapters are pluggable** — different adapters for different visualizers
4. **Protocol is versioned** — handshake ensures compatibility

### 6.2 Architecture

```
ncsim                      viz-bridge                         iobt-viz
  │                            │                                  │
  │  SimState change           │                                  │
  │  (Python object)           │                                  │
  ├───────────────────────────►│                                  │
  │                            │                                  │
  │                      ┌─────┴─────┐                            │
  │                      │  Encoder  │                            │
  │                      │           │                            │
  │                      │ Converts: │                            │
  │                      │ - NodeCreated → create_entity cmd      │
  │                      │ - FlowStarted → transfer_anim cmd      │
  │                      │ - LinkUtilChanged → update_link cmd    │
  │                      └─────┬─────┘                            │
  │                            │                                  │
  │                      ┌─────┴─────┐                            │
  │                      │  Adapter  │                            │
  │                      │ (iobt-viz)│                            │
  │                      │           │                            │
  │                      │ Translates generic commands to         │
  │                      │ iobt-viz specific format:              │
  │                      │ - entity types → OpenRA actor types    │
  │                      │ - positions → map coordinates          │
  │                      │ - colors → RGB values                  │
  │                      └─────┬─────┘                            │
  │                            │                                  │
  │                      ┌─────┴─────┐                            │
  │                      │  Frame    │                            │
  │                      │  Buffer   │                            │
  │                      │           │                            │
  │                      │ Batches commands into step frames      │
  │                      │ Handles backpressure (max N in-flight) │
  │                      └─────┬─────┘                            │
  │                            │                                  │
  │                            │  JSON over TCP                   │
  │                            ├─────────────────────────────────►│
  │                            │                                  │
  │                            │  Step Ack                        │
  │                            │◄─────────────────────────────────┤
  │                            │                                  │
  │  Backpressure signal       │                                  │
  │◄───────────────────────────┤                                  │
  │                            │                                  │
  │                            │  User interaction event          │
  │                            │◄─────────────────────────────────┤
  │  Event callback            │                                  │
  │◄───────────────────────────┤                                  │
```

### 6.3 Protocol Messages

#### 6.3.1 Handshake
```json
// viz-bridge → iobt-viz (on connect)
{
  "type": "handshake",
  "protocol_version": "1.0",
  "client": "ncsim",
  "client_version": "0.1.0"
}

// iobt-viz → viz-bridge (response)
{
  "type": "handshake_ack",
  "protocol_version": "1.0",
  "server": "iobt-viz",
  "server_version": "0.1.0",
  "capabilities": ["entities", "links", "overlays", "animations"]
}
```

#### 6.3.2 Step Frames
```json
// viz-bridge → iobt-viz
{
  "type": "step_frame",
  "step_id": 42,
  "sim_time": 10.5,
  "commands": [
    {"cmd": "create_entity", "id": "node_0", "entity_type": "compute_node", 
     "position": {"x": 10, "y": 15}, "visual": "comm_tower"},
    {"cmd": "create_link", "id": "link_0_1", "from": "node_0", "to": "node_1",
     "color": "#00FF00"},
    {"cmd": "update_link", "id": "link_0_1", "utilization": 0.75, 
     "color": "#FF8800"},
    {"cmd": "move_entity", "id": "unit_5", "to": {"x": 20, "y": 25}, 
     "duration_sim_sec": 2.0},
    {"cmd": "start_transfer", "id": "xfer_12", "link": "link_0_1",
     "progress": 0.0, "duration_sim_sec": 1.5},
    {"cmd": "task_state", "task_id": "T1", "node_id": "node_0", 
     "state": "running"}
  ]
}

// iobt-viz → viz-bridge
{
  "type": "step_ack",
  "step_id": 42
}
```

**Wire format vs internal objects:**

| Context | Field Name | Access Pattern |
|---------|------------|----------------|
| Wire (JSON on network) | `"cmd"` | `msg["cmd"]` |
| Internal (Python objects) | `.type` | `cmd.type` |

The adapter converts between these:
```python
# Internal Command object → Wire JSON
def command_to_wire(cmd: Command) -> dict:
    return {"cmd": cmd.type, "id": cmd.id, ...}

# Wire JSON → Internal Command object  
def wire_to_command(msg: dict) -> Command:
    return Command(type=msg["cmd"], id=msg["id"], ...)
```

#### 6.3.3 User Interaction Events
```json
// iobt-viz → viz-bridge
{
  "type": "entity_selected",
  "id": "node_0",
  "position": {"x": 10, "y": 15}
}

{
  "type": "overlay_toggled",
  "layer": "network_utilization",
  "enabled": true
}

{
  "type": "user_command",
  "command": "pause"
}
```

#### 6.3.4 Control Messages
```json
// viz-bridge → iobt-viz
{
  "type": "control",
  "command": "reset"  // reset | clear | set_speed
}

{
  "type": "control",
  "command": "set_speed",
  "speed_factor": 2.0
}
```

### 6.4 Adapter Interface

```python
# viz_bridge/adapters/base.py

from abc import ABC, abstractmethod
from typing import Dict, Any, List
from ..protocol import Command, StepFrame

class VisualizerAdapter(ABC):
    """Base class for visualizer-specific adapters."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Adapter name (e.g., 'iobt-viz', 'matplotlib', 'unity')."""
        pass
    
    @abstractmethod
    def translate_entity_type(self, ncsim_type: str) -> str:
        """Map ncsim entity types to visualizer-specific types."""
        pass
    
    @abstractmethod
    def translate_position(self, pos: Dict[str, float]) -> Dict[str, Any]:
        """Convert ncsim coordinates to visualizer coordinates."""
        pass
    
    @abstractmethod
    def translate_color(self, utilization: float) -> str:
        """Map utilization (0-1) to color representation."""
        pass
    
    @abstractmethod
    def encode_step_frame(self, frame: StepFrame) -> bytes:
        """Serialize step frame for transmission."""
        pass
    
    @abstractmethod
    def decode_event(self, data: bytes) -> Dict[str, Any]:
        """Parse incoming event from visualizer."""
        pass
```

```python
# viz_bridge/adapters/iobt_viz.py

from .base import VisualizerAdapter

class IoBTVizAdapter(VisualizerAdapter):
    """Adapter for iobt-viz (OpenRA-derived visualizer)."""
    
    name = "iobt-viz"
    
    # Map ncsim entity types to OpenRA actor types
    ENTITY_TYPE_MAP = {
        "compute_node": "iobt_compute",
        "sensor": "iobt_sensor",
        "relay": "iobt_relay",
        "mobile_unit": "iobt_mobile",
        "base_station": "iobt_basestation",
    }
    
    # Color gradient for utilization (green → yellow → red)
    def translate_color(self, utilization: float) -> str:
        if utilization < 0.5:
            # Green to yellow
            r = int(255 * (utilization * 2))
            g = 255
        else:
            # Yellow to red
            r = 255
            g = int(255 * (1 - (utilization - 0.5) * 2))
        return f"#{r:02X}{g:02X}00"
    
    # ... other implementations
```

### 6.5 Frame Buffer and Backpressure

**Note:** The following code is *illustrative* of the backpressure concept. The actual implementation should be tested thoroughly.

```python
# viz_bridge/frame_buffer.py (illustrative)

import asyncio
from collections import deque
from typing import Optional

class FrameBuffer:
    """Manages step frames with backpressure control.
    
    NOTE: This is illustrative pseudocode. The actual implementation
    needs careful testing of the backpressure logic.
    """
    
    def __init__(self, max_in_flight: int = 5):
        self.max_in_flight = max_in_flight
        self.in_flight: dict = {}  # step_id → frame
        self.next_step_id = 0
        self._can_send = asyncio.Event()
        self._can_send.set()
    
    async def wait_for_capacity(self) -> None:
        """Block until there's capacity to send more frames."""
        while len(self.in_flight) >= self.max_in_flight:
            await self._can_send.wait()
    
    def send_frame(self, frame: StepFrame) -> int:
        """Mark frame as sent, return step_id."""
        step_id = self.next_step_id
        self.next_step_id += 1
        self.in_flight[step_id] = frame
        
        if len(self.in_flight) >= self.max_in_flight:
            self._can_send.clear()
        
        return step_id
    
    def acknowledge(self, step_id: int) -> None:
        """Handle ack, release backpressure if possible."""
        if step_id in self.in_flight:
            del self.in_flight[step_id]
        
        if len(self.in_flight) < self.max_in_flight:
            self._can_send.set()
```

### 6.6 Step Framing Policy

**This section is authoritative.** It defines when and how ncsim emits step frames to the visualizer.

#### Frame Emission Rules

Emit a new step frame when ANY of these conditions is met:

| Condition | Value | Rationale |
|-----------|-------|-----------|
| Δsim_time elapsed | 0.1 seconds | Smooth visual updates (~10 fps equivalent) |
| Event count | 100 events | Prevent event bursts from delaying frames |
| Critical event | Task state change, transfer complete | Immediate feedback on important events |

```python
# Frame emission policy
FRAME_INTERVAL_SIM_SEC = 0.1      # Max sim time between frames
FRAME_MAX_EVENTS = 100            # Max events before forcing frame
CRITICAL_EVENTS = {'task_started', 'task_completed', 'transfer_completed', 'transfer_failed'}

def should_emit_frame(last_frame_time, current_sim_time, events_since_frame, latest_event):
    if current_sim_time - last_frame_time >= FRAME_INTERVAL_SIM_SEC:
        return True
    if events_since_frame >= FRAME_MAX_EVENTS:
        return True
    if latest_event.type in CRITICAL_EVENTS:
        return True
    return False
```

#### Command Coalescing

Within a single frame, coalesce redundant updates:

| Update Type | Coalescing Rule |
|-------------|-----------------|
| `update_link` (same link) | Keep only the last utilization value |
| `move_entity` (same entity) | Keep only the final destination |
| `task_state` (same task) | Keep only the final state |
| `create_entity` | Never coalesce (all creates preserved) |
| `delete_entity` | Never coalesce (all deletes preserved) |

```python
def coalesce_commands(commands: List[Command]) -> List[Command]:
    """Reduce redundant commands within a frame."""
    # Track latest update per entity/link
    link_updates = {}    # link_id → latest update_link command
    entity_moves = {}    # entity_id → latest move_entity command
    task_states = {}     # task_id → latest task_state command
    other_commands = []  # creates, deletes, etc.
    
    for cmd in commands:
        if cmd.type == 'update_link':
            link_updates[cmd.id] = cmd
        elif cmd.type == 'move_entity':
            entity_moves[cmd.id] = cmd
        elif cmd.type == 'task_state':
            task_states[cmd.task_id] = cmd
        else:
            other_commands.append(cmd)
    
    # Reconstruct in deterministic order
    return (other_commands + 
            list(link_updates.values()) + 
            list(entity_moves.values()) + 
            list(task_states.values()))
```

#### Frame Size Limits

| Limit | Value | Behavior if exceeded |
|-------|-------|---------------------|
| Max commands per frame | 500 | Split into multiple frames |
| Max frame size (bytes) | 64 KB | Split into multiple frames |

**Frame splitting semantics:**
- Split frames receive sequential `step_id` values (e.g., 42, 43, 44)
- All split frames share the same `sim_time` (the time when the original frame was generated)
- Visualizer must ack each split frame individually
- Visualizer must apply split frames in `step_id` order
- Backpressure applies to total in-flight frames (including splits)

### 6.7 Wire Protocol: Transport and Framing

**Transport:** TCP (reliable, ordered delivery)

**Default port:** 9999

#### Message Framing

Use **length-prefixed JSON** (not newline-delimited):

```
┌──────────────────┬─────────────────────────────────┐
│  Length (4 bytes)│  JSON payload (UTF-8)           │
│  big-endian uint │                                 │
└──────────────────┴─────────────────────────────────┘
```

```python
import struct
import json

def send_message(sock, message: dict) -> None:
    """Send length-prefixed JSON message."""
    payload = json.dumps(message).encode('utf-8')
    length = struct.pack('>I', len(payload))  # 4-byte big-endian
    sock.sendall(length + payload)

def recv_message(sock) -> dict:
    """Receive length-prefixed JSON message."""
    length_bytes = recv_exact(sock, 4)
    length = struct.unpack('>I', length_bytes)[0]
    
    if length > MAX_MESSAGE_SIZE:
        raise ProtocolError(f"Message too large: {length} bytes")
    
    payload = recv_exact(sock, length)
    return json.loads(payload.decode('utf-8'))
```

#### Protocol Limits

| Limit | Value |
|-------|-------|
| Max message size | 1 MB (1,048,576 bytes) |
| Connection timeout | 30 seconds |
| Heartbeat interval | 5 seconds (if no traffic) |

#### Reconnection Semantics

**On disconnect:**

1. iobt-viz shows "DISCONNECTED" overlay
2. iobt-viz freezes visualization (no time advance)
3. iobt-viz listens for new connection

**On reconnect:**

1. Client (viz-bridge) initiates new connection
2. Full handshake required
3. Client sends `{"type": "reconnect", "last_acked_step": N}`
4. Server (iobt-viz) responds with `{"type": "reconnect_ack", "reset": true|false}`
5. If `reset: true`, client must resend full state
6. If `reset: false`, client resumes from step N+1

**Idempotency:**

- Step frames with already-acked step_ids are silently ignored
- Entity creates for existing IDs are treated as updates
- Entity deletes for non-existent IDs are silently ignored

### 6.8 Interactive Command Preservation (OpenRA Mouse UX → ncsim Topology Events)

#### Goal

Preserve iobt-viz's most compelling demo property (inherited from OpenRA): the user can select units and issue mouse-driven commands (e.g., move by right-click) while the DAG workload is continuously deployed and executing. The simulator shows live execution status and performance metrics while the user reconfigures the network topology by repositioning "troops" (mobile nodes).

#### Design Principle

| Component | Role |
|-----------|------|
| **iobt-viz (OpenRA)** | Interactive front-end: selection, right-click, command issuance, animation |
| **ncsim** | Authoritative back-end: topology/state/time ownership, action validation, movement timing, link quality, scheduling |
| **viz-bridge** | Transports "user intents" (iobt-viz → ncsim) and authoritative state deltas (ncsim → iobt-viz) |

#### External User Intent Events

iobt-viz MUST emit an event when the user issues a command via the OpenRA UI (mouse/keyboard). 

**Implementation note for coding agent:** The precise format emitted by OpenRA/mod hooks MUST be confirmed (OpenRA order system / mod API / Lua bindings). If OpenRA's native emitted payload differs from the canonical schema below, viz-bridge shall include a translator that maps OpenRA-native payload → canonical schema.

#### Canonical Schema: `user_intent`

All user-driven actions are represented as a `user_intent` message from iobt-viz → viz-bridge → ncsim:

```json
{
  "type": "user_intent",
  "client_time_ms": 1730000123456,
  "intent_id": "u-000001",
  "intent_kind": "MOVE",
  "selection": {
    "entity_ids": ["unit_5"]
  },
  "payload": {
    "destination": {"x": 20, "y": 25}
  }
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Fixed: `"user_intent"` |
| `client_time_ms` | int | Wall-clock time at client (debugging/telemetry only, NOT used in sim_time) |
| `intent_id` | string | Unique per client session (monotonic or UUID). Used for idempotency and tracing |
| `intent_kind` | string | One of the intent kinds below |
| `selection.entity_ids` | string[] | Entities the user is commanding (from OpenRA selection) |
| `payload` | object | Intent-specific payload |

#### v1 Intent Kinds

**MOVE** — User right-clicks a destination after selecting mobile entities
```json
{
  "intent_kind": "MOVE",
  "selection": {"entity_ids": ["unit_5", "unit_7"]},
  "payload": {"destination": {"x": 20, "y": 25}}
}
```

**STOP** — User cancels movement / issues stop
```json
{
  "intent_kind": "STOP",
  "selection": {"entity_ids": ["unit_5"]},
  "payload": {}
}
```

**TOGGLE_ROLE** (optional, great for demos) — User toggles a unit role
```json
{
  "intent_kind": "TOGGLE_ROLE",
  "selection": {"entity_ids": ["unit_5"]},
  "payload": {"role": "relay", "enabled": true}
}
```

**SET_POWER_MODE** (optional) — Impacts comm range/capacity
```json
{
  "intent_kind": "SET_POWER_MODE",
  "selection": {"entity_ids": ["unit_5"]},
  "payload": {"power_mode": "HIGH"}
}
```

#### ncsim Handling of User Intents

ncsim receives `user_intent` messages via viz-bridge inbound channel and processes them as external events.

**Processing steps:**
1. Validate that `selection.entity_ids` exist and are controllable
2. Validate destination/payload is within allowed bounds
3. Translate accepted intents into simulation events (movement, role toggles, power changes)
4. Emit acknowledgements (for UI feedback) and step-frame updates (for visualization)

#### Canonical Response: `intent_ack`

ncsim → viz-bridge → iobt-viz:

```json
{
  "type": "intent_ack",
  "intent_id": "u-000001",
  "accepted": true,
  "reason": null,
  "assigned_action_ids": ["move-000142"]
}
```

If rejected:
```json
{
  "type": "intent_ack",
  "intent_id": "u-000001",
  "accepted": false,
  "reason": "Entity unit_5 is not mobile",
  "assigned_action_ids": []
}
```

#### Movement Semantics (Authoritative)

For `MOVE` intents, ncsim schedules movement in sim_time. Two supported modes:

**Mode A (recommended default): ncsim Authoritative Movement Timing**
- ncsim computes travel time from current position → destination using deterministic model (constant speed, optionally Manhattan distance)
- ncsim emits `move_entity` commands in step frames (start + end or intermediate waypoints)
- iobt-viz animates accordingly
- **Preserves interactive mouse control while keeping experiments reproducible**

**Mode B (optional demo mode): Viz Pathfinding Feedback**
- iobt-viz computes travel_time/path based on OpenRA world (terrain, obstacles)
- iobt-viz reports back via `movement_feedback` event
- ncsim reschedules move completion event based on feedback (per §10.8 event rescheduling rules)
- **⚠️ NOT guaranteed reproducible across builds; use for demos only**

#### Movement Feedback Events (Mode B Only)

If Mode B is enabled, iobt-viz MUST send feedback:

**ETA update:**
```json
{
  "type": "movement_feedback",
  "intent_id": "u-000001",
  "action_id": "move-000142",
  "entity_id": "unit_5",
  "feedback_kind": "ETA",
  "payload": {
    "travel_time_sim_sec": 3.2
  }
}
```

**Arrival notification:**
```json
{
  "type": "movement_feedback",
  "intent_id": "u-000001",
  "action_id": "move-000142",
  "entity_id": "unit_5",
  "feedback_kind": "ARRIVED",
  "payload": {
    "final_position": {"x": 20, "y": 25}
  }
}
```

#### How Topology Changes Affect Running DAGs

When a move (or role/power toggle) changes node positions or capabilities, ncsim MUST:

1. **Update node state** (position, comm range, compute capacity, etc.)
2. **Recompute affected links** (bandwidth/latency/reliability) per §11.3 network model
3. **Trigger `TaskMapper.on_network_change(snapshot)`** if the scheduler supports adaptive re-mapping
4. **Emit step-frame updates** reflecting:
   - Moved entity position (`move_entity`)
   - Updated link qualities and/or link up/down events (`update_link`, `delete_link`, `create_link`)
   - Transfer rate changes (per §11.3.1 dynamic transfer update rules)
   - Any resulting task/transfer state transitions (`task_state`)

#### Coordinate System Requirements

OpenRA uses its own coordinate system. iobt-viz MUST standardize coordinates:

| Option | Format | Notes |
|--------|--------|-------|
| Tile coordinates | `{x_tile, y_tile}` | Integer grid positions |
| World coordinates | `{x_world, y_world}` | Sub-tile precision |

**The choice must be stated and used consistently in:**
- Scenario YAML node positions
- `user_intent.payload.destination`
- All `move_entity` / `create_entity` / entity position messages

If conversion is needed, it MUST happen in viz-bridge with documented mapping.

#### What the Coding Agent Must Confirm About OpenRA

The coding agent MUST determine how OpenRA provides access to:

| Capability | OpenRA Mechanism (to be confirmed) |
|------------|-----------------------------------|
| Selected entities at command time | Selection system / trait |
| Right-click move orders (destination) | Order system / `MoveOrderGenerator` |
| Stop/cancel orders | Order system |
| Event emission hooks | Trait hooks, Lua bindings, order-queue instrumentation |

If OpenRA's native payload differs substantially from the canonical schema, the coding agent MUST implement a translator in iobt-viz or viz-bridge.

#### Hero Demo Scenario

The "killer demo" that showcases interactive topology reconfiguration:

```yaml
# scenarios/interactive_relay_demo.yaml
scenario:
  name: "Interactive Relay Network"
  description: "User repositions relay troops to optimize DAG throughput"
  
  config:
    interactive_mode: true
    movement_mode: A  # ncsim authoritative (reproducible)
    
  # Continuous DAG arrival
  dag_source:
    type: poisson
    arrival_rate: 0.5  # DAGs per second
    dag_template: sensor_fusion_dag
    
  nodes:
    # Fixed compute nodes at corners
    - {id: base_0, type: compute, position: {x: 5, y: 5}, mobile: false}
    - {id: base_1, type: compute, position: {x: 45, y: 5}, mobile: false}
    - {id: base_2, type: compute, position: {x: 25, y: 45}, mobile: false}
    
    # Mobile relay troops - user can reposition these!
    - {id: relay_0, type: relay, position: {x: 15, y: 15}, mobile: true, 
       movement_speed: 5.0, comm_range: 20}
    - {id: relay_1, type: relay, position: {x: 35, y: 15}, mobile: true,
       movement_speed: 5.0, comm_range: 20}
    - {id: relay_2, type: relay, position: {x: 25, y: 30}, mobile: true,
       movement_speed: 5.0, comm_range: 20}

  # Initial links computed from positions + comm_range
  links: auto_from_range
  
  viz_overlays:
    - link_utilization_heatmap
    - task_state_indicators
    - comm_range_circles
```

**Demo flow:**
1. DAGs arrive continuously (Poisson)
2. User sees live task execution status and link utilization heatmap
3. User selects relay troops and right-click moves them
4. Links dynamically form/break based on comm_range
5. ncsim-deck shows real-time: throughput trend, queue lengths, makespan distribution
6. User discovers optimal relay positions through interactive exploration

---

## 7. CRITICAL DESIGN PRINCIPLES

### 7.1 Separation of Concerns (MANDATORY)

| Component | Owns | Does NOT Own |
|-----------|------|--------------|
| **ncsim** | Time, state, causality, scheduling, routing | Graphics, animation, UI |
| **viz-bridge** | Protocol translation, buffering, adapters | Simulation logic, rendering |
| **iobt-viz** | Rendering, animation, user input capture | Scheduling, time advancement |
| **ncsim-deck** | Scenario orchestration, dashboards | State truth, rendering, simulation |

**Rule**: ncsim must be fully functional without any visualizer. iobt-viz must work with any viz-bridge client.

### 7.2 Timing Model (CRITICAL)

#### Single Authoritative Time
- **ncsim** is the sole authority for `sim_time`
- iobt-viz frame rate does not affect simulation outcomes
- viz-bridge handles time-to-animation translation

#### Time Concepts
```
sim_time     = timeline of the modeled system (seconds)
wall_time    = real time observed by the user (seconds)
speed_factor = sim_time advancement per wall_time
  S = 0    → paused
  S = 1    → real-time (1 sim second = 1 wall second)
  S = 5    → 5x faster
  S = inf  → as fast as possible (batch mode)
```

#### Step Framing Protocol
```
Step k covers [t_k, t_{k+1}] in sim_time

ncsim                 viz-bridge              iobt-viz
  │                       │                       │
  │──State changes───────►│                       │
  │                       │──Step k frame────────►│
  │                       │                       │
  │                       │◄─────Step k ack───────│
  │◄──Ack propagated──────│                       │
  │                       │                       │
  │──More state changes──►│                       │
  │                       │──Step k+1 frame──────►│

Constraints:
- Ordered delivery (steps applied in sequence)
- Backpressure (max N unacknowledged steps in flight)
- Determinism (same seed + inputs = same step sequence)
```

### 7.3 Headless Mode

ncsim must support running without visualization:

```bash
# Run batch experiment
ncsim --headless --scenario experiment.yaml --output results/

# Run with different scheduler
ncsim --headless --scheduler greedy --scenario experiment.yaml

# Run multiple seeds
for seed in {1..100}; do
  ncsim --headless --seed $seed --scenario experiment.yaml --output results/run_$seed/
done
```

In headless mode:
- viz-bridge is not initialized
- Simulation runs at maximum speed
- Metrics are collected and written to files
- No step framing or backpressure

---

## 8. NCSIM-DECK CONTROL PROTOCOL

This section defines the control-plane protocol between ncsim-deck (the dashboard/control app) and ncsim (the simulation engine).

### 8.1 Overview

```
┌─────────────────┐                    ┌─────────────────┐
│   ncsim-deck    │◄──── Control ─────►│     ncsim       │
│                 │      Protocol      │                 │
│  - UI/Dashboard │                    │  - Simulation   │
│  - Scenario mgmt│◄──── Metrics ──────│  - Scheduler    │
│  - Controls     │      Stream        │  - Metrics      │
└─────────────────┘                    └─────────────────┘
```

**Transport:** TCP (port 9998)

*Future option: WebSocket (ws://localhost:9998) for browser-based dashboards*

**Protocol:** JSON-RPC 2.0 style (request/response + notifications)

### 8.2 Connection Lifecycle

```
1. ncsim starts, listens on port 9998
2. ncsim-deck connects
3. Handshake exchange
4. ncsim-deck subscribes to metrics streams
5. ncsim-deck sends commands (load, start, pause, etc.)
6. ncsim sends metrics updates and event notifications
7. Disconnect (graceful or timeout)
```

### 8.3 Message Format

**Request (deck → ncsim):**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "start",
  "params": {"speed_factor": 1.0}
}
```

**Response (ncsim → deck):**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {"status": "running", "sim_time": 0.0}
}
```

**Notification (ncsim → deck, no response expected):**
```json
{
  "jsonrpc": "2.0",
  "method": "metrics_update",
  "params": {"sim_time": 10.5, "makespan": null, "utilization": {...}}
}
```

### 8.4 Control Commands

#### Session Management

| Method | Params | Response | Description |
|--------|--------|----------|-------------|
| `handshake` | `{client: str, version: str}` | `{server: str, version: str, capabilities: [...]}` | Initial connection |
| `get_status` | `{}` | `{state: str, sim_time: float, ...}` | Current simulation state |

#### Scenario Management

| Method | Params | Response | Description |
|--------|--------|----------|-------------|
| `load_scenario` | `{path: str}` or `{scenario: {...}}` | `{run_id: str, scenario_name: str}` | Load scenario from file or inline |
| `get_scenario` | `{}` | `{scenario: {...}}` | Get currently loaded scenario |
| `list_scenarios` | `{directory: str}` | `{scenarios: [...]}` | List available scenarios |

#### Simulation Control

| Method | Params | Response | Description |
|--------|--------|----------|-------------|
| `start` | `{speed_factor?: float}` | `{status: "running"}` | Start or resume simulation |
| `pause` | `{}` | `{status: "paused", sim_time: float}` | Pause simulation |
| `reset` | `{}` | `{status: "ready"}` | Reset to initial state |
| `step` | `{count?: int}` | `{status: str, sim_time: float, events: int}` | Advance N events (default 1) |
| `set_speed` | `{speed_factor: float}` | `{speed_factor: float}` | Change simulation speed |
| `stop` | `{}` | `{status: "stopped", results: {...}}` | Stop and finalize |

#### Metrics Subscription

| Method | Params | Response | Description |
|--------|--------|----------|-------------|
| `subscribe` | `{channels: [str]}` | `{subscribed: [str]}` | Subscribe to metrics channels |
| `unsubscribe` | `{channels: [str]}` | `{unsubscribed: [str]}` | Unsubscribe from channels |

**Available channels:**
- `utilization` — Per-link utilization updates
- `queues` — Per-node queue length updates  
- `tasks` — Task state changes
- `makespan` — Current makespan estimate
- `events` — Raw simulation events (verbose)

### 8.5 Metrics Notifications

**Utilization update:**
```json
{
  "jsonrpc": "2.0",
  "method": "metrics.utilization",
  "params": {
    "sim_time": 10.5,
    "links": {
      "link_0_1": 0.75,
      "link_1_2": 0.30
    }
  }
}
```

**Queue length update:**
```json
{
  "jsonrpc": "2.0",
  "method": "metrics.queues",
  "params": {
    "sim_time": 10.5,
    "nodes": {
      "node_0": 3,
      "node_1": 0
    }
  }
}
```

**Task state change:**
```json
{
  "jsonrpc": "2.0",
  "method": "metrics.task",
  "params": {
    "sim_time": 10.5,
    "task_id": "T1",
    "state": "running",
    "node_id": "node_0"
  }
}
```

**Makespan update:**
```json
{
  "jsonrpc": "2.0",
  "method": "metrics.makespan",
  "params": {
    "sim_time": 10.5,
    "completed_dags": 0,
    "estimated_makespan": 25.3
  }
}
```

### 8.6 Error Handling

**Error response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32600,
    "message": "Invalid scenario",
    "data": {"path": "/bad/path.yaml", "reason": "File not found"}
  }
}
```

**Error codes:**
| Code | Meaning |
|------|---------|
| -32700 | Parse error |
| -32600 | Invalid request |
| -32601 | Method not found |
| -32602 | Invalid params |
| -32000 | Simulation error (custom) |
| -32001 | Scenario error (custom) |

### 8.7 Metrics Update Frequency

| Channel | Update Frequency | Notes |
|---------|-----------------|-------|
| `utilization` | Every 0.1 sim_sec or on change > 5% | Coalesced |
| `queues` | Every 0.1 sim_sec or on change | Coalesced |
| `tasks` | On every state change | Not coalesced |
| `makespan` | Every 1.0 sim_sec | Low frequency |
| `events` | Every event | High volume, use carefully |

---

## 9. DATA MODELS

### 9.1 Network Model
```yaml
# scenarios/network.yaml
network:
  nodes:
    - id: node_0
      type: edge_compute
      compute_capacity: 100    # abstract compute units
      position: {x: 10, y: 15}
      energy_limit: null       # optional
      
    - id: node_1
      type: sensor
      compute_capacity: 10
      position: {x: 25, y: 20}
      
  links:
    - id: link_0_1
      from: node_0
      to: node_1
      bandwidth: 1000          # Mbps
      latency: 5               # ms
      reliability: 0.99        # optional, default 1.0
```

### 9.2 Task DAG Model
```yaml
# scenarios/dag.yaml
dag:
  id: mission_alpha
  tasks:
    - id: T0
      compute_cost: 50
      pinned_to: node_1        # sensor task, fixed location
      
    - id: T1
      compute_cost: 100
      # not pinned, scheduler decides placement
      
    - id: T2
      compute_cost: 75
      
  edges:
    - from: T0
      to: T1
      data_size: 500           # MB, induces network transfer
      
    - from: T1
      to: T2
      data_size: 200
```

### 9.3 Scenario File
```yaml
# scenarios/demo_bottleneck.yaml
scenario:
  name: "Bottleneck Demo"
  description: "Demonstrates scheduling around a network bottleneck"
  
  network:
    # inline or reference: !include network.yaml
    nodes:
      - {id: n0, type: edge_compute, compute_capacity: 100, position: {x: 10, y: 10}}
      - {id: n1, type: edge_compute, compute_capacity: 50, position: {x: 30, y: 10}}
      - {id: n2, type: sensor, compute_capacity: 10, position: {x: 20, y: 30}}
    links:
      - {id: l01, from: n0, to: n1, bandwidth: 1000, latency: 2}
      - {id: l02, from: n0, to: n2, bandwidth: 100, latency: 10}  # bottleneck!
      - {id: l12, from: n1, to: n2, bandwidth: 500, latency: 5}
  
  dags:
    - id: dag_1
      inject_at: 0.0           # sim_time to inject
      tasks:
        - {id: T0, compute_cost: 20, pinned_to: n2}
        - {id: T1, compute_cost: 80}
        - {id: T2, compute_cost: 40}
      edges:
        - {from: T0, to: T1, data_size: 200}
        - {from: T1, to: T2, data_size: 100}
  
  config:
    scheduler: heft
    router: shortest_path
    duration: 30.0             # sim_time to run
    seed: 42                   # deterministic random seed
    
  visualization:
    initial_overlays: [network_links, task_states]
    camera_focus: {x: 20, y: 20}
```

---

## 10. NCSIM ARCHITECTURE

ncsim is a **research platform** for developing and evaluating task scheduling algorithms on dynamic mobile networks. The architecture must support a wide range of scheduler implementations while providing robust infrastructure for execution simulation, state observation, and metrics collection.

### 10.1 Core Design Philosophy

**ncsim provides infrastructure; researchers provide scheduling policy.**

| ncsim Provides | Researchers Implement |
|----------------|----------------------|
| DAG injection and lifecycle | Scheduling/placement algorithms |
| Network state observation | Rescheduling policies |
| Execution timing simulation | Failure recovery strategies |
| Metrics collection and logging | Optimization objectives |
| Viz feedback integration | Distributed coordination |

The architecture must be **policy-agnostic** — it should not constrain what scheduling strategies are possible.

### 10.2 Two-Level Scheduling Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           TASK MAPPER                                    │
│                    (Pluggable, Researcher-Implemented)                   │
│                                                                          │
│  Inputs:                         Outputs:                                │
│  - Pending DAGs                  - Placement plan (task → node)          │
│  - Network state snapshot        - Execution order                       │
│  - Running tasks                 - (Optional) Estimated completion       │
│  - Node states & queues                                                  │
│                                                                          │
│  Examples: HEFT, CPOP, SMT, custom heuristics, RL-based, distributed    │
└─────────────────────────────────────┬───────────────────────────────────┘
                                      │ Placement Plan
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        EXECUTION ENGINE                                  │
│                    (ncsim Core, DES-based)                              │
│                                                                          │
│  - Follows placement plan                                                │
│  - Computes ACTUAL timing dynamically based on:                         │
│    • Current network conditions (bandwidth, latency)                    │
│    • Node compute capacity and queue state                              │
│    • Concurrent transfers (bandwidth sharing)                           │
│  - Logs all execution events with timestamps                            │
│  - Reports state changes back to Task Mapper (if rescheduling)          │
│  - Handles timeouts and failure logging                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

**Key principle:** The Task Mapper decides WHERE and WHEN (planned). The Execution Engine simulates WHAT ACTUALLY HAPPENS given dynamic conditions.

### 10.3 Scheduler Interface (Task Mapper)

**Terminology note:**
| This Spec | Also Known As | Description |
|-----------|---------------|-------------|
| **Task Mapper** | Offline Scheduler, Scheduler (SAGA) | Computes placement plan given current state |
| **Execution Engine** | Online Scheduler, Runtime | Executes plan with dynamic timing |

SAGA and most scheduling literature call the task mapping phase "scheduling". We use "Task Mapper" to distinguish it from the runtime execution, but the interfaces are compatible. **SAGA schedulers implement the Task Mapper interface.**

The Task Mapper is a **pluggable component**. ncsim provides a base interface; researchers implement scheduling logic.

**Pinned task enforcement:**
Tasks with `pinned_to` constraints flow through the system as follows:
1. **Scenario**: Task specifies `pinned_to: node_id`
2. **Task Mapper**: Must respect constraint (SAGA adapters pass this through)
3. **Execution Engine**: Validates assignment matches constraint, logs error if violated

```python
# ncsim/scheduler/base.py

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class PlacementPlan:
    """Output of Task Mapper: where tasks should run."""
    assignments: Dict[str, str]      # task_id → node_id
    execution_order: List[str]       # task_ids in planned order
    estimated_makespan: Optional[float] = None

@dataclass 
class NetworkSnapshot:
    """Current network state available to Task Mapper."""
    nodes: Dict[str, 'NodeState']    # node_id → state
    links: Dict[str, 'LinkState']    # link_id → state
    timestamp: float                  # sim_time of snapshot
    
@dataclass
class NodeState:
    node_id: str
    position: tuple                   # (x, y)
    compute_capacity: float
    current_task: Optional[str]       # task currently executing
    queue: List[str]                  # tasks waiting
    utilization: float                # 0.0 - 1.0

@dataclass
class LinkState:
    link_id: str
    from_node: str
    to_node: str
    bandwidth: float                  # current effective bandwidth
    latency: float
    active_transfers: int             # concurrent flows
    utilization: float                # 0.0 - 1.0

class TaskMapper(ABC):
    """
    Base interface for task mapping/scheduling algorithms.
    
    Also known as: Scheduler (SAGA), Offline Scheduler.
    
    Researchers implement this to create custom schedulers.
    ncsim provides the infrastructure; this provides the policy.
    SAGA schedulers are wrapped to implement this interface.
    """
    
    @abstractmethod
    def compute_placement(
        self,
        dags: List['DAG'],
        network: NetworkSnapshot,
        running_tasks: Dict[str, 'TaskExecution'],
        config: Dict
    ) -> PlacementPlan:
        """
        Compute task-to-node assignments.
        
        Called when:
        - New DAG is injected
        - Reschedule is requested (policy-dependent)
        - Network state changes significantly (policy-dependent)
        
        Args:
            dags: All pending DAGs (may include partially-executed ones)
            network: Current network state snapshot
            running_tasks: Currently executing tasks with progress
            config: Scheduler-specific configuration
            
        Returns:
            PlacementPlan with assignments and execution order
        """
        pass
    
    def on_task_completed(self, task_id: str, actual_time: float) -> Optional[PlacementPlan]:
        """
        Hook called when a task completes.
        
        Override to implement dynamic rescheduling.
        Return new PlacementPlan to reschedule, or None to continue.
        """
        return None
    
    def on_transfer_completed(self, transfer_id: str, actual_time: float) -> Optional[PlacementPlan]:
        """Hook called when a data transfer completes."""
        return None
    
    def on_transfer_failed(self, transfer: 'Transfer', reason: str) -> Optional[PlacementPlan]:
        """
        Hook called when a data transfer fails (after retries exhausted).
        
        Override to implement custom failure recovery strategies.
        Used when failure_outcome='notify_mapper' in config.
        
        Args:
            transfer: The failed transfer details
            reason: Failure reason (e.g., 'link_broken', 'retries_exhausted')
            
        Returns:
            New PlacementPlan to reschedule affected tasks, or None
        """
        return None
    
    def on_network_change(self, change: 'NetworkChange') -> Optional[PlacementPlan]:
        """
        Hook called when network topology/quality changes.
        
        Override to implement adaptive rescheduling based on mobility.
        """
        return None
    
    def on_timeout(self, dag_id: str) -> Optional[PlacementPlan]:
        """
        Hook called when a DAG times out.
        
        Override to implement recovery/retry strategies.
        """
        return None
```

### 10.4 DAG Injection Modes

DAGs can be injected into ncsim in multiple ways:

**Mode 1: Upfront Specification (Batch)**
```yaml
# All DAGs specified in scenario file with injection times
scenario:
  dags:
    - id: dag_1
      inject_at: 0.0      # Available immediately
      timeout: 30.0       # Must complete within 30 sim_sec
      tasks: [...]
      
    - id: dag_2
      inject_at: 10.0     # Available at t=10
      timeout: 25.0
      tasks: [...]
      
    - id: dag_3
      inject_at: 15.5     # Available at t=15.5
      timeout: 20.0
      tasks: [...]
```

**Mode 2: Programmatic Injection (Dynamic)**
```python
# Inject DAGs at runtime (for interactive or external triggers)
sim = Simulation(scenario)

# Inject immediately
sim.inject_dag(dag, timeout=30.0)

# Schedule future injection
sim.schedule_dag_injection(dag, inject_at=10.0, timeout=25.0)

# External trigger (e.g., from ncsim-deck or external process)
@sim.on_external_event('new_mission')
def handle_mission(event):
    dag = build_dag_from_mission(event.data)
    sim.inject_dag(dag, timeout=event.data.get('deadline'))
```

**Mode 3: Continuous Generation (Workload Model)**
```python
# Stochastic DAG arrival process
class PoissonDAGSource:
    def __init__(self, rate: float, dag_generator: Callable):
        self.rate = rate  # arrivals per sim_second
        self.generator = dag_generator
    
    def next_arrival(self, current_time: float) -> Tuple[float, DAG]:
        inter_arrival = random.exponential(1.0 / self.rate)
        return (current_time + inter_arrival, self.generator())

sim.add_dag_source(PoissonDAGSource(rate=0.5, dag_generator=random_dag))
```

### 10.5 Execution Engine Internals

The Execution Engine is a discrete-event simulation that computes actual execution times.

```
┌──────────────────────────────────────────────────────────────────┐
│                      EXECUTION ENGINE                             │
│                                                                   │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐        │
│  │ Event Queue │────►│   Clock     │────►│  Executor   │        │
│  │  (heapq)    │     │ (sim_time)  │     │             │        │
│  └─────────────┘     └─────────────┘     └──────┬──────┘        │
│         ▲                                        │               │
│         │                                        ▼               │
│         │            ┌───────────────────────────────────┐      │
│         │            │         Event Handlers            │      │
│         │            │  ┌─────────┐ ┌─────────┐ ┌─────┐ │      │
│         └────────────│  │DAG_INJECT│ │TASK_START│ │ ... │ │      │
│      (new events)    │  └─────────┘ └─────────┘ └─────┘ │      │
│                      └───────────────────────────────────┘      │
│                                       │                          │
│                                       ▼                          │
│                      ┌───────────────────────────────────┐      │
│                      │        State Managers             │      │
│                      │  ┌────────┐ ┌────────┐ ┌───────┐ │      │
│                      │  │Network │ │ Nodes  │ │ DAGs  │ │      │
│                      │  │ State  │ │ State  │ │ State │ │      │
│                      │  └────────┘ └────────┘ └───────┘ │      │
│                      └───────────────────────────────────┘      │
│                                       │                          │
│                                       ▼                          │
│                      ┌───────────────────────────────────┐      │
│                      │      Metrics & Trace Logger       │      │
│                      └───────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────────┘
```

**Event Types:**

| Event | Trigger | Action |
|-------|---------|--------|
| `DAG_INJECT` | Scheduled injection time | Add DAG to pending, invoke Task Mapper |
| `TASK_START` | Node available + dependencies met | Begin execution, schedule TASK_COMPLETE |
| `TASK_COMPLETE` | Execution time elapsed | Mark complete, start successor transfers |
| `TRANSFER_START` | Task complete + link available | Begin transfer, schedule TRANSFER_COMPLETE |
| `TRANSFER_COMPLETE` | Transfer time elapsed | Mark data available, check task readiness |
| `NODE_MOVE` | Mobility tick | Update position, recompute link states |
| `LINK_CHANGE` | Position change | Update bandwidth/latency, notify mapper |
| `DAG_TIMEOUT` | Deadline exceeded | Log failure, invoke mapper hook |
| `RESCHEDULE` | Mapper requests | Re-plan pending tasks |

### 10.6 Dynamic Network State

Network state is continuously updated and always available to the Task Mapper.

```python
class NetworkStateManager:
    """Maintains current network state, updated by events."""
    
    def __init__(self, network_config: NetworkConfig):
        self.nodes: Dict[str, NodeState] = {}
        self.links: Dict[str, LinkState] = {}
        self._initialize(network_config)
    
    def get_snapshot(self) -> NetworkSnapshot:
        """
        Get current network state.
        
        Called by Task Mapper at any time.
        Thread-safe, returns immutable snapshot.
        """
        return NetworkSnapshot(
            nodes=copy.deepcopy(self.nodes),
            links=copy.deepcopy(self.links),
            timestamp=self.current_time
        )
    
    def update_node_position(self, node_id: str, position: tuple) -> List[LinkChange]:
        """
        Update node position, recompute affected links.
        
        Returns list of link changes for notification.
        """
        self.nodes[node_id].position = position
        changes = []
        for link in self._links_involving(node_id):
            old_state = copy.copy(link)
            self._recompute_link_quality(link)
            if self._significant_change(old_state, link):
                changes.append(LinkChange(link_id=link.link_id, old=old_state, new=link))
        return changes
    
    def update_link_utilization(self, link_id: str, active_transfers: int):
        """Update link state when transfers start/complete."""
        link = self.links[link_id]
        link.active_transfers = active_transfers
        link.utilization = self._compute_utilization(link)
```

### 10.7 Transfer Time Computation

Transfer times are computed **dynamically** based on current conditions and **updated** as conditions change.

```python
class TransferManager:
    """Manages data transfers with dynamic timing."""
    
    def start_transfer(self, transfer: Transfer) -> float:
        """
        Start a transfer, compute initial completion time.
        
        Returns estimated completion time (may be updated later).
        """
        route = self.routing.compute_route(transfer.from_node, transfer.to_node)
        
        # Get current link states
        bottleneck_bw = min(
            self.network.links[link_id].bandwidth / 
            (self.network.links[link_id].active_transfers + 1)
            for link_id in route.links
        )
        total_latency = sum(
            self.network.links[link_id].latency 
            for link_id in route.links
        )
        
        # Compute time
        transfer_time = (transfer.data_size_mb * 8) / bottleneck_bw + total_latency / 1000
        
        # Record transfer state (for updates if conditions change)
        self.active_transfers[transfer.id] = ActiveTransfer(
            transfer=transfer,
            route=route,
            start_time=self.sim_time,
            bytes_sent=0,
            estimated_completion=self.sim_time + transfer_time
        )
        
        return self.sim_time + transfer_time
    
    def on_network_change(self, link_id: str) -> List[TransferUpdate]:
        """
        Called when link conditions change.
        
        Recomputes completion times for affected transfers.
        Returns list of updated completion times.
        """
        updates = []
        for active in self.active_transfers.values():
            if link_id in active.route.links:
                # Compute progress so far
                elapsed = self.sim_time - active.start_time
                progress = self._estimate_progress(active, elapsed)
                
                # Recompute remaining time with new conditions
                remaining = self._compute_remaining_time(active, progress)
                new_completion = self.sim_time + remaining
                
                if new_completion != active.estimated_completion:
                    active.estimated_completion = new_completion
                    updates.append(TransferUpdate(
                        transfer_id=active.transfer.id,
                        new_completion=new_completion
                    ))
        
        return updates
```

### 10.8 Viz Feedback Integration

ncsim supports two modes of movement/pathfinding:

**Mode A: ncsim Authoritative (Headless) — DEFAULT**
- ncsim computes movement with simplified model
- Used when running without visualization
- Faster, fully deterministic, reproducible

**Mode B: Viz Feedback (Connected) — EXPERIMENTAL / DEMO REALISM**
- ncsim sends movement intent to iobt-viz
- iobt-viz computes actual travel time (terrain, pathfinding, obstacles)
- iobt-viz reports completion via viz-bridge
- ncsim **reschedules events** based on reported times

**⚠️ Mode B Warning:** Unless iobt-viz pathfinding is deterministic across machines and OpenRA versions, Mode B results may not be reproducible. Use Mode A for research publications; Mode B for demos and exploration.

```
MODE A (Headless):
┌─────────┐                      
│  ncsim  │ ── movement model ──► state update
└─────────┘                      

MODE B (Connected):
┌─────────┐         ┌──────────┐         ┌─────────┐
│  ncsim  │──intent─►│viz-bridge│──move───►│iobt-viz │
└─────────┘         └──────────┘         └────┬────┘
     ▲                    ▲                   │
     │                    │                   │
     └──event reschedule──┴───travel_time─────┘
```

**Critical invariant: ncsim ALWAYS owns sim_time.**

Viz feedback works via **event rescheduling**, NOT time adjustment:

1. ncsim schedules a `MOVE_COMPLETE` event at estimated arrival time
2. ncsim sends movement intent to viz
3. Viz computes actual travel and reports `travel_time` for the `move_id`
4. ncsim receives report BEFORE the estimated `MOVE_COMPLETE` fires
5. ncsim **reschedules** the `MOVE_COMPLETE` event to the reported arrival time
6. When `MOVE_COMPLETE` fires, ncsim updates node position and link qualities

**Implementation:**

```python
@dataclass
class PendingMove:
    """Tracks a movement awaiting viz feedback."""
    move_id: str
    node_id: str
    destination: tuple
    start_time: float           # sim_time when move initiated
    estimated_arrival: float
    event_handle: int           # For rescheduling

class MovementManager:
    """Handles node movement with optional viz feedback."""
    
    def __init__(self, mode: str = 'headless'):
        self.mode = mode  # 'headless' or 'viz_feedback'
        self.pending_moves: Dict[str, PendingMove] = {}
    
    def move_node(self, node_id: str, destination: tuple) -> float:
        """
        Initiate node movement.
        
        Returns estimated arrival time (may be rescheduled in viz_feedback mode).
        """
        if self.mode == 'headless':
            # Compute locally with simplified model
            distance = self._compute_distance(node_id, destination)
            speed = self.nodes[node_id].movement_speed
            travel_time = distance / speed
            arrival_time = self.sim_time + travel_time
            
            # Schedule completion event
            self.event_queue.schedule(arrival_time, MoveCompleteEvent(node_id, destination))
            return arrival_time
        
        else:  # viz_feedback
            # Estimate arrival for initial event scheduling
            estimated_travel = self._estimate_travel_time(node_id, destination)
            estimated_arrival = self.sim_time + estimated_travel
            
            move_id = self._next_move_id()
            event = MoveCompleteEvent(node_id, destination, move_id=move_id)
            event_handle = self.event_queue.schedule(estimated_arrival, event)
            
            self.pending_moves[move_id] = PendingMove(
                move_id=move_id,
                node_id=node_id,
                destination=destination,
                start_time=self.sim_time,      # CRITICAL: record when move started
                estimated_arrival=estimated_arrival,
                event_handle=event_handle
            )
            
            # Send intent to viz (async, response comes later)
            self.viz_bridge.send_move_intent(
                move_id=move_id,
                entity_id=node_id,
                destination=destination
            )
            
            return estimated_arrival
    
    def on_viz_travel_time_report(self, move_id: str, travel_time: float):
        """
        Callback from viz-bridge with actual travel time.
        
        Reschedules the MOVE_COMPLETE event if it hasn't fired yet.
        ncsim remains authoritative over sim_time.
        """
        if move_id not in self.pending_moves:
            return  # Already completed or cancelled
        
        pending = self.pending_moves[move_id]
        actual_arrival = pending.start_time + travel_time  # Uses stored start_time
        
        if actual_arrival != pending.estimated_arrival:
            # Reschedule the event (not adjust sim_time!)
            if self.event_queue.cancel(pending.event_handle):
                new_event = MoveCompleteEvent(pending.node_id, pending.destination, move_id=move_id)
                pending.event_handle = self.event_queue.schedule(actual_arrival, new_event)
                pending.estimated_arrival = actual_arrival
            # else: event already fired, too late to reschedule
    
    def on_move_complete(self, event: MoveCompleteEvent):
        """Handle MOVE_COMPLETE event (fires at scheduled time)."""
        if event.move_id and event.move_id in self.pending_moves:
            self.pending_moves.pop(event.move_id)
        
        # Update node position
        self.network.update_node_position(event.node_id, event.destination)
        
        # Recompute link qualities (may affect active transfers)
        link_changes = self.network.recompute_links_for_node(event.node_id)
        for change in link_changes:
            self._handle_link_change(change)
```

### 10.9 DAG Lifecycle and Timeouts

```
DAG Lifecycle:
                                                     
  INJECTED ──► MAPPING ──► EXECUTING ──► COMPLETED   
      │            │            │             │       
      │            │            │             ▼       
      │            │            │         (success)   
      │            │            │                     
      │            │            └──► TIMED_OUT       
      │            │                      │          
      │            │                      ▼          
      │            │                 (logged, mapper notified)
      │            │                                 
      └────────────┴──► FAILED (unrecoverable)      
```

**Timeout handling:**

```python
class DAGManager:
    def inject_dag(self, dag: DAG, timeout: float):
        """Inject a DAG with deadline."""
        dag.state = DAGState.INJECTED
        dag.inject_time = self.sim_time
        dag.deadline = self.sim_time + timeout
        
        # Schedule timeout event
        self.event_queue.schedule(
            time=dag.deadline,
            event=DAGTimeoutEvent(dag_id=dag.id)
        )
        
        # Invoke task mapper
        self._request_mapping(dag)
    
    def on_dag_timeout(self, dag_id: str):
        """Handle DAG timeout."""
        dag = self.dags[dag_id]
        
        if dag.state == DAGState.COMPLETED:
            return  # Already finished, ignore timeout
        
        # Log timeout with details
        self.logger.log_dag_timeout(
            dag_id=dag_id,
            inject_time=dag.inject_time,
            deadline=dag.deadline,
            completed_tasks=[t for t in dag.tasks if t.state == TaskState.COMPLETED],
            pending_tasks=[t for t in dag.tasks if t.state != TaskState.COMPLETED]
        )
        
        dag.state = DAGState.TIMED_OUT
        
        # Notify task mapper (may trigger recovery)
        new_plan = self.task_mapper.on_timeout(dag_id)
        if new_plan:
            self._apply_plan(new_plan)
```

### 10.10 Extension Points for Researchers

ncsim provides these extension points for scheduling research:

| Extension Point | What Researchers Implement |
|-----------------|---------------------------|
| `TaskMapper` | Scheduling/placement algorithm |
| `TaskMapper.on_*` hooks | Rescheduling policies |
| `DAGSource` | Workload generation models |
| `MovementModel` | Custom mobility patterns (headless) |
| `LinkQualityModel` | Distance-to-quality functions |
| `FailureModel` | Task/transfer failure injection |

**Example: Custom Scheduler**

```python
from ncsim.scheduler import TaskMapper, PlacementPlan
from saga.schedulers import HeftScheduler

class AdaptiveHEFT(TaskMapper):
    """HEFT with rescheduling on network changes."""
    
    def __init__(self, reschedule_threshold: float = 0.2):
        self.heft = HeftScheduler()
        self.reschedule_threshold = reschedule_threshold
        self.last_network_snapshot = None
    
    def compute_placement(self, dags, network, running_tasks, config) -> PlacementPlan:
        # Use SAGA's HEFT for initial placement
        saga_network = self._convert_network(network)
        saga_dag = self._convert_dags(dags)
        
        schedule = self.heft.schedule(saga_network, saga_dag)
        self.last_network_snapshot = network
        
        return self._convert_to_plan(schedule)
    
    def on_network_change(self, change) -> Optional[PlacementPlan]:
        # Reschedule if network changed significantly
        if self._change_magnitude(change) > self.reschedule_threshold:
            return self.compute_placement(
                self.pending_dags,
                self.get_network_snapshot(),
                self.running_tasks,
                {}
            )
        return None
```

### 10.11 Future: Distributed Scheduling

The architecture supports future extension to distributed scheduling:

```
Centralized (current):
┌─────────────────────────────────────────┐
│           Global Task Mapper            │
│  (sees entire network, all DAGs)        │
└─────────────────────────────────────────┘

Distributed (future):
┌─────────┐    ┌─────────┐    ┌─────────┐
│ Local   │◄──►│ Local   │◄──►│ Local   │
│ Mapper  │    │ Mapper  │    │ Mapper  │
│ (node A)│    │ (node B)│    │ (node C)│
└─────────┘    └─────────┘    └─────────┘
     │              │              │
     ▼              ▼              ▼
┌─────────┐    ┌─────────┐    ┌─────────┐
│  k-hop  │    │  k-hop  │    │  k-hop  │
│ discovery│    │ discovery│    │ discovery│
└─────────┘    └─────────┘    └─────────┘
```

**Key difference:** In distributed mode, each node's mapper only sees its k-hop neighborhood, requiring:
- Neighborhood discovery protocol
- Partial state decision-making
- Coordination between local mappers

The current architecture supports this by:
- `NetworkSnapshot` can represent partial views
- `TaskMapper` interface doesn't assume global knowledge
- Event system can model message passing between nodes

---

## 11. MODEL SEMANTICS (AUTHORITATIVE)

This section defines the precise behavioral contracts for ncsim models. These rules are **authoritative** — all implementations must conform to them for research reproducibility.

### 11.1 Units and Conventions

| Quantity | Unit | Definition | Notes |
|----------|------|------------|-------|
| `sim_time` | seconds (float) | Simulation time | Always ≥ 0 |
| `wall_time` | seconds (float) | Real elapsed time | For UI/pacing only |
| `compute_capacity` | abstract units/sec | Processing rate | Higher = faster |
| `compute_cost` | abstract units | Total work for task | Time = cost / capacity |
| `bandwidth` | Mbps (10⁶ bits/sec) | Link data rate | Decimal, not binary |
| `latency` | milliseconds (ms) | Propagation delay | Does NOT include queueing |
| `data_size` | MB (10⁶ bytes) | Transfer payload | Decimal megabytes |
| `position` | {x, y} | Map coordinates | Integer cell positions |

**Conversion formulas:**
```
transfer_time_sec = (data_size_MB * 8) / bandwidth_Mbps + latency_ms / 1000
task_exec_time_sec = compute_cost / compute_capacity
```

**Example:**
- Transfer 100 MB over 1000 Mbps link with 5ms latency:
  - `(100 * 8) / 1000 + 5/1000 = 0.8 + 0.005 = 0.805 seconds`

**Floating point handling (for determinism):**

| Context | Precision | Rounding |
|---------|-----------|----------|
| Event times (internal) | Full `float64` | No rounding during computation |
| Event times (comparison) | 1 microsecond (1e-6 sec) | Round-half-even for tie-breaking |
| Metrics output (JSON) | 6 decimal places | Truncate at serialization |
| Trace output (JSONL) | 6 decimal places | Truncate at serialization |

```python
# Event time comparison uses epsilon for floating point tolerance
TIME_EPSILON = 1e-9  # 1 nanosecond

def times_equal(t1: float, t2: float) -> bool:
    return abs(t1 - t2) < TIME_EPSILON

# Serialization rounding
def serialize_time(t: float) -> float:
    return round(t, 6)  # 6 decimal places = microsecond precision
```

### 11.2 Compute Model

**Architecture:** Single-core per node (no internal parallelism)

| Property | Behavior |
|----------|----------|
| Parallelism | One task executes at a time per node |
| Preemption | None — tasks run to completion once started |
| Queue discipline | FIFO — tasks execute in arrival order |
| Context switch | Zero overhead |
| Task execution time | `compute_cost / compute_capacity` seconds |

**Task lifecycle:**
```
PENDING → READY → RUNNING → COMPLETED
           │
           └→ (waiting for dependencies)
```

- `PENDING`: Task exists but has unmet dependencies
- `READY`: All dependencies satisfied, waiting in node queue
- `RUNNING`: Actively executing on assigned node
- `COMPLETED`: Finished, output data available for transfer

**Queue behavior:**
- Each node has a single FIFO queue
- Ready tasks are appended to queue when scheduled
- Node pulls from head of queue when idle
- Queue length metric = number of READY tasks waiting

### 11.3 Network Model

**Model type:** Fluid model (not packet-level)

| Property | Behavior |
|----------|----------|
| Bandwidth sharing | Fair share among concurrent flows |
| Flow model | Fluid (continuous rate, not packets) |
| Latency | Propagation only (fixed per link) |
| Queueing delay | Implicit via bandwidth contention |
| Link queues | Not modeled explicitly |
| Max concurrent flows | Unlimited (bandwidth subdivides) |
| Reliability | Bernoulli success per transfer (if < 1.0) |

**Link direction and duplex:**

| Property | Specification |
|----------|---------------|
| Graph type | **Directed** — each link is one-way |
| Full duplex | Requires two separate link definitions (A→B and B→A) |
| Asymmetric links | Supported — A→B can differ from B→A in bandwidth/latency |
| Undirected shorthand | Scenario loader can expand `bidirectional: true` into two links |

```yaml
# Explicit directed links
links:
  - {id: l01, from: n0, to: n1, bandwidth: 1000, latency: 5}
  - {id: l10, from: n1, to: n0, bandwidth: 500, latency: 5}  # asymmetric!

# Shorthand for symmetric bidirectional
links:
  - {id: l01, from: n0, to: n1, bandwidth: 1000, latency: 5, bidirectional: true}
  # Expands to l01_fwd (n0→n1) and l01_rev (n1→n0) with same properties
```

**Bandwidth sharing:**
When N flows share a link simultaneously:
```
effective_rate_per_flow = link_bandwidth / N
```

**Transfer time calculation:**
```python
def transfer_time(data_size_MB, bandwidth_Mbps, latency_ms, num_concurrent_flows):
    effective_bandwidth = bandwidth_Mbps / num_concurrent_flows
    serialization_time = (data_size_MB * 8) / effective_bandwidth  # seconds
    propagation_time = latency_ms / 1000  # seconds
    return serialization_time + propagation_time
```

**Multi-hop transfers:**
- Route is computed at transfer start
- Each link on path has its bandwidth reduced
- Total latency = sum of per-link latencies
- Bottleneck bandwidth = minimum bandwidth along path

#### 11.3.1 Dynamic Transfer Update Rules (AUTHORITATIVE)

**This subsection is the single source of truth for how transfers respond to changing conditions.**

Transfer timing uses **processor-sharing with discrete event updates**:

| Event | Effect on Active Transfers |
|-------|---------------------------|
| New transfer starts on shared link | All transfers on that link: recalculate remaining time |
| Transfer completes on shared link | All transfers on that link: recalculate remaining time |
| Link quality changes (mobility) | All transfers on that link: recalculate remaining time |
| Link breaks (out of range) | All transfers on that link: **FAIL** |

**Transfer state tracking:**

```python
@dataclass
class ActiveTransfer:
    """State of an in-progress transfer."""
    transfer_id: str
    from_node: str
    to_node: str
    data_size_MB: float
    route: List[str]               # link_ids (fixed at start)
    total_latency_ms: float        # sum of link latencies (fixed at start)
    
    # Mutable state for incremental updates:
    bytes_sent: float = 0.0        # Bytes successfully sent so far
    current_rate_Mbps: float = 0.0 # Current effective rate (bottleneck)
    last_update_time: float = 0.0  # sim_time of last recalculation
    estimated_completion: float = 0.0
```

**Remaining time calculation (AUTHORITATIVE):**

```python
def recalculate_transfer(
    transfer: ActiveTransfer, 
    current_time: float, 
    network_state: NetworkSnapshot
) -> float:
    """
    Recalculate transfer completion time after a link event.
    
    This is the AUTHORITATIVE algorithm for dynamic transfer updates.
    Uses INCREMENTAL updates to avoid double-counting on repeated calls.
    Handles MULTI-HOP routes by computing bottleneck across all links.
    """
    # Step 1: Update bytes_sent based on progress since last update
    time_since_last_update = current_time - transfer.last_update_time
    if time_since_last_update > 0 and transfer.current_rate_Mbps > 0:
        bits_sent_since = transfer.current_rate_Mbps * 1e6 * time_since_last_update
        transfer.bytes_sent += bits_sent_since / 8
    
    # Step 2: Calculate remaining bytes
    total_bytes = transfer.data_size_MB * 1e6
    remaining_bytes = max(0, total_bytes - transfer.bytes_sent)
    
    if remaining_bytes == 0:
        # Transfer data complete, just waiting for propagation delay
        # (propagation is added once at end, not during serialization)
        return transfer.estimated_completion  # No change
    
    # Step 3: Compute new bottleneck rate across ALL links in route
    # active_transfers count INCLUDES this transfer (it's already active)
    bottleneck_rate_Mbps = float('inf')
    for link_id in transfer.route:
        link = network_state.links[link_id]
        # Fair share: link bandwidth divided by number of active transfers on this link
        link_fair_share = link.bandwidth / max(1, link.active_transfers)
        bottleneck_rate_Mbps = min(bottleneck_rate_Mbps, link_fair_share)
    
    # Step 4: Compute remaining time at new rate
    remaining_bits = remaining_bytes * 8
    remaining_serialization_sec = remaining_bits / (bottleneck_rate_Mbps * 1e6)
    
    # Add propagation delay (only once, at the end)
    # Note: propagation is the time for the last bit to traverse the path
    propagation_sec = transfer.total_latency_ms / 1000
    
    # Step 5: Update transfer state
    transfer.current_rate_Mbps = bottleneck_rate_Mbps
    transfer.last_update_time = current_time
    transfer.estimated_completion = current_time + remaining_serialization_sec + propagation_sec
    
    return transfer.estimated_completion
```

**Note on `active_transfers` count:** The count on each link **includes** the transfer being recalculated (it's already active on those links). When a new transfer starts, increment counts first, then recalculate all affected transfers.

**Route stability:**
- Route is computed once at transfer start and NOT recomputed mid-transfer
- If any link on the route breaks, the entire transfer FAILS
- Retry (if configured) recomputes the route

#### 11.3.2 Failure and Retry Policy (AUTHORITATIVE)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_retries` | 3 | Maximum retry attempts per transfer |
| `retry_delay` | 0.0 sec | Delay before retry (0 = immediate) |
| `recompute_route` | true | Recompute route on retry |
| `failure_outcome` | `task_blocked` | What happens when retries exhausted |

**Failure outcomes:**

| Outcome | Behavior |
|---------|----------|
| `task_blocked` | Task remains PENDING, may be rescheduled by mapper |
| `dag_failed` | Entire DAG marked FAILED, logged |
| `notify_mapper` | Invoke `mapper.on_transfer_failed()` for custom handling |

**Retry logic:**
```python
def on_transfer_failed(transfer: Transfer, reason: str):
    if transfer.retry_count < config.max_retries:
        transfer.retry_count += 1
        
        if config.retry_delay > 0:
            schedule_event(current_time + config.retry_delay, RetryTransfer(transfer))
        else:
            # Immediate retry
            if config.recompute_route:
                transfer.route = routing.compute_route(transfer.from_node, transfer.to_node)
            start_transfer(transfer)
    else:
        # Retries exhausted
        if config.failure_outcome == 'dag_failed':
            mark_dag_failed(transfer.dag_id, f"Transfer failed after {config.max_retries} retries")
        elif config.failure_outcome == 'notify_mapper':
            new_plan = mapper.on_transfer_failed(transfer)
            if new_plan:
                apply_plan(new_plan)
        # else: task_blocked — task stays PENDING, mapper may reschedule
```

### 11.4 Task Execution Model

**Execution phases:** Sequential (no pipelining)

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Transfer input │ →  │  Execute task   │ →  │ Output available│
│  data to node   │    │  on node        │    │ for successors  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
     (network)              (compute)              (immediate)
```

| Property | Behavior |
|----------|----------|
| Input transfer | All input data must arrive before compute starts |
| Pipelining | None — compute waits for complete input |
| Partial data | Not supported |
| Output availability | Immediate upon task completion |
| Local data | If task and predecessor on same node, transfer time = 0 |

**Dependency satisfaction:**
- Task becomes READY when ALL predecessor tasks are COMPLETED AND all data transfers to the assigned node are complete
- Multiple inputs: all must arrive (last arrival triggers READY)

### 11.5 Mobility Model (Optional)

**Default:** Static (positions fixed)

**When enabled:**

| Property | Behavior |
|----------|----------|
| Movement model | Waypoint-based interpolation |
| Position update | Continuous (evaluated at event times) |
| Link existence | Distance-based (link exists if distance ≤ range) |
| Link quality | Distance-based degradation function |

**Distance → Link quality function:**
```python
def link_quality(distance, max_range, base_bandwidth, base_latency):
    if distance > max_range:
        return None  # No link
    
    # Linear degradation (configurable)
    quality_factor = 1.0 - (distance / max_range) * 0.5
    
    return {
        'bandwidth': base_bandwidth * quality_factor,
        'latency': base_latency / quality_factor,
        'reliability': 0.99 * quality_factor
    }
```

**Topology updates:**
- Links are re-evaluated at each simulation event
- Active transfers on broken links: FAILED (triggers retry or task failure)

### 11.6 Defaults Table

| Parameter | Default Value | Override in |
|-----------|---------------|-------------|
| Queue discipline | FIFO | scenario.config |
| Bandwidth sharing | Fair share | scenario.config |
| Link reliability | 1.0 (perfect) | scenario.config |
| Mobility | Disabled | scenario.config |
| Random seed | 0 | scenario.config.seed |
| Retry on failure | 3 attempts | scenario.config |

---

## 12. SAGA SCHEDULER INTEGRATION

ncsim leverages the **SAGA** (Scheduling Algorithms Gathered) library for DAG scheduling algorithms. SAGA is a Python toolkit from ANRGUSC (github.com/anrgusc/saga) that provides a collection of scheduling algorithms under a unified API.

### 12.1 Why SAGA?

- **Battle-tested algorithms**: HEFT, CPOP, brute-force, SMT-based optimizers
- **Common interface**: All schedulers share the same API
- **Research-grade**: Used in academic publications, well-documented
- **Extensible**: Easy to add custom schedulers following the same interface
- **Python native**: Integrates naturally with ncsim

### 12.2 Available Schedulers (via SAGA)

| Scheduler | Description | Use Case |
|-----------|-------------|----------|
| `HeftScheduler` | Heterogeneous Earliest Finish Time | Default, fast heuristic |
| `CpopScheduler` | Critical Path on Processor | Alternative heuristic |
| `BruteForceScheduler` | Exhaustive search | Small DAGs, optimal baseline |
| `SMTScheduler` | SMT solver-based | Optimal for medium DAGs |

### 12.3 Integration Architecture

```
ncsim models                    SAGA models
─────────────                   ───────────
                               
┌─────────────┐                ┌─────────────┐
│ ncsim.models│   Converter    │ saga.Network│
│   .Network  │ ─────────────► │             │
└─────────────┘                └─────────────┘
                               
┌─────────────┐                ┌─────────────┐
│ ncsim.models│   Converter    │saga.TaskGraph│
│   .TaskDAG  │ ─────────────► │             │
└─────────────┘                └─────────────┘
                               
                               ┌─────────────┐
                               │ saga.       │
                               │ HeftScheduler│
                               │ .schedule() │
                               └──────┬──────┘
                                      │
                                      ▼
                               ┌─────────────┐
                               │  Schedule   │
                               │ (task→node  │
                               │  mapping)   │
                               └──────┬──────┘
                                      │
                        Converter     │
              ◄───────────────────────┘
                               
┌─────────────┐
│ncsim.Schedule│
│ (with timing)│
└─────────────┘
```

### 12.4 SAGA Adapter Implementation

SAGA adapters implement the `TaskMapper` interface, wrapping SAGA's schedulers:

```python
# ncsim/scheduler/saga_adapter.py

from typing import Dict, Any, List, Optional
from saga.schedulers import HeftScheduler, CpopScheduler
from saga import Network as SagaNetwork, TaskGraph as SagaTaskGraph

from ncsim.models.network import Network as NcsimNetwork
from ncsim.models.task import TaskDAG
from ncsim.scheduler.base import TaskMapper, PlacementPlan, NetworkSnapshot

class SagaTaskMapper(TaskMapper):
    """
    Adapter that wraps SAGA schedulers for use in ncsim.
    
    SAGA calls this "scheduling" — it's the offline task mapping phase.
    The ncsim Execution Engine handles the online/runtime phase.
    """
    
    # Available SAGA schedulers
    SCHEDULERS = {
        'heft': HeftScheduler,
        'cpop': CpopScheduler,
        # Add more as needed
    }
    
    def __init__(self, algorithm: str = 'heft', **kwargs):
        """
        Initialize with a SAGA scheduler.
        
        Args:
            algorithm: Name of SAGA scheduler ('heft', 'cpop', etc.)
            **kwargs: Additional arguments for the SAGA scheduler
        """
        if algorithm not in self.SCHEDULERS:
            raise ValueError(f"Unknown scheduler: {algorithm}. "
                           f"Available: {list(self.SCHEDULERS.keys())}")
        
        self.algorithm = algorithm
        self.saga_scheduler = self.SCHEDULERS[algorithm](**kwargs)
    
    def compute_placement(
        self,
        dags: List['DAG'],
        network: NetworkSnapshot,
        running_tasks: Dict[str, 'TaskExecution'],
        config: Dict
    ) -> PlacementPlan:
        """
        Compute task-to-node assignments using SAGA.
        
        Args:
            dags: Pending DAGs to schedule
            network: Current network state snapshot
            running_tasks: Currently executing tasks
            config: Scheduler-specific configuration
            
        Returns:
            PlacementPlan with task assignments
        """
        # Convert ncsim models to SAGA models
        saga_network = self._convert_network(network)
        
        all_assignments = {}
        all_order = []
        
        for dag in dags:
            saga_taskgraph = self._convert_dag(dag)
            
            # Run SAGA scheduler
            saga_schedule = self.saga_scheduler.schedule(saga_network, saga_taskgraph)
            
            # Convert result to PlacementPlan format
            assignments, order = self._extract_assignments(saga_schedule, dag)
            all_assignments.update(assignments)
            all_order.extend(order)
        
        return PlacementPlan(
            assignments=all_assignments,
            execution_order=all_order
        )
    
    def _convert_network(self, snapshot: NetworkSnapshot) -> SagaNetwork:
        """Convert ncsim NetworkSnapshot to SAGA Network."""
        # Implementation: map node capacities and link bandwidths
        pass
    
    def _convert_dag(self, dag: 'DAG') -> SagaTaskGraph:
        """
        Convert ncsim DAG to SAGA TaskGraph.
        
        Respects pinned_to constraints by setting node affinity in SAGA.
        """
        # Implementation: map tasks, edges, and pin constraints
        pass
    
    def _extract_assignments(self, saga_schedule, dag) -> tuple:
        """Extract task→node assignments from SAGA schedule."""
        # Implementation: parse SAGA output format
        pass
```

### 12.5 Usage in ncsim

```python
# Example: Using SAGA scheduler in ncsim

from ncsim.core.simulation import Simulation
from ncsim.scheduler.saga_adapter import SagaTaskMapper
from ncsim.io.scenario_loader import load_scenario

# Load scenario
scenario = load_scenario('scenarios/demo_bottleneck.yaml')

# Create task mapper (using SAGA's HEFT)
mapper = SagaTaskMapper(algorithm='heft')

# Alternative: use CPOP
# mapper = SagaTaskMapper(algorithm='cpop')

# Run simulation
sim = Simulation(
    network=scenario.network,
    task_mapper=mapper,      # Note: 'task_mapper' not 'scheduler'
    router=scenario.router
)

# Inject DAG and run
sim.inject_dag(scenario.dags[0])
results = sim.run()
```

### 12.6 CLI Support

```bash
# Run with default HEFT scheduler
ncsim --scenario demo.yaml

# Run with specific SAGA scheduler
ncsim --scenario demo.yaml --scheduler heft
ncsim --scenario demo.yaml --scheduler cpop

# Compare schedulers
ncsim --scenario demo.yaml --compare-schedulers heft,cpop
```

### 12.7 Installation

SAGA is available on PyPI:

```bash
pip install anrg-saga
```

Or include in ncsim's dependencies:

```toml
# ncsim/pyproject.toml
[project]
dependencies = [
    "anrg-saga>=2.0.0",
    "networkx>=3.0",
    "numpy>=1.24",
    "pyyaml>=6.0",
    # ...
]
```

### 12.8 Custom Task Mappers

While SAGA provides the primary schedulers, ncsim supports custom task mappers:

```python
# ncsim/scheduler/custom/my_mapper.py

from typing import List, Dict, Optional
from ncsim.scheduler.base import TaskMapper, PlacementPlan, NetworkSnapshot

class MyCustomMapper(TaskMapper):
    """Example custom task mapper."""
    
    def compute_placement(
        self,
        dags: List['DAG'],
        network: NetworkSnapshot,
        running_tasks: Dict[str, 'TaskExecution'],
        config: Dict
    ) -> PlacementPlan:
        # Custom scheduling/mapping logic
        # Can still use SAGA utilities if helpful
        pass
```

Register custom task mappers:

```python
# In ncsim configuration or code
from ncsim.scheduler import register_mapper
from ncsim.scheduler.custom.my_mapper import MyCustomMapper

register_mapper('my_custom', MyCustomMapper)

# Now usable via CLI
# ncsim --scenario demo.yaml --scheduler my_custom
```

---

## 13. REPRODUCIBILITY AND VALIDATION

For research credibility, ncsim must produce **reproducible results** and include **validation benchmarks**.

### 13.1 Deterministic Execution

**Every simulation run must be reproducible given the same inputs.**

| Requirement | Implementation |
|-------------|----------------|
| Random seed | Explicit `seed` parameter in scenario config |
| Event ordering | Deterministic tie-breaking (see below) |
| Floating point | Use consistent rounding (round-half-even) |
| Parallel execution | Not supported in core sim (determinism > speed) |

#### 13.1.1 Event ID Assignment

Every event has a unique, monotonically increasing `event_id`:

```python
class EventQueue:
    def __init__(self):
        self._next_id = 0
        self._heap = []  # (sim_time, event_id, event)
    
    def schedule(self, time: float, event: Event) -> int:
        event_id = self._next_id
        self._next_id += 1
        heapq.heappush(self._heap, (time, event_id, event))
        return event_id
```

#### 13.1.2 Tie-Breaking Rules (AUTHORITATIVE)

When multiple events have the same `sim_time`, they are processed in this order:

```python
# Sort key for events at the same sim_time
def event_sort_key(event):
    return (
        event.sim_time,           # Primary: scheduled time
        EVENT_PRIORITY[event.type], # Secondary: event type priority
        event.event_id            # Tertiary: insertion order (FIFO)
    )

# Event type priorities (lower = higher priority)
EVENT_PRIORITY = {
    'DAG_INJECT': 0,       # DAG arrivals first
    'TASK_COMPLETE': 1,    # Completions before starts
    'TRANSFER_COMPLETE': 2,
    'TASK_START': 3,       # Starts after completions
    'TRANSFER_START': 4,
    'NODE_MOVE': 5,        # Mobility updates
    'RESCHEDULE': 6,       # Rescheduling last
}
```

**FIFO for same type at same time:**
When multiple tasks become READY at the same `sim_time` for the same node, they are queued in `event_id` order (which reflects creation order).

#### 13.1.3 Coalescing Determinism

When coalescing commands in step frames, sort by key for deterministic order:

```python
def coalesce_commands(commands: List[Command]) -> List[Command]:
    """Reduce redundant commands within a frame (deterministic)."""
    link_updates = {}
    entity_moves = {}
    task_states = {}
    other_commands = []
    
    for cmd in commands:
        if cmd.type == 'update_link':
            link_updates[cmd.id] = cmd
        elif cmd.type == 'move_entity':
            entity_moves[cmd.id] = cmd
        elif cmd.type == 'task_state':
            task_states[cmd.task_id] = cmd
        else:
            other_commands.append(cmd)
    
    # CRITICAL: Sort by key for deterministic output order
    return (
        other_commands +  # Preserve insertion order for creates/deletes
        [link_updates[k] for k in sorted(link_updates.keys())] +
        [entity_moves[k] for k in sorted(entity_moves.keys())] +
        [task_states[k] for k in sorted(task_states.keys())]
    )
```

```yaml
# Scenario with explicit seed
scenario:
  config:
    seed: 42  # Reproducible random sequence
```

```bash
# Same seed = same results
ncsim --scenario demo.yaml --seed 42 --output run1/
ncsim --scenario demo.yaml --seed 42 --output run2/
diff run1/metrics.json run2/metrics.json  # Should be empty
```

### 13.2 Event Trace Format

**Primary debug path:** Replay is based on event traces, not state snapshots.

Every simulation produces an **event trace** — an append-only log of all simulation events.

**Trace file format:** `{run_id}_trace.jsonl` (JSON Lines)

```jsonl
{"seq": 0, "sim_time": 0.0, "type": "sim_start", "seed": 42, "scenario": "demo.yaml"}
{"seq": 1, "sim_time": 0.0, "type": "dag_injected", "dag_id": "dag_1", "tasks": ["T0", "T1", "T2"]}
{"seq": 2, "sim_time": 0.0, "type": "task_scheduled", "task_id": "T0", "node_id": "n2"}
{"seq": 3, "sim_time": 0.0, "type": "task_started", "task_id": "T0", "node_id": "n2"}
{"seq": 4, "sim_time": 2.0, "type": "task_completed", "task_id": "T0", "node_id": "n2"}
{"seq": 5, "sim_time": 2.0, "type": "transfer_started", "from_task": "T0", "to_task": "T1", "link": "l02", "size_mb": 200}
{"seq": 6, "sim_time": 18.0, "type": "transfer_completed", "from_task": "T0", "to_task": "T1"}
...
{"seq": N, "sim_time": 25.3, "type": "sim_end", "makespan": 25.3, "status": "completed"}
```

**Event types:**
| Type | Description | Key Fields |
|------|-------------|------------|
| `sim_start` | Simulation begins | seed, scenario |
| `sim_end` | Simulation completes | makespan, status |
| `dag_injected` | DAG added to simulation | dag_id, tasks |
| `task_scheduled` | Scheduler assigns task | task_id, node_id |
| `task_started` | Task begins execution | task_id, node_id |
| `task_completed` | Task finishes | task_id, duration |
| `transfer_started` | Data transfer begins | from_task, to_task, link, size_mb |
| `transfer_completed` | Data transfer finishes | from_task, to_task, duration |
| `transfer_failed` | Transfer error | from_task, to_task, reason |

### 13.3 Replay Mode

Traces can be replayed for debugging and visualization:

```bash
# Replay a trace (recomputes state from events)
ncsim replay trace_20240115_run42.jsonl --verify

# Replay with visualization
ncsim replay trace.jsonl --viz localhost:9999

# Replay at different speed
ncsim replay trace.jsonl --speed 0.5
```

**Replay guarantees:**
- Same trace → same metrics (exact match)
- Visualization sees same sequence of updates
- Can pause/step through events

### 13.4 Validation Suite

A `validation/` directory contains canonical tests where expected outputs are known:

```
validation/
├── micro/                      # Hand-calculable scenarios
│   ├── single_task.yaml        # 1 task, 1 node → trivial makespan
│   ├── two_tasks_same_node.yaml    # Sequential execution
│   ├── two_tasks_diff_nodes.yaml   # Parallel + transfer
│   ├── diamond_dag.yaml        # Classic diamond dependency
│   └── expected/
│       ├── single_task.json
│       ├── two_tasks_same_node.json
│       └── ...
├── scheduler/                  # Scheduler correctness
│   ├── heft_vs_bruteforce_tiny.yaml  # HEFT should match optimal
│   ├── cpop_critical_path.yaml       # Verify critical path
│   └── expected/
├── routing/                    # Network routing
│   ├── shortest_path_simple.yaml
│   ├── bandwidth_contention.yaml
│   └── expected/
└── regression/                 # Bugs found and fixed
    ├── issue_042_queue_ordering.yaml
    └── expected/
```

**Running validation:**

```bash
# Run all validation tests
ncsim validate

# Run specific category
ncsim validate --category micro

# Verbose output
ncsim validate --verbose
```

**Validation output:**
```
Validation Results
==================
micro/single_task.yaml                    PASS (0.001s)
micro/two_tasks_same_node.yaml            PASS (0.002s)
micro/two_tasks_diff_nodes.yaml           PASS (0.003s)
micro/diamond_dag.yaml                    PASS (0.002s)
scheduler/heft_vs_bruteforce_tiny.yaml    PASS (0.150s)
routing/shortest_path_simple.yaml         PASS (0.002s)
routing/bandwidth_contention.yaml         PASS (0.005s)
regression/issue_042_queue_ordering.yaml  PASS (0.003s)

8/8 tests passed
```

### 13.5 Expected Output Format

Each validation scenario has a corresponding expected output:

```json
// validation/micro/expected/diamond_dag.json
{
  "makespan": 12.5,
  "task_completions": {
    "T0": {"node": "n0", "start": 0.0, "end": 2.0},
    "T1": {"node": "n1", "start": 2.5, "end": 6.5},
    "T2": {"node": "n0", "start": 2.5, "end": 5.5},
    "T3": {"node": "n1", "start": 7.0, "end": 12.5}
  },
  "transfers": [
    {"from": "T0", "to": "T1", "duration": 0.5},
    {"from": "T0", "to": "T2", "duration": 0.5},
    {"from": "T1", "to": "T3", "duration": 0.5},
    {"from": "T2", "to": "T3", "duration": 0.5}
  ],
  "tolerance": {
    "makespan": 0.001,
    "times": 0.001
  }
}
```

### 13.6 Experiment Runner (Research Workflows)

For parameter sweeps and batch experiments:

```yaml
# experiments/sweep_schedulers.yaml
experiment:
  name: "Scheduler Comparison"
  base_scenario: scenarios/medium_dag.yaml
  
  sweep:
    scheduler: [heft, cpop]
    seed: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
  
  metrics:
    - makespan
    - avg_utilization
    - max_queue_length
  
  output:
    format: csv
    path: results/scheduler_comparison.csv
```

```bash
# Run experiment
ncsim experiment experiments/sweep_schedulers.yaml

# Output: results/scheduler_comparison.csv
# scheduler,seed,makespan,avg_utilization,max_queue_length
# heft,1,25.3,0.72,4
# heft,2,24.8,0.74,3
# ...
```

### 13.7 Git Integration

Every run records environment for reproducibility:

```json
// In trace header
{
  "environment": {
    "ncsim_version": "0.1.0",
    "git_hash": "abc123def",
    "git_dirty": false,
    "python_version": "3.11.5",
    "platform": "Linux-5.15.0-x86_64",
    "timestamp": "2024-01-15T14:30:00Z"
  }
}
```

---

## 14. PHASED IMPLEMENTATION PLAN

Each phase delivers a **working, demonstrable product**. Phases build incrementally.

---

### PHASE 1: Clean Visualization Client (iobt-viz)
**Goal**: Transform OpenRA into a clean simulation display through incremental modifications

**Approach**: This phase consists of many small checkpoints, each independently testable and committable. The order may vary based on discoveries during development.

#### Checkpoint 1.1: Setup and Baseline
- [x] Copy OpenRA and OpenRAModSDK to `reference/` (read-only)
- [x] Copy to `iobt-viz/` (working copy)
- [x] Verify iobt-viz builds and launches (build succeeded 2026-01-24)
- [x] Document baseline state

#### Checkpoint 1.2: Audio Mute Option
- [x] Add mute toggle to settings or UI (inherited from common|chrome/settings-audio.yaml)
- [x] Audio remains on by default (Mute = false in SoundSettings)
- [x] Build verified - Settings > Audio panel includes Mute Sound checkbox
- [x] No code changes needed - inherited from OpenRA

#### Checkpoint 1.3: Lobby Simplification
- [x] Identify lobby chrome files in `reference/` (explored - lobby is bypassed)
- [x] Lobby already bypassed via IoBTMainMenuLogic.cs auto-start
- [x] Game loads directly to map (no lobby UI shown)
- [x] Added IoBT-viz branding overlay (bottom-right: "IoBT-viz" + "ANRG, USC, 2026")
- [x] Build verified - branding displays during visualization

#### Checkpoint 1.4: Escape Menu Cleanup
- [x] Find ingame menu chrome files (mods/iobt/chrome/ingame-menu.yaml)
- [x] Remove "Surrender" option (not present - only RESUME, SETTINGS, QUIT defined)
- [x] Remove "Diplomacy" option (not present)
- [x] Keep only: Resume, Settings, Exit (implemented via IoBTIngameMenuLogic.cs)
- [x] Test: Escape menu works with reduced options
- [x] Included in initial commit

#### Checkpoint 1.5: Remove Production Sidebar
- [x] Identify production tab chrome in `reference/` (ingame-player.yaml)
- [x] Simplified `ingame-player.yaml` - removed command bar, stance bar, support powers
- [x] Remove credits/money display (removed)
- [x] Remove power display (removed)
- [x] Test: Game runs without sidebar clutter
- [x] Commit: "iobt-viz: Simplify UI and add makespan tracking"

#### Checkpoint 1.6: Radar Minimap
- [x] **KEPT** - Radar minimap intentionally preserved for map navigation
- [x] User needs minimap to move around the battlefield
- [x] Only removed game-specific buttons (beacon, sell, power, repair)

#### Checkpoint 1.7: Entity Definitions
- [x] Entity definitions exist in initial commit (infantry, vehicles as compute nodes)
- [x] IoBTNetworkOverlay.cs handles compute node assignment
- [x] Entities spawn and display on map
- [x] Included in initial commit

#### Checkpoint 1.8: Network Link Overlay (Basic)
- [x] IoBTNetworkOverlay.cs implements full overlay system
- [x] Distance-based link quality with color coding (green→yellow→red)
- [x] Active transfer highlighting (cyan)
- [x] DAG status panel with task states
- [x] Included in initial commit

#### Checkpoint 1.9: Demo Map
- [x] Maps exist: `iobt-sim/` and `iobt-demo2/`
- [x] Lua config files define units, buildings, DAG execution
- [x] Maps load with entities and network overlay
- [x] Included in initial commit

#### Checkpoint 1.9.1: Makespan Display (Added)
- [x] Track DAG start time (first task assigned)
- [x] Track DAG completion time (all tasks completed)
- [x] Display running makespan in yellow, completed in green
- [x] Commit: "iobt-viz: Simplify UI and add makespan tracking"

#### Checkpoint 1.10: Bridge Server Skeleton
- [x] Create `OpenRA.Mods.IoBT/Bridge/` directory structure
- [x] Implement TCP listener on port 9999 (`IoBTBridgeServer.cs`)
- [x] Accept connections and log messages
- [x] **Phase 1 uses newline-delimited JSON** (for easy testing with netcat)
- [x] Responds to ping with pong, get_state with network info
- [x] Test: Can connect with `nc localhost 9999` and send `{"type":"ping"}\n`

**Note:** Phase 3 upgrades to length-prefixed binary framing for robustness. Phase 1's newline-delimited protocol is for development convenience only.

#### Checkpoint 1.11: Bridge Trait Integration
- [x] Create trait to attach bridge to world (`IoBTBridgeTrait.cs`)
- [x] Bridge starts when game/map loads (AutoStart: true in world.yaml)
- [x] Added to world.yaml with `IoBTBridge:` trait
- [x] Lua API: `IsBridgeRunning()`, `GetBridgeConnectionCount()`, `RequestSchedule()`
- [x] Test: Bridge active during gameplay

#### Checkpoint 1.11.1: SAGA Scheduler Service (NEW)
- [x] Create `saga-service/` Python package
- [x] Implement `scheduler_service.py` - connects to bridge, calls SAGA
- [x] Fallback to round-robin if SAGA not installed
- [x] Protocol: schedule_request → HeftScheduler → schedule_response
- [x] Test script: `test_connection.py`

#### Checkpoint 1.12: LuaSim Backend Discovery and Preservation
**IMPORTANT: Read existing code first before making changes.**

The existing iobt mod likely contains Lua-based simulation logic that already provides:
- DAG definition and execution
- Task state updates and visualization
- Network connectivity based on troop positions  
- Transfer stall/resume on disconnect

The coding agent MUST:
- [ ] Inventory existing Lua simulation code in `mods/iobt/`
- [ ] Document what currently exists (DAG format, execution model, connectivity rules)
- [ ] Identify where simulation logic is intertwined with UI
- [ ] Create `LuaSimBackend` wrapper around existing code (minimal changes)
- [ ] Verify existing demo behavior still works after wrapping
- [ ] Document LuaSim capabilities vs limitations
- [ ] Commit: "iobt-viz: isolate LuaSimBackend interface"

**Goal:** Wrap and stabilize, not rewrite. Preserve the interactive demo experience.

#### Checkpoint 1.13: VizState Abstraction Layer
- [ ] Define `VizState` / `VizDelta` data model (entities, links, tasks, transfers)
- [ ] Refactor overlay rendering to consume only VizState (not backend-specific data)
- [ ] Verify LuaSimBackend produces VizState correctly
- [ ] Commit: "iobt-viz: introduce VizState abstraction"

This abstraction enables both LuaSim and BridgeBackend to drive the same overlays.

#### Checkpoint 1.14: Backend Mode Selection
- [ ] Add `backend` config option (`lua_sim` or `bridge`)
- [ ] Implement mode switch (config flag, hotkey, or menu)
- [ ] LuaSim mode: works standalone, no external connection
- [ ] Bridge mode: waits for viz-bridge connection
- [ ] Test: Can switch modes and both work
- [ ] Commit: "iobt-viz: add backend mode selection"

#### Additional Checkpoints (discovered during development)
- [x] SAGA Scheduler Service (saga-service/) - Python service for HEFT/CPOP scheduling
- [ ] _(add as needed)_

#### Phase 1 Exit Criteria
- [ ] All above checkpoints completed
- [ ] iobt-viz launches with clean, minimal UI
- [ ] Static nodes and links render clearly
- [ ] Audio mute option available (audio on by default)
- [ ] TCP server accepts connections and logs messages
- [ ] **LuaSim backend preserved and working** (interactive demo mode)
- [ ] **VizState abstraction in place** (both backends can drive overlays)
- [ ] **Backend mode selection working**
- [ ] Screenshot demonstrates clean visualization
- [ ] All changes committed with descriptive messages

#### Key Files Modified
```
iobt-viz/
├── mods/iobt/
│   ├── mod.yaml                    # Mod configuration (audio mute option, backend mode)
│   ├── chrome/
│   │   ├── ingame-iobt.yaml        # Minimal ingame chrome
│   │   ├── lobby-iobt.yaml         # Simplified lobby
│   │   └── menu-iobt.yaml          # Simplified menus
│   ├── rules/
│   │   ├── iobt-entities.yaml      # Compute node actor definitions
│   │   └── iobt-world.yaml         # World setup rules
│   ├── scripts/
│   │   ├── lua-sim/                # LuaSim backend (existing code, wrapped)
│   │   │   ├── dag-executor.lua    # DAG execution logic
│   │   │   ├── connectivity.lua    # Network connectivity rules
│   │   │   └── transfer-manager.lua # Transfer state management
│   │   └── viz-state.lua           # VizState/VizDelta producer
│   └── maps/iobt-demo/
│       ├── map.yaml
│       └── demo-config.lua         # Entity configuration
├── OpenRA.Mods.IoBT/
│   ├── Bridge/
│   │   ├── IoBTBridgeServer.cs     # TCP server on port 9999
│   │   └── IoBTBridgeTrait.cs      # World trait for bridge lifecycle
│   ├── Backend/
│   │   ├── IBackend.cs             # Backend interface
│   │   ├── LuaSimBackend.cs        # Wrapper for Lua simulation
│   │   ├── BridgeBackend.cs        # ncsim connection handler
│   │   └── VizState.cs             # Shared state model
│   └── Bridge/
│       ├── BridgeServer.cs         # TCP listener
│       ├── MessageParser.cs        # JSON parsing stub
│       └── BridgeTrait.cs          # Trait to attach to world
```

#### Working Demo (LuaSim Mode)
```bash
cd iobt-viz
make
./launch-game.sh Game.Mod=iobt
# Simplified lobby appears
# Start skirmish on iobt-demo map
# Clean visualization with no game chrome
# LuaSim backend runs automatically
# Select units, right-click to move
# Watch network topology and task execution update live
```

#### Working Demo (Bridge Mode)
```bash
cd iobt-viz
make
./launch-game.sh Game.Mod=iobt Backend=bridge
# Waits for viz-bridge connection
# In another terminal: nc localhost 9999
# Type: {"type": "ping"}
# See log output in iobt-viz
```

---

### PHASE 2: ncsim Core Engine (Headless)
**Goal**: Functional discrete-event simulation that runs without visualization

**Approach**: Build ncsim incrementally with testable checkpoints. Each model component should work independently before integration.

#### Checkpoint 2.1: Project Setup
- [ ] Create `ncsim/` directory structure
- [ ] Set up `pyproject.toml` with dependencies (including `anrg-saga`)
- [ ] Create virtual environment
- [ ] Verify imports work
- [ ] Commit: "ncsim: initial project structure"

#### Checkpoint 2.2: Event Queue
- [ ] Implement priority queue with `heapq`
- [ ] Support event scheduling and retrieval
- [ ] Unit tests for event queue
- [ ] Commit: "ncsim: event queue implementation"

#### Checkpoint 2.3: Simulation Clock
- [ ] Implement `sim_time` management
- [ ] Time advancement logic
- [ ] Unit tests
- [ ] Commit: "ncsim: simulation clock"

#### Checkpoint 2.4: Network Model
- [ ] NetworkX-based graph representation
- [ ] Node model with compute capacity
- [ ] Link model with bandwidth and latency
- [ ] Unit tests
- [ ] Commit: "ncsim: network model"

#### Checkpoint 2.5: Task/DAG Model
- [ ] Task definition with compute cost
- [ ] DAG structure with dependencies
- [ ] Data edge sizes
- [ ] Unit tests
- [ ] Commit: "ncsim: task/DAG model"

#### Checkpoint 2.6: SAGA Integration
- [ ] Create `saga_adapter.py`
- [ ] Implement ncsim → SAGA converters
- [ ] Implement SAGA → ncsim converters
- [ ] Test with `HeftScheduler`
- [ ] Commit: "ncsim: SAGA scheduler integration"

#### Checkpoint 2.7: Basic Routing
- [ ] Shortest path (Dijkstra) implementation
- [ ] Bandwidth tracking on links
- [ ] Unit tests
- [ ] Commit: "ncsim: basic routing"

#### Checkpoint 2.8: Simulation Loop Integration
- [ ] Connect all components
- [ ] Event-driven execution
- [ ] Test simple DAG execution
- [ ] Commit: "ncsim: simulation loop integration"

#### Checkpoint 2.9: Metrics Collection
- [ ] Makespan calculation
- [ ] Per-task completion times
- [ ] Link utilization tracking
- [ ] Commit: "ncsim: metrics collection"

#### Checkpoint 2.10: CLI Interface
- [ ] Scenario YAML loading
- [ ] Command-line argument parsing
- [ ] Results output (JSON/CSV)
- [ ] Commit: "ncsim: CLI interface"

#### Checkpoint 2.11: Demo Scenario
- [ ] Create `demo_simple.yaml`
- [ ] End-to-end test
- [ ] Document usage
- [ ] Commit: "ncsim: demo scenario"

#### Additional Checkpoints
- [ ] _(discovered during development)_

#### Phase 2 Exit Criteria
- [ ] `ncsim --scenario demo_simple.yaml` runs to completion
- [ ] DAG executes with dependencies respected
- [ ] SAGA scheduler produces valid assignments
- [ ] Makespan is computed and printed
- [ ] Results written to JSON file
- [ ] All unit tests pass

#### Deliverables

5. **Basic routing**
   - Shortest path (Dijkstra)
   - Bandwidth tracking on links

6. **Metrics collection**
   - Makespan
   - Per-task completion time
   - Link utilization time series

7. **CLI interface**
   - Load scenario from YAML
   - Run simulation
   - Output results to JSON/CSV

#### Files to Create
```
ncsim/
├── ncsim/
│   ├── __init__.py
│   ├── main.py                     # CLI entry point
│   ├── core/
│   │   ├── simulation.py           # Main DES loop
│   │   ├── event_queue.py          # Priority queue
│   │   └── clock.py                # sim_time management
│   ├── models/
│   │   ├── network.py              # Network graph
│   │   ├── compute.py              # Compute node
│   │   ├── task.py                 # Task and DAG
│   │   └── flow.py                 # Data transfers
│   ├── scheduler/
│   │   ├── base.py                 # Scheduler interface
│   │   ├── saga_adapter.py         # SAGA library integration
│   │   └── converters.py           # ncsim ↔ SAGA model conversion
│   ├── routing/
│   │   ├── base.py                 # Interface
│   │   └── shortest_path.py        # Dijkstra
│   ├── metrics/
│   │   └── collector.py            # Metrics aggregation
│   └── io/
│       ├── scenario_loader.py      # YAML parsing
│       └── results_writer.py       # Output
├── tests/
│   ├── test_event_queue.py
│   ├── test_network.py
│   ├── test_saga_adapter.py        # Test SAGA integration
│   └── test_simulation.py
└── scenarios/
    └── demo_simple.yaml
```

#### Exit Criteria
- [ ] `ncsim --scenario demo_simple.yaml` runs to completion
- [ ] DAG executes with dependencies respected
- [ ] Makespan is computed and printed
- [ ] Results written to JSON file
- [ ] Unit tests pass

#### Working Demo
```bash
cd ncsim
pip install -e .
ncsim --scenario scenarios/demo_simple.yaml --output results/
cat results/metrics.json
# Shows: makespan, task_completions, link_utilization
```

---

### PHASE 3: viz-bridge Protocol Implementation
**Goal**: Establish bidirectional communication between ncsim and iobt-viz

#### Deliverables
1. **Protocol definitions**
   - Message types (handshake, step_frame, events)
   - JSON schema for all messages
   - Version negotiation

2. **Encoder/Decoder**
   - ncsim state → protocol messages
   - Protocol messages → ncsim events

3. **iobt-viz adapter**
   - Entity type mapping
   - Coordinate translation
   - Color mapping for utilization

4. **Frame buffer with backpressure**
   - Queue management
   - Acknowledgement handling
   - Flow control

5. **Connection manager**
   - TCP client with reconnection
   - Async message handling
   - Connection state tracking

6. **iobt-viz bridge implementation**
   - Command dispatch to game systems
   - Entity creation/movement
   - Link overlay updates

#### Files to Create
```
viz-bridge/
├── viz_bridge/
│   ├── __init__.py
│   ├── protocol.py                 # Message definitions
│   ├── encoder.py                  # State → messages
│   ├── decoder.py                  # Messages → events
│   ├── connection.py               # TCP client
│   ├── frame_buffer.py             # Backpressure handling
│   └── adapters/
│       ├── base.py                 # Adapter interface
│       └── iobt_viz.py             # iobt-viz specific
└── tests/
    ├── test_protocol.py
    ├── test_encoder.py
    └── test_frame_buffer.py

iobt-viz/IoBTViz.Bridge/
├── BridgeServer.cs                 # Updated: full implementation
├── CommandDispatcher.cs            # Route commands to systems
├── EntityManager.cs                # Create/update/delete entities
└── LinkOverlayManager.cs           # Link visualization
```

#### Exit Criteria
- [ ] ncsim connects to iobt-viz via viz-bridge
- [ ] Handshake completes with version check
- [ ] Step frames sent and acknowledged
- [ ] Entities appear in iobt-viz when created by ncsim
- [ ] Backpressure prevents buffer overflow
- [ ] Connection loss handled gracefully

#### Working Demo
```bash
# Terminal 1: iobt-viz
cd iobt-viz && ./launch-game.sh Game.Mod=iobt

# Terminal 2: ncsim with visualization
cd ncsim
ncsim --scenario scenarios/demo_simple.yaml --viz localhost:9999

# Watch: entities appear in iobt-viz as simulation runs
```

---

### PHASE 4: ncsim-deck Control Application
**Goal**: Dashboard and control UI for interactive simulation

#### Deliverables
1. **Main window framework** (PyQt6)
   - Multi-panel layout
   - Docking/resizing support

2. **Control panel**
   - Start/Pause/Reset buttons
   - Speed control (1x, 2x, 5x, Max)
   - Step mode (advance one step)

3. **Scenario panel**
   - Scenario file browser
   - Scenario preview
   - Configuration overrides

4. **Metrics dashboard**
   - Throughput chart (live updating)
   - Utilization bars per link
   - Queue length per node
   - Makespan counter

5. **ncsim connection**
   - Connect to running ncsim
   - Send control commands
   - Receive metrics stream

#### Files to Create
```
ncsim-deck/
├── ncsim_deck/
│   ├── __init__.py
│   ├── main.py                     # Entry point
│   ├── ui/
│   │   ├── main_window.py          # Main window
│   │   ├── control_panel.py        # Start/Pause/Speed
│   │   ├── scenario_panel.py       # Scenario loading
│   │   ├── dashboard.py            # Metrics container
│   │   └── widgets/
│   │       ├── throughput_chart.py # PyQtGraph chart
│   │       ├── utilization_bars.py # Bar chart
│   │       └── gantt_chart.py      # Task timeline
│   ├── connection/
│   │   └── ncsim_client.py         # ncsim communication
│   └── mock/
│       └── fake_sim.py             # For UI testing
└── tests/
    └── test_ui.py
```

#### Exit Criteria
- [ ] ncsim-deck launches with all panels
- [ ] Start/Pause/Reset controls work
- [ ] Speed slider affects simulation rate
- [ ] Charts update with live metrics
- [ ] Scenario loading works

#### Working Demo
```bash
# Terminal 1: iobt-viz
cd iobt-viz && ./launch-game.sh Game.Mod=iobt

# Terminal 2: ncsim-deck
cd ncsim-deck && python -m ncsim_deck

# In ncsim-deck: Load scenario, click Start
# Watch: simulation runs, charts update, iobt-viz shows activity
```

---

### PHASE 5: Integration & Polish
**Goal**: Coherent three-component system with hero demo scenario

#### Deliverables
1. **Hero scenario**
   - Multi-node network with clear bottleneck
   - Complex DAG with parallel paths
   - Demonstrates scheduling decisions visually

2. **Enhanced visualization**
   - Animated data transfers (moving markers along links)
   - Task state indicators on nodes (queued/running/completed)
   - Link utilization heat coloring (green→yellow→red)
   - Node queue visualization

3. **Rich dashboards**
   - Gantt chart of task execution
   - Network topology view with live utilization
   - Per-node resource charts

4. **Record/Replay**
   - Event log capture during simulation
   - Deterministic replay from log
   - Replay speed control

5. **Error handling polish**
   - Graceful degradation on connection loss
   - Clear error messages
   - Auto-reconnect

#### Exit Criteria
- [ ] Hero demo runs start-to-finish reliably
- [ ] Non-expert can understand visualization
- [ ] Replay produces identical visualization
- [ ] All three components coordinate smoothly

---

### PHASE 6: iobt-viz Engine Cleanup and Refactoring (OPTIONAL - LONG TERM)

**⚠️ This phase is OPTIONAL and should only be attempted after:**
- All research workflows are stable and validated
- Pain points with build time, dependencies, or codebase size are documented and measured
- Phases 1-5 have been in use long enough to identify what's truly unused

**Goal**: Transform OpenRA+IoBT into a cleaner, leaner iobt-viz engine

**Risk level**: HIGH — This is a major refactoring effort that could break working functionality.

**Trigger criteria** (attempt only when ALL are true):
- [ ] Build time > 2 minutes bothering developers
- [ ] Dependency conflicts with OpenRA updates causing friction  
- [ ] Dead code causing confusion for new contributors
- [ ] Need to distribute iobt-viz independently from OpenRA

#### Incremental Refactoring Strategy

**Do NOT attempt a big-bang refactor.** Instead, proceed incrementally:

**Stage 6.1: Inventory and measure**
- [ ] Document all files in OpenRA codebase
- [ ] Instrument to identify actually-used vs dead code
- [ ] Measure current build time baseline
- [ ] Identify specific pain points

**Stage 6.2: Remove obviously unused mods (low risk)**
- [ ] Delete mods/cnc/, mods/d2k/, mods/ts/ content (keep mods/ra/ for now as base)
- [ ] Delete OpenRA.Mods.Cnc/, OpenRA.Mods.D2k/ projects
- [ ] Verify build still works, iobt mod still runs

**Stage 6.3: Remove unused game systems (medium risk)**
- [ ] Remove combat system (one system at a time)
- [ ] Remove economy system  
- [ ] Remove AI opponents
- [ ] After each removal: full test cycle

**Stage 6.4: Namespace rename (high risk, defer until necessary)**
- [ ] OpenRA.* → IoBTViz.* (only if truly needed)
- [ ] Requires careful find-replace and testing
- [ ] Breaks all upstream merge potential

#### What to KEEP (do not remove)

```
DEFINITELY KEEP:
- Core rendering pipeline (Graphics/)
- Primitives (WPos, CPos, etc.)
- Widget system (for overlays)
- Map loading
- Sprite/animation system
- Basic movement (for mobile nodes)
- Trait system (it's the architecture)
- YAML loading (MiniYAML)
```

#### What to REMOVE (only after measuring)

```
CANDIDATES FOR REMOVAL (verify unused first):
- Combat system (weapons, damage, projectiles)
- Economy (resources, money, production)  
- AI opponents and combat pathfinding
- Multiplayer game sync (keep viz sync)
- Campaign/mission infrastructure
- Unused mods
```

#### Exit Criteria (if Phase 6 is attempted)
- [ ] Codebase compiles and all tests pass
- [ ] Build time measurably reduced
- [ ] No regressions in Phases 1-5 functionality
- [ ] Documentation updated for new structure

**Recommendation:** Most research projects will NOT need Phase 6. Only proceed if you have specific, measured pain points.

---

### PHASE 7: Advanced Features (Research Extensions)
**Goal**: Research-ready platform with extensibility

#### Deliverables
1. **Extended SAGA scheduler support**
   - Enable all SAGA schedulers (BruteForce, SMT, etc.)
   - Custom ncsim schedulers following SAGA patterns
   - Scheduler comparison utilities and benchmarks
   - Document scheduler interface for researchers

2. **Enhanced routing**
   - Multi-path routing option
   - Load balancing
   - Routing visualization

3. **Mobility model**
   - Configurable movement patterns
   - Connectivity changes based on position
   - Link quality degradation with distance

4. **Failure injection**
   - Node failures at scheduled times
   - Link failures/degradation
   - Recovery behaviors

5. **Distributed mode exploration**
   - DAG injection from any node
   - Local vs global scheduling comparison

---

## 15. TECHNOLOGY STACK

**Note:** Specific technologies are locked in for v1 to avoid branching decisions during implementation. Alternatives listed for future consideration.

### iobt-viz (Visualization Engine)
| Component | Technology | Notes |
|-----------|------------|-------|
| Language | C# (.NET 8.0) | Required (OpenRA) |
| Rendering | OpenGL + GLSL | Required (OpenRA) |
| Config | YAML (MiniYAML format) | Required (OpenRA) |
| Build | Makefile / MSBuild | Required (OpenRA) |

### ncsim (Simulation Engine)
| Component | Technology | Rationale |
|-----------|------------|-----------|
| Language | Python 3.11+ | Required |
| DES Framework | **Custom** (not SimPy) | Full control over determinism, event ordering |
| **Task Mapping** | **SAGA (anrg-saga)** | github.com/anrgusc/saga |
| Graphs | NetworkX | Standard, well-documented |
| Numerics | NumPy, Pandas | Standard scientific Python |
| Config | PyYAML | Simple, widely used |
| CLI | **Click** | Better UX than argparse, decorator-based |

*Future alternatives: SimPy if custom DES proves too complex*

### viz-bridge (Protocol Adapter)
| Component | Technology | Rationale |
|-----------|------------|-----------|
| Language | Python 3.11+ | Same as ncsim |
| Async | asyncio | Standard library, no deps |
| Serialization | **orjson** | 10x faster than stdlib json |
| Transport | TCP sockets | Reliable, ordered |

### ncsim-deck (Control Application)
| Component | Technology | Rationale |
|-----------|------------|-----------|
| Language | Python 3.11+ | Same as ncsim |
| UI Framework | **PyQt6** | More mature than PySide6, better docs |
| Charts | PyQtGraph | Fast, integrates with PyQt |
| Connection | asyncio + TCP | Consistent with viz-bridge |

*Future alternatives: PySide6 if Qt licensing becomes an issue*

---

## 16. ACCEPTANCE CRITERIA (Minimum Viable Demo)

### Visual Integration
- [ ] Compute nodes displayed as distinct entities
- [ ] Network links rendered with dynamic coloring
- [ ] Active transfers shown as animated markers
- [ ] Task states visible (queued/running/completed)

### Simulation Correctness
- [ ] DAG dependencies enforced
- [ ] Data transfers consume link bandwidth
- [ ] Task execution times match compute model
- [ ] Makespan matches manual calculation

### Timing Coherence
- [ ] Pause/resume maintains synchronization
- [ ] Speed changes affect wall-clock only
- [ ] Frame rate variations don't affect sim outcomes
- [ ] Headless mode produces identical results

### Metrics
- [ ] Makespan displayed and correct
- [ ] Per-link utilization graphed
- [ ] Per-node queue length tracked

---

## 17. RISK MITIGATIONS

| Risk | Mitigation |
|------|------------|
| Time desynchronization | Single authoritative sim_time in ncsim; step framing; backpressure |
| Over-coupling sim to viz | Strict separation; ncsim never imports viz code; viz-bridge is only interface |
| Message flood | Interval-based step frames; motion intents not positions; backpressure |
| Debugging complexity | Event logging; deterministic seeds; replay mode |
| OpenRA complexity | Phased removal; keep only rendering core |
| Python performance | Profile before optimizing; Cython/Numba for hot paths if needed |

---

## 18. COMMANDS REFERENCE

### Build & Run
```bash
# Build iobt-viz
cd iobt-viz && make

# Launch visualization
cd iobt-viz && ./launch-game.sh Game.Mod=iobt

# Install ncsim (development mode)
cd ncsim && pip install -e .

# Run ncsim headless
ncsim --scenario scenarios/demo.yaml --output results/

# Run ncsim with visualization
ncsim --scenario scenarios/demo.yaml --viz localhost:9999

# Launch control app
cd ncsim-deck && python -m ncsim_deck

# Run all tests
cd ncsim && pytest
cd viz-bridge && pytest
cd ncsim-deck && pytest
```

### Development
```bash
# Type checking
cd ncsim && mypy ncsim/

# Code formatting
cd ncsim && black ncsim/ tests/
cd viz-bridge && black viz_bridge/ tests/

# Linting
cd ncsim && ruff check ncsim/
```

---

## 19. KEY FILES REFERENCE

| Purpose | File Path |
|---------|-----------|
| OpenRA Lua API | OpenRA/docs/api/lua.md |
| Trait reference | OpenRA/docs/api/traits.md |
| Line rendering | OpenRA/OpenRA.Mods.Common/Graphics/LineAnnotationRenderable.cs |
| Debug overlay | OpenRA/OpenRA.Mods.Common/Traits/CombatDebugOverlay.cs |

---

## 20. GLOSSARY

| Term | Definition |
|------|------------|
| **sim_time** | Simulated time in the modeled system |
| **wall_time** | Real time experienced by user |
| **speed_factor** | Ratio: sim_time advancement per wall_time |
| **step_frame** | Discrete batch of visualization commands |
| **DAG** | Directed Acyclic Graph (task dependencies) |
| **HEFT** | Heterogeneous Earliest Finish Time scheduler |
| **CPOP** | Critical Path on Processor scheduler |
| **SAGA** | Scheduling Algorithms Gathered — scheduler library (github.com/anrgusc/saga) |
| **pinned_task** | Task with fixed node placement (e.g., sensor) |
| **DES** | Discrete Event Simulation |
| **LuaSimBackend** | iobt-viz standalone execution mode for demos/teaching (runs in Lua, no external sim) |
| **BridgeBackend** | ncsim-connected execution mode for research (uses viz-bridge protocol) |
| **VizState** | Shared visualization state model consumed by overlays (backend-agnostic) |
| **VizDelta** | Incremental update to VizState (what changed since last frame) |
| **TaskMapper** | Pluggable component that computes task-to-node assignments (also called "scheduler" in SAGA) |
| **user_intent** | User-driven command from OpenRA UI (e.g., MOVE, STOP) sent to backend |

---

## 21. NOTES FOR CLAUDE CODE

### 21.1 Core Development Principles

1. **Evolutionary, not revolutionary**: iobt-viz transforms FROM OpenRA incrementally, not built from scratch
2. **Fine-grained commits**: One logical change per commit, not "Phase X complete"
3. **Always maintain working state**: Each commit should leave the system runnable and testable
4. **Test after every change**: Does it still build? Does it still run? Any regressions?
5. **Discover tasks as you go**: The checkpoint lists are starting points, not exhaustive — add tasks as needed

### 21.1.1 Component-Specific Development Notes

**Read these files before working on each component:**

| Component | Development Notes |
|-----------|-------------------|
| iobt-viz | `iobt-viz/DEVELOPMENT.md` - Build tips, common errors, inheritance patterns, lessons learned |

These files contain practical lessons learned during development. Always check them first to avoid repeating past mistakes.

**After completing work on a component, add lessons learned to its DEVELOPMENT.md file.**

### 21.2 Working with Reference Copies

**The `reference/` directory is READ-ONLY. Never modify files there.**

When modifying iobt-viz:

```bash
# BEFORE making a change, understand the original:
grep -r "SomeFeature" reference/OpenRA/
cat reference/OpenRA/mods/ra/chrome/ingame-player.yaml

# THEN make targeted changes in iobt-viz/
vim iobt-viz/mods/iobt/chrome/ingame-iobt.yaml

# AFTER, verify changes work:
cd iobt-viz && make && ./launch-game.sh Game.Mod=iobt
```

**When to consult reference/:**
- Before removing any feature
- When something breaks unexpectedly
- To understand how OpenRA implements something
- To find all files related to a feature

### 21.2.1 CRITICAL: Existing LuaSim Code Discovery

**Before modifying any simulation-related code, you MUST inventory and understand what already exists.**

The iobt mod may already contain Lua-based simulation logic that provides:
- DAG definition and execution
- Task state management
- Network connectivity based on positions
- Transfer stall/resume on disconnect

**Discovery checklist (do this FIRST):**

```bash
# Find all Lua files in the mod
find iobt-viz/mods/iobt/ -name "*.lua" -type f

# Look for simulation-related code
grep -r "dag\|task\|transfer\|connectivity\|network" iobt-viz/mods/iobt/ --include="*.lua"

# Check for existing traits related to simulation
grep -r "IoBT\|Simulation\|Network" iobt-viz/OpenRA.Mods.IoBT/ --include="*.cs"

# Document what you find in a temporary file
echo "# Existing LuaSim Code Inventory" > /tmp/luasim-inventory.md
# ... add findings
```

**Principles for working with existing LuaSim code:**

| Do | Don't |
|----|-------|
| Read and understand existing code first | Jump in and start rewriting |
| Wrap existing code in new interfaces | Delete code you don't understand |
| Preserve working demo behavior | "Improve" things that already work |
| Document what you find | Assume the code does what you expect |
| Make minimal changes to existing logic | Refactor prematurely |

**Why this matters:**
The interactive standalone demo is one of the project's strongest features. Breaking it while implementing ncsim integration would be a significant regression. The goal is to **wrap and stabilize**, not rewrite.

### 21.3 Commit Message Format

Use descriptive commit messages that indicate component and change:

```
iobt-viz: add audio mute option
iobt-viz: simplify escape menu (remove surrender/diplomacy)
iobt-viz: remove production sidebar
ncsim: implement event queue
ncsim: integrate SAGA scheduler
viz-bridge: implement step frame protocol
ncsim-deck: add throughput chart widget
```

### 21.4 Checkpoint Workflow

For each checkpoint:

```
1. Understand what needs to change
   - Check reference/ if modifying OpenRA code
   - Read existing code in iobt-viz/ or ncsim/
   
2. Make the smallest change that achieves the goal
   - Don't refactor unrelated code
   - Don't add features not in this checkpoint
   
3. Test immediately
   - Build succeeds?
   - Feature works as intended?
   - No regressions?
   
4. Commit with descriptive message
   
5. Mark checkpoint complete in CLAUDE.md
   - Update [ ] to [x]
   - Add any discovered sub-tasks
   
6. Move to next checkpoint
```

### 21.5 Discovering New Tasks

Tasks will be discovered during development. When this happens:

1. Add the new task to the appropriate checkpoint section in CLAUDE.md
2. Decide if it blocks the current checkpoint or can be deferred
3. If blocking, complete it before marking current checkpoint done
4. If not blocking, add to "Additional Checkpoints" section

Example:
```markdown
#### Additional Checkpoints (discovered during development)
- [x] Fix map loading crash when fog of war disabled
- [ ] Update unit selection highlight color
- [ ] _(add as needed)_
```

### 21.6 Phase Boundaries

Before moving to next phase:
- [ ] All checkpoints in current phase marked [x]
- [ ] Working demo runs successfully
- [ ] All changes committed with descriptive messages
- [ ] No TODO comments left for "later in this phase"
- [ ] CLAUDE.md updated with any discovered tasks
- [ ] Tests passing (for Python components)

### 21.7 Key Reminders

| Don't | Do |
|-------|-----|
| Make large changes in one commit | Make small, focused changes |
| Skip testing "obvious" changes | Test every change, no matter how small |
| Modify reference/ directory | Keep reference/ pristine, always |
| Implement features ahead of schedule | Focus on current checkpoint |
| Leave broken state overnight | Always commit working state |
| Assume checkpoint list is complete | Add discovered tasks as you go |

### 21.8 Separation of Concerns

```
iobt-viz (C#)           NEVER imports from    ncsim (Python)
     │                                              │
     │                                              │
     └──────────► viz-bridge protocol ◄─────────────┘
                  (TCP + JSON only)
```

- ncsim must work fully in headless mode without iobt-viz
- iobt-viz must work with any viz-bridge client, not just ncsim
- viz-bridge is the ONLY coupling point

### 21.9 Python Environment Setup

```bash
# Create virtual environment for the project
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install all Python components in development mode
pip install -e ncsim/
pip install -e viz-bridge/
pip install -e ncsim-deck/

# Install SAGA scheduler
pip install anrg-saga
```

### 21.10 Building and Testing

```bash
# iobt-viz (C#)
cd iobt-viz
make                              # Build
./launch-game.sh Game.Mod=iobt    # Run

# ncsim (Python)
cd ncsim
pytest                            # Run tests
ncsim --scenario scenarios/demo_simple.yaml  # Run simulation

# Full integration test
# Terminal 1:
cd iobt-viz && ./launch-game.sh Game.Mod=iobt
# Terminal 2:
cd ncsim && ncsim --scenario demo.yaml --viz localhost:9999
# Terminal 3:
cd ncsim-deck && python -m ncsim_deck
```

# ncsim-viz

Interactive web visualization for [ncsim](../) trace playback. Configure experiments, run simulations, and explore network topology, DAG structure, scheduling decisions, and animated execution replay.

## Quick Start

### 1. Install dependencies

```bash
# Frontend
cd viz/
npm install

# Backend
cd viz/server/
pip install -r requirements.txt

# ncsim (if not already installed)
pip install -e ..
```

### 2. Start the backend API server (port 8000)

```bash
cd viz/server/
python run.py
```

The backend runs ncsim experiments and serves saved results. Required for "Configure & Run" and browsing experiments.

### 3. Start the frontend dev server (port 5173)

In a separate terminal:

```bash
cd viz/
npm run dev
```

### 4. Open the app

Go to **http://localhost:5173**

## Usage

The home page offers two paths:

### Configure & Run

Build a scenario from scratch using the form UI:
- **Basic config**: experiment name, dynamically discovered SAGA/built-in scheduler, routing, seed
- **Interference model**: none, proximity, CSMA/CA clique, CSMA/CA Bianchi (with full WiFi RF config)
- **Network topology**: presets (line, ring, star, mesh, grid) with editable node/link tables
- **DAG structure**: presets (chain, fork-join, diamond, parallel) with editable task/edge tables
- **YAML preview**: live preview of the generated scenario YAML
- Click **Run Experiment** to execute ncsim via the backend and auto-load results

### Visualize Existing

- **Experiment browser**: click any saved experiment card to load it instantly
- **Manual file loading**: drag-and-drop or file picker for scenario.yaml, trace.jsonl, metrics.json
- **Open Run Folder**: select an ncsim output directory to load all 3 files at once

## Visualization Tabs

Once data is loaded, six tabs are available:

| Tab | Content |
|-----|---------|
| **Overview** | Summary metrics, node/link utilization bars, WiFi config |
| **Network** | Interactive D3 topology diagram with pan/zoom and tooltips |
| **DAG** | Task dependency graph colored by assigned node |
| **Schedule** | Static Gantt chart of the full execution |
| **Simulation** | Animated replay with network + live Gantt + event log |
| **Parameters** | Full config inspector (scenario, scheduler, routing, interference, RF) |

### Replay the simulation

- Go to the **Simulation** tab
- Press **Space** to play/pause
- Use **Left/Right arrows** to step through events
- Change speed with the **0.25x-10x** buttons at bottom-right
- Click any event in the log to jump to that time

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Space | Play / Pause |
| Left / Right | Step backward / forward by event |
| Shift+Left/Right | Jump 10% |
| Home / End | Jump to start / end |
| + / - | Speed up / down |
| 1-6 | Switch tabs |
| D | Toggle dark / light mode |
| ? | Show shortcut help |

## Architecture

```
Browser (Vite :5173)                    Python Backend (:8000)
+-----------------------+               +--------------------+
|  HomePage             |               |  FastAPI           |
|  +- Configure & Run --POST /api/run-->|  runs ncsim        |
|  +- Visualize --------GET /api/experiments-->scan dirs     |
+-----------------------+               +--------------------+
Vite proxies /api/* to localhost:8000
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/experiments` | GET | List all saved experiments with summary metrics |
| `/api/experiments/{name}` | GET | Get full files (scenario, trace, metrics) for an experiment |
| `/api/run` | POST | Run ncsim with provided scenario YAML, return results |

## Manual Simulation (without backend)

You can also generate trace files manually and load them via drag-and-drop:

```bash
python -m ncsim --scenario scenarios/parallel_spread.yaml --output /tmp/my-run --seed 42
```

This creates three files: `scenario.yaml`, `trace.jsonl`, `metrics.json`

## Tech Stack

- React 19 + TypeScript + Vite
- D3.js for network/Gantt visualizations
- Dagre for DAG layout
- Tailwind CSS v4 with dark/light theme
- Lucide React for icons
- FastAPI + uvicorn (backend)

## Building for Production

```bash
npm run build
```

Static files are output to `dist/`. Serve with any static file server.

## Sample Data

Pre-generated sample runs are included in `public/sample-runs/` for quick testing without running ncsim.

## Requirements

- **Node.js** 18+ (frontend)
- **Python** 3.12+ (backend)
- **ncsim** installed (`pip install -e ..` from repo root)

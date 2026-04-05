# Viz Setup

This page walks through installing dependencies and starting the ncsim-viz frontend and backend servers.

---

## Prerequisites

Before setting up ncsim-viz, ensure you have:

| Requirement | Minimum Version | Check Command |
|---|---|---|
| Python | 3.10+ | `python --version` |
| Node.js | 18+ | `node --version` |
| npm | 9+ | `npm --version` |
| ncsim | Installed in editable mode | `python -c "import ncsim"` |

!!! warning "ncsim must be installed first"
    The backend invokes ncsim as a subprocess. If you have not yet installed ncsim, follow the [Installation](../getting-started/installation.md) guide first:

    ```bash
    pip install -e .
    ```

---

## Install Backend Dependencies

The backend requires FastAPI and uvicorn. Install them from the server requirements file:

```bash
pip install -r viz/server/requirements.txt
```

This installs:

- `fastapi>=0.115.0` -- the async web framework that serves the API
- `uvicorn>=0.34.0` -- the ASGI server that runs FastAPI

---

## Install Frontend Dependencies

Install the Node.js packages for the React frontend:

```bash
cd viz
npm install
cd ..
```

Key frontend dependencies include:

| Package | Purpose |
|---|---|
| `react` / `react-dom` | UI framework (React 19) |
| `d3` | Network graph and Gantt chart rendering |
| `dagre` | Hierarchical DAG layout algorithm |
| `js-yaml` | YAML parsing for scenario preview |
| `lucide-react` | Icon library |
| `tailwindcss` | Utility-first CSS framework (v4) |
| `vite` | Development server and build tool |

---

## Start the Servers

ncsim-viz requires two servers running simultaneously. Open two terminal windows:

### Terminal 1 -- Backend

```bash
cd viz/server
python run.py
```

You should see output similar to:

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
```

The FastAPI backend is now serving on **http://localhost:8000**. It auto-reloads when you edit server files.

### Terminal 2 -- Frontend

```bash
cd viz
npm run dev
```

You should see output similar to:

```
  VITE v7.x.x  ready in XXX ms

  ➜  Local:   http://localhost:5173/
```

The Vite development server is now serving on **http://localhost:5173**.

!!! tip "Open your browser"
    Navigate to **http://localhost:5173** to access the ncsim-viz UI.

---

## How the Proxy Works

The Vite configuration (`viz/vite.config.ts`) includes a proxy rule that forwards all `/api/*` requests from the frontend dev server (port 5173) to the FastAPI backend (port 8000):

```typescript
server: {
  proxy: {
    '/api': 'http://127.0.0.1:8000',
  },
},
```

This means:

- **Both servers must be running** for the Configure & Run workflow (which calls `POST /api/run`)
- **Visualize Existing** mode also calls `/api/experiments` to list and load saved experiments, so the backend is needed for browsing sample runs as well
- The browser always connects to port 5173 -- it never talks directly to port 8000

---

## Verify the Setup

After both servers are running, verify everything works:

1. **Home page** -- Open http://localhost:5173 and confirm you see the home page with two workflow cards: "Configure & Run" and "Visualize Existing".

2. **Browse experiments** -- Click "Visualize Existing". You should see a list of saved experiments from the `sample-runs/` directory (if any exist).

3. **Load an experiment** -- Click on any listed experiment. The Overview tab should appear, displaying metrics such as makespan, task count, and utilization bars.

4. **Run an experiment** -- Click "Configure & Run", leave the default settings, and click "Run Experiment". The backend should execute ncsim and display the results.

!!! note "No sample runs?"
    If the experiment browser shows no experiments, the `viz/public/sample-runs/` directory may be empty. Run a simulation first using the CLI or the Configure & Run workflow to populate it.

---

## Production Build

To create an optimized production build of the frontend:

```bash
cd viz
npm run build
```

This runs the TypeScript compiler followed by Vite's production bundler. The output is written to the `viz/dist/` directory. You can serve these static files with any web server, but you will still need the FastAPI backend running for experiment execution and browsing.

!!! info "Preview the production build"
    After building, you can preview the production output locally:

    ```bash
    cd viz
    npm run preview
    ```

    This starts a local server serving the `dist/` directory, useful for verifying the build before deployment.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `ModuleNotFoundError: No module named 'ncsim'` | Install ncsim in editable mode: `pip install -e .` from the repo root |
| `ModuleNotFoundError: No module named 'fastapi'` | Run `pip install -r viz/server/requirements.txt` |
| Port 8000 already in use | Stop the other process, or edit `viz/server/run.py` to use a different port |
| Port 5173 already in use | Vite will automatically try the next available port (5174, 5175, etc.) |
| "Run Experiment" button shows error | Confirm the backend is running on port 8000 and the proxy is configured correctly |
| CORS errors in browser console | Make sure you are accessing the frontend through port 5173 (not 8000 directly) |

---

## Next Steps

- **[Configure & Run](configure-run.md)** -- Build and run an experiment using the form editor
- **[Visualization Tabs](visualization-tabs.md)** -- Explore the six visualization views

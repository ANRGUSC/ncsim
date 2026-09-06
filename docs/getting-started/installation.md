# Installation

This guide walks through installing ncsim, its dependencies, and the optional web visualization frontend.

---

## Prerequisites

Verify that the following tools are installed and meet the minimum version requirements:

| Tool | Minimum Version | Check Command | Notes |
|------|----------------|---------------|-------|
| Python | 3.12+ | `python --version` | Required by ncsim's SAGA integration |
| pip | 21+ | `pip --version` | Required |
| Git | 2.30+ | `git --version` | Required for cloning the repo |
| Node.js | 18+ | `node --version` | Viz frontend only |
| npm | 9+ | `npm --version` | Viz frontend only |

!!! note "Node.js is optional"
    Node.js and npm are only required if you plan to use the web visualization UI. The core simulator and CLI work with just Python.

---

## Clone the Repository

The recommended way to get started is to clone the full repository. This gives you the example scenarios, experiment scripts, documentation, and web visualization UI:

```bash
git clone https://github.com/ANRGUSC/ncsim.git
cd ncsim
```

---

## Install ncsim

### Editable Install (Recommended)

Install ncsim in editable (development) mode so that changes to the source code take effect immediately:

```bash
pip install -e .
```

This installs the following dependencies automatically:

| Package | Version | Purpose |
|---------|---------|---------|
| [anrg-saga](https://github.com/ANRGUSC/saga) | >= 2.0.4 | 22 SAGA static batch scheduling algorithms; PEFT is available with 2.1.0 |
| [networkx](https://networkx.org/) | >= 3.0 | Graph data structures for routing and conflict graphs |
| [pyyaml](https://pyyaml.org/) | >= 6.0 | YAML scenario file parsing |

!!! info "Optional PEFT support"
    The latest SAGA version on PyPI is 2.0.4. It provides all of ncsim's
    registered SAGA schedulers except PEFT. To expose PEFT as the 23rd
    scheduler, use this two-command sequence in place of the single editable
    install above:

    ```bash
    python -m pip install "anrg-saga @ git+https://github.com/ANRGUSC/saga.git@v2.1.0"
    python -m pip install -e .
    ```

    ncsim discovers PEFT at startup, so the CLI and visualization scheduler
    lists update automatically. Run `ncsim --help` to see the active list.

To also install development dependencies (pytest, pytest-cov), use:

```bash
pip install -e ".[dev]"
```

### PyPI Install (Core Only)

Alternatively, install just the core simulator package from PyPI:

```bash
pip install anrg-ncsim
```

!!! warning "PyPI install does not include extras"
    The `pip install anrg-ncsim` command installs only the core simulator library and the `ncsim` CLI. It does **not** include the example scenarios, experiment scripts, visualization UI, or documentation. Use this option if you want to integrate ncsim as a library in your own project and will write your own scenario YAML files.

### Verify the CLI

After installation, confirm that the `ncsim` command is available:

```bash
ncsim --version
```

Expected output:

```
ncsim 1.1.0
```

---

## Install the Visualization Backend

The visualization backend is a FastAPI server that connects the web UI to ncsim. Install its dependencies from the `viz/server/` directory:

```bash
pip install -r viz/server/requirements.txt
```

This installs:

| Package | Version | Purpose |
|---------|---------|---------|
| [FastAPI](https://fastapi.tiangolo.com/) | >= 0.115.0 | REST API framework |
| [uvicorn](https://www.uvicorn.org/) | >= 0.34.0 | ASGI server |

---

## Install the Visualization Frontend

The frontend is a React application built with Vite. Install its Node.js dependencies:

```bash
cd viz
npm install
cd ..
```

!!! tip "Stay in the project root"
    After running `npm install`, return to the project root directory so that subsequent `ncsim` commands work with the correct relative paths to scenario files.

---

## Verify the Installation

### Verify the CLI

Run the included `demo_simple` scenario to confirm the simulator works end to end:

```bash
ncsim --scenario scenarios/demo_simple.yaml --output results/verify
```

You should see output ending with:

```
=== Simulation Complete ===
Scenario: Simple Demo
Scheduler: heft
Routing: direct
Interference: proximity
  radius=15.0
Seed: 42
Makespan: 3.000000 seconds
Total events: 7
Status: completed
```

Confirm that three output files were created:

```bash
ls results/verify/
```

```
metrics.json    scenario.yaml    trace.jsonl
```

### Verify the Visualization

Start the backend and frontend in two separate terminals:

=== "Terminal 1 -- Backend"

    ```bash
    cd viz/server
    python run.py
    ```

    The backend starts on **http://localhost:8000**.

=== "Terminal 2 -- Frontend"

    ```bash
    cd viz
    npm run dev
    ```

    The frontend starts on **http://localhost:5173**.

Open **http://localhost:5173** in your browser. You should see the ncsim-viz interface with a Configure & Run panel.

### Run the Test Suite

To run the full test suite and confirm everything is functioning correctly:

```bash
pytest
```

Or equivalently:

```bash
python -m pytest tests/ -v
```

The test suite includes unit tests for the event queue, execution engine, scheduling, routing, WiFi physics, interference models, and end-to-end acceptance tests.

---

## Troubleshooting

### 1. `ModuleNotFoundError: No module named 'ncsim'`

**Cause:** ncsim is not installed in your current Python environment.

**Fix:** Run `pip install -e .` from the repository root. If you are using a virtual environment, make sure it is activated first.

```bash
# Activate your virtual environment (if using one)
source venv/bin/activate    # Linux/macOS
venv\Scripts\activate       # Windows

# Install ncsim
pip install -e .
```

### 2. `ncsim: command not found`

**Cause:** The pip scripts directory is not on your system PATH.

**Fix:** Either add pip's script directory to your PATH, or invoke ncsim as a Python module:

```bash
# Option A: Run as a module
python -m ncsim --scenario scenarios/demo_simple.yaml --output results/test

# Option B: Find and add the scripts directory
python -m site --user-base
# Add the bin/ (Linux/macOS) or Scripts/ (Windows) subdirectory to your PATH
```

### 3. Frontend shows "Network Error" when running an experiment

**Cause:** The FastAPI backend server is not running, or it is running on a different port than expected.

**Fix:** Start the backend in a separate terminal:

```bash
cd viz/server
python run.py
```

Confirm it is listening on **http://localhost:8000** before using the frontend.

### 4. Port 8000 or 5173 is already in use

**Cause:** Another process is occupying the port.

**Fix:** Find and stop the conflicting process, or run on a different port:

=== "Backend (port 8000)"

    ```bash
    # Find the process
    lsof -i :8000          # Linux/macOS
    netstat -ano | findstr :8000  # Windows

    # Or run on a different port
    cd viz/server
    uvicorn main:app --port 8001
    ```

=== "Frontend (port 5173)"

    ```bash
    # Vite will automatically try the next available port (5174, 5175, ...)
    # Or set it explicitly:
    cd viz
    npx vite --port 3000
    ```

### 5. `npm install` fails with errors

**Cause:** Node.js version is too old. The frontend requires Node.js 18 or later.

**Fix:** Update Node.js to version 18+ and try again:

```bash
node --version    # Check current version

# Update using your package manager, nvm, or download from https://nodejs.org/
nvm install 18    # If using nvm
npm install       # Retry
```

### 6. Visualization shows no experiments / empty experiment list

**Cause:** The `viz/public/sample-runs/` directory is missing or contains no experiment results.

**Fix:** Run a simulation with output directed to the sample-runs directory, or copy an existing results folder there:

```bash
ncsim --scenario scenarios/demo_simple.yaml --output viz/public/sample-runs/demo
```

Then refresh the visualization in your browser.

### 7. `ImportError: cannot import name ... from 'saga'`

**Cause:** The `anrg-saga` package is not installed, or an incompatible version is installed.

**Fix:** Install or upgrade anrg-saga to version 2.0.4 or later:

```bash
pip install "anrg-saga>=2.0.4"
```

If you have a different package named `saga` installed, it may conflict. Uninstall it first:

```bash
pip uninstall saga
pip install "anrg-saga>=2.0.4"
```

---

## Next Steps

With ncsim installed, head to the [Quick Start](quickstart.md) guide to run your first simulation in under five minutes.

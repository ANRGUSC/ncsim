# Troubleshooting

Solutions for common issues encountered when installing, running, or
visualizing ncsim simulations.

---

## Installation Issues

### ModuleNotFoundError: No module named 'ncsim'

**Cause:** ncsim is not installed in the active Python environment.

**Fix:** Install ncsim in editable mode from the repository root:

```bash
pip install -e .
```

If you are using a virtual environment, make sure it is activated first:

```bash
# Linux / macOS
source venv/bin/activate

# Windows
venv\Scripts\activate

# Then install
pip install -e .
```

!!! tip "Verify installation"
    Confirm ncsim is importable:

    ```bash
    python -c "import ncsim; print('OK')"
    ```

---

### ncsim: command not found

**Cause:** The pip scripts directory is not on your system PATH.

**Fix:** Use `python -m ncsim` as an alternative, or add pip's bin
directory to your PATH:

```bash
# Option A: Run as a module (always works)
python -m ncsim --scenario scenarios/demo_simple.yaml --output results/test

# Option B: Find the scripts directory
python -m site --user-base
# Add the bin/ (Linux/macOS) or Scripts/ (Windows) subdirectory to PATH
```

---

### ImportError: anrg-saga

**Cause:** The `anrg-saga` package is not installed, or a conflicting
`saga` package is present.

**Fix:** Install or upgrade anrg-saga:

```bash
pip install "anrg-saga>=2.0.3"
```

If you have a different package named `saga` installed, uninstall it
first:

```bash
pip uninstall saga
pip install "anrg-saga>=2.0.3"
```

!!! warning "pygraphviz on Windows"
    The `anrg-saga` package has an optional dependency on `pygraphviz`,
    which can be difficult to install on Windows. If the full install
    fails, install without optional dependencies:

    ```bash
    pip install anrg-saga --no-deps
    pip install networkx numpy scipy pandas pydantic tqdm
    ```

---

### SAGA library not available (warning at runtime)

**Cause:** The `anrg-saga` package is not importable, so HEFT and CPOP
schedulers are unavailable.

**Fix:** Reinstall anrg-saga:

```bash
pip install "anrg-saga>=2.0.3"
```

When SAGA is unavailable, ncsim falls back to Round Robin scheduling
with a warning. HEFT and CPOP will not be available until SAGA is
properly installed.

---

### pip install -e . fails with build errors

**Cause:** Missing build dependencies or incompatible Python version.

**Fix:**

1. Verify Python version is 3.10+: `python --version`
2. Upgrade pip and setuptools: `pip install --upgrade pip setuptools`
3. Retry: `pip install -e .`

---

## CLI Issues

### "to_node 'X' not found"

**Cause:** A link in the scenario YAML references a node ID that does
not exist in the `nodes:` list.

**Fix:** Open the scenario YAML and verify that every `from:` and `to:`
value in the `links:` section matches an `id:` in the `nodes:` section.

```yaml
nodes:
  - id: n0     # <-- node IDs defined here
  - id: n1

links:
  - id: l01
    from: n0   # <-- must match a node ID above
    to: n1     # <-- must match a node ID above
```

---

### No direct link between nodes

**Cause:** The scheduler assigned communicating tasks to nodes that are
not directly connected, but `direct` routing is active.

**Fix:** Switch to multi-hop routing:

```bash
ncsim --scenario scenario.yaml --output results/ --routing widest_path
```

Or use `--routing shortest_path`. Both support multi-hop data transfers
through intermediate relay nodes.

!!! info "Why this happens"
    HEFT and CPOP choose node assignments based on compute speed and
    may place dependent tasks on non-adjacent nodes. Direct routing
    only works when every communicating pair has an explicit link.
    Multi-hop routing resolves this by forwarding data through
    intermediate nodes.

---

### Simulation takes very long

**Cause:** Large networks with the `csma_bianchi` interference model.
Bianchi recalculates interference factors for all active links whenever
any transfer starts or completes.

**Fix:** Several options, in order of preference:

1. **Use `csma_clique` instead** -- computes bandwidth once at setup,
   no dynamic recalculation:

    ```bash
    ncsim --scenario scenario.yaml --output results/ --interference csma_clique
    ```

2. **Reduce network size** -- fewer links means fewer recalculations.

3. **Use `proximity` interference** -- simpler distance-based model:

    ```bash
    ncsim --scenario scenario.yaml --output results/ --interference proximity
    ```

4. **Disable interference entirely** -- for wired networks or when
   interference is not relevant:

    ```bash
    ncsim --scenario scenario.yaml --output results/ --interference none
    ```

---

### Invalid scheduler / routing / interference value

**Cause:** Unrecognized value passed to `--scheduler`, `--routing`, or
`--interference`.

**Fix:** Use one of the supported values:

| Flag | Valid Values |
|---|---|
| `--scheduler` | `heft`, `cpop`, `round_robin`, `manual` |
| `--routing` | `direct`, `widest_path`, `shortest_path` |
| `--interference` | `none`, `proximity`, `csma_clique`, `csma_bianchi` |

---

### Unexpected makespan (all schedulers produce the same result)

**Cause:** All tasks have `pinned_to` set, which overrides the
scheduler's placement decisions.

**Fix:** If you want the scheduler to make placement decisions, remove
the `pinned_to` fields from the task definitions in the scenario YAML.

---

## Visualization Issues

### Frontend shows "Network Error" on Run

**Cause:** The FastAPI backend is not running, or there is a CORS /
proxy configuration issue.

**Fix:**

1. Verify the backend is running:

    ```bash
    cd viz/server
    python run.py
    ```

2. Check the terminal for error messages (missing modules, port
   conflicts).

3. Ensure you are accessing the frontend at `http://localhost:5173`
   (not port 8000 directly). The Vite proxy forwards `/api/*` requests
   to the backend.

---

### Port 8000 or 5173 already in use

**Cause:** Another process is occupying the required port.

**Fix:** Find and stop the conflicting process:

=== "Linux / macOS"

    ```bash
    # Find the process using port 8000
    lsof -i :8000

    # Kill it (replace PID with the actual process ID)
    kill PID
    ```

=== "Windows"

    ```bash
    # Find the process using port 8000
    netstat -ano | findstr :8000

    # Kill it (replace PID with the actual process ID)
    taskkill /PID PID /F
    ```

Alternatively, change the port:

```bash
# Backend on a different port
cd viz/server
uvicorn main:app --port 8001

# Frontend on a different port
cd viz
npx vite --port 3000
```

!!! warning "Proxy configuration"
    If you change the backend port, update the proxy setting in
    `viz/vite.config.ts` to match the new port.

---

### npm install fails

**Cause:** Node.js version is too old. The frontend requires Node.js 18
or later.

**Fix:** Upgrade Node.js:

```bash
# Check current version
node --version

# Upgrade (using nvm)
nvm install 18
nvm use 18

# Or download from https://nodejs.org/

# Retry installation
cd viz
npm install
```

---

### Viz shows no experiments in browser

**Cause:** The `viz/public/sample-runs/` directory is missing or does
not contain any experiment results.

**Fix:** Run a simulation and copy the output to the sample-runs
directory:

```bash
# Run a simulation
ncsim --scenario scenarios/demo_simple.yaml --output results/demo

# Copy to sample-runs
cp -r results/demo viz/public/sample-runs/demo
```

Then refresh the browser. The experiment should appear in the list.

---

### Visualization is slow or unresponsive

**Cause:** Very large traces (thousands of events) can slow down the
D3 visualizations.

**Fix:**

- Use a smaller scenario for interactive exploration.
- For large experiments, use the CLI analysis tools (`analyze_trace.py`)
  instead of the web UI.
- Ensure hardware acceleration is enabled in your browser settings.

---

## Common Errors Reference Table

| Error | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: ncsim` | Not installed | `pip install -e .` |
| `ncsim: command not found` | PATH issue | Use `python -m ncsim` |
| `ImportError: anrg-saga` | Missing dependency | `pip install "anrg-saga>=2.0.3"` |
| `"to_node 'X' not found"` | Invalid node reference in YAML | Check that all link endpoints match node IDs |
| `No direct link` | Direct routing + non-adjacent nodes | Use `--routing widest_path` |
| `Network Error` in viz | Backend not running | Start `python run.py` on port 8000 |
| `Port in use` | Port conflict | Kill conflicting process or change port |
| `npm install` fails | Old Node.js | Upgrade to Node.js 18+ |
| `SAGA not available` | anrg-saga not importable | `pip install "anrg-saga>=2.0.3"` |
| Same makespan for all schedulers | All tasks have `pinned_to` | Remove `pinned_to` to let scheduler decide |

---

## Getting More Help

If your issue is not covered here:

1. **Enable verbose logging** to get detailed debug output:

    ```bash
    ncsim --scenario scenario.yaml --output results/ --verbose
    ```

2. **Check the trace file** (`trace.jsonl`) for unexpected event
   sequences.

3. **Review the metrics file** (`metrics.json`) for error messages in
   the `error_message` field.

4. **File an issue** on the
   [GitHub repository](https://github.com/ANRGUSC/ncsim/issues) with:
    - The scenario YAML file
    - The full error message or unexpected output
    - Your Python version (`python --version`)
    - Your ncsim version (`ncsim --version`)

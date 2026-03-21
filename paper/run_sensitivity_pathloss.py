#!/usr/bin/env python3
"""Sensitivity analysis: sweep path loss exponent to show regime transitions.

Varies the path loss exponent from 2.0 (free-space) to 4.0 (heavy indoor),
recomputing WiFi PHY rates at each value. Compares makespan under no
interference vs csma_bianchi to quantify how propagation environment
affects the gap between ideal and realistic wireless scheduling.

Network: 3x3 grid (40m spacing, grid+diagonal links)
DAG:     10-task diamond (medium)
Scheduler: heft
Routing: shortest_path
"""

import json
import math
import os
import subprocess
import sys
from pathlib import Path

# Allow importing ncsim from parent directory
sys.path.insert(0, str(Path(__file__).parent.parent))
from ncsim.models.wifi import (
    RFConfig, received_power_dBm, snr_dB, snr_to_rate_mbps,
    rate_mbps_to_MBps,
)

# --- Fixed Parameters --------------------------------------------

COMPUTE_COST = 500
DATA_SIZE = 10.0          # MB
GRID_SPACING = 40         # meters
SEED = 42

# Heterogeneous compute capacities cycled across nodes
_CAPACITIES = [200, 100, 150, 80, 300, 120, 250, 180, 160, 90, 220, 140, 280, 110, 190, 170]

# Path loss exponents to sweep: free-space through heavy indoor
PATH_LOSS_EXPONENTS = [2.0, 2.5, 3.0, 3.5, 4.0]

# Interference models to compare
INTERFERENCE_MODES = ["none", "csma_bianchi"]

# Output directory for results
OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_results")
WORKDIR = os.path.join(OUTDIR, "_pathloss_work")


# --- WiFi Rate Computation ---------------------------------------

def make_rf_config(path_loss_exponent):
    """Create an RFConfig with the specified path loss exponent."""
    return RFConfig(path_loss_exponent=path_loss_exponent)


def euclidean_distance(x1, y1, x2, y2):
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def compute_wifi_rate(dist, rf):
    """Compute WiFi PHY rate in MB/s for a given distance and RF config."""
    rx_power = received_power_dBm(rf.tx_power_dBm, dist, rf, 0.0)
    link_snr = snr_dB(rx_power, rf.noise_floor_dBm)
    rate_mbps = snr_to_rate_mbps(link_snr, rf.wifi_standard, rf.channel_width_mhz)
    return rate_mbps_to_MBps(rate_mbps)


# --- Network Generation -----------------------------------------

def generate_network(rf):
    """Generate a 3x3 grid mesh with WiFi rates computed under the given RF config.

    Returns (nodes, links) with explicit bandwidth on each link.
    """
    n = 3  # 3x3 grid
    nodes = []
    for row in range(n):
        for col in range(n):
            idx = row * n + col
            nodes.append({
                "id": f"n{idx}",
                "compute_capacity": _CAPACITIES[idx % len(_CAPACITIES)],
                "x": col * GRID_SPACING,
                "y": row * GRID_SPACING,
            })

    # Collect undirected link pairs (grid + diagonal)
    pairs = set()

    def add_pair(r1, c1, r2, c2):
        if 0 <= r2 < n and 0 <= c2 < n:
            a, b = r1 * n + c1, r2 * n + c2
            pairs.add((min(a, b), max(a, b)))

    for row in range(n):
        for col in range(n):
            add_pair(row, col, row, col + 1)      # horizontal
            add_pair(row, col, row + 1, col)       # vertical
            if (row + col) % 2 == 0:               # diagonal (checkerboard)
                add_pair(row, col, row + 1, col + 1)
            else:
                add_pair(row, col, row + 1, col - 1)

    # Generate bidirectional links with WiFi-computed bandwidths
    links = []
    for a, b in sorted(pairs):
        na, nb = f"n{a}", f"n{b}"
        dist = euclidean_distance(
            nodes[a]["x"], nodes[a]["y"],
            nodes[b]["x"], nodes[b]["y"],
        )
        rate = compute_wifi_rate(dist, rf)
        links.append({"id": f"l_{na}_{nb}", "from": na, "to": nb, "bandwidth": rate})
        links.append({"id": f"l_{nb}_{na}", "from": nb, "to": na, "bandwidth": rate})

    return nodes, links


# --- DAG Generation ----------------------------------------------

def make_dag_medium():
    """Diamond pipeline: source -> 4 parallel -> 4 parallel -> sink (10 tasks)."""
    tasks = [{"id": f"T{i}", "compute_cost": COMPUTE_COST} for i in range(10)]
    edges = []
    # T0 -> T1,T2,T3,T4
    for i in range(1, 5):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": DATA_SIZE})
    # T1,T2,T3,T4 -> T5,T6,T7,T8 (selective cross-connections)
    for i in range(1, 5):
        for j in range(5, 9):
            if (i + j) % 2 == 0:
                edges.append({"from": f"T{i}", "to": f"T{j}", "data_size": DATA_SIZE})
    # T5,T6,T7,T8 -> T9
    for i in range(5, 9):
        edges.append({"from": f"T{i}", "to": "T9", "data_size": DATA_SIZE})
    return tasks, edges


# --- YAML Generation --------------------------------------------

def generate_scenario_yaml(path_loss_exp):
    """Generate scenario YAML with WiFi rates computed for the given path loss exponent."""
    rf = make_rf_config(path_loss_exp)
    nodes, links = generate_network(rf)
    tasks, edges = make_dag_medium()

    yaml = "scenario:\n"
    yaml += f'  name: "sensitivity_pathloss_n{path_loss_exp:.1f}"\n'
    yaml += "  network:\n    nodes:\n"
    for nd in nodes:
        yaml += (f"      - {{id: {nd['id']}, compute_capacity: {nd['compute_capacity']}, "
                 f"position: {{x: {nd['x']}, y: {nd['y']}}}}}\n")
    yaml += "    links:\n"
    for link in links:
        yaml += (f"      - {{id: {link['id']}, from: {link['from']}, to: {link['to']}, "
                 f"bandwidth: {link['bandwidth']:.4f}}}\n")
    yaml += "  dags:\n    - id: dag_1\n      inject_at: 0.0\n      tasks:\n"
    for t in tasks:
        yaml += f"        - {{id: {t['id']}, compute_cost: {t['compute_cost']}}}\n"
    yaml += "      edges:\n"
    for e in edges:
        yaml += f"        - {{from: {e['from']}, to: {e['to']}, data_size: {e['data_size']}}}\n"
    yaml += "  config:\n"
    yaml += "    scheduler: heft\n"
    yaml += f"    seed: {SEED}\n"
    yaml += "    routing: shortest_path\n"
    yaml += "    interference: none\n"
    return yaml


# --- Subprocess Runner -------------------------------------------

def run_scenario(yaml_str, run_label, interference, path_loss_exp):
    """Write scenario YAML, invoke ncsim, return output directory."""
    outdir = os.path.join(WORKDIR, run_label)
    os.makedirs(outdir, exist_ok=True)

    input_dir = os.path.join(WORKDIR, "_inputs", run_label)
    os.makedirs(input_dir, exist_ok=True)
    yaml_path = os.path.join(input_dir, "scenario.yaml")
    with open(yaml_path, "w") as f:
        f.write(yaml_str)

    cmd = [
        sys.executable, "-m", "ncsim",
        "--scenario", yaml_path,
        "--output", outdir,
        "--interference", interference,
        "--scheduler", "heft",
        "--routing", "shortest_path",
        "--seed", str(SEED),
        "--path-loss-exponent", str(path_loss_exp),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR running {run_label}:", file=sys.stderr)
        print(f"    stderr: {result.stderr[-500:] if result.stderr else '(empty)'}", file=sys.stderr)
        return None
    return outdir


def get_makespan(outdir):
    """Extract makespan from metrics.json in the output directory."""
    path = os.path.join(outdir, "metrics.json")
    try:
        with open(path) as f:
            data = json.load(f)
        if data.get("status") == "error":
            return None
        return data["makespan"]
    except Exception:
        return None


# --- Main --------------------------------------------------------

def main():
    os.makedirs(OUTDIR, exist_ok=True)
    os.makedirs(WORKDIR, exist_ok=True)

    print()
    print("=" * 70)
    print("  Path Loss Exponent Sensitivity Analysis")
    print("  Network: 3x3 grid | DAG: 10-task diamond | Scheduler: HEFT")
    print(f"  compute_cost={COMPUTE_COST}, data_size={DATA_SIZE}MB, spacing={GRID_SPACING}m")
    print("=" * 70)
    print()

    # Show WiFi rates at each path loss exponent for reference
    dist_grid = GRID_SPACING
    dist_diag = GRID_SPACING * math.sqrt(2)
    print("  WiFi PHY rates (MB/s) at each path loss exponent:")
    print(f"  {'n':>5s}  {'40m (grid)':>12s}  {'56.6m (diag)':>14s}")
    for n_val in PATH_LOSS_EXPONENTS:
        rf = make_rf_config(n_val)
        r_grid = compute_wifi_rate(dist_grid, rf)
        r_diag = compute_wifi_rate(dist_diag, rf)
        print(f"  {n_val:5.1f}  {r_grid:12.3f}  {r_diag:14.3f}")
    print()

    # Run simulations
    results = {}  # (path_loss_exp, interference) -> makespan
    total = len(PATH_LOSS_EXPONENTS) * len(INTERFERENCE_MODES)
    count = 0

    for n_val in PATH_LOSS_EXPONENTS:
        yaml_str = generate_scenario_yaml(n_val)
        for intf in INTERFERENCE_MODES:
            count += 1
            label = f"n{n_val:.1f}_{intf}"
            print(f"  [{count:>2d}/{total}] path_loss_exp={n_val:.1f}, interference={intf}...",
                  end=" ", flush=True)
            outdir = run_scenario(yaml_str, label, intf, n_val)
            if outdir is None:
                results[(n_val, intf)] = None
                print("FAILED")
            else:
                ms = get_makespan(outdir)
                results[(n_val, intf)] = ms
                print(f"{ms:.4f}s" if ms is not None else "ERROR")

    print()

    # --- Results Table --------------------------------------------

    print(f"  {'n':>5s}  {'none (s)':>10s}  {'bianchi (s)':>12s}  {'slowdown':>10s}")
    print(f"  {'-' * 45}")

    json_results = []
    for n_val in PATH_LOSS_EXPONENTS:
        none_ms = results.get((n_val, "none"))
        bian_ms = results.get((n_val, "csma_bianchi"))
        none_str = f"{none_ms:.4f}" if none_ms is not None else "ERR"
        bian_str = f"{bian_ms:.4f}" if bian_ms is not None else "ERR"
        if none_ms is not None and bian_ms is not None and none_ms > 0:
            slowdown = bian_ms / none_ms
            slow_str = f"{slowdown:.3f}x"
        else:
            slowdown = None
            slow_str = "n/a"
        print(f"  {n_val:5.1f}  {none_str:>10s}  {bian_str:>12s}  {slow_str:>10s}")

        # Build JSON record
        rf = make_rf_config(n_val)
        json_results.append({
            "path_loss_exponent": n_val,
            "makespan_none": none_ms,
            "makespan_csma_bianchi": bian_ms,
            "slowdown_factor": slowdown,
            "wifi_rate_40m_MBps": compute_wifi_rate(GRID_SPACING, rf),
            "wifi_rate_diag_MBps": compute_wifi_rate(GRID_SPACING * math.sqrt(2), rf),
        })

    print()

    # --- Save JSON Results ----------------------------------------

    output = {
        "experiment": "sensitivity_pathloss",
        "description": "Sweep path loss exponent to show regime transitions",
        "parameters": {
            "network": "3x3 grid",
            "grid_spacing_m": GRID_SPACING,
            "dag": "10-task diamond (medium)",
            "compute_cost": COMPUTE_COST,
            "data_size_MB": DATA_SIZE,
            "scheduler": "heft",
            "routing": "shortest_path",
            "seed": SEED,
        },
        "sweep_variable": "path_loss_exponent",
        "sweep_values": PATH_LOSS_EXPONENTS,
        "results": json_results,
    }

    results_path = os.path.join(OUTDIR, "sensitivity_pathloss.json")
    with open(results_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Results saved to {results_path}")
    print()

    # Check for failures
    failures = sum(1 for v in results.values() if v is None)
    if failures > 0:
        print(f"  WARNING: {failures} simulation(s) failed!")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

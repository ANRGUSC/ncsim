#!/usr/bin/env python3
"""Sensitivity analysis: sweep communication-to-computation ratio (CCR).

Varies data_size from 1 MB to 100 MB while holding compute_cost fixed,
effectively sweeping the CCR. Measures how the interference-induced
slowdown scales with communication intensity across three DAG structures.

Network: 3x3 grid (40m spacing, grid+diagonal links)
DAGs:    small (5-task fork-join), medium (10-task diamond), large (20-task multi-level)
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
GRID_SPACING = 40         # meters
SEED = 42

# Heterogeneous compute capacities cycled across nodes
_CAPACITIES = [200, 100, 150, 80, 300, 120, 250, 180, 160, 90, 220, 140, 280, 110, 190, 170]

# Data sizes to sweep (MB) -- controls the CCR
DATA_SIZES = [1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0]

# Interference models to compare
INTERFERENCE_MODES = ["none", "csma_bianchi"]

# Default RF config (path_loss_exponent=3.0)
RF = RFConfig()

# Output directory for results
OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_results")
WORKDIR = os.path.join(OUTDIR, "_ccr_work")


# --- WiFi Rate Computation ---------------------------------------

def euclidean_distance(x1, y1, x2, y2):
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def compute_wifi_rate(dist):
    """Compute WiFi PHY rate in MB/s for a given distance using default RF config."""
    rx_power = received_power_dBm(RF.tx_power_dBm, dist, RF, 0.0)
    link_snr = snr_dB(rx_power, RF.noise_floor_dBm)
    rate_mbps = snr_to_rate_mbps(link_snr, RF.wifi_standard, RF.channel_width_mhz)
    return rate_mbps_to_MBps(rate_mbps)


# --- Network Generation -----------------------------------------

def generate_network():
    """Generate a 3x3 grid mesh with WiFi-computed bandwidths.

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
        rate = compute_wifi_rate(dist)
        links.append({"id": f"l_{na}_{nb}", "from": na, "to": nb, "bandwidth": rate})
        links.append({"id": f"l_{nb}_{na}", "from": nb, "to": na, "bandwidth": rate})

    return nodes, links


# --- DAG Generators ----------------------------------------------

def _make_dag_small(data_size):
    """Fork-join: 1 source -> 3 parallel -> 1 sink (5 tasks)."""
    tasks = [{"id": f"T{i}", "compute_cost": COMPUTE_COST} for i in range(5)]
    edges = [
        {"from": "T0", "to": "T1", "data_size": data_size},
        {"from": "T0", "to": "T2", "data_size": data_size},
        {"from": "T0", "to": "T3", "data_size": data_size},
        {"from": "T1", "to": "T4", "data_size": data_size},
        {"from": "T2", "to": "T4", "data_size": data_size},
        {"from": "T3", "to": "T4", "data_size": data_size},
    ]
    return tasks, edges


def _make_dag_medium(data_size):
    """Diamond pipeline: source -> 4 parallel -> 4 parallel -> sink (10 tasks)."""
    tasks = [{"id": f"T{i}", "compute_cost": COMPUTE_COST} for i in range(10)]
    edges = []
    # T0 -> T1,T2,T3,T4
    for i in range(1, 5):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": data_size})
    # T1,T2,T3,T4 -> T5,T6,T7,T8 (selective cross-connections)
    for i in range(1, 5):
        for j in range(5, 9):
            if (i + j) % 2 == 0:
                edges.append({"from": f"T{i}", "to": f"T{j}", "data_size": data_size})
    # T5,T6,T7,T8 -> T9
    for i in range(5, 9):
        edges.append({"from": f"T{i}", "to": "T9", "data_size": data_size})
    return tasks, edges


def _make_dag_large(data_size):
    """Multi-level DAG: 3-stage pipeline with branching (20 tasks).

    Stage 0: T0 (source)
    Stage 1: T1-T4 (4 tasks)
    Stage 2: T5-T10 (6 tasks)
    Stage 3: T11-T16 (6 tasks)
    Stage 4: T17-T19 (3 sinks that merge)
    """
    tasks = [{"id": f"T{i}", "compute_cost": COMPUTE_COST} for i in range(20)]
    edges = []
    for i in range(1, 5):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": data_size})
    stage1_to_2 = {1: [5, 6], 2: [6, 7], 3: [8, 9], 4: [9, 10]}
    for src, dsts in stage1_to_2.items():
        for dst in dsts:
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": data_size})
    stage2_to_3 = {5: [11, 12], 6: [12, 13], 7: [13, 14], 8: [14, 15], 9: [15, 16], 10: [16, 11]}
    for src, dsts in stage2_to_3.items():
        for dst in dsts:
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": data_size})
    stage3_to_4 = {11: [17], 12: [17], 13: [18], 14: [18], 15: [19], 16: [19]}
    for src, dsts in stage3_to_4.items():
        for dst in dsts:
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": data_size})
    return tasks, edges


DAG_GENERATORS = {
    "small":  ("5-task fork-join", _make_dag_small),
    "medium": ("10-task diamond", _make_dag_medium),
    "large":  ("20-task multi-level", _make_dag_large),
}


# --- YAML Generation --------------------------------------------

def generate_scenario_yaml(dag_size, data_size):
    """Generate scenario YAML with the specified DAG type and data size."""
    nodes, links = generate_network()
    _, gen_fn = DAG_GENERATORS[dag_size]
    tasks, edges = gen_fn(data_size)

    yaml = "scenario:\n"
    yaml += f'  name: "ccr_{dag_size}dag_ds{data_size:.0f}"\n'
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

def run_scenario(yaml_str, run_label, interference):
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

    dag_sizes = ["small", "medium", "large"]

    print()
    print("=" * 70)
    print("  CCR Sensitivity Analysis: Sweep data_size")
    print("  Network: 3x3 grid | Scheduler: HEFT | Routing: shortest_path")
    print(f"  compute_cost={COMPUTE_COST}, grid_spacing={GRID_SPACING}m, seed={SEED}")
    print(f"  data_sizes (MB): {DATA_SIZES}")
    print(f"  DAGs: {', '.join(desc for desc, _ in DAG_GENERATORS.values())}")
    print("=" * 70)
    print()

    # Show WiFi rates for reference
    dist_grid = GRID_SPACING
    dist_diag = GRID_SPACING * math.sqrt(2)
    print(f"  WiFi rates: 40m={compute_wifi_rate(dist_grid):.3f} MB/s, "
          f"56.6m(diag)={compute_wifi_rate(dist_diag):.3f} MB/s")
    print()

    # Run all simulations: 3 DAGs x 7 data_sizes x 2 interference = 42 runs
    results = {}  # (dag_size, data_size, interference) -> makespan
    total = len(dag_sizes) * len(DATA_SIZES) * len(INTERFERENCE_MODES)
    count = 0

    for dag_size in dag_sizes:
        for data_size in DATA_SIZES:
            yaml_str = generate_scenario_yaml(dag_size, data_size)
            for intf in INTERFERENCE_MODES:
                count += 1
                label = f"{dag_size}dag_ds{data_size:.0f}_{intf}"
                print(f"  [{count:>2d}/{total}] {dag_size} DAG, data={data_size:.0f}MB, "
                      f"intf={intf}...", end=" ", flush=True)
                outdir = run_scenario(yaml_str, label, intf)
                if outdir is None:
                    results[(dag_size, data_size, intf)] = None
                    print("FAILED")
                else:
                    ms = get_makespan(outdir)
                    results[(dag_size, data_size, intf)] = ms
                    print(f"{ms:.4f}s" if ms is not None else "ERROR")

    print()

    # --- Results Tables -------------------------------------------

    json_results = []

    for dag_size in dag_sizes:
        desc, _ = DAG_GENERATORS[dag_size]
        print(f"  DAG: {desc}")
        print(f"  {'data_size':>10s}  {'none (s)':>10s}  {'bianchi (s)':>12s}  {'slowdown':>10s}  {'CCR':>8s}")
        print(f"  {'-' * 58}")

        for data_size in DATA_SIZES:
            none_ms = results.get((dag_size, data_size, "none"))
            bian_ms = results.get((dag_size, data_size, "csma_bianchi"))
            none_str = f"{none_ms:.4f}" if none_ms is not None else "ERR"
            bian_str = f"{bian_ms:.4f}" if bian_ms is not None else "ERR"

            if none_ms is not None and bian_ms is not None and none_ms > 0:
                slowdown = bian_ms / none_ms
                slow_str = f"{slowdown:.3f}x"
            else:
                slowdown = None
                slow_str = "n/a"

            # Approximate CCR: data_size / (compute_cost / avg_capacity) * avg_bandwidth
            # Simplified: ratio of communication time to computation time
            avg_cap = sum(_CAPACITIES[:9]) / 9  # 9 nodes in 3x3 grid
            avg_bw = compute_wifi_rate(GRID_SPACING)  # typical link rate
            ccr = (data_size / avg_bw) / (COMPUTE_COST / avg_cap) if avg_bw > 0 else float('inf')

            print(f"  {data_size:10.1f}  {none_str:>10s}  {bian_str:>12s}  "
                  f"{slow_str:>10s}  {ccr:8.2f}")

            json_results.append({
                "dag_size": dag_size,
                "data_size_MB": data_size,
                "makespan_none": none_ms,
                "makespan_csma_bianchi": bian_ms,
                "slowdown_factor": slowdown,
                "approximate_ccr": round(ccr, 4),
            })
        print()

    # --- Save JSON Results ----------------------------------------

    output = {
        "experiment": "sensitivity_ccr",
        "description": "Sweep data_size to vary communication-to-computation ratio",
        "parameters": {
            "network": "3x3 grid",
            "grid_spacing_m": GRID_SPACING,
            "compute_cost": COMPUTE_COST,
            "scheduler": "heft",
            "routing": "shortest_path",
            "seed": SEED,
            "path_loss_exponent": RF.path_loss_exponent,
        },
        "sweep_variable": "data_size_MB",
        "sweep_values": DATA_SIZES,
        "dag_sizes": list(DAG_GENERATORS.keys()),
        "results": json_results,
    }

    results_path = os.path.join(OUTDIR, "sensitivity_ccr.json")
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

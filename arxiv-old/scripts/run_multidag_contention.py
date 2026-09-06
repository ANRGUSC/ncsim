#!/usr/bin/env python3
"""Multi-DAG contention experiment: show non-linear contention growth.

Injects 1 to 5 concurrent fork-join DAGs with staggered arrival times
onto the same 3x3 grid network. Measures how makespan scales under
interference as more DAGs compete for shared wireless bandwidth.

Network: 3x3 grid (40m spacing, grid+diagonal links)
DAG:     5-task fork-join (small), replicated with unique task IDs
Scheduler: heft
Routing: shortest_path
Staggering: DAG k injected at (k-1)*0.5 seconds
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

# Number of concurrent DAGs to sweep
DAG_COUNTS = [1, 2, 3, 4, 5]

# Stagger interval between DAG injections (seconds)
STAGGER_INTERVAL = 0.5

# Tasks per DAG (fork-join has 5 tasks)
TASKS_PER_DAG = 5

# Interference models to compare
INTERFERENCE_MODES = ["none", "csma_bianchi"]

# Default RF config (path_loss_exponent=3.0)
RF = RFConfig()

# Output directory for results
OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_results")
WORKDIR = os.path.join(OUTDIR, "_multidag_work")


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


# --- Multi-DAG Generation ---------------------------------------

def make_fork_join_dag(dag_index, inject_at):
    """Generate a single 5-task fork-join DAG with unique task IDs.

    Task IDs are offset by dag_index * TASKS_PER_DAG to ensure uniqueness
    across all DAGs in the scenario. For example:
      dag 0: T0-T4, inject_at=0.0
      dag 1: T5-T9, inject_at=0.5
      dag 2: T10-T14, inject_at=1.0

    Returns (dag_id, inject_at, tasks, edges).
    """
    base = dag_index * TASKS_PER_DAG
    dag_id = f"dag_{dag_index + 1}"

    tasks = [{"id": f"T{base + i}", "compute_cost": COMPUTE_COST} for i in range(5)]

    # Fork-join structure: T0 -> {T1, T2, T3} -> T4
    edges = [
        {"from": f"T{base}", "to": f"T{base + 1}", "data_size": DATA_SIZE},
        {"from": f"T{base}", "to": f"T{base + 2}", "data_size": DATA_SIZE},
        {"from": f"T{base}", "to": f"T{base + 3}", "data_size": DATA_SIZE},
        {"from": f"T{base + 1}", "to": f"T{base + 4}", "data_size": DATA_SIZE},
        {"from": f"T{base + 2}", "to": f"T{base + 4}", "data_size": DATA_SIZE},
        {"from": f"T{base + 3}", "to": f"T{base + 4}", "data_size": DATA_SIZE},
    ]

    return dag_id, inject_at, tasks, edges


# --- YAML Generation --------------------------------------------

def generate_scenario_yaml(num_dags):
    """Generate scenario YAML with num_dags concurrent fork-join DAGs.

    Each DAG is staggered by STAGGER_INTERVAL seconds.
    """
    nodes, links = generate_network()

    yaml = "scenario:\n"
    yaml += f'  name: "multidag_{num_dags}dags"\n'
    yaml += "  network:\n    nodes:\n"
    for nd in nodes:
        yaml += (f"      - {{id: {nd['id']}, compute_capacity: {nd['compute_capacity']}, "
                 f"position: {{x: {nd['x']}, y: {nd['y']}}}}}\n")
    yaml += "    links:\n"
    for link in links:
        yaml += (f"      - {{id: {link['id']}, from: {link['from']}, to: {link['to']}, "
                 f"bandwidth: {link['bandwidth']:.4f}}}\n")

    # Generate multiple DAGs with staggered injection
    yaml += "  dags:\n"
    for k in range(num_dags):
        inject_at = k * STAGGER_INTERVAL
        dag_id, _, tasks, edges = make_fork_join_dag(k, inject_at)

        yaml += f"    - id: {dag_id}\n"
        yaml += f"      inject_at: {inject_at}\n"
        yaml += "      tasks:\n"
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

    print()
    print("=" * 70)
    print("  Multi-DAG Contention Scaling Experiment")
    print("  Network: 3x3 grid | DAG: 5-task fork-join | Scheduler: HEFT")
    print(f"  compute_cost={COMPUTE_COST}, data_size={DATA_SIZE}MB, spacing={GRID_SPACING}m")
    print(f"  DAG counts: {DAG_COUNTS}, stagger={STAGGER_INTERVAL}s")
    print("=" * 70)
    print()

    # Show WiFi rates for reference
    dist_grid = GRID_SPACING
    dist_diag = GRID_SPACING * math.sqrt(2)
    print(f"  WiFi rates: 40m={compute_wifi_rate(dist_grid):.3f} MB/s, "
          f"56.6m(diag)={compute_wifi_rate(dist_diag):.3f} MB/s")
    print()

    # Run all simulations: 5 DAG counts x 2 interference = 10 runs
    results = {}  # (num_dags, interference) -> makespan
    total = len(DAG_COUNTS) * len(INTERFERENCE_MODES)
    count = 0

    for num_dags in DAG_COUNTS:
        yaml_str = generate_scenario_yaml(num_dags)
        for intf in INTERFERENCE_MODES:
            count += 1
            label = f"{num_dags}dags_{intf}"
            print(f"  [{count:>2d}/{total}] {num_dags} DAG(s), interference={intf}...",
                  end=" ", flush=True)
            outdir = run_scenario(yaml_str, label, intf)
            if outdir is None:
                results[(num_dags, intf)] = None
                print("FAILED")
            else:
                ms = get_makespan(outdir)
                results[(num_dags, intf)] = ms
                print(f"{ms:.4f}s" if ms is not None else "ERROR")

    print()

    # --- Results Table --------------------------------------------

    # Baseline makespans for scaling factor computation
    baseline_none = results.get((1, "none"))
    baseline_bian = results.get((1, "csma_bianchi"))

    print(f"  {'#DAGs':>6s}  {'none (s)':>10s}  {'bianchi (s)':>12s}  "
          f"{'scale_none':>11s}  {'scale_bian':>11s}  {'slowdown':>10s}")
    print(f"  {'-' * 68}")

    json_results = []
    for num_dags in DAG_COUNTS:
        none_ms = results.get((num_dags, "none"))
        bian_ms = results.get((num_dags, "csma_bianchi"))
        none_str = f"{none_ms:.4f}" if none_ms is not None else "ERR"
        bian_str = f"{bian_ms:.4f}" if bian_ms is not None else "ERR"

        # Contention scaling: makespan_k / makespan_1
        if none_ms is not None and baseline_none is not None and baseline_none > 0:
            scale_none = none_ms / baseline_none
            scale_none_str = f"{scale_none:.3f}x"
        else:
            scale_none = None
            scale_none_str = "n/a"

        if bian_ms is not None and baseline_bian is not None and baseline_bian > 0:
            scale_bian = bian_ms / baseline_bian
            scale_bian_str = f"{scale_bian:.3f}x"
        else:
            scale_bian = None
            scale_bian_str = "n/a"

        # Interference slowdown at this DAG count
        if none_ms is not None and bian_ms is not None and none_ms > 0:
            slowdown = bian_ms / none_ms
            slow_str = f"{slowdown:.3f}x"
        else:
            slowdown = None
            slow_str = "n/a"

        print(f"  {num_dags:6d}  {none_str:>10s}  {bian_str:>12s}  "
              f"{scale_none_str:>11s}  {scale_bian_str:>11s}  {slow_str:>10s}")

        json_results.append({
            "num_dags": num_dags,
            "total_tasks": num_dags * TASKS_PER_DAG,
            "inject_times": [k * STAGGER_INTERVAL for k in range(num_dags)],
            "makespan_none": none_ms,
            "makespan_csma_bianchi": bian_ms,
            "contention_scale_none": scale_none,
            "contention_scale_csma_bianchi": scale_bian,
            "slowdown_factor": slowdown,
        })

    print()

    # --- Non-linearity Check -------------------------------------

    if baseline_bian is not None:
        print("  Contention non-linearity (csma_bianchi):")
        print("  If scaling were linear, makespan_k = makespan_1 + (k-1)*stagger_overhead")
        print("  Super-linear scaling indicates contention amplification.")
        for num_dags in DAG_COUNTS[1:]:  # skip k=1
            bian_ms = results.get((num_dags, "csma_bianchi"))
            if bian_ms is not None:
                actual_ratio = bian_ms / baseline_bian
                linear_bound = num_dags  # worst-case linear scaling
                surplus = actual_ratio - 1.0  # growth beyond single-DAG
                print(f"    k={num_dags}: actual_scale={actual_ratio:.3f}x, "
                      f"growth={surplus:.3f}x above baseline")
        print()

    # --- Save JSON Results ----------------------------------------

    output = {
        "experiment": "multidag_contention",
        "description": "Non-linear contention growth with concurrent DAGs",
        "parameters": {
            "network": "3x3 grid",
            "grid_spacing_m": GRID_SPACING,
            "dag_type": "5-task fork-join",
            "compute_cost": COMPUTE_COST,
            "data_size_MB": DATA_SIZE,
            "scheduler": "heft",
            "routing": "shortest_path",
            "seed": SEED,
            "stagger_interval_s": STAGGER_INTERVAL,
            "path_loss_exponent": RF.path_loss_exponent,
        },
        "sweep_variable": "num_dags",
        "sweep_values": DAG_COUNTS,
        "results": json_results,
    }

    results_path = os.path.join(OUTDIR, "multidag_contention.json")
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

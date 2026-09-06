#!/usr/bin/env python3
"""Full scheduler comparison matrix: 3 grids x 3 DAGs x 3 schedulers x 2 routings x 2 interference = 108 runs.

Compares heft, cpop, and round_robin schedulers across all combinations of:
  - Networks: 2x2 (4 nodes), 3x3 (9 nodes), 4x4 (16 nodes) grid meshes
  - DAGs: small (5 tasks, fork-join), medium (10 tasks, diamond), large (20 tasks, multi-level)
  - Routings: widest_path, shortest_path
  - Interference: none, csma_bianchi

WiFi PHY rates are computed from the RF model and embedded as explicit bandwidths
in the YAML so that none-vs-bianchi comparison is fair (both start from the same
base link rates).

Post-processing:
  - Winner matrix: which scheduler wins for each (network, DAG, interference, routing)
  - Rank inversions: cases where the best scheduler changes between none and csma_bianchi
  - Regret: makespan cost of choosing the "none"-optimal scheduler when running under csma_bianchi
"""

import json
import math
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup: ensure ncsim is importable from the repo root
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent))

from ncsim.models.wifi import (
    RFConfig,
    received_power_dBm,
    snr_dB,
    snr_to_rate_mbps,
    rate_mbps_to_MBps,
)

# ---------------------------------------------------------------------------
# Output directories
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent

# Per-run trace files go here
OUTDIR = SCRIPT_DIR / "_results" / "scheduler_comparison"
# Aggregated results JSON goes here
RESULTS_DIR = SCRIPT_DIR / "_results"

# ---------------------------------------------------------------------------
# Fixed experiment parameters
# ---------------------------------------------------------------------------
COMPUTE_COST = 500
DATA_SIZE = 10.0          # MB
SEED = 42
GRID_SPACING = 40         # meters between adjacent grid nodes

# Heterogeneous compute capacities (cycled across nodes)
_CAPACITIES = [200, 100, 150, 80, 300, 120, 250, 180, 160, 90, 220, 140, 280, 110, 190, 170]

# WiFi RF configuration (defaults: 20 dBm, 5 GHz, n=3.0, 802.11ax)
RF = RFConfig()

# ---------------------------------------------------------------------------
# Matrix axes
# ---------------------------------------------------------------------------
NETWORK_SIZES = {
    "small":  (2, "2x2"),
    "medium": (3, "3x3"),
    "large":  (4, "4x4"),
}
NET_KEYS = ["small", "medium", "large"]

DAG_KEYS = ["small", "medium", "large"]
DAG_TASK_COUNTS = {"small": 5, "medium": 10, "large": 20}

SCHEDULERS = ["heft", "cpop", "round_robin"]
ROUTINGS = ["widest_path", "shortest_path"]
INTERFERENCES = ["none", "csma_bianchi"]


# ===========================================================================
# WiFi rate computation
# ===========================================================================

def euclidean_distance(x1, y1, x2, y2):
    """Euclidean distance between two 2D points."""
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def compute_wifi_rate(dist):
    """Compute WiFi PHY rate in MB/s for a given distance using the RF model."""
    rx_power = received_power_dBm(RF.tx_power_dBm, dist, RF, 0.0)
    link_snr = snr_dB(rx_power, RF.noise_floor_dBm)
    rate_mbps = snr_to_rate_mbps(link_snr, RF.wifi_standard, RF.channel_width_mhz)
    return rate_mbps_to_MBps(rate_mbps)


# ===========================================================================
# Network generation
# ===========================================================================

def generate_network(grid_size):
    """Generate a grid_size x grid_size mesh with bidirectional grid + diagonal links.

    Diagonal links follow a checkerboard pattern: nodes at even (row+col)
    connect down-right; nodes at odd (row+col) connect down-left.

    WiFi PHY rates are computed from the RF model and attached as explicit
    bandwidths on each link.
    """
    n = grid_size
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

    # Collect undirected link pairs (de-duplicated)
    pairs = set()

    def add_pair(r1, c1, r2, c2):
        if 0 <= r2 < n and 0 <= c2 < n:
            a, b = r1 * n + c1, r2 * n + c2
            pairs.add((min(a, b), max(a, b)))

    for row in range(n):
        for col in range(n):
            # Horizontal and vertical grid edges
            add_pair(row, col, row, col + 1)
            add_pair(row, col, row + 1, col)
            # Diagonals (checkerboard pattern)
            if (row + col) % 2 == 0:
                add_pair(row, col, row + 1, col + 1)
            else:
                add_pair(row, col, row + 1, col - 1)

    # Generate bidirectional links with explicit WiFi bandwidths
    links = []
    for a, b in sorted(pairs):
        na_id, nb_id = f"n{a}", f"n{b}"
        na_node, nb_node = nodes[a], nodes[b]
        dist = euclidean_distance(na_node["x"], na_node["y"], nb_node["x"], nb_node["y"])
        rate = compute_wifi_rate(dist)
        links.append({"id": f"l_{na_id}_{nb_id}", "from": na_id, "to": nb_id, "bandwidth": rate, "dist": dist})
        links.append({"id": f"l_{nb_id}_{na_id}", "from": nb_id, "to": na_id, "bandwidth": rate, "dist": dist})

    return nodes, links


# ===========================================================================
# DAG generators
# ===========================================================================

def _make_dag_small():
    """Fork-join DAG: T0 -> T1,T2,T3 -> T4 (5 tasks)."""
    tasks = [{"id": f"T{i}", "compute_cost": COMPUTE_COST} for i in range(5)]
    edges = [
        {"from": "T0", "to": "T1", "data_size": DATA_SIZE},
        {"from": "T0", "to": "T2", "data_size": DATA_SIZE},
        {"from": "T0", "to": "T3", "data_size": DATA_SIZE},
        {"from": "T1", "to": "T4", "data_size": DATA_SIZE},
        {"from": "T2", "to": "T4", "data_size": DATA_SIZE},
        {"from": "T3", "to": "T4", "data_size": DATA_SIZE},
    ]
    return tasks, edges


def _make_dag_medium():
    """Diamond DAG: T0 -> T1-T4 -> T5-T8 -> T9 (10 tasks).

    Selective cross-connections between the two middle layers:
    T_i connects to T_j when (i + j) is even.
    """
    tasks = [{"id": f"T{i}", "compute_cost": COMPUTE_COST} for i in range(10)]
    edges = []
    # T0 -> T1,T2,T3,T4
    for i in range(1, 5):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": DATA_SIZE})
    # T1-T4 -> T5-T8 (selective cross-connections)
    for i in range(1, 5):
        for j in range(5, 9):
            if (i + j) % 2 == 0:
                edges.append({"from": f"T{i}", "to": f"T{j}", "data_size": DATA_SIZE})
    # T5-T8 -> T9
    for i in range(5, 9):
        edges.append({"from": f"T{i}", "to": "T9", "data_size": DATA_SIZE})
    return tasks, edges


def _make_dag_large():
    """Multi-level DAG with 20 tasks across 4 stages.

    Stage 0: T0 (source)
    Stage 1: T1-T4 (4 tasks)
    Stage 2: T5-T10 (6 tasks)
    Stage 3: T11-T16 (6 tasks)
    Stage 4: T17-T19 (3 sinks)
    """
    tasks = [{"id": f"T{i}", "compute_cost": COMPUTE_COST} for i in range(20)]
    edges = []
    # Stage 0 -> Stage 1
    for i in range(1, 5):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": DATA_SIZE})
    # Stage 1 -> Stage 2
    stage1_to_2 = {1: [5, 6], 2: [6, 7], 3: [8, 9], 4: [9, 10]}
    for src, dsts in stage1_to_2.items():
        for dst in dsts:
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": DATA_SIZE})
    # Stage 2 -> Stage 3
    stage2_to_3 = {5: [11, 12], 6: [12, 13], 7: [13, 14], 8: [14, 15], 9: [15, 16], 10: [16, 11]}
    for src, dsts in stage2_to_3.items():
        for dst in dsts:
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": DATA_SIZE})
    # Stage 3 -> Stage 4
    stage3_to_4 = {11: [17], 12: [17], 13: [18], 14: [18], 15: [19], 16: [19]}
    for src, dsts in stage3_to_4.items():
        for dst in dsts:
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": DATA_SIZE})
    return tasks, edges


DAG_GENERATORS = {
    "small":  _make_dag_small,
    "medium": _make_dag_medium,
    "large":  _make_dag_large,
}


# ===========================================================================
# YAML generation
# ===========================================================================

def generate_scenario_yaml(net_size_label, dag_size, scheduler, routing, interference):
    """Generate a complete scenario YAML string with explicit WiFi bandwidths.

    Embedding bandwidth ensures that 'none' and 'csma_bianchi' runs share
    identical base link rates, making their makespans directly comparable.
    """
    grid_size, _ = NETWORK_SIZES[net_size_label]
    nodes, links = generate_network(grid_size)
    tasks, edges = DAG_GENERATORS[dag_size]()

    yaml = "scenario:\n"
    yaml += f'  name: "sched_cmp_{net_size_label}net_{dag_size}dag_{scheduler}_{routing}_{interference}"\n'
    yaml += "  network:\n"
    yaml += "    nodes:\n"
    for n in nodes:
        yaml += (f"      - {{id: {n['id']}, compute_capacity: {n['compute_capacity']}, "
                 f"position: {{x: {n['x']}, y: {n['y']}}}}}\n")
    yaml += "    links:\n"
    for link in links:
        yaml += (f"      - {{id: {link['id']}, from: {link['from']}, to: {link['to']}, "
                 f"bandwidth: {link['bandwidth']:.4f}}}\n")
    yaml += "  dags:\n"
    yaml += "    - id: dag_1\n"
    yaml += "      inject_at: 0.0\n"
    yaml += "      tasks:\n"
    for t in tasks:
        yaml += f"        - {{id: {t['id']}, compute_cost: {t['compute_cost']}}}\n"
    yaml += "      edges:\n"
    for e in edges:
        yaml += f"        - {{from: {e['from']}, to: {e['to']}, data_size: {e['data_size']}}}\n"
    yaml += "  config:\n"
    yaml += f"    scheduler: {scheduler}\n"
    yaml += f"    seed: {SEED}\n"
    yaml += f"    routing: {routing}\n"
    yaml += f"    interference: {interference}\n"
    return yaml


# ===========================================================================
# Subprocess runner
# ===========================================================================

def run_scenario(yaml_str, run_label, scheduler, routing, interference):
    """Write YAML to a temp file, invoke ncsim via subprocess, return output dir."""
    outdir = str(OUTDIR / run_label)
    os.makedirs(outdir, exist_ok=True)

    input_dir = str(OUTDIR / "_inputs" / run_label)
    os.makedirs(input_dir, exist_ok=True)
    yaml_path = os.path.join(input_dir, "scenario.yaml")
    with open(yaml_path, "w") as f:
        f.write(yaml_str)

    cmd = [
        sys.executable, "-m", "ncsim",
        "--scenario", yaml_path,
        "--output", outdir,
        "--scheduler", scheduler,
        "--routing", routing,
        "--interference", interference,
        "--seed", str(SEED),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR running {run_label}:", file=sys.stderr)
        if result.stdout:
            print(f"    stdout: {result.stdout[-500:]}", file=sys.stderr)
        if result.stderr:
            print(f"    stderr: {result.stderr[-500:]}", file=sys.stderr)
        return None
    return outdir


def get_makespan(outdir):
    """Read makespan from metrics.json in the given output directory."""
    path = os.path.join(outdir, "metrics.json")
    try:
        with open(path) as f:
            data = json.load(f)
        if data.get("status") == "error":
            return None
        return data["makespan"]
    except Exception:
        return None


# ===========================================================================
# Post-processing: rank inversions, regret, winner matrix
# ===========================================================================

def find_winner(results, net, dag, routing, interference):
    """Return (best_scheduler, best_makespan) for the given combination.

    Returns (None, None) if all runs failed.
    """
    best_sched = None
    best_ms = None
    for sched in SCHEDULERS:
        ms = results.get((net, dag, sched, routing, interference))
        if ms is not None and (best_ms is None or ms < best_ms):
            best_ms = ms
            best_sched = sched
    return best_sched, best_ms


def compute_rank_inversions(results):
    """Identify (network, DAG, routing) triples where the best scheduler
    changes between 'none' and 'csma_bianchi' interference.

    Returns a list of dicts describing each inversion.
    """
    inversions = []
    total_triples = 0
    for net in NET_KEYS:
        for dag in DAG_KEYS:
            for routing in ROUTINGS:
                best_none, _ = find_winner(results, net, dag, routing, "none")
                best_bianchi, _ = find_winner(results, net, dag, routing, "csma_bianchi")
                if best_none is None or best_bianchi is None:
                    continue
                total_triples += 1
                if best_none != best_bianchi:
                    inversions.append({
                        "network": net,
                        "dag": dag,
                        "routing": routing,
                        "best_under_none": best_none,
                        "best_under_bianchi": best_bianchi,
                    })
    return inversions, total_triples


def compute_regret(results):
    """Compute regret: for each (network, DAG, routing) triple, measure how much
    worse the makespan is when you pick the scheduler that's best under 'none'
    but actually run under 'csma_bianchi'.

    Regret = (makespan of none-optimal scheduler under bianchi) - (makespan of
              actual best scheduler under bianchi).

    Returns a list of dicts with regret info.
    """
    regret_entries = []
    for net in NET_KEYS:
        for dag in DAG_KEYS:
            for routing in ROUTINGS:
                # Find the scheduler that looks best under "none"
                best_none_sched, _ = find_winner(results, net, dag, routing, "none")
                # Find the actual best scheduler under "csma_bianchi"
                best_bianchi_sched, best_bianchi_ms = find_winner(results, net, dag, routing, "csma_bianchi")

                if best_none_sched is None or best_bianchi_sched is None:
                    continue

                # Makespan of the "none"-optimal scheduler when run under bianchi
                none_sched_bianchi_ms = results.get((net, dag, best_none_sched, routing, "csma_bianchi"))
                if none_sched_bianchi_ms is None or best_bianchi_ms is None:
                    continue

                regret_abs = none_sched_bianchi_ms - best_bianchi_ms
                regret_pct = (regret_abs / best_bianchi_ms) * 100 if best_bianchi_ms > 0 else 0.0

                regret_entries.append({
                    "network": net,
                    "dag": dag,
                    "routing": routing,
                    "scheduler_chosen": best_none_sched,
                    "scheduler_optimal": best_bianchi_sched,
                    "makespan_chosen": none_sched_bianchi_ms,
                    "makespan_optimal": best_bianchi_ms,
                    "regret_abs": regret_abs,
                    "regret_pct": regret_pct,
                })
    return regret_entries


# ===========================================================================
# Printing helpers
# ===========================================================================

def print_winner_matrix(results):
    """Print which scheduler wins for each (network, DAG) pair under each
    (interference, routing) combination."""
    print()
    print("=" * 90)
    print("  WINNER MATRIX: best scheduler per (network, DAG, interference, routing)")
    print("=" * 90)

    # Column headers: interference x routing combos
    combos = [(intf, rt) for intf in INTERFERENCES for rt in ROUTINGS]
    combo_labels = [f"{intf}/{rt}" for intf, rt in combos]

    # Header row
    header = f"  {'Net':<8s} {'DAG':<8s}"
    for label in combo_labels:
        header += f"  {label:>22s}"
    print(header)
    print(f"  {'-' * (16 + 24 * len(combos))}")

    for net in NET_KEYS:
        grid_size, net_desc = NETWORK_SIZES[net]
        for dag in DAG_KEYS:
            row = f"  {net_desc:<8s} {dag:<8s}"
            for intf, rt in combos:
                winner, ms = find_winner(results, net, dag, rt, intf)
                if winner is not None and ms is not None:
                    cell = f"{winner}({ms:.2f}s)"
                else:
                    cell = "n/a"
                row += f"  {cell:>22s}"
            print(row)
    print()


def print_rank_inversions(inversions, total_triples):
    """Print rank inversion summary."""
    print("=" * 90)
    print("  RANK INVERSIONS: cases where best scheduler changes between none and csma_bianchi")
    print("=" * 90)
    print()

    if not inversions:
        print("  No rank inversions found.")
    else:
        print(f"  {'Network':<10s} {'DAG':<10s} {'Routing':<16s} {'Best(none)':<14s} {'Best(bianchi)':<14s}")
        print(f"  {'-' * 64}")
        for inv in inversions:
            print(f"  {inv['network']:<10s} {inv['dag']:<10s} {inv['routing']:<16s} "
                  f"{inv['best_under_none']:<14s} {inv['best_under_bianchi']:<14s}")

    inversion_rate = len(inversions) / total_triples if total_triples > 0 else 0.0
    print()
    print(f"  Rank inversions: {len(inversions)} / {total_triples} triples "
          f"({inversion_rate:.1%} inversion rate)")
    print()


def print_regret_statistics(regret_entries):
    """Print regret statistics: mean and max regret across all triples."""
    print("=" * 90)
    print("  REGRET: cost of choosing the 'none'-optimal scheduler under csma_bianchi")
    print("=" * 90)
    print()

    if not regret_entries:
        print("  No regret data available.")
        print()
        return

    # Detailed table
    print(f"  {'Network':<10s} {'DAG':<10s} {'Routing':<16s} {'Chosen':<12s} {'Optimal':<12s} "
          f"{'MS(chosen)':>12s} {'MS(optimal)':>12s} {'Regret':>10s} {'Regret%':>10s}")
    print(f"  {'-' * 104}")
    for entry in regret_entries:
        print(f"  {entry['network']:<10s} {entry['dag']:<10s} {entry['routing']:<16s} "
              f"{entry['scheduler_chosen']:<12s} {entry['scheduler_optimal']:<12s} "
              f"{entry['makespan_chosen']:>12.4f} {entry['makespan_optimal']:>12.4f} "
              f"{entry['regret_abs']:>10.4f} {entry['regret_pct']:>9.2f}%")

    # Summary statistics
    regrets_abs = [e["regret_abs"] for e in regret_entries]
    regrets_pct = [e["regret_pct"] for e in regret_entries]
    nonzero_regrets = [r for r in regrets_abs if r > 1e-9]

    print()
    print(f"  Regret statistics across {len(regret_entries)} triples:")
    print(f"    Mean absolute regret: {sum(regrets_abs) / len(regrets_abs):.4f}s")
    print(f"    Max absolute regret:  {max(regrets_abs):.4f}s")
    print(f"    Mean relative regret: {sum(regrets_pct) / len(regrets_pct):.2f}%")
    print(f"    Max relative regret:  {max(regrets_pct):.2f}%")
    print(f"    Non-zero regret cases: {len(nonzero_regrets)} / {len(regret_entries)}")
    print()


# ===========================================================================
# Main
# ===========================================================================

def main():
    os.makedirs(str(OUTDIR), exist_ok=True)
    os.makedirs(str(RESULTS_DIR), exist_ok=True)

    # Print experiment banner
    print()
    print("=" * 90)
    print("  Full Scheduler Comparison Matrix")
    print(f"  {len(NET_KEYS)} networks x {len(DAG_KEYS)} DAGs x {len(SCHEDULERS)} schedulers "
          f"x {len(ROUTINGS)} routings x {len(INTERFERENCES)} interference = "
          f"{len(NET_KEYS) * len(DAG_KEYS) * len(SCHEDULERS) * len(ROUTINGS) * len(INTERFERENCES)} runs")
    print(f"  Task config: compute_cost={COMPUTE_COST}, data_size={DATA_SIZE}MB, seed={SEED}")
    print(f"  Grid spacing: {GRID_SPACING}m")
    print("=" * 90)
    print()

    # Print WiFi rate info for reference
    dist_adj = compute_wifi_rate(GRID_SPACING)
    dist_diag = compute_wifi_rate(GRID_SPACING * math.sqrt(2))
    print(f"  WiFi rates: {GRID_SPACING}m (adj) = {dist_adj:.3f} MB/s, "
          f"{GRID_SPACING * math.sqrt(2):.1f}m (diag) = {dist_diag:.3f} MB/s")
    print()

    # Print network info
    for ns in NET_KEYS:
        grid_size, net_desc = NETWORK_SIZES[ns]
        nodes, links = generate_network(grid_size)
        print(f"  {ns} network: {net_desc} ({grid_size * grid_size} nodes, {len(links)} links)")
    print()

    # --- Run all 108 simulations ---------------------------------
    results = {}  # (net, dag, scheduler, routing, interference) -> makespan
    total = len(NET_KEYS) * len(DAG_KEYS) * len(SCHEDULERS) * len(ROUTINGS) * len(INTERFERENCES)
    count = 0

    for net in NET_KEYS:
        for dag in DAG_KEYS:
            for sched in SCHEDULERS:
                for routing in ROUTINGS:
                    for intf in INTERFERENCES:
                        count += 1
                        label = f"{net}net_{dag}dag_{sched}_{routing}_{intf}"
                        print(f"  [{count:>3d}/{total}] {label}...", end=" ", flush=True)

                        yaml_str = generate_scenario_yaml(net, dag, sched, routing, intf)
                        outdir = run_scenario(yaml_str, label, sched, routing, intf)

                        if outdir is None:
                            results[(net, dag, sched, routing, intf)] = None
                            print("FAILED")
                        else:
                            ms = get_makespan(outdir)
                            results[(net, dag, sched, routing, intf)] = ms
                            print(f"{ms:.4f}s" if ms is not None else "ERROR")

    print()

    # --- Post-processing -----------------------------------------

    # 1. Winner matrix
    print_winner_matrix(results)

    # 2. Rank inversions
    inversions, total_triples = compute_rank_inversions(results)
    print_rank_inversions(inversions, total_triples)

    # 3. Regret analysis
    regret_entries = compute_regret(results)
    print_regret_statistics(regret_entries)

    # --- Save results to JSON ------------------------------------

    # Convert tuple keys to string keys for JSON serialization
    json_results = {}
    for (net, dag, sched, routing, intf), ms in results.items():
        key = f"{net}_{dag}_{sched}_{routing}_{intf}"
        json_results[key] = ms

    output_data = {
        "metadata": {
            "description": "Full scheduler comparison: 3 grids x 3 DAGs x 3 schedulers x 2 routings x 2 interference",
            "compute_cost": COMPUTE_COST,
            "data_size_MB": DATA_SIZE,
            "seed": SEED,
            "grid_spacing_m": GRID_SPACING,
            "networks": {k: {"grid": v[0], "label": v[1]} for k, v in NETWORK_SIZES.items()},
            "schedulers": SCHEDULERS,
            "routings": ROUTINGS,
            "interferences": INTERFERENCES,
            "dag_task_counts": DAG_TASK_COUNTS,
        },
        "results": json_results,
        "rank_inversions": inversions,
        "rank_inversion_rate": len(inversions) / total_triples if total_triples > 0 else 0.0,
        "regret": regret_entries,
        "regret_summary": {},
    }

    # Add regret summary if data is available
    if regret_entries:
        regrets_abs = [e["regret_abs"] for e in regret_entries]
        regrets_pct = [e["regret_pct"] for e in regret_entries]
        output_data["regret_summary"] = {
            "mean_absolute": sum(regrets_abs) / len(regrets_abs),
            "max_absolute": max(regrets_abs),
            "mean_relative_pct": sum(regrets_pct) / len(regrets_pct),
            "max_relative_pct": max(regrets_pct),
            "nonzero_count": sum(1 for r in regrets_abs if r > 1e-9),
            "total_count": len(regret_entries),
        }

    results_path = str(RESULTS_DIR / "scheduler_comparison.json")
    with open(results_path, "w") as f:
        json.dump(output_data, f, indent=2)
    print(f"  Results saved to {results_path}")

    # Report failures
    failures = sum(1 for v in results.values() if v is None)
    if failures > 0:
        print(f"\n  WARNING: {failures} of {total} simulation(s) failed!")
        return 1

    print(f"\n  All {total} simulations completed successfully.")
    print(f"  Trace files: {OUTDIR}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

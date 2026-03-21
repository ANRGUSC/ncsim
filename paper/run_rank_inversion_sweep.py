#!/usr/bin/env python3
"""Rank inversion sweep: test whether the best scheduler changes when
interference is introduced across a broad matrix of topologies and DAGs.

Runs ~600 simulations:
  10 topologies x 5 DAGs x 3 schedulers x 2 routings x 2 interference models

For each (topology, DAG, routing) triple, we check whether the best
scheduler under "none" interference remains the best under "csma_bianchi".
A rank inversion occurs when the winner changes.

Output:
  paper/_results/rank_inversion_sweep/     (per-run trace dirs)
  paper/_results/rank_inversion_sweep.json (aggregated results)
"""

import json
import math
import os
import random
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup: ensure we can import ncsim from the repo root
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
# Constants
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(SCRIPT_DIR, "_results", "rank_inversion_sweep")
RESULTS_JSON = os.path.join(SCRIPT_DIR, "_results", "rank_inversion_sweep.json")

COMPUTE_COST = 500
DATA_SIZE = 10.0  # MB
GRID_SPACING = 40  # meters between adjacent nodes

# Heterogeneous compute capacities cycled across nodes
_CAPACITIES = [
    200, 100, 150, 80, 300, 120, 250, 180,
    160, 90, 220, 140, 280, 110, 190, 170,
]

# WiFi RF configuration (defaults: 20 dBm, 5 GHz, n=3.0, ax)
RF = RFConfig()

# WiFi connectivity threshold for random geometric graphs (meters)
WIFI_RANGE = 80.0


# ---------------------------------------------------------------------------
# WiFi PHY rate helpers
# ---------------------------------------------------------------------------

def euclidean_distance(x1, y1, x2, y2):
    """Euclidean distance between two 2-D points."""
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def compute_wifi_rate(dist):
    """Compute WiFi PHY rate in MB/s for a given distance using ncsim RF model."""
    rx_power = received_power_dBm(RF.tx_power_dBm, dist, RF, 0.0)
    link_snr = snr_dB(rx_power, RF.noise_floor_dBm)
    rate_mbps = snr_to_rate_mbps(link_snr, RF.wifi_standard, RF.channel_width_mhz)
    return rate_mbps_to_MBps(rate_mbps)


# ---------------------------------------------------------------------------
# Helper: build bidirectional link list from undirected pairs
# ---------------------------------------------------------------------------

def _links_from_pairs(pairs, nodes):
    """Given a set of (i, j) undirected pairs and a node list, return
    bidirectional link dicts with WiFi PHY bandwidth computed from distance."""
    links = []
    for a, b in sorted(pairs):
        na_id, nb_id = f"n{a}", f"n{b}"
        na_node, nb_node = nodes[a], nodes[b]
        dist = euclidean_distance(
            na_node["x"], na_node["y"], nb_node["x"], nb_node["y"]
        )
        rate = compute_wifi_rate(dist)
        links.append({
            "id": f"l_{na_id}_{nb_id}", "from": na_id, "to": nb_id,
            "bandwidth": rate, "dist": dist,
        })
        links.append({
            "id": f"l_{nb_id}_{na_id}", "from": nb_id, "to": na_id,
            "bandwidth": rate, "dist": dist,
        })
    return links


# ===================================================================
# Topology generators
# ===================================================================

def generate_grid(n):
    """n x n grid mesh with grid + diagonal links (40 m spacing).

    Diagonal pattern alternates by checkerboard: even (row+col) gets
    down-right diagonal, odd gets down-left. Same pattern as the
    existing interference / routing comparison scripts.
    """
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

    pairs = set()

    def add_pair(r1, c1, r2, c2):
        if 0 <= r2 < n and 0 <= c2 < n:
            a, b = r1 * n + c1, r2 * n + c2
            pairs.add((min(a, b), max(a, b)))

    for row in range(n):
        for col in range(n):
            # Horizontal and vertical
            add_pair(row, col, row, col + 1)
            add_pair(row, col, row + 1, col)
            # Diagonals (alternating by checkerboard)
            if (row + col) % 2 == 0:
                add_pair(row, col, row + 1, col + 1)
            else:
                add_pair(row, col, row + 1, col - 1)

    return nodes, _links_from_pairs(pairs, nodes)


def generate_line(n):
    """n nodes arranged in a straight line at 40 m spacing.

    Node i is at position (i * 40, 0). Links connect adjacent nodes only
    (bidirectional).
    """
    nodes = []
    for i in range(n):
        nodes.append({
            "id": f"n{i}",
            "compute_capacity": _CAPACITIES[i % len(_CAPACITIES)],
            "x": i * GRID_SPACING,
            "y": 0,
        })

    pairs = set()
    for i in range(n - 1):
        pairs.add((i, i + 1))

    return nodes, _links_from_pairs(pairs, nodes)


def generate_star(n):
    """1 center node at (0, 0) + (n - 1) leaf nodes at 40 m radius.

    Leaves are evenly distributed around the center. Links: center to
    each leaf (bidirectional only; no leaf-to-leaf links).
    """
    nodes = [{
        "id": "n0",
        "compute_capacity": _CAPACITIES[0],
        "x": 0,
        "y": 0,
    }]
    for i in range(1, n):
        angle = 2 * math.pi * (i - 1) / (n - 1)
        nodes.append({
            "id": f"n{i}",
            "compute_capacity": _CAPACITIES[i % len(_CAPACITIES)],
            "x": round(GRID_SPACING * math.cos(angle), 4),
            "y": round(GRID_SPACING * math.sin(angle), 4),
        })

    pairs = set()
    for i in range(1, n):
        pairs.add((0, i))

    return nodes, _links_from_pairs(pairs, nodes)


def generate_binary_tree(depth):
    """Complete binary tree with the given depth.

    depth=1 -> 3 nodes (root + 2 children)
    depth=2 -> 7 nodes
    depth=3 -> 15 nodes

    Horizontal spacing: leaves are 40 m apart. Parent is centered above
    its children. Vertical spacing: 40 m between levels. Root is at the
    top (highest y), leaves at the bottom (y = 0).
    """
    total_nodes = (1 << (depth + 1)) - 1  # 2^(depth+1) - 1
    num_leaves = 1 << depth                # 2^depth

    # Leaf-level width: (num_leaves - 1) * GRID_SPACING
    # Index nodes level by level (BFS order: root = 0)
    # Level k has 2^k nodes, indices [2^k - 1 .. 2^(k+1) - 2]

    # Precompute x positions bottom-up: leaves first, then average parents
    x_pos = [0.0] * total_nodes
    y_pos = [0.0] * total_nodes

    # Leaf positions (level = depth, indices 2^depth - 1 .. 2^(depth+1) - 2)
    leaf_start = (1 << depth) - 1
    for i in range(num_leaves):
        x_pos[leaf_start + i] = i * GRID_SPACING

    # Y positions: leaves at y=0, root at y = depth * GRID_SPACING
    for level in range(depth + 1):
        level_start = (1 << level) - 1
        level_count = 1 << level
        y = (depth - level) * GRID_SPACING
        for i in range(level_count):
            y_pos[level_start + i] = y

    # X positions for internal nodes: average of children
    for level in range(depth - 1, -1, -1):
        level_start = (1 << level) - 1
        level_count = 1 << level
        for i in range(level_count):
            node_idx = level_start + i
            left_child = 2 * node_idx + 1
            right_child = 2 * node_idx + 2
            x_pos[node_idx] = (x_pos[left_child] + x_pos[right_child]) / 2.0

    # Build node list
    nodes = []
    for idx in range(total_nodes):
        nodes.append({
            "id": f"n{idx}",
            "compute_capacity": _CAPACITIES[idx % len(_CAPACITIES)],
            "x": round(x_pos[idx], 4),
            "y": round(y_pos[idx], 4),
        })

    # Parent-child links (bidirectional)
    pairs = set()
    for idx in range(total_nodes):
        left_child = 2 * idx + 1
        right_child = 2 * idx + 2
        if left_child < total_nodes:
            pairs.add((min(idx, left_child), max(idx, left_child)))
        if right_child < total_nodes:
            pairs.add((min(idx, right_child), max(idx, right_child)))

    return nodes, _links_from_pairs(pairs, nodes)


def generate_random_geometric(n, area, seed):
    """n nodes placed uniformly at random in an area x area square.

    Two nodes are linked if their distance <= WIFI_RANGE (80 m).
    If the resulting graph is disconnected, retry with seed + 1, +2, ...
    until a connected graph is found. Capacities cycle from _CAPACITIES.
    """
    def _is_connected(adj, num_nodes):
        """BFS connectivity check."""
        visited = set()
        queue = [0]
        visited.add(0)
        while queue:
            cur = queue.pop()
            for nb in adj.get(cur, []):
                if nb not in visited:
                    visited.add(nb)
                    queue.append(nb)
        return len(visited) == num_nodes

    attempt_seed = seed
    while True:
        rng = random.Random(attempt_seed)
        positions = [(rng.uniform(0, area), rng.uniform(0, area)) for _ in range(n)]

        # Build adjacency for connectivity check
        adj = {i: [] for i in range(n)}
        pairs = set()
        for i in range(n):
            for j in range(i + 1, n):
                dist = euclidean_distance(
                    positions[i][0], positions[i][1],
                    positions[j][0], positions[j][1],
                )
                if dist <= WIFI_RANGE:
                    pairs.add((i, j))
                    adj[i].append(j)
                    adj[j].append(i)

        if _is_connected(adj, n):
            break
        attempt_seed += 1  # Retry with next seed

    nodes = []
    for i in range(n):
        nodes.append({
            "id": f"n{i}",
            "compute_capacity": _CAPACITIES[i % len(_CAPACITIES)],
            "x": round(positions[i][0], 4),
            "y": round(positions[i][1], 4),
        })

    return nodes, _links_from_pairs(pairs, nodes)


# ===================================================================
# DAG generators
# ===================================================================

def _make_dag_small():
    """Fork-join: 1 source -> 3 parallel -> 1 sink (5 tasks)."""
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
    """Diamond pipeline: source -> 4 parallel -> 4 parallel -> sink (10 tasks)."""
    tasks = [{"id": f"T{i}", "compute_cost": COMPUTE_COST} for i in range(10)]
    edges = []
    # T0 -> T1, T2, T3, T4
    for i in range(1, 5):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": DATA_SIZE})
    # T1..T4 -> T5..T8 (selective cross-connections by parity)
    for i in range(1, 5):
        for j in range(5, 9):
            if (i + j) % 2 == 0:
                edges.append({"from": f"T{i}", "to": f"T{j}", "data_size": DATA_SIZE})
    # T5..T8 -> T9
    for i in range(5, 9):
        edges.append({"from": f"T{i}", "to": "T9", "data_size": DATA_SIZE})
    return tasks, edges


def _make_dag_large():
    """Multi-level DAG with branching (20 tasks).

    Stage 0: T0 (source)
    Stage 1: T1-T4 (4 tasks)
    Stage 2: T5-T10 (6 tasks)
    Stage 3: T11-T16 (6 tasks)
    Stage 4: T17-T19 (3 sinks)
    """
    tasks = [{"id": f"T{i}", "compute_cost": COMPUTE_COST} for i in range(20)]
    edges = []
    # Stage 0 -> 1
    for i in range(1, 5):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": DATA_SIZE})
    # Stage 1 -> 2
    stage1_to_2 = {1: [5, 6], 2: [6, 7], 3: [8, 9], 4: [9, 10]}
    for src, dsts in stage1_to_2.items():
        for dst in dsts:
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": DATA_SIZE})
    # Stage 2 -> 3
    stage2_to_3 = {
        5: [11, 12], 6: [12, 13], 7: [13, 14],
        8: [14, 15], 9: [15, 16], 10: [16, 11],
    }
    for src, dsts in stage2_to_3.items():
        for dst in dsts:
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": DATA_SIZE})
    # Stage 3 -> 4
    stage3_to_4 = {11: [17], 12: [17], 13: [18], 14: [18], 15: [19], 16: [19]}
    for src, dsts in stage3_to_4.items():
        for dst in dsts:
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": DATA_SIZE})
    return tasks, edges


def _make_dag_chain(length):
    """Serial chain: T0 -> T1 -> ... -> T_{length-1}."""
    tasks = [{"id": f"T{i}", "compute_cost": COMPUTE_COST} for i in range(length)]
    edges = []
    for i in range(length - 1):
        edges.append({"from": f"T{i}", "to": f"T{i + 1}", "data_size": DATA_SIZE})
    return tasks, edges


def _make_dag_wide_fan(width):
    """Fork-join fan: T0 -> [T1 .. T_width] -> T_{width+1}.

    Total tasks: width + 2.
    """
    total = width + 2
    tasks = [{"id": f"T{i}", "compute_cost": COMPUTE_COST} for i in range(total)]
    edges = []
    # Source fans out
    for i in range(1, width + 1):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": DATA_SIZE})
    # All fan tasks converge to sink
    sink_id = f"T{width + 1}"
    for i in range(1, width + 1):
        edges.append({"from": f"T{i}", "to": sink_id, "data_size": DATA_SIZE})
    return tasks, edges


# ===================================================================
# Full sweep matrix
# ===================================================================

# Topologies: (label, generator_callable) -- callable returns (nodes, links)
TOPOLOGIES = [
    ("grid_2x2",       lambda: generate_grid(2)),
    ("grid_3x3",       lambda: generate_grid(3)),
    ("grid_4x4",       lambda: generate_grid(4)),
    ("line_4",         lambda: generate_line(4)),
    ("line_8",         lambda: generate_line(8)),
    ("star_5",         lambda: generate_star(5)),
    ("star_9",         lambda: generate_star(9)),
    ("tree_depth2",    lambda: generate_binary_tree(2)),
    ("tree_depth3",    lambda: generate_binary_tree(3)),
    ("random_geo_8",   lambda: generate_random_geometric(8, 200, seed=42)),
]

# DAGs: (label, generator_callable) -- callable returns (tasks, edges)
DAGS = [
    ("small",    _make_dag_small),
    ("medium",   _make_dag_medium),
    ("large",    _make_dag_large),
    ("chain_8",  lambda: _make_dag_chain(8)),
    ("fan_6",    lambda: _make_dag_wide_fan(6)),
]

SCHEDULERS = ["heft", "cpop", "round_robin"]
ROUTINGS = ["widest_path", "shortest_path"]
INTERFERENCES = ["none", "csma_bianchi"]


# ===================================================================
# YAML generation
# ===================================================================

def generate_scenario_yaml(topo_label, nodes, links, dag_label, tasks, edges):
    """Build a complete scenario YAML string with explicit WiFi bandwidths."""
    yaml = "scenario:\n"
    yaml += f'  name: "rank_inv_{topo_label}_{dag_label}"\n'

    # Network
    yaml += "  network:\n    nodes:\n"
    for nd in nodes:
        yaml += (
            f"      - {{id: {nd['id']}, "
            f"compute_capacity: {nd['compute_capacity']}, "
            f"position: {{x: {nd['x']}, y: {nd['y']}}}}}\n"
        )
    yaml += "    links:\n"
    for lk in links:
        yaml += (
            f"      - {{id: {lk['id']}, from: {lk['from']}, to: {lk['to']}, "
            f"bandwidth: {lk['bandwidth']:.4f}}}\n"
        )

    # DAG
    yaml += "  dags:\n    - id: dag_1\n      inject_at: 0.0\n      tasks:\n"
    for t in tasks:
        yaml += f"        - {{id: {t['id']}, compute_cost: {t['compute_cost']}}}\n"
    yaml += "      edges:\n"
    for e in edges:
        yaml += f"        - {{from: {e['from']}, to: {e['to']}, data_size: {e['data_size']}}}\n"

    # Config placeholder (overridden by CLI flags)
    yaml += "  config:\n"
    yaml += "    scheduler: heft\n"
    yaml += "    seed: 42\n"
    yaml += "    routing: shortest_path\n"
    yaml += "    interference: none\n"
    return yaml


# ===================================================================
# Subprocess runner
# ===================================================================

def run_scenario(yaml_str, run_label, scheduler, routing, interference):
    """Write YAML to a temp file, invoke ncsim via subprocess, return output dir."""
    outdir = os.path.join(OUTDIR, run_label)
    os.makedirs(outdir, exist_ok=True)

    input_dir = os.path.join(OUTDIR, "_inputs", run_label)
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
        "--seed", "42",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR running {run_label}:", file=sys.stderr)
        if result.stderr:
            print(f"    stderr: {result.stderr[-400:]}", file=sys.stderr)
        return None
    return outdir


def get_makespan(outdir):
    """Read makespan from metrics.json in the output directory."""
    path = os.path.join(outdir, "metrics.json")
    try:
        with open(path) as f:
            data = json.load(f)
        if data.get("status") == "error":
            return None
        return data["makespan"]
    except Exception:
        return None


# ===================================================================
# Post-processing: rank inversion analysis
# ===================================================================

def analyze_rank_inversions(results, topo_labels, dag_labels):
    """Compute rank inversion statistics.

    For each (topology, DAG, routing) triple:
      - Find the best scheduler under "none" interference.
      - Find the best scheduler under "csma_bianchi" interference.
      - A rank inversion occurs when the winner changes.
      - Regret = makespan(naive_best, bianchi) / makespan(true_best, bianchi) - 1

    Returns a list of per-scenario dicts and summary statistics.
    """
    scenarios = []
    inversion_count = 0
    total_scenarios = 0
    regrets = []

    for topo in topo_labels:
        for dag in dag_labels:
            for routing in ROUTINGS:
                # Gather makespans per scheduler for each interference mode
                none_makespans = {}
                bianchi_makespans = {}
                for sched in SCHEDULERS:
                    key_none = (topo, dag, sched, routing, "none")
                    key_bian = (topo, dag, sched, routing, "csma_bianchi")
                    none_makespans[sched] = results.get(key_none)
                    bianchi_makespans[sched] = results.get(key_bian)

                # Skip if any data is missing
                if any(v is None for v in none_makespans.values()):
                    continue
                if any(v is None for v in bianchi_makespans.values()):
                    continue

                total_scenarios += 1

                # Best under "none" (lowest makespan)
                best_none = min(SCHEDULERS, key=lambda s: none_makespans[s])
                # Best under "csma_bianchi"
                best_bianchi = min(SCHEDULERS, key=lambda s: bianchi_makespans[s])

                inversion = (best_none != best_bianchi)
                if inversion:
                    inversion_count += 1

                # Regret: using the none-best scheduler under bianchi vs true best
                naive_ms = bianchi_makespans[best_none]
                true_ms = bianchi_makespans[best_bianchi]
                regret = (naive_ms / true_ms - 1.0) if true_ms > 0 else 0.0
                regrets.append(regret)

                scenarios.append({
                    "topology": topo,
                    "dag": dag,
                    "routing": routing,
                    "best_none": best_none,
                    "best_bianchi": best_bianchi,
                    "inversion": inversion,
                    "regret": regret,
                    "none_makespans": dict(none_makespans),
                    "bianchi_makespans": dict(bianchi_makespans),
                })

    summary = {
        "total_scenarios": total_scenarios,
        "inversion_count": inversion_count,
        "inversion_rate": (inversion_count / total_scenarios * 100.0)
            if total_scenarios > 0 else 0.0,
        "mean_regret": (sum(regrets) / len(regrets)) if regrets else 0.0,
        "max_regret": max(regrets) if regrets else 0.0,
    }

    return scenarios, summary


def print_summary(scenarios, summary, topo_labels, dag_labels):
    """Print human-readable summary of rank inversion results."""
    print()
    print("=" * 72)
    print("  RANK INVERSION ANALYSIS")
    print("=" * 72)
    print()
    print(f"  Total (topology, DAG, routing) scenarios: {summary['total_scenarios']}")
    print(f"  Rank inversions: {summary['inversion_count']} "
          f"({summary['inversion_rate']:.1f}%)")
    print(f"  Mean regret:     {summary['mean_regret']:.4f} "
          f"({summary['mean_regret'] * 100:.2f}%)")
    print(f"  Max regret:      {summary['max_regret']:.4f} "
          f"({summary['max_regret'] * 100:.2f}%)")
    print()

    # Heatmap-style table: topology x DAG showing inversion count
    # (aggregated over routings)
    print("  Inversion count heatmap (topology x DAG, summed over routings):")
    print(f"  {'-' * 68}")

    # Header
    header = f"  {'Topology':<16s}"
    for dag in dag_labels:
        header += f"  {dag:>10s}"
    header += f"  {'Total':>8s}"
    print(header)
    print(f"  {'-' * 68}")

    total_per_dag = {d: 0 for d in dag_labels}
    for topo in topo_labels:
        row = f"  {topo:<16s}"
        row_total = 0
        for dag in dag_labels:
            count = sum(
                1 for s in scenarios
                if s["topology"] == topo and s["dag"] == dag and s["inversion"]
            )
            row_total += count
            total_per_dag[dag] += count
            row += f"  {count:>10d}"
        row += f"  {row_total:>8d}"
        print(row)

    # Footer totals
    footer = f"  {'Total':<16s}"
    grand_total = 0
    for dag in dag_labels:
        footer += f"  {total_per_dag[dag]:>10d}"
        grand_total += total_per_dag[dag]
    footer += f"  {grand_total:>8d}"
    print(f"  {'-' * 68}")
    print(footer)
    print()

    # List all inversions for inspection
    inversions = [s for s in scenarios if s["inversion"]]
    if inversions:
        print(f"  Detailed inversions ({len(inversions)} total):")
        print(f"  {'-' * 68}")
        for s in inversions:
            print(f"    {s['topology']:>16s} | {s['dag']:>8s} | {s['routing']:>14s} | "
                  f"none-best={s['best_none']:<12s} bianchi-best={s['best_bianchi']:<12s} "
                  f"regret={s['regret']:.4f}")
        print()


# ===================================================================
# Main
# ===================================================================

def main():
    os.makedirs(OUTDIR, exist_ok=True)

    # Precompute representative WiFi rates for info
    rate_40m = compute_wifi_rate(40)
    rate_diag = compute_wifi_rate(40 * math.sqrt(2))
    print()
    print("=" * 72)
    print("  Rank Inversion Sweep")
    print("=" * 72)
    print(f"  WiFi rates: 40m = {rate_40m:.3f} MB/s, "
          f"56.6m (diag) = {rate_diag:.3f} MB/s")
    print(f"  Task config: compute_cost={COMPUTE_COST}, data_size={DATA_SIZE} MB")
    print(f"  Schedulers: {', '.join(SCHEDULERS)}")
    print(f"  Routings: {', '.join(ROUTINGS)}")
    print(f"  Interference: {', '.join(INTERFERENCES)}")
    print()

    # Print topology info
    topo_labels = []
    topo_cache = {}  # label -> (nodes, links)
    for topo_label, gen_fn in TOPOLOGIES:
        nodes, links = gen_fn()
        topo_cache[topo_label] = (nodes, links)
        topo_labels.append(topo_label)
        print(f"  Topology {topo_label}: {len(nodes)} nodes, {len(links)} links")

    # Print DAG info
    dag_labels = []
    dag_cache = {}  # label -> (tasks, edges)
    for dag_label, gen_fn in DAGS:
        tasks, edges = gen_fn()
        dag_cache[dag_label] = (tasks, edges)
        dag_labels.append(dag_label)
        print(f"  DAG {dag_label}: {len(tasks)} tasks, {len(edges)} edges")

    total_runs = len(TOPOLOGIES) * len(DAGS) * len(SCHEDULERS) * len(ROUTINGS) * len(INTERFERENCES)
    print(f"\n  Total simulation runs: {total_runs}")
    print()

    # ---------------------------------------------------------------------------
    # Run all simulations
    # ---------------------------------------------------------------------------
    results = {}  # (topo, dag, scheduler, routing, interference) -> makespan
    count = 0

    for topo_label in topo_labels:
        nodes, links = topo_cache[topo_label]
        for dag_label in dag_labels:
            tasks, edges = dag_cache[dag_label]
            # Generate YAML once per (topology, DAG) pair
            yaml_str = generate_scenario_yaml(
                topo_label, nodes, links, dag_label, tasks, edges,
            )
            for scheduler in SCHEDULERS:
                for routing in ROUTINGS:
                    for interference in INTERFERENCES:
                        count += 1
                        run_label = (
                            f"{topo_label}__{dag_label}__{scheduler}"
                            f"__{routing}__{interference}"
                        )
                        print(
                            f"  [{count:>3d}/{total_runs}] {run_label}...",
                            end=" ", flush=True,
                        )

                        outdir = run_scenario(
                            yaml_str, run_label, scheduler, routing, interference,
                        )
                        key = (topo_label, dag_label, scheduler, routing, interference)
                        if outdir is None:
                            results[key] = None
                            print("FAILED")
                        else:
                            ms = get_makespan(outdir)
                            results[key] = ms
                            print(f"{ms:.4f}s" if ms is not None else "ERROR")

    # ---------------------------------------------------------------------------
    # Post-processing: rank inversion analysis
    # ---------------------------------------------------------------------------
    scenarios, summary = analyze_rank_inversions(results, topo_labels, dag_labels)
    print_summary(scenarios, summary, topo_labels, dag_labels)

    # ---------------------------------------------------------------------------
    # Save complete results to JSON
    # ---------------------------------------------------------------------------
    json_output = {
        "summary": summary,
        "scenarios": scenarios,
        "raw_results": {},
    }
    # Flatten tuple keys for JSON serialization
    for (topo, dag, sched, routing, intf), ms in results.items():
        flat_key = f"{topo}__{dag}__{sched}__{routing}__{intf}"
        json_output["raw_results"][flat_key] = ms

    os.makedirs(os.path.dirname(RESULTS_JSON), exist_ok=True)
    with open(RESULTS_JSON, "w") as f:
        json.dump(json_output, f, indent=2)
    print(f"  Results saved to {RESULTS_JSON}")
    print(f"  Trace files in   {OUTDIR}")
    print()

    # Return non-zero if any simulations failed
    failures = sum(1 for v in results.values() if v is None)
    if failures > 0:
        print(f"  WARNING: {failures} simulation(s) failed!")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Routing comparison: widest_path vs shortest_path under HEFT with csma_bianchi.

Runs 18 simulations (3 network sizes x 3 DAG sizes x 2 routing strategies)
comparing makespan for widest_path vs shortest_path routing.

Network sizes (grid meshes with bidirectional grid + diagonal links):
  Small:  2x2 grid (4 nodes)
  Medium: 3x3 grid (9 nodes)
  Large:  4x4 grid (16 nodes)

DAG sizes: small (5 tasks, fork-join), medium (10 tasks, diamond), large (20 tasks, multi-level)
Fixed task config: compute_cost=500, data_size=10MB
"""

import json
import os
import subprocess
import sys
from pathlib import Path

OUTDIR = "/tmp/ncsim_routing_comparison"

# Fixed task configuration
COMPUTE_COST = 500
DATA_SIZE = 10.0

# Heterogeneous compute capacities cycled across nodes
_CAPACITIES = [200, 100, 150, 80, 300, 120, 250, 180, 160, 90, 220, 140, 280, 110, 190, 170]

GRID_SPACING = 40  # meters between adjacent nodes

# ─── Network Generation ─────────────────────────────────────────


def generate_network(grid_size):
    """Generate a grid_size x grid_size mesh network.

    Returns (nodes, links) where links are bidirectional grid edges + diagonals.
    Grid spacing is 40m; diagonals are ~56.6m, giving different PHY rates.
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

    # Collect undirected link pairs
    pairs = set()

    def add_pair(r1, c1, r2, c2):
        if 0 <= r2 < n and 0 <= c2 < n:
            a, b = r1 * n + c1, r2 * n + c2
            pairs.add((min(a, b), max(a, b)))

    for row in range(n):
        for col in range(n):
            # Grid edges (horizontal + vertical)
            add_pair(row, col, row, col + 1)
            add_pair(row, col, row + 1, col)
            # Diagonals (down-right and down-left, alternating by checkerboard)
            if (row + col) % 2 == 0:
                add_pair(row, col, row + 1, col + 1)
            else:
                add_pair(row, col, row + 1, col - 1)

    # Generate bidirectional links
    links = []
    for a, b in sorted(pairs):
        na, nb = f"n{a}", f"n{b}"
        links.append({"id": f"l_{na}_{nb}", "from": na, "to": nb})
        links.append({"id": f"l_{nb}_{na}", "from": nb, "to": na})

    return nodes, links


NETWORK_SIZES = {
    "small":  (2, "2x2 (4 nodes)"),
    "medium": (3, "3x3 (9 nodes)"),
    "large":  (4, "4x4 (16 nodes)"),
}

# ─── Bottleneck Network Generation ──────────────────────────────


def generate_bottleneck_network():
    """Generate a bottleneck network: two compute clusters connected by relay chain.

    n0(0,0)---n1(30,0)---n2(60,0)---n3(90,0)---n4(120,0)
      \                                          /
       --------------- 120m direct ---------------

    Adjacent links (30m) have 8.6 MB/s (MCS 5).
    Direct n0-n4 link (120m) has 1.075 MB/s (MCS 0).
    Widest path n0->n4 uses the relay chain (bottleneck 8.6 MB/s).
    Shortest path n0->n4 uses the slow direct link (1 hop, 1.075 MB/s).
    """
    nodes = [
        {"id": "n0", "compute_capacity": 200, "x": 0, "y": 0},
        {"id": "n1", "compute_capacity": 200, "x": 30, "y": 0},
        {"id": "n2", "compute_capacity": 200, "x": 60, "y": 0},
        {"id": "n3", "compute_capacity": 200, "x": 90, "y": 0},
        {"id": "n4", "compute_capacity": 200, "x": 120, "y": 0},
    ]

    # All pairs within communication range (~130m)
    n = len(nodes)
    links = []
    for i in range(n):
        for j in range(i + 1, n):
            ni, nj = nodes[i], nodes[j]
            dist = ((ni["x"] - nj["x"])**2 + (ni["y"] - nj["y"])**2)**0.5
            if dist < 130:
                a, b = ni["id"], nj["id"]
                links.append({"id": f"l_{a}_{b}", "from": a, "to": b})
                links.append({"id": f"l_{b}_{a}", "from": b, "to": a})

    return nodes, links


BOTTLENECK_NETWORK = ("bottleneck", "bottleneck (5 nodes, relay chain)")

# ─── DAG Generators ─────────────────────────────────────────────


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


def _make_dag_large():
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
        edges.append({"from": "T0", "to": f"T{i}", "data_size": DATA_SIZE})
    stage1_to_2 = {1: [5, 6], 2: [6, 7], 3: [8, 9], 4: [9, 10]}
    for src, dsts in stage1_to_2.items():
        for dst in dsts:
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": DATA_SIZE})
    stage2_to_3 = {5: [11, 12], 6: [12, 13], 7: [13, 14], 8: [14, 15], 9: [15, 16], 10: [16, 11]}
    for src, dsts in stage2_to_3.items():
        for dst in dsts:
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": DATA_SIZE})
    stage3_to_4 = {11: [17], 12: [17], 13: [18], 14: [18], 15: [19], 16: [19]}
    for src, dsts in stage3_to_4.items():
        for dst in dsts:
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": DATA_SIZE})
    return tasks, edges


DAG_GENERATORS = {
    "small":  ("small (5 tasks, fork-join)", _make_dag_small),
    "medium": ("medium (10 tasks, diamond)", _make_dag_medium),
    "large":  ("large (20 tasks, multi-level)", _make_dag_large),
}


# ─── Bottleneck DAG Generators ──────────────────────────────────


def _make_bottleneck_dag_small():
    """Chain DAG with tasks pinned to opposite ends of the network.

    T0(n0) -> T1(n4) -> T2(n0) -> T3(n4) -> T4(n0)
    4 transfers across the bottleneck, all sequential (no contention).
    """
    tasks = [
        {"id": "T0", "compute_cost": COMPUTE_COST, "pinned_to": "n0"},
        {"id": "T1", "compute_cost": COMPUTE_COST, "pinned_to": "n4"},
        {"id": "T2", "compute_cost": COMPUTE_COST, "pinned_to": "n0"},
        {"id": "T3", "compute_cost": COMPUTE_COST, "pinned_to": "n4"},
        {"id": "T4", "compute_cost": COMPUTE_COST, "pinned_to": "n0"},
    ]
    edges = [
        {"from": "T0", "to": "T1", "data_size": DATA_SIZE},
        {"from": "T1", "to": "T2", "data_size": DATA_SIZE},
        {"from": "T2", "to": "T3", "data_size": DATA_SIZE},
        {"from": "T3", "to": "T4", "data_size": DATA_SIZE},
    ]
    return tasks, edges


def _make_bottleneck_dag_medium():
    """Fork-join with 3 parallel tasks pinned across the network.

    T0(n0) -> {T1(n2), T2(n3), T3(n4)} -> T4(n0)
    3 concurrent outbound transfers + 3 concurrent return transfers.
    """
    tasks = [
        {"id": "T0", "compute_cost": COMPUTE_COST, "pinned_to": "n0"},
        {"id": "T1", "compute_cost": COMPUTE_COST, "pinned_to": "n2"},
        {"id": "T2", "compute_cost": COMPUTE_COST, "pinned_to": "n3"},
        {"id": "T3", "compute_cost": COMPUTE_COST, "pinned_to": "n4"},
        {"id": "T4", "compute_cost": COMPUTE_COST, "pinned_to": "n0"},
    ]
    edges = [
        {"from": "T0", "to": "T1", "data_size": DATA_SIZE},
        {"from": "T0", "to": "T2", "data_size": DATA_SIZE},
        {"from": "T0", "to": "T3", "data_size": DATA_SIZE},
        {"from": "T1", "to": "T4", "data_size": DATA_SIZE},
        {"from": "T2", "to": "T4", "data_size": DATA_SIZE},
        {"from": "T3", "to": "T4", "data_size": DATA_SIZE},
    ]
    return tasks, edges


def _make_bottleneck_dag_large():
    """Fork-join with 8 parallel tasks spread across all nodes.

    T0(n0) -> {T1(n1), T2(n2), T3(n3), T4(n4),
               T5(n1), T6(n2), T7(n3), T8(n4)} -> T9(n0)
    8 concurrent outbound + 8 concurrent return transfers.
    """
    pin_targets = ["n1", "n2", "n3", "n4", "n1", "n2", "n3", "n4"]
    tasks = [{"id": "T0", "compute_cost": COMPUTE_COST, "pinned_to": "n0"}]
    for i, target in enumerate(pin_targets, 1):
        tasks.append({"id": f"T{i}", "compute_cost": COMPUTE_COST,
                       "pinned_to": target})
    tasks.append({"id": "T9", "compute_cost": COMPUTE_COST, "pinned_to": "n0"})

    edges = []
    for i in range(1, 9):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": DATA_SIZE})
        edges.append({"from": f"T{i}", "to": "T9", "data_size": DATA_SIZE})
    return tasks, edges


BOTTLENECK_DAG_GENERATORS = {
    "small":  ("small (5 tasks, chain)", _make_bottleneck_dag_small),
    "medium": ("medium (5 tasks, fork-join 3)", _make_bottleneck_dag_medium),
    "large":  ("large (10 tasks, fork-join 8)", _make_bottleneck_dag_large),
}

# ─── YAML Generation ────────────────────────────────────────────


def generate_scenario_yaml(net_size_label, dag_size, dag_generators=None,
                           network_fn=None):
    """Generate a complete scenario YAML string."""
    if dag_generators is None:
        dag_generators = DAG_GENERATORS
    if network_fn is None:
        grid_size, _ = NETWORK_SIZES[net_size_label]
        nodes, links = generate_network(grid_size)
    else:
        nodes, links = network_fn()

    _, gen_fn = dag_generators[dag_size]
    tasks, edges = gen_fn()

    yaml = "scenario:\n"
    yaml += f'  name: "routing_cmp_{net_size_label}net_{dag_size}dag"\n'
    yaml += "  network:\n"
    yaml += "    nodes:\n"
    for n in nodes:
        yaml += (f"      - {{id: {n['id']}, compute_capacity: {n['compute_capacity']}, "
                 f"position: {{x: {n['x']}, y: {n['y']}}}}}\n")
    yaml += "    links:\n"
    for link in links:
        yaml += f"      - {{id: {link['id']}, from: {link['from']}, to: {link['to']}}}\n"
    yaml += "  dags:\n"
    yaml += "    - id: dag_1\n"
    yaml += "      inject_at: 0.0\n"
    yaml += "      tasks:\n"
    for t in tasks:
        pin = f", pinned_to: {t['pinned_to']}" if t.get('pinned_to') else ""
        yaml += f"        - {{id: {t['id']}, compute_cost: {t['compute_cost']}{pin}}}\n"
    yaml += "      edges:\n"
    for e in edges:
        yaml += f"        - {{from: {e['from']}, to: {e['to']}, data_size: {e['data_size']}}}\n"
    yaml += "  config:\n"
    yaml += "    scheduler: heft\n"
    yaml += "    seed: 42\n"
    yaml += "    routing: direct\n"
    yaml += "    interference: csma_bianchi\n"
    return yaml


# ─── Subprocess Runner ───────────────────────────────────────────


def run_scenario(yaml_str, run_label, routing):
    """Write YAML to temp file, invoke ncsim via subprocess, return output dir."""
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
        "--interference", "csma_bianchi",
        "--scheduler", "heft",
        "--routing", routing,
        "--seed", "42",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR running {run_label}:")
        print(f"    stdout: {result.stdout[-500:] if result.stdout else '(empty)'}")
        print(f"    stderr: {result.stderr[-500:] if result.stderr else '(empty)'}")
        return None
    return outdir


def get_makespan(outdir):
    """Get makespan from metrics.json."""
    path = os.path.join(outdir, "metrics.json")
    try:
        with open(path) as f:
            data = json.load(f)
        if data.get("status") == "error":
            return None
        return data["makespan"]
    except Exception:
        return None


# ─── Main ────────────────────────────────────────────────────────


def main():
    os.makedirs(OUTDIR, exist_ok=True)

    print()
    print("=" * 70)
    print("  Routing Comparison: Widest Path vs Shortest Path")
    print("  Scheduler: HEFT | Interference: csma_bianchi")
    print(f"  Task config: compute_cost={COMPUTE_COST}, data_size={DATA_SIZE}MB")
    print(f"  Grid spacing: {GRID_SPACING}m")
    print("=" * 70)
    print()

    net_sizes = ["small", "medium", "large"]
    dag_sizes = ["small", "medium", "large"]
    routings = ["widest_path", "shortest_path"]

    # Print network info
    for ns in net_sizes:
        grid_size, desc = NETWORK_SIZES[ns]
        nodes, links = generate_network(grid_size)
        print(f"  {ns} network: {desc}, {len(links)} links")
    print()

    # Run all 18 simulations
    results = {}  # (net_size, dag_size, routing) -> makespan
    total = len(net_sizes) * len(dag_sizes) * len(routings)
    count = 0

    for net_size in net_sizes:
        for dag_size in dag_sizes:
            yaml_str = generate_scenario_yaml(net_size, dag_size)
            for routing in routings:
                count += 1
                label = f"{net_size}net_{dag_size}dag_{routing}"
                print(f"  [{count:>2d}/{total}] {label}...", end=" ", flush=True)
                outdir = run_scenario(yaml_str, label, routing)
                if outdir is None:
                    results[(net_size, dag_size, routing)] = None
                    print("FAILED")
                else:
                    ms = get_makespan(outdir)
                    results[(net_size, dag_size, routing)] = ms
                    print(f"{ms:.4f}s" if ms is not None else "ERROR")

    print()

    # ─── Per-Network Tables ──────────────────────────────────────

    for net_size in net_sizes:
        _, net_desc = NETWORK_SIZES[net_size]
        print(f"  Network: {net_desc}")
        print(f"  {'─' * 58}")
        print(f"  {'DAG Size':<12s}  {'Widest(s)':>12s}  {'Shortest(s)':>12s}  {'Diff(%)':>10s}")

        for dag_size in dag_sizes:
            w = results.get((net_size, dag_size, "widest_path"))
            s = results.get((net_size, dag_size, "shortest_path"))
            w_str = f"{w:.4f}" if w is not None else "ERROR"
            s_str = f"{s:.4f}" if s is not None else "ERROR"
            if w is not None and s is not None and s != 0:
                diff = ((w - s) / s) * 100
                diff_str = f"{diff:+.1f}%"
            else:
                diff_str = "n/a"
            print(f"  {dag_size:<12s}  {w_str:>12s}  {s_str:>12s}  {diff_str:>10s}")
        print()

    # ─── Summary Table ───────────────────────────────────────────

    print(f"  Summary Table (makespan in seconds, W=widest / S=shortest):")
    print(f"  {'─' * 62}")
    header = f"  {'':>12s}"
    for net_size in net_sizes:
        _, net_desc = NETWORK_SIZES[net_size]
        header += f"  {net_desc:>16s}"
    print(header)

    for dag_size in dag_sizes:
        desc, _ = DAG_GENERATORS[dag_size]
        row = f"  {dag_size + ' DAG':<12s}"
        for net_size in net_sizes:
            w = results.get((net_size, dag_size, "widest_path"))
            s = results.get((net_size, dag_size, "shortest_path"))
            if w is not None and s is not None:
                cell = f"{w:.2f}/{s:.2f}"
            else:
                cell = "err"
            row += f"  {cell:>16s}"
        print(row)

    print()

    # ─── Winner Summary ──────────────────────────────────────────

    widest_wins = 0
    shortest_wins = 0
    ties = 0

    print(f"  Winner per cell (lower makespan):")
    print(f"  {'─' * 62}")
    header = f"  {'':>12s}"
    for net_size in net_sizes:
        _, net_desc = NETWORK_SIZES[net_size]
        header += f"  {net_desc:>16s}"
    print(header)

    for dag_size in dag_sizes:
        row = f"  {dag_size + ' DAG':<12s}"
        for net_size in net_sizes:
            w = results.get((net_size, dag_size, "widest_path"))
            s = results.get((net_size, dag_size, "shortest_path"))
            if w is not None and s is not None:
                if abs(w - s) / max(w, s) < 0.001:
                    cell = "TIE"
                    ties += 1
                elif w < s:
                    cell = "WIDEST"
                    widest_wins += 1
                else:
                    cell = "SHORTEST"
                    shortest_wins += 1
            else:
                cell = "n/a"
            row += f"  {cell:>16s}"
        print(row)

    print()
    print(f"  Wins: widest_path={widest_wins}, shortest_path={shortest_wins}, ties={ties}")
    print()
    print(f"  Trace files saved to: {OUTDIR}")
    print()

    # ─── Bottleneck Network Scenarios ────────────────────────────

    print()
    print("=" * 70)
    print("  Bottleneck Network: Widest Path Advantage")
    print("  5 nodes in a line (30m spacing), direct n0-n4 at 120m")
    print("  Adjacent links: 8.6 MB/s | Direct n0-n4: 1.075 MB/s")
    print("  Tasks pinned to force cross-network transfers")
    print("=" * 70)
    print()

    bn_nodes, bn_links = generate_bottleneck_network()
    print(f"  bottleneck network: 5 nodes, {len(bn_links)} links")
    print()

    bn_results = {}
    bn_dag_sizes = ["small", "medium", "large"]
    bn_total = len(bn_dag_sizes) * len(routings)
    bn_count = 0

    for dag_size in bn_dag_sizes:
        yaml_str = generate_scenario_yaml(
            "bottleneck", dag_size,
            dag_generators=BOTTLENECK_DAG_GENERATORS,
            network_fn=generate_bottleneck_network,
        )
        for routing in routings:
            bn_count += 1
            label = f"bottleneck_{dag_size}dag_{routing}"
            print(f"  [{bn_count:>2d}/{bn_total}] {label}...", end=" ", flush=True)
            outdir = run_scenario(yaml_str, label, routing)
            if outdir is None:
                bn_results[(dag_size, routing)] = None
                print("FAILED")
            else:
                ms = get_makespan(outdir)
                bn_results[(dag_size, routing)] = ms
                print(f"{ms:.4f}s" if ms is not None else "ERROR")

    print()
    print(f"  {'DAG':<12s}  {'Widest(s)':>12s}  {'Shortest(s)':>12s}  "
          f"{'Diff(%)':>10s}  {'Winner':>10s}")
    print(f"  {'─' * 62}")

    for dag_size in bn_dag_sizes:
        desc, _ = BOTTLENECK_DAG_GENERATORS[dag_size]
        w = bn_results.get((dag_size, "widest_path"))
        s = bn_results.get((dag_size, "shortest_path"))
        w_str = f"{w:.4f}" if w is not None else "ERROR"
        s_str = f"{s:.4f}" if s is not None else "ERROR"
        if w is not None and s is not None and s != 0:
            diff = ((w - s) / s) * 100
            diff_str = f"{diff:+.1f}%"
            if abs(w - s) / max(w, s) < 0.001:
                winner = "TIE"
            elif w < s:
                winner = "WIDEST"
            else:
                winner = "SHORTEST"
        else:
            diff_str = "n/a"
            winner = "n/a"
        print(f"  {desc:<12s}  {w_str:>12s}  {s_str:>12s}  "
              f"{diff_str:>10s}  {winner:>10s}")

    print()
    print(f"  Trace files saved to: {OUTDIR}")
    print()

    # Check for failures
    all_results = list(results.values()) + list(bn_results.values())
    failures = sum(1 for v in all_results if v is None)
    if failures > 0:
        print(f"  WARNING: {failures} simulation(s) failed!")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

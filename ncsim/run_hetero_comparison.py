#!/usr/bin/env python3
"""Heterogeneous data-size comparison: W / S / GS / GC / GB / GO / GSD.

Tests whether GB (greedy-by-bytes) wins when data sizes vary widely (2-100MB).
Runs on 4x4 grid and bottleneck networks with large heterogeneous DAGs.
"""

import json
import os
import subprocess
import sys

OUTDIR = "/tmp/ncsim_hetero_comparison"
COMPUTE_COST = 500
NUM_SEEDS = 30
GRID_SPACING = 40

_CAPACITIES = [200, 100, 150, 80, 300, 120, 250, 180, 160, 90, 220, 140, 280, 110, 190, 170]

# ─── Networks ────────────────────────────────────────────────────


def generate_4x4_network():
    """4x4 grid mesh (16 nodes, 68 links)."""
    n = 4
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
            add_pair(row, col, row, col + 1)
            add_pair(row, col, row + 1, col)
            if (row + col) % 2 == 0:
                add_pair(row, col, row + 1, col + 1)
            else:
                add_pair(row, col, row + 1, col - 1)
    links = []
    for a, b in sorted(pairs):
        na, nb = f"n{a}", f"n{b}"
        links.append({"id": f"l_{na}_{nb}", "from": na, "to": nb})
        links.append({"id": f"l_{nb}_{na}", "from": nb, "to": na})
    return nodes, links


def generate_bottleneck_network():
    """5 nodes in a line (30m spacing) + direct n0-n4 at 120m."""
    nodes = [
        {"id": "n0", "compute_capacity": 200, "x": 0, "y": 0},
        {"id": "n1", "compute_capacity": 200, "x": 30, "y": 0},
        {"id": "n2", "compute_capacity": 200, "x": 60, "y": 0},
        {"id": "n3", "compute_capacity": 200, "x": 90, "y": 0},
        {"id": "n4", "compute_capacity": 200, "x": 120, "y": 0},
    ]
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


# ─── Heterogeneous DAGs ──────────────────────────────────────────


def make_hetero_grid_dag():
    """20-task multi-level DAG with data sizes from 2MB to 100MB.

    Same topology as _make_dag_large but with widely varying edge sizes.
    Critical-path edges get large sizes; secondary edges get small sizes.
    """
    tasks = [{"id": f"T{i}", "compute_cost": COMPUTE_COST} for i in range(20)]
    edges = []

    # Stage 0->1: T0 fans out to T1-T4
    # One big flow (100MB), one medium (50MB), two small (5MB, 2MB)
    s0_sizes = [100, 50, 5, 2]
    for i, sz in zip(range(1, 5), s0_sizes):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": sz})

    # Stage 1->2: selective connections with mixed sizes
    stage1_to_2 = {
        1: [(5, 80), (6, 3)],     # T1 sends big (80MB) and tiny (3MB)
        2: [(6, 40), (7, 40)],    # T2 sends two medium (40MB each)
        3: [(8, 5),  (9, 5)],     # T3 sends small
        4: [(9, 60), (10, 2)],    # T4 sends one big (60MB), one tiny
    }
    for src, dsts in stage1_to_2.items():
        for dst, sz in dsts:
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": sz})

    # Stage 2->3: mixed sizes
    stage2_to_3 = {
        5: [(11, 90), (12, 3)],
        6: [(12, 10), (13, 70)],
        7: [(13, 5),  (14, 5)],
        8: [(14, 30), (15, 30)],
        9: [(15, 2),  (16, 2)],
        10: [(16, 50), (11, 8)],
    }
    for src, dsts in stage2_to_3.items():
        for dst, sz in dsts:
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": sz})

    # Stage 3->4: final merge, mixed sizes
    stage3_to_4 = {
        11: [(17, 80)],
        12: [(17, 3)],
        13: [(18, 60)],
        14: [(18, 5)],
        15: [(19, 40)],
        16: [(19, 2)],
    }
    for src, dsts in stage3_to_4.items():
        for dst, sz in dsts:
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": sz})

    total_data = sum(e["data_size"] for e in edges)
    sizes = sorted(set(e["data_size"] for e in edges))
    return tasks, edges, total_data, sizes


def make_hetero_bottleneck_dag():
    """Fork-join with 8 parallel tasks, heterogeneous data sizes (2-100MB).

    T0(n0) -> {T1..T8} -> T9(n0)
    Big flows go to far nodes, small flows to near nodes.
    """
    pin_targets = ["n1", "n2", "n3", "n4", "n1", "n2", "n3", "n4"]
    # Outbound sizes: some huge, some tiny
    out_sizes =   [100,   80,   60,    5,    3,    2,   50,   40]
    # Return sizes: inverse pattern (big ones return small, small ones return big)
    ret_sizes =   [  5,    3,    2,  100,   80,   60,    5,    3]

    tasks = [{"id": "T0", "compute_cost": COMPUTE_COST, "pinned_to": "n0"}]
    for i, target in enumerate(pin_targets, 1):
        tasks.append({"id": f"T{i}", "compute_cost": COMPUTE_COST,
                       "pinned_to": target})
    tasks.append({"id": "T9", "compute_cost": COMPUTE_COST, "pinned_to": "n0"})

    edges = []
    for i in range(1, 9):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": out_sizes[i-1]})
        edges.append({"from": f"T{i}", "to": "T9", "data_size": ret_sizes[i-1]})

    total_data = sum(e["data_size"] for e in edges)
    sizes = sorted(set(e["data_size"] for e in edges))
    return tasks, edges, total_data, sizes


# ─── YAML + Runner ───────────────────────────────────────────────


def generate_yaml(nodes, links, tasks, edges):
    """Generate scenario YAML string."""
    yaml = "scenario:\n"
    yaml += '  name: "hetero_test"\n'
    yaml += "  network:\n    nodes:\n"
    for n in nodes:
        yaml += (f"      - {{id: {n['id']}, compute_capacity: {n['compute_capacity']}, "
                 f"position: {{x: {n['x']}, y: {n['y']}}}}}\n")
    yaml += "    links:\n"
    for link in links:
        yaml += f"      - {{id: {link['id']}, from: {link['from']}, to: {link['to']}}}\n"
    yaml += "  dags:\n    - id: dag_1\n      inject_at: 0.0\n      tasks:\n"
    for t in tasks:
        pin = f", pinned_to: {t['pinned_to']}" if t.get("pinned_to") else ""
        yaml += f"        - {{id: {t['id']}, compute_cost: {t['compute_cost']}{pin}}}\n"
    yaml += "      edges:\n"
    for e in edges:
        yaml += f"        - {{from: {e['from']}, to: {e['to']}, data_size: {e['data_size']}}}\n"
    yaml += "  config:\n    scheduler: heft\n    seed: 42\n"
    yaml += "    routing: direct\n    interference: csma_bianchi\n"
    return yaml


def run_scenario(yaml_str, label, routing, seed=42, greedy_order=None):
    """Run a single ncsim scenario."""
    outdir = os.path.join(OUTDIR, label)
    os.makedirs(outdir, exist_ok=True)
    input_dir = os.path.join(OUTDIR, "_inputs", label)
    os.makedirs(input_dir, exist_ok=True)
    yaml_path = os.path.join(input_dir, "scenario.yaml")
    with open(yaml_path, "w") as f:
        f.write(yaml_str)
    cmd = [
        sys.executable, "-m", "ncsim",
        "--scenario", yaml_path, "--output", outdir,
        "--interference", "csma_bianchi", "--scheduler", "heft",
        "--routing", routing, "--seed", str(seed),
    ]
    if greedy_order is not None:
        cmd.extend(["--greedy-order", greedy_order])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return outdir


def get_makespan(outdir):
    path = os.path.join(outdir, "metrics.json")
    try:
        with open(path) as f:
            data = json.load(f)
        if data.get("status") == "error":
            return None
        return data["makespan"]
    except Exception:
        return None


def run_averaged(yaml_str, base_label, routing, greedy_order=None):
    makespans = []
    for seed in range(1, NUM_SEEDS + 1):
        label = f"{base_label}_s{seed}"
        outdir = run_scenario(yaml_str, label, routing, seed=seed,
                              greedy_order=greedy_order)
        if outdir is not None:
            ms = get_makespan(outdir)
            if ms is not None:
                makespans.append(ms)
    if not makespans:
        return None
    return sum(makespans) / len(makespans)


# ─── Main ────────────────────────────────────────────────────────


STRATEGIES = [
    ("W",   "widest_path",              None),
    ("S",   "shortest_path",            None),
    ("GS",  "interference_aware",       "start"),
    ("GC",  "interference_aware",       "criticality"),
    ("GB",  "interference_aware",       "bytes"),
    ("GO",  "interference_aware",       "overlap"),
    ("GSD", "interference_aware_dynamic", None),
]
LABELS = [s[0] for s in STRATEGIES]


def run_comparison(name, yaml_str, total_data, sizes):
    """Run all strategies on a scenario and print results."""
    col_w = 10
    results = {}
    n_strats = len(STRATEGIES)
    print(f"  Running {n_strats} strategies x {NUM_SEEDS} seeds "
          f"= {n_strats * NUM_SEEDS} simulations...")
    print(f"  Data sizes: {sizes}  (total: {total_data}MB)")
    print()

    for idx, (label, routing, greedy_order) in enumerate(STRATEGIES, 1):
        base = f"{name}_{label}"
        print(f"  [{idx:>2d}/{n_strats}] {label:>3s} ...", end=" ", flush=True)
        mean_ms = run_averaged(yaml_str, base, routing, greedy_order)
        results[label] = mean_ms
        if mean_ms is not None:
            print(f"{mean_ms:.4f}s")
        else:
            print("FAILED")

    print()
    hdr = "  ".join(f"{lb + '(s)':>{col_w}s}" for lb in LABELS)
    print(f"  {hdr}  {'Best':>6s}")
    print(f"  {'─' * ((col_w + 2) * len(LABELS) + 8)}")

    vals = {lb: v for lb, v in results.items() if v is not None}
    strs = {lb: f"{v:.2f}" if v is not None else "ERR" for lb, v in results.items()}
    best = min(vals, key=vals.get) if vals else "n/a"
    row = "  ".join(f"{strs[lb]:>{col_w}s}" for lb in LABELS)
    print(f"  {row}  {best:>6s}")

    # Show improvement over worst G-variant
    g_variants = {lb: vals[lb] for lb in ["GS", "GC", "GB", "GO"] if lb in vals}
    if len(g_variants) >= 2:
        best_g = min(g_variants, key=g_variants.get)
        worst_g = max(g_variants, key=g_variants.get)
        spread = g_variants[worst_g] - g_variants[best_g]
        pct = (spread / g_variants[worst_g]) * 100
        print(f"  G-variant spread: {best_g}={g_variants[best_g]:.2f} to "
              f"{worst_g}={g_variants[worst_g]:.2f} ({pct:.1f}% range)")
    print()
    return results


def main():
    os.makedirs(OUTDIR, exist_ok=True)

    print()
    print("=" * 100)
    print("  Heterogeneous Data-Size Comparison (averaged over 30 seeds)")
    print("  Edge sizes range from 2MB to 100MB — tests whether GB benefits")
    print("  Scheduler: HEFT | Interference: csma_bianchi")
    print("=" * 100)

    # ─── 4x4 Grid ────────────────────────────────────────────────
    print()
    print("─" * 80)
    print("  SCENARIO 1: 4x4 Grid (16 nodes) + Heterogeneous 20-task DAG")
    print("─" * 80)
    print()

    nodes, links = generate_4x4_network()
    tasks, edges, total_data, sizes = make_hetero_grid_dag()
    yaml_str = generate_yaml(nodes, links, tasks, edges)
    grid_results = run_comparison("grid4x4_hetero", yaml_str, total_data, sizes)

    # ─── Bottleneck ───────────────────────────────────────────────
    print()
    print("─" * 80)
    print("  SCENARIO 2: Bottleneck (5 nodes, relay chain) + Heterogeneous fork-join")
    print("─" * 80)
    print()

    nodes, links = generate_bottleneck_network()
    tasks, edges, total_data, sizes = make_hetero_bottleneck_dag()
    yaml_str = generate_yaml(nodes, links, tasks, edges)
    bn_results = run_comparison("bottleneck_hetero", yaml_str, total_data, sizes)

    # ─── Summary ──────────────────────────────────────────────────
    print("=" * 80)
    print("  Summary")
    print("=" * 80)
    print()
    for name, res in [("4x4 Grid", grid_results), ("Bottleneck", bn_results)]:
        vals = {k: v for k, v in res.items() if v is not None}
        if vals:
            best = min(vals, key=vals.get)
            print(f"  {name:>12s}: winner = {best} ({vals[best]:.2f}s)")
            g_only = {k: v for k, v in vals.items() if k.startswith("G") and k != "GSD"}
            if g_only:
                best_g = min(g_only, key=g_only.get)
                print(f"               best pre-planner = {best_g} ({g_only[best_g]:.2f}s)")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

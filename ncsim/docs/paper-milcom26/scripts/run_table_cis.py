#!/usr/bin/env python3
"""Re-run experiments needed to compute 95% CIs for Tables III and V.

Table III rows (grid topology, fixed SH):
  4x4 small / 4x4 large / 7x7 small / 7x7 large
  HEFT-1 and HEFT-2 each.

Table V rows (random density, large DAG):
  L150 / L300 with HEFT-1/HEFT-2 + SH routing.
  L500 with HEFT-1/HEFT-2 + GSD-D routing.

Note: HEFT-1 SH at L150/L300/L500 with the large DAG is also in
penalty_sweep_results.json at penalty=0.001, so we re-extract those samples
to avoid duplicate work.

Output: docs/paper-milcom26/table_ci_results.json
"""

import concurrent.futures
import json
import math
import os
import random
import subprocess
import sys
import time
from pathlib import Path

OUTDIR       = "/tmp/ncsim_table_cis"
DOCS_DIR     = Path(__file__).resolve().parent
RESULTS_PATH = DOCS_DIR / "table_ci_results.json"
NUM_SEEDS    = 30
MAX_WORKERS  = 8
INTERFERENCE = "csma_bianchi"

COMM_RANGE   = 80
NUM_NODES    = 50
TOPO_SEED    = 42
GRID_SPACING = 40

_COMPUTE_COSTS = [500, 200, 800, 350, 1000, 150, 600, 450, 750, 300,
                  900, 250, 550, 700, 400, 850]
_DATA_SIZES    = [10.0, 2.0, 25.0, 5.0, 30.0, 8.0, 15.0, 3.0,
                  20.0, 6.0, 12.0, 28.0, 4.0, 18.0, 7.0, 22.0]
_CAPACITIES    = [200, 100, 150, 80, 300, 120, 250, 180, 160, 90,
                  220, 140, 280, 110, 190, 170]


def make_dag_small():
    """Fork-join: T0 -> T1..T6 -> T7 (8 tasks)."""
    np = 6
    tasks = [{"id": f"T{i}", "compute_cost": _COMPUTE_COSTS[i % len(_COMPUTE_COSTS)]}
             for i in range(np + 2)]
    edges, ei = [], 0
    for i in range(1, np + 1):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
        edges.append({"from": f"T{i}", "to": f"T{np+1}", "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    return tasks, edges


def make_dag_large():
    """30-task 5-stage pipeline (matches Table III/V 'large')."""
    tasks = [{"id": f"T{i}", "compute_cost": _COMPUTE_COSTS[i % len(_COMPUTE_COSTS)]}
             for i in range(30)]
    edges, ei = [], 0
    for i in range(1, 7):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    s1, s2, s3, s4 = range(1, 7), range(7, 15), range(15, 23), range(23, 29)
    for i, src in enumerate(s1):
        for j in range(2):
            edges.append({"from": f"T{src}", "to": f"T{s2[(i*2+j)%len(s2)]}",
                          "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    for i, src in enumerate(s2):
        for j in range(2):
            edges.append({"from": f"T{src}", "to": f"T{s3[(i*2+j)%len(s3)]}",
                          "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    for i, src in enumerate(s3):
        edges.append({"from": f"T{src}", "to": f"T{s4[i % len(s4)]}",
                      "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    for src in s4:
        edges.append({"from": f"T{src}", "to": "T29",
                      "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    return tasks, edges


def generate_random_network(n_nodes, side_length, comm_range, seed):
    rng = random.Random(seed)
    pos = [(rng.uniform(0, side_length), rng.uniform(0, side_length))
           for _ in range(n_nodes)]
    def dist(i, j):
        return math.sqrt((pos[i][0] - pos[j][0])**2 + (pos[i][1] - pos[j][1])**2)
    pairs = {(min(i, j), max(i, j))
             for i in range(n_nodes) for j in range(i + 1, n_nodes)
             if dist(i, j) <= comm_range}
    def component(start, edge_set):
        adj = {i: set() for i in range(n_nodes)}
        for a, b in edge_set:
            adj[a].add(b); adj[b].add(a)
        seen, q = set(), [start]
        while q:
            v = q.pop()
            if v in seen: continue
            seen.add(v); q.extend(adj[v] - seen)
        return seen
    while True:
        comp = component(0, pairs)
        if len(comp) == n_nodes: break
        outside = set(range(n_nodes)) - comp
        best = min(((dist(a, b), (min(a, b), max(a, b)))
                    for a in comp for b in outside))[1]
        pairs.add(best)
    nodes = [{"id": f"n{i}",
              "compute_capacity": _CAPACITIES[i % len(_CAPACITIES)],
              "x": round(pos[i][0], 1), "y": round(pos[i][1], 1)}
             for i in range(n_nodes)]
    links = []
    for a, b in sorted(pairs):
        na, nb = f"n{a}", f"n{b}"
        links.append({"id": f"l_{na}_{nb}", "from": na, "to": nb})
        links.append({"id": f"l_{nb}_{na}", "from": nb, "to": na})
    return nodes, links


def generate_grid_network(n):
    nodes = []
    for row in range(n):
        for col in range(n):
            idx = row * n + col
            nodes.append({"id": f"n{idx}",
                          "compute_capacity": _CAPACITIES[idx % len(_CAPACITIES)],
                          "x": col * GRID_SPACING, "y": row * GRID_SPACING})
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


def make_yaml(nodes, links, tasks, edges):
    y  = 'scenario:\n  name: "table_ci"\n  network:\n    nodes:\n'
    for nd in nodes:
        y += (f"      - {{id: {nd['id']}, compute_capacity: {nd['compute_capacity']}, "
              f"position: {{x: {nd['x']}, y: {nd['y']}}}}}\n")
    y += "    links:\n"
    for lk in links:
        y += f"      - {{id: {lk['id']}, from: {lk['from']}, to: {lk['to']}}}\n"
    y += "  dags:\n    - id: dag_1\n      inject_at: 0.0\n      tasks:\n"
    for t in tasks:
        y += f"        - {{id: {t['id']}, compute_cost: {t['compute_cost']}}}\n"
    y += "      edges:\n"
    for e in edges:
        y += f"        - {{from: {e['from']}, to: {e['to']}, data_size: {e['data_size']}}}\n"
    y += f"  config:\n    scheduler: heft\n    seed: 42\n"
    y += f"    routing: direct\n    interference: {INTERFERENCE}\n"
    return y


def run_one(yaml_path, outdir, scheduler, routing, seed):
    os.makedirs(outdir, exist_ok=True)
    cmd = [sys.executable, "-m", "ncsim",
           "--scenario", yaml_path, "--output", outdir,
           "--interference", INTERFERENCE,
           "--scheduler", scheduler,
           "--routing", routing,
           "--seed", str(seed)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        with open(os.path.join(outdir, "metrics.json")) as f:
            d = json.load(f)
        return d["makespan"] if d.get("status") != "error" else None
    except Exception:
        return None


def run_seeds(yaml_str, base_label, scheduler, routing):
    inp_dir = os.path.join(OUTDIR, "_inputs", base_label)
    os.makedirs(inp_dir, exist_ok=True)
    yaml_path = os.path.join(inp_dir, "scenario.yaml")
    with open(yaml_path, "w") as f:
        f.write(yaml_str)
    def _run(seed):
        outdir = os.path.join(OUTDIR, f"{base_label}_s{seed}")
        return run_one(yaml_path, outdir, scheduler, routing, seed)
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        out = list(ex.map(_run, range(1, NUM_SEEDS + 1)))
    return [v for v in out if v is not None]


def stats(samples):
    if not samples:
        return None
    n = len(samples)
    mean = sum(samples) / n
    var = sum((x - mean)**2 for x in samples) / max(1, n - 1)
    std = var**0.5
    ci = 1.96 * std / (n**0.5)
    return {"n": n, "mean": mean, "std": std, "ci95_halfwidth": ci, "samples": samples}


# Configurations to run.
# (base_label, network_spec, dag_fn, scheduler, routing)
# network_spec: ("grid", n) or ("random", side_len)
CONFIGS = [
    # Table III: grid, both DAG sizes, both schedulers, fixed SH.
    ("4x4_S_heft1", ("grid", 4),    "small", "heft1", "shortest_hop"),
    ("4x4_S_heft2", ("grid", 4),    "small", "heft2", "shortest_hop"),
    ("4x4_L_heft1", ("grid", 4),    "large", "heft1", "shortest_hop"),
    ("4x4_L_heft2", ("grid", 4),    "large", "heft2", "shortest_hop"),
    ("7x7_S_heft1", ("grid", 7),    "small", "heft1", "shortest_hop"),
    ("7x7_S_heft2", ("grid", 7),    "small", "heft2", "shortest_hop"),
    ("7x7_L_heft1", ("grid", 7),    "large", "heft1", "shortest_hop"),
    ("7x7_L_heft2", ("grid", 7),    "large", "heft2", "shortest_hop"),
    # Table V: random, large DAG, best routing per (density, scheduler).
    # L150/L300 best is SH for both. L500 best is GSD-D for both.
    ("L150_heft1_SH",    ("random", 150), "large", "heft1", "shortest_hop"),
    ("L150_heft2_SH",    ("random", 150), "large", "heft2", "shortest_hop"),
    ("L300_heft1_SH",    ("random", 300), "large", "heft1", "shortest_hop"),
    ("L300_heft2_SH",    ("random", 300), "large", "heft2", "shortest_hop"),
    ("L500_heft1_GSDD",  ("random", 500), "large", "heft1", "interference_aware_dynamic_deferral"),
    ("L500_heft2_GSDD",  ("random", 500), "large", "heft2", "interference_aware_dynamic_deferral"),
]


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    t0 = time.time()
    print(f"\n{'='*72}")
    print(f"  Table III / V CI runs ({len(CONFIGS)} configs, {NUM_SEEDS} seeds each)")
    print(f"{'='*72}\n")

    dag_cache = {"small": make_dag_small(), "large": make_dag_large()}
    network_cache = {}
    results = {}

    for label, net_spec, dag_kind, scheduler, routing in CONFIGS:
        if net_spec not in network_cache:
            net_type, net_param = net_spec
            if net_type == "grid":
                network_cache[net_spec] = generate_grid_network(net_param)
            else:
                network_cache[net_spec] = generate_random_network(NUM_NODES, net_param, COMM_RANGE, TOPO_SEED)
        nodes, links = network_cache[net_spec]
        tasks, edges = dag_cache[dag_kind]
        yaml_str = make_yaml(nodes, links, tasks, edges)
        t1 = time.time()
        samples = run_seeds(yaml_str, label, scheduler, routing)
        elapsed = time.time() - t1
        s = stats(samples)
        results[label] = s
        if s:
            print(f"  {label:<22s}  n={s['n']:>2d}/{NUM_SEEDS}  "
                  f"mean={s['mean']:>10.3f}  ci95={s['ci95_halfwidth']:>8.3f}  "
                  f"({elapsed:.1f}s)")
        else:
            print(f"  {label:<22s}  FAILED  ({elapsed:.1f}s)")

    elapsed = time.time() - t0
    print(f"\nTotal elapsed: {elapsed/60:.1f} min")
    with open(RESULTS_PATH, "w") as f:
        json.dump({
            "num_seeds": NUM_SEEDS,
            "interference": INTERFERENCE,
            "results": results,
        }, f, indent=2)
    print(f"Results written to: {RESULTS_PATH}")


if __name__ == "__main__":
    main()

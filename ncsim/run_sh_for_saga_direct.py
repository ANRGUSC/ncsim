#!/usr/bin/env python3
"""Run ncsim with SH (shortest_hop) routing for all grid+random experiments.

Generates grid_sh_results.json and random_sh_results.json in the same format
as grid_augmented.json / random_augmented.json, keyed by "{exp}|{sched}|SH"
and "{density}|{dag}|{sched}|SH".

Grid:   4 experiments × 3 schedulers × 30 seeds = 360 runs
Random: 7 densities × 2 DAG sizes × 3 schedulers × 30 seeds = 1260 runs
Total: 1620 runs
"""

import concurrent.futures
import json
import math
import os
import random
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

NUM_SEEDS   = 30
MAX_WORKERS = 8
GRID_SPACING = 40
COMM_RANGE   = 80
NUM_NODES    = 50

SCHEDULERS = ["heft", "heft1", "heft2"]

GRID_DIR = Path("/tmp/ncsim_full_eval")
RAND_DIR = Path("/tmp/ncsim_random_eval")

_COMPUTE_COSTS = [500, 200, 800, 350, 1000, 150, 600, 450, 750, 300,
                  900, 250, 550, 700, 400, 850]
_DATA_SIZES    = [10.0, 2.0, 25.0, 5.0, 30.0, 8.0, 15.0, 3.0,
                  20.0, 6.0, 12.0, 28.0, 4.0, 18.0, 7.0, 22.0]
_CAPACITIES    = [200, 100, 150, 80, 300, 120, 250, 180, 160, 90,
                  220, 140, 280, 110, 190, 170]


# ── Network generators ────────────────────────────────────────────────────────

def generate_grid_network(grid_size):
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


def generate_random_network(side_length, seed):
    rng = random.Random(seed)
    pos = [(rng.uniform(0, side_length), rng.uniform(0, side_length))
           for _ in range(NUM_NODES)]

    def dist(i, j):
        return math.sqrt((pos[i][0]-pos[j][0])**2 + (pos[i][1]-pos[j][1])**2)

    pairs = {(min(i, j), max(i, j))
             for i in range(NUM_NODES) for j in range(i+1, NUM_NODES)
             if dist(i, j) <= COMM_RANGE}

    def component(start, edge_set):
        adj = {i: set() for i in range(NUM_NODES)}
        for a, b in edge_set:
            adj[a].add(b); adj[b].add(a)
        seen, q = set(), [start]
        while q:
            n = q.pop()
            if n in seen: continue
            seen.add(n); q.extend(adj[n] - seen)
        return seen

    while True:
        comp = component(0, pairs)
        if len(comp) == NUM_NODES:
            break
        outside = set(range(NUM_NODES)) - comp
        best = min(((dist(a, b), (min(a, b), max(a, b)))
                    for a in comp for b in outside))[1]
        pairs.add(best)

    nodes = [{"id": f"n{i}",
              "compute_capacity": _CAPACITIES[i % len(_CAPACITIES)],
              "x": round(pos[i][0], 1), "y": round(pos[i][1], 1)}
             for i in range(NUM_NODES)]
    links = []
    for a, b in sorted(pairs):
        na, nb = f"n{a}", f"n{b}"
        links.append({"id": f"l_{na}_{nb}", "from": na, "to": nb})
        links.append({"id": f"l_{nb}_{na}", "from": nb, "to": na})
    return nodes, links


# ── DAG generators ────────────────────────────────────────────────────────────

def make_dag_small():
    np_ = 6
    tasks = [{"id": "T0", "compute_cost": _COMPUTE_COSTS[0]}]
    for i in range(1, np_+1):
        tasks.append({"id": f"T{i}", "compute_cost": _COMPUTE_COSTS[i % len(_COMPUTE_COSTS)]})
    tasks.append({"id": f"T{np_+1}", "compute_cost": _COMPUTE_COSTS[(np_+1) % len(_COMPUTE_COSTS)]})
    sink = f"T{np_+1}"
    edges, ei = [], 0
    for i in range(1, np_+1):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
        edges.append({"from": f"T{i}", "to": sink, "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    return tasks, edges


def make_dag_large_4x4():
    tasks = [{"id": f"T{i}", "compute_cost": _COMPUTE_COSTS[i % len(_COMPUTE_COSTS)]} for i in range(30)]
    edges, ei = [], 0
    for i in range(1, 7):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    s1, s2, s3, s4 = range(1,7), range(7,15), range(15,23), range(23,29)
    for i, src in enumerate(s1):
        for j in range(2):
            edges.append({"from": f"T{src}", "to": f"T{s2[(i*2+j)%8]}", "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    for i, src in enumerate(s2):
        for j in range(2):
            edges.append({"from": f"T{src}", "to": f"T{s3[(i*2+j)%8]}", "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    for i, src in enumerate(s3):
        edges.append({"from": f"T{src}", "to": f"T{s4[i%6]}", "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    for src in s4:
        edges.append({"from": f"T{src}", "to": "T29", "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    return tasks, edges


def make_dag_large_7x7():
    tasks = [{"id": f"T{i}", "compute_cost": _COMPUTE_COSTS[i % len(_COMPUTE_COSTS)]} for i in range(60)]
    edges, ei = [], 0
    s1 = list(range(1, 11)); s2 = list(range(11, 25))
    s3 = list(range(25, 39)); s4 = list(range(39, 49)); s5 = list(range(49, 59))
    for i in s1:
        edges.append({"from": "T0", "to": f"T{i}", "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    for i, src in enumerate(s1):
        for j in range(3):
            edges.append({"from": f"T{src}", "to": f"T{s2[(i*3+j)%14]}", "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    for i, src in enumerate(s2):
        for j in range(2):
            edges.append({"from": f"T{src}", "to": f"T{s3[(i*2+j)%14]}", "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    for i, src in enumerate(s3):
        edges.append({"from": f"T{src}", "to": f"T{s4[i%10]}", "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    for i, src in enumerate(s4):
        edges.append({"from": f"T{src}", "to": f"T{s5[i%10]}", "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    for src in s5:
        edges.append({"from": f"T{src}", "to": "T59", "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    return tasks, edges


def make_dag_large_random():
    tasks = [{"id": f"T{i}", "compute_cost": _COMPUTE_COSTS[i % len(_COMPUTE_COSTS)]} for i in range(30)]
    edges, ei = [], 0
    for i in range(1, 7):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    s1, s2, s3, s4 = range(1,7), range(7,15), range(15,23), range(23,29)
    for i, src in enumerate(s1):
        for j in range(2):
            edges.append({"from": f"T{src}", "to": f"T{s2[(i*2+j)%len(list(s2))]}",
                          "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    for i, src in enumerate(s2):
        for j in range(2):
            edges.append({"from": f"T{src}", "to": f"T{s3[(i*2+j)%len(list(s3))]}",
                          "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    for i, src in enumerate(s3):
        edges.append({"from": f"T{src}", "to": f"T{s4[i%len(list(s4))]}",
                      "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    for src in s4:
        edges.append({"from": f"T{src}", "to": "T29", "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    return tasks, edges


# ── YAML builder ──────────────────────────────────────────────────────────────

def build_yaml(nodes, links, tasks, edges):
    y = "scenario:\n  name: sh_eval\n  network:\n    nodes:\n"
    for n in nodes:
        y += f"      - {{id: {n['id']}, compute_capacity: {n['compute_capacity']}, position: {{x: {n['x']}, y: {n['y']}}}}}\n"
    y += "    links:\n"
    for lk in links:
        y += f"      - {{id: {lk['id']}, from: {lk['from']}, to: {lk['to']}}}\n"
    y += "  dags:\n    - id: dag_1\n      inject_at: 0.0\n      tasks:\n"
    for t in tasks:
        y += f"        - {{id: {t['id']}, compute_cost: {t['compute_cost']}}}\n"
    y += "      edges:\n"
    for e in edges:
        y += f"        - {{from: {e['from']}, to: {e['to']}, data_size: {e['data_size']}}}\n"
    y += "  config:\n    scheduler: heft\n    seed: 42\n    routing: direct\n    interference: csma_bianchi\n"
    return y


# ── Runner ────────────────────────────────────────────────────────────────────

def run_one(yaml_str, scheduler, seed):
    with tempfile.TemporaryDirectory() as tmpdir:
        scenario_dir = os.path.join(tmpdir, "input")
        outdir       = os.path.join(tmpdir, "output")
        os.makedirs(scenario_dir); os.makedirs(outdir)
        yaml_path = os.path.join(scenario_dir, "scenario.yaml")
        with open(yaml_path, "w") as f:
            f.write(yaml_str)
        cmd = [
            sys.executable, "-m", "ncsim",
            "--scenario", yaml_path, "--output", outdir,
            "--interference", "csma_bianchi",
            "--scheduler", scheduler,
            "--routing", "shortest_hop",
            "--seed", str(seed),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(Path(__file__).parent))
        if result.returncode != 0:
            return None
        metrics_path = os.path.join(outdir, "metrics.json")
        if not os.path.exists(metrics_path):
            return None
        with open(metrics_path) as f:
            return json.load(f)


def aggregate(makespans):
    if not makespans:
        return None
    return {
        "mean": round(statistics.mean(makespans), 3),
        "std":  round(statistics.stdev(makespans) if len(makespans) > 1 else 0.0, 3),
        "n":    len(makespans),
    }


# ── Grid evaluation ───────────────────────────────────────────────────────────

GRID_CONFIGS = {
    "4x4_small": (4, "small"),
    "4x4_large": (4, "large"),
    "7x7_small": (7, "small"),
    "7x7_large": (7, "large"),
}


def run_grid():
    print("Running grid SH simulations (360 runs) ...")
    results = {}

    for exp, (grid_size, dag_label) in GRID_CONFIGS.items():
        nodes, links = generate_grid_network(grid_size)
        if dag_label == "small":
            tasks, edges = make_dag_small()
        elif grid_size == 4:
            tasks, edges = make_dag_large_4x4()
        else:
            tasks, edges = make_dag_large_7x7()
        yaml_str = build_yaml(nodes, links, tasks, edges)

        for sched in SCHEDULERS:
            jobs = [(yaml_str, sched, seed) for seed in range(1, NUM_SEEDS+1)]
            makespans = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
                futs = {ex.submit(run_one, y, s, sd): (y, s, sd) for y, s, sd in jobs}
                for fut in concurrent.futures.as_completed(futs):
                    m = fut.result()
                    if m:
                        makespans.append(m["makespan"])
            key = f"{exp}|{sched}|SH"
            results[key] = aggregate(makespans)
            ms = results[key]
            if ms:
                print(f"  {key}: mean={ms['mean']:.1f}s  n={ms['n']}")
            else:
                print(f"  {key}: NO DATA (all runs failed)")

    return results


# ── Random evaluation ─────────────────────────────────────────────────────────

DENSITIES = [
    ("L150", 150), ("L200", 200), ("L250", 250), ("L300", 300),
    ("L350", 350), ("L400", 400), ("L500", 500),
]


def run_random():
    print("\nRunning random network SH simulations (1260 runs) ...")
    results = {}
    tasks_small, edges_small = make_dag_small()
    tasks_large, edges_large = make_dag_large_random()
    dag_data = {"small": (tasks_small, edges_small), "large": (tasks_large, edges_large)}

    for dl, side in DENSITIES:
        for dag_label, (tasks, edges) in dag_data.items():
            for sched in SCHEDULERS:
                makespans = []
                jobs = []
                for seed in range(1, NUM_SEEDS+1):
                    nodes, links = generate_random_network(side, seed)
                    yaml_str = build_yaml(nodes, links, tasks, edges)
                    jobs.append((yaml_str, sched, seed))

                with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
                    futs = {ex.submit(run_one, y, s, sd): sd for y, s, sd in jobs}
                    for fut in concurrent.futures.as_completed(futs):
                        m = fut.result()
                        if m:
                            makespans.append(m["makespan"])

                key = f"{dl}|{dag_label}|{sched}|SH"
                results[key] = aggregate(makespans)
                ms = results[key]
                if ms:
                    print(f"  {key}: mean={ms['mean']:.1f}s  n={ms['n']}")
                else:
                    print(f"  {key}: NO DATA")

    return results


if __name__ == "__main__":
    grid_results = run_grid()
    rand_results = run_random()

    grid_path = GRID_DIR / "grid_sh_results.json"
    rand_path  = RAND_DIR / "random_sh_results.json"
    GRID_DIR.mkdir(exist_ok=True)
    RAND_DIR.mkdir(exist_ok=True)

    with open(grid_path, "w") as f:
        json.dump(grid_results, f, indent=2)
    with open(rand_path, "w") as f:
        json.dump(rand_results, f, indent=2)

    print(f"\nGrid results  → {grid_path}")
    print(f"Random results → {rand_path}")

#!/usr/bin/env python3
"""Communication/computation ratio sweep.

Scales DAG edge data_size by {0.1, 1.0, 10.0} on L150 (dense) and L500
(sparse) random networks, large DAG, HEFT-1+SH and HEFT-2+SH, 20 seeds.

Output: docs/paper-milcom26/commcomp_sweep_results.json
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

OUTDIR       = "/tmp/ncsim_commcomp_sweep"
DOCS_DIR     = Path(__file__).resolve().parent
RESULTS_PATH = DOCS_DIR / "commcomp_sweep_results.json"
NUM_SEEDS    = 20
MAX_WORKERS  = 8
INTERFERENCE = "csma_bianchi"
ROUTING      = "shortest_hop"

SCHEDULERS  = ["heft1", "heft2"]
SCALES      = [0.1, 1.0, 10.0]
NETWORKS    = [("L150", 150), ("L500", 500)]

COMM_RANGE   = 80
NUM_NODES    = 50
TOPO_SEED    = 42

_COMPUTE_COSTS = [500, 200, 800, 350, 1000, 150, 600, 450, 750, 300,
                  900, 250, 550, 700, 400, 850]
_DATA_SIZES    = [10.0, 2.0, 25.0, 5.0, 30.0, 8.0, 15.0, 3.0,
                  20.0, 6.0, 12.0, 28.0, 4.0, 18.0, 7.0, 22.0]
_CAPACITIES    = [200, 100, 150, 80, 300, 120, 250, 180, 160, 90,
                  220, 140, 280, 110, 190, 170]


def make_dag_large():
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
        if len(comp) == n_nodes:
            break
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


def make_yaml(nodes, links, tasks, edges):
    y  = 'scenario:\n  name: "commcomp_sweep"\n  network:\n    nodes:\n'
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


def run_one(yaml_path, outdir, scheduler, scale, seed):
    os.makedirs(outdir, exist_ok=True)
    cmd = [sys.executable, "-m", "ncsim",
           "--scenario", yaml_path, "--output", outdir,
           "--interference", INTERFERENCE,
           "--scheduler", scheduler,
           "--routing", ROUTING,
           "--data-size-scale", str(scale),
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


def run_seeds(yaml_str, base_label, scheduler, scale):
    inp_dir = os.path.join(OUTDIR, "_inputs", base_label)
    os.makedirs(inp_dir, exist_ok=True)
    yaml_path = os.path.join(inp_dir, "scenario.yaml")
    with open(yaml_path, "w") as f:
        f.write(yaml_str)

    def _run(seed):
        outdir = os.path.join(OUTDIR, f"{base_label}_s{seed}")
        return run_one(yaml_path, outdir, scheduler, scale, seed)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        results = list(ex.map(_run, range(1, NUM_SEEDS + 1)))
    return [v for v in results if v is not None]


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    t0 = time.time()
    print(f"\n{'='*72}")
    print("  Comm/comp ratio sweep")
    print(f"  Scales: {SCALES}  Networks: {[n[0] for n in NETWORKS]}")
    print(f"  Schedulers: {SCHEDULERS}, large DAG, SH, {NUM_SEEDS} seeds")
    print(f"{'='*72}\n")

    tasks, edges = make_dag_large()
    results = {}

    for net_label, side_len in NETWORKS:
        nodes, links = generate_random_network(NUM_NODES, side_len, COMM_RANGE, TOPO_SEED)
        yaml_str = make_yaml(nodes, links, tasks, edges)
        print(f"  {net_label}: {len(nodes)} nodes, {len(links)//2} links")

        for scheduler in SCHEDULERS:
            for scale in SCALES:
                label = f"{net_label}_{scheduler}_x{scale}"
                t1 = time.time()
                seeds_ms = run_seeds(yaml_str, label, scheduler, scale)
                elapsed = time.time() - t1
                if seeds_ms:
                    mean = sum(seeds_ms) / len(seeds_ms)
                    var = sum((x - mean) ** 2 for x in seeds_ms) / max(1, len(seeds_ms) - 1)
                    std = var ** 0.5
                    ci = 1.96 * std / (len(seeds_ms) ** 0.5)
                else:
                    mean = std = ci = None
                results[(net_label, scheduler, scale)] = {
                    "n_seeds_ok": len(seeds_ms),
                    "mean": mean,
                    "std": std,
                    "ci95_halfwidth": ci,
                    "samples": seeds_ms,
                }
                ms_str = f"{mean:.2f}" if mean is not None else "FAIL"
                print(f"    {scheduler}  scale={scale:>4}  n={len(seeds_ms):>2d}/{NUM_SEEDS}  "
                      f"mean={ms_str}  ({elapsed:.1f}s)")

    elapsed = time.time() - t0
    print(f"\nTotal elapsed: {elapsed/60:.1f} min")

    json_results = {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in results.items()}
    with open(RESULTS_PATH, "w") as f:
        json.dump({
            "scales": SCALES,
            "networks": [n[0] for n in NETWORKS],
            "schedulers": SCHEDULERS,
            "num_seeds": NUM_SEEDS,
            "routing": ROUTING,
            "interference": INTERFERENCE,
            "results": json_results,
        }, f, indent=2)
    print(f"Results written to: {RESULTS_PATH}")


if __name__ == "__main__":
    main()

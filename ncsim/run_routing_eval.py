#!/usr/bin/env python3
"""Routing scheme evaluation: W / S / GS / GC / GB / GO / GSD on 4x4 and 7x7 grids.

Each (network, DAG, routing) combo is run 30 times with different seeds
to average out HEFT non-determinism from Python hash randomization.

Network sizes:
  4x4 grid (16 nodes, 40m spacing)
  7x7 grid (49 nodes, 40m spacing)

DAG sizes per network:
  small:  8 tasks  (fork-join)
  large: 30 tasks  (multi-level pipeline)  — for 4x4
  large: 60 tasks  (multi-level pipeline)  — for 7x7
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

OUTDIR = "/tmp/ncsim_routing_eval"
COMPUTE_COST = 500
DATA_SIZE = 10.0
NUM_SEEDS = 30
GRID_SPACING = 40

_CAPACITIES = [200, 100, 150, 80, 300, 120, 250, 180, 160, 90,
               220, 140, 280, 110, 190, 170]

STRATEGIES = [
    ("W",   "widest_path",                None),
    ("S",   "shortest_path",              None),
    ("GS",  "interference_aware",         "start"),
    ("GC",  "interference_aware",         "criticality"),
    ("GB",  "interference_aware",         "bytes"),
    ("GO",  "interference_aware",         "overlap"),
    ("GSD", "interference_aware_dynamic", None),
]
LABELS = [s[0] for s in STRATEGIES]


# ─── Network Generation ─────────────────────────────────────────

def generate_network(grid_size):
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


# ─── DAG Generators ─────────────────────────────────────────────

def make_dag_small():
    """Fork-join: 1 source -> 6 parallel -> 1 sink (8 tasks).

    Produces 12 inter-node edges (6 fan-out + 6 fan-in), enough concurrency
    to stress routing on a 4x4 grid without overwhelming a 7x7.
    """
    n_parallel = 6
    tasks = [{"id": "T0", "compute_cost": COMPUTE_COST}]
    for i in range(1, n_parallel + 1):
        tasks.append({"id": f"T{i}", "compute_cost": COMPUTE_COST})
    tasks.append({"id": f"T{n_parallel + 1}", "compute_cost": COMPUTE_COST})

    sink = f"T{n_parallel + 1}"
    edges = []
    for i in range(1, n_parallel + 1):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": DATA_SIZE})
        edges.append({"from": f"T{i}", "to": sink, "data_size": DATA_SIZE})
    return tasks, edges


def make_dag_large_4x4():
    """Multi-level pipeline for 4x4 grid: 30 tasks across 5 stages.

    Stage 0: T0 (source)
    Stage 1: T1-T6 (6 tasks)
    Stage 2: T7-T14 (8 tasks)
    Stage 3: T15-T22 (8 tasks)
    Stage 4: T23-T28 (6 tasks)
    Stage 5: T29 (sink)

    Cross-connected between stages for rich routing diversity.
    """
    tasks = [{"id": f"T{i}", "compute_cost": COMPUTE_COST} for i in range(30)]
    edges = []

    # Stage 0 -> Stage 1
    for i in range(1, 7):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": DATA_SIZE})

    # Stage 1 -> Stage 2 (selective connections)
    s1 = list(range(1, 7))
    s2 = list(range(7, 15))
    for i, src in enumerate(s1):
        for j in range(2):  # each stage-1 task feeds ~2 stage-2 tasks
            dst = s2[(i * 2 + j) % len(s2)]
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": DATA_SIZE})

    # Stage 2 -> Stage 3
    s3 = list(range(15, 23))
    for i, src in enumerate(s2):
        for j in range(2):
            dst = s3[(i * 2 + j) % len(s3)]
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": DATA_SIZE})

    # Stage 3 -> Stage 4
    s4 = list(range(23, 29))
    for i, src in enumerate(s3):
        dst = s4[i % len(s4)]
        edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": DATA_SIZE})

    # Stage 4 -> Sink
    for i in s4:
        edges.append({"from": f"T{i}", "to": "T29", "data_size": DATA_SIZE})

    return tasks, edges


def make_dag_large_7x7():
    """Multi-level pipeline for 7x7 grid: 60 tasks across 6 stages.

    Stage 0: T0 (source)
    Stage 1: T1-T10 (10 tasks)
    Stage 2: T11-T24 (14 tasks)
    Stage 3: T25-T38 (14 tasks)
    Stage 4: T39-T48 (10 tasks)
    Stage 5: T49-T58 (10 tasks)
    Stage 6: T59 (sink)
    """
    tasks = [{"id": f"T{i}", "compute_cost": COMPUTE_COST} for i in range(60)]
    edges = []

    s1 = list(range(1, 11))
    s2 = list(range(11, 25))
    s3 = list(range(25, 39))
    s4 = list(range(39, 49))
    s5 = list(range(49, 59))

    # Source -> Stage 1
    for i in s1:
        edges.append({"from": "T0", "to": f"T{i}", "data_size": DATA_SIZE})

    # Stage 1 -> Stage 2 (each feeds ~3)
    for i, src in enumerate(s1):
        for j in range(3):
            dst = s2[(i * 3 + j) % len(s2)]
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": DATA_SIZE})

    # Stage 2 -> Stage 3
    for i, src in enumerate(s2):
        for j in range(2):
            dst = s3[(i * 2 + j) % len(s3)]
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": DATA_SIZE})

    # Stage 3 -> Stage 4
    for i, src in enumerate(s3):
        dst = s4[i % len(s4)]
        edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": DATA_SIZE})

    # Stage 4 -> Stage 5
    for i, src in enumerate(s4):
        dst = s5[i % len(s5)]
        edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": DATA_SIZE})

    # Stage 5 -> Sink
    for i in s5:
        edges.append({"from": f"T{i}", "to": "T59", "data_size": DATA_SIZE})

    return tasks, edges


# ─── YAML + Runner ──────────────────────────────────────────────

def generate_yaml(grid_size, tasks, edges):
    nodes, links = generate_network(grid_size)
    yaml = "scenario:\n"
    yaml += f'  name: "eval_{grid_size}x{grid_size}"\n'
    yaml += "  network:\n    nodes:\n"
    for n in nodes:
        yaml += (f"      - {{id: {n['id']}, compute_capacity: {n['compute_capacity']}, "
                 f"position: {{x: {n['x']}, y: {n['y']}}}}}\n")
    yaml += "    links:\n"
    for lk in links:
        yaml += f"      - {{id: {lk['id']}, from: {lk['from']}, to: {lk['to']}}}\n"
    yaml += "  dags:\n    - id: dag_1\n      inject_at: 0.0\n      tasks:\n"
    for t in tasks:
        yaml += f"        - {{id: {t['id']}, compute_cost: {t['compute_cost']}}}\n"
    yaml += "      edges:\n"
    for e in edges:
        yaml += f"        - {{from: {e['from']}, to: {e['to']}, data_size: {e['data_size']}}}\n"
    yaml += "  config:\n    scheduler: heft\n    seed: 42\n"
    yaml += "    routing: direct\n    interference: csma_bianchi\n"
    return yaml


def run_one(yaml_str, label, routing, seed, greedy_order=None):
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
    try:
        with open(os.path.join(outdir, "metrics.json")) as f:
            data = json.load(f)
        if data.get("status") == "error":
            return None
        return data["makespan"]
    except Exception:
        return None


def run_averaged(yaml_str, base_label, routing, greedy_order=None):
    makespans = []
    for seed in range(1, NUM_SEEDS + 1):
        outdir = run_one(yaml_str, f"{base_label}_s{seed}", routing, seed, greedy_order)
        if outdir:
            ms = get_makespan(outdir)
            if ms is not None:
                makespans.append(ms)
    if not makespans:
        return None
    return sum(makespans) / len(makespans)


# ─── Experiments ─────────────────────────────────────────────────

EXPERIMENTS = [
    {
        "name": "4x4_small",
        "grid": 4,
        "dag_label": "small (8 tasks, fork-join)",
        "dag_fn": make_dag_small,
    },
    {
        "name": "4x4_large",
        "grid": 4,
        "dag_label": "large (30 tasks, 5-stage pipeline)",
        "dag_fn": make_dag_large_4x4,
    },
    {
        "name": "7x7_small",
        "grid": 7,
        "dag_label": "small (8 tasks, fork-join)",
        "dag_fn": make_dag_small,
    },
    {
        "name": "7x7_large",
        "grid": 7,
        "dag_label": "large (60 tasks, 6-stage pipeline)",
        "dag_fn": make_dag_large_7x7,
    },
]


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    t0 = time.time()

    print()
    print("=" * 100)
    print("  Routing Scheme Evaluation: W / S / GS / GC / GB / GO / GSD")
    print("  Scheduler: HEFT | Interference: csma_bianchi | Seeds: 30")
    print(f"  Task config: compute_cost={COMPUTE_COST}, data_size={DATA_SIZE}MB")
    print(f"  Grid spacing: {GRID_SPACING}m")
    print("=" * 100)
    print()

    # Print network info
    for gs in sorted({e["grid"] for e in EXPERIMENTS}):
        nodes, links = generate_network(gs)
        print(f"  {gs}x{gs} grid: {len(nodes)} nodes, {len(links)} links")
    print()

    total_combos = len(EXPERIMENTS) * len(STRATEGIES)
    total_runs = total_combos * NUM_SEEDS
    print(f"  {total_combos} combos x {NUM_SEEDS} seeds = {total_runs} simulation runs")
    print()

    results = {}  # (experiment_name, label) -> mean makespan
    combo_idx = 0

    for exp in EXPERIMENTS:
        tasks, edges = exp["dag_fn"]()
        yaml_str = generate_yaml(exp["grid"], tasks, edges)
        print(f"  ── {exp['grid']}x{exp['grid']} grid, {exp['dag_label']} ──")

        for label, routing, greedy_order in STRATEGIES:
            combo_idx += 1
            go_suffix = f"_{greedy_order}" if greedy_order else ""
            base_label = f"{exp['name']}_{routing}{go_suffix}"
            print(f"  [{combo_idx:>2d}/{total_combos}] {label:>3s} ...", end=" ", flush=True)
            mean_ms = run_averaged(yaml_str, base_label, routing, greedy_order)
            results[(exp["name"], label)] = mean_ms
            if mean_ms is not None:
                print(f"{mean_ms:.4f}s")
            else:
                print("FAILED")
        print()

    elapsed = time.time() - t0

    # ─── Results Table ────────────────────────────────────────────
    col_w = 10
    hdr = "  ".join(f"{lb + '(s)':>{col_w}s}" for lb in LABELS)

    print("=" * 100)
    print("  RESULTS (mean makespan over 30 seeds)")
    print("=" * 100)
    print()
    print(f"  {'Experiment':<22s}  {hdr}  {'Best':>6s}  {'vs W':>7s}")
    print(f"  {'─' * (22 + 2 + (col_w + 2) * len(LABELS) + 8 + 9)}")

    for exp in EXPERIMENTS:
        vals = {}
        strs = {}
        for lb in LABELS:
            v = results.get((exp["name"], lb))
            strs[lb] = f"{v:.4f}" if v is not None else "ERROR"
            if v is not None:
                vals[lb] = v
        best = min(vals, key=vals.get) if vals else "n/a"
        w_val = vals.get("W")
        best_val = vals.get(best) if best != "n/a" else None
        if w_val and best_val:
            improvement = (w_val - best_val) / w_val * 100
            imp_str = f"{improvement:+.1f}%"
        else:
            imp_str = "n/a"
        row_vals = "  ".join(f"{strs[lb]:>{col_w}s}" for lb in LABELS)
        label = f"{exp['grid']}x{exp['grid']} {exp['dag_label'].split('(')[0].strip()}"
        print(f"  {label:<22s}  {row_vals}  {best:>6s}  {imp_str:>7s}")

    print()

    # ─── Pairwise Comparison ──────────────────────────────────────
    print("  Winner per experiment:")
    print()
    wins = {lb: 0 for lb in LABELS}
    for exp in EXPERIMENTS:
        vals = {lb: results.get((exp["name"], lb)) for lb in LABELS}
        vals = {k: v for k, v in vals.items() if v is not None}
        if vals:
            best_val = min(vals.values())
            winners = [k for k, v in vals.items()
                       if abs(v - best_val) / max(best_val, 1e-9) < 0.005]
            label = f"{exp['grid']}x{exp['grid']} {exp['dag_label'].split('(')[0].strip()}"
            if len(winners) == 1:
                wins[winners[0]] += 1
                print(f"    {label:<22s} -> {winners[0]}")
            else:
                print(f"    {label:<22s} -> TIE ({', '.join(winners)})")

    print()
    print(f"  Win counts: {', '.join(f'{lb}={wins[lb]}' for lb in LABELS)}")
    print()
    print(f"  Elapsed: {elapsed:.0f}s")
    print(f"  Output:  {OUTDIR}")
    print()

    # ─── Save JSON for programmatic analysis ──────────────────────
    json_results = {}
    for exp in EXPERIMENTS:
        json_results[exp["name"]] = {
            "grid": exp["grid"],
            "dag": exp["dag_label"],
        }
        for lb in LABELS:
            json_results[exp["name"]][lb] = results.get((exp["name"], lb))

    json_path = os.path.join(OUTDIR, "eval_results.json")
    with open(json_path, "w") as f:
        json.dump(json_results, f, indent=2)
    print(f"  JSON results: {json_path}")

    failures = sum(1 for v in results.values() if v is None)
    if failures > 0:
        print(f"\n  WARNING: {failures} combo(s) failed!")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

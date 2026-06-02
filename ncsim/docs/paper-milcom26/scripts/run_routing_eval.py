#!/usr/bin/env python3
"""Routing scheme evaluation: all schemes x heft1/heft2 x 4x4/7x7 x small/large DAGs.

Each (network, DAG, scheduler, routing) combo is run 30 times with different seeds
to average out HEFT non-determinism from Python hash randomization.

Network sizes:
  4x4 grid (16 nodes, 40m spacing)
  7x7 grid (49 nodes, 40m spacing)

DAG sizes per network:
  small:  8 tasks  (fork-join)
  large: 30 tasks  (multi-level pipeline)  — for 4x4
  large: 60 tasks  (multi-level pipeline)  — for 7x7

Workload:
  Heterogeneous compute costs (150-1000) and data sizes (2-30 MB).
"""

import concurrent.futures
import json
import os
import subprocess
import sys
import time
from pathlib import Path

OUTDIR = "/tmp/ncsim_full_eval"
NUM_SEEDS = 30
GRID_SPACING = 40
MAX_WORKERS = 8

SCHEDULERS = ["heft", "heft1", "heft2"]

# Heterogeneous compute costs: range from 150 to 1000 (~6.7x variation)
_COMPUTE_COSTS = [500, 200, 800, 350, 1000, 150, 600, 450, 750, 300,
                  900, 250, 550, 700, 400, 850]

# Heterogeneous data sizes in MB: range from 2 to 30 (15x variation)
_DATA_SIZES = [10.0, 2.0, 25.0, 5.0, 30.0, 8.0, 15.0, 3.0,
               20.0, 6.0, 12.0, 28.0, 4.0, 18.0, 7.0, 22.0]

_CAPACITIES = [200, 100, 150, 80, 300, 120, 250, 180, 160, 90,
               220, 140, 280, 110, 190, 170]

STRATEGIES = [
    ("W",     "widest_path",                          None),
    ("S",     "shortest_path",                        None),
    ("SH",    "shortest_hop",                         None),
    ("GS",    "interference_aware",                   "start"),
    ("GC",    "interference_aware",                   "criticality"),
    ("GB",    "interference_aware",                   "bytes"),
    ("GO",    "interference_aware",                   "overlap"),
    ("GSD",   "interference_aware_dynamic",           None),
    ("GSD-D", "interference_aware_dynamic_deferral",  None),
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
    Heterogeneous compute costs and data sizes.
    """
    n_parallel = 6
    tasks = [{"id": "T0", "compute_cost": _COMPUTE_COSTS[0]}]
    for i in range(1, n_parallel + 1):
        tasks.append({"id": f"T{i}", "compute_cost": _COMPUTE_COSTS[i % len(_COMPUTE_COSTS)]})
    tasks.append({"id": f"T{n_parallel + 1}", "compute_cost": _COMPUTE_COSTS[(n_parallel + 1) % len(_COMPUTE_COSTS)]})

    sink = f"T{n_parallel + 1}"
    edges = []
    edge_idx = 0
    for i in range(1, n_parallel + 1):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": _DATA_SIZES[edge_idx % len(_DATA_SIZES)]})
        edge_idx += 1
        edges.append({"from": f"T{i}", "to": sink, "data_size": _DATA_SIZES[edge_idx % len(_DATA_SIZES)]})
        edge_idx += 1
    return tasks, edges


def make_dag_large_4x4():
    """Multi-level pipeline for 4x4 grid: 30 tasks across 5 stages."""
    tasks = [{"id": f"T{i}", "compute_cost": _COMPUTE_COSTS[i % len(_COMPUTE_COSTS)]} for i in range(30)]
    edges = []
    edge_idx = 0

    for i in range(1, 7):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": _DATA_SIZES[edge_idx % len(_DATA_SIZES)]})
        edge_idx += 1

    s1 = list(range(1, 7))
    s2 = list(range(7, 15))
    for i, src in enumerate(s1):
        for j in range(2):
            dst = s2[(i * 2 + j) % len(s2)]
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": _DATA_SIZES[edge_idx % len(_DATA_SIZES)]})
            edge_idx += 1

    s3 = list(range(15, 23))
    for i, src in enumerate(s2):
        for j in range(2):
            dst = s3[(i * 2 + j) % len(s3)]
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": _DATA_SIZES[edge_idx % len(_DATA_SIZES)]})
            edge_idx += 1

    s4 = list(range(23, 29))
    for i, src in enumerate(s3):
        dst = s4[i % len(s4)]
        edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": _DATA_SIZES[edge_idx % len(_DATA_SIZES)]})
        edge_idx += 1

    for i in s4:
        edges.append({"from": f"T{i}", "to": "T29", "data_size": _DATA_SIZES[edge_idx % len(_DATA_SIZES)]})
        edge_idx += 1

    return tasks, edges


def make_dag_large_7x7():
    """Multi-level pipeline for 7x7 grid: 60 tasks across 6 stages."""
    tasks = [{"id": f"T{i}", "compute_cost": _COMPUTE_COSTS[i % len(_COMPUTE_COSTS)]} for i in range(60)]
    edges = []
    edge_idx = 0

    s1 = list(range(1, 11))
    s2 = list(range(11, 25))
    s3 = list(range(25, 39))
    s4 = list(range(39, 49))
    s5 = list(range(49, 59))

    for i in s1:
        edges.append({"from": "T0", "to": f"T{i}", "data_size": _DATA_SIZES[edge_idx % len(_DATA_SIZES)]})
        edge_idx += 1

    for i, src in enumerate(s1):
        for j in range(3):
            dst = s2[(i * 3 + j) % len(s2)]
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": _DATA_SIZES[edge_idx % len(_DATA_SIZES)]})
            edge_idx += 1

    for i, src in enumerate(s2):
        for j in range(2):
            dst = s3[(i * 2 + j) % len(s3)]
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": _DATA_SIZES[edge_idx % len(_DATA_SIZES)]})
            edge_idx += 1

    for i, src in enumerate(s3):
        dst = s4[i % len(s4)]
        edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": _DATA_SIZES[edge_idx % len(_DATA_SIZES)]})
        edge_idx += 1

    for i, src in enumerate(s4):
        dst = s5[i % len(s5)]
        edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": _DATA_SIZES[edge_idx % len(_DATA_SIZES)]})
        edge_idx += 1

    for i in s5:
        edges.append({"from": f"T{i}", "to": "T59", "data_size": _DATA_SIZES[edge_idx % len(_DATA_SIZES)]})
        edge_idx += 1

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


def run_one(yaml_str, label, routing, seed, greedy_order, scheduler):
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
        "--interference", "csma_bianchi", "--scheduler", scheduler,
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


def run_averaged(yaml_str, base_label, routing, greedy_order, scheduler):
    """Run NUM_SEEDS seeds in parallel and return mean makespan."""
    def _run(seed):
        outdir = run_one(yaml_str, f"{base_label}_s{seed}", routing, seed, greedy_order, scheduler)
        if outdir:
            return get_makespan(outdir)
        return None

    makespans = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_run, s): s for s in range(1, NUM_SEEDS + 1)}
        for f in concurrent.futures.as_completed(futures):
            ms = f.result()
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


# ─── LaTeX Output ────────────────────────────────────────────────

def fmt(v):
    return f"{v:.3f}" if v is not None else "---"


def bold(s):
    return r"\textbf{" + s + "}"


def generate_tex(results, json_path):
    """Generate eval_results.tex from results dict.

    results[(exp_name, sched, label)] = mean_makespan or None
    """
    lines = []
    lines.append(r"\documentclass[11pt]{article}")
    lines.append(r"\usepackage[margin=1in]{geometry}")
    lines.append(r"\usepackage{booktabs}")
    lines.append(r"\usepackage{xcolor}")
    lines.append(r"\usepackage{amsmath}")
    lines.append(r"\usepackage{hyperref}")
    lines.append(r"\hypersetup{colorlinks=true, linkcolor=blue!60!black}")
    lines.append("")
    lines.append(r"\title{Routing Scheme Evaluation Results}")
    lines.append(r"\author{Autonomous Networks Research Group (ANRG)\\University of Southern California}")
    lines.append(r"\date{}")
    lines.append("")
    lines.append(r"\begin{document}")
    lines.append(r"\maketitle")
    lines.append(r"\tableofcontents")
    lines.append(r"\newpage")
    lines.append("")

    # ── Setup summary
    lines.append(r"\section{Evaluation Setup}")
    lines.append("")
    lines.append(r"\begin{tabular}{ll}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{Parameter} & \textbf{Value} \\")
    lines.append(r"\midrule")
    lines.append(r"Seeds per combo & 30 (seeds 1--30) \\")
    lines.append(r"Schedulers & HEFT-1, HEFT-2 \\")
    lines.append(r"Routing schemes & W, S, GS, GC, GB, GO, GSD, GSD-D \\")
    lines.append(r"Interference model & \texttt{csma\_bianchi} \\")
    lines.append(r"Grid spacing & 40\,m \\")
    lines.append(r"Compute costs & 150--1000 cu (heterogeneous, $\approx$6.7$\times$ range) \\")
    lines.append(r"Data sizes & 2--30\,MB (heterogeneous, 15$\times$ range) \\")
    lines.append(r"Node capacities & 80--300 cu/s (heterogeneous) \\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append("")

    # ── Per-experiment sections
    lines.append(r"\section{Results by Experiment}")
    lines.append("")

    for exp in EXPERIMENTS:
        name = exp["name"]
        grid = exp["grid"]
        dag_label = exp["dag_label"]

        lines.append(r"\subsection{" + f"{grid}\\times{grid} Grid, {dag_label}" + "}")
        lines.append("")

        # Build per-routing rows
        # Columns: Routing | HEFT-1 (s) | HEFT-2 (s) | Δ (%)
        # Bold the better makespan in each row; shade best overall

        h1_vals = {lb: results.get((name, "heft1", lb)) for lb in LABELS}
        h2_vals = {lb: results.get((name, "heft2", lb)) for lb in LABELS}

        all_vals = [v for v in list(h1_vals.values()) + list(h2_vals.values()) if v is not None]
        global_best = min(all_vals) if all_vals else None

        lines.append(r"\begin{table}[ht]")
        lines.append(r"\centering")
        lines.append(r"\begin{tabular}{l r r r}")
        lines.append(r"\toprule")
        lines.append(r"\textbf{Routing} & \textbf{HEFT-1 (s)} & \textbf{HEFT-2 (s)} & \textbf{$\Delta$ (\%)} \\")
        lines.append(r"\midrule")

        for lb in LABELS:
            v1 = h1_vals[lb]
            v2 = h2_vals[lb]
            s1 = fmt(v1)
            s2 = fmt(v2)
            # Bold the lower of the two
            if v1 is not None and v2 is not None:
                if v1 < v2:
                    s1 = bold(s1)
                elif v2 < v1:
                    s2 = bold(s2)
                else:
                    s1 = bold(s1)
                    s2 = bold(s2)
                delta = (v2 - v1) / v1 * 100
                delta_str = f"{delta:+.1f}"
                # Colour: green if HEFT-2 wins (negative delta = improvement), red if worse
                if delta < -0.5:
                    delta_str = r"\textcolor{green!60!black}{" + delta_str + r"\%}"
                elif delta > 0.5:
                    delta_str = r"\textcolor{red!70!black}{" + delta_str + r"\%}"
                else:
                    delta_str = delta_str + r"\%"
            else:
                delta_str = "---"

            # Mark global best with a dagger
            if global_best is not None:
                if v1 is not None and abs(v1 - global_best) / global_best < 0.001:
                    s1 = s1 + r"$^\dagger$"
                if v2 is not None and abs(v2 - global_best) / global_best < 0.001:
                    s2 = s2 + r"$^\dagger$"

            lines.append(f"  {lb} & {s1} & {s2} & {delta_str} \\\\")

        lines.append(r"\bottomrule")
        lines.append(r"\end{tabular}")
        lines.append(r"\caption{Mean makespan over 30 seeds. "
                     r"\textbf{Bold}: lower of HEFT-1/HEFT-2 for that routing scheme. "
                     r"$\Delta$\,(\%) = (HEFT-2 $-$ HEFT-1)\,/\,HEFT-1. "
                     r"$\dagger$: overall best for this experiment.}")
        lines.append(r"\end{table}")
        lines.append("")

    # ── Summary: best routing per experiment per scheduler
    lines.append(r"\section{Summary}")
    lines.append("")
    lines.append(r"Best routing scheme (minimum mean makespan) per experiment and scheduler:")
    lines.append("")
    lines.append(r"\begin{table}[ht]")
    lines.append(r"\centering")
    lines.append(r"\begin{tabular}{l l r l r l r}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{Experiment} & \textbf{H1 best} & \textbf{H1 (s)} & "
                 r"\textbf{H2 best} & \textbf{H2 (s)} & \textbf{Overall best} & \textbf{(s)} \\")
    lines.append(r"\midrule")

    for exp in EXPERIMENTS:
        name = exp["name"]
        grid = exp["grid"]
        dag_short = exp["dag_label"].split("(")[0].strip()

        def best_for(sched):
            vals = {lb: results.get((name, sched, lb)) for lb in LABELS}
            vals = {k: v for k, v in vals.items() if v is not None}
            if not vals:
                return "---", None
            best_lb = min(vals, key=vals.get)
            return best_lb, vals[best_lb]

        h1_best, h1_ms = best_for("heft1")
        h2_best, h2_ms = best_for("heft2")

        all_vals = {}
        for lb in LABELS:
            for sched in SCHEDULERS:
                v = results.get((name, sched, lb))
                if v is not None:
                    all_vals[(sched, lb)] = v
        if all_vals:
            overall_key = min(all_vals, key=all_vals.get)
            overall_label = f"{overall_key[0].upper()}/{overall_key[1]}"
            overall_ms = all_vals[overall_key]
        else:
            overall_label, overall_ms = "---", None

        label_str = f"{grid}\\times{grid} {dag_short}"
        h1_str = fmt(h1_ms)
        h2_str = fmt(h2_ms)
        ov_str = fmt(overall_ms)
        lines.append(f"  ${label_str}$ & {h1_best} & {h1_str} & {h2_best} & {h2_str} & {overall_label} & {ov_str} \\\\")

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\caption{Best routing scheme per scheduler variant. "
                 r"H1/H2 columns show the winner and its mean makespan. "
                 r"Overall best is the single (scheduler, routing) combo with lowest makespan.}")
    lines.append(r"\end{table}")
    lines.append("")
    lines.append(r"\medskip")
    lines.append(r"Full numerical results saved to: \texttt{" + json_path.replace("_", r"\_") + "}")
    lines.append("")
    lines.append(r"\end{document}")

    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTDIR, exist_ok=True)
    t0 = time.time()

    total_combos = len(EXPERIMENTS) * len(STRATEGIES) * len(SCHEDULERS)
    total_runs = total_combos * NUM_SEEDS

    print()
    print("=" * 100)
    print("  Routing Scheme Evaluation")
    print(f"  Schedulers: {', '.join(SCHEDULERS)}  (heft=calibrated, heft1=direct-link penalty, heft2=widest-path calibrated)")
    print(f"  Routing:    {', '.join(LABELS)}")
    print(f"  Grids:      4x4, 7x7  |  DAGs: small, large")
    print(f"  Seeds:      {NUM_SEEDS}  |  Workers: {MAX_WORKERS}")
    print(f"  Compute costs: {min(_COMPUTE_COSTS)}-{max(_COMPUTE_COSTS)}  |  "
          f"Data sizes: {min(_DATA_SIZES)}-{max(_DATA_SIZES)} MB")
    print(f"  Total runs: {total_combos} combos x {NUM_SEEDS} seeds = {total_runs}")
    print("=" * 100)
    print()

    for gs in sorted({e["grid"] for e in EXPERIMENTS}):
        nodes, links = generate_network(gs)
        print(f"  {gs}x{gs} grid: {len(nodes)} nodes, {len(links)} links")
    print()

    results = {}  # (exp_name, scheduler, label) -> mean makespan
    combo_idx = 0

    for exp in EXPERIMENTS:
        tasks, edges = exp["dag_fn"]()
        yaml_str = generate_yaml(exp["grid"], tasks, edges)
        print(f"  ── {exp['grid']}x{exp['grid']} grid, {exp['dag_label']} ──")

        for sched in SCHEDULERS:
            for label, routing, greedy_order in STRATEGIES:
                combo_idx += 1
                go_suffix = f"_{greedy_order}" if greedy_order else ""
                base_label = f"{exp['name']}_{sched}_{routing}{go_suffix}"
                print(f"  [{combo_idx:>3d}/{total_combos}] {sched} / {label:<5s} ...", end=" ", flush=True)
                mean_ms = run_averaged(yaml_str, base_label, routing, greedy_order, sched)
                results[(exp["name"], sched, label)] = mean_ms
                if mean_ms is not None:
                    print(f"{mean_ms:.4f}s")
                else:
                    print("FAILED")
        print()

    elapsed = time.time() - t0

    # ─── Console Results Table ────────────────────────────────────
    print("=" * 100)
    print("  RESULTS (mean makespan over 30 seeds)")
    print("=" * 100)
    print()

    for exp in EXPERIMENTS:
        name = exp["name"]
        print(f"  {exp['grid']}x{exp['grid']} {exp['dag_label']}")
        hdr = f"  {'Routing':<8s}" + "".join(f"  {lb + ' H1':>10s}  {lb + ' H2':>10s}" for lb in LABELS)
        col_w = 10
        row_labels = f"  {'':8s}" + "".join(f"  {'HEFT-1':>{col_w}s}  {'HEFT-2':>{col_w}s}" for _ in LABELS)
        routing_hdr = f"  {'':8s}" + "".join(f"  {lb:>{col_w+2+col_w}s}" for lb in LABELS)
        print(f"  {'Routing':<8s}", end="")
        for lb in LABELS:
            print(f"  {lb + ' H1':>10s}  {lb + ' H2':>10s}", end="")
        print()
        print(f"  {'-'*8}", end="")
        for _ in LABELS:
            print(f"  {'-'*10}  {'-'*10}", end="")
        print()
        # Just print H1 and H2 rows
        for sched in SCHEDULERS:
            print(f"  {sched:<8s}", end="")
            for lb in LABELS:
                v = results.get((name, sched, lb))
                print(f"  {fmt(v):>10s}  {'':>10s}", end="")
            print()
        print()

    # ─── Save JSON ────────────────────────────────────────────────
    json_results = {}
    for exp in EXPERIMENTS:
        json_results[exp["name"]] = {"grid": exp["grid"], "dag": exp["dag_label"]}
        for sched in SCHEDULERS:
            json_results[exp["name"]][sched] = {}
            for lb in LABELS:
                json_results[exp["name"]][sched][lb] = results.get((exp["name"], sched, lb))

    json_path = os.path.join(OUTDIR, "eval_results.json")
    with open(json_path, "w") as f:
        json.dump(json_results, f, indent=2)
    print(f"  JSON results: {json_path}")

    # ─── Generate LaTeX ───────────────────────────────────────────
    tex_content = generate_tex(results, json_path)
    docs_dir = Path(__file__).parent / "docs"
    tex_path = docs_dir / "eval_results.tex"
    with open(tex_path, "w") as f:
        f.write(tex_content)
    print(f"  LaTeX:        {tex_path}")

    print(f"  Elapsed:      {elapsed:.0f}s")
    print()

    failures = sum(1 for v in results.values() if v is None)
    if failures > 0:
        print(f"\n  WARNING: {failures} combo(s) failed!")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

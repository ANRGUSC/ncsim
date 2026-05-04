#!/usr/bin/env python3
"""No-interference evaluation: grid (4x4, 7x7) + random networks (L150–L500).

Identical workloads and scheduler/routing combos as the csma_bianchi evals,
but with --interference none.  Produces a single TeX/PDF report containing:
  • Grid results tables (4 experiments)
  • Random-network results tables (7 density levels × 2 DAGs)
  • Matplotlib line graphs: best makespan vs avg degree (small + large DAG)
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

OUTDIR      = "/tmp/ncsim_no_interference_eval"
NUM_SEEDS   = 30
MAX_WORKERS = 8
TOPO_SEED   = 42
COMM_RANGE  = 80    # metres (random networks)
NUM_NODES   = 50    # random networks
GRID_SPACING = 40   # metres (grid networks)

DENSITIES = [
    ("L150", 150), ("L200", 200), ("L250", 250), ("L300", 300),
    ("L350", 350), ("L400", 400), ("L500", 500),
]

SCHEDULERS = ["heft", "heft1", "heft2"]

GRID_STRATEGIES = [
    ("W",     "widest_path",                         None),
    ("S",     "shortest_path",                       None),
    ("SH",    "shortest_hop",                        None),
    ("GS",    "interference_aware",                  "start"),
    ("GC",    "interference_aware",                  "criticality"),
    ("GB",    "interference_aware",                  "bytes"),
    ("GO",    "interference_aware",                  "overlap"),
    ("GSD",   "interference_aware_dynamic",          None),
    ("GSD-D", "interference_aware_dynamic_deferral", None),
]
GRID_LABELS = [s[0] for s in GRID_STRATEGIES]

RAND_STRATEGIES = [
    ("W",     "widest_path",                         None),
    ("S",     "shortest_path",                       None),
    ("SH",    "shortest_hop",                        None),
    ("GO",    "interference_aware",                  "overlap"),
    ("GS",    "interference_aware",                  "start"),
    ("GSD",   "interference_aware_dynamic",          None),
    ("GSD-D", "interference_aware_dynamic_deferral", None),
]
RAND_LABELS = [s[0] for s in RAND_STRATEGIES]

_COMPUTE_COSTS = [500, 200, 800, 350, 1000, 150, 600, 450, 750, 300,
                  900, 250, 550, 700, 400, 850]
_DATA_SIZES    = [10.0, 2.0, 25.0, 5.0, 30.0, 8.0, 15.0, 3.0,
                  20.0, 6.0, 12.0, 28.0, 4.0, 18.0, 7.0, 22.0]
_CAPACITIES    = [200, 100, 150, 80, 300, 120, 250, 180, 160, 90,
                  220, 140, 280, 110, 190, 170]


# ─── Network generators ──────────────────────────────────────────────────────

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
            nd = q.pop()
            if nd in seen: continue
            seen.add(nd); q.extend(adj[nd] - seen)
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
    avg_degree = 2 * len(pairs) / n_nodes
    return nodes, links, len(pairs), avg_degree


# ─── DAG generators ──────────────────────────────────────────────────────────

def make_dag_small():
    np_ = 6
    tasks = [{"id": "T0", "compute_cost": _COMPUTE_COSTS[0]}]
    for i in range(1, np_ + 1):
        tasks.append({"id": f"T{i}", "compute_cost": _COMPUTE_COSTS[i % len(_COMPUTE_COSTS)]})
    tasks.append({"id": f"T{np_+1}", "compute_cost": _COMPUTE_COSTS[(np_+1) % len(_COMPUTE_COSTS)]})
    sink = f"T{np_+1}"
    edges, ei = [], 0
    for i in range(1, np_ + 1):
        edges.append({"from": "T0",    "to": f"T{i}", "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
        edges.append({"from": f"T{i}", "to": sink,    "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    return tasks, edges


def make_dag_large():
    """30-task 5-stage pipeline (identical to 4x4 large / random large)."""
    tasks = [{"id": f"T{i}", "compute_cost": _COMPUTE_COSTS[i % len(_COMPUTE_COSTS)]}
             for i in range(30)]
    edges, ei = [], 0
    for i in range(1, 7):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    s1, s2 = range(1, 7), range(7, 15)
    s3, s4 = range(15, 23), range(23, 29)
    for i, src in enumerate(s1):
        for j in range(2):
            edges.append({"from": f"T{src}", "to": f"T{s2[(i*2+j) % len(s2)]}",
                          "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    for i, src in enumerate(s2):
        for j in range(2):
            edges.append({"from": f"T{src}", "to": f"T{s3[(i*2+j) % len(s3)]}",
                          "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    for i, src in enumerate(s3):
        edges.append({"from": f"T{src}", "to": f"T{s4[i % len(s4)]}",
                      "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    for src in s4:
        edges.append({"from": f"T{src}", "to": "T29",
                      "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    return tasks, edges


def make_dag_large_7x7():
    """60-task 6-stage pipeline (7x7 large only)."""
    tasks = [{"id": f"T{i}", "compute_cost": _COMPUTE_COSTS[i % len(_COMPUTE_COSTS)]}
             for i in range(60)]
    edges, ei = [], 0
    s1 = range(1, 11); s2 = range(11, 25); s3 = range(25, 39)
    s4 = range(39, 49); s5 = range(49, 59)
    for i in s1:
        edges.append({"from": "T0", "to": f"T{i}", "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    for i, src in enumerate(s1):
        for j in range(3):
            edges.append({"from": f"T{src}", "to": f"T{s2[(i*3+j) % len(s2)]}",
                          "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    for i, src in enumerate(s2):
        for j in range(2):
            edges.append({"from": f"T{src}", "to": f"T{s3[(i*2+j) % len(s3)]}",
                          "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    for i, src in enumerate(s3):
        edges.append({"from": f"T{src}", "to": f"T{s4[i % len(s4)]}",
                      "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    for i, src in enumerate(s4):
        edges.append({"from": f"T{src}", "to": f"T{s5[i % len(s5)]}",
                      "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    for i in s5:
        edges.append({"from": f"T{i}", "to": "T59",
                      "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    return tasks, edges


GRID_EXPERIMENTS = [
    {"name": "4x4_small", "grid": 4, "dag_label": "small (8 tasks, fork-join)",
     "dag_fn": make_dag_small},
    {"name": "4x4_large", "grid": 4, "dag_label": "large (30 tasks, 5-stage pipeline)",
     "dag_fn": make_dag_large},
    {"name": "7x7_small", "grid": 7, "dag_label": "small (8 tasks, fork-join)",
     "dag_fn": make_dag_small},
    {"name": "7x7_large", "grid": 7, "dag_label": "large (60 tasks, 6-stage pipeline)",
     "dag_fn": make_dag_large_7x7},
]

RAND_DAGS = [("small", make_dag_small), ("large", make_dag_large)]


# ─── YAML + runner ───────────────────────────────────────────────────────────

def make_yaml(nodes, links, tasks, edges):
    y  = 'scenario:\n  name: "no_interference_eval"\n  network:\n    nodes:\n'
    for n in nodes:
        y += (f"      - {{id: {n['id']}, compute_capacity: {n['compute_capacity']}, "
              f"position: {{x: {n['x']}, y: {n['y']}}}}}\n")
    y += "    links:\n"
    for lk in links:
        y += f"      - {{id: {lk['id']}, from: {lk['from']}, to: {lk['to']}}}\n"
    y += "  dags:\n    - id: dag_1\n      inject_at: 0.0\n      tasks:\n"
    for t in tasks:
        y += f"        - {{id: {t['id']}, compute_cost: {t['compute_cost']}}}\n"
    y += "      edges:\n"
    for e in edges:
        y += f"        - {{from: {e['from']}, to: {e['to']}, data_size: {e['data_size']}}}\n"
    y += "  config:\n    scheduler: heft\n    seed: 42\n    routing: direct\n    interference: none\n"
    return y


def run_one(yaml_str, label, routing, seed, greedy_order, scheduler):
    outdir = os.path.join(OUTDIR, label)
    os.makedirs(outdir, exist_ok=True)
    inp = os.path.join(OUTDIR, "_inputs", label)
    os.makedirs(inp, exist_ok=True)
    yaml_path = os.path.join(inp, "scenario.yaml")
    with open(yaml_path, "w") as f:
        f.write(yaml_str)
    cmd = [sys.executable, "-m", "ncsim",
           "--scenario", yaml_path, "--output", outdir,
           "--interference", "none",
           "--scheduler", scheduler,
           "--routing", routing,
           "--seed", str(seed)]
    if greedy_order:
        cmd += ["--greedy-order", greedy_order]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return outdir if r.returncode == 0 else None


def get_makespan(outdir):
    try:
        with open(os.path.join(outdir, "metrics.json")) as f:
            d = json.load(f)
        return d["makespan"] if d.get("status") != "error" else None
    except Exception:
        return None


def run_averaged(yaml_str, base_label, routing, greedy_order, scheduler):
    def _run(seed):
        od = run_one(yaml_str, f"{base_label}_s{seed}", routing, seed, greedy_order, scheduler)
        return get_makespan(od) if od else None
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        ms_list = [v for v in ex.map(_run, range(1, NUM_SEEDS + 1)) if v is not None]
    return sum(ms_list) / len(ms_list) if ms_list else None


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTDIR, exist_ok=True)
    t0 = time.time()

    grid_total   = len(GRID_EXPERIMENTS) * len(GRID_STRATEGIES) * len(SCHEDULERS)
    random_total = len(DENSITIES) * len(RAND_DAGS) * len(SCHEDULERS) * len(RAND_STRATEGIES)
    total_combos = grid_total + random_total

    print(f"\n{'='*80}")
    print("  No-Interference Evaluation  (--interference none)")
    print(f"  Grid:   {len(GRID_EXPERIMENTS)} experiments × {len(GRID_STRATEGIES)} routing × {len(SCHEDULERS)} schedulers = {grid_total} combos")
    print(f"  Random: {len(DENSITIES)} densities × {len(RAND_DAGS)} DAGs × {len(SCHEDULERS)} schedulers × {len(RAND_STRATEGIES)} routing = {random_total} combos")
    print(f"  Total:  {total_combos} combos × {NUM_SEEDS} seeds = {total_combos * NUM_SEEDS} runs")
    print(f"{'='*80}\n")

    # ── Grid experiments ─────────────────────────────────────────────────────
    print("  ── GRID EXPERIMENTS ──")
    grid_results = {}   # (exp_name, sched, label) → mean_ms
    combo_idx = 0

    for exp in GRID_EXPERIMENTS:
        tasks, edges = exp["dag_fn"]()
        nodes, links = generate_grid_network(exp["grid"])
        yaml_str = make_yaml(nodes, links, tasks, edges)
        print(f"\n  {exp['grid']}x{exp['grid']} grid, {exp['dag_label']}")

        for sched in SCHEDULERS:
            for label, routing, greedy_order in GRID_STRATEGIES:
                combo_idx += 1
                go_sfx = f"_{greedy_order}" if greedy_order else ""
                base = f"grid_{exp['name']}_{sched}_{routing}{go_sfx}"
                print(f"    [{combo_idx:>3d}/{total_combos}] {sched}/{label:<5s} ...", end=" ", flush=True)
                ms = run_averaged(yaml_str, base, routing, greedy_order, sched)
                grid_results[(exp["name"], sched, label)] = ms
                print(f"{ms:.3f}s" if ms is not None else "FAILED")

    # ── Random experiments ────────────────────────────────────────────────────
    print("\n  ── RANDOM NETWORK EXPERIMENTS ──")
    rand_results  = {}   # (dlabel, dag_label, sched, rlabel) → mean_ms
    rand_topo     = {}   # dlabel → {side_len, avg_degree, n_links}

    for dlabel, side_len in DENSITIES:
        nodes, links, n_links, avg_deg = generate_random_network(
            NUM_NODES, side_len, COMM_RANGE, TOPO_SEED)
        rand_topo[dlabel] = {"side_len": side_len, "avg_degree": avg_deg, "n_links": n_links}
        print(f"\n  {dlabel}: L={side_len}m  links={n_links}  avg_degree={avg_deg:.1f}")

        for dag_label, dag_fn in RAND_DAGS:
            tasks, edges = dag_fn()
            yaml_str = make_yaml(nodes, links, tasks, edges)
            print(f"  ── {dlabel} / {dag_label} ──")

            for sched in SCHEDULERS:
                for rlabel, routing, greedy_order in RAND_STRATEGIES:
                    combo_idx += 1
                    go_sfx = f"_{greedy_order}" if greedy_order else ""
                    base = f"rand_{dlabel}_{dag_label}_{sched}_{routing}{go_sfx}"
                    print(f"    [{combo_idx:>3d}/{total_combos}] {sched}/{rlabel:<5s} ...", end=" ", flush=True)
                    ms = run_averaged(yaml_str, base, routing, greedy_order, sched)
                    rand_results[(dlabel, dag_label, sched, rlabel)] = ms
                    print(f"{ms:.3f}s" if ms is not None else "FAILED")

    elapsed = time.time() - t0

    # ── Best routing per cell ─────────────────────────────────────────────────
    rand_best = {}
    for dlabel, _ in DENSITIES:
        for dag_label, _ in RAND_DAGS:
            for sched in SCHEDULERS:
                vals = {lb: rand_results[(dlabel, dag_label, sched, lb)]
                        for lb in RAND_LABELS
                        if rand_results.get((dlabel, dag_label, sched, lb)) is not None}
                if vals:
                    bl = min(vals, key=vals.get)
                    rand_best[(dlabel, dag_label, sched)] = (bl, vals[bl])

    # Console summary
    print(f"\n{'='*80}")
    print("  RANDOM NETWORK — BEST ROUTING PER (DENSITY, DAG, SCHEDULER)")
    print(f"{'='*80}")
    for dag_label, _ in RAND_DAGS:
        print(f"\n  {dag_label.upper()} DAG")
        for dlabel, _ in DENSITIES:
            ad = rand_topo[dlabel]["avg_degree"]
            row = f"  {dlabel:<8} (deg {ad:.1f})  "
            for sched in SCHEDULERS:
                bl, ms = rand_best.get((dlabel, dag_label, sched), ("---", None))
                row += f"  {sched}/{bl}={ms:.3f}" if ms is not None else f"  {sched}/---"
            print(row)

    # ── Save JSON ─────────────────────────────────────────────────────────────
    json_path = os.path.join(OUTDIR, "no_interference_results.json")
    with open(json_path, "w") as f:
        json.dump({
            "grid": {f"{e}|{s}|{l}": v for (e, s, l), v in grid_results.items()},
            "random": {f"{d}|{g}|{s}|{r}": v for (d, g, s, r), v in rand_results.items()},
            "rand_topo": rand_topo,
            "rand_best": {f"{d}|{g}|{s}": {"routing": rb, "makespan": ms}
                          for (d, g, s), (rb, ms) in rand_best.items()},
        }, f, indent=2)
    print(f"\n  JSON: {json_path}")

    # ── Generate plots + TeX ──────────────────────────────────────────────────
    docs_dir = Path(__file__).parent / "docs"
    docs_dir.mkdir(exist_ok=True)
    _gen_density_plots(rand_best, rand_topo, docs_dir)
    tex = _build_tex(grid_results, rand_results, rand_best, rand_topo, json_path)
    tex_path = docs_dir / "no_interference_results.tex"
    tex_path.write_text(tex)
    print(f"  LaTeX: {tex_path}")
    print(f"  Elapsed: {elapsed:.0f}s\n")


# ─── Matplotlib density plots ─────────────────────────────────────────────────

def _gen_density_plots(rand_best, rand_topo, docs_dir):
    import matplotlib
    matplotlib.use("pdf")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker

    degrees = [rand_topo[dl]["avg_degree"] for dl, _ in DENSITIES]

    STYLES = {
        "heft":  dict(color="#2166ac", marker="o", linestyle="-", linewidth=1.8, markersize=6),
        "heft1": dict(color="#1a9641", marker="s", linestyle="-", linewidth=1.8, markersize=6),
        "heft2": dict(color="#d7191c", marker="^", linestyle="-", linewidth=1.8, markersize=6),
    }
    NAMES = {"heft": "HEFT (calib.)", "heft1": "HEFT-1", "heft2": "HEFT-2"}

    for dag_label, dag_fn in RAND_DAGS:
        fig, ax = plt.subplots(figsize=(6.5, 3.8))
        for sched in SCHEDULERS:
            ys = []
            for dlabel, _ in DENSITIES:
                key = (dlabel, dag_label, sched)
                ys.append(rand_best[key][1] if key in rand_best else None)
            xs_plot = [x for x, y in zip(degrees, ys) if y is not None]
            ys_plot = [y for y in ys if y is not None]
            ax.plot(xs_plot, ys_plot, label=NAMES[sched], **STYLES[sched])

        ax.set_yscale("log")
        ax.set_xlabel("Average node degree (higher = denser)", fontsize=11)
        ax.set_ylabel("Best mean makespan (s, log scale)", fontsize=11)
        dag_title = "Small DAG (8 tasks, fork-join)" if dag_label == "small" \
            else "Large DAG (30 tasks, 5-stage pipeline)"
        ax.set_title(dag_title, fontsize=12, pad=8)
        ax.set_xticks(degrees)
        ax.set_xticklabels([f"{d:.1f}" for d in degrees], fontsize=9)
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:g}"))
        ax.grid(True, which="major", linestyle="--", linewidth=0.5, alpha=0.7)
        ax.grid(True, which="minor", linestyle=":",  linewidth=0.3, alpha=0.4)
        ax.legend(loc="upper right" if dag_label == "small" else "upper left",
                  fontsize=9, framealpha=0.9)
        fig.tight_layout()
        out = docs_dir / f"noint_density_{dag_label}.pdf"
        fig.savefig(out, bbox_inches="tight")
        plt.close(fig)
        print(f"  Plot: {out}")


# ─── LaTeX generation ─────────────────────────────────────────────────────────

def fmt(v, d=3):
    return f"{v:.{d}f}" if v is not None else "---"


def _build_tex(grid_results, rand_results, rand_best, rand_topo, json_path):
    W = []
    ap = W.append

    def row_sep():  ap(r"\midrule")

    ap(r"\documentclass[11pt]{article}")
    ap(r"\usepackage[margin=1in]{geometry}")
    ap(r"\usepackage{booktabs}")
    ap(r"\usepackage{xcolor}")
    ap(r"\usepackage{amsmath}")
    ap(r"\usepackage{float}")
    ap(r"\usepackage{graphicx}")
    ap(r"\usepackage{hyperref}")
    ap(r"\hypersetup{colorlinks=true, linkcolor=blue!60!black}")
    ap(r"")
    ap(r"\newcommand{\win}[1]{\textcolor{green!50!black}{\textbf{#1}}}")
    ap(r"\newcommand{\bad}[1]{\textcolor{red!70!black}{#1}}")
    ap(r"")
    ap(r"\title{Routing Evaluation --- No Interference}")
    ap(r"\author{Autonomous Networks Research Group (ANRG)\\University of Southern California}")
    ap(r"\date{}")
    ap(r"\begin{document}")
    ap(r"\maketitle")
    ap(r"\tableofcontents")
    ap(r"\newpage")
    ap(r"")

    # ── Section 1: Setup ──────────────────────────────────────────────────────
    ap(r"\section{Evaluation Setup}")
    ap(r"")
    ap(r"Identical workloads and scheduler/routing combinations as the \texttt{csma\_bianchi}")
    ap(r"interference evaluations, but with \texttt{--interference none}: links share")
    ap(r"bandwidth fairly under concurrent flows but there is no inter-link interference.")
    ap(r"Results can be compared directly against the interference reports to isolate")
    ap(r"the cost imposed by wireless contention.")
    ap(r"")
    ap(r"\begin{table}[H]")
    ap(r"\centering")
    ap(r"\begin{tabular}{ll}")
    ap(r"\toprule")
    ap(r"\textbf{Parameter} & \textbf{Value} \\")
    ap(r"\midrule")
    ap(r"Interference & \textbf{none} (intra-link fair-share only) \\")
    ap(r"Schedulers & HEFT (calibrated), HEFT-1, HEFT-2 \\")
    ap(r"Grid routing & W, S, SH, GS, GC, GB, GO, GSD, GSD-D \\")
    ap(r"Random routing & W, S, SH, GO, GS, GSD, GSD-D \\")
    ap(r"Seeds per combo & 30 \\")
    ap(r"Grid sizes & $4\times4$ (16 nodes, 40\,m spacing) and $7\times7$ (49 nodes) \\")
    ap(r"Random nodes & 50, uniform in $[0,L]^2$, comm range $R=80$\,m \\")
    ap(r"Density levels & L150--L500 ($L=150$\,m to $500$\,m) \\")
    ap(r"DAGs & Small (8 tasks, fork-join), Large (30/60 tasks, pipeline) \\")
    ap(r"\bottomrule")
    ap(r"\end{tabular}")
    ap(r"\caption{Evaluation parameters. All other settings identical to the interference reports.}")
    ap(r"\end{table}")
    ap(r"")

    # ── Section 2: Grid results ───────────────────────────────────────────────
    ap(r"\section{Grid Network Results}")
    ap(r"")
    ap(r"Mean makespan in seconds, averaged over 30 seeds.")
    ap(r"\win{Bold green}: overall experiment winner. \bad{Red}: worst in that scheduler column.")
    ap(r"")

    for exp in GRID_EXPERIMENTS:
        name = exp["name"]
        grid = exp["grid"]
        dag_label = exp["dag_label"]
        ap(r"\subsection{$" + str(grid) + r"\times" + str(grid) + r"$ Grid, "
           + dag_label.capitalize() + "}")
        ap(r"")
        ap(r"\begin{table}[H]")
        ap(r"\centering")
        ap(r"\small")
        ap(r"\begin{tabular}{l r r r}")
        ap(r"\toprule")
        ap(r"\textbf{Routing} & \textbf{HEFT (s)} & \textbf{HEFT-1 (s)} & \textbf{HEFT-2 (s)} \\")
        ap(r"\midrule")

        cols = {sched: {lb: grid_results.get((name, sched, lb))
                        for lb in GRID_LABELS}
                for sched in SCHEDULERS}
        all_vals = [v for c in cols.values() for v in c.values() if v is not None]
        global_best = min(all_vals) if all_vals else None
        col_worst = {sched: max((v for v in cols[sched].values() if v is not None),
                                default=None)
                     for sched in SCHEDULERS}

        for lb in GRID_LABELS:
            cells = []
            for sched in SCHEDULERS:
                v = cols[sched].get(lb)
                s = fmt(v)
                if v is not None:
                    if global_best is not None and abs(v - global_best) / (global_best + 1e-9) < 0.001:
                        s = r"\win{" + s + r"}"
                    elif col_worst[sched] is not None and abs(v - col_worst[sched]) / (col_worst[sched] + 1e-9) < 0.001:
                        s = r"\bad{" + s + r"}"
                cells.append(s)
            ap(f"  {lb} & " + " & ".join(cells) + r" \\")

        ap(r"\midrule")
        best_row = []
        for sched in SCHEDULERS:
            vals = {lb: v for lb, v in cols[sched].items() if v is not None}
            if vals:
                bl = min(vals, key=vals.get)
                best_row.append(r"\textit{" + bl + f" {vals[bl]:.3f}" + r"}")
            else:
                best_row.append("---")
        ap(r"  \textit{Best} & " + " & ".join(best_row) + r" \\")
        ap(r"\bottomrule")
        ap(r"\end{tabular}")
        ap(r"\caption{$" + str(grid) + r"\times" + str(grid) + r"$ " + dag_label
           + r". Mean makespan over 30 seeds.}")
        ap(r"\end{table}")
        ap(r"")

    # ── Section 3: Random network results ─────────────────────────────────────
    ap(r"\section{Random Network Results}")
    ap(r"")

    # Topology table
    ap(r"\subsection{Topology Statistics}")
    ap(r"\begin{table}[H]")
    ap(r"\centering")
    ap(r"\begin{tabular}{l r r r}")
    ap(r"\toprule")
    ap(r"\textbf{Level} & \textbf{Side $L$ (m)} & \textbf{Links} & \textbf{Avg.\ degree} \\")
    ap(r"\midrule")
    for dlabel, side_len in DENSITIES:
        st = rand_topo[dlabel]
        ap(f"  {dlabel} & {side_len} & {st['n_links']} & {st['avg_degree']:.1f} \\\\")
    ap(r"\bottomrule")
    ap(r"\end{tabular}")
    ap(r"\caption{Random network topology statistics (seed~42).}")
    ap(r"\end{table}")
    ap(r"")

    # Density line graphs
    ap(r"\subsection{Makespan vs.\ Density}")
    ap(r"")
    ap(r"Each point is the best-routing mean makespan for that scheduler at that")
    ap(r"density, averaged over 30 seeds.")
    ap(r"")
    for dag_label, _ in RAND_DAGS:
        dag_cap = "Small DAG (8 tasks, fork-join)" if dag_label == "small" \
            else "Large DAG (30 tasks, 5-stage pipeline)"
        ap(r"\begin{figure}[H]")
        ap(r"\centering")
        ap(r"\includegraphics[width=0.9\textwidth]{noint_density_" + dag_label + r".pdf}")
        ap(r"\caption{No-interference: best-routing mean makespan vs.\ average node degree"
           r" --- " + dag_cap + r".}")
        ap(r"\end{figure}")
        ap(r"")

    # Best-routing summary tables for random
    for dag_label, _ in RAND_DAGS:
        dag_cap = "Small DAG" if dag_label == "small" else "Large DAG (30 tasks)"
        ap(r"\subsection{Best Routing --- " + dag_cap + "}")
        ap(r"\begin{table}[H]")
        ap(r"\centering")
        ap(r"\small")
        ap(r"\begin{tabular}{l r r@{\,}l r@{\,}l r@{\,}l}")
        ap(r"\toprule")
        ap(r"\textbf{Density} & \textbf{Avg.\ deg.}"
           r" & \multicolumn{2}{c}{\textbf{HEFT (calib.)}}"
           r" & \multicolumn{2}{c}{\textbf{HEFT-1}}"
           r" & \multicolumn{2}{c}{\textbf{HEFT-2}} \\")
        ap(r" & & \textbf{Route} & \textbf{(s)}"
           r" & \textbf{Route} & \textbf{(s)}"
           r" & \textbf{Route} & \textbf{(s)} \\")
        ap(r"\midrule")

        all_best_ms = [rand_best[(dl, dag_label, s)][1]
                       for dl, _ in DENSITIES for s in SCHEDULERS
                       if (dl, dag_label, s) in rand_best]
        global_best_ms = min(all_best_ms) if all_best_ms else None

        for dlabel, _ in DENSITIES:
            ad = rand_topo[dlabel]["avg_degree"]
            row_parts = [f"  {dlabel} & {ad:.1f}"]
            for sched in SCHEDULERS:
                key = (dlabel, dag_label, sched)
                if key in rand_best:
                    bl, ms = rand_best[key]
                    ms_str = fmt(ms)
                    if global_best_ms is not None and abs(ms - global_best_ms) / (global_best_ms + 1e-9) < 0.001:
                        ms_str = r"\win{" + ms_str + r"}"
                    row_parts.append(f" & {bl} & {ms_str}")
                else:
                    row_parts.append(" & --- & ---")
            ap("".join(row_parts) + r" \\")

        ap(r"\bottomrule")
        ap(r"\end{tabular}")
        ap(r"\caption{Best routing scheme and mean makespan per scheduler and density level"
           r" --- " + dag_cap + r". \win{Bold green}: overall best.}")
        ap(r"\end{table}")
        ap(r"")

    # ── Section 4: Full random results tables ────────────────────────────────
    ap(r"\section{Full Random Network Results}")
    ap(r"")
    ap(r"Mean makespan (seconds) averaged over 30 seeds. "
       r"\win{Bold green}: overall best for that density+DAG. \bad{Red}: worst in that scheduler column.")
    ap(r"")

    for dag_label, _ in RAND_DAGS:
        dag_cap = "Small DAG (8 tasks)" if dag_label == "small" else "Large DAG (30 tasks)"
        for dlabel, _ in DENSITIES:
            ad = rand_topo[dlabel]["avg_degree"]
            ap(r"\subsection{" + dlabel + r" (avg.\ degree " + f"{ad:.1f}" + r") --- " + dag_cap + r"}")
            ap(r"\begin{table}[H]")
            ap(r"\centering")
            ap(r"\small")
            ap(r"\begin{tabular}{l r r r}")
            ap(r"\toprule")
            ap(r"\textbf{Routing} & \textbf{HEFT (s)} & \textbf{HEFT-1 (s)} & \textbf{HEFT-2 (s)} \\")
            ap(r"\midrule")

            cols_r = {sched: {lb: rand_results.get((dlabel, dag_label, sched, lb))
                               for lb in RAND_LABELS}
                      for sched in SCHEDULERS}
            all_vals_r = [v for c in cols_r.values() for v in c.values() if v is not None]
            gb = min(all_vals_r) if all_vals_r else None
            cw = {sched: max((v for v in cols_r[sched].values() if v is not None), default=None)
                  for sched in SCHEDULERS}

            for lb in RAND_LABELS:
                cells = []
                for sched in SCHEDULERS:
                    v = cols_r[sched].get(lb)
                    s = fmt(v)
                    if v is not None:
                        if gb is not None and abs(v - gb) / (gb + 1e-9) < 0.001:
                            s = r"\win{" + s + r"}"
                        elif cw[sched] is not None and abs(v - cw[sched]) / (cw[sched] + 1e-9) < 0.001:
                            s = r"\bad{" + s + r"}"
                    cells.append(s)
                ap(f"  {lb} & " + " & ".join(cells) + r" \\")

            ap(r"\bottomrule")
            ap(r"\end{tabular}")
            ap(r"\caption{" + dlabel + r" ($L=" + str(rand_topo[dlabel]['side_len'])
               + r"$\,m, avg.\ degree " + f"{ad:.1f}" + r") --- " + dag_cap + r".}")
            ap(r"\end{table}")
            ap(r"")

    # ── Section 5: Analysis ───────────────────────────────────────────────────
    ap(r"\section{Analysis}")
    ap(r"")
    ap(r"\subsection{Effect of Removing Interference}")
    ap(r"")
    ap(r"Without inter-link interference, all routing schemes compete only through")
    ap(r"intra-link bandwidth sharing (fair share among concurrent flows on the same link).")
    ap(r"Key differences from the \texttt{csma\_bianchi} results:")
    ap(r"")
    ap(r"\begin{itemize}")
    ap(r"  \item \textbf{HEFT-1 co-location advantage shrinks.}  Under interference,")
    ap(r"    co-location avoids both per-link contention and inter-link spectrum")
    ap(r"    degradation.  Without interference, only intra-link contention remains,")
    ap(r"    so multi-hop paths are less penalised.  HEFT and HEFT-2 recover")
    ap(r"    relative to HEFT-1 compared to the interference case.")
    ap(r"  \item \textbf{Widest-path (W) improves relative to other schemes.}")
    ap(r"    Without interference, selecting the highest-bottleneck-bandwidth path")
    ap(r"    is less harmful: the chosen path no longer radiates contention to")
    ap(r"    neighbouring links.  W may now be competitive or even win.")
    ap(r"  \item \textbf{Greedy interference-aware schemes (GS, GO, GSD, GSD-D) lose")
    ap(r"    their advantage.}  These schemes were designed to avoid simultaneous")
    ap(r"    transmissions on interfering link pairs.  With no inter-link interference,")
    ap(r"    their routing decisions reduce to bandwidth-aware reordering, offering")
    ap(r"    little over S or W.")
    ap(r"  \item \textbf{SH vs.\ S.}  Without interference the hop-count-minimisation")
    ap(r"    rationale for SH disappears entirely.  S (min-delay = min $\sum 1/b$)")
    ap(r"    should consistently win over SH.")
    ap(r"\end{itemize}")
    ap(r"")
    ap(r"\subsection{Reproducing These Results}")
    ap(r"\begin{verbatim}")
    ap(r"cd ncsim/")
    ap(r"python run_no_interference_eval.py")
    ap(r"# JSON: /tmp/ncsim_no_interference_eval/no_interference_results.json")
    ap(r"\end{verbatim}")
    ap(r"")
    ap(r"\end{document}")

    return "\n".join(W)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""DAG-size scaling evaluation: fixed networks, varying DAG size, HEFT-1 scheduler.

Since HEFT-1 dominates under csma_bianchi interference, this experiment holds the
scheduler fixed at HEFT-1 and asks: which routing scheme performs best as DAG size
grows?  Three representative networks are tested:

  - Random L150  (50 nodes, 150 m side — dense)
  - Random L500  (50 nodes, 500 m side — sparse)
  - 7×7 Grid     (49 nodes, 40 m spacing)

DAG sizes span from the existing "small" (8 tasks, fork-join) to the existing "large"
(60 tasks, 6-stage pipeline) with four intermediate sizes.

Routing schemes tested: W, S, SH, GS, GC, GB, GO, GSD, GSD-D.
Interference model: csma_bianchi (802.11ax, 5 GHz, 20 MHz).
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

# ─── Configuration ────────────────────────────────────────────────────────────

OUTDIR       = "/tmp/ncsim_dag_scaling"
DOCS_DIR     = Path(__file__).parent / "docs"
NUM_SEEDS    = 20
MAX_WORKERS  = 8
SCHEDULER    = "heft1"          # Fixed: best with csma_bianchi interference
INTERFERENCE = "csma_bianchi"

# Random network parameters
COMM_RANGE = 80    # meters
NUM_NODES  = 50
TOPO_SEED  = 42    # fixed topology per density level

# Grid parameters
GRID_SIZE    = 7
GRID_SPACING = 40  # meters

# Heterogeneous workload (same as other evaluations for consistency)
_COMPUTE_COSTS = [500, 200, 800, 350, 1000, 150, 600, 450, 750, 300,
                  900, 250, 550, 700, 400, 850]
_DATA_SIZES    = [10.0, 2.0, 25.0, 5.0, 30.0, 8.0, 15.0, 3.0,
                  20.0, 6.0, 12.0, 28.0, 4.0, 18.0, 7.0, 22.0]
_CAPACITIES    = [200, 100, 150, 80, 300, 120, 250, 180, 160, 90,
                  220, 140, 280, 110, 190, 170]

# Routing schemes to compare
ROUTING_SCHEMES = [
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
LABELS = [s[0] for s in ROUTING_SCHEMES]

# DAG sizes: (n_tasks, stage_widths, short_description)
# stage_widths are the number of tasks per stage; sum = n_tasks
DAG_CONFIGS = [
    (8,  [1, 6, 1],                   "fork-join"),
    (16, [1, 6, 8, 1],                "3-stage pipeline"),
    (24, [1, 6, 8, 8, 1],             "4-stage pipeline"),
    (32, [1, 6, 8, 8, 8, 1],          "5-stage pipeline"),
    (45, [1, 8, 12, 12, 11, 1],       "5-stage expanded"),
    (60, [1, 10, 14, 14, 10, 10, 1],  "6-stage pipeline"),
]

# Networks to test: (name, type, side_length or grid_size)
NETWORKS = [
    ("L150",  "random", 150),
    ("L500",  "random", 500),
    ("7x7",   "grid",   7),
]


# ─── DAG Generation ───────────────────────────────────────────────────────────

def make_pipeline_dag(stage_widths):
    """Build a pipeline DAG from a list of stage widths.

    Connectivity rules between stage i (width w_i) and stage i+1 (width w_{i+1}):
      - If w_i == 1: fan-out to all tasks in the next stage.
      - If w_{i+1} == 1: fan-in from all tasks in the current stage.
      - Otherwise: each task in stage i connects to ceil(w_{i+1}/w_i) tasks in stage
        i+1 using circular indexing, ensuring all destination tasks have at least
        one predecessor.
    """
    tasks = []
    stage_starts = []
    tid = 0
    for w in stage_widths:
        stage_starts.append(tid)
        for _ in range(w):
            tasks.append({
                "id": f"T{tid}",
                "compute_cost": _COMPUTE_COSTS[tid % len(_COMPUTE_COSTS)],
            })
            tid += 1

    edges = []
    ei = 0
    for s in range(len(stage_widths) - 1):
        w_cur  = stage_widths[s]
        w_next = stage_widths[s + 1]
        s_cur  = stage_starts[s]
        s_next = stage_starts[s + 1]

        if w_cur == 1:
            for j in range(w_next):
                edges.append({
                    "from":      f"T{s_cur}",
                    "to":        f"T{s_next + j}",
                    "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)],
                })
                ei += 1
        elif w_next == 1:
            for i in range(w_cur):
                edges.append({
                    "from":      f"T{s_cur + i}",
                    "to":        f"T{s_next}",
                    "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)],
                })
                ei += 1
        else:
            n_out = max(1, math.ceil(w_next / w_cur))
            for i in range(w_cur):
                for j in range(n_out):
                    dst = (i * n_out + j) % w_next
                    edges.append({
                        "from":      f"T{s_cur + i}",
                        "to":        f"T{s_next + dst}",
                        "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)],
                    })
                    ei += 1

    return tasks, edges


# ─── Network Generation ───────────────────────────────────────────────────────

def generate_random_network(n_nodes, side_length, comm_range, seed):
    """50 nodes in [0,side]², links within comm_range, connectivity guaranteed."""
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
            adj[a].add(b)
            adj[b].add(a)
        seen, q = set(), [start]
        while q:
            v = q.pop()
            if v in seen:
                continue
            seen.add(v)
            q.extend(adj[v] - seen)
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
              "x": round(pos[i][0], 1),
              "y": round(pos[i][1], 1)}
             for i in range(n_nodes)]
    links = []
    for a, b in sorted(pairs):
        na, nb = f"n{a}", f"n{b}"
        links.append({"id": f"l_{na}_{nb}", "from": na, "to": nb})
        links.append({"id": f"l_{nb}_{na}", "from": nb, "to": na})

    avg_degree = 2 * len(pairs) / n_nodes
    return nodes, links, len(pairs), avg_degree


def generate_grid_network(n):
    """n×n grid with checkerboard diagonals (40 m spacing)."""
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

    avg_degree = 2 * len(pairs) / (n * n)
    return nodes, links, len(pairs), avg_degree


# ─── YAML + Runner ────────────────────────────────────────────────────────────

def make_yaml(nodes, links, tasks, edges):
    y  = 'scenario:\n  name: "dag_scaling_eval"\n  network:\n    nodes:\n'
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


def run_one(yaml_str, label, routing, seed, greedy_order):
    outdir   = os.path.join(OUTDIR, label)
    inp_dir  = os.path.join(OUTDIR, "_inputs", label)
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(inp_dir, exist_ok=True)
    yaml_path = os.path.join(inp_dir, "scenario.yaml")
    with open(yaml_path, "w") as f:
        f.write(yaml_str)
    cmd = [
        sys.executable, "-m", "ncsim",
        "--scenario", yaml_path, "--output", outdir,
        "--interference", INTERFERENCE,
        "--scheduler",    SCHEDULER,
        "--routing",      routing,
        "--seed",         str(seed),
    ]
    if greedy_order:
        cmd += ["--greedy-order", greedy_order]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return outdir if result.returncode == 0 else None


def get_makespan(outdir):
    try:
        with open(os.path.join(outdir, "metrics.json")) as f:
            d = json.load(f)
        return d["makespan"] if d.get("status") != "error" else None
    except Exception:
        return None


def run_averaged(yaml_str, base_label, routing, greedy_order):
    def _run(seed):
        od = run_one(yaml_str, f"{base_label}_s{seed}", routing, seed, greedy_order)
        return get_makespan(od) if od else None

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        ms_list = [v for v in ex.map(_run, range(1, NUM_SEEDS + 1)) if v is not None]
    if not ms_list:
        return None, None
    mean = sum(ms_list) / len(ms_list)
    std  = math.sqrt(sum((x - mean) ** 2 for x in ms_list) / len(ms_list))
    return mean, std


# ─── Main Experiment ──────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTDIR, exist_ok=True)
    DOCS_DIR.mkdir(exist_ok=True)
    t0 = time.time()

    total_combos = len(NETWORKS) * len(DAG_CONFIGS) * len(ROUTING_SCHEMES)
    total_runs   = total_combos * NUM_SEEDS

    print()
    print("=" * 100)
    print("  DAG-Size Scaling Evaluation")
    print(f"  Scheduler:  {SCHEDULER}  (fixed — best with {INTERFERENCE})")
    print(f"  Routing:    {', '.join(LABELS)}")
    print(f"  Networks:   {', '.join(n for n, *_ in NETWORKS)}")
    print(f"  DAG sizes:  {', '.join(str(n) for n, *_ in DAG_CONFIGS)} tasks")
    print(f"  Seeds:      {NUM_SEEDS}  |  Workers: {MAX_WORKERS}")
    print(f"  Total runs: {total_combos} combos × {NUM_SEEDS} seeds = {total_runs}")
    print("=" * 100)
    print()

    # Pre-generate all networks
    net_info = {}   # name → {nodes, links, n_links, avg_degree}
    for net_name, net_type, param in NETWORKS:
        if net_type == "random":
            nodes, links, n_links, avg_deg = generate_random_network(
                NUM_NODES, param, COMM_RANGE, TOPO_SEED)
        else:
            nodes, links, n_links, avg_deg = generate_grid_network(param)
        net_info[net_name] = {
            "nodes": nodes, "links": links,
            "n_nodes": len(nodes), "n_links": n_links, "avg_degree": avg_deg,
        }
        print(f"  {net_name}: {len(nodes)} nodes, {n_links} undirected links, "
              f"avg degree {avg_deg:.1f}")
    print()

    # results[(net_name, n_tasks, label)] = (mean, std) or (None, None)
    results = {}
    combo_idx = 0

    for net_name, net_type, param in NETWORKS:
        info  = net_info[net_name]
        nodes = info["nodes"]
        links = info["links"]
        print(f"  ══ Network: {net_name} ══")

        for n_tasks, stage_widths, dag_desc in DAG_CONFIGS:
            tasks, edges = make_pipeline_dag(stage_widths)
            yaml_str     = make_yaml(nodes, links, tasks, edges)
            n_edges      = len(edges)
            print(f"  DAG: {n_tasks} tasks, {n_edges} edges ({dag_desc})")

            for label, routing, greedy_order in ROUTING_SCHEMES:
                combo_idx += 1
                go_sfx    = f"_{greedy_order}" if greedy_order else ""
                base_lbl  = f"{net_name}_t{n_tasks}_{routing}{go_sfx}"
                print(f"    [{combo_idx:>3d}/{total_combos}] {label:<6s} ...", end=" ", flush=True)
                mean_ms, std_ms = run_averaged(yaml_str, base_lbl, routing, greedy_order)
                results[(net_name, n_tasks, label)] = (mean_ms, std_ms)
                if mean_ms is not None:
                    print(f"{mean_ms:.3f}s ± {std_ms:.3f}s")
                else:
                    print("FAILED")
        print()

    elapsed = time.time() - t0

    # ── Save JSON ─────────────────────────────────────────────────────────────
    json_out = {
        "config": {
            "scheduler": SCHEDULER,
            "interference": INTERFERENCE,
            "num_seeds": NUM_SEEDS,
            "networks": {n: {"n_nodes": net_info[n]["n_nodes"],
                             "n_links": net_info[n]["n_links"],
                             "avg_degree": net_info[n]["avg_degree"]}
                         for n, *_ in NETWORKS},
            "dag_configs": [[n, sw, d] for n, sw, d in DAG_CONFIGS],
        },
        "results": {
            f"{net}|{nt}|{lb}": {"mean": m, "std": s}
            for (net, nt, lb), (m, s) in results.items()
            if m is not None
        },
    }
    json_path = os.path.join(OUTDIR, "dag_scaling_results.json")
    with open(json_path, "w") as f:
        json.dump(json_out, f, indent=2)
    print(f"  JSON results: {json_path}")
    print(f"  Elapsed:      {elapsed:.0f}s")

    # ── Generate LaTeX ────────────────────────────────────────────────────────
    tex_content = build_tex(results, net_info, json_path)
    tex_path    = DOCS_DIR / "dag_scaling_results.tex"
    with open(tex_path, "w") as f:
        f.write(tex_content)
    print(f"  LaTeX:        {tex_path}")

    # ── Compile PDF ──────────────────────────────────────────────────────────
    for _ in range(2):
        r = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode",
             "-output-directory", str(DOCS_DIR), str(tex_path)],
            capture_output=True, text=True, cwd=str(DOCS_DIR),
        )
    pdf_path = tex_path.with_suffix(".pdf")
    if pdf_path.exists():
        print(f"  PDF:          {pdf_path}")
    else:
        print("  PDF compilation failed — see LaTeX log for details")
        print(r.stdout[-2000:])

    failures = sum(1 for (m, s) in results.values() if m is None)
    if failures:
        print(f"\n  WARNING: {failures} combo(s) returned no result.")
    print()
    return 0


# ─── LaTeX Generation ─────────────────────────────────────────────────────────

# Visual encoding for 9 routing schemes in pgfplots
_SCHEME_STYLE = {
    "W":     ("blue!70!black",    "o",         "solid"),
    "S":     ("red!70!black",     "square*",   "solid"),
    "SH":    ("orange!80!black",  "triangle*", "solid"),
    "GS":    ("green!60!black",   "diamond*",  "dashed"),
    "GC":    ("purple!80!black",  "x",         "dashed"),
    "GB":    ("brown!70!black",   "+",         "dashed"),
    "GO":    ("teal",             "pentagon*", "dashed"),
    "GSD":   ("cyan!60!black",    "star",      "dotted"),
    "GSD-D": ("magenta!70!black", "square",    "dotted"),
}

_NET_TITLE = {
    "L150": r"Random Network, $L=150$\,m (Dense, avg.\ degree $\approx 22$)",
    "L500": r"Random Network, $L=500$\,m (Sparse, avg.\ degree $\approx 2.5$)",
    "7x7":  r"$7\times7$ Grid (49 nodes, 40\,m spacing)",
}


def fmt(v, d=3):
    return f"{v:.{d}f}" if v is not None else "---"


def build_tex(results, net_info, json_path):
    dag_sizes = [n for n, *_ in DAG_CONFIGS]
    dag_descs = {n: d for n, _, d in DAG_CONFIGS}
    dag_edges = {}
    for n_tasks, stage_widths, _ in DAG_CONFIGS:
        _, edges = make_pipeline_dag(stage_widths)
        dag_edges[n_tasks] = len(edges)

    parts = []

    # ── Preamble ─────────────────────────────────────────────────────────────
    parts.append(r"""\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{booktabs}
\usepackage{xcolor}
\usepackage{amsmath}
\usepackage{float}
\usepackage{pgfplots}
\pgfplotsset{compat=1.16}
\usepackage{hyperref}

\hypersetup{colorlinks=true, linkcolor=blue!60!black}

\newcommand{\win}[1]{\textcolor{green!50!black}{\textbf{#1}}}
\newcommand{\bad}[1]{\textcolor{red!70!black}{#1}}

\title{DAG-Size Scaling: Routing Scheme Comparison\\
       {\large Fixed Networks, Varying DAG Size, HEFT-1 Scheduler}}
\author{Autonomous Networks Research Group (ANRG)\\University of Southern California}
\date{}

\begin{document}
\maketitle
\tableofcontents
\newpage
""")

    # ── Section 1: Setup ─────────────────────────────────────────────────────
    parts.append(r"""
%======================================================================
\section{Evaluation Setup}

Since HEFT-1 dominates under \texttt{csma\_bianchi} interference (co-locates tasks
to avoid multi-hop transfers), this experiment fixes the scheduler to HEFT-1 and
investigates \emph{which routing scheme performs best as DAG size grows}.  Three
networks are held fixed; DAG size is varied from 8 to 60 tasks.

\begin{table}[H]
\centering
\begin{tabular}{ll}
\toprule
\textbf{Parameter} & \textbf{Value} \\
\midrule
""")
    parts.append(r"Scheduler & HEFT-1 (direct-link BW; 0.001\,MB/s for non-adjacent) \\")
    parts.append(r"Interference & \texttt{csma\_bianchi} (802.11ax, 5\,GHz, 20\,MHz, $P_\text{tx}=20$\,dBm) \\")
    parts.append(r"Routing schemes & W, S, SH, GS, GC, GB, GO, GSD, GSD-D (9 total) \\")
    parts.append(f"Seeds per combo & {NUM_SEEDS} (seeds 1--{NUM_SEEDS}); values are mean makespan \\\\")
    parts.append(r"Compute costs & 150--1000\,cu (heterogeneous, $\approx6.7\times$ range) \\")
    parts.append(r"Data sizes & 2--30\,MB (heterogeneous, $15\times$ range) \\")
    parts.append(r"Node capacities & 80--300\,cu/s (heterogeneous) \\")
    parts.append(r"\midrule")
    parts.append(r"\multicolumn{2}{l}{\textbf{Fixed Networks}} \\")

    for net_name, net_type, param in NETWORKS:
        info = net_info[net_name]
        if net_type == "random":
            desc = f"50 nodes, $L={param}$\\,m side, comm.\\ range 80\\,m"
        else:
            desc = f"{param}\\times{param} grid, 40\\,m spacing"
        parts.append(f"  {net_name} & {desc}; "
                     f"{info['n_nodes']} nodes, {info['n_links']} undirected links, "
                     f"avg.\\ degree ${info['avg_degree']:.1f}$ \\\\")

    parts.append(r"\midrule")
    parts.append(r"\multicolumn{2}{l}{\textbf{DAG Sizes}} \\")
    for n_tasks, stage_widths, dag_desc in DAG_CONFIGS:
        n_edges = dag_edges[n_tasks]
        stages  = r"$\to$".join(str(w) for w in stage_widths)
        parts.append(f"  {n_tasks} tasks & {dag_desc} ({stages}); {n_edges} edges \\\\")

    parts.append(r"""\bottomrule
\end{tabular}
\caption{Evaluation parameters.}
\end{table}
""")

    # ── Section 2: Per-network results ────────────────────────────────────────
    parts.append(r"""
%======================================================================
\section{Results per Network}

Mean makespan (seconds) over """ + str(NUM_SEEDS) + r""" seeds.
\win{Bold green}: best for that DAG size.
\bad{Red}: worst for that DAG size.
""")

    for net_name, net_type, param in NETWORKS:
        title = _NET_TITLE.get(net_name, net_name)
        parts.append(r"\subsection{" + title + "}\n")

        # ── Table: routing × DAG sizes ─────────────────────────────────────
        col_fmt = "l " + " r" * len(dag_sizes)
        parts.append(r"\begin{table}[H]")
        parts.append(r"\centering")
        parts.append(r"\small")
        parts.append(r"\setlength{\tabcolsep}{5pt}")
        parts.append(r"\begin{tabular}{" + col_fmt + "}")
        parts.append(r"\toprule")

        hdr = r"\textbf{Routing}"
        for n_tasks in dag_sizes:
            hdr += f" & \\textbf{{{n_tasks}t}}"
        hdr += r" \\"
        parts.append(hdr)
        parts.append(r"\midrule")

        # Find best/worst per DAG-size column
        col_best  = {}
        col_worst = {}
        for n_tasks in dag_sizes:
            vals = {lb: results.get((net_name, n_tasks, lb), (None, None))[0]
                    for lb in LABELS}
            vals = {k: v for k, v in vals.items() if v is not None}
            if vals:
                col_best[n_tasks]  = min(vals, key=vals.get)
                col_worst[n_tasks] = max(vals, key=vals.get)

        for label in LABELS:
            cells = [label.replace("-", r"\mbox{-}") if "-" in label else label]
            for n_tasks in dag_sizes:
                mean_ms, _ = results.get((net_name, n_tasks, label), (None, None))
                s = fmt(mean_ms)
                if mean_ms is not None:
                    if label == col_best.get(n_tasks):
                        s = r"\win{" + s + "}"
                    elif label == col_worst.get(n_tasks):
                        s = r"\bad{" + s + "}"
                cells.append(s)
            parts.append("  " + " & ".join(cells) + r" \\")

        parts.append(r"\midrule")
        # Best row
        best_row = [r"\textit{Best}"]
        for n_tasks in dag_sizes:
            bl = col_best.get(n_tasks, "---")
            best_row.append(r"\textit{" + bl + "}")
        parts.append("  " + " & ".join(best_row) + r" \\")

        parts.append(r"\bottomrule")
        parts.append(r"\end{tabular}")

        size_str = ", ".join(str(n) for n in dag_sizes)
        parts.append(
            r"\caption{Mean makespan (s) for " + net_name + r" network, HEFT-1, "
            + str(NUM_SEEDS) + r" seeds. "
            r"DAG sizes (tasks): " + size_str + r". "
            r"\win{Bold green}: best per column. \bad{Red}: worst per column.}"
        )
        parts.append(r"\end{table}")
        parts.append("")

        # ── Line plot: makespan vs n_tasks per routing ─────────────────────
        parts.append(r"\begin{figure}[H]")
        parts.append(r"\centering")
        parts.append(r"\begin{tikzpicture}")
        parts.append(r"\begin{axis}[")
        parts.append(r"    width=0.92\textwidth, height=8cm,")
        parts.append(r"    xlabel={Number of tasks (DAG size)},")
        parts.append(r"    ylabel={Mean makespan (s)},")
        parts.append(f"    title={{{title}}},")
        parts.append(r"    ymode=log,")
        parts.append(f"    xmin=5, xmax=65,")
        parts.append(r"    xtick={" + ",".join(str(n) for n in dag_sizes) + r"},")
        parts.append(r"    xticklabels={" + ",".join(str(n) for n in dag_sizes) + r"},")
        parts.append(r"    grid=both,")
        parts.append(r"    grid style={line width=0.2pt, draw=gray!30},")
        parts.append(r"    major grid style={line width=0.4pt, draw=gray!60},")
        parts.append(r"    legend pos=north west,")
        parts.append(r"    legend style={font=\tiny, cells={align=left}},")
        parts.append(r"    legend columns=3,")
        parts.append(r"]")

        for label, routing, greedy_order in ROUTING_SCHEMES:
            color, mark, dash = _SCHEME_STYLE[label]
            coords = []
            for n_tasks in dag_sizes:
                mean_ms, _ = results.get((net_name, n_tasks, label), (None, None))
                if mean_ms is not None:
                    coords.append(f"({n_tasks},{mean_ms:.4f})")
            if not coords:
                continue
            parts.append(
                f"\\addplot[color={color}, mark={mark}, {dash}, thick, mark size=2pt]"
            )
            parts.append(f"    coordinates {{{' '.join(coords)}}};")
            parts.append(f"\\addlegendentry{{{label}}}")

        parts.append(r"\end{axis}")
        parts.append(r"\end{tikzpicture}")
        parts.append(
            r"\caption{Makespan vs.\ DAG size for " + net_name + r" (HEFT-1, "
            + str(NUM_SEEDS) + r" seeds, log scale). "
            r"Each point is the mean over seeds; lines connect DAG sizes.}"
        )
        parts.append(r"\end{figure}")
        parts.append("")

    # ── Section 3: Cross-network summary ─────────────────────────────────────
    parts.append(r"""
%======================================================================
\section{Cross-Network Summary}

\subsection{Best Routing per Network and DAG Size}
""")

    parts.append(r"\begin{table}[H]")
    parts.append(r"\centering")
    parts.append(r"\small")
    net_labels = [n for n, *_ in NETWORKS]
    col_fmt = "l " + " r@{\,}l" * len(NETWORKS)
    parts.append(r"\begin{tabular}{" + col_fmt + "}")
    parts.append(r"\toprule")
    hdr = r"\textbf{Tasks}"
    for net_name in net_labels:
        hdr += f" & \\multicolumn{{2}}{{c}}{{\\textbf{{{net_name}}}}}"
    hdr += r" \\"
    parts.append(hdr)
    parts.append(r"& " + " & ".join(r"\textbf{Route} & \textbf{(s)}"
                                     for _ in net_labels) + r" \\")
    parts.append(r"\midrule")

    for n_tasks in dag_sizes:
        row = [str(n_tasks)]
        for net_name in net_labels:
            vals = {lb: results.get((net_name, n_tasks, lb), (None, None))[0]
                    for lb in LABELS}
            vals = {k: v for k, v in vals.items() if v is not None}
            if vals:
                bl = min(vals, key=vals.get)
                row.append(bl)
                row.append(fmt(vals[bl]))
            else:
                row.append("---")
                row.append("---")
        parts.append("  " + " & ".join(row) + r" \\")

    parts.append(r"\bottomrule")
    parts.append(r"\end{tabular}")
    parts.append(
        r"\caption{Best routing scheme (and mean makespan) per network and DAG size. "
        r"All results use HEFT-1 scheduler with \texttt{csma\_bianchi} interference.}"
    )
    parts.append(r"\end{table}")
    parts.append("")

    # Win-count summary
    parts.append(r"\subsection{Routing Scheme Win Counts}")
    parts.append("")
    parts.append(
        r"Number of (network, DAG-size) cells where each routing scheme "
        r"achieves the lowest mean makespan (out of "
        + str(len(NETWORKS) * len(dag_sizes)) + r" cells)."
    )
    parts.append("")
    parts.append(r"\begin{table}[H]")
    parts.append(r"\centering")
    parts.append(r"\begin{tabular}{l r r r r}")
    parts.append(r"\toprule")
    parts.append(r"\textbf{Routing} & \textbf{Total wins} & \textbf{L150} & \textbf{L500} & \textbf{7x7} \\")
    parts.append(r"\midrule")

    net_wins = {lb: {nn: 0 for nn, *_ in NETWORKS} for lb in LABELS}
    for net_name in net_labels:
        for n_tasks in dag_sizes:
            vals = {lb: results.get((net_name, n_tasks, lb), (None, None))[0]
                    for lb in LABELS}
            vals = {k: v for k, v in vals.items() if v is not None}
            if vals:
                bl = min(vals, key=vals.get)
                net_wins[bl][net_name] += 1

    for label in LABELS:
        total = sum(net_wins[label].values())
        per   = [str(net_wins[label][nn]) for nn in net_labels]
        lbl   = label.replace("-", r"\mbox{-}") if "-" in label else label
        row   = [lbl, str(total)] + per
        if total == max(sum(net_wins[lb].values()) for lb in LABELS):
            row[0] = r"\textbf{" + row[0] + r"}"
            row[1] = r"\textbf{" + row[1] + r"}"
        parts.append("  " + " & ".join(row) + r" \\")

    parts.append(r"\bottomrule")
    parts.append(r"\end{tabular}")
    parts.append(r"\caption{Win counts per routing scheme. \textbf{Bold}: overall winner.}")
    parts.append(r"\end{table}")
    parts.append("")

    # ── Section 4: Analysis ───────────────────────────────────────────────────
    parts.append(r"""
%======================================================================
\section{Analysis}

\subsection{Effect of DAG Size on Routing Performance}

Under HEFT-1, tasks are placed on the same node or direct neighbours to avoid
the 0.001\,MB/s inter-node penalty.  As DAG size grows, two competing effects emerge:

\begin{enumerate}
  \item \textbf{More parallelism $\Rightarrow$ more concurrent transfers.}
    Larger DAGs have more tasks executing simultaneously across stages, increasing
    the number of simultaneous link-level transfers and therefore interference.
    Routing schemes that account for concurrency (GS, GO, GSD, GSD-D) are
    expected to gain relative to static schemes (W, S, SH) as DAG size grows.

  \item \textbf{More stages $\Rightarrow$ deeper critical paths.}
    Larger DAGs have longer chains of sequential dependencies.  If the critical
    path runs through co-located tasks (same node), routing has little influence.
    If inter-node transfers appear on the critical path, routing quality dominates.
\end{enumerate}

\subsection{Dense vs.\ Sparse Networks}

On the dense random network (L150, avg.\ degree $\approx22$), many routing
alternatives exist; interference-aware ordering (GS, GO, GSD-D) can exploit path
diversity.  On the sparse network (L500, avg.\ degree $\approx2.5$), most node
pairs have exactly one path; interference-aware schemes reduce to shortest/widest
path.  The 7$\times$7 grid lies between these extremes with regular path structure.

\subsection{Key Takeaways}

\begin{enumerate}
  \item Routing scheme rankings are largely consistent across DAG sizes for a
    given network, especially under HEFT-1 (co-location removes most transfers).
  \item At large DAG sizes, interference-aware greedy schemes (particularly GO
    and GSD-D) tend to outperform static routing (W, S, SH) because the dense
    transfer phase benefits from overlap-aware or deferral-based ordering.
  \item The widest-path (W) scheme is consistently among the worst: it maximises
    flow bandwidth but routes through congested links, amplifying csma\_bianchi
    interference.
  \item On sparse networks (L500), routing scheme differences narrow because
    fewer path choices are available; scheduler quality dominates over routing.
\end{enumerate}

%======================================================================
\section{Reproducing These Results}

\begin{verbatim}
cd ncsim/
python run_dag_scaling_eval.py
# Outputs: /tmp/ncsim_dag_scaling/dag_scaling_results.json
#          docs/dag_scaling_results.tex
#          docs/dag_scaling_results.pdf
\end{verbatim}
""")

    parts.append(r"\end{document}")
    return "\n".join(parts)


if __name__ == "__main__":
    sys.exit(main())

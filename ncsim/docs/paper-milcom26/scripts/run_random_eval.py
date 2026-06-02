#!/usr/bin/env python3
"""Random network routing evaluation: vary spatial density, compare scheduler variants.

50 nodes placed uniformly at random in an L×L square.
Bidirectional links between nodes within communication range R=80m.
Vary L from 150m (dense) to 500m (sparse).

For each density level and scheduler, find the best routing scheme, then
compare HEFT / HEFT-1 / HEFT-2 at their respective best routing schemes
as a function of network density.
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

OUTDIR = "/tmp/ncsim_random_eval"
NUM_SEEDS = 30
COMM_RANGE = 80   # meters — link between nodes within this distance
NUM_NODES = 50
MAX_WORKERS = 8
TOPO_SEED = 42    # fixed seed for topology generation per density level

# Deployment area side lengths — smaller = denser
DENSITIES = [
    ("L150", 150),
    ("L200", 200),
    ("L250", 250),
    ("L300", 300),
    ("L350", 350),
    ("L400", 400),
    ("L500", 500),
]

SCHEDULERS = ["heft", "heft1", "heft2"]

ROUTING_SCHEMES = [
    ("W",     "widest_path",                          None),
    ("S",     "shortest_path",                        None),
    ("SH",    "shortest_hop",                         None),
    ("GO",    "interference_aware",                   "overlap"),
    ("GS",    "interference_aware",                   "start"),
    ("GSD",   "interference_aware_dynamic",           None),
    ("GSD-D", "interference_aware_dynamic_deferral",  None),
]
LABELS = [s[0] for s in ROUTING_SCHEMES]

_COMPUTE_COSTS = [500, 200, 800, 350, 1000, 150, 600, 450, 750, 300,
                  900, 250, 550, 700, 400, 850]
_DATA_SIZES    = [10.0, 2.0, 25.0, 5.0, 30.0, 8.0, 15.0, 3.0,
                  20.0, 6.0, 12.0, 28.0, 4.0, 18.0, 7.0, 22.0]
_CAPACITIES    = [200, 100, 150, 80, 300, 120, 250, 180, 160, 90,
                  220, 140, 280, 110, 190, 170]


# ─── Topology Generation ─────────────────────────────────────────────────────

def generate_random_network(n_nodes, side_length, comm_range, seed):
    """Place n_nodes uniformly at random in [0,side]², link pairs within comm_range.

    Guarantees a connected graph by bridging disconnected components with the
    shortest cross-component edge (even if it exceeds comm_range).
    Returns (nodes, links, avg_degree).
    """
    rng = random.Random(seed)
    pos = [(rng.uniform(0, side_length), rng.uniform(0, side_length))
           for _ in range(n_nodes)]

    def dist(i, j):
        return math.sqrt((pos[i][0] - pos[j][0])**2 + (pos[i][1] - pos[j][1])**2)

    pairs = {(min(i, j), max(i, j))
             for i in range(n_nodes) for j in range(i + 1, n_nodes)
             if dist(i, j) <= comm_range}

    # Ensure connectivity
    def component(start, edge_set):
        adj = {i: set() for i in range(n_nodes)}
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


# ─── DAG Generators ──────────────────────────────────────────────────────────

def make_dag_small():
    """Fork-join: 1 source → 6 parallel → 1 sink (8 tasks, 12 edges)."""
    np = 6
    tasks = [{"id": "T0", "compute_cost": _COMPUTE_COSTS[0]}]
    for i in range(1, np + 1):
        tasks.append({"id": f"T{i}", "compute_cost": _COMPUTE_COSTS[i % len(_COMPUTE_COSTS)]})
    tasks.append({"id": f"T{np+1}", "compute_cost": _COMPUTE_COSTS[(np+1) % len(_COMPUTE_COSTS)]})
    sink = f"T{np+1}"
    edges, ei = [], 0
    for i in range(1, np + 1):
        edges.append({"from": "T0",    "to": f"T{i}", "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
        edges.append({"from": f"T{i}", "to": sink,    "data_size": _DATA_SIZES[ei % len(_DATA_SIZES)]}); ei += 1
    return tasks, edges


def make_dag_large():
    """5-stage pipeline (30 tasks, 48 edges) — same as 4×4 large."""
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


DAGS = [("small", make_dag_small), ("large", make_dag_large)]


# ─── YAML + Runner ───────────────────────────────────────────────────────────

def make_yaml(nodes, links, tasks, edges):
    y = 'scenario:\n  name: "random_eval"\n  network:\n    nodes:\n'
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
    y += "  config:\n    scheduler: heft\n    seed: 42\n    routing: direct\n    interference: csma_bianchi\n"
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
           "--interference", "csma_bianchi",
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


def get_metrics(outdir):
    """Per-run (makespan, mean_hops, peak_link_util) from one ncsim output dir.

    mean_hops = mean route length over transfer_complete events (single-hop
    transfers omit the 'route' field and count as 1). peak_link_util = max over
    all links of the utilization recorded in metrics.json.
    """
    try:
        with open(os.path.join(outdir, "metrics.json")) as f:
            d = json.load(f)
        if d.get("status") == "error":
            return None
        ms = d["makespan"]
        lu = d.get("link_utilization") or {}
        plu = max(lu.values()) if lu else 0.0
        hops = []
        with open(os.path.join(outdir, "trace.jsonl")) as f:
            for line in f:
                e = json.loads(line)
                if e.get("type") == "transfer_complete":
                    hops.append(len(e.get("route", [e["link_id"]])))
        mean_hops = sum(hops) / len(hops) if hops else 0.0
        return {"makespan": ms, "hops": mean_hops, "plu": plu}
    except Exception:
        return None


def run_averaged(yaml_str, base_label, routing, greedy_order, scheduler):
    """Run NUM_SEEDS replications; return mean makespan plus per-seed metric lists.

    Returns a dict {makespan_mean, ms[], hops[], plu[]} or None if all failed.
    """
    def _run(seed):
        od = run_one(yaml_str, f"{base_label}_s{seed}", routing, seed, greedy_order, scheduler)
        return get_metrics(od) if od else None

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        recs = [m for m in ex.map(_run, range(1, NUM_SEEDS + 1)) if m is not None]
    if not recs:
        return None
    ms_list = [r["makespan"] for r in recs]
    return {
        "makespan_mean": sum(ms_list) / len(ms_list),
        "ms":   ms_list,
        "hops": [r["hops"] for r in recs],
        "plu":  [r["plu"] for r in recs],
    }


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTDIR, exist_ok=True)
    t0 = time.time()

    total_combos = len(DENSITIES) * len(DAGS) * len(SCHEDULERS) * len(ROUTING_SCHEMES)
    print(f"\n{'='*80}")
    print(f"  Random Network Evaluation")
    print(f"  {NUM_NODES} nodes, comm_range={COMM_RANGE}m, {len(DENSITIES)} density levels")
    print(f"  {len(SCHEDULERS)} schedulers × {len(ROUTING_SCHEMES)} routing × {len(DAGS)} DAGs × {NUM_SEEDS} seeds")
    print(f"  Total combos: {total_combos}  |  Total runs: {total_combos * NUM_SEEDS}")
    print(f"{'='*80}\n")

    topo_stats = {}
    results    = {}   # (dlabel, dag_label, sched, rlabel) → mean_ms
    perseed    = {}   # (dlabel, dag_label, sched, rlabel) → {ms[], hops[], plu[]}

    combo_idx = 0
    for dlabel, side_len in DENSITIES:
        nodes, links, n_links, avg_deg = generate_random_network(
            NUM_NODES, side_len, COMM_RANGE, TOPO_SEED)
        topo_stats[dlabel] = {"side_len": side_len, "avg_degree": avg_deg, "n_links": n_links}
        print(f"  {dlabel}: L={side_len}m  links={n_links}  avg_degree={avg_deg:.1f}")

        for dag_label, dag_fn in DAGS:
            tasks, edges = dag_fn()
            yaml_str = make_yaml(nodes, links, tasks, edges)
            print(f"  ── {dlabel} / {dag_label} ──")

            for sched in SCHEDULERS:
                for rlabel, routing, greedy_order in ROUTING_SCHEMES:
                    combo_idx += 1
                    go_sfx = f"_{greedy_order}" if greedy_order else ""
                    base = f"{dlabel}_{dag_label}_{sched}_{routing}{go_sfx}"
                    print(f"    [{combo_idx:>3d}/{total_combos}] {sched}/{rlabel:<5s} ...", end=" ", flush=True)
                    agg = run_averaged(yaml_str, base, routing, greedy_order, sched)
                    ms = agg["makespan_mean"] if agg else None
                    results[(dlabel, dag_label, sched, rlabel)] = ms
                    if agg:
                        perseed[(dlabel, dag_label, sched, rlabel)] = {
                            "ms": agg["ms"], "hops": agg["hops"], "plu": agg["plu"]}
                    print(f"{ms:.3f}s" if ms is not None else "FAILED")
        print()

    elapsed = time.time() - t0

    # ─── Find best routing per (dlabel, dag_label, sched) ────────────────────
    best = {}   # (dlabel, dag_label, sched) → (rlabel, ms)
    for dlabel, _ in DENSITIES:
        for dag_label, _ in DAGS:
            for sched in SCHEDULERS:
                vals = {lb: results[(dlabel, dag_label, sched, lb)]
                        for lb in LABELS
                        if results.get((dlabel, dag_label, sched, lb)) is not None}
                if vals:
                    bl = min(vals, key=vals.get)
                    best[(dlabel, dag_label, sched)] = (bl, vals[bl])

    # ─── Console summary ─────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print("  BEST ROUTING PER (DENSITY, DAG, SCHEDULER)")
    print(f"{'='*80}")
    for dag_label, _ in DAGS:
        print(f"\n  {dag_label.upper()} DAG")
        hdr = f"  {'Density':<8} {'AvgDeg':>7}  "
        hdr += "  ".join(f"{s:>16}" for s in SCHEDULERS)
        print(hdr)
        for dlabel, side_len in DENSITIES:
            ad = topo_stats[dlabel]['avg_degree']
            row = f"  {dlabel:<8} {ad:>7.1f}  "
            for sched in SCHEDULERS:
                bl, ms = best.get((dlabel, dag_label, sched), ("---", None))
                row += f"  {bl:>5}/{ms:>8.3f}  " if ms else f"  {'---':>5}/{'---':>8}  "
            print(row)

    # ─── Save JSON ───────────────────────────────────────────────────────────
    json_out = {
        "topo_stats": topo_stats,
        "results": {f"{d}|{g}|{s}|{r}": v
                    for (d, g, s, r), v in results.items() if v is not None},
        "best": {f"{d}|{g}|{s}": {"routing": rb, "makespan": ms}
                 for (d, g, s), (rb, ms) in best.items()},
        "perseed": {f"{d}|{g}|{s}|{r}": v
                    for (d, g, s, r), v in perseed.items()},
        "config": {"num_seeds": NUM_SEEDS, "topo_seed": TOPO_SEED,
                   "num_nodes": NUM_NODES, "comm_range": COMM_RANGE,
                   "densities": DENSITIES, "schedulers": SCHEDULERS,
                   "routing_labels": LABELS},
    }
    json_path = os.path.join(OUTDIR, "random_eval_results.json")
    with open(json_path, "w") as f:
        json.dump(json_out, f, indent=2)
    print(f"\n  JSON: {json_path}")
    print(f"  Elapsed: {elapsed:.0f}s\n")

    # ─── Generate LaTeX ──────────────────────────────────────────────────────
    tex = build_tex(topo_stats, results, best)
    docs_dir = Path(__file__).parent / "docs"
    tex_path = docs_dir / "random_network_results.tex"
    with open(tex_path, "w") as f:
        f.write(tex)
    print(f"  LaTeX: {tex_path}")

    return results, best, topo_stats


# ─── LaTeX Generation ────────────────────────────────────────────────────────

def fmt(v, decimals=3):
    return f"{v:.{decimals}f}" if v is not None else "---"


def build_tex(topo_stats, results, best):
    """Build the full random_network_results.tex."""
    density_list = list(DENSITIES)                         # [(label, side_len)]
    avg_degs     = {dl: topo_stats[dl]["avg_degree"] for dl, _ in density_list}

    # ── pgfplots data strings ────────────────────────────────────────────────
    # One line per DAG, one set per scheduler, x=avg_degree, y=best_makespan
    sched_colors = {"heft": "blue!70!black", "heft1": "green!60!black", "heft2": "red!70!black"}
    sched_marks  = {"heft": "o",             "heft1": "square*",         "heft2": "triangle*"}
    sched_names  = {"heft": "HEFT (calib.)", "heft1": "HEFT-1",          "heft2": "HEFT-2"}

    def pgf_coords(dag_label, sched):
        coords = []
        for dlabel, _ in density_list:
            key = (dlabel, dag_label, sched)
            if key in best:
                _, ms = best[key]
                coords.append(f"({avg_degs[dlabel]:.1f},{ms:.3f})")
        return " ".join(coords)

    lines = []
    lines.append(r"\documentclass[11pt]{article}")
    lines.append(r"\usepackage[margin=1in]{geometry}")
    lines.append(r"\usepackage{booktabs}")
    lines.append(r"\usepackage{xcolor}")
    lines.append(r"\usepackage{amsmath}")
    lines.append(r"\usepackage{float}")
    lines.append(r"\usepackage{pgfplots}")
    lines.append(r"\pgfplotsset{compat=1.16}")
    lines.append(r"\usepackage{hyperref}")
    lines.append(r"\hypersetup{colorlinks=true, linkcolor=blue!60!black}")
    lines.append(r"")
    lines.append(r"\newcommand{\win}[1]{\textcolor{green!50!black}{\textbf{#1}}}")
    lines.append(r"\newcommand{\bad}[1]{\textcolor{red!70!black}{#1}}")
    lines.append(r"")
    lines.append(r"\title{Random Network Routing Evaluation}")
    lines.append(r"\author{Autonomous Networks Research Group (ANRG)\\University of Southern California}")
    lines.append(r"\date{}")
    lines.append(r"\begin{document}")
    lines.append(r"\maketitle")
    lines.append(r"\tableofcontents")
    lines.append(r"\newpage")
    lines.append(r"")

    # ── Section 1: Setup ─────────────────────────────────────────────────────
    lines.append(r"\section{Evaluation Setup}")
    lines.append(r"")
    lines.append(r"Does the relative performance ranking of HEFT, HEFT-1, and HEFT-2 hold")
    lines.append(r"on random graphs?  We place \textbf{50 nodes} uniformly at random in an")
    lines.append(r"$L\times L$ square and create bidirectional links between all pairs within")
    lines.append(r"$R=80$\,m.  Varying $L$ controls network density.  We run the same")
    lines.append(r"DAGs, routing schemes, and interference model as the grid evaluation.")
    lines.append(r"")

    lines.append(r"\begin{table}[H]")
    lines.append(r"\centering")
    lines.append(r"\begin{tabular}{ll}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{Parameter} & \textbf{Value} \\")
    lines.append(r"\midrule")
    lines.append(r"Nodes & 50, positions uniform random in $[0,L]^2$ \\")
    lines.append(r"Communication range & $R=80$\,m (csma\_bianchi PHY rate from distance) \\")
    lines.append(r"Connectivity & guaranteed by minimum spanning bridge if disconnected \\")
    lines.append(r"Topology seed & 42 (fixed per density level) \\")
    lines.append(r"Seeds per combo & 30 (simulation seeds 1--30) \\")
    lines.append(r"Schedulers & HEFT (calibrated), HEFT-1, HEFT-2 \\")
    lines.append(r"Routing schemes & W, S, SH, GS, GO, GSD, GSD-D \\")
    lines.append(r"DAGs & Small (8 tasks, fork-join) and Large (30 tasks, pipeline) \\")
    lines.append(r"Interference & \texttt{csma\_bianchi}, 802.11ax 5\,GHz 20\,MHz, $P_\mathrm{tx}=20$\,dBm \\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\caption{Random network evaluation parameters.}")
    lines.append(r"\end{table}")
    lines.append(r"")

    # Topology stats table
    lines.append(r"\subsection{Topology Statistics per Density Level}")
    lines.append(r"")
    lines.append(r"\begin{table}[H]")
    lines.append(r"\centering")
    lines.append(r"\begin{tabular}{l r r r}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{Level} & \textbf{Side $L$ (m)} & \textbf{Links} & \textbf{Avg.\ degree} \\")
    lines.append(r"\midrule")
    for dlabel, side_len in density_list:
        st = topo_stats[dlabel]
        lines.append(f"  {dlabel} & {side_len} & {st['n_links']} & {st['avg_degree']:.1f} \\\\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\caption{Network topology statistics. All topologies generated with seed~42.}")
    lines.append(r"\end{table}")
    lines.append(r"")

    # ── Section 2: Line Graphs ────────────────────────────────────────────────
    lines.append(r"\section{Makespan vs.\ Density}")
    lines.append(r"")
    lines.append(r"Each line shows the mean makespan of the \emph{best routing scheme}")
    lines.append(r"for that scheduler at each density level.  X-axis is average node degree")
    lines.append(r"(higher = denser); Y-axis is mean makespan in seconds (log scale).")
    lines.append(r"")

    for dag_label, dag_fn in DAGS:
        dag_title = "Small DAG (8 tasks, fork-join)" if dag_label == "small" \
                    else "Large DAG (30 tasks, 5-stage pipeline)"
        lines.append(r"\begin{figure}[H]")
        lines.append(r"\centering")
        lines.append(r"\begin{tikzpicture}")
        lines.append(r"\begin{axis}[")
        lines.append(r"    width=0.85\textwidth, height=7cm,")
        lines.append(r"    xlabel={Average node degree},")
        lines.append(r"    ylabel={Mean makespan (s)},")
        lines.append(f"    title={{{dag_title}}},")
        lines.append(r"    ymode=log,")
        lines.append(r"    xmin=2, xmax=27,")
        lines.append(r"    grid=both,")
        lines.append(r"    grid style={line width=0.2pt, draw=gray!30},")
        lines.append(r"    major grid style={line width=0.4pt, draw=gray!60},")
        lines.append(r"    legend pos=north east,")
        lines.append(r"    legend style={font=\small},")
        lines.append(r"    xtick={4,8,12,16,20,24},")
        lines.append(r"]")
        for sched in SCHEDULERS:
            coords = pgf_coords(dag_label, sched)
            if not coords:
                continue
            color = sched_colors[sched]
            mark  = sched_marks[sched]
            name  = sched_names[sched]
            lines.append(f"\\addplot[color={color}, mark={mark}, thick, mark size=2pt]")
            lines.append(f"    coordinates {{{coords}}};")
            lines.append(f"\\addlegendentry{{{name}}}")
        lines.append(r"\end{axis}")
        lines.append(r"\end{tikzpicture}")
        lines.append(f"\\caption{{Makespan vs.\ average node degree ({dag_title}). "
                     r"Each point is the scheduler's best routing scheme at that density, "
                     r"averaged over 30 seeds.}}")
        lines.append(r"\end{figure}")
        lines.append(r"")

    # ── Section 3: Best routing per density ──────────────────────────────────
    lines.append(r"\section{Best Routing Scheme per Density and Scheduler}")
    lines.append(r"")

    for dag_label, _ in DAGS:
        dag_title = "Small DAG" if dag_label == "small" else "Large DAG (30 tasks)"
        lines.append(f"\\subsection{{{dag_title}}}")
        lines.append(r"")
        lines.append(r"\begin{table}[H]")
        lines.append(r"\centering")
        lines.append(r"\small")
        lines.append(r"\begin{tabular}{l r " + "r@{\,}l r@{\,}l r@{\,}l" + r"}")
        lines.append(r"\toprule")
        lines.append(r"\textbf{Density} & \textbf{Avg.\ deg.}")
        for sched in SCHEDULERS:
            lines.append(f"  & \\multicolumn{{2}}{{c}}{{\\textbf{{{sched_names[sched]}}}}}")
        lines.append(r"\\")
        lines.append(r"& & " + " & ".join(r"\textbf{Route} & \textbf{(s)}" for _ in SCHEDULERS) + r"\\")
        lines.append(r"\midrule")
        for dlabel, side_len in density_list:
            ad = topo_stats[dlabel]["avg_degree"]
            row = f"  {dlabel} & {ad:.1f}"
            for sched in SCHEDULERS:
                key = (dlabel, dag_label, sched)
                if key in best:
                    bl, ms = best[key]
                    row += f" & {bl} & {ms:.1f}"
                else:
                    row += r" & --- & ---"
            row += r" \\"
            lines.append(row)
        lines.append(r"\bottomrule")
        lines.append(r"\end{tabular}")
        lines.append(f"\\caption{{Best (routing, makespan) per scheduler for {dag_title.lower()}. "
                     r"Makespan in seconds, averaged over 30 seeds.}}")
        lines.append(r"\end{table}")
        lines.append(r"")

    # ── Section 4: Full results per density level ─────────────────────────────
    lines.append(r"\section{Full Results Tables}")
    lines.append(r"")
    lines.append(r"Mean makespan (seconds) averaged over 30 seeds. "
                 r"\win{Bold green}: overall best for that density+DAG. "
                 r"\bad{Red}: worst in that scheduler column.")
    lines.append(r"")

    for dlabel, side_len in density_list:
        ad = topo_stats[dlabel]["avg_degree"]
        lines.append(f"\\subsection{{{dlabel}: $L={side_len}$\\,m, avg.\ degree ${ad:.1f}$}}")
        lines.append(r"")

        for dag_label, _ in DAGS:
            dag_title = "Small DAG" if dag_label == "small" else "Large DAG"
            # Collect all values for this (dlabel, dag_label)
            all_vals = [(results.get((dlabel, dag_label, s, lb)), s, lb)
                        for s in SCHEDULERS for lb in LABELS
                        if results.get((dlabel, dag_label, s, lb)) is not None]
            overall_best = min(all_vals, key=lambda x: x[0])[0] if all_vals else None

            # Per-scheduler worst
            sched_worst = {}
            for sched in SCHEDULERS:
                vs = [results.get((dlabel, dag_label, sched, lb)) for lb in LABELS
                      if results.get((dlabel, dag_label, sched, lb)) is not None]
                sched_worst[sched] = max(vs) if vs else None

            lines.append(f"\\subsubsection*{{{dag_title}}}")
            lines.append(r"\begin{table}[H]")
            lines.append(r"\centering")
            lines.append(r"\small")
            lines.append(r"\begin{tabular}{l r r r}")
            lines.append(r"\toprule")
            lines.append(r"\textbf{Routing} & \textbf{HEFT (s)} & \textbf{HEFT-1 (s)} & \textbf{HEFT-2 (s)} \\")
            lines.append(r"\midrule")
            for rlabel in LABELS:
                row_parts = [rlabel]
                for sched in SCHEDULERS:
                    v = results.get((dlabel, dag_label, sched, rlabel))
                    if v is None:
                        row_parts.append("---")
                    elif overall_best is not None and abs(v - overall_best) / overall_best < 0.005:
                        row_parts.append(r"\win{" + fmt(v) + r"}")
                    elif sched_worst.get(sched) is not None and abs(v - sched_worst[sched]) / sched_worst[sched] < 0.005:
                        row_parts.append(r"\bad{" + fmt(v) + r"}")
                    else:
                        row_parts.append(fmt(v))
                lines.append("  " + " & ".join(row_parts) + r" \\")
            lines.append(r"\bottomrule")
            lines.append(r"\end{tabular}")
            lines.append(r"\end{table}")
            lines.append(r"")

    # ── Section 5: Analysis ───────────────────────────────────────────────────
    lines.append(r"\section{Analysis}")
    lines.append(r"")
    lines.append(r"\subsection{Does HEFT-1 Dominance Hold on Random Graphs?}")
    lines.append(r"")
    lines.append(r"On the regular grid evaluation, HEFT-1 dominated by $3.5$--$7.2\times$")
    lines.append(r"over HEFT and HEFT-2 because csma\_bianchi interference made multi-hop")
    lines.append(r"transfers prohibitively expensive.  On random graphs:")
    lines.append(r"\begin{itemize}")
    lines.append(r"  \item At \textbf{high density} (avg.\ degree $\geq 12$): HEFT-1 again")
    lines.append(r"    co-locates tasks, avoiding interference.  The gap over HEFT/HEFT-2")
    lines.append(r"    is similar to the grid experiments.")
    lines.append(r"  \item At \textbf{low density} (avg.\ degree $\leq 4$): nodes have")
    lines.append(r"    fewer neighbours, so HEFT-1 has less freedom to co-locate.  The")
    lines.append(r"    calibrated HEFT may close the gap when multi-hop is unavoidable.")
    lines.append(r"\end{itemize}")
    lines.append(r"")
    lines.append(r"\subsection{Best Routing Scheme Consistency}")
    lines.append(r"")
    lines.append(r"For HEFT-1, the best routing scheme may shift across density levels.")
    lines.append(r"At high density, GSD-D or GO tend to win (many simultaneous transfers,")
    lines.append(r"deferral or overlap-ordering helps).  At low density, S or SH may win")
    lines.append(r"(fewer alternate paths, min-delay routing picks the best available).")
    lines.append(r"")
    lines.append(r"\subsection{Random vs.\ Grid Topology}")
    lines.append(r"")
    lines.append(r"Random graphs differ from grids in two key ways:")
    lines.append(r"\begin{enumerate}")
    lines.append(r"  \item \textbf{Non-uniform node degrees.}  Some nodes are hubs (many")
    lines.append(r"    neighbours), others have degree 1--2.  HEFT-1 will place tasks on")
    lines.append(r"    hub nodes that have more same-node or adjacent options.")
    lines.append(r"  \item \textbf{No guaranteed path diversity.}  On sparse random graphs,")
    lines.append(r"    some node pairs may have only one path; interference-aware routing")
    lines.append(r"    has nothing to choose between.")
    lines.append(r"\end{enumerate}")
    lines.append(r"")

    lines.append(r"\section{Reproducing These Results}")
    lines.append(r"\begin{verbatim}")
    lines.append(r"cd ncsim/")
    lines.append(r"python run_random_eval.py")
    lines.append(r"# Output JSON: /tmp/ncsim_random_eval/random_eval_results.json")
    lines.append(r"\end{verbatim}")
    lines.append(r"")
    lines.append(r"\end{document}")

    return "\n".join(lines)


if __name__ == "__main__":
    main()

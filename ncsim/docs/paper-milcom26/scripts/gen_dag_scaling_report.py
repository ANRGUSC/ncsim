#!/usr/bin/env python3
"""Generate dag_scaling_results.tex + PDF from dag_scaling_results.json.

Uses matplotlib for line plots (saved as PDF) instead of pgfplots,
so no extra TeX packages are required.
"""

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

PAPER_DIR = Path(__file__).parent.parent          # paper-milcom26/ (graphicspath {.})
DATASET   = PAPER_DIR / "dataset"
JSON_PATH = DATASET / "dag_scaling_results.json"
FIGS_DIR  = PAPER_DIR                              # embedded Fig 4 panels go here
DOCS      = DATASET                                # aggregate .tex lives here

LABELS = ["W", "S", "SH", "GS", "GC", "GB", "GO", "GSD", "GSD-D"]

_SCHEME_COLOR = {
    "W":     "#1f77b4",
    "S":     "#d62728",
    "SH":    "#ff7f0e",
    "GS":    "#2ca02c",
    "GC":    "#9467bd",
    "GB":    "#8c564b",
    "GO":    "#17becf",
    "GSD":   "#7f7f7f",
    "GSD-D": "#e377c2",
}
_SCHEME_MARKER = {
    "W": "o", "S": "s", "SH": "^", "GS": "D",
    "GC": "x", "GB": "+", "GO": "p", "GSD": "*", "GSD-D": "h",
}
_SCHEME_DASH = {
    "W": "-",  "S": "-",  "SH": "-",
    "GS": "--", "GC": "--", "GB": "--", "GO": "--",
    "GSD": ":", "GSD-D": ":",
}

NET_TITLES = {
    "L150": r"Random Network, $L=150\,\mathrm{m}$ (Dense)",
    "L500": r"Random Network, $L=500\,\mathrm{m}$ (Sparse)",
    "7x7":  r"$7\times7$ Grid (49 nodes, 40 m spacing)",
}
NET_ORDER = ["L150", "L500", "7x7"]


def load():
    with open(JSON_PATH) as f:
        d = json.load(f)
    cfg = d["config"]
    dag_configs = cfg["dag_configs"]   # [[n_tasks, stage_widths, desc], ...]
    dag_sizes   = [c[0] for c in dag_configs]
    dag_descs   = {c[0]: c[2] for c in dag_configs}

    # Rebuild stage_widths for edge count
    def count_edges(sw):
        import math as _m
        edges = 0
        for i in range(len(sw) - 1):
            w_cur, w_next = sw[i], sw[i+1]
            if w_cur == 1:
                edges += w_next
            elif w_next == 1:
                edges += w_cur
            else:
                n_out = max(1, _m.ceil(w_next / w_cur))
                edges += w_cur * n_out
        return edges

    dag_edges = {c[0]: count_edges(c[1]) for c in dag_configs}
    nets      = cfg["networks"]    # {name: {n_nodes, n_links, avg_degree}}

    NUM_SEEDS = cfg.get("num_seeds", 20)
    results = {}    # (net, n_tasks, label) -> (mean, std) | (None, None)
    for key, val in d["results"].items():
        net, nt, lb = key.split("|")
        results[(net, int(nt), lb)] = (val["mean"], val.get("std", 0.0))

    return dag_sizes, dag_descs, dag_edges, nets, results, NUM_SEEDS


def make_plots(dag_sizes, nets, results, num_seeds):
    """Save one line-plot PDF per network with 95% CI error bars."""
    z95 = 1.96 / math.sqrt(num_seeds)   # multiplier: CI half-width = z95 * std
    paths = {}
    for net_name in NET_ORDER:
        fig, ax = plt.subplots(figsize=(8, 4.5))
        for lb in LABELS:
            xs, ys, yerr = [], [], []
            for n in dag_sizes:
                entry = results.get((net_name, n, lb), (None, None))
                mean, std = entry
                if mean is not None:
                    xs.append(n)
                    ys.append(mean)
                    yerr.append(z95 * (std or 0.0))
            if xs:
                ax.errorbar(xs, ys, yerr=yerr,
                            color=_SCHEME_COLOR[lb],
                            marker=_SCHEME_MARKER[lb],
                            linestyle=_SCHEME_DASH[lb],
                            linewidth=1.4, markersize=4,
                            capsize=3, capthick=1, elinewidth=0.8,
                            label=lb)
        ax.set_yscale("log")
        ax.set_xlabel("Number of tasks (DAG size)", fontsize=11)
        ax.set_ylabel("Mean makespan (s, log scale)", fontsize=11)
        ax.set_title(NET_TITLES[net_name], fontsize=11)
        ax.set_xticks(dag_sizes)
        ax.xaxis.set_major_formatter(ticker.ScalarFormatter())
        ax.grid(True, which="both", linestyle=":", linewidth=0.5, alpha=0.7)
        ax.legend(ncol=3, fontsize=8, loc="upper left")
        fig.tight_layout()
        out = FIGS_DIR / f"dag_scaling_{net_name}.pdf"
        fig.savefig(out)
        plt.close(fig)
        paths[net_name] = out
    return paths


def fmt(v, d=3):
    return f"{v:.{d}f}" if v is not None else "---"


def build_tex(dag_sizes, dag_descs, dag_edges, nets, results, num_seeds, plot_paths, json_path):
    NUM_SEEDS = num_seeds
    parts = []

    # ── Preamble ─────────────────────────────────────────────────────────────
    parts.append(r"""\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{booktabs}
\usepackage{tabularx}
\usepackage{xcolor}
\usepackage{amsmath}
\usepackage{float}
\usepackage{graphicx}
\usepackage{hyperref}

\hypersetup{colorlinks=true, linkcolor=blue!60!black}

\newcommand{\win}[1]{\textcolor{green!50!black}{\textbf{#1}}}
\newcommand{\bad}[1]{\textcolor{red!70!black}{#1}}

\title{DAG-Size Scaling: Routing Scheme Comparison\\
{\large Fixed Networks $\cdot$ Varying DAG Size $\cdot$ HEFT-1 Scheduler}}
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

Since HEFT-1 dominates under \texttt{csma\_bianchi} interference (it co-locates
tasks to avoid multi-hop transfers), this experiment fixes the scheduler to HEFT-1
and asks: \emph{which routing scheme performs best as DAG size grows?}
Three representative networks are held fixed; DAG size is varied from 8 to 60 tasks.

\begin{center}
\small
\begin{tabularx}{\textwidth}{l X}
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

    net_avg_deg = {}
    for net_name in NET_ORDER:
        info = nets[net_name]
        ad = info["avg_degree"]
        net_avg_deg[net_name] = ad
        if "L" in net_name:
            L = int(net_name[1:])
            desc = (f"50 nodes in $L={L}$\\,m square, comm.\\ range 80\\,m; "
                    f"{info['n_links']} links, avg.\\ degree ${ad:.1f}$")
        else:
            desc = (f"49 nodes, 40\\,m grid spacing; "
                    f"{info['n_links']} links, avg.\\ degree ${ad:.1f}$")
        parts.append(f"  {net_name} & {desc} \\\\")

    parts.append(r"\midrule")
    parts.append(r"\multicolumn{2}{l}{\textbf{DAG Sizes}} \\")
    for n_tasks in dag_sizes:
        n_edges = dag_edges[n_tasks]
        desc    = dag_descs[n_tasks]
        parts.append(f"  {n_tasks} tasks & {desc}; {n_edges} edges \\\\")

    parts.append(r"""\bottomrule
\end{tabularx}
\par\smallskip\noindent{\small\textit{Table 1: Evaluation parameters.}}
\end{center}
\addtocounter{table}{1}
""")

    # ── Section 2: Per-network results ────────────────────────────────────────
    parts.append(r"""
%======================================================================
\section{Results per Network}
""")

    for net_name in NET_ORDER:
        title = NET_TITLES[net_name]
        parts.append(r"\subsection{" + title + "}\n")

        # ── Makespan table ─────────────────────────────────────────────────
        col_fmt = "l " + " r" * len(dag_sizes)
        parts.append(r"\begin{table}[H]")
        parts.append(r"\centering")
        parts.append(r"\small")
        parts.append(r"\setlength{\tabcolsep}{4pt}")
        parts.append(r"\begin{tabular}{" + col_fmt + "}")
        parts.append(r"\toprule")

        hdr = r"\textbf{Routing}"
        for n in dag_sizes:
            hdr += f" & \\textbf{{{n}t}}"
        hdr += r" \\"
        parts.append(hdr)
        parts.append(r"\midrule")

        # column best/worst by mean
        z95 = 1.96 / math.sqrt(NUM_SEEDS)
        col_best, col_worst = {}, {}
        for n in dag_sizes:
            vals = {lb: results.get((net_name, n, lb), (None, None))[0] for lb in LABELS}
            vals = {k: v for k, v in vals.items() if v is not None}
            if vals:
                col_best[n]  = min(vals, key=vals.get)
                col_worst[n] = max(vals, key=vals.get)

        for lb in LABELS:
            lbl = lb.replace("-", r"\mbox{-}") if "-" in lb else lb
            cells = [lbl]
            for n in dag_sizes:
                mean, std = results.get((net_name, n, lb), (None, None))
                if mean is None:
                    cells.append("---")
                else:
                    ci = z95 * (std or 0.0)
                    s = f"{mean:.1f}$\\pm${ci:.1f}"
                    if lb == col_best.get(n):
                        s = r"\win{" + s + "}"
                    elif lb == col_worst.get(n):
                        s = r"\bad{" + s + "}"
                    cells.append(s)
            parts.append("  " + " & ".join(cells) + r" \\")

        parts.append(r"\midrule")
        best_row = [r"\textit{Best}"]
        for n in dag_sizes:
            bl = col_best.get(n, "---")
            best_row.append(r"\textit{" + bl + "}")
        parts.append("  " + " & ".join(best_row) + r" \\")
        parts.append(r"\bottomrule")
        parts.append(r"\end{tabular}")

        size_str = ", ".join(str(n) for n in dag_sizes)
        parts.append(
            r"\caption{Mean makespan $\pm$ 95\% CI (s) for " + net_name + r" network, HEFT-1, "
            + str(NUM_SEEDS) + r" seeds. DAG sizes (tasks): " + size_str + r". "
            r"\win{Bold green}: best per column. \bad{Red}: worst per column.}"
        )
        parts.append(r"\end{table}")
        parts.append("")

        # ── Line plot ──────────────────────────────────────────────────────
        plot_file = plot_paths[net_name].name
        parts.append(r"\begin{figure}[H]")
        parts.append(r"\centering")
        parts.append(r"\includegraphics[width=0.92\textwidth]{" + plot_file + "}")
        parts.append(
            r"\caption{Makespan vs.\ DAG size for " + net_name
            + r" (HEFT-1, " + str(NUM_SEEDS) + r" seeds, log-scale y-axis). "
            r"Each point is the mean over seeds.}"
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
    col_fmt = "l " + " r@{\\,}l" * len(NET_ORDER)
    parts.append(r"\begin{tabular}{" + col_fmt + "}")
    parts.append(r"\toprule")
    hdr = r"\textbf{Tasks}"
    for net_name in NET_ORDER:
        hdr += f" & \\multicolumn{{2}}{{c}}{{\\textbf{{{net_name}}}}}"
    hdr += r" \\"
    parts.append(hdr)
    parts.append(r"& " + " & ".join(r"\textbf{Route} & \textbf{(s)}"
                                     for _ in NET_ORDER) + r" \\")
    parts.append(r"\midrule")

    for n in dag_sizes:
        row = [str(n)]
        for net_name in NET_ORDER:
            vals = {lb: results.get((net_name, n, lb), (None, None))[0] for lb in LABELS}
            vals = {k: v for k, v in vals.items() if v is not None}
            if vals:
                bl = min(vals, key=vals.get)
                row += [bl, fmt(vals[bl])]
            else:
                row += ["---", "---"]
        parts.append("  " + " & ".join(row) + r" \\")

    parts.append(r"\bottomrule")
    parts.append(r"\end{tabular}")
    parts.append(
        r"\caption{Best routing scheme and mean makespan per network and DAG size. "
        r"All results use HEFT-1 with \texttt{csma\_bianchi} interference.}"
    )
    parts.append(r"\end{table}")
    parts.append("")

    # Win-count table
    parts.append(r"\subsection{Routing Scheme Win Counts}")
    parts.append("")
    total_cells = len(NET_ORDER) * len(dag_sizes)
    parts.append(
        r"Number of (network, DAG-size) cells where each routing scheme achieves "
        r"the lowest mean makespan (out of " + str(total_cells) + r" cells total)."
    )
    parts.append("")

    net_wins = {lb: {n: 0 for n in NET_ORDER} for lb in LABELS}
    for net_name in NET_ORDER:
        for n in dag_sizes:
            vals = {lb: results.get((net_name, n, lb), (None, None))[0] for lb in LABELS}
            vals = {k: v for k, v in vals.items() if v is not None}
            if vals:
                bl = min(vals, key=vals.get)
                net_wins[bl][net_name] += 1

    max_wins = max(sum(net_wins[lb].values()) for lb in LABELS)

    parts.append(r"\begin{table}[H]")
    parts.append(r"\centering")
    parts.append(r"\begin{tabular}{l r r r r}")
    parts.append(r"\toprule")
    parts.append(
        r"\textbf{Routing} & \textbf{Total} & \textbf{L150} & \textbf{L500} & \textbf{7x7} \\"
    )
    parts.append(r"\midrule")

    for lb in sorted(LABELS, key=lambda x: -sum(net_wins[x].values())):
        total = sum(net_wins[lb].values())
        per   = [str(net_wins[lb][n]) for n in NET_ORDER]
        lbl   = lb.replace("-", r"\mbox{-}") if "-" in lb else lb
        row   = [lbl, str(total)] + per
        if total == max_wins:
            row[0] = r"\textbf{" + row[0] + r"}"
            row[1] = r"\textbf{" + row[1] + r"}"
        parts.append("  " + " & ".join(row) + r" \\")

    parts.append(r"\bottomrule")
    parts.append(r"\end{tabular}")
    parts.append(r"\caption{Win counts. \textbf{Bold}: overall winner.}")
    parts.append(r"\end{table}")
    parts.append("")

    # ── Section 4: Analysis ───────────────────────────────────────────────────
    parts.append(r"""
%======================================================================
\section{Analysis}

\subsection{L150 (Dense Random Network): SH Dominates, Greedy Fails Catastrophically}

On the dense random network (avg.\ degree $\approx22$), \textbf{SH (shortest-hop)
wins at every DAG size from 16 tasks onward}, with S a close second at small sizes.
The interference-aware greedy schemes (GS, GC, GB, GO, GSD, GSD-D) are catastrophically
worse: 10--14$\times$ slower than SH at 60 tasks, with GS reaching nearly 5000\,s
vs.\ SH's 412\,s.

\textbf{Why:} HEFT-1 places tasks on adjacent nodes.  In a 50-node network with
$\approx22$ neighbours per node, there are many alternative paths.  The static
greedy interference-aware schemes route transfers through paths that minimise
predicted interference, but this prediction triggers cascading recalculations that
amplify actual interference among concurrent flows.  Shorter-hop paths (SH) reduce
the number of active relay links and thus reduce total interference, without any
predictive overhead.

\textbf{Scaling behaviour:} The SH and S makespans grow roughly linearly in task
count; the greedy schemes grow faster than linearly, diverging from SH as DAG
size increases.  The 45-task DAG (with its wide stage of 12 parallel tasks) causes
a particularly sharp jump for the greedy schemes.

\subsection{L500 (Sparse Random Network): GSD-D Wins, All Schemes Highly Variable}

On the sparse random network (avg.\ degree $\approx2.5$), GSD-D (dynamic routing
with deferral) wins decisively at 16, 32, and 45 tasks, sometimes by $2$--$4\times$.
At 8 tasks all schemes tie; at 60 tasks extreme variance makes rankings unreliable.

\textbf{Why:} With very few routing alternatives, interference-aware path selection
cannot pick bad paths---there is usually only one path.  But deferral (GSD-D) still
helps: when a bottleneck link is in use, deferring the next transfer avoids
double-booking that link, reducing queuing delay.  Static greedy schemes cannot
defer and may stack transfers onto the same bottleneck.

\textbf{High variance:} The sparse topology has a few critical bridge links.
Whether HEFT-1 places two tasks whose communication crosses a bridge link varies
seed-by-seed.  When it does, makespan explodes; when it does not, makespan is low.
This bimodal behaviour produces enormous standard deviations ($>$mean at large
DAG sizes), making 20-seed estimates unreliable for 45+ task DAGs on L500.

\subsection{7$\times$7 Grid: S and GS Lead, GSD Worst}

On the regular grid, \textbf{S (shortest-path) leads at small DAG sizes}; at
24 tasks GB briefly wins; at 45--60 tasks S and SH are again competitive.
GSD (dynamic routing without deferral) is consistently the worst scheme on the
grid, 1.5--3$\times$ slower than S across all sizes.  GSD-D partially recovers
by deferring, but remains behind static shortest-path.

\textbf{Why:} The 7$\times$7 grid has regular, moderate path diversity.
Shortest-path routing (S) picks the minimum-delay route, which on a grid with
uniform 40\,m spacing is also the high-BW route (cardinal 2-hop vs.\ diagonal
1-hop).  Dynamic interference-aware routing (GSD) incurs runtime overhead
recalculating paths on every transfer start/complete event; on the grid this
overhead hurts more than the improved path selection helps.

\subsection{Key Takeaways}

\begin{enumerate}
  \item \textbf{No single routing scheme wins across all networks.}
    SH wins on dense random (L150); GSD-D wins on sparse random (L500);
    S is most consistent on the regular grid.

  \item \textbf{Dense random networks: use SH, avoid interference-aware routing.}
    Path diversity enables the greedy schemes to make catastrophically bad choices;
    fewer relay hops reduces total interference better than any ordering heuristic.

  \item \textbf{Sparse random networks: use GSD-D.}
    Deferral avoids double-booking the few bottleneck links.
    Static schemes (including SH) cannot adapt when the only path is contested.

  \item \textbf{Regular grids: use S.}
    Minimum-delay routing is consistently good.  Dynamic schemes add overhead
    without meaningful benefit on the predictable grid topology.

  \item \textbf{W is always the worst or near-worst.}
    Widest-path routing maximises bottleneck bandwidth but routes through the
    most-congested links, amplifying csma\_bianchi interference in every topology.

  \item \textbf{GSD (dynamic, no deferral) is the worst scheme on regular grids.}
    Runtime recalculation overhead dominates; use GSD-D or static schemes instead.

  \item \textbf{Rankings are stable with DAG size on dense/grid networks,
    but sparse networks need more seeds at large DAG sizes.}
    L500 standard deviations exceed the mean at 45--60 tasks with 20 seeds;
    these results should be treated as indicative rather than conclusive.
\end{enumerate}

%======================================================================
\section{Reproducing These Results}

\begin{verbatim}
cd ncsim/
python run_dag_scaling_eval.py
# Outputs: /tmp/ncsim_dag_scaling/dag_scaling_results.json  (1614 s)
#          docs/dag_scaling_results.tex
#          docs/dag_scaling_results.pdf
\end{verbatim}
""")

    parts.append(r"\end{document}")
    return "\n".join(parts)


def main():
    DOCS.mkdir(exist_ok=True)
    dag_sizes, dag_descs, dag_edges, nets, results, num_seeds = load()

    print("  Generating plots ...")
    plot_paths = make_plots(dag_sizes, nets, results, num_seeds)
    for net, p in plot_paths.items():
        print(f"    {net}: {p}")

    print("  Building LaTeX ...")
    tex = build_tex(dag_sizes, dag_descs, dag_edges, nets, results, num_seeds, plot_paths, JSON_PATH)
    tex_path = DOCS / "dag_scaling_results.tex"
    with open(tex_path, "w") as f:
        f.write(tex)
    print(f"  Wrote {tex_path}")

    print("  Compiling standalone report PDF (throwaway build dir) ...")
    build = Path(tempfile.mkdtemp(prefix="dag_scaling_report_"))
    for _ in range(2):
        r = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode",
             "-output-directory", str(build), str(tex_path)],
            capture_output=True, text=True, cwd=str(build),
        )
    pdf_path = build / "dag_scaling_results.pdf"
    if pdf_path.exists():
        print(f"  Report PDF: {pdf_path}")
    else:
        print("  Compilation failed:")
        print(r.stdout[-3000:])
        sys.exit(1)


if __name__ == "__main__":
    main()

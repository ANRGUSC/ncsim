#!/usr/bin/env python3
"""Regenerate eval_results.tex with std devs and extra metrics.

Reads:
  /tmp/ncsim_full_eval/grid_augmented.json
    keys: "{exp}|{sched}|{label}" → {mean, std, mean_hops, peak_link_util,
                                       mean_xfer_duration, peak_node_util, ...}
Produces:
  docs/eval_results.tex
"""

import json
from pathlib import Path

GRID_DIR = Path("/tmp/ncsim_full_eval")
DOCS     = Path(__file__).parent / "docs"
DOCS.mkdir(exist_ok=True)

with open(GRID_DIR / "grid_augmented.json") as f:
    AUG = json.load(f)

SCHEDULERS  = ["heft", "heft1", "heft2"]
SCHED_NAMES = {"heft": "HEFT (calib.)", "heft1": "HEFT-1", "heft2": "HEFT-2"}
GRID_LABELS = ["W", "S", "SH", "GS", "GC", "GB", "GO", "GSD", "GSD-D"]

EXPERIMENTS = [
    ("4x4_small", r"$4\times4$ Grid, Small DAG (8 tasks, fork-join, 12 edges)"),
    ("4x4_large", r"$4\times4$ Grid, Large DAG (30 tasks, 5-stage pipeline, 48 edges)"),
    ("7x7_small", r"$7\times7$ Grid, Small DAG (8 tasks, fork-join, 12 edges)"),
    ("7x7_large", r"$7\times7$ Grid, Large DAG (60 tasks, 6-stage pipeline, 102 edges)"),
]
EXP_SHORT = {
    "4x4_small": r"$4\times4$ S",
    "4x4_large": r"$4\times4$ L",
    "7x7_small": r"$7\times7$ S",
    "7x7_large": r"$7\times7$ L",
}


def aug(exp, sched, lb):
    return AUG.get(f"{exp}|{sched}|{lb}", {})


def fmt(v, d=3):
    return f"{v:.{d}f}" if v is not None and v != 0.0 else "---"


def fmtms(v):
    return f"{v:.3f}" if v is not None else "---"


def wc(s):
    return r"\win{" + s + "}"


def bc(s):
    return r"\bad{" + s + "}"


# ── Find best/worst for highlighting ─────────────────────────────────────────

def highlights(exp, sched):
    """Return (best_label, worst_label) by mean makespan for (exp, sched)."""
    vals = {}
    for lb in GRID_LABELS:
        d = aug(exp, sched, lb)
        if d.get("mean"):
            vals[lb] = d["mean"]
    if not vals:
        return None, None
    best  = min(vals, key=vals.get)
    worst = max(vals, key=vals.get)
    return best, worst


def overall_winner(exp):
    """Return (sched, label, mean) of global best across all schedulers."""
    best_val  = float("inf")
    best_info = None
    for sched in SCHEDULERS:
        for lb in GRID_LABELS:
            d = aug(exp, sched, lb)
            ms = d.get("mean")
            if ms and ms < best_val:
                best_val  = ms
                best_info = (sched, lb, ms)
    return best_info


# ── Per-experiment table ──────────────────────────────────────────────────────

EXP_CAPTIONS = {
    "4x4_small": (
        r"$4\times4$ small. HEFT-1 co-locates all 8 tasks on one node; "
        r"no transfers occur so routing is irrelevant (all schemes tie near 18\,s). "
        r"GSD-D gains a small margin via deferral. HEFT and HEFT-2 are identical: "
        r"the 4$\times$4 topology's BW estimates converge across routing models. "
        r"Std devs are near zero because same-node execution is deterministic."
    ),
    "4x4_large": (
        r"$4\times4$ large. Under HEFT-1, static greedy schemes (GS--GO) tie at $\approx292$\,s "
        r"($-41\%$ vs W) by routing direct-neighbour transfers efficiently; small std devs "
        r"confirm stability. Within original HEFT, GSD wins at $\approx856$\,s: calibrated "
        r"placement spreads tasks and GSD's runtime congestion avoidance pays off. "
        r"Mean hops $>1$ under HEFT/HEFT-2 reflect multi-hop paths across the 4$\times$4 grid."
    ),
    "7x7_small": (
        r"$7\times7$ small. With 8 tasks and heterogeneous compute, the workload remains "
        r"largely compute-bound: SH and S both achieve $\approx94$\,s under HEFT/HEFT-2. "
        r"Greedy static schemes (GS--GO) are much worse under HEFT/HEFT-2 because calibrated "
        r"placement spreads tasks, then static interference-aware routing cannot handle the "
        r"resulting congestion. GSD-D wins under HEFT-1 (deferral advantage on same-node handoffs). "
        r"Peak link utilisation is low throughout, confirming compute dominance."
    ),
    "7x7_large": (
        r"$7\times7$ large. S beats SH under both HEFT ($-2\%$) and HEFT-1 ($-6\%$): "
        r"2-hop high-BW paths outperform 1-hop diagonals because bottleneck bandwidth "
        r"dominates over relay interference. Under HEFT-1, GO wins at $\approx542$\,s: "
        r"overlap-based ordering best handles dense parallel transfers in the 60-task pipeline. "
        r"W is consistently worst with the highest peak link utilisation, confirming that "
        r"widest-path routing maximises congestion under csma\_bianchi interference."
    ),
}


def make_exp_table(exp):
    lines = []
    ow_sched, ow_lb, ow_val = overall_winner(exp) or (None, None, None)

    # Column spec: Routing | per sched: mean ± std | H | PLU
    # 1 + 3*(3 metric cols) = 10 cols
    lines.append(r"\begin{table}[H]")
    lines.append(r"\centering")
    lines.append(r"\small")
    lines.append(r"\setlength{\tabcolsep}{4pt}")

    # Header: Routing | HEFT: ms±std H PLU | HEFT-1: ms±std H PLU | HEFT-2: ms±std H PLU
    lines.append(r"\begin{tabular}{l " + " ".join(["r@{$\,\pm\,$}l r r"] * 3) + "}")
    lines.append(r"\toprule")
    hdr_top = (
        r"\textbf{Routing}"
        + r" & \multicolumn{4}{c}{\textbf{HEFT (calib.)}}"
        + r" & \multicolumn{4}{c}{\textbf{HEFT-1}}"
        + r" & \multicolumn{4}{c}{\textbf{HEFT-2}} \\"
    )
    lines.append(hdr_top)
    lines.append(r"\cmidrule(lr){2-5}\cmidrule(lr){6-9}\cmidrule(lr){10-13}")
    hdr_sub = (
        r" & \multicolumn{2}{c}{ms (s)} & H & PLU"
        + r" & \multicolumn{2}{c}{ms (s)} & H & PLU"
        + r" & \multicolumn{2}{c}{ms (s)} & H & PLU \\"
    )
    lines.append(hdr_sub)
    lines.append(r"\midrule")

    for lb in GRID_LABELS:
        row_cells = [lb.replace("-", r"\mbox{-}") if lb == "GSD-D" else lb]
        for sched in SCHEDULERS:
            d = aug(exp, sched, lb)
            ms  = d.get("mean")
            std = d.get("std")
            h   = d.get("mean_hops")
            plu = d.get("peak_link_util")

            best_lb, worst_lb = highlights(exp, sched)
            is_global_best = (sched == ow_sched and lb == ow_lb)

            if ms:
                ms_str  = fmtms(ms)
                std_str = fmtms(std) if std else "0.000"
                if is_global_best:
                    ms_str = wc(ms_str)
                elif lb == worst_lb:
                    ms_str = bc(ms_str)
                elif lb == best_lb:
                    ms_str = r"\textbf{" + ms_str + r"}$^\dagger$"
                row_cells += [ms_str, std_str, fmt(h, 2), fmt(plu, 2)]
            else:
                row_cells += ["---", "---", "---", "---"]

        lines.append(" & ".join(row_cells) + r" \\")

    lines.append(r"\midrule")
    # Best row
    best_cells = [r"\textit{Best}"]
    for sched in SCHEDULERS:
        best_lb, _ = highlights(exp, sched)
        if best_lb:
            d = aug(exp, sched, best_lb)
            ms = d.get("mean", 0)
            best_cells += [r"\textit{" + best_lb + f" {ms:.3f}" + r"}", "", "", ""]
        else:
            best_cells += ["---", "", "", ""]
    lines.append(" & ".join(best_cells) + r" \\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    cap = EXP_CAPTIONS.get(exp, "")
    lines.append(r"\caption{" + cap + "}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


# ── Cross-experiment summary tables ───────────────────────────────────────────

def make_cross_table_sched(sched):
    """Per-routing ranking across experiments for one scheduler."""
    sname = SCHED_NAMES[sched]
    lines = []
    lines.append(r"\begin{table}[H]")
    lines.append(r"\centering")
    lines.append(r"\small")
    lines.append(r"\setlength{\tabcolsep}{4pt}")
    exp_shorts = [EXP_SHORT[e] for e, _ in EXPERIMENTS]
    lines.append(r"\begin{tabular}{l " + " r" * len(EXPERIMENTS) + " r}")
    lines.append(r"\toprule")
    hdr = r"\textbf{Routing} & " + " & ".join(exp_shorts) + r" & \textbf{Wins} \\"
    lines.append(hdr)
    lines.append(r"\midrule")

    # Find column winners
    col_bests = {}
    for exp, _ in EXPERIMENTS:
        best_lb, _ = highlights(exp, sched)
        col_bests[exp] = best_lb

    # Find overall winner
    global_best_exp, global_best_lb, global_best_val = None, None, float("inf")
    for exp, _ in EXPERIMENTS:
        for lb in GRID_LABELS:
            d = aug(exp, sched, lb)
            ms = d.get("mean")
            if ms and ms < global_best_val:
                global_best_val = ms
                global_best_lb  = lb
                global_best_exp = exp

    for lb in GRID_LABELS:
        wins = sum(1 for exp, _ in EXPERIMENTS if col_bests[exp] == lb)
        cells = [lb.replace("-", r"\mbox{-}") if lb == "GSD-D" else lb]
        for exp, _ in EXPERIMENTS:
            d = aug(exp, sched, lb)
            ms = d.get("mean")
            if ms:
                ms_str = f"{ms:.3f}"
                is_gw = (exp == global_best_exp and lb == global_best_lb)
                if is_gw:
                    ms_str = wc(ms_str)
                elif lb == col_bests[exp]:
                    ms_str = r"\textbf{" + ms_str + r"}$^\dagger$"
                elif lb == highlights(exp, sched)[1]:
                    ms_str = bc(ms_str)
                cells.append(ms_str)
            else:
                cells.append("---")
        cells.append(str(wins))
        lines.append(" & ".join(cells) + r" \\")

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\caption{" + sname + r" routing rankings across experiments. "
                 r"\win{Bold green}: global winner. \textbf{Bold}$^\dagger$: column winner.}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


def make_sh_vs_s_table():
    lines = []
    lines.append(r"\begin{table}[H]")
    lines.append(r"\centering")
    lines.append(r"\begin{tabular}{l r r r}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{Experiment} & \textbf{S (s)} & \textbf{SH (s)} & \textbf{SH vs S (\%)} \\")
    lines.append(r"\midrule")
    for sched in SCHEDULERS:
        lines.append(r"\multicolumn{4}{l}{\textit{" + SCHED_NAMES[sched] + r"}} \\")
        for exp, _ in EXPERIMENTS:
            ds = aug(exp, sched, "S")
            dh = aug(exp, sched, "SH")
            ms_s  = ds.get("mean")
            ms_sh = dh.get("mean")
            if ms_s and ms_sh:
                pct = (ms_sh - ms_s) / ms_s * 100
                sign = "+" if pct > 0 else ""
                s_fmt  = f"{ms_s:.3f}"
                sh_fmt = f"{ms_sh:.3f}"
                if ms_s < ms_sh:
                    s_fmt = r"\textbf{" + s_fmt + "}"
                else:
                    sh_fmt = r"\textbf{" + sh_fmt + "}"
                cells = [EXP_SHORT[exp], s_fmt, sh_fmt, f"${sign}{pct:.1f}$"]
            else:
                cells = [EXP_SHORT[exp], "---", "---", "---"]
            lines.append(" & ".join(cells) + r" \\")
        if sched != "heft2":
            lines.append(r"\midrule")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\caption{SH vs S makespan comparison. \textbf{Bold}: lower of the two. "
                 r"SH does not win by a meaningful margin in any case where the two differ.}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


def make_best_summary_table():
    lines = []
    lines.append(r"\begin{table}[H]")
    lines.append(r"\centering")
    lines.append(r"\begin{tabular}{l l r@{$\,\pm\,$}l l r@{$\,\pm\,$}l l r@{$\,\pm\,$}l}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{Experiment}"
                 r" & \multicolumn{3}{c}{\textbf{HEFT (calib.)}}"
                 r" & \multicolumn{3}{c}{\textbf{HEFT-1}}"
                 r" & \multicolumn{3}{c}{\textbf{HEFT-2}} \\")
    lines.append(r"\cmidrule(lr){2-4}\cmidrule(lr){5-7}\cmidrule(lr){8-10}")
    lines.append(r" & Routing & \multicolumn{2}{c}{ms (s)} "
                 r"& Routing & \multicolumn{2}{c}{ms (s)} "
                 r"& Routing & \multicolumn{2}{c}{ms (s)} \\")
    lines.append(r"\midrule")
    for exp, _ in EXPERIMENTS:
        cells = [EXP_SHORT[exp]]
        for sched in SCHEDULERS:
            best_lb, _ = highlights(exp, sched)
            if best_lb:
                d   = aug(exp, sched, best_lb)
                ms  = d.get("mean", 0)
                std = d.get("std", 0)
                cells += [best_lb, f"{ms:.3f}", f"{std:.3f}"]
            else:
                cells += ["---", "---", "---"]
        lines.append(" & ".join(cells) + r" \\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\caption{Best routing scheme per scheduler and experiment (mean $\pm$ std over 30 seeds). "
                 r"HEFT-1 achieves the lowest makespans in every experiment.}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


# ── Build full TeX ────────────────────────────────────────────────────────────

def build_tex():
    parts = []
    parts.append(r"""\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{booktabs}
\usepackage{xcolor}
\usepackage{amsmath}
\usepackage{float}
\usepackage{hyperref}

\hypersetup{colorlinks=true, linkcolor=blue!60!black}

\newcommand{\win}[1]{\textcolor{green!50!black}{\textbf{#1}}}
\newcommand{\bad}[1]{\textcolor{red!70!black}{#1}}

\title{Routing Scheme Evaluation Results\\{\large Grid Networks with csma\_bianchi Interference}}
\author{Autonomous Networks Research Group (ANRG)\\University of Southern California}
\date{}

\begin{document}
\maketitle
\tableofcontents
\newpage
""")

    # ── Section 1: Setup ──────────────────────────────────────────────────────
    parts.append(r"""
%======================================================================
\section{Evaluation Setup}

\begin{table}[H]
\centering
\begin{tabular}{ll}
\toprule
\textbf{Parameter} & \textbf{Value} \\
\midrule
Seeds per combo        & 30 (seeds 1--30); values are mean $\pm$ std makespan \\
Schedulers             & HEFT: calibrated to runtime routing model \\
                       & HEFT-1: direct-link BW; 0.001\,MB/s for non-adjacent \\
                       & HEFT-2: widest-path BW for all pairs (fixed) \\
Routing schemes        & W, S, SH, GS, GC, GB, GO, GSD, GSD-D \\
Interference model     & \texttt{csma\_bianchi} (802.11ax, 5\,GHz, 20\,MHz) \\
RF parameters          & $P_\text{tx}=20$\,dBm, path-loss exponent $n=3.0$ \\
Grid spacing           & 40\,m; adjacent-link PHY rate $\approx8.6$\,MB/s \\
Compute costs          & 150--1000\,cu (heterogeneous, $\approx6.7\times$ range) \\
Data sizes             & 2--30\,MB (heterogeneous, $15\times$ range) \\
Node capacities        & 80--300\,cu/s (heterogeneous) \\
Total runs             & 3 schedulers $\times$ 9 routing $\times$ 4 experiments $\times$ 30 seeds = 3240 \\
\bottomrule
\end{tabular}
\caption{Evaluation parameters.}
\end{table}

\medskip\noindent
\textbf{HEFT} (calibrated) passes the runtime routing model to HEFT's pairwise
rate matrix, so placement decisions are calibrated to whichever routing scheme
runs at simulation time.  Equals HEFT-2 when paired with \texttt{widest\_path}.

\medskip\noindent
\textbf{HEFT-1} pins 0.001\,MB/s on all non-adjacent pairs regardless of runtime
routing.  Strongly biases placement toward same-node or direct-neighbour assignments.

\medskip\noindent
\textbf{HEFT-2} always uses \texttt{WidestPathRouting} for pairwise BW estimates,
regardless of the runtime routing scheme.

\medskip\noindent
\textbf{SH} (Shortest Hop) minimises hop count, breaking ties by $\sum 1/b_\ell$.
Added alongside S to test whether reducing relay count reduces csma\_bianchi
interference enough to offset lower bottleneck bandwidth.

\medskip\noindent
\textbf{Extra metrics}: H = mean path length (hops) per transfer;
PLU = peak link utilisation (fraction of time the busiest link was active).
Values are averaged over 30 seeds.
""")

    # ── Section 2: Full tables ─────────────────────────────────────────────────
    parts.append(r"""
%======================================================================
\section{Full Results Tables}

Mean makespan $\pm$ std in seconds, over 30 seeds.
\win{Bold green}: global experiment winner.
\textbf{Bold}$^\dagger$: best within that scheduler column.
\bad{Red}: worst within that scheduler column.
H = mean hops per transfer; PLU = peak link utilisation.
""")

    for exp, title in EXPERIMENTS:
        parts.append(r"\subsection{" + title + "}\n")
        parts.append(make_exp_table(exp))
        parts.append("")

    # ── Section 3: Cross-experiment summaries ─────────────────────────────────
    parts.append(r"""
%======================================================================
\section{Cross-Experiment Comparison}

\subsection{Overall Best per Experiment}
""")
    parts.append(make_best_summary_table())

    parts.append(r"\subsection{HEFT-1: Routing Rankings}")
    parts.append(make_cross_table_sched("heft1"))

    parts.append(r"\subsection{HEFT (calibrated): Routing Rankings}")
    parts.append(make_cross_table_sched("heft"))

    parts.append(r"\subsection{HEFT-2: Routing Rankings}")
    parts.append(make_cross_table_sched("heft2"))

    parts.append(r"\subsection{SH vs S: Does Hop-Count Routing Help?}")
    parts.append(make_sh_vs_s_table())

    # ── Section 4: Analysis ────────────────────────────────────────────────────
    parts.append(r"""
%======================================================================
\section{Analysis}

\subsection{Why HEFT-1 Dominates on csma\_bianchi Grids}

HEFT-1's 0.001\,MB/s penalty forces all communicating tasks onto the same
node or direct neighbours.  On a csma\_bianchi grid, PHY rates drop steeply
with distance and relay hops accumulate interference; co-location avoids both.
HEFT and HEFT-2 spread tasks across the topology, where runtime interference
is typically $5\text{--}10\times$ worse than HEFT's estimates.  The extra-metric
tables confirm this: HEFT and HEFT-2 show consistently higher peak link
utilisation and mean hops than HEFT-1, which achieves near-zero utilisation
by routing most transfers as same-node handoffs.

\subsection{Why SH Does Not Beat S on These Grids}

The hypothesis was: fewer relay hops $\Rightarrow$ fewer interfering transmitters
$\Rightarrow$ lower total interference $\Rightarrow$ lower makespan.  The
empirical result contradicts this on the 40\,m grids.  On a grid with 8.6\,MB/s
cardinal links and lower-BW diagonal links at 56.6\,m, the path that minimises
$\sum 1/b$ (S) typically uses 2-hop cardinal routes rather than 1-hop diagonal
routes.  The 2-hop path has higher bottleneck bandwidth (8.6 vs lower diagonal
BW), which more than compensates for the second active link.

\textbf{When SH might win:} topologies where all alternate paths have the same
bandwidth (equal-BW grids) but different hop counts, making the relay
interference cost the binding constraint.  On the heterogeneous-BW grids tested
here, this condition is not met.

\subsection{Original HEFT vs HEFT-2: When Does Calibration Matter?}

On the $4\times4$ grid, original HEFT and HEFT-2 produce identical results for
all routing schemes.  The topology is compact enough that different routing
models return similar path bandwidths.

On the $7\times7$ grid with the large DAG, calibration starts to matter: HEFT
(calibrated to GSD) gives $\approx4192$\,s for GSD-routing, while HEFT-2 gives
$\approx4460$\,s.  The calibrated scheduler places tasks at nodes where GSD-style
congestion avoidance is effective; HEFT-2's widest-path calibration places them
differently, and GSD cannot recover.

\subsection{GO Wins on $7\times7$ Large (HEFT-1)}

Under HEFT-1, tasks are placed on direct neighbours.  The 60-task pipeline
creates many simultaneous transfers at each stage transition.  GO (overlap-based
ordering) routes the most contested flows first---flows whose time windows
overlap with the most other flows get first pick of low-interference paths.  On
the denser $7\times7$ grid (240 links, more routing diversity), this ordering
extracts more benefit than start-time ordering (GS), delivering $\approx542$\,s
vs $\approx661$\,s ($-18\%$).

\subsection{Key Takeaways}

\begin{enumerate}
  \item \textbf{HEFT-1 dominates on csma\_bianchi grids.}  Co-location is
        optimal; HEFT and HEFT-2 spread tasks into heavy interference, yielding
        3--10$\times$ higher makespans on large experiments.
  \item \textbf{Use GO with HEFT-1 on large grids.}  Overlap-based ordering
        outperforms start-time (GS) and byte-size (GB) by routing the most
        contested flows first.  On small grids or small DAGs, GSD-D is slightly
        better via deferral.
  \item \textbf{SH does not improve over S} on heterogeneous-BW grids.
        Min-delay (S) beats min-hop (SH) because 2-hop high-BW paths deliver
        higher bottleneck bandwidth than 1-hop low-BW diagonals.
  \item \textbf{W is always the worst routing scheme.}  Widest-path routes
        flows through the highest-BW but also most-congested paths, maximising
        interference; peak link utilisation under W is consistently the highest
        in every experiment.
  \item \textbf{Original HEFT calibration matters on large topologies.}
        On $7\times7$, calibrated HEFT outperforms HEFT-2 for dynamic routing
        schemes (GSD) by correctly anticipating per-scheme path bandwidths.
  \item \textbf{Std devs are low under HEFT-1}, reflecting the stability of
        co-location: routing is irrelevant when all tasks share a node.  Under
        HEFT/HEFT-2, std devs are larger, indicating sensitivity to per-seed
        topology variation (random node capacities and data sizes).
\end{enumerate}

%======================================================================
\section{Reproducing These Results}

\begin{verbatim}
cd ncsim/
python run_routing_eval.py
# Output: /tmp/ncsim_full_eval/  (per-seed run directories)
# Runtime: ~590 s  (3240 runs, 8 parallel workers)

python compute_interference_metrics.py
# Output: /tmp/ncsim_full_eval/grid_augmented.json

python gen_eval_results_report.py
# Output: docs/eval_results.tex
\end{verbatim}

\end{document}
""")

    return "\n".join(parts)


def main():
    print("  Building LaTeX ...")
    tex = build_tex()
    out = DOCS / "eval_results.tex"
    with open(out, "w") as f:
        f.write(tex)
    print(f"  Wrote {out}")


if __name__ == "__main__":
    main()

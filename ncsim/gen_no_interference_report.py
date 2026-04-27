#!/usr/bin/env python3
"""Regenerate no_interference_results.tex with extra evaluation metrics.

Reads:
  /tmp/ncsim_no_interference_eval/no_interference_results.json  (makespan)
  /tmp/ncsim_no_interference_eval/extra_metrics.json            (hops, util, etc.)

Produces:
  docs/no_interference_results.tex   (updated)
  docs/noint_density_small.pdf       (updated — makespan)
  docs/noint_density_large.pdf       (updated — makespan)
  docs/noint_hops_large.pdf          (new — avg hops vs density)
  docs/noint_peaklu_large.pdf        (new — peak link util vs density)
"""

import json
import statistics
from pathlib import Path

BASE    = Path("/tmp/ncsim_no_interference_eval")
DOCS    = Path(__file__).parent / "docs"
DOCS.mkdir(exist_ok=True)

# ── Load data ─────────────────────────────────────────────────────────────────

with open(BASE / "no_interference_results.json") as f:
    main_data = json.load(f)

with open(BASE / "extra_metrics.json") as f:
    extra_data = json.load(f)

def gm(key):        return main_data["grid"].get(key)
def ge(key):        return extra_data["grid"].get(key, {})
def rm(key):        return main_data["random"].get(key)
def re_(key):       return extra_data["random"].get(key, {})
def rb(key):        return main_data["rand_best"].get(key, {})
def rt(key):        return main_data["rand_topo"].get(key, {})

SCHEDULERS      = ["heft", "heft1", "heft2"]
SCHED_NAMES     = {"heft": "HEFT", "heft1": "HEFT-1", "heft2": "HEFT-2"}
DENSITIES       = ["L150","L200","L250","L300","L350","L400","L500"]
RAND_DAGS       = ["small","large"]
GRID_EXPERIMENTS = [
    ("4x4_small", 4, "small (8 tasks, fork-join)"),
    ("4x4_large", 4, "large (30 tasks, 5-stage pipeline)"),
    ("7x7_small", 7, "small (8 tasks, fork-join)"),
    ("7x7_large", 7, "large (60 tasks, 6-stage pipeline)"),
]
GRID_LABELS = ["W","S","SH","GS","GC","GB","GO","GSD","GSD-D"]
RAND_LABELS = ["W","S","SH","GO","GS","GSD","GSD-D"]


# ── Matplotlib plots ──────────────────────────────────────────────────────────

def make_plots():
    import matplotlib
    matplotlib.use("pdf")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker

    degrees = [rt(dl)["avg_degree"] for dl in DENSITIES]
    STYLES  = {
        "heft":  dict(color="#2166ac", marker="o", linewidth=1.8, markersize=6, linestyle="-"),
        "heft1": dict(color="#1a9641", marker="s", linewidth=1.8, markersize=6, linestyle="-"),
        "heft2": dict(color="#d7191c", marker="^", linewidth=1.8, markersize=6, linestyle="-"),
    }
    NAMES = {"heft": "HEFT (calib.)", "heft1": "HEFT-1", "heft2": "HEFT-2"}

    def _fig(ylabel, title, outfile, data_fn, log=False):
        fig, ax = plt.subplots(figsize=(6.5, 3.8))
        for sched in SCHEDULERS:
            ys = []
            for dl in DENSITIES:
                bk = f"{dl}|large|{sched}"
                best = rb(bk)
                if best:
                    ek = f"{dl}|large|{sched}|{best['routing']}"
                    ys.append(data_fn(re_(ek)))
                else:
                    ys.append(None)
            xs = [x for x, y in zip(degrees, ys) if y is not None]
            ys = [y for y in ys if y is not None]
            ax.plot(xs, ys, label=NAMES[sched], **STYLES[sched])
        if log:
            ax.set_yscale("log")
        ax.invert_xaxis()
        ax.set_xlabel("Average node degree (higher = denser)", fontsize=11)
        ax.set_ylabel(ylabel, fontsize=11)
        ax.set_title(title, fontsize=12, pad=8)
        ax.set_xticks(degrees)
        ax.set_xticklabels([f"{d:.1f}" for d in degrees], fontsize=9)
        if log:
            ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:g}"))
        ax.grid(True, which="major", linestyle="--", linewidth=0.5, alpha=0.7)
        ax.grid(True, which="minor", linestyle=":",  linewidth=0.3, alpha=0.4)
        ax.legend(fontsize=9, framealpha=0.9)
        fig.tight_layout()
        fig.savefig(outfile, bbox_inches="tight")
        plt.close(fig)
        print(f"  Plot: {outfile}")

    # Makespan (both DAGs)
    for dag_label in RAND_DAGS:
        dag_cap = "Small DAG (8 tasks, fork-join)" if dag_label == "small" \
                  else "Large DAG (30 tasks, 5-stage pipeline)"
        fig, ax = plt.subplots(figsize=(6.5, 3.8))
        for sched in SCHEDULERS:
            ys = []
            for dl in DENSITIES:
                bk = f"{dl}|{dag_label}|{sched}"
                best = rb(bk)
                ys.append(best["makespan"] if best else None)
            xs = [x for x, y in zip(degrees, ys) if y is not None]
            ys = [y for y in ys if y is not None]
            ax.plot(xs, ys, label=NAMES[sched], **STYLES[sched])
        ax.set_yscale("log")
        ax.invert_xaxis()
        ax.set_xlabel("Average node degree (higher = denser)", fontsize=11)
        ax.set_ylabel("Best mean makespan (s, log scale)", fontsize=11)
        ax.set_title(dag_cap, fontsize=12, pad=8)
        ax.set_xticks(degrees)
        ax.set_xticklabels([f"{d:.1f}" for d in degrees], fontsize=9)
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:g}"))
        ax.grid(True, which="major", linestyle="--", linewidth=0.5, alpha=0.7)
        ax.grid(True, which="minor", linestyle=":",  linewidth=0.3, alpha=0.4)
        ax.legend(loc="upper right" if dag_label == "small" else "upper left",
                  fontsize=9, framealpha=0.9)
        fig.tight_layout()
        out = DOCS / f"noint_density_{dag_label}.pdf"
        fig.savefig(out, bbox_inches="tight")
        plt.close(fig)
        print(f"  Plot: {out}")

    # Avg hops vs density (large DAG only — small DAG is trivially 1 hop everywhere)
    _fig("Mean hops per transfer",
         "Large DAG — Mean transfer hops vs.\ density",
         DOCS / "noint_hops_large.pdf",
         lambda ev: ev.get("mean_hops"))

    # Peak link utilisation vs density (large DAG)
    _fig("Peak link utilization",
         "Large DAG — Peak link utilization vs.\ density",
         DOCS / "noint_peaklu_large.pdf",
         lambda ev: ev.get("peak_link_util"))

    # Mean transfer duration vs density (large DAG)
    _fig("Mean transfer duration (s)",
         "Large DAG — Mean transfer duration vs.\ density",
         DOCS / "noint_xferdur_large.pdf",
         lambda ev: ev.get("mean_xfer_duration"))


# ── LaTeX helpers ─────────────────────────────────────────────────────────────

def fmt(v, d=3):
    return f"{v:.{d}f}" if v is not None else "---"

def wc(s):   return r"\win{" + s + "}"
def bc(s):   return r"\bad{" + s + "}"


def build_tex():
    W = []
    ap = W.append

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

    # ── §1 Setup ──────────────────────────────────────────────────────────────
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
    ap(r"Additional metrics collected per run:")
    ap(r"\begin{itemize}\setlength{\itemsep}{1pt}")
    ap(r"  \item \textbf{Mean hops}: average path length (number of links) per logical transfer.")
    ap(r"  \item \textbf{Max hops}: longest path seen in any transfer.")
    ap(r"  \item \textbf{Peak link util.}: maximum link utilisation fraction across all links")
    ap(r"        (time the link carried traffic / makespan).")
    ap(r"  \item \textbf{Mean active link util.}: mean utilisation of links that carried any traffic.")
    ap(r"  \item \textbf{Peak node util.}: maximum node utilisation fraction (compute busy / makespan).")
    ap(r"  \item \textbf{Mean xfer duration}: mean duration of individual transfers (seconds).")
    ap(r"  \item \textbf{Mean queue wait}: mean time a task waits in a node queue before starting.")
    ap(r"\end{itemize}")
    ap(r"")

    # ── §2 Grid results ───────────────────────────────────────────────────────
    ap(r"\section{Grid Network Results}")
    ap(r"")
    ap(r"Mean makespan and additional metrics averaged over 30 seeds.")
    ap(r"\win{Bold green}: overall experiment winner. \bad{Red}: worst in that scheduler column.")
    ap(r"")

    for exp_name, grid, dag_label in GRID_EXPERIMENTS:
        ap(r"\subsection{$" + str(grid) + r"\times" + str(grid) + r"$ Grid, "
           + dag_label.capitalize() + "}")
        ap(r"")

        # Collect all values to find global best and col worst
        cols = {sched: {lb: gm(f"{exp_name}|{sched}|{lb}") for lb in GRID_LABELS}
                for sched in SCHEDULERS}
        all_ms = [v for c in cols.values() for v in c.values() if v is not None]
        gb = min(all_ms) if all_ms else None
        cw = {sched: max((v for v in cols[sched].values() if v is not None), default=None)
              for sched in SCHEDULERS}

        # Makespan table
        ap(r"\begin{table}[H]")
        ap(r"\centering\small")
        ap(r"\begin{tabular}{l r r r}")
        ap(r"\toprule")
        ap(r"\textbf{Routing} & \textbf{HEFT (s)} & \textbf{HEFT-1 (s)} & \textbf{HEFT-2 (s)} \\")
        ap(r"\midrule")
        for lb in GRID_LABELS:
            cells = []
            for sched in SCHEDULERS:
                v = cols[sched].get(lb)
                s = fmt(v)
                if v is not None:
                    if gb is not None and abs(v - gb) / (gb + 1e-9) < 0.001:
                        s = wc(s)
                    elif cw[sched] is not None and abs(v - cw[sched]) / (cw[sched] + 1e-9) < 0.001:
                        s = bc(s)
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
           + r" --- mean makespan (s) over 30 seeds.}")
        ap(r"\end{table}")
        ap(r"")

        # Extra metrics table (one per scheduler to keep width manageable)
        ap(r"\begin{table}[H]")
        ap(r"\centering\small")
        ap(r"\begin{tabular}{l r r r r r r r r r}")
        ap(r"\toprule")
        ap(r"\textbf{Routing} &"
           r" \multicolumn{3}{c}{\textbf{HEFT}} &"
           r" \multicolumn{3}{c}{\textbf{HEFT-1}} &"
           r" \multicolumn{3}{c}{\textbf{HEFT-2}} \\")
        ap(r"\cmidrule(lr){2-4}\cmidrule(lr){5-7}\cmidrule(lr){8-10}")
        ap(r"& \textbf{Hops} & \textbf{P-LU} & \textbf{XD(s)}"
           r" & \textbf{Hops} & \textbf{P-LU} & \textbf{XD(s)}"
           r" & \textbf{Hops} & \textbf{P-LU} & \textbf{XD(s)} \\")
        ap(r"\midrule")
        for lb in GRID_LABELS:
            cells = []
            for sched in SCHEDULERS:
                ek = f"{exp_name}|{sched}|{lb}"
                ev = ge(ek)
                cells += [
                    fmt(ev.get("mean_hops"), 1),
                    fmt(ev.get("peak_link_util"), 3),
                    fmt(ev.get("mean_xfer_duration"), 1),
                ]
            ap(f"  {lb} & " + " & ".join(cells) + r" \\")
        ap(r"\bottomrule")
        ap(r"\end{tabular}")
        ap(r"\caption{$" + str(grid) + r"\times" + str(grid) + r"$ " + dag_label
           + r" --- additional metrics averaged over 30 seeds."
           r" Hops = mean path length; P-LU = peak link utilisation; XD = mean transfer duration.}")
        ap(r"\end{table}")
        ap(r"")

    # ── §3 Random network results ─────────────────────────────────────────────
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
    for dl in DENSITIES:
        st = rt(dl)
        ap(f"  {dl} & {st['side_len']} & {st['n_links']} & {st['avg_degree']:.1f} \\\\")
    ap(r"\bottomrule")
    ap(r"\end{tabular}")
    ap(r"\caption{Random network topology statistics (seed~42).}")
    ap(r"\end{table}")
    ap(r"")

    # §3.2 Makespan density graphs
    ap(r"\subsection{Makespan vs.\ Density}")
    ap(r"Each point is the best-routing mean makespan for that scheduler at that"
       r" density, averaged over 30 seeds.")
    ap(r"")
    for dag_label in RAND_DAGS:
        dag_cap = "Small DAG (8 tasks, fork-join)" if dag_label == "small" \
                  else "Large DAG (30 tasks, 5-stage pipeline)"
        ap(r"\begin{figure}[H]")
        ap(r"\centering")
        ap(r"\includegraphics[width=0.85\textwidth]{noint_density_" + dag_label + r".pdf}")
        ap(r"\caption{No-interference: best-routing mean makespan vs.\ avg node degree --- "
           + dag_cap + r".}")
        ap(r"\end{figure}")
        ap(r"")

    # §3.3 Additional metric graphs (large DAG only — small trivial)
    ap(r"\subsection{Additional Metrics vs.\ Density (Large DAG)}")
    ap(r"")
    ap(r"Metrics are taken at the \emph{best} routing scheme for each scheduler at each"
       r" density level, averaged over 30 seeds. Small-DAG metrics are omitted: all"
       r" transfers are same-node (0\,hops), so hops and link utilisation are zero.")
    ap(r"")
    for fname, cap in [
        ("noint_hops_large",   "Mean hops per transfer for the best routing scheme at each density."),
        ("noint_peaklu_large", "Peak link utilisation (max over all links, fraction of makespan) for the best routing scheme."),
        ("noint_xferdur_large","Mean transfer duration (s) for the best routing scheme at each density."),
    ]:
        ap(r"\begin{figure}[H]")
        ap(r"\centering")
        ap(r"\includegraphics[width=0.85\textwidth]{" + fname + r".pdf}")
        ap(r"\caption{" + cap + r"}")
        ap(r"\end{figure}")
        ap(r"")

    # §3.4 Best-routing summary tables for random (makespan + metrics)
    for dag_label in RAND_DAGS:
        dag_cap = "Small DAG (8 tasks)" if dag_label == "small" else "Large DAG (30 tasks)"
        ap(r"\subsection{Best Routing Summary --- " + dag_cap + "}")
        ap(r"")

        # Makespan + metrics combined table
        ap(r"\begin{table}[H]")
        ap(r"\centering\small")
        ap(r"\begin{tabular}{l r r@{\,}l@{\,}r r@{\,}l@{\,}r r@{\,}l@{\,}r}")
        ap(r"\toprule")
        ap(r"\textbf{Density} &"
           r" \textbf{Deg.} &"
           r" \multicolumn{3}{c}{\textbf{HEFT}} &"
           r" \multicolumn{3}{c}{\textbf{HEFT-1}} &"
           r" \multicolumn{3}{c}{\textbf{HEFT-2}} \\")
        ap(r"\cmidrule(lr){3-5}\cmidrule(lr){6-8}\cmidrule(lr){9-11}")
        ap(r"& & \textbf{Rt} & \textbf{ms(s)} & \textbf{H/PLU}"
           r" & \textbf{Rt} & \textbf{ms(s)} & \textbf{H/PLU}"
           r" & \textbf{Rt} & \textbf{ms(s)} & \textbf{H/PLU} \\")
        ap(r"\midrule")

        all_ms_dag = [rb(f"{dl}|{dag_label}|{s}")["makespan"]
                      for dl in DENSITIES for s in SCHEDULERS
                      if rb(f"{dl}|{dag_label}|{s}")]
        gb_dag = min(all_ms_dag) if all_ms_dag else None

        for dl in DENSITIES:
            ad = rt(dl).get("avg_degree", 0)
            row = [f"  {dl} & {ad:.1f}"]
            for sched in SCHEDULERS:
                bk = f"{dl}|{dag_label}|{sched}"
                best = rb(bk)
                if best:
                    bl  = best["routing"]
                    ms  = best["makespan"]
                    ek  = f"{dl}|{dag_label}|{sched}|{bl}"
                    ev  = re_(ek)
                    hops = ev.get("mean_hops", 0)
                    plu  = ev.get("peak_link_util", 0)
                    ms_s = fmt(ms)
                    if gb_dag is not None and abs(ms - gb_dag) / (gb_dag + 1e-9) < 0.001:
                        ms_s = wc(ms_s)
                    row.append(f" & {bl} & {ms_s} & {hops:.1f}/{plu:.2f}")
                else:
                    row.append(" & --- & --- & ---")
            ap("".join(row) + r" \\")

        ap(r"\bottomrule")
        ap(r"\end{tabular}")
        ap(r"\caption{" + dag_cap + r" --- best routing scheme per (density, scheduler)."
           r" ms(s) = mean makespan; H = mean hops; PLU = peak link util."
           r" \win{Bold green}: overall best.}")
        ap(r"\end{table}")
        ap(r"")

    # ── §4 Full random results ─────────────────────────────────────────────────
    ap(r"\section{Full Random Network Results}")
    ap(r"")
    ap(r"Mean makespan (s), mean hops, and peak link util.\ averaged over 30 seeds."
       r" \win{Bold green}: overall best for that density+DAG. \bad{Red}: worst in that scheduler column.")
    ap(r"")

    for dag_label in RAND_DAGS:
        dag_cap = "Small DAG (8 tasks)" if dag_label == "small" else "Large DAG (30 tasks)"
        for dl in DENSITIES:
            ad   = rt(dl).get("avg_degree", 0)
            side = rt(dl).get("side_len", 0)
            ap(r"\subsection{" + dl + r" (avg.\ degree " + f"{ad:.1f}" + r") --- " + dag_cap + r"}")
            ap(r"\begin{table}[H]")
            ap(r"\centering\small")
            ap(r"\begin{tabular}{l r r r r r r r r r}")
            ap(r"\toprule")
            ap(r"\textbf{Routing} &"
               r" \multicolumn{3}{c}{\textbf{HEFT}} &"
               r" \multicolumn{3}{c}{\textbf{HEFT-1}} &"
               r" \multicolumn{3}{c}{\textbf{HEFT-2}} \\")
            ap(r"\cmidrule(lr){2-4}\cmidrule(lr){5-7}\cmidrule(lr){8-10}")
            ap(r"& \textbf{ms(s)} & \textbf{Hops} & \textbf{P-LU}"
               r" & \textbf{ms(s)} & \textbf{Hops} & \textbf{P-LU}"
               r" & \textbf{ms(s)} & \textbf{Hops} & \textbf{P-LU} \\")
            ap(r"\midrule")

            cols_r = {sched: {lb: rm(f"{dl}|{dag_label}|{sched}|{lb}")
                               for lb in RAND_LABELS}
                      for sched in SCHEDULERS}
            all_ms_r = [v for c in cols_r.values() for v in c.values() if v is not None]
            gb_r = min(all_ms_r) if all_ms_r else None
            cw_r = {sched: max((v for v in cols_r[sched].values() if v is not None), default=None)
                    for sched in SCHEDULERS}

            for lb in RAND_LABELS:
                cells = []
                for sched in SCHEDULERS:
                    v  = cols_r[sched].get(lb)
                    ek = f"{dl}|{dag_label}|{sched}|{lb}"
                    ev = re_(ek)
                    ms_s = fmt(v)
                    if v is not None:
                        if gb_r is not None and abs(v - gb_r) / (gb_r + 1e-9) < 0.001:
                            ms_s = wc(ms_s)
                        elif cw_r[sched] is not None and abs(v - cw_r[sched]) / (cw_r[sched] + 1e-9) < 0.001:
                            ms_s = bc(ms_s)
                    cells += [ms_s,
                               fmt(ev.get("mean_hops"), 1) if ev else "---",
                               fmt(ev.get("peak_link_util"), 3) if ev else "---"]
                ap(f"  {lb} & " + " & ".join(cells) + r" \\")

            ap(r"\bottomrule")
            ap(r"\end{tabular}")
            ap(r"\caption{" + dl + r" ($L=" + str(side)
               + r"$\,m) --- " + dag_cap
               + r". ms = makespan (s); Hops = mean path length; P-LU = peak link util.}")
            ap(r"\end{table}")
            ap(r"")

    # ── §5 Analysis ───────────────────────────────────────────────────────────
    ap(r"\section{Analysis}")
    ap(r"")
    ap(r"\subsection{Small DAG: Compute-Bound, All Metrics Trivial}")
    ap(r"")
    ap(r"All routing schemes and schedulers produce identical makespan (13.500\,s)"
       r" on the small DAG across both grid sizes and all density levels."
       r" Transfers are same-node (0 hops, 0 link utilisation) because HEFT-1"
       r" co-locates all 8 tasks. Even under HEFT/HEFT-2, the DAG's compute time"
       r" dominates: transfer costs are negligible without interference. The additional"
       r" metrics (hops, link utilisation) are all zero or near-zero for the small DAG"
       r" and are therefore omitted from the density graphs.")
    ap(r"")
    ap(r"\subsection{Why GSD/GSD-D Win on the Large DAG}")
    ap(r"")
    ap(r"The extra metrics reveal the mechanism clearly. On the $7\times7$ grid"
       r" large DAG under HEFT-1:")
    ap(r"")
    ap(r"\begin{center}")
    ap(r"\small")
    ap(r"\begin{tabular}{l r r r r}")
    ap(r"\toprule")
    ap(r"\textbf{Routing} & \textbf{Makespan (s)} & \textbf{Mean hops}"
       r" & \textbf{Peak link util.} & \textbf{Mean xfer dur.\ (s)} \\")
    ap(r"\midrule")
    for lb in ["W","S","SH","GS","GO","GSD","GSD-D"]:
        ek  = f"7x7_large|heft1|{lb}"
        ev  = ge(ek)
        ms  = gm(f"7x7_large|heft1|{lb}")
        ap(f"  {lb} & {fmt(ms)} & {fmt(ev.get('mean_hops'),1)} &"
           f" {fmt(ev.get('peak_link_util'),3)} & {fmt(ev.get('mean_xfer_duration'),1)} \\\\")
    ap(r"\bottomrule")
    ap(r"\end{tabular}")
    ap(r"\end{center}")
    ap(r"")
    ap(r"W, S, and SH all use 1-hop paths but achieve peak link utilisation of"
       r" 0.93, with mean transfer durations of 25--28\,s."
       r" GS and GO use 2.4--2.7 hops on average---their greedy ordering"
       r" tries to route around congested links but can only do so at schedule"
       r" time, and picks longer paths without reducing peak utilisation."
       r" GSD and GSD-D also use 1-hop paths but reduce peak link utilisation"
       r" to 0.77--0.79 and halve the mean transfer duration to 13.7\,s,"
       r" directly explaining the $2\times$ makespan advantage.")
    ap(r"")
    ap(r"The mechanism: HEFT-1 places each task on a direct neighbour, so all"
       r" transfers are 1-hop. However, 60 tasks across 6 pipeline stages create"
       r" many simultaneous transfers at each stage boundary. Static-path schemes"
       r" commit all flows to the same set of links; GSD observes current link"
       r" load at transfer time and routes each flow to the \emph{least-loaded}"
       r" 1-hop neighbour. The result is lower peak utilisation on any single link"
       r" and faster completion times---a pure traffic-engineering benefit that"
       r" persists even without inter-link interference.")
    ap(r"")
    ap(r"\subsection{Density Effects on the Random Network (Large DAG)}")
    ap(r"")
    ap(r"The three new density graphs (hops, peak link util., transfer duration)"
       r" show complementary trends:")
    ap(r"")
    ap(r"\begin{itemize}")
    ap(r"  \item \textbf{Mean hops} is 1.0 for all schedulers at all densities."
       r"    HEFT-1 co-locates tasks on direct neighbours; even HEFT/HEFT-2 place"
       r"    most tasks within comm-range because the 30-task pipeline is small"
       r"    relative to 50 nodes. No multi-hop routing is needed.")
    ap(r"  \item \textbf{Peak link utilisation} decreases from 0.76 at L150 (dense)"
       r"    to 0.64 at L400 (medium-sparse) and rises again at L500 (sparse)."
       r"    At medium density the network has enough path diversity for GSD to"
       r"    spread load while keeping paths short. At L500 fewer links exist,"
       r"    funnelling more traffic through each one.")
    ap(r"  \item \textbf{Mean transfer duration} tracks makespan closely: shortest"
       r"    at L350--L400 (9--10\,s) where peak link utilisation is lowest,"
       r"    longest at L500 (12--14\,s) where bottleneck links are most loaded.")
    ap(r"\end{itemize}")
    ap(r"")
    ap(r"\subsection{Comparison to csma\_bianchi Results}")
    ap(r"")
    ap(r"Removing interference collapses the large-DAG makespan from"
       r" 150--927\,s (csma\_bianchi, best routing) to 47--66\,s"
       r" (no interference, best routing) under HEFT-1---a $3$--$14\times$"
       r" reduction. The routing winner changes: SH (which minimised relay"
       r" interference) gives way to GSD (which minimises intra-link congestion"
       r" through dynamic load balancing). This confirms that the dominant cost"
       r" in the csma\_bianchi experiments was inter-link spectrum contention,"
       r" not intra-link queuing.")
    ap(r"")
    ap(r"\subsection{Reproducing These Results}")
    ap(r"\begin{verbatim}")
    ap(r"cd ncsim/")
    ap(r"python run_no_interference_eval.py      # ~70 min (12 060 runs)")
    ap(r"python compute_extra_metrics.py         # reads existing traces, ~3 min")
    ap(r"python gen_no_interference_report.py    # regenerates tex + plots")
    ap(r"cd docs/ && pdflatex no_interference_results.tex")
    ap(r"\end{verbatim}")
    ap(r"")
    ap(r"\end{document}")

    return "\n".join(W)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n  Generating plots ...")
    make_plots()

    print("  Building LaTeX ...")
    tex = build_tex()
    tex_path = DOCS / "no_interference_results.tex"
    tex_path.write_text(tex)
    print(f"  Wrote {tex_path}")

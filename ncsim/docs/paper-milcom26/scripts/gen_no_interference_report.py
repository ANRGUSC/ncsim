#!/usr/bin/env python3
"""Regenerate no_interference_results.tex with CI error bars and extra metrics.

SUPPLEMENTARY / NOT ON THE PAPER'S CRITICAL PATH. This produces a fuller
standalone .tex report and depends on ``noint_augmented.json``, which is
NOT committed (an extra aggregate emitted by a fresh
``run_no_interference_eval.py`` run into its /tmp OUTDIR). The paper's
Fig 7 is reproducible WITHOUT this script: see ``regen_density_figs.py``,
which draws it with 95% CIs directly from the committed
``dataset/no_interference_results.json``. Run this only if you re-ran
``run_no_interference_eval.py`` and want the full report.

Reads:
  /tmp/ncsim_no_interference_eval/noint_augmented.json
    keys: "{exp}|{sched}|{label}"   (grid)   → {mean, std, n, mean_hops, ...}
          "{dl}|{dag}|{sched}|{label}" (rand) → same
  /tmp/ncsim_random_eval/random_eval_results.json  → topo_stats

Produces:
  docs/no_interference_results.tex
  docs/noint_density_small.pdf      (makespan + 95% CI)
  docs/noint_density_large.pdf      (makespan + 95% CI)
  docs/noint_hops_large.pdf
  docs/noint_peaklu_large.pdf
  docs/noint_xferdur_large.pdf
"""

import json
import math
import statistics
from pathlib import Path

BASE    = Path("/tmp/ncsim_no_interference_eval")
DOCS    = Path(__file__).parent / "docs"
DOCS.mkdir(exist_ok=True)

# ── Load data ─────────────────────────────────────────────────────────────────

with open(BASE / "noint_augmented.json") as f:
    AUG = json.load(f)

with open("/tmp/ncsim_random_eval/random_eval_results.json") as f:
    _rand_eval = json.load(f)
TOPO = _rand_eval["topo_stats"]   # dlabel → {side_len, avg_degree, n_links}

GRID_DATA = AUG["grid"]     # "{exp}|{sched}|{lb}" → {mean, std, n, ...}
RAND_DATA = AUG["random"]   # "{dl}|{dag}|{sched}|{lb}" → {mean, std, n, ...}

SCHEDULERS       = ["heft", "heft1", "heft2"]
SCHED_NAMES      = {"heft": "HEFT (calib.)", "heft1": "HEFT-1", "heft2": "HEFT-2"}
DENSITIES        = ["L150","L200","L250","L300","L350","L400","L500"]
RAND_DAGS        = ["small","large"]
GRID_EXPERIMENTS = [
    ("4x4_small", 4, "small (8 tasks, fork-join)"),
    ("4x4_large", 4, "large (30 tasks, 5-stage pipeline)"),
    ("7x7_small", 7, "small (8 tasks, fork-join)"),
    ("7x7_large", 7, "large (60 tasks, 6-stage pipeline)"),
]
GRID_LABELS = ["W","S","SH","GS","GC","GB","GO","GSD","GSD-D"]
RAND_LABELS = ["W","S","SH","GO","GS","GSD","GSD-D"]


def gev(exp, sched, lb):
    """Get grid entry dict."""
    return GRID_DATA.get(f"{exp}|{sched}|{lb}", {})

def rev(dl, dag, sched, lb):
    """Get random entry dict."""
    return RAND_DATA.get(f"{dl}|{dag}|{sched}|{lb}", {})

def best_rand(dl, dag, sched):
    """Return (best_label, entry_dict) with minimum mean makespan."""
    best_lb, best_ev = None, {}
    for lb in RAND_LABELS:
        ev = rev(dl, dag, sched, lb)
        ms = ev.get("mean")
        if ms is not None and (best_lb is None or ms < best_ev.get("mean", float("inf"))):
            best_lb, best_ev = lb, ev
    return best_lb, best_ev

def _ci95(std, n=30):
    """95% CI half-width: t_{n-1,0.025} * std / sqrt(n)."""
    if not std or n <= 1:
        return std or 0.0
    t = 2.045 if n <= 30 else (2.009 if n <= 60 else 1.96)
    return t * std / math.sqrt(n)

def fmt(v, d=3):
    return f"{v:.{d}f}" if v is not None else "---"

def wc(s):   return r"\win{" + s + "}"
def bc(s):   return r"\bad{" + s + "}"


# ── Matplotlib plots ──────────────────────────────────────────────────────────

def make_plots():
    import matplotlib
    matplotlib.use("pdf")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker

    degrees = [TOPO[dl]["avg_degree"] for dl in DENSITIES]
    STYLES  = {
        "heft":  dict(color="#2166ac", marker="o", linewidth=1.8, markersize=6, linestyle="-"),
        "heft1": dict(color="#1a9641", marker="s", linewidth=1.8, markersize=6, linestyle="-"),
        "heft2": dict(color="#d7191c", marker="^", linewidth=1.8, markersize=6, linestyle="-"),
    }
    EFMT  = dict(capsize=3, capthick=0.8, elinewidth=0.8, alpha=0.6)
    NAMES = {"heft": "HEFT (calib.)", "heft1": "HEFT-1", "heft2": "HEFT-2"}

    def _extra_fig(ylabel, title, outfile, metric_key, log=False):
        fig, ax = plt.subplots(figsize=(6.5, 3.8))
        for sched in SCHEDULERS:
            ys = []
            for dl in DENSITIES:
                lb, ev = best_rand(dl, "large", sched)
                ys.append(ev.get(metric_key))
            xs = [x for x, y in zip(degrees, ys) if y is not None]
            ys2 = [y for y in ys if y is not None]
            st = STYLES[sched].copy()
            color = st.pop("color")
            ax.plot(xs, ys2, label=NAMES[sched], color=color, **st)
        if log:
            ax.set_yscale("log")
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
        print(f"  Plot: {outfile.name}")

    # Makespan (both DAGs) — with 95% CI error bars
    for dag_label in RAND_DAGS:
        dag_cap = "Small DAG (8 tasks, fork-join)" if dag_label == "small" \
                  else "Large DAG (30 tasks, 5-stage pipeline)"
        fig, ax = plt.subplots(figsize=(6.5, 3.8))
        for sched in SCHEDULERS:
            ys, errs = [], []
            for dl in DENSITIES:
                lb, ev = best_rand(dl, dag_label, sched)
                ms  = ev.get("mean")
                std = ev.get("std", 0)
                n   = ev.get("n", 30)
                ys.append(ms)
                errs.append(_ci95(std, n) if ms is not None else None)
            xs    = [x for x, y in zip(degrees, ys) if y is not None]
            ys_p  = [y for y in ys if y is not None]
            err_p = [e for e, y in zip(errs, ys) if y is not None]
            st = STYLES[sched].copy()
            color = st.pop("color")
            ax.errorbar(xs, ys_p, yerr=err_p, label=NAMES[sched],
                        color=color, **st, **EFMT)
        ax.set_yscale("log")
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
        print(f"  Plot: {out.name}")

    # Extra metric plots (large DAG — no error bars, just mean line)
    _extra_fig("Mean hops per transfer",
               r"Large DAG — Mean transfer hops vs.\ density",
               DOCS / "noint_hops_large.pdf", "mean_hops")

    _extra_fig("Peak link utilization",
               r"Large DAG — Peak link utilization vs.\ density",
               DOCS / "noint_peaklu_large.pdf", "peak_link_util")

    _extra_fig("Mean transfer duration (s)",
               r"Large DAG — Mean transfer duration vs.\ density",
               DOCS / "noint_xferdur_large.pdf", "mean_xfer_duration", log=True)


# ── LaTeX ─────────────────────────────────────────────────────────────────────

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
    ap(r"\begin{table}[H]\centering")
    ap(r"\begin{tabular}{ll}\toprule")
    ap(r"\textbf{Parameter} & \textbf{Value} \\\midrule")
    ap(r"Interference & \textbf{none} (intra-link fair-share only) \\")
    ap(r"Schedulers & HEFT (calibrated), HEFT-1, HEFT-2 \\")
    ap(r"Grid routing & W, S, SH, GS, GC, GB, GO, GSD, GSD-D \\")
    ap(r"Random routing & W, S, SH, GO, GS, GSD, GSD-D \\")
    ap(r"Seeds per combo & 30 \\")
    ap(r"Grid sizes & $4\times4$ (16 nodes, 40\,m spacing) and $7\times7$ (49 nodes) \\")
    ap(r"Random nodes & 50, uniform in $[0,L]^2$, comm range $R=80$\,m \\")
    ap(r"Density levels & L150--L500 ($L=150$\,m to $500$\,m) \\")
    ap(r"DAGs & Small (8 tasks, fork-join), Large (30/60 tasks, pipeline) \\")
    ap(r"\bottomrule\end{tabular}")
    ap(r"\caption{Evaluation parameters. All other settings identical to the interference reports.}")
    ap(r"\end{table}")
    ap(r"")
    ap(r"Error bars and uncertainty columns report 95\,\% confidence intervals")
    ap(r"($t_{29}=2.045$, $n=30$ seeds): $\mathrm{CI} = 2.045 \cdot \sigma / \sqrt{30}$.")
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

        # Collect means for global best / col worst
        cols_ms = {sched: {lb: gev(exp_name, sched, lb).get("mean")
                           for lb in GRID_LABELS}
                   for sched in SCHEDULERS}
        all_ms = [v for c in cols_ms.values() for v in c.values() if v is not None]
        gb  = min(all_ms) if all_ms else None
        cw  = {sched: max((v for v in cols_ms[sched].values() if v is not None), default=None)
               for sched in SCHEDULERS}

        # Makespan table with 95% CI
        ap(r"\begin{table}[H]\centering\small")
        ap(r"\begin{tabular}{l r@{$\pm$}l r@{$\pm$}l r@{$\pm$}l}")
        ap(r"\toprule")
        ap(r"\textbf{Routing} &"
           r" \multicolumn{2}{c}{\textbf{HEFT (s)}} &"
           r" \multicolumn{2}{c}{\textbf{HEFT-1 (s)}} &"
           r" \multicolumn{2}{c}{\textbf{HEFT-2 (s)}} \\")
        ap(r"\midrule")
        for lb in GRID_LABELS:
            cells = []
            for sched in SCHEDULERS:
                ev  = gev(exp_name, sched, lb)
                mn  = ev.get("mean")
                std = ev.get("std", 0)
                n   = ev.get("n", 30)
                ms_s = fmt(mn)
                ci_s = fmt(_ci95(std, n))
                if mn is not None:
                    if gb is not None and abs(mn - gb) / (gb + 1e-9) < 0.001:
                        ms_s = wc(ms_s)
                    elif cw[sched] is not None and abs(mn - cw[sched]) / (cw[sched] + 1e-9) < 0.001:
                        ms_s = bc(ms_s)
                cells += [ms_s, ci_s]
            ap(f"  {lb} & " + " & ".join(cells) + r" \\")
        ap(r"\midrule")
        best_row = []
        for sched in SCHEDULERS:
            vals = {lb: v for lb, v in cols_ms[sched].items() if v is not None}
            if vals:
                bl = min(vals, key=vals.get)
                best_row.append(r"\textit{" + bl + f" {vals[bl]:.3f}" + r"}")
            else:
                best_row.append("---")
        ap(r"  \textit{Best} & " + " & --- & ".join(best_row) + r" & --- \\")
        ap(r"\bottomrule\end{tabular}")
        ap(r"\caption{$" + str(grid) + r"\times" + str(grid) + r"$ " + dag_label
           + r" --- mean$\pm$95\,\%\,CI makespan (s) over 30 seeds.}")
        ap(r"\end{table}")
        ap(r"")

        # Extra metrics table
        ap(r"\begin{table}[H]\centering\small")
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
                ev = gev(exp_name, sched, lb)
                cells += [
                    fmt(ev.get("mean_hops"), 1),
                    fmt(ev.get("peak_link_util"), 3),
                    fmt(ev.get("mean_xfer_duration"), 1),
                ]
            ap(f"  {lb} & " + " & ".join(cells) + r" \\")
        ap(r"\bottomrule\end{tabular}")
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
    ap(r"\begin{table}[H]\centering")
    ap(r"\begin{tabular}{l r r r}\toprule")
    ap(r"\textbf{Level} & \textbf{Side $L$ (m)} & \textbf{Links} & \textbf{Avg.\ degree} \\\midrule")
    for dl in DENSITIES:
        st = TOPO[dl]
        ap(f"  {dl} & {st['side_len']} & {st['n_links']} & {st['avg_degree']:.1f} \\\\")
    ap(r"\bottomrule\end{tabular}")
    ap(r"\caption{Random network topology statistics (seed~42).}")
    ap(r"\end{table}")
    ap(r"")

    # §3.2 Makespan vs density
    ap(r"\subsection{Makespan vs.\ Density}")
    ap(r"Each point is the best-routing mean makespan $\pm$ 95\,\% CI ($t_{29}=2.045$) over 30 seeds.")
    ap(r"")
    for dag_label in RAND_DAGS:
        dag_cap = "Small DAG (8 tasks, fork-join)" if dag_label == "small" \
                  else "Large DAG (30 tasks, 5-stage pipeline)"
        ap(r"\begin{figure}[H]\centering")
        ap(r"\includegraphics[width=0.85\textwidth]{noint_density_" + dag_label + r".pdf}")
        ap(r"\caption{No-interference: best-routing mean makespan vs.\ avg node degree --- "
           + dag_cap + r". Error bars show 95\,\% CI over 30 seeds.}")
        ap(r"\end{figure}")
        ap(r"")

    # §3.3 Additional metric graphs
    ap(r"\subsection{Additional Metrics vs.\ Density (Large DAG)}")
    ap(r"")
    ap(r"Metrics are taken at the \emph{best} routing scheme for each scheduler at each"
       r" density level, averaged over 30 seeds.")
    ap(r"")
    for fname, cap in [
        ("noint_hops_large",   "Mean hops per transfer for the best routing scheme at each density."),
        ("noint_peaklu_large", "Peak link utilisation (max over all links) for the best routing scheme."),
        ("noint_xferdur_large","Mean transfer duration (s, log scale) for the best routing scheme."),
    ]:
        ap(r"\begin{figure}[H]\centering")
        ap(r"\includegraphics[width=0.85\textwidth]{" + fname + r".pdf}")
        ap(r"\caption{" + cap + r"}")
        ap(r"\end{figure}")
        ap(r"")

    # §3.4 Best-routing summary tables
    for dag_label in RAND_DAGS:
        dag_cap = "Small DAG (8 tasks)" if dag_label == "small" else "Large DAG (30 tasks)"
        ap(r"\subsection{Best Routing Summary --- " + dag_cap + "}")
        ap(r"")
        ap(r"\begin{table}[H]\centering\small")
        ap(r"\begin{tabular}{l r l r@{$\pm$}l r l r@{$\pm$}l r l r@{$\pm$}l r}")
        ap(r"\toprule")
        ap(r"\textbf{Density} & \textbf{Deg.} &"
           r" \multicolumn{4}{c}{\textbf{HEFT}} &"
           r" \multicolumn{4}{c}{\textbf{HEFT-1}} &"
           r" \multicolumn{4}{c}{\textbf{HEFT-2}} \\")
        ap(r"\cmidrule(lr){3-6}\cmidrule(lr){7-10}\cmidrule(lr){11-14}")
        ap(r"& & \textbf{Rt} & \multicolumn{2}{c}{\textbf{ms(s)}} & \textbf{H}"
           r" & \textbf{Rt} & \multicolumn{2}{c}{\textbf{ms(s)}} & \textbf{H}"
           r" & \textbf{Rt} & \multicolumn{2}{c}{\textbf{ms(s)}} & \textbf{H} \\")
        ap(r"\midrule")

        all_ms_dag = []
        for dl in DENSITIES:
            for s in SCHEDULERS:
                _, ev = best_rand(dl, dag_label, s)
                ms = ev.get("mean")
                if ms is not None:
                    all_ms_dag.append(ms)
        gb_dag = min(all_ms_dag) if all_ms_dag else None

        for dl in DENSITIES:
            ad  = TOPO[dl].get("avg_degree", 0)
            row = [f"  {dl} & {ad:.1f}"]
            for sched in SCHEDULERS:
                lb, ev = best_rand(dl, dag_label, sched)
                if lb:
                    mn   = ev.get("mean", 0)
                    std  = ev.get("std", 0)
                    n    = ev.get("n", 30)
                    hops = ev.get("mean_hops", 0)
                    ci   = _ci95(std, n)
                    ms_s = fmt(mn)
                    if gb_dag is not None and abs(mn - gb_dag) / (gb_dag + 1e-9) < 0.001:
                        ms_s = wc(ms_s)
                    row.append(f" & {lb} & {ms_s} & {fmt(ci)} & {hops:.1f}")
                else:
                    row.append(" & --- & --- & --- & ---")
            ap("".join(row) + r" \\")

        ap(r"\bottomrule\end{tabular}")
        ap(r"\caption{" + dag_cap + r" --- best routing per (density, scheduler)."
           r" ms = mean$\pm$95\,\%\,CI; H = mean hops. \win{Bold green}: overall best.}")
        ap(r"\end{table}")
        ap(r"")

    # ── §4 Full random results ────────────────────────────────────────────────
    ap(r"\section{Full Random Network Results}")
    ap(r"")
    ap(r"Mean$\pm$95\,\%\,CI makespan (s), mean hops, and peak link util over 30 seeds."
       r" \win{Bold green}: overall best for that density+DAG. \bad{Red}: worst in column.")
    ap(r"")

    for dag_label in RAND_DAGS:
        dag_cap = "Small DAG (8 tasks)" if dag_label == "small" else "Large DAG (30 tasks)"
        for dl in DENSITIES:
            ad   = TOPO[dl].get("avg_degree", 0)
            side = TOPO[dl].get("side_len", 0)
            ap(r"\subsection{" + dl + r" (avg.\ degree " + f"{ad:.1f}" + r") --- " + dag_cap + r"}")
            ap(r"\begin{table}[H]\centering\small")
            ap(r"\begin{tabular}{l r@{$\pm$}l r r r@{$\pm$}l r r r@{$\pm$}l r r}")
            ap(r"\toprule")
            ap(r"\textbf{Route} &"
               r" \multicolumn{4}{c}{\textbf{HEFT}} &"
               r" \multicolumn{4}{c}{\textbf{HEFT-1}} &"
               r" \multicolumn{4}{c}{\textbf{HEFT-2}} \\")
            ap(r"\cmidrule(lr){2-5}\cmidrule(lr){6-9}\cmidrule(lr){10-13}")
            ap(r"& \multicolumn{2}{c}{\textbf{ms(s)}} & \textbf{H} & \textbf{PLU}"
               r"& \multicolumn{2}{c}{\textbf{ms(s)}} & \textbf{H} & \textbf{PLU}"
               r"& \multicolumn{2}{c}{\textbf{ms(s)}} & \textbf{H} & \textbf{PLU} \\")
            ap(r"\midrule")

            all_ms_r = []
            for s in SCHEDULERS:
                for lb in RAND_LABELS:
                    ms = rev(dl, dag_label, s, lb).get("mean")
                    if ms:
                        all_ms_r.append(ms)
            gb_r = min(all_ms_r) if all_ms_r else None
            cw_r = {}
            for s in SCHEDULERS:
                vals = [rev(dl, dag_label, s, lb).get("mean", 0) for lb in RAND_LABELS]
                cw_r[s] = max(vals) if vals else None

            for lb in RAND_LABELS:
                cells = []
                for sched in SCHEDULERS:
                    ev   = rev(dl, dag_label, sched, lb)
                    mn   = ev.get("mean")
                    std  = ev.get("std", 0)
                    n    = ev.get("n", 30)
                    hops = ev.get("mean_hops")
                    plu  = ev.get("peak_link_util")
                    ms_s = fmt(mn)
                    ci_s = fmt(_ci95(std, n))
                    if mn is not None:
                        if gb_r is not None and abs(mn - gb_r) / (gb_r + 1e-9) < 0.001:
                            ms_s = wc(ms_s)
                        elif cw_r[sched] is not None and abs(mn - cw_r[sched]) / (cw_r[sched] + 1e-9) < 0.001:
                            ms_s = bc(ms_s)
                    cells += [ms_s, ci_s, fmt(hops, 1), fmt(plu, 3)]
                ap(f"  {lb} & " + " & ".join(cells) + r" \\")

            ap(r"\bottomrule\end{tabular}")
            ap(r"\caption{" + dl + r" ($L=" + str(side)
               + r"$\,m) --- " + dag_cap
               + r". ms = mean$\pm$95\,\%\,CI; H = mean hops; PLU = peak link util.}")
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
       r" dominates: transfer costs are negligible without interference.")
    ap(r"")
    ap(r"\subsection{Why GSD/GSD-D Win on the Large DAG}")
    ap(r"")
    ap(r"The extra metrics reveal the mechanism clearly. On the $7\times7$ grid"
       r" large DAG under HEFT-1:")
    ap(r"")
    ap(r"\begin{center}\small")
    ap(r"\begin{tabular}{l r r r r}\toprule")
    ap(r"\textbf{Routing} & \textbf{Makespan (s)} & \textbf{Mean hops}"
       r" & \textbf{Peak link util.} & \textbf{Mean xfer dur.\ (s)} \\\midrule")
    for lb in ["W","S","SH","GS","GO","GSD","GSD-D"]:
        ev  = gev("7x7_large", "heft1", lb)
        ms  = ev.get("mean")
        ap(f"  {lb} & {fmt(ms)} & {fmt(ev.get('mean_hops'),1)} &"
           f" {fmt(ev.get('peak_link_util'),3)} & {fmt(ev.get('mean_xfer_duration'),1)} \\\\")
    ap(r"\bottomrule\end{tabular}")
    ap(r"\end{center}")
    ap(r"")
    ap(r"W, S, and SH all use 1-hop paths but achieve peak link utilisation of"
       r" 0.93, with mean transfer durations of 25--28\,s."
       r" GS and GO use 2.4--2.7 hops on average."
       r" GSD and GSD-D also use 1-hop paths but reduce peak link utilisation"
       r" to 0.77--0.79 and halve the mean transfer duration to 13.7\,s,"
       r" directly explaining the $2\times$ makespan advantage.")
    ap(r"")
    ap(r"\subsection{Comparison to csma\_bianchi Results}")
    ap(r"")
    ap(r"Removing interference collapses the large-DAG makespan from"
       r" 150--927\,s (csma\_bianchi, best routing) to 47--66\,s"
       r" (no interference, best routing) under HEFT-1---a $3$--$14\times$"
       r" reduction. This confirms that the dominant cost"
       r" in the csma\_bianchi experiments was inter-link spectrum contention,"
       r" not intra-link queuing.")
    ap(r"")
    ap(r"\subsection{Reproducing These Results}")
    ap(r"\begin{verbatim}")
    ap(r"cd ncsim/")
    ap(r"python run_no_interference_eval.py      # ~70 min (12 060 runs)")
    ap(r"python compute_noint_augmented.py       # reads existing traces")
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

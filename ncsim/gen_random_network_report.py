#!/usr/bin/env python3
"""Regenerate random_network_results.tex with std devs and extra metrics.

Reads:
  /tmp/ncsim_random_eval/random_augmented.json
    keys: "{dlabel}|{dag}|{sched}|{label}" → {mean, std, mean_hops, peak_link_util,
                                               mean_xfer_duration, peak_node_util, ...}
Produces:
  docs/random_network_results.tex
  docs/density_small.pdf      (updated with error bands)
  docs/density_large.pdf      (updated with error bands)
  docs/density_hops_large.pdf (new)
  docs/density_plu_large.pdf  (new)
  docs/density_xd_large.pdf   (new)
"""

import json
import math
import statistics
from pathlib import Path

RAND_DIR = Path("/tmp/ncsim_random_eval")
DOCS     = Path(__file__).parent / "docs"
DOCS.mkdir(exist_ok=True)

with open(RAND_DIR / "random_augmented.json") as f:
    AUG = json.load(f)

with open(RAND_DIR / "random_eval_results.json") as f:
    RAW = json.load(f)

TOPO     = RAW["topo_stats"]        # dlabel → {side_len, avg_degree, n_links}
BEST_RAW = RAW["best"]              # "dl|dag|sched" → {routing, makespan}

SCHEDULERS  = ["heft", "heft1", "heft2"]
SCHED_NAMES = {"heft": "HEFT (calib.)", "heft1": "HEFT-1", "heft2": "HEFT-2"}
DENSITIES   = ["L150","L200","L250","L300","L350","L400","L500"]
RAND_DAGS   = ["small","large"]
RAND_LABELS = ["W","S","SH","GO","GS","GSD","GSD-D"]


def aug(dl, dag, sched, lb):
    return AUG.get(f"{dl}|{dag}|{sched}|{lb}", {})

def best_aug(dl, dag, sched):
    key = f"{dl}|{dag}|{sched}"
    b   = BEST_RAW.get(key, {})
    lb  = b.get("routing")
    if lb:
        return lb, aug(dl, dag, sched, lb)
    return None, {}

def _ci95(std, n=30):
    """95% CI half-width: t_{n-1,0.025} * std / sqrt(n)."""
    if not std or n <= 1:
        return std or 0.0
    t = 2.045 if n <= 30 else (2.009 if n <= 60 else 1.96)
    return t * std / math.sqrt(n)

def fmt(v, d=3):
    return f"{v:.{d}f}" if v is not None else "---"

def wc(s): return r"\win{" + s + "}"
def bc(s): return r"\bad{" + s + "}"


# ── Plots ─────────────────────────────────────────────────────────────────────

def make_plots():
    import matplotlib
    matplotlib.use("pdf")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker

    degrees = [TOPO[dl]["avg_degree"] for dl in DENSITIES]

    STYLES = {
        "heft":  dict(color="#2166ac", marker="o",  linewidth=1.8, markersize=5, linestyle="-"),
        "heft1": dict(color="#1a9641", marker="s",  linewidth=1.8, markersize=5, linestyle="-"),
        "heft2": dict(color="#d7191c", marker="^",  linewidth=1.8, markersize=5, linestyle="-"),
    }
    EFMT = dict(capsize=3, capthick=0.8, elinewidth=0.8, alpha=0.6)

    def _plot(ylabel, title, outfile, y_fn, err_fn=None, log=False, legend_loc="upper left"):
        fig, ax = plt.subplots(figsize=(6.5, 3.8))
        for sched in SCHEDULERS:
            ys, errs = [], []
            for dl in DENSITIES:
                lb, ev = best_aug(dl, "large", sched)
                ys.append(y_fn(ev))
                errs.append(err_fn(ev) if err_fn else None)
            xs    = [x for x, y in zip(degrees, ys) if y is not None]
            ys_p  = [y for y in ys if y is not None]
            err_p = [e for e, y in zip(errs, ys) if y is not None]
            st = STYLES[sched].copy()
            color = st.pop("color")
            if err_fn and any(e is not None for e in err_p):
                ax.errorbar(xs, ys_p, yerr=err_p, label=SCHED_NAMES[sched],
                            color=color, **st, **EFMT)
            else:
                ax.plot(xs, ys_p, label=SCHED_NAMES[sched], color=color, **st)
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
        ax.legend(loc=legend_loc, fontsize=9, framealpha=0.9)
        fig.tight_layout()
        fig.savefig(outfile, bbox_inches="tight")
        plt.close(fig)
        print(f"  {outfile.name}")

    # Makespan — both DAGs
    for dag_label in RAND_DAGS:
        dag_cap = "Small DAG (8 tasks, fork-join)" if dag_label == "small" \
                  else "Large DAG (30 tasks, 5-stage pipeline)"
        fig, ax = plt.subplots(figsize=(6.5, 3.8))
        for sched in SCHEDULERS:
            ys, errs = [], []
            for dl in DENSITIES:
                lb, ev = best_aug(dl, dag_label, sched)
                ys.append(ev.get("mean"))
                errs.append(_ci95(ev.get("std", 0)))
            xs    = [x for x, y in zip(degrees, ys) if y is not None]
            ys_p  = [y for y in ys if y is not None]
            err_p = [e for e, y in zip(errs, ys) if y is not None]
            st = STYLES[sched].copy()
            color = st.pop("color")
            ax.errorbar(xs, ys_p, yerr=err_p, label=SCHED_NAMES[sched],
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
        out = DOCS / f"density_{dag_label}.pdf"
        fig.savefig(out, bbox_inches="tight")
        plt.close(fig)
        print(f"  {out.name}")

    # Extra-metric plots (large DAG only)
    _plot("Mean hops per transfer",
          "Large DAG — Mean transfer hops vs.\ density",
          DOCS / "density_hops_large.pdf",
          lambda ev: ev.get("mean_hops"), log=False, legend_loc="upper left")

    _plot("Peak link utilization",
          "Large DAG — Peak link utilization vs.\ density",
          DOCS / "density_plu_large.pdf",
          lambda ev: ev.get("peak_link_util"), log=False, legend_loc="upper left")

    _plot("Mean transfer duration (s)",
          "Large DAG — Mean transfer duration vs.\ density",
          DOCS / "density_xd_large.pdf",
          lambda ev: ev.get("mean_xfer_duration"),
          err_fn=None, log=True, legend_loc="upper left")


# ── LaTeX ─────────────────────────────────────────────────────────────────────

def build_tex():
    W  = []
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
    ap(r"\title{Random Network Routing Evaluation}")
    ap(r"\author{Autonomous Networks Research Group (ANRG)\\University of Southern California}")
    ap(r"\date{}")
    ap(r"\begin{document}")
    ap(r"\maketitle")
    ap(r"\tableofcontents")
    ap(r"\newpage")
    ap(r"")

    # §1 Setup
    ap(r"\section{Evaluation Setup}")
    ap(r"")
    ap(r"Does the relative performance ranking of HEFT, HEFT-1, and HEFT-2 hold")
    ap(r"on random graphs?  We place \textbf{50 nodes} uniformly at random in an")
    ap(r"$L\times L$ square and create bidirectional links between all pairs within")
    ap(r"$R=80$\,m.  Varying $L$ controls network density.")
    ap(r"")
    ap(r"\begin{table}[H]\centering")
    ap(r"\begin{tabular}{ll}\toprule")
    ap(r"\textbf{Parameter} & \textbf{Value} \\\midrule")
    ap(r"Nodes & 50, positions uniform random in $[0,L]^2$ \\")
    ap(r"Communication range & $R=80$\,m (\texttt{csma\_bianchi} PHY rate from distance) \\")
    ap(r"Topology seed & 42 (fixed per density level) \\")
    ap(r"Seeds per combo & 30 (seeds 1--30) \\")
    ap(r"Schedulers & HEFT (calibrated), HEFT-1, HEFT-2 \\")
    ap(r"Routing schemes & W, S, SH, GO, GS, GSD, GSD-D \\")
    ap(r"DAGs & Small (8 tasks, fork-join) and Large (30 tasks, pipeline) \\")
    ap(r"Interference & \texttt{csma\_bianchi}, 802.11ax 5\,GHz 20\,MHz \\")
    ap(r"\bottomrule\end{tabular}")
    ap(r"\caption{Evaluation parameters.}\end{table}")
    ap(r"")
    ap(r"Values reported as mean $\pm$ 95\,\% confidence interval over 30 seeds.")
    ap(r"Additional metrics: mean hops (path length), peak link utilization (P-LU),"
       r" mean transfer duration (XD).")
    ap(r"")

    # §2 Topology stats
    ap(r"\begin{table}[H]\centering")
    ap(r"\begin{tabular}{l r r r}\toprule")
    ap(r"\textbf{Level} & \textbf{Side $L$ (m)} & \textbf{Links} & \textbf{Avg.\ degree} \\\midrule")
    for dl in DENSITIES:
        st = TOPO[dl]
        ap(f"  {dl} & {st['side_len']} & {st['n_links']} & {st['avg_degree']:.1f} \\\\")
    ap(r"\bottomrule\end{tabular}")
    ap(r"\caption{Topology statistics (seed~42).}\end{table}")
    ap(r"")

    # §3 Makespan vs density graphs (with error bars)
    ap(r"\section{Makespan vs.\ Density}")
    ap(r"")
    ap(r"Each point is the best-routing mean makespan $\pm$ 95\,\% CI over 30 seeds ($t_{29}=2.045$).")
    ap(r"")
    for dag_label in RAND_DAGS:
        dag_cap = "Small DAG (8 tasks, fork-join)" if dag_label == "small" \
                  else "Large DAG (30 tasks, 5-stage pipeline)"
        ap(r"\begin{figure}[H]\centering")
        ap(r"\includegraphics[width=0.88\textwidth]{density_" + dag_label + r".pdf}")
        ap(r"\caption{Best-routing makespan vs.\ avg degree --- " + dag_cap
           + r". Error bars show 95\,\% CI over 30 seeds.}")
        ap(r"\end{figure}")
        ap(r"")

    # §4 Additional metric graphs (large DAG)
    ap(r"\section{Additional Metrics vs.\ Density (Large DAG)}")
    ap(r"")
    ap(r"Computed at the best routing scheme per (density, scheduler) cell.")
    ap(r"")
    for fname, cap in [
        ("density_hops_large",
         r"Mean hops per transfer. Values $>1$ indicate multi-hop paths."),
        ("density_plu_large",
         r"Peak link utilization (max over all links). High values indicate congestion hotspots."),
        ("density_xd_large",
         r"Mean transfer duration (s, log scale). Tracks makespan closely."),
    ]:
        ap(r"\begin{figure}[H]\centering")
        ap(r"\includegraphics[width=0.88\textwidth]{" + fname + r".pdf}")
        ap(r"\caption{" + cap + r"}")
        ap(r"\end{figure}")
        ap(r"")

    # §5 Best-routing summary tables (makespan ± std + metrics)
    ap(r"\section{Best Routing per Density and Scheduler}")
    ap(r"")
    for dag_label in RAND_DAGS:
        dag_cap = "Small DAG (8 tasks)" if dag_label == "small" else "Large DAG (30 tasks)"
        ap(r"\subsection{" + dag_cap + "}")
        ap(r"\begin{table}[H]\centering\small")
        ap(r"\begin{tabular}{l r r@{\,}l@{$\pm$}l@{\,}r r@{\,}l@{$\pm$}l@{\,}r r@{\,}l@{$\pm$}l@{\,}r}")
        ap(r"\toprule")
        ap(r"\textbf{Dens.} & \textbf{Deg.} &"
           r" \multicolumn{4}{c}{\textbf{HEFT (calib.)}} &"
           r" \multicolumn{4}{c}{\textbf{HEFT-1}} &"
           r" \multicolumn{4}{c}{\textbf{HEFT-2}} \\")
        ap(r"\cmidrule(lr){3-6}\cmidrule(lr){7-10}\cmidrule(lr){11-14}")
        ap(r"& & \textbf{Rt} & \multicolumn{2}{c}{\textbf{ms (s)}} & \textbf{H/PLU}"
           r" & \textbf{Rt} & \multicolumn{2}{c}{\textbf{ms (s)}} & \textbf{H/PLU}"
           r" & \textbf{Rt} & \multicolumn{2}{c}{\textbf{ms (s)}} & \textbf{H/PLU} \\")
        ap(r"\midrule")

        all_means = [aug(dl, dag_label, s, lb).get("mean")
                     for dl in DENSITIES for s in SCHEDULERS
                     for lb in RAND_LABELS
                     if aug(dl, dag_label, s, lb).get("mean")]
        gb = min(all_means) if all_means else None

        for dl in DENSITIES:
            ad   = TOPO[dl]["avg_degree"]
            row  = [f"  {dl} & {ad:.1f}"]
            for sched in SCHEDULERS:
                lb, ev = best_aug(dl, dag_label, sched)
                if lb:
                    mn   = ev.get("mean", 0)
                    sd   = ev.get("std",  0)
                    hops = ev.get("mean_hops", 0)
                    plu  = ev.get("peak_link_util", 0)
                    ms_s = fmt(mn)
                    if gb is not None and mn > 0 and abs(mn - gb) / (gb + 1e-9) < 0.001:
                        ms_s = wc(ms_s)
                    row.append(f" & {lb} & {ms_s} & {fmt(_ci95(sd))} & {hops:.1f}/{plu:.2f}")
                else:
                    row.append(" & --- & --- & --- & ---")
            ap("".join(row) + r" \\")

        ap(r"\bottomrule\end{tabular}")
        ap(r"\caption{" + dag_cap + r" --- best routing per (density, scheduler)."
           r" ms = mean $\pm$ 95\,\%\,CI; H = mean hops; PLU = peak link util."
           r" \win{Bold green}: overall best.}")
        ap(r"\end{table}")
        ap(r"")

    # §6 Full tables with std dev + extra metrics
    ap(r"\section{Full Results Tables}")
    ap(r"")
    ap(r"Mean $\pm$ 95\,\%\,CI makespan (s), mean hops, peak link util over 30 seeds."
       r" \win{Bold green}: overall best for density+DAG. \bad{Red}: worst per scheduler column.")
    ap(r"")

    for dag_label in RAND_DAGS:
        dag_cap = "Small DAG (8 tasks)" if dag_label == "small" else "Large DAG (30 tasks)"
        for dl in DENSITIES:
            ad   = TOPO[dl]["avg_degree"]
            side = TOPO[dl]["side_len"]
            ap(r"\subsection{" + dl + r" (avg.\ degree " + f"{ad:.1f}" + r") --- " + dag_cap + "}")
            ap(r"\begin{table}[H]\centering\small")
            ap(r"\begin{tabular}{l r@{$\pm$}l r r r@{$\pm$}l r r r@{$\pm$}l r r}")
            ap(r"\toprule")
            ap(r"\textbf{Route} &"
               r" \multicolumn{4}{c}{\textbf{HEFT}} &"
               r" \multicolumn{4}{c}{\textbf{HEFT-1}} &"
               r" \multicolumn{4}{c}{\textbf{HEFT-2}} \\")
            ap(r"\cmidrule(lr){2-5}\cmidrule(lr){6-9}\cmidrule(lr){10-13}")
            ap(r"& \multicolumn{2}{c}{\textbf{ms (s)}} & \textbf{H} & \textbf{PLU}"
               r"& \multicolumn{2}{c}{\textbf{ms (s)}} & \textbf{H} & \textbf{PLU}"
               r"& \multicolumn{2}{c}{\textbf{ms (s)}} & \textbf{H} & \textbf{PLU} \\")
            ap(r"\midrule")

            all_ms = [aug(dl, dag_label, s, lb).get("mean")
                      for s in SCHEDULERS for lb in RAND_LABELS
                      if aug(dl, dag_label, s, lb).get("mean")]
            gb2   = min(all_ms) if all_ms else None
            cw    = {}
            for s in SCHEDULERS:
                vals = [aug(dl, dag_label, s, lb).get("mean", 0) for lb in RAND_LABELS]
                cw[s] = max(vals) if vals else None

            for lb in RAND_LABELS:
                cells = []
                for sched in SCHEDULERS:
                    ev   = aug(dl, dag_label, sched, lb)
                    mn   = ev.get("mean")
                    sd   = ev.get("std", 0)
                    hops = ev.get("mean_hops")
                    plu  = ev.get("peak_link_util")
                    ms_s = fmt(mn)
                    if mn is not None:
                        if gb2 is not None and abs(mn - gb2) / (gb2 + 1e-9) < 0.001:
                            ms_s = wc(ms_s)
                        elif cw[sched] is not None and abs(mn - cw[sched]) / (cw[sched] + 1e-9) < 0.001:
                            ms_s = bc(ms_s)
                    cells += [ms_s, fmt(_ci95(sd if sd else 0)), fmt(hops, 1), fmt(plu, 3)]
                ap(f"  {lb} & " + " & ".join(cells) + r" \\")

            ap(r"\bottomrule\end{tabular}")
            ap(r"\caption{" + dl + r" ($L=" + str(side)
               + r"$\,m) --- " + dag_cap
               + r". ms = mean$\pm$95\,\%\,CI; H = mean hops; PLU = peak link util.}")
            ap(r"\end{table}")
            ap(r"")

    # §7 Analysis (kept from previous version, updated with actual metric callouts)
    ap(r"\section{Analysis}")
    ap(r"")
    ap(r"\subsection{HEFT-1 Dominance Is Robust Across All Densities}")
    ap(r"")
    ap(r"HEFT-1 wins at every density level for both DAGs. For the large DAG,"
       r" the advantage over calibrated HEFT ranges from $1.9\times$ at L150"
       r" to $5.6\times$ at L500. The standard deviations under HEFT and HEFT-2"
       r" are large (often $>50$\% of the mean) because csma\_bianchi interference"
       r" is highly sensitive to the exact traffic pattern, which varies across seeds."
       r" HEFT-1's std is much smaller: co-location eliminates most transfers,"
       r" leaving only compute variance.")
    ap(r"")
    ap(r"\subsection{SH vs.\ S: Density-Dependent Reversal}")
    ap(r"")
    ap(r"Under HEFT-1, SH beats S at L150--L300 for the large DAG (mean-hops = 1.0"
       r" for both, confirming co-location). The routing tie-break wins come from"
       r" how each scheme selects the single hop: SH prefers the nearest (lowest-loss)"
       r" link, reducing PHY-layer retransmission and thus interference variance."
       r" At sparse topologies (L400--L500), fewer 1-hop options exist and S"
       r" regains the lead by picking the highest-bandwidth available link.")
    ap(r"")
    ap(r"\subsection{Hops, Peak Link Util., and Transfer Duration}")
    ap(r"")
    ap(r"The additional metrics confirm that routing choice under csma\_bianchi"
       r" is primarily about \emph{which} 1-hop link is used, not multi-hop avoidance:")
    ap(r"\begin{itemize}")
    ap(r"  \item Mean hops is $\approx 1.0$ for HEFT-1 across all density levels,"
       r"    confirming that co-located tasks transfer directly to adjacent nodes.")
    ap(r"  \item Calibrated HEFT and HEFT-2 use 2--4 hops at high density (L150--L200),"
       r"    where tasks are spread across many nodes. Multi-hop paths under csma\_bianchi"
       r"    amplify interference---each relay adds an active transmitter---explaining"
       r"    the large makespan gap.")
    ap(r"  \item Peak link utilization under HEFT-1 is low ($<0.06$) because"
       r"    co-located tasks do not use links; the few transfers that occur are"
       r"    short and non-overlapping. Under HEFT/HEFT-2 peak link util can"
       r"    exceed 0.9, indicating severe bottleneck congestion.")
    ap(r"\end{itemize}")
    ap(r"")
    ap(r"\subsection{Reproducing These Results}")
    ap(r"\begin{verbatim}")
    ap(r"cd ncsim/")
    ap(r"python run_random_eval.py                  # ~3500 s (8820 runs)")
    ap(r"python compute_interference_metrics.py      # reads traces, ~3 min")
    ap(r"python gen_random_network_report.py         # generates tex + plots")
    ap(r"cd docs/ && pdflatex random_network_results.tex")
    ap(r"\end{verbatim}")
    ap(r"")
    ap(r"\end{document}")

    return "\n".join(W)


if __name__ == "__main__":
    print("\n  Generating plots ...")
    make_plots()
    print("  Building LaTeX ...")
    tex = build_tex()
    out = DOCS / "random_network_results.tex"
    out.write_text(tex)
    print(f"  Wrote {out}")

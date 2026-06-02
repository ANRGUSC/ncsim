"""Regenerate the three density-vs-degree figures used in the paper with
x-axis going low-to-high (sparse on the left, dense on the right).

Hops and peak-link-utilization figures (density_hops_large.pdf,
density_plu_large.pdf) are computed from the per-seed JSON produced by
``run_random_eval.py`` (committed at ``dataset/random_eval_results.json``),
including 95% CI error bars. The no-interference baseline figure
(noint_density_large.pdf) is computed from the per-seed makespan samples in
``dataset/no_interference_results.json`` (produced by
``run_no_interference_eval.py``), also with 95% CI error bars.

Outputs go to ncsim/docs/ to overwrite the figures the paper references via
\\graphicspath{{../}}.
"""
from __future__ import annotations
import json
import math
import os
import statistics

import matplotlib

matplotlib.use("pdf")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

OUT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET = os.path.join(OUT, "paper-milcom26", "dataset") \
    if os.path.basename(OUT) == "docs" \
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dataset")
RANDOM_JSON = os.path.join(DATASET, "random_eval_results.json")
NOINT_JSON = os.path.join(DATASET, "no_interference_results.json")

Z95 = 1.96  # CI half-width = Z95 * std / sqrt(n)
SCHED_SERIES = [("HEFT-1", "heft1"), ("HEFT-2", "heft2")]


def _ci95(samples):
    n = len(samples)
    if n < 2:
        return 0.0
    return Z95 * statistics.stdev(samples) / math.sqrt(n)


def load_density_metrics(path):
    """Build (degrees, hops, hops_ci, plu, plu_ci) for the large DAG.

    For each density level and scheduler, use the best routing scheme (lowest
    mean makespan) and report that scheme's per-seed hops / peak-link-util as
    mean +- 95% CI. Densities are ordered sparse -> dense (ascending degree).
    """
    with open(path) as f:
        d = json.load(f)
    topo, best, perseed = d["topo_stats"], d["best"], d["perseed"]

    dens = sorted(topo, key=lambda dl: topo[dl]["avg_degree"])
    degrees = [round(topo[dl]["avg_degree"], 1) for dl in dens]

    hops, hops_ci, plu, plu_ci = {}, {}, {}, {}
    for label, sk in SCHED_SERIES:
        hv, hc, pv, pc = [], [], [], []
        for dl in dens:
            br = best[f"{dl}|large|{sk}"]["routing"]
            cell = perseed[f"{dl}|large|{sk}|{br}"]
            h, p = cell["hops"], cell["plu"]
            hv.append(sum(h) / len(h)); hc.append(_ci95(h))
            pv.append(sum(p) / len(p)); pc.append(_ci95(p))
        hops[label], hops_ci[label] = hv, hc
        plu[label], plu_ci[label] = pv, pc
    return degrees, hops, hops_ci, plu, plu_ci


def load_noint_metrics(path):
    """Build (degrees, noint, noint_ci) for the large DAG, no interference.

    For each density level and scheduler, use the best routing scheme (lowest
    mean makespan) and report that scheme's per-seed makespan as mean +- 95%
    CI. Densities are ordered sparse -> dense (ascending degree).
    """
    with open(path) as f:
        d = json.load(f)
    topo, best, perseed = d["rand_topo"], d["rand_best"], d["rand_perseed"]

    dens = sorted(topo, key=lambda dl: topo[dl]["avg_degree"])
    degrees = [round(topo[dl]["avg_degree"], 1) for dl in dens]

    noint, noint_ci = {}, {}
    for label, sk in SCHED_SERIES:
        mv, mc = [], []
        for dl in dens:
            br = best[f"{dl}|large|{sk}"]["routing"]
            ms = perseed[f"{dl}|large|{sk}|{br}"]["ms"]
            mv.append(sum(ms) / len(ms)); mc.append(_ci95(ms))
        noint[label], noint_ci[label] = mv, mc
    return degrees, noint, noint_ci


DEGREES, HOPS_LARGE, HOPS_LARGE_CI95, PLU_LARGE, PLU_LARGE_CI95 = \
    load_density_metrics(RANDOM_JSON)

# No-interference baseline: best-routing mean makespan, large DAG, with
# 95% CI from the per-seed makespan samples cached in no_interference_results.json.
_NOINT_DEG, NOINT_LARGE, NOINT_LARGE_CI95 = load_noint_metrics(NOINT_JSON)

STYLES = {
    "HEFT-1": dict(color="#1a9641", marker="s", linestyle="-",
                   linewidth=1.8, markersize=6),
    "HEFT-2": dict(color="#d7191c", marker="^", linestyle="-",
                   linewidth=1.8, markersize=6),
}


def make_plot(data, ylabel, title, outfile, log=False, legend_loc="best",
              errors=None):
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    for label, vals in data.items():
        if errors and label in errors:
            ax.errorbar(DEGREES, vals, yerr=errors[label], label=label,
                        capsize=3, elinewidth=1.0, **STYLES[label])
        else:
            ax.plot(DEGREES, vals, label=label, **STYLES[label])

    if log:
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(
            ticker.FuncFormatter(lambda v, _: f"{v:g}"))

    ax.set_xlabel("Average node degree (higher = denser)", fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_title(title, fontsize=12, pad=8)
    ax.set_xticks(DEGREES)
    ax.set_xticklabels([f"{d}" for d in DEGREES], fontsize=9)
    ax.grid(True, which="major", linestyle="--", linewidth=0.5, alpha=0.7)
    ax.grid(True, which="minor", linestyle=":", linewidth=0.3, alpha=0.4)
    ax.legend(loc=legend_loc, fontsize=9, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(outfile, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {outfile}")


make_plot(
    HOPS_LARGE,
    ylabel="Mean hops per transfer",
    title="Large DAG (30 tasks, 5-stage pipeline)",
    outfile=os.path.join(OUT, "density_hops_large.pdf"),
    legend_loc="upper right",
    errors=HOPS_LARGE_CI95,
)

make_plot(
    PLU_LARGE,
    ylabel="Peak link utilization",
    title="Large DAG (30 tasks, 5-stage pipeline)",
    outfile=os.path.join(OUT, "density_plu_large.pdf"),
    legend_loc="center right",
    errors=PLU_LARGE_CI95,
)

make_plot(
    NOINT_LARGE,
    ylabel="Best mean makespan (s, log scale)",
    title="Large DAG (30 tasks, 5-stage pipeline), no interference",
    outfile=os.path.join(OUT, "noint_density_large.pdf"),
    log=True,
    legend_loc="upper right",
    errors=NOINT_LARGE_CI95,
)

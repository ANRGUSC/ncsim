"""Regenerate the three density-vs-degree figures used in the paper with
x-axis going low-to-high (sparse on the left, dense on the right).

The original cache at /tmp/ncsim_random_eval is gone, so we extract the
numbers directly from the published .tex tables that are checked in to the
repo. Outputs go to ncsim/docs/ to overwrite the figures that the paper
references via \\graphicspath{{../}}.
"""
from __future__ import annotations
import os
import matplotlib

matplotlib.use("pdf")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

OUT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Sorted ascending so the x-axis runs sparse -> dense, left -> right.
DEGREES = [3.7, 5.8, 6.7, 8.7, 12.4, 17.1, 24.0]

# All data tables below come from
#   ncsim/docs/random_network_results.tex   (interference cases)
#   ncsim/docs/no_interference_results.tex  (no-interference baseline)
# and were ordered ascending in degree.

# Mean hops per inter-task transfer, large DAG, best routing per cell.
HOPS_LARGE = {
    "HEFT-1": [1.3, 1.3, 1.1, 1.0, 1.1, 1.0, 1.0],
    "HEFT-2": [5.3, 2.6, 2.7, 2.2, 2.1, 1.3, 1.2],
}

# Peak link utilization, large DAG, best routing per cell.
PLU_LARGE = {
    "HEFT-1": [0.09, 0.09, 0.09, 0.04, 0.06, 0.03, 0.05],
    "HEFT-2": [0.01, 0.02, 0.01, 0.01, 0.01, 0.03, 0.04],
}

# No-interference baseline: best-routing mean makespan, large DAG.
NOINT_LARGE = {
    "HEFT-1": [ 57.1,  47.5,  47.5, 65.7, 55.3,  61.7,  61.7],
    "HEFT-2": [121.6, 121.6, 120.3, 66.8, 78.0, 102.0, 102.0],
}

# 95% CI half-widths for NOINT_LARGE (no-interference, n=30 seeds).
# Source: no_interference_results.tex best-routing-summary table.
NOINT_LARGE_CI95 = {
    "HEFT-1": [2.433, 0.485, 0.477, 4.227, 0.992, 0.000, 0.000],
    "HEFT-2": [4.585, 5.206, 5.098, 6.055, 8.457, 0.000, 0.000],
}

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
)

make_plot(
    PLU_LARGE,
    ylabel="Peak link utilization",
    title="Large DAG (30 tasks, 5-stage pipeline)",
    outfile=os.path.join(OUT, "density_plu_large.pdf"),
    legend_loc="center right",
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

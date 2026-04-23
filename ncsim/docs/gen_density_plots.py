"""Generate density-vs-makespan line plots for random_network_results.tex."""
import matplotlib
matplotlib.use("pdf")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import os

OUT = os.path.dirname(os.path.abspath(__file__))

DEGREES = [24.0, 17.1, 12.4, 8.7, 6.7, 5.8, 3.7]

SMALL = {
    "HEFT (calib.)": [31.584, 29.712, 32.688, 31.009, 75.816, 45.980, 247.260],
    "HEFT-1":        [21.594, 27.861, 23.513, 24.388, 24.179, 22.909,  20.926],
    "HEFT-2":        [34.633, 35.664, 37.796, 28.641, 71.486, 54.861, 174.510],
}

LARGE = {
    "HEFT (calib.)": [287.323,  501.174, 1344.548, 2063.615, 1939.104, 2426.675, 3914.460],
    "HEFT-1":        [149.899,  391.400,  449.477,  405.276,  362.181,  927.488,  694.194],
    "HEFT-2":        [308.494,  472.856, 1336.595, 2140.430, 2060.780, 2388.566, 5068.567],
}

STYLES = {
    "HEFT (calib.)": dict(color="#2166ac", marker="o",  linestyle="-",  linewidth=1.8, markersize=6),
    "HEFT-1":        dict(color="#1a9641", marker="s",  linestyle="-",  linewidth=1.8, markersize=6),
    "HEFT-2":        dict(color="#d7191c", marker="^",  linestyle="-",  linewidth=1.8, markersize=6),
}

def make_plot(data, title, outfile):
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    for label, vals in data.items():
        ax.plot(DEGREES, vals, label=label, **STYLES[label])

    ax.set_yscale("log")
    ax.invert_xaxis()          # denser on the left (higher degree)
    ax.set_xlabel("Average node degree (higher = denser)", fontsize=11)
    ax.set_ylabel("Mean makespan (s, log scale)", fontsize=11)
    ax.set_title(title, fontsize=12, pad=8)
    ax.set_xticks(DEGREES)
    ax.set_xticklabels([str(d) for d in DEGREES], fontsize=9)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(
        lambda x, _: f"{x:g}"))
    ax.grid(True, which="major", linestyle="--", linewidth=0.5, alpha=0.7)
    ax.grid(True, which="minor", linestyle=":",  linewidth=0.3, alpha=0.4)
    ax.legend(loc="upper right", fontsize=9, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(outfile, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {outfile}")

make_plot(SMALL, "Small DAG (8 tasks, fork-join)",
          os.path.join(OUT, "density_small.pdf"))
make_plot(LARGE, "Large DAG (30 tasks, 5-stage pipeline)",
          os.path.join(OUT, "density_large.pdf"))

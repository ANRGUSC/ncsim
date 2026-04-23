"""Generate grid-size-vs-makespan line plots for eval_results.tex."""
import matplotlib
matplotlib.use("pdf")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import os

OUT = os.path.dirname(os.path.abspath(__file__))

# X-axis: number of nodes in the grid (4x4=16, 7x7=49)
NODES = [16, 49]
XLABELS = ["4×4\n(16 nodes)", "7×7\n(49 nodes)"]

# Best makespan per scheduler per grid size (best over all routing schemes)
SMALL = {
    "HEFT (calib.)": [ 91.134,  93.819],
    "HEFT-1":        [ 18.035,  19.779],
    "HEFT-2":        [ 91.134,  93.696],
}

LARGE = {
    "HEFT (calib.)": [ 855.880, 2487.685],
    "HEFT-1":        [ 292.091,  542.189],
    "HEFT-2":        [ 855.880, 2497.366],
}

# Best routing label annotations
SMALL_LABELS = {
    "HEFT (calib.)": ["GSD-D", "SH"],
    "HEFT-1":        ["GSD-D", "GSD-D"],
    "HEFT-2":        ["GSD-D", "S"],
}
LARGE_LABELS = {
    "HEFT (calib.)": ["GSD", "S"],
    "HEFT-1":        ["GS/GO", "GO"],
    "HEFT-2":        ["GSD", "S"],
}

STYLES = {
    "HEFT (calib.)": dict(color="#2166ac", marker="o",  linestyle="-",  linewidth=1.8, markersize=7),
    "HEFT-1":        dict(color="#1a9641", marker="s",  linestyle="-",  linewidth=1.8, markersize=7),
    "HEFT-2":        dict(color="#d7191c", marker="^",  linestyle="-",  linewidth=1.8, markersize=7),
}

def make_plot(data, label_map, title, outfile):
    fig, ax = plt.subplots(figsize=(5.5, 3.8))

    x = [0, 1]   # positions for the two grid sizes
    for sched, vals in data.items():
        ax.plot(x, vals, label=sched, **STYLES[sched])
        # annotate each point with best routing scheme
        for xi, (yi, route) in enumerate(zip(vals, label_map[sched])):
            va = "bottom" if sched == "HEFT-1" else "top"
            offset = 1.06 if va == "bottom" else 0.94
            ax.annotate(route,
                        xy=(xi, yi),
                        xytext=(xi, yi * offset),
                        fontsize=7,
                        ha="center", va=va,
                        color=STYLES[sched]["color"])

    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels(XLABELS, fontsize=10)
    ax.set_xlabel("Grid size", fontsize=11)
    ax.set_ylabel("Best mean makespan (s, log scale)", fontsize=11)
    ax.set_title(title, fontsize=12, pad=8)
    ax.set_xlim(-0.3, 1.3)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.grid(True, which="major", linestyle="--", linewidth=0.5, alpha=0.7)
    ax.grid(True, which="minor", linestyle=":",  linewidth=0.3, alpha=0.4)
    ax.legend(loc="upper left", fontsize=9, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(outfile, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {outfile}")

make_plot(SMALL, SMALL_LABELS,
          "Small DAG (8 tasks, fork-join)",
          os.path.join(OUT, "grid_small.pdf"))

make_plot(LARGE, LARGE_LABELS,
          "Large DAG (30/60 tasks, pipeline)",
          os.path.join(OUT, "grid_large.pdf"))

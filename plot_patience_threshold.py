"""
Patience-threshold figure: makespan/oracle vs single-failure outage
duration, over biting cells of the duration sweep (results-archive).

Usage:
    python plot_patience_threshold.py [--output figures-extra]
"""

import argparse
import gzip
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from plot_repair_experiments import EDGE, POLICY_STYLE, TEXT_PRIMARY, style_axis

DURS = ("0.125", "0.25", "0.5", "1.0", "2.0")


def geo(values):
    return math.exp(sum(math.log(v) for v in values) / len(values))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="figures-extra")
    parser.add_argument("--archive", default="results-archive")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    series = {p: [] for p in POLICY_STYLE}
    for d in DURS:
        path = Path(args.archive) / f"sweep_dur_{d}.records.jsonl.gz"
        recs = [json.loads(l) for l in gzip.open(path, "rt")]
        oracle, runs = {}, {}
        for r in recs:
            k = (r["instance"], r["ccr"])
            if r["policy"] == "oracle":
                oracle[k] = r["makespan"]
            else:
                runs.setdefault(r["policy"], {})[k] = r
        bite = {k for k, r in runs["wait"].items()
                if r["makespan"] > 1.001 * r["m0"]}
        for p in POLICY_STYLE:
            series[p].append(geo([runs[p][k]["makespan"] / oracle[k]
                                  for k in bite]))

    x = [float(d) for d in DURS]
    fig, ax = plt.subplots(figsize=(3.5, 2.3), dpi=200)
    for p, style in POLICY_STYLE.items():
        ax.plot(x, series[p], color=style["color"], linewidth=0.9,
                linestyle=style["ls"], marker=style["marker"], markersize=2.8,
                markerfacecolor="white", markeredgewidth=0.7, label=p,
                zorder=3)
    ax.axhline(1.0, color=EDGE, linewidth=0.5, linestyle=(0, (4, 3)), zorder=1)
    ax.set_xscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{v:g}" for v in x], fontsize=7)
    ax.minorticks_off()
    ax.set_xlabel("outage duration / $M_0$", fontsize=8, color=TEXT_PRIMARY)
    ax.set_ylabel("Makespan / oracle", fontsize=8, color=TEXT_PRIMARY)
    ax.tick_params(axis="y", labelsize=7)
    style_axis(ax)
    ax.axvspan(0.11, 0.25, color="#e9e9e6", alpha=0.55, zorder=0)
    ax.annotate("patience\nzone", (0.167, 1.42), fontsize=6.5, ha="center",
                color="#444444")
    ax.set_xlim(0.11, 2.35)
    ax.legend(frameon=False, fontsize=7, loc="upper left",
              bbox_to_anchor=(0.28, 0.98), handlelength=1.8, labelspacing=0.3)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(output / f"patience_threshold.{ext}", bbox_inches="tight")
    print(f"figures -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

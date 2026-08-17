"""
Disruption-trace gallery: one panel per generator showing link state over
time for every radio pair of one representative instance, so the four
processes' correlation structures are visible at a glance.

Usage:
    python plot_trace_gallery.py --output DIR [--structure out_tree]
        [--seed 420000] [--ccr 1.0] [--horizon 2.0]
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "STIXGeneral", "DejaVu Serif"],
    "mathtext.fontset": "stix",
    "axes.linewidth": 0.6,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})
import matplotlib.pyplot as plt

from ncsim.experiments.runner import build_trace, undisrupted_makespan
from ncsim.experiments.workloads import (
    ALL_STRUCTURES,
    make_workload,
    scale_network_to_ccr,
    spatial_network,
)
from ncsim.models.disruptions import DisruptionType
from ncsim.models.failure_traces import radio_pairs

GENERATORS = ("single", "flapping", "mobility", "jamming")
LABELS = {"single": "Single failure", "flapping": "Flapping (GE)",
          "mobility": "Mobility", "jamming": "Jamming"}
DOWN = "#3a3a3a"
DEGRADED = "#bdbdbd"
TEXT = "#1a1a1a"


def pair_intervals(events, pair, horizon):
    """(state, start, end) intervals for one undirected pair.

    Walks the pair's events in time order: DOWN opens a down interval
    (closed by its duration or the next RECOVERY), DEGRADE opens a degraded
    one, RECOVERY returns the link to full bandwidth.
    """
    link_id = f"l_{pair[0]}_{pair[1]}"
    own = sorted((e for e in events if e.target_id == link_id),
                 key=lambda e: e.time)
    intervals, state, since, until = [], None, 0.0, None
    for event in own:
        t = min(event.time, horizon)
        if state is not None and t > since:
            intervals.append((state, since, t))
        if event.disruption_type == DisruptionType.LINK_DOWN:
            state, since = "down", t
            until = (t + event.duration) if event.duration else None
        elif event.disruption_type == DisruptionType.LINK_DEGRADE:
            state, since, until = "degraded", t, None
        else:  # RECOVERY
            state, until = None, None
        if until is not None and until <= horizon:
            intervals.append((state, since, until))
            state, until = None, None
    if state is not None:
        intervals.append((state, since, horizon))
    return intervals


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--structure", default="out_tree",
                        choices=list(ALL_STRUCTURES))
    parser.add_argument("--seed", type=int, default=420000)
    parser.add_argument("--nodes", type=int, default=5)
    parser.add_argument("--ccr", type=float, default=1.0)
    parser.add_argument("--horizon", type=float, default=2.0,
                        help="Window shown, in multiples of M0")
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    dag = make_workload(args.structure, seed=args.seed)
    network = spatial_network(args.nodes, seed=args.seed)
    scale_network_to_ccr(network, dag, args.ccr)
    m0 = undisrupted_makespan(network, dag)
    pairs = sorted(tuple(sorted(k))
                   for k in radio_pairs(network) if len(k) == 2)

    fig, axes = plt.subplots(1, len(GENERATORS), figsize=(7.0, 1.75),
                             dpi=200, sharey=True)
    for ax, generator in zip(axes, GENERATORS):
        trace = build_trace(generator, network, m0, seed=args.seed)
        for row, pair in enumerate(pairs):
            for state, start, end in pair_intervals(
                    trace, pair, args.horizon * m0):
                ax.barh(row, (end - start) / m0, left=start / m0,
                        height=0.72,
                        color=DOWN if state == "down" else DEGRADED,
                        linewidth=0, zorder=3)
        ax.set_xlim(0, args.horizon)
        ax.set_ylim(-0.6, len(pairs) - 0.4)
        ax.set_title(LABELS[generator], fontsize=8, color=TEXT)
        ax.set_xlabel("time / $M_0$", fontsize=7, color=TEXT)
        ax.tick_params(labelsize=6.5, colors=TEXT, direction="out")
        ax.xaxis.grid(True, color="#e3e3e3", linewidth=0.4)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#262626")
    axes[0].set_yticks(range(len(pairs)))
    axes[0].set_yticklabels(["-".join(p) for p in pairs], fontsize=5.5)
    axes[0].set_ylabel("radio pair", fontsize=7.5, color=TEXT)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(output / f"trace_gallery.{ext}")
    plt.close(fig)
    print(f"figures -> {output} (M0={m0:.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Plot the schedule-repair experiment records.

Usage:
    python plot_repair_experiments.py --records results/repair/records.jsonl --output figures/

Produces:
    repair_ladder.(pdf|png)  -- normalized makespan (vs. the oracle) per
                                disruption generator and repair policy
    cost_sweep.(pdf|png)     -- makespan vs. per-task repair cost for the
                                costed policies, with the wait reference
    summary.json             -- the aggregates behind both figures

Design notes: every instance is normalized by ITS OWN oracle makespan, so 1.0
means "as good as knowing the trace"; aggregation is the geometric mean (these
are ratios); per-instance dots show spread honestly; hatch textures keep
policy identity legible in grayscale print; the palette is CVD-validated with
direct labels satisfying the low-contrast relief rule.
"""

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ncsim.experiments import load_records

# Print-oriented styling: serif type to match the IEEE body font, hairline
# axes, and a muted categorical palette; hatch textures and per-policy
# markers remain the secondary encoding for grayscale print and CVD.
matplotlib.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "STIXGeneral", "DejaVu Serif"],
    "mathtext.fontset": "stix",
    "axes.linewidth": 0.6,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "xtick.major.size": 2.5,
    "ytick.major.size": 2.5,
    "hatch.linewidth": 0.5,
})

POLICY_STYLE = {
    "wait": {"color": "#4d6d9a", "hatch": "///", "marker": "o", "ls": "-"},
    "reroute": {"color": "#b5573f", "hatch": "\\\\\\", "marker": "^",
                "ls": (0, (4, 1.6))},
    "local": {"color": "#3f8264", "hatch": "xx", "marker": "s",
              "ls": (0, (4, 1.4, 1, 1.4))},
    "global": {"color": "#a8842c", "hatch": "..", "marker": "D",
               "ls": (0, (1, 1.1))},
}
TEXT_PRIMARY = "#1a1a1a"
TEXT_SECONDARY = "#444444"
EDGE = "#262626"


def lighten(hex_color, amount=0.45):
    """Mix a hex color toward white; bar fills stay pale under dark hatch."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    mix = lambda c: int(c + (255 - c) * amount)
    return f"#{mix(r):02x}{mix(g):02x}{mix(b):02x}"
GENERATOR_LABELS = {
    "single": "Single failure",
    "flapping": "Flapping (GE)",
    "mobility": "Mobility",
    "jamming": "Jamming",
}
FAMILY_OF = {
    "out_tree": "synthetic", "in_tree": "synthetic", "parallel_chains": "synthetic",
    "etl": "riotbench", "stats": "riotbench", "train": "riotbench",
    "predict": "riotbench",
    "epigenomics": "wfcommons", "montage": "wfcommons", "seismology": "wfcommons",
}
FAMILY_LABELS = {"synthetic": "Synthetic", "riotbench": "RIoTBench",
                 "wfcommons": "WfCommons"}


def geo_mean(values):
    values = [v for v in values if v and v > 0]
    if not values:
        return None
    return math.exp(sum(math.log(v) for v in values) / len(values))


def percentile(values, q):
    """q-th percentile (0..1) by linear interpolation of sorted values."""
    ordered = sorted(values)
    if not ordered:
        return None
    pos = q * (len(ordered) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def spread_whisker(ax, x, values, cap):
    """10th-90th percentile whisker at x; an arrow marks a clipped top."""
    lo, hi = percentile(values, 0.10), percentile(values, 0.90)
    if lo is None:
        return
    top = min(hi, cap)
    ax.errorbar(x, (lo + top) / 2, yerr=[[(lo + top) / 2 - lo], [top - (lo + top) / 2]],
                fmt="none", ecolor="#333333", elinewidth=0.7,
                capsize=1.3, capthick=0.7, zorder=4)
    if hi > cap:
        ax.scatter([x], [cap], s=5, marker="^", color="#333333",
                   zorder=4, linewidths=0)


def index_records(records):
    """(generator, policy, cost) -> {(instance, ccr): record}.

    Aggregates therefore pool across the CCR grid: each (instance, ccr)
    variant is one sample, normalized by its own oracle.
    """
    table = defaultdict(dict)
    for record in records:
        key = (record["generator"], record["policy"], record["repair_cost_frac"])
        table[key][(record["instance"], record.get("ccr", 1.0))] = record
    return table


def oracle_normalized(table, generator, policy, cost, oracle_key_cost=0.0):
    """Per-instance makespan / oracle makespan, only where both completed."""
    oracle = table.get((generator, "oracle", oracle_key_cost), {})
    runs = table.get((generator, policy, cost), {})
    ratios = {}
    for instance, record in runs.items():
        reference = oracle.get(instance)
        if not record["completed"] or not reference or not reference["completed"]:
            continue
        if reference["makespan"] > 0:
            ratios[instance] = record["makespan"] / reference["makespan"]
    return ratios


def style_axis(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(EDGE)
    ax.spines["bottom"].set_color(EDGE)
    ax.tick_params(colors=TEXT_PRIMARY, labelsize=7.5, direction="out")
    ax.yaxis.grid(True, color="#dedede", linewidth=0.4)
    ax.set_axisbelow(True)


def _draw_ladder(ax, table, generators, summary):
    """Draw the grouped ladder bars onto ax; used by both ladder figures."""
    policies = [p for p in POLICY_STYLE if any(
        (g, p, 0.0) in table for g in generators)]
    group_width = 0.8
    bar_width = group_width / len(policies)

    for gi, generator in enumerate(generators):
        for pi, policy in enumerate(policies):
            ratios = oracle_normalized(table, generator, policy, 0.0)
            total = len(table.get((generator, policy, 0.0), {}))
            summary["ladder"][generator][policy] = {
                "geo_mean": geo_mean(ratios.values()),
                "n_completed": len(ratios),
                "n_total": total,
            }
            if not ratios:
                continue
            x = gi - group_width / 2 + (pi + 0.5) * bar_width
            mean = geo_mean(ratios.values())
            style = POLICY_STYLE[policy]
            ax.bar(
                x, mean, width=bar_width * 0.88,
                color=lighten(style["color"]), hatch=style["hatch"],
                edgecolor=EDGE, linewidth=0.5, zorder=3,
                label=policy if gi == 0 else None,
            )
            # Honest spread behind the aggregate, as a 10th-90th percentile
            # whisker: individual dots smear into a streak at bar width.
            spread_whisker(ax, x, list(ratios.values()), cap=2.2)
            # Left of the bar center so the label clears the dot column.
            ax.annotate(
                f"{mean:.2f}", (x, mean), xytext=(-3, 2),
                textcoords="offset points", ha="right", va="bottom",
                fontsize=6, color=TEXT_PRIMARY, zorder=5,
            )
            if len(ratios) < total:
                ax.annotate(
                    f"{len(ratios)}/{total}", (x, 0.06), ha="center",
                    va="bottom", fontsize=5.5, color=TEXT_SECONDARY, zorder=5,
                    annotation_clip=False,
                )

    ax.axhline(1.0, color=EDGE, linewidth=0.7, linestyle=(0, (4, 3)), zorder=2)
    ax.set_xticks(range(len(generators)))
    ax.set_xticklabels([GENERATOR_LABELS.get(g, g) for g in generators],
                       fontsize=8, color=TEXT_PRIMARY)
    ax.set_ylabel("Makespan / oracle (geo. mean)", fontsize=8,
                  color=TEXT_PRIMARY)
    ax.set_ylim(0, 2.3)
    style_axis(ax)
    # Legend above the axis, outside the data area, so it never sits on the
    # per-instance dot columns.
    ax.legend(frameon=False, fontsize=7.5, loc="lower left",
              bbox_to_anchor=(0.0, 1.01), ncols=len(policies),
              handlelength=1.6, handleheight=0.9, columnspacing=1.4,
              borderaxespad=0.0)


def plot_ladder(table, generators, output, summary):
    """Grouped bars: normalized makespan by generator x policy."""
    fig, ax = plt.subplots(figsize=(7.0, 2.25), dpi=200)
    _draw_ladder(ax, table, generators, summary)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(output / f"repair_ladder.{ext}")
    plt.close(fig)


def _draw_ladder_by_ccr(axes, ccrs, table, generators):
    """Per-generator panels: policy bars grouped by CCR, with variant dots.

    The CCR-resolved counterpart of _draw_ladder, sharing its x structure
    with the per-CCR trend row so the two rows read column by column.
    """
    group_width = 0.78
    bar_width = group_width / len(POLICY_STYLE)
    # Ceiling above the largest mean (flapping/reroute at CCR 5 is 2.68) so
    # no bar is silently cut; a whisker past the cap gets an arrowhead.
    cap = 2.7
    for ax, generator in zip(axes, generators):
        for ci, ccr in enumerate(ccrs):
            for pi, (policy, style) in enumerate(POLICY_STYLE.items()):
                ratios = oracle_normalized(table, generator, policy, 0.0)
                values = [v for (inst, c), v in ratios.items() if c == ccr]
                mean = geo_mean(values)
                if mean is None:
                    continue
                x = ci - group_width / 2 + (pi + 0.5) * bar_width
                ax.bar(x, mean, width=bar_width * 0.9,
                       color=lighten(style["color"]), hatch=style["hatch"],
                       edgecolor=EDGE, linewidth=0.4, zorder=3,
                       label=policy if (ci == 0 and ax is axes[0]) else None)
                spread_whisker(ax, x, values, cap)
        ax.axhline(1.0, color=EDGE, linewidth=0.5, linestyle=(0, (4, 3)),
                   zorder=2)
        ax.set_xticks(range(len(ccrs)))
        ax.set_xticklabels([f"{c:g}" for c in ccrs], fontsize=6.5)
        ax.set_xlabel("CCR", fontsize=7, color=TEXT_PRIMARY)
        ax.set_ylim(0, 2.85)
        ax.set_title(GENERATOR_LABELS.get(generator, generator), fontsize=8,
                     color=TEXT_PRIMARY)
        style_axis(ax)
    axes[0].set_ylabel("Makespan / oracle", fontsize=8, color=TEXT_PRIMARY)
    for ax in axes[1:]:
        ax.tick_params(labelleft=False)


def plot_cost_sweep(table, generators, costs, output, summary):
    """Lines: normalized makespan vs. per-task repair cost, per generator."""
    costed = [p for p in ("local", "global") if any(
        (g, p, c) in table for g in generators for c in costs)]
    if not costed or len(costs) < 2:
        return
    fig, axes = plt.subplots(
        1, len(generators), figsize=(7.0, 1.85), dpi=200, sharey=True
    )
    if len(generators) == 1:
        axes = [axes]

    for ax, generator in zip(axes, generators):
        for policy in costed:
            xs, ys = [], []
            for cost in sorted(costs):
                ratios = oracle_normalized(table, generator, policy, cost)
                mean = geo_mean(ratios.values())
                summary["cost_sweep"][generator][policy][str(cost)] = mean
                if mean is not None:
                    xs.append(cost)
                    ys.append(mean)
            style = POLICY_STYLE[policy]
            ax.plot(xs, ys, color=style["color"], linewidth=0.9,
                    linestyle=style["ls"],
                    marker=style["marker"], markersize=2.6,
                    markerfacecolor="white", markeredgewidth=0.7,
                    zorder=3, label=policy)
        # Wait pays no repair cost: flat reference.
        wait_ratios = oracle_normalized(table, generator, "wait", 0.0)
        wait_mean = geo_mean(wait_ratios.values())
        summary["cost_sweep"][generator]["wait"] = wait_mean
        if wait_mean is not None:
            ax.axhline(wait_mean, color=POLICY_STYLE["wait"]["color"],
                       linewidth=0.8, linestyle=":", zorder=2, label="wait")
        ax.axhline(1.0, color=EDGE, linewidth=0.5, linestyle=(0, (4, 3)),
                   zorder=1)
        ax.set_title(GENERATOR_LABELS.get(generator, generator), fontsize=8,
                     color=TEXT_PRIMARY)
        ax.set_xlabel("Repair cost / task (frac. of $M_0$)", fontsize=7,
                      color=TEXT_PRIMARY)
        style_axis(ax)

    axes[0].set_ylabel("Makespan / oracle", fontsize=8, color=TEXT_PRIMARY)
    axes[-1].legend(frameon=False, fontsize=7, loc="best", handlelength=1.7)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(output / f"cost_sweep.{ext}")
    plt.close(fig)


def _draw_ccr(axes, ccrs, table, generators, summary, legend=True):
    """Draw the per-CCR trend panels onto axes; one axis per generator."""
    for ax, generator in zip(axes, generators):
        panel_max = 1.0
        for policy, style in POLICY_STYLE.items():
            xs, ys = [], []
            for ccr in ccrs:
                ratios = oracle_normalized(table, generator, policy, 0.0)
                values = [v for (inst, c), v in ratios.items() if c == ccr]
                mean = geo_mean(values)
                summary["ccr_trend"][generator][policy][str(ccr)] = mean
                if mean is not None:
                    xs.append(ccr)
                    ys.append(mean)
            if ys:
                panel_max = max(panel_max, max(ys))
            ax.plot(xs, ys, color=style["color"], linewidth=0.9,
                    linestyle=style["ls"],
                    marker=style["marker"], markersize=2.6,
                    markerfacecolor="white", markeredgewidth=0.7,
                    zorder=3, label=policy)
        ax.axhline(1.0, color=EDGE, linewidth=0.5, linestyle=(0, (4, 3)),
                   zorder=1)
        ax.set_xscale("log")
        ax.set_xticks(ccrs)
        ax.set_xticklabels([f"{c:g}" for c in ccrs], fontsize=6.5)
        ax.minorticks_off()
        # Per-panel y range: a shared scale would let flapping's blow-up
        # flatten every other panel's curves into an indistinguishable band.
        ax.set_ylim(0.985, 1.0 + (panel_max - 1.0) * 1.12 + 0.01)
        ax.tick_params(axis="y", labelsize=6.5)
        ax.set_title(GENERATOR_LABELS.get(generator, generator), fontsize=8,
                     color=TEXT_PRIMARY)
        ax.set_xlabel("CCR", fontsize=7, color=TEXT_PRIMARY)
        style_axis(ax)
    axes[0].set_ylabel("Makespan / oracle", fontsize=8, color=TEXT_PRIMARY)
    if legend:
        # Flapping panel: its curves hug the floor until the right side, so
        # the upper left is the one reliably empty corner.
        target = 1 if len(axes) > 1 else 0
        axes[target].legend(frameon=False, fontsize=6.5, loc="upper left",
                            handlelength=1.9, labelspacing=0.3,
                            borderaxespad=0.2)


def plot_ccr_trend(records, table, generators, output, summary):
    """Lines: geo-mean makespan/oracle vs. CCR per policy, per generator."""
    ccrs = sorted({r.get("ccr", 1.0) for r in records})
    if len(ccrs) < 2:
        return
    fig, axes = plt.subplots(1, len(generators), figsize=(7.0, 1.85),
                             dpi=200)
    if len(generators) == 1:
        axes = [axes]
    _draw_ccr(axes, ccrs, table, generators, summary)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(output / f"ccr_trend.{ext}")
    plt.close(fig)


def plot_ladder_ccr(records, table, generators, output, summary):
    """Combined figure: ladder bars on top, per-CCR trend panels below.

    One figure and one caption in the paper instead of two; the bars carry
    the policy legend for both rows.
    """
    ccrs = sorted({r.get("ccr", 1.0) for r in records})
    if len(ccrs) < 2:
        return
    fig = plt.figure(figsize=(7.0, 3.45), dpi=200)
    grid = fig.add_gridspec(2, len(generators), height_ratios=[1.15, 1.0],
                            hspace=0.62)
    top = [fig.add_subplot(grid[0, i]) for i in range(len(generators))]
    _draw_ladder_by_ccr(top, ccrs, table, generators)
    bottom = [fig.add_subplot(grid[1, i]) for i in range(len(generators))]
    _draw_ccr(bottom, ccrs, table, generators, summary, legend=True)
    handles, labels = top[0].get_legend_handles_labels()
    fig.legend(handles, labels, ncols=len(labels), frameon=False,
               fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, 1.0),
               handlelength=1.6, handleheight=0.9, columnspacing=1.4)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    for ext in ("pdf", "png"):
        fig.savefig(output / f"ladder_ccr.{ext}")
    plt.close(fig)


def family_table(records, table, generators, output, summary):
    """Per-workload-family geo-means as a LaTeX table body (family_table.tex).

    Rows: family x generator; columns: policies. Values are geo-mean
    makespan/oracle at zero repair cost. Emits the complete tabular
    environment: an input inside a tabular breaks TeX's alignment scanner, so
    the paper inputs the whole table instead.
    """
    families = sorted({FAMILY_OF.get(r["structure"], "other") for r in records})
    policies = [p for p in POLICY_STYLE]
    lines = []
    for family in families:
        instances = {r["instance"] for r in records
                     if FAMILY_OF.get(r["structure"], "other") == family}
        for gi, generator in enumerate(generators):
            cells = []
            for policy in policies:
                ratios = oracle_normalized(table, generator, policy, 0.0)
                mean = geo_mean([v for (inst, _ccr), v in ratios.items()
                                 if inst in instances])
                summary["family"][family][generator][policy] = mean
                cells.append(f"{mean:.2f}" if mean is not None else "--")
            best = min((float(c) for c in cells if c != "--"), default=None)
            cells = [
                (r"\textbf{" + c + "}") if c != "--" and float(c) == best else c
                for c in cells
            ]
            row_head = FAMILY_LABELS.get(family, family) if gi == 0 else ""
            lines.append(
                f"{row_head} & {GENERATOR_LABELS.get(generator, generator)} & "
                + " & ".join(cells) + r" \\"
            )
        lines.append(r"\midrule")
    if lines and lines[-1] == r"\midrule":
        lines.pop()
    header = [
        r"\begin{tabular}{llcccc}",
        r"\toprule",
        r"Family & Disruption & Wait & Reroute & Local & Global \\",
        r"\midrule",
    ]
    footer = [r"\bottomrule", r"\end{tabular}"]
    with open(output / "family_table.tex", "w", encoding="utf-8") as handle:
        handle.write("\n".join(header + lines + footer) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    records = load_records(Path(args.records))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    table = index_records(records)
    generators = sorted(
        {r["generator"] for r in records},
        key=lambda g: list(GENERATOR_LABELS).index(g) if g in GENERATOR_LABELS else 99,
    )
    costs = sorted({r["repair_cost_frac"] for r in records})

    summary = {
        "ladder": defaultdict(dict),
        "cost_sweep": defaultdict(lambda: defaultdict(dict)),
        "family": defaultdict(lambda: defaultdict(dict)),
        "ccr_trend": defaultdict(lambda: defaultdict(dict)),
    }
    plot_ladder(table, generators, output, summary)
    plot_cost_sweep(table, generators, costs, output, summary)
    plot_ccr_trend(records, table, generators, output, summary)
    plot_ladder_ccr(records, table, generators, output, summary)
    family_table(records, table, generators, output, summary)

    with open(output / "summary.json", "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, default=dict)
    print(f"figures + summary -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

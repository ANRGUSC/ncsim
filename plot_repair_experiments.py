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

# Validated categorical palette (dataviz reference, adjacent-pair mode) with
# per-policy hatch textures as the secondary encoding for print/CVD.
POLICY_STYLE = {
    "wait": {"color": "#2a78d6", "hatch": "///"},
    "reroute": {"color": "#eb6834", "hatch": "\\\\\\"},
    "local": {"color": "#1baf7a", "hatch": "xx"},
    "global": {"color": "#eda100", "hatch": ".."},
}
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
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


def index_records(records):
    """(generator, policy, cost) -> {instance: record}."""
    table = defaultdict(dict)
    for record in records:
        key = (record["generator"], record["policy"], record["repair_cost_frac"])
        table[key][record["instance"]] = record
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
    ax.spines["left"].set_color("#d8d7d2")
    ax.spines["bottom"].set_color("#d8d7d2")
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=8)
    ax.yaxis.grid(True, color="#e8e7e2", linewidth=0.7)
    ax.set_axisbelow(True)


def plot_ladder(table, generators, output, summary):
    """Grouped bars: normalized makespan by generator x policy."""
    policies = [p for p in POLICY_STYLE if any(
        (g, p, 0.0) in table for g in generators)]
    fig, ax = plt.subplots(figsize=(7.0, 2.25), dpi=200)
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
                x, mean, width=bar_width * 0.92,
                color=style["color"], hatch=style["hatch"],
                edgecolor="white", linewidth=0.8, zorder=3,
                label=policy if gi == 0 else None,
            )
            # Per-instance dots: honest spread behind the aggregate. Dots
            # beyond the cap render as up-triangles pinned at the cap so one
            # outlier cannot flatten every bar.
            cap = 2.2
            inside = [v for v in ratios.values() if v <= cap]
            clipped = [v for v in ratios.values() if v > cap]
            ax.scatter(
                [x] * len(inside), inside,
                s=4, color=TEXT_PRIMARY, alpha=0.35, zorder=4, linewidths=0,
            )
            if clipped:
                ax.scatter(
                    [x] * len(clipped), [cap] * len(clipped),
                    s=8, marker="^", color=TEXT_PRIMARY, alpha=0.5,
                    zorder=4, linewidths=0,
                )
            ax.annotate(
                f"{mean:.2f}", (x, mean), xytext=(0, 2),
                textcoords="offset points", ha="center", va="bottom",
                fontsize=6.5, color=TEXT_PRIMARY, zorder=5,
            )
            if len(ratios) < total:
                ax.annotate(
                    f"{len(ratios)}/{total}", (x, 0.06), ha="center",
                    va="bottom", fontsize=5.5, color=TEXT_SECONDARY, zorder=5,
                    annotation_clip=False,
                )

    ax.axhline(1.0, color=TEXT_SECONDARY, linewidth=1.0, linestyle="--", zorder=2)
    ax.annotate("oracle = 1.0", (-0.48, 1.0), xytext=(0, -9),
                textcoords="offset points", ha="left", fontsize=7,
                color=TEXT_SECONDARY)
    ax.set_xticks(range(len(generators)))
    ax.set_xticklabels([GENERATOR_LABELS.get(g, g) for g in generators],
                       fontsize=8.5, color=TEXT_PRIMARY)
    ax.set_ylabel("Makespan / oracle (geo. mean)", fontsize=8.5,
                  color=TEXT_PRIMARY)
    ax.set_ylim(0, 2.3)
    style_axis(ax)
    ax.legend(frameon=False, fontsize=8, loc="upper left", ncols=len(policies),
              handlelength=1.4, columnspacing=1.0)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(output / f"repair_ladder.{ext}")
    plt.close(fig)


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
            ax.plot(xs, ys, color=style["color"], linewidth=1.8,
                    marker="o", markersize=4, zorder=3, label=policy)
        # Wait pays no repair cost: flat reference.
        wait_ratios = oracle_normalized(table, generator, "wait", 0.0)
        wait_mean = geo_mean(wait_ratios.values())
        summary["cost_sweep"][generator]["wait"] = wait_mean
        if wait_mean is not None:
            ax.axhline(wait_mean, color=POLICY_STYLE["wait"]["color"],
                       linewidth=1.2, linestyle=":", zorder=2, label="wait")
        ax.axhline(1.0, color=TEXT_SECONDARY, linewidth=0.8, linestyle="--",
                   zorder=1)
        ax.set_title(GENERATOR_LABELS.get(generator, generator), fontsize=8.5,
                     color=TEXT_PRIMARY)
        ax.set_xlabel("Repair cost / task (frac. of $M_0$)", fontsize=7.5,
                      color=TEXT_SECONDARY)
        style_axis(ax)

    axes[0].set_ylabel("Makespan / oracle", fontsize=8.5, color=TEXT_PRIMARY)
    axes[-1].legend(frameon=False, fontsize=7.5, loc="best", handlelength=1.6)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(output / f"cost_sweep.{ext}")
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
                mean = geo_mean([v for k, v in ratios.items() if k in instances])
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
    }
    plot_ladder(table, generators, output, summary)
    plot_cost_sweep(table, generators, costs, output, summary)
    family_table(records, table, generators, output, summary)

    with open(output / "summary.json", "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, default=dict)
    print(f"figures + summary -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

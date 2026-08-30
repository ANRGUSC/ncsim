#!/usr/bin/env python3
"""Analyze revision experiments using topology-level and paired statistics."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from rev1_common import DATA_DIR, PAPER_ROOT, ROUTES, write_json

RESULTS = DATA_DIR / "rev1_results.json"
SUMMARY = DATA_DIR / "rev1_summary.json"
BOOTSTRAP_SEED = 20260829
BOOTSTRAP_REPS = 10_000
LABELS = [r[0] for r in ROUTES]
SCHED_LABEL = {"heft1": "HEFT-L", "lc_heft": "LC-HEFT", "heft2": "HEFT-W"}
COLORS = {"heft1": "#0072B2", "lc_heft": "#009E73", "heft2": "#D55E00"}


def load_ok():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    return [r for r in payload["records"] if r.get("design_version") == 2
            if r.get("status") in ("ok", "completed") and r.get("makespan") is not None]


def percentile_ci(values):
    return [float(x) for x in np.percentile(values, [2.5, 97.5])]


def topology_summary(rows, group_fields):
    """Summarize topology-level means; workload replicates are not pseudoreplicates."""
    cells = defaultdict(lambda: defaultdict(list))
    for r in rows:
        key = tuple(r[f] for f in group_fields)
        cells[key][r["topology_ordinal"]].append(float(r["makespan"]))
    out = {}
    for key, by_top in cells.items():
        top_means = np.array([np.mean(v) for _, v in sorted(by_top.items())])
        mean = float(np.mean(top_means))
        if len(top_means) > 1:
            # t_0.975,9 for the intended K=10 design; exact common small-n values.
            tcrit = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776,
                     6: 2.571, 7: 2.447, 8: 2.365, 9: 2.306, 10: 2.262}.get(
                         len(top_means), 1.96)
            half = tcrit * float(np.std(top_means, ddof=1)) / math.sqrt(len(top_means))
        else:
            half = 0.0
        out["|".join(map(str, key))] = {
            "mean": mean, "ci95": [mean - half, mean + half],
            "n_topologies": len(top_means), "topology_means": top_means.tolist(),
        }
    return out


def scheduler_analysis(rows):
    selected = [r for r in rows if r.get("experiment") == "scheduler_density"]
    stats = topology_summary(selected, ("network", "scheduler"))
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    paired = {}
    for side in (150, 200, 250, 300, 350, 400, 500):
        network = f"L{side}"
        cell = [r for r in selected if r["network"] == network]
        lookup = {(r["topology_ordinal"], r["workload_seed"], r["scheduler"]):
                  float(r["makespan"]) for r in cell}
        by_top = defaultdict(list)
        for topology, workload, scheduler in lookup:
            if scheduler != "heft1":
                continue
            comparison = (topology, workload, "heft2")
            if comparison in lookup:
                by_top[topology].append(
                    math.log(lookup[comparison] / lookup[(topology, workload, "heft1")]))
        ratio, ci = hierarchical_bootstrap(by_top, rng)
        paired[network] = {"ratio": ratio, "ci95": ci,
                           "n_topologies": len(by_top)}

    fig, ax = plt.subplots(figsize=(3.45, 2.35))
    all_y = []
    for sched in ("heft1", "lc_heft", "heft2"):
        xs, ys, lo, hi = [], [], [], []
        for side in (150, 200, 250, 300, 350, 400, 500):
            s = stats.get(f"L{side}|{sched}")
            if not s:
                continue
            xs.append(side); ys.append(s["mean"])
            all_y.append(s["mean"])
            lo.append(s["mean"] - s["ci95"][0]); hi.append(s["ci95"][1] - s["mean"])
        ax.errorbar(xs, ys, yerr=[lo, hi], marker="o", lw=1.2, ms=3.2,
                    capsize=2, label=SCHED_LABEL[sched], color=COLORS[sched])
    ax.set_xlabel("Square side length $L$ (m)")
    ax.set_ylabel("Realized makespan (s)")
    ax.set_yscale("log")
    ax.set_ylim(80, max(all_y) * 1.35)
    ax.grid(True, which="both", alpha=.25)
    ax.legend(frameon=False, fontsize=7, ncol=3, loc="upper left")
    fig.tight_layout(pad=.3)
    fig.savefig(PAPER_ROOT / "saga_rand_large_vs_ncsim.pdf", bbox_inches="tight")
    fig.savefig(PAPER_ROOT / "saga_rand_large_vs_ncsim.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    stats["paired_HEFT-W_over_HEFT-L"] = paired
    return stats


def table_analysis(rows):
    selected = [r for r in rows if r.get("experiment") == "table_iii"]
    groups = defaultdict(list)
    exemplars = defaultdict(list)
    for r in selected:
        key = (r["network"], r["dag_size"], r["scheduler"])
        groups[key].append(float(r["makespan"]))
        exemplars[key].append(r)
    output = {}
    tex = [r"\begin{tabular}{llrrrr}", r"\toprule",
           r"Network & DAG & Model & Pred. (s) & Realized (s) & $>1$-hop edges \\",
           r"\midrule"]
    for key in sorted(groups, key=lambda x: (int(x[0].split("x")[0]), x[1], x[2])):
        vals = np.array(groups[key]); sample_rows = exemplars[key]
        mean = float(vals.mean())
        half = 1.96 * float(vals.std(ddof=1)) / math.sqrt(len(vals)) if len(vals) > 1 else 0
        multi = float(np.mean([r.get("diagnostics", {}).get("counts", {}).get("multi_hop", 0)
                               for r in sample_rows]))
        pred = float(np.mean([r.get("predicted_makespan", float("nan")) for r in sample_rows]))
        output["|".join(map(str, key))] = {
            "predicted": pred, "realized_mean": mean,
            "realized_ci95": [mean-half, mean+half], "n": len(vals),
            "mean_multi_hop_edges": multi,
            "diagnostics_by_workload": [r.get("diagnostics", {}) for r in sample_rows],
        }
        tex.append(f"{key[0]} & {key[1]} & {SCHED_LABEL[key[2]]} & {pred:.1f} & "
                   f"{mean:.1f} $\\pm$ {half:.1f} & {multi:.1f} \\\\")
    tex += [r"\bottomrule", r"\end{tabular}"]
    (DATA_DIR / "rev1_table_iii.tex").write_text("\n".join(tex)+"\n", encoding="utf-8")
    return output


def paired_arrays(rows, network, dag_size, route):
    cell = [r for r in rows if r.get("experiment") == "routing"
            and r["network"] == network and r["dag_size"] == dag_size]
    lookup = {(r["topology_ordinal"], r["workload_seed"], r["routing_label"]):
              float(r["makespan"]) for r in cell}
    by_top = defaultdict(list)
    keys = {(t, w) for t, w, label in lookup if label == "SH"}
    for t, w in sorted(keys):
        if (t, w, route) in lookup:
            by_top[t].append(math.log(lookup[t, w, route] / lookup[t, w, "SH"]))
    return by_top


def hierarchical_bootstrap(by_top, rng, reps=BOOTSTRAP_REPS):
    tops = sorted(by_top)
    observed = float(np.mean([np.mean(by_top[t]) for t in tops]))
    draws = np.empty(reps)
    for b in range(reps):
        chosen = rng.integers(0, len(tops), size=len(tops))
        top_values = []
        for index in chosen:
            vals = np.asarray(by_top[tops[int(index)]])
            top_values.append(float(np.mean(rng.choice(vals, len(vals), replace=True))))
        draws[b] = np.mean(top_values)
    return math.exp(observed), [math.exp(x) for x in np.percentile(draws, [2.5, 97.5])]


def aggregate_routing_bootstrap(rows, route, rng, reps=BOOTSTRAP_REPS):
    """Cell-balanced hierarchical bootstrap across the 18 routing cells."""
    cell_clusters = []
    for network in ("L150", "L500", "7x7"):
        for n in (8, 16, 24, 32, 45, 60):
            by_top = paired_arrays(rows, network, n, route)
            if by_top:
                cell_clusters.append(by_top)
    observed_cells = [np.mean([np.mean(v) for v in by_top.values()])
                      for by_top in cell_clusters]
    draws = np.empty(reps)
    for b in range(reps):
        sampled_cells = []
        for by_top in cell_clusters:
            tops = sorted(by_top)
            chosen = rng.integers(0, len(tops), size=len(tops))
            sampled_tops = []
            for index in chosen:
                vals = np.asarray(by_top[tops[int(index)]])
                sampled_tops.append(float(np.mean(rng.choice(vals, len(vals), replace=True))))
            sampled_cells.append(float(np.mean(sampled_tops)))
        draws[b] = np.mean(sampled_cells)
    observed = float(np.mean(observed_cells))
    return math.exp(observed), [math.exp(x) for x in np.percentile(draws, [2.5, 97.5])]


def routing_analysis(rows):
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    cells = {}
    for network in ("L150", "L500", "7x7"):
        for n in (8, 16, 24, 32, 45, 60):
            for route in LABELS:
                by_top = paired_arrays(rows, network, n, route)
                if not by_top:
                    continue
                ratio, ci = hierarchical_bootstrap(by_top, rng)
                cells[f"{network}|{n}|{route}"] = {"ratio": ratio, "ci95": ci}

    aggregate = {}
    for route in LABELS:
        if not any(k.endswith("|"+route) for k in cells):
            continue
        ratio, ci = aggregate_routing_bootstrap(rows, route, rng)
        better = sum(v["ci95"][1] < 1 for k, v in cells.items() if k.endswith("|"+route))
        worse = sum(v["ci95"][0] > 1 for k, v in cells.items() if k.endswith("|"+route))
        aggregate[route] = {"ratio": ratio, "ci95": ci,
                            "cells_better": better, "cells_worse": worse}

    tex = [r"\begin{tabular}{lrrr}", r"\toprule",
           r"Route & Geom. mean / SH (95\% CI) & Better & Worse \\", r"\midrule"]
    for route in LABELS:
        if route not in aggregate:
            continue
        x = aggregate[route]
        tex.append(f"{route} & {x['ratio']:.2f} [{x['ci95'][0]:.2f}, {x['ci95'][1]:.2f}] "
                   f"& {x['cells_better']} & {x['cells_worse']} \\\\")
    tex += [r"\bottomrule", r"\end{tabular}"]
    (DATA_DIR / "rev1_routing_stats.tex").write_text("\n".join(tex)+"\n", encoding="utf-8")

    for network, filename in (("L150", "dag_scaling_L150.pdf"),
                              ("L500", "dag_scaling_L500.pdf"),
                              ("7x7", "dag_scaling_7x7.pdf")):
        fig, ax = plt.subplots(figsize=(3.45, 2.25))
        for index, route in enumerate(LABELS):
            xs, ys = [], []
            for n in (8, 16, 24, 32, 45, 60):
                cell = cells.get(f"{network}|{n}|{route}")
                if cell:
                    xs.append(n); ys.append(cell["ratio"])
            if xs:
                ax.plot(xs, ys, marker=("o", "s", "^", "v", "D", "P", "X", "<", ">")[index],
                        ms=2.5, lw=.85, label=route)
        ax.axhline(1.0, color="black", lw=.65, ls="--", alpha=.7)
        ax.set_xlabel("DAG tasks"); ax.set_ylabel("Paired makespan / SH")
        ax.set_ylim(bottom=.7)
        ax.grid(True, alpha=.22)
        ax.legend(ncol=3, fontsize=5.8, frameon=False)
        fig.tight_layout(pad=.3); fig.savefig(PAPER_ROOT / filename, bbox_inches="tight"); plt.close(fig)
    return {"cells": cells, "aggregate": aggregate}


def ablation_analysis(rows):
    noint = [r for r in rows if r.get("experiment") == "no_interference"]
    comm = [r for r in rows if r.get("experiment") == "commcomp"]
    penalty = [r for r in rows if r.get("experiment") == "penalty"]
    return {
        "no_interference": topology_summary(noint, ("network", "scheduler")) if noint else {},
        "commcomp": topology_summary(comm, ("network", "scheduler", "data_scale")) if comm else {},
        "penalty": topology_summary(penalty, ("network", "penalty_rate")) if penalty else {},
    }


def main():
    rows = load_ok()
    summary = {
        "analysis": {"bootstrap_seed": BOOTSTRAP_SEED,
                     "bootstrap_replicates": BOOTSTRAP_REPS,
                     "statistical_unit": "topology-level mean; matched workload pairing; equal-weight routing cells"},
        "scheduler": scheduler_analysis(rows),
        "table_iii": table_analysis(rows),
        "routing": routing_analysis(rows),
        "ablations": ablation_analysis(rows),
    }
    write_json(SUMMARY, summary)
    print(f"Analyzed {len(rows)} successful records; wrote {SUMMARY}")


if __name__ == "__main__":
    main()

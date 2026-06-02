#!/usr/bin/env python3
r"""Generate paper figures from sweep result JSONs.

Reads cached per-seed JSONs from ``dataset/`` (adjacent to ``main.tex``)
and writes:

Figures (PDFs in paper-milcom26/, where \graphicspath{{.}} finds them):
  - penalty_sweep.pdf       : HEFT-1 penalty sensitivity (Fig 3)
  - commcomp_sweep.pdf      : comm/comp ratio (Fig 8)

Verification fragments (in dataset/) for Table III and Table V CIs. The
paper transcribes these numbers by hand (main.tex has no \input), so the
fragments exist only to cross-check the printed table values:
  - table_iii_ci.tex
  - table_v_ci.tex
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

SCRIPTS_DIR = Path(__file__).resolve().parent
PAPER_DIR   = SCRIPTS_DIR.parent          # paper-milcom26/ (graphicspath {.})
DATASET     = PAPER_DIR / "dataset"       # committed per-seed JSONs

PENALTY_JSON = DATASET / "penalty_sweep_results.json"
COMMCOMP_JSON = DATASET / "commcomp_sweep_results.json"
TABLE_JSON   = DATASET / "table_ci_results.json"

OUT_PENALTY  = PAPER_DIR / "penalty_sweep.pdf"
OUT_COMMCOMP = PAPER_DIR / "commcomp_sweep.pdf"


def plot_penalty_sweep():
    if not PENALTY_JSON.exists():
        print(f"skip penalty sweep: {PENALTY_JSON} not found")
        return
    d = json.loads(PENALTY_JSON.read_text())
    penalties = d["penalties"]
    networks  = d["networks"]
    res       = d["results"]

    fig, ax = plt.subplots(figsize=(5.5, 3.4))
    markers = ['o', 's', '^', 'D', 'v']
    colors  = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
    for i, net in enumerate(networks):
        means, errs = [], []
        for p in penalties:
            row = res.get(f"{net}|{p:.0e}", {})
            means.append(row.get("mean"))
            errs.append(row.get("ci95_halfwidth") or 0)
        ax.errorbar(penalties, means, yerr=errs, marker=markers[i % len(markers)],
                    color=colors[i % len(colors)], label=net, capsize=2, lw=1.2)
    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_xlabel(r'HEFT-1 non-adjacent penalty rate (MB/s)')
    ax.set_ylabel(r'Mean simulated makespan (s)')
    ax.set_title(r'HEFT-1 penalty sensitivity (large DAG, SH routing)')
    ax.grid(True, which='both', linestyle=':', alpha=0.4)
    ax.legend(loc='best', fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(OUT_PENALTY)
    plt.close(fig)
    print(f"wrote {OUT_PENALTY}")


def plot_commcomp_sweep():
    if not COMMCOMP_JSON.exists():
        print(f"skip commcomp sweep: {COMMCOMP_JSON} not found")
        return
    d = json.loads(COMMCOMP_JSON.read_text())
    scales     = d["scales"]
    networks   = d["networks"]
    schedulers = d["schedulers"]
    res        = d["results"]

    fig, axes = plt.subplots(1, len(networks), figsize=(8, 3.0), sharey=False)
    if len(networks) == 1:
        axes = [axes]
    sched_color = {"heft1": "#1f77b4", "heft2": "#ff7f0e"}
    sched_label = {"heft1": r"\heftone (Locality-penalized)", "heft2": r"\hefttwo (Widest-path)"}
    for ax, net in zip(axes, networks):
        for sch in schedulers:
            means, errs = [], []
            for s in scales:
                row = res.get(f"{net}|{sch}|{s}", {})
                means.append(row.get("mean"))
                errs.append(row.get("ci95_halfwidth") or 0)
            ax.errorbar(scales, means, yerr=errs, marker='o',
                        color=sched_color[sch], label=sch.upper(), capsize=2, lw=1.2)
        ax.set_xscale('log')
        ax.set_yscale('log')
        ax.set_xlabel(r'Edge data-size scale')
        ax.set_title(net)
        ax.grid(True, which='both', linestyle=':', alpha=0.4)
        ax.legend(loc='best', fontsize=8)
    axes[0].set_ylabel(r'Mean simulated makespan (s)')
    fig.suptitle(r'Comm/comp ratio sweep (large DAG, SH routing)', y=1.02)
    fig.tight_layout()
    fig.savefig(OUT_COMMCOMP, bbox_inches='tight')
    plt.close(fig)
    print(f"wrote {OUT_COMMCOMP}")


def fmt_mean_ci(row, fmt="{:.1f}"):
    if not row:
        return "--"
    m = row.get("mean")
    c = row.get("ci95_halfwidth") or 0
    if m is None:
        return "--"
    return fmt.format(m) + r" $\pm$ " + fmt.format(c)


def write_table_iii_ci():
    if not TABLE_JSON.exists():
        print(f"skip table III CI: {TABLE_JSON} not found")
        return
    d = json.loads(TABLE_JSON.read_text())
    r = d["results"]
    out = DATASET / "table_iii_ci.tex"
    rows = [
        ("$4\\times4$ S", "4x4_S_heft1", "4x4_S_heft2"),
        ("$4\\times4$ L", "4x4_L_heft1", "4x4_L_heft2"),
        ("$7\\times7$ S", "7x7_S_heft1", "7x7_S_heft2"),
        ("$7\\times7$ L", "7x7_L_heft1", "7x7_L_heft2"),
    ]
    lines = []
    for label, k1, k2 in rows:
        lines.append(f"{label} & {fmt_mean_ci(r.get(k1))} & {fmt_mean_ci(r.get(k2))} \\\\")
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out}")


def write_table_v_ci():
    if not TABLE_JSON.exists():
        print(f"skip table V CI: {TABLE_JSON} not found")
        return
    d = json.loads(TABLE_JSON.read_text())
    r = d["results"]
    out = DATASET / "table_v_ci.tex"
    rows = [
        ("L150_heft1_SH", "L150_heft2_SH"),
        ("L300_heft1_SH", "L300_heft2_SH"),
        ("L500_heft1_GSDD", "L500_heft2_GSDD"),
    ]
    lines = []
    for k1, k2 in rows:
        lines.append(f"{k1}: {fmt_mean_ci(r.get(k1))}")
        lines.append(f"{k2}: {fmt_mean_ci(r.get(k2))}")
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    plot_penalty_sweep()
    plot_commcomp_sweep()
    write_table_iii_ci()
    write_table_v_ci()

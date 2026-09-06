#!/usr/bin/env python3
"""Plot ns-3 cross-validation results for ncsim paper.

Two-panel figure:
  (a) N-way contention scaling: ncsim prediction vs ns-3 mean +/- 95% CI
  (b) Separation sweep: ncsim stepped prediction vs ns-3 results

Reads:
  - paper/ns3/results/ncsim_contention_predictions.json
  - paper/ns3/results/ncsim_separation_predictions.json
  - paper/ns3/results/contention_n*_s*.csv
  - paper/ns3/results/separation_s*_fixed_seed*.csv
"""

import json
import glob
import os
import sys
import numpy as np
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Times New Roman', 'Times', 'DejaVu Serif'],
    'font.size': 9,
    'axes.labelsize': 9,
    'xtick.labelsize': 7,
    'ytick.labelsize': 7,
})

RESULTS_DIR = Path(__file__).resolve().parent.parent / "ns3" / "results"
FIGURES_DIR = Path(__file__).resolve().parent.parent / "figures"


def load_ns3_contention():
    """Load and aggregate contention scaling CSV results."""
    data = {}  # n -> list of per-link goodput values (MBps)
    pattern = str(RESULTS_DIR / "contention_n*_s*.csv")
    for fpath in glob.glob(pattern):
        with open(fpath) as f:
            header = f.readline()
            for line in f:
                parts = line.strip().split(",")
                if len(parts) < 5:
                    continue
                n = int(parts[0])
                goodput_MBps = float(parts[4])
                data.setdefault(n, []).append(goodput_MBps)
    return data


def load_ns3_separation(mcs_mode="fixed"):
    """Load and aggregate separation sweep CSV results."""
    data = {}  # separation -> list of per-link goodput values (MBps)
    pattern = str(RESULTS_DIR / f"separation_s*_{mcs_mode}_seed*.csv")
    for fpath in glob.glob(pattern):
        with open(fpath) as f:
            header = f.readline()
            for line in f:
                parts = line.strip().split(",")
                if len(parts) < 6:
                    continue
                sep = int(float(parts[0]))
                goodput_MBps = float(parts[5])
                data.setdefault(sep, []).append(goodput_MBps)
    return data


def mean_ci95(values):
    """Compute mean and 95% confidence interval half-width."""
    arr = np.array(values)
    mean = np.mean(arr)
    if len(arr) < 2:
        return mean, 0.0
    se = np.std(arr, ddof=1) / np.sqrt(len(arr))
    ci95 = 1.96 * se
    return mean, ci95


def plot_contention_panel(ax, ncsim_preds, ns3_data):
    """Panel (a): N-way contention scaling."""
    # ncsim predictions
    ns = [p["n"] for p in ncsim_preds]
    ncsim_rates = [p["per_link_MBps"] for p in ncsim_preds]
    ax.plot(ns, ncsim_rates, 'o-', color='#2266bb', linewidth=1.5,
            markersize=4, label='ncsim prediction', zorder=5)

    # ns-3 results with error bars
    if ns3_data:
        ns3_ns = sorted(ns3_data.keys())
        ns3_means = []
        ns3_cis = []
        for n in ns3_ns:
            m, ci = mean_ci95(ns3_data[n])
            ns3_means.append(m)
            ns3_cis.append(ci)
        ax.errorbar(ns3_ns, ns3_means, yerr=ns3_cis, fmt='s',
                     color='#dd4444', markersize=4, capsize=3,
                     linewidth=1, label='ns-3 (mean ± 95% CI)', zorder=4)

        # Compute and annotate max relative error
        max_err = 0
        for n in ns3_ns:
            if n <= len(ncsim_preds):
                pred = ncsim_preds[n - 1]["per_link_MBps"]
                ns3_m, _ = mean_ci95(ns3_data[n])
                if pred > 0:
                    err = abs(ns3_m - pred) / pred * 100
                    max_err = max(max_err, err)
        if max_err > 0:
            ax.text(0.98, 0.95, f'max error: {max_err:.1f}%',
                    transform=ax.transAxes, fontsize=6, ha='right', va='top',
                    color='#666666')
    else:
        ax.text(0.5, 0.5, 'ns-3 data not yet available',
                transform=ax.transAxes, fontsize=8, ha='center', va='center',
                color='#999999', style='italic')

    ax.set_xlabel('Number of Contending Links ($n$)')
    ax.set_ylabel('Per-Link Goodput (MB/s)')
    ax.set_xlim(0.5, 8.5)
    ax.set_xticks(range(1, 9))
    ax.set_ylim(0)
    ax.grid(True, color='#cccccc', linewidth=0.5)
    ax.legend(fontsize=6, loc='upper right')
    ax.set_title('(a) Contention Scaling', fontsize=9, fontweight='bold')


def plot_separation_panel(ax, ncsim_preds, ns3_data, solo_rate=3.78):
    """Panel (b): Two-link separation sweep."""
    cs_range = 71.2  # from RF config

    # ncsim predictions (stepped line)
    seps = [p["separation_m"] for p in ncsim_preds]
    ncsim_rates = [p["per_link_MBps"] for p in ncsim_preds]

    # Split into contention / hidden terminal for coloring
    cont_seps = [p["separation_m"] for p in ncsim_preds if p["regime"] == "contention"]
    cont_rates = [p["per_link_MBps"] for p in ncsim_preds if p["regime"] == "contention"]
    ht_seps = [p["separation_m"] for p in ncsim_preds if p["regime"] == "hidden_terminal"]
    ht_rates = [p["per_link_MBps"] for p in ncsim_preds if p["regime"] == "hidden_terminal"]

    ax.plot(cont_seps, cont_rates, 'o-', color='#2266bb', linewidth=1.5,
            markersize=3, label='ncsim: contention', zorder=5)
    ax.plot(ht_seps, ht_rates, 's-', color='#dd8800', linewidth=1.5,
            markersize=3, label='ncsim: hidden terminal', zorder=5)

    # CS range boundary
    ax.axvline(x=cs_range, color='#cc4444', linewidth=0.8, linestyle='--', alpha=0.6)
    ax.text(cs_range + 2, solo_rate * 0.7,
            'CS boundary', fontsize=6, color='#cc4444', rotation=90, va='center')

    # ns-3 results
    if ns3_data:
        ns3_seps = sorted(ns3_data.keys())
        ns3_means = []
        ns3_cis = []
        for s in ns3_seps:
            m, ci = mean_ci95(ns3_data[s])
            ns3_means.append(m)
            ns3_cis.append(ci)
        ax.errorbar(ns3_seps, ns3_means, yerr=ns3_cis, fmt='D',
                     color='#dd4444', markersize=3, capsize=2,
                     linewidth=1, label='ns-3 (mean ± 95% CI)', zorder=4)
    else:
        ax.text(0.5, 0.5, 'ns-3 data not yet available',
                transform=ax.transAxes, fontsize=8, ha='center', va='center',
                color='#999999', style='italic')

    # Solo rate reference (n=1 goodput, not raw PHY rate)
    ax.axhline(y=solo_rate, color='gray', linewidth=0.8, linestyle='--', alpha=0.5)
    ax.text(180, solo_rate + 0.15, 'solo rate', fontsize=6, color='gray', alpha=0.7)

    ax.set_xlabel('Link Separation (m)')
    ax.set_ylabel('Per-Link Goodput (MB/s)')
    ax.set_xlim(0, 210)
    ax.set_ylim(0, solo_rate * 1.3)
    ax.grid(True, color='#cccccc', linewidth=0.5)
    ax.legend(fontsize=6, loc='lower right')
    ax.set_title('(b) Separation Sweep', fontsize=9, fontweight='bold')


def main():
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # Load ncsim predictions
    pred_cont_path = RESULTS_DIR / "ncsim_contention_predictions.json"
    pred_sep_path = RESULTS_DIR / "ncsim_separation_predictions.json"

    if not pred_cont_path.exists():
        print("Error: ncsim contention predictions not found. "
              "Run generate_ns3_baselines.py first.")
        sys.exit(1)
    with open(pred_cont_path) as f:
        exp1_preds = json.load(f)["predictions"]

    if not pred_sep_path.exists():
        print("Error: ncsim separation predictions not found. "
              "Run generate_ns3_baselines.py first.")
        sys.exit(1)
    with open(pred_sep_path) as f:
        exp2_preds = json.load(f)["predictions"]

    # Load ns-3 results (may be empty if not yet run)
    ns3_cont = load_ns3_contention()
    ns3_sep = load_ns3_separation("fixed")

    # Create two-panel figure
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 3.0))

    # n=1 Bianchi goodput = solo rate (no contention)
    solo_rate = exp1_preds[0]["per_link_MBps"]

    plot_contention_panel(ax1, exp1_preds, ns3_cont)
    plot_separation_panel(ax2, exp2_preds, ns3_sep, solo_rate=solo_rate)

    plt.tight_layout(pad=0.5, w_pad=1.5)

    outpath = FIGURES_DIR / "ns3_validation.png"
    fig.savefig(outpath, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"Saved {outpath}")

    # Also save PDF for LaTeX
    outpath_pdf = FIGURES_DIR / "ns3_validation.pdf"
    fig2, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 2.8))
    plot_contention_panel(ax1, exp1_preds, ns3_cont)
    plot_separation_panel(ax2, exp2_preds, ns3_sep, solo_rate=solo_rate)
    plt.tight_layout(pad=0.5, w_pad=1.5)
    fig2.savefig(outpath_pdf, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"Saved {outpath_pdf}")

    # Print summary statistics if ns-3 data available
    if ns3_cont:
        print("\n=== Contention Scaling: ncsim vs ns-3 ===")
        print(f"{'n':>3}  {'ncsim':>8}  {'ns-3':>8}  {'CI95':>6}  {'err%':>6}")
        for p in exp1_preds:
            n = p["n"]
            if n in ns3_cont:
                m, ci = mean_ci95(ns3_cont[n])
                err = abs(m - p["per_link_MBps"]) / p["per_link_MBps"] * 100
                print(f"{n:3d}  {p['per_link_MBps']:8.3f}  {m:8.3f}  "
                      f"±{ci:.3f}  {err:5.1f}%")

    if ns3_sep:
        print("\n=== Separation Sweep: ncsim vs ns-3 ===")
        print(f"{'sep':>5}  {'ncsim':>8}  {'ns-3':>8}  {'CI95':>6}  {'err%':>6}")
        for p in exp2_preds:
            s = p["separation_m"]
            if s in ns3_sep:
                m, ci = mean_ci95(ns3_sep[s])
                err = abs(m - p["per_link_MBps"]) / p["per_link_MBps"] * 100
                print(f"{s:5d}  {p['per_link_MBps']:8.3f}  {m:8.3f}  "
                      f"±{ci:.3f}  {err:5.1f}%")


if __name__ == "__main__":
    main()

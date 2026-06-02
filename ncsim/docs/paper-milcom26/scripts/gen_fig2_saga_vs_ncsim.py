"""Reproduce the Fig 2 comparison (SAGA-predicted vs. ncsim-measured makespan
under shortest-hop (SH) routing, across network density, for HEFT-1 / HEFT-2)
from cached per-seed data in ``dataset/``, **with 95% CI error bars**.

Output: ``saga_rand_{small,large}_vs_ncsim_ci.pdf`` (the ``_ci`` suffix marks
these as the data-backed, error-bar versions). These are written ALONGSIDE the
paper's published ``saga_rand_large_vs_ncsim.pdf`` and do NOT overwrite it --
see the "Known issue" note below.

Data sources (reproducible from dataset/ alone, no live SAGA run needed):

- SAGA-predicted side: ``dataset/saga_direct_results.json`` (the ``random``
  subtree), produced by ``run_saga_direct_eval.py``. Each cell carries
  ``makespan_mean`` / ``makespan_std`` / ``n``.
- ncsim SH side: derived here from the per-seed makespan samples in
  ``dataset/random_eval_results.json`` (produced by ``run_random_eval.py``).
  This script also writes ``dataset/random_sh_results.json``
  (keys ``{density}|{dag}|{sched}|SH`` -> {mean, std, n}) so the canonical
  ``run_saga_direct_eval.py`` renderer can consume it too.

KNOWN ISSUE -- HEFT-1 bimodal makespan at sparse density (why the CIs are huge,
and why this figure differs from the published PDF):

  At large area side lengths (sparse networks), HEFT-1 large-DAG makespan under
  SH routing is BIMODAL: each random seed lands either in a "good" regime
  (~100-260 s) or a "bad" bottleneck regime (~1500-2850 s, a structural
  outcome). The MEAN of a bimodal distribution is not robust -- it swings on how
  many of the 30 seeds hit the bad mode (e.g. L400 large heft1 SH: median 264 s
  vs mean 1444 s; std > mean). Consequences:
    * The 95% CI bars here are very wide for HEFT-1 at L300-L500 -- this figure
      is generated specifically to make that instability visible.
    * The published ``saga_rand_large_vs_ncsim.pdf`` shows different HEFT-1
      MEANS (e.g. ~2557 s vs ~633 s at L500) because (a) the SAGA cache was
      regenerated after that figure was made and (b) the per-seed data behind
      it lived in /tmp and is gone -- so exact means are not byte-reproducible.
    * HEFT-2 reproduces cleanly (no penalty-path bimodality); the qualitative
      conclusion -- SAGA under-predicts makespan, and the gap widens as the
      network gets sparser -- is robust across seed draws.

  The paper therefore retains the original published figure; this ``_ci``
  variant is shipped as reproducible, error-bar-annotated supporting evidence.

Output PDFs go to ncsim/docs/paper-milcom26/ (graphicspath {.}).
"""
from __future__ import annotations
import json
import math
import os
import statistics

import matplotlib

matplotlib.use("pdf")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.dirname(HERE)
DATASET = os.path.join(PAPER, "dataset")
RANDOM_JSON = os.path.join(DATASET, "random_eval_results.json")
SAGA_JSON = os.path.join(DATASET, "saga_direct_results.json")
SH_JSON = os.path.join(DATASET, "random_sh_results.json")

DENSITIES = ["L150", "L200", "L250", "L300", "L350", "L400", "L500"]
DEGREES = [int(dl[1:]) for dl in DENSITIES]   # side lengths (m), x-axis
RAND_DAGS = ["small", "large"]

SCHED_NAMES = {"heft1": "HEFT-1", "heft2": "HEFT-2"}
COLORS = {"heft1": "#1a9641", "heft2": "#d7191c"}
MARKERS = {"heft1": "s", "heft2": "^"}
EFMT = dict(capsize=3, capthick=0.8, elinewidth=0.8, alpha=0.5)


def _ci95(std, n):
    """95% CI half-width matching run_saga_direct_eval.py (t=2.045 for n<=30)."""
    if n <= 1:
        return std
    t = 2.045 if n <= 30 else (2.009 if n <= 60 else 1.96)
    return t * std / math.sqrt(n)


def build_sh_results(random_json):
    """ncsim SH makespan stats per (density, dag, sched): {mean, std, n}."""
    with open(random_json) as f:
        d = json.load(f)
    perseed = d["perseed"]
    out = {}
    for dl in DENSITIES:
        for dag in RAND_DAGS:
            for sk in ("heft", "heft1", "heft2"):
                cell = perseed.get(f"{dl}|{dag}|{sk}|SH")
                if not cell:
                    continue
                ms = cell["ms"]
                out[f"{dl}|{dag}|{sk}|SH"] = {
                    "mean": statistics.mean(ms),
                    "std": statistics.stdev(ms) if len(ms) > 1 else 0.0,
                    "n": len(ms),
                }
    return out


def make_fig2(rand_res, ncsim_rand):
    for dag in RAND_DAGS:
        fig, ax = plt.subplots(figsize=(6.5, 3.8))
        for sched in ("heft1", "heft2"):
            n = rand_res[DENSITIES[0]][dag].get(sched, {}).get("n", 30)
            saga_ys = [rand_res[dl][dag].get(sched, {}).get("makespan_mean", 0)
                       for dl in DENSITIES]
            saga_errs = [_ci95(rand_res[dl][dag].get(sched, {}).get("makespan_std", 0), n)
                         for dl in DENSITIES]
            ncsim_ys, ncsim_errs = [], []
            for dl in DENSITIES:
                entry = ncsim_rand.get(f"{dl}|{dag}|{sched}|SH", {})
                ncsim_ys.append(entry.get("mean") or 0)
                ncsim_errs.append(_ci95(entry.get("std", 0), entry.get("n", 30)))
            ax.errorbar(DEGREES, saga_ys, yerr=saga_errs,
                        color=COLORS[sched], marker=MARKERS[sched],
                        linewidth=1.8, markersize=5, linestyle="-",
                        label=f"{SCHED_NAMES[sched]} (SAGA)", **EFMT)
            efmt_ncsim = {k: v for k, v in EFMT.items() if k != "alpha"}
            ax.errorbar(DEGREES, ncsim_ys, yerr=ncsim_errs,
                        color=COLORS[sched], marker=MARKERS[sched],
                        linewidth=1.4, markersize=4, linestyle="--",
                        label=f"{SCHED_NAMES[sched]} (NCSIM SH)", alpha=0.65,
                        **efmt_ncsim)
        ax.set_xlabel("Area side length (m)", fontsize=10)
        ax.set_ylabel("Makespan (s)", fontsize=10)
        ax.set_title(f"Random — {dag.capitalize()} DAG — SAGA vs NCSIM (SH), 95% CI",
                     fontsize=10)
        ax.legend(fontsize=7, ncol=2, loc="upper left")
        ax.grid(alpha=0.3)
        if dag == "large":
            ax.annotate(
                "Wide CIs: HEFT-1 makespan is bimodal at sparse density\n"
                "(median ≪ mean); the mean is not a robust statistic.",
                xy=(0.985, 0.03), xycoords="axes fraction", ha="right", va="bottom",
                fontsize=6.5, color="#444",
                bbox=dict(boxstyle="round,pad=0.3", fc="#fff7e6", ec="#d0a040",
                          lw=0.6, alpha=0.9))
        fig.tight_layout()
        out = os.path.join(PAPER, f"saga_rand_{dag}_vs_ncsim_ci.pdf")
        fig.savefig(out)
        plt.close(fig)
        print(f"Wrote {out}")


def main():
    ncsim_rand = build_sh_results(RANDOM_JSON)
    with open(SH_JSON, "w") as f:
        json.dump(ncsim_rand, f, indent=2)
    print(f"Wrote {SH_JSON} ({len(ncsim_rand)} cells)")

    with open(SAGA_JSON) as f:
        rand_res = json.load(f)["random"]

    make_fig2(rand_res, ncsim_rand)


if __name__ == "__main__":
    main()

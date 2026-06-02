# IEEE Milcom 2026 paper

**Title:** Scheduling Edge Computing in the Presence of Wireless Interference
**Authors:** Maya Gutierrez (USC), Jared Coleman (LMU), Bhaskar Krishnamachari (USC)

## Files

- `main.tex` — IEEEtran two-column conference paper
- `references.bib` — bibliography
- `build.bat` — Windows build (`pdflatex`, `bibtex`, `pdflatex` x2)
- `scripts/` — experiment runners and figure renderers (see below)
- `dataset/` — cached results for the renderers

## Building the paper

```
build.bat
```
or
```
pdflatex main && bibtex main && pdflatex main && pdflatex main
```

The paper uses `\graphicspath{{.}}`, so the figure PDFs must sit in
this directory (`ncsim/docs/paper-milcom26/`) alongside `main.tex`. The
figures referenced by `main.tex` are: `saga_rand_large_vs_ncsim.pdf`,
`penalty_sweep.pdf`,
`dag_scaling_{L150,L500,7x7}.pdf`, `density_hops_large.pdf`,
`density_plu_large.pdf`, `noint_density_large.pdf`,
`commcomp_sweep.pdf`.

# Reproducibility package

## Layout

- `scripts/` — experiment runners (`run_*.py`) that call ncsim, plus
  renderers (`gen_*.py`, `generate_paper_figures.py`,
  `regen_density_figs.py`) that turn raw results into the paper's PDFs
  and TeX fragments.
- `dataset/` — cached results: full per-seed JSONs for the new
  experiments and aggregate `.tex` tables for the older experiments.

## Reproducibility hierarchy

1. **Experiment runners (`scripts/run_*.py`)** are the canonical
   reproducibility artifact. They call ncsim with the paper's network,
   DAG, scheduler, routing, and interference settings; re-running them
   from a clean checkout regenerates the raw per-seed numbers.
2. **Renderers** (`scripts/generate_paper_figures.py`,
   `scripts/gen_*.py`, `scripts/regen_density_figs.py`) convert raw
   numbers into the paper's figures and tables. Required only if you
   want byte-identical PDFs.
3. **Cached data (`dataset/`)** lets the renderers run without re-doing
   the experiments. Coverage is mixed (see "What's reproducible from
   `dataset/` alone" below).

## Mapping: paper item → runner → renderer → data

| Paper item | Runner | Renderer | Data we have |
|---|---|---|---|
| Table III (grid HEFT predicted vs ncsim) | `run_table_cis.py` (ncsim cols) + `run_saga_direct_eval.py` (predicted cols) | `generate_paper_figures.py` | `table_ci_results.json` (full per-seed); `saga_direct_results.tex` (aggregate predicted) |
| Table IV (routing win counts) | `run_dag_scaling_eval.py` | `gen_dag_scaling_report.py` | `dag_scaling_results.tex` (aggregate) |
| Table V (L150/L300/L500 aux metrics) | Hops/PLU: `run_random_eval.py`; Makespan: `run_table_cis.py` | Hops/PLU: `gen_random_network_report.py`; Makespan: `generate_paper_figures.py` | Hops/PLU: `random_network_results.tex` (aggregate); Makespan: `table_ci_results.json` |
| Fig 2 `saga_rand_large_vs_ncsim.pdf` | `run_random_eval.py` (ncsim/SH half) + `run_saga_direct_eval.py` (SAGA half) | `gen_fig2_saga_vs_ncsim.py` (data-backed `_ci` variant); `run_saga_direct_eval.py` (live) | `random_eval_results.json` (per-seed) + `saga_direct_results.json` (per-seed). **See "Known issue: Fig 2 HEFT-1 bimodality" below** |
| Fig 3 `penalty_sweep.pdf` *(NEW)* | `run_penalty_sweep.py` | `generate_paper_figures.py` | `penalty_sweep_results.json` (full per-seed) |
| Fig 4 `dag_scaling_{L150,L500,7x7}.pdf` | `run_dag_scaling_eval.py` | `gen_dag_scaling_report.py` | `dag_scaling_results.tex` (aggregate) |
| Fig 5 `density_hops_large.pdf` | `run_random_eval.py` | `regen_density_figs.py` | `random_eval_results.json` (per-seed; **CI error bars**) |
| Fig 6 `density_plu_large.pdf` | `run_random_eval.py` | `regen_density_figs.py` | `random_eval_results.json` (per-seed; **CI error bars**) |
| Fig 7 `noint_density_large.pdf` | `run_no_interference_eval.py` | `regen_density_figs.py` | `no_interference_results.json` (per-seed; **CI error bars**) |
| Fig 8 `commcomp_sweep.pdf` *(NEW)* | `run_commcomp_sweep.py` | `generate_paper_figures.py` | `commcomp_sweep_results.json` (full per-seed) |

Tables I and II are pure prose; nothing to reproduce.

## Known issue: Fig 2 HEFT-1 bimodality

The paper ships the **original published** `saga_rand_large_vs_ncsim.pdf`.
A data-backed, error-bar-annotated variant
(`saga_rand_large_vs_ncsim_ci.pdf`, plus the `small` companion) is
produced by `scripts/gen_fig2_saga_vs_ncsim.py` and shipped as
supporting evidence. The two differ in the HEFT-1 curves, and the
reason is a genuine statistical instability worth documenting:

- **HEFT-1 large-DAG makespan under SH routing is bimodal at sparse
  density.** Each random seed lands either in a "good" regime
  (~100–260 s) or a "bad" bottleneck regime (~1500–2850 s, a structural
  outcome of where the penalty-path lands). The mean of a bimodal
  distribution is not robust: it swings on how many of the 30 seeds hit
  the bad mode. E.g. L400 large HEFT-1 SH: **median 264 s vs mean
  1444 s** (std > mean).
- **Consequence for the figure.** The 95% CI bars in the `_ci` variant
  are very wide for HEFT-1 at L300–L500 — the variant exists
  specifically to make that instability visible. The published PDF
  shows different HEFT-1 *means* (e.g. ~2557 s vs ~633 s at L500)
  because (a) the SAGA cache was regenerated after that figure was made
  and (b) the per-seed data behind the published figure lived in `/tmp`
  and is gone, so the exact published means are not byte-reproducible.
- **What is robust.** HEFT-2 reproduces cleanly (no penalty-path
  bimodality), and the paper's qualitative conclusion — SAGA
  under-predicts makespan, and the gap widens as the network gets
  sparser — holds across seed draws regardless of which HEFT-1 mean you
  use. The published figure is therefore retained; the `_ci` variant is
  the reproducible, error-bar-annotated evidence for the same claim.

## What's reproducible from `dataset/` alone (no rerun needed)

Running just the renderer regenerates the paper artifact:

- **Fig 3** (penalty sensitivity) — `python scripts/generate_paper_figures.py`
  reads `dataset/penalty_sweep_results.json`.
- **Fig 8** (comm/comp ratio) — same renderer, reads
  `dataset/commcomp_sweep_results.json`.
- **Table III** ncsim columns and **Table V** Makespan column — same
  renderer reads `dataset/table_ci_results.json` and emits TeX
  fragments.
- **Figs 5, 6** (density hops/PLU) — `python scripts/regen_density_figs.py`
  reads per-seed samples from `dataset/random_eval_results.json` and
  draws 95% CI error bars.
- **Fig 7** (no-interference baseline) — same renderer reads per-seed
  makespan samples from `dataset/no_interference_results.json`, also
  with 95% CI error bars.
- **Fig 4** (DAG scaling) — `python scripts/gen_dag_scaling_report.py`
  reads `dataset/dag_scaling_results.json` and writes the three
  `dag_scaling_{L150,L500,7x7}.pdf` panels.
- **Fig 2 evidence variant** — `python scripts/gen_fig2_saga_vs_ncsim.py`
  reads `dataset/random_eval_results.json` + `dataset/saga_direct_results.json`
  and writes the `_ci` error-bar variant (the published figure is retained).

## Recently regenerated (per-seed JSONs now in `dataset/`)

The following were re-run in May 2026 against the current ncsim engine
and their per-seed outputs are now committed:

| Paper item | Runner re-run | Per-seed JSON |
|---|---|---|
| Table IV / Fig 4 | `scripts/run_dag_scaling_eval.py` | `dataset/dag_scaling_results.json` |
| Table III ncsim grid verification | `scripts/run_routing_eval.py` | `dataset/routing_eval_results.json` |
| Table III predicted columns + Fig 2 SAGA curves | `scripts/run_saga_direct_eval.py` | `dataset/saga_direct_results.json` |
| Table V Hops/PLU + Figs 5/6 + Fig 2 ncsim half | `scripts/run_random_eval.py` (~10–15 h) | `dataset/random_eval_results.json` |
| Fig 7 per-seed CIs | `scripts/run_no_interference_eval.py` (~15+ h) | `dataset/no_interference_results.json` |

The last two are the largest experiments (10+ hours each on the
reference machine); their per-seed outputs are now committed, so the
figures redraw with real 95% CI error bars without a rerun.

When rerunning any of these, note that `OUTDIR` in each script reads
`/tmp/...` — on Windows Python this resolves to `C:\tmp\...`. After the
run completes, copy the result JSON into `dataset/`.

## Quickstart

Every figure the paper embeds is regenerable from the committed
`dataset/` JSONs alone — no experiment rerun and no ncsim install needed.
All four renderers read from `dataset/` and write the figure PDFs into
this directory (`paper-milcom26/`), where `\graphicspath{{.}}` finds
them. From the repository root (one directory above `docs/`):

```bash
P=docs/paper-milcom26/scripts
python $P/generate_paper_figures.py   # Fig 3 penalty_sweep.pdf, Fig 8 commcomp_sweep.pdf
                                      #   + Table III/V CI fragments -> dataset/*.tex
python $P/regen_density_figs.py       # Fig 5 density_hops_large, Fig 6 density_plu_large,
                                      #   Fig 7 noint_density_large  (all 95% CI)
python $P/gen_dag_scaling_report.py   # Fig 4 dag_scaling_{L150,L500,7x7}.pdf
python $P/gen_fig2_saga_vs_ncsim.py   # Fig 2 evidence variant saga_rand_{large,small}_vs_ncsim_ci.pdf

# Rebuild the paper PDF
cd docs/paper-milcom26 && pdflatex main && pdflatex main
```

Notes:
- **Fig 2** in the paper is the original published `saga_rand_large_vs_ncsim.pdf`
  (kept as-is; not overwritten by any renderer — see "Known issue" above).
  `gen_fig2_saga_vs_ncsim.py` produces only the `_ci` evidence variant.
- `gen_dag_scaling_report.py` also compiles a standalone `.tex` report into
  a throwaway temp dir; the embedded Fig 4 panels are what the paper uses.
- `gen_random_network_report.py` and `gen_no_interference_report.py` are
  supplementary full-report generators that need an uncommitted
  `*_augmented.json` from a fresh runner pass; they are NOT required for any
  embedded figure (see their module docstrings).

To regenerate raw experimental data, install the ncsim package
(`pip install -e .`) and run any of the `scripts/run_*.py` files. Each
script prints a console summary and writes a JSON or per-seed metrics
tree to its `OUTDIR`.

## Settings used in the paper

- **Interference model:** `csma_bianchi` (802.11ax DCF, 5 GHz, 20 MHz channel,
  $P_\mathrm{tx}=20$ dBm, path-loss exponent 3, noise floor $-95$ dBm,
  CCA threshold $-82$ dBm, no RTS/CTS).
- **Compute costs:** heterogeneous in $[150, 1000]$ cu; data sizes $[2, 30]$ MB;
  node capacities $[80, 300]$ cu/s.
- **Topology seed:** `TOPO_SEED=42` for the random geometric graphs (50 nodes,
  comm range 80 m, side length varied).
- **Replication:** 30 seeds for grid and random density experiments, 20 seeds
  for DAG-scaling and comm/comp sweeps.
- **HEFT-1 non-adjacent penalty:** 0.001 MB/s (sweep results in Fig 3 show
  the choice is robust across $10^{-4}$–$10^{-1}$ MB/s).

The exact YAML scenarios are generated programmatically inside each
`run_*.py`; see the `make_yaml()` and `make_dag_*()` helpers.

## Things to verify before submission

1. All entries in `references.bib` (titles, page ranges, years). Per the
   project's citation-integrity rule (`CLAUDE.md`), no DOIs from memory.
2. Author affiliations and emails (currently no email fields).

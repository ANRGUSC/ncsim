# MILCOM 2026 placement and routing artifact

This folder contains the scenarios, recorded results, and existing experiment
and analysis code for:

> M. Gutierrez, J. Coleman, and B. Krishnamachari, "Locality versus
> Widest-Path for DAG Scheduling under Wireless Edge Interference," IEEE
> MILCOM 2026.

The package is intentionally limited to material needed to reconstruct the key
placement, routing, and ablation results in the paper. It does not include the
manuscript, review correspondence, literature PDFs, LaTeX build products,
temporary simulator output, or superseded experiment files.

## Contents

- `dataset/rev1_manifest.json` records the exact accepted and rejected topology
  seeds, node and link definitions, DAG tasks and edges, experiment design, and
  simulator commit.
- `dataset/rev1_results.json` contains the 7,140 successful design-version-2
  run records used by the revised analysis. Workstation-only output paths and
  superseded pre-revision records have been removed; numerical fields are
  unchanged.
- `scripts/run_rev1_experiments.py` defines the scheduler, routing, and ablation
  sweeps and regenerates each per-run YAML scenario.
- `scripts/rev1_common.py` contains the deterministic topology, workload,
  placement, and ncsim invocation logic.
- `scripts/analyze_rev1.py` regenerates the reported confidence intervals,
  table fragments, and four principal figures from the recorded results.
- `scripts/run_saga_direct_eval.py` is an existing helper imported by the
  revision infrastructure.
- `scripts/test_rev1_common.py` checks the radius-limited random graphs and the
  LC-HEFT placement constraint.

The generated YAML files are not duplicated here. They are deterministic
expansions of the topology and workload definitions in the manifest and are
written under `tmp/rev1_runs/_inputs` by the runner.

## Environment used

- Python 3.12.10
- ncsim commit `18b88aa227c354ee7f60551ed97d61ffc031fa5e`
- anrg-saga 2.0.3
- NumPy 2.4.3 and Matplotlib 3.10.8 for the recorded analysis

The paper-specific routing modes are preserved at the pinned ncsim commit but
are not present on current `main`. Create a detached worktree for the exact
simulator source before running the tests, analysis, or experiments:

```bash
git fetch origin dev-mg
git worktree add ../ncsim-milcom26-simulator 18b88aa227c354ee7f60551ed97d61ffc031fa5e
python -m pip install "anrg-saga==2.0.3"
python -m pip install -e ../ncsim-milcom26-simulator/ncsim
python -m pip install "numpy==2.4.3" "matplotlib==3.10.8" "pytest==9.0.2"
export NCSIM_SOURCE="$(cd ../ncsim-milcom26-simulator/ncsim && pwd)"
```

In PowerShell, set the last variable with
`$env:NCSIM_SOURCE=(Resolve-Path ..\ncsim-milcom26-simulator\ncsim).Path`.
The explicit source path prevents the current `main` package from shadowing
the pinned implementation.

## Reconstruct the reported analysis

From the root of a current ncsim clone:

```bash
python -m pytest experiments/milcom26/scripts/test_rev1_common.py -q
python experiments/milcom26/scripts/analyze_rev1.py
```

The analysis reads the committed result records and writes
`rev1_summary.json`, the two LaTeX table fragments, and the placement and
routing figures within `experiments/milcom26`. This step does not rerun the
simulations.

## Re-run simulations

The experiment runner is resumable by run ID and requires `PYTHONHASHSEED=0`.
Use a working copy if starting from an empty result file. The modes used for the
paper are:

```bash
PYTHONHASHSEED=0 python experiments/milcom26/scripts/run_rev1_experiments.py --mode scheduler --workers 8
PYTHONHASHSEED=0 python experiments/milcom26/scripts/run_rev1_experiments.py --mode table --workers 8
PYTHONHASHSEED=0 python experiments/milcom26/scripts/run_rev1_experiments.py --mode routing --workers 8
PYTHONHASHSEED=0 python experiments/milcom26/scripts/run_rev1_experiments.py --mode ablations --workers 8
```

In PowerShell, set `$env:PYTHONHASHSEED='0'` once and omit the leading
assignment from each command.

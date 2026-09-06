# ncsim study artifact: arXiv 2605.01094

This directory contains the inputs, saved observations, and reproduction tools
for *ncsim: A Lightweight Simulator for Networked Edge Computing with Wireless
Interference Modeling*. Its home is the
[`paper` branch](https://github.com/ANRGUSC/ncsim/tree/paper/artifacts/arxiv-2605.01094).
Record `git rev-parse HEAD` when using this artifact: the branch is a moving
pointer. The manifest identifies the separately tested shared implementation;
the provenance records identify the recovered observation-producing source.

## Layout

- `ncsim_arxiv.pdf`: current compiled manuscript.
- `inputs/`: frozen topology/workload generators and packet settings.
- `results/workflows.json`: 108 grid, 42 payload-sensitivity, and ten concurrent-workflow observations.
- `results/packet/`: seed-level CSV observations, separated by measurement configuration.
- `scripts/`: workflow execution, model checks, statistical analysis, and plotting.
- `ns3/`: byte-preserved packet-experiment C++ sources and explicit rerun instructions.
- `manuscript/`: the LaTeX manuscript and its referenced figure/table dependencies.
- `MANIFEST.json`: artifact and repository-source hashes, with separate default/optional model identities.
- `provenance.json`: source hashes and the selections used to prepare the records and helper functions.
- `environment.json`: the recorded workflow environment and the figure-build package versions.

The simulator is the repository's top-level `ncsim/` package, not a second copy
inside this folder. Use the complete repository checkout at the desired commit.
The manuscript-only source ZIP is for LaTeX compilation, not simulation replay.
`verify` refuses missing or changed files.

## Environment

The workflow observations used Python 3.12.10, `anrg-saga==2.0.3`, seed 42,
and `PYTHONHASHSEED=0`. Keep this SAGA version for replay; the runtime command
sets the hash seed before importing the scheduler. The simulator supports 22
SAGA static schedulers in this environment. PEFT is exposed with SAGA versions
that provide it, but PEFT is not part of this study's comparisons.

In a Python 3.12 virtual environment, install `requirements.txt` from this
directory. Commands import the matching top-level simulator directly; an
editable installation of another checkout is not required. `paper` additionally
requires `pdflatex` and IEEEtran, with the LaTeX packages named in the manuscript.
The packet experiments use ns-3.41 and are separate from the Python commands.

## Commands

From this directory:

```text
python reproduce.py verify
python reproduce.py figures
python reproduce.py workflows --smoke
python reproduce.py workflows
python reproduce.py hidden
python reproduce.py paper
```

`verify` checks hashes and reported workflow counts without executing simulations.
`figures` uses saved workflow and packet observations, recomputes the small
internal flow checks and fixed-capture validation, and regenerates numerical
tables and plots. Architecture artwork and the PHY illustration are supplied
assets. All regenerated numerical tables must match the supplied table files.
`workflows --smoke` runs ten selected executions and compares their scientific
outputs with the saved observations. Without `--smoke`, `workflows` runs exactly
the 160 executions reported in the manuscript, not any additional campaign.
`hidden` checks 16 two-link separations and eight homogeneous-contention settings
in both default and optional modes against saved packet observations.
`paper` compiles the supplied manuscript and figures and creates a standalone
source ZIP; it does not run experiments.

Outputs default to `output/arxiv-artifact/` at the repository root. Use
`--output PATH` to choose another output directory. Generated results never
replace the saved artifact observations or manuscript. Reusing an output
directory replaces its generated products. The original generator files in
`inputs/` are loaded only for their topology/DAG functions; do not execute their
standalone driver entry points. `reproduce.py workflows` supplies the study's
Solo/Full modes, routes, and executor.

## Measurement conventions and provenance

`results/packet/main/` contains 480 configuration-seed CSVs: eight contention
settings and 16 fixed-MCS separation settings, each with 20 seeds. Traffic starts
at 0.5 s and stops at 30 s; the goodput denominator is 29.5 s. Links are averaged
within each seed before computing a mean and Student-t 95% interval across seeds.

The supplementary groups are `short_contention/` (eight settings, 4.5 s window),
`overlapping/` (three links, 4.5 s window), `rate_overhead/` (four MCS/RTS settings,
5 s window), and `dynamic/` (two geometries, 0.1 s bins and prespecified windows).
Each setting has 20 seeds. Do not combine groups with different windows.

Copied CSVs and frozen input files retain their original bytes. The workflow
file is an extraction of the three reported record arrays with the original
provenance object retained. The analysis file excludes unused analysis branches;
the parent file hashes and selections are recorded in `provenance.json`.
Recorded source hashes describe the observation-producing implementation;
the manifest separately describes the packaged source and reproduction tools.
No new observations are substituted for the saved measurements during packaging.

## Publication

The current manuscript is in `manuscript/`. The earlier public paper tree is
archived at the repository root in `arxiv-old/`; it is not the current source.
No tag or release is required for these commands. Use a commit-pinned checkout
when recording a reproduction attempt.

`provenance/recorded-simulator.zip` contains all 24 source files and the workflow
driver whose bytes match the hashes saved with the workflow observations. It is
a reference archive, not a second runnable package. The exact historical commit
and full environment are not established by those hashes. See
`provenance/recorded-source.json` for the recovered record and its limits.

The final implementation adds the opt-in fixed-capture path, CLI normalization
and status corrections, and a scheduler catalog classification correction.
Line endings are normalized in executable source. These changes are distinct
from the recorded source; compatibility is assessed by regression tests and
bounded replay, not asserted from an identical source snapshot. Packet CSVs,
workflow observations, scientific manuscript text, and supplied numeric tables
are preserved. A smoke replay is not a full research-campaign reproduction.

Run `python -m pytest artifacts/arxiv-2605.01094/tests` from the repository
root for artifact checks (requires pytest).
No public link or tag is claimed by this local package.

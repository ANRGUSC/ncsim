# Contributing to ncsim

Thank you for helping improve ncsim. Contributions are welcome for simulator
behavior, tests, scenarios, documentation, experiment tooling, and the
visualization application.

## Development setup

ncsim requires Python 3.12 or later.

```bash
git clone https://github.com/ANRGUSC/ncsim.git
cd ncsim
python -m venv .venv
python -m pip install -e ".[dev]"
python -m pip install -r viz/server/requirements.txt
```

Activate the virtual environment using the command appropriate for your shell,
then verify the checkout:

```bash
python -m pytest
ncsim --scenario scenarios/demo_simple.yaml --output results/contributor-smoke
```

See [DEVELOPMENT.md](DEVELOPMENT.md) for the package layout, design decisions,
trace format, SAGA adapter notes, and common development errors.

## Making a change

1. Create a focused branch from the latest `main`.
2. Keep the change scoped and add tests for behavior changes.
3. Update user documentation when CLI, YAML, output, or visualization behavior
   changes.
4. Add a concise entry under `Unreleased` in [CHANGELOG.md](CHANGELOG.md) when
   the change is user-visible.
5. Run the relevant checks locally before opening a pull request.

The principal implementation areas are:

| Area | Main locations |
|---|---|
| Simulation and event handling | `ncsim/core/` |
| Network, routing, Wi-Fi, and interference | `ncsim/models/` |
| Scheduling and SAGA adaptation | `ncsim/scheduler/` |
| Scenario and result formats | `ncsim/io/` |
| Command-line behavior | `ncsim/main.py` |
| Documentation and examples | `docs/`, `scenarios/` |
| Visualization | `viz/` |

When adding or changing a model, update its factory or registry, CLI and YAML
validation, tests, and documentation together so every interface exposes the
same behavior.

## Validation

Run the Python suite:

```bash
python -m pytest
```

Validate the documentation:

```bash
python -m pip install mkdocs-material mkdocs-glightbox mkdocs-print-site-plugin
python -m mkdocs build --strict
```

Validate Python distributions:

```bash
python -m pip install build twine
python -m build
python -m twine check dist/*
```

For visualization changes:

```bash
cd viz
npm install
npm run lint
npm run build
```

CI repeats the Python-version matrix, distribution build, clean wheel smoke
test, documentation validation, and Codespaces integration checks.

## Release metadata

`pyproject.toml` is the authoritative Python package version. The Python API,
CLI, and visualization backend read that installed metadata. At release time,
maintainers also update `CITATION.cff`, `viz/package.json`, and
`viz/package-lock.json`; automated tests check that these versions agree.

Do not create tags or publish packages as part of an ordinary contribution.
Release publication is handled separately by project maintainers.

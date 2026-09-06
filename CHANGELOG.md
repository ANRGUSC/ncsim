# Changelog

All notable changes to ncsim are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Simulator synchronization

- Correct event-time byte accounting, task serialization, directed interference
  notifications, rate-aware MAC normalization, and minimum-hop routing.
- Add canonical Raw/Solo/Full wireless setup and an explicit, scope-checked
  `fixed_capture_overlap` option; the default hidden treatment is unchanged.
- Add static conflict-aware, uniform-discount, and all-on-fastest placements;
  retain the remote SAGA catalog, including conditional PEFT support.
- Support the recorded SAGA 2.0.3 environment and restrict wheel discovery to
  the `ncsim` package. Regression tests do not require private paper folders.
- Report non-completed CLI runs through a nonzero exit status.

### Added

- Python-version test coverage and clean wheel-install validation in CI.
- Strict documentation validation before GitHub Pages deployment.
- Contributor guidance and machine-checked release metadata consistency.

### Changed

- The Python API, CLI, and visualization backend now read the installed package
  version instead of maintaining separate constants.
- Project metadata, citation information, README links, and contributor credits
  now reflect the current scope of ncsim.

## [1.1.0] - 2026-08-14

### Added

- Version-aware integration with the SAGA static scheduling catalog: 22
  compatible algorithms with PyPI SAGA 2.0.4 and PEFT when SAGA 2.1.0 is
  installed.
- Typed constructor options for configurable SAGA schedulers.
- Multi-hop widest-path and shortest-path routing.
- 802.11n/ac/ax PHY rates, RF-derived link bandwidths, CSMA clique modeling,
  and dynamic Bianchi interference modeling.
- React and FastAPI visualization workflow for configuring, running, browsing,
  and replaying experiments.
- GitHub Codespaces setup, demonstration run, and integration checks.
- Expanded MkDocs guide, tutorials, scenario reference, and standalone
  "Why ncsim?" introduction.

### Changed

- ncsim now requires Python 3.12 or later.
- The base dependency accepts PyPI `anrg-saga>=2.0.4`; SAGA 2.1.0 remains an
  optional tagged-source installation for PEFT.

## [1.0.0] - 2026-03-20

### Added

- Initial public release of the deterministic discrete-event simulation core,
  YAML scenarios, CLI, scheduling adapter, routing and interference models,
  trace analysis, tests, and documentation.

[Unreleased]: https://github.com/ANRGUSC/ncsim/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/ANRGUSC/ncsim/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/ANRGUSC/ncsim/releases/tag/v1.0.0

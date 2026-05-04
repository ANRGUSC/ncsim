# IEEE Milcom 2026 paper

**Title:** Scheduling Edge Computing in the Presence of Wireless Interference

**Authors:** Maya Gutierrez (USC), Jared Coleman (LMU), Bhaskar Krishnamachari (USC)

## Files

- `main.tex` — IEEEtran two-column conference paper
- `references.bib` — bibliography (verify entries before submission)
- `build.bat` — Windows build script (`pdflatex`, `bibtex`, `pdflatex` x2)

## Building

From this directory:

```
build.bat
```

This produces `main.pdf`.

On a Unix shell with TeX Live installed:

```
pdflatex main && bibtex main && pdflatex main && pdflatex main
```

## Figures

The paper uses `\graphicspath{{../}}` and references PDFs that already exist
one directory up in `ncsim/docs/`:

- `saga_grid_vs_ncsim.pdf`
- `saga_rand_large_vs_ncsim.pdf`
- `dag_scaling_L150.pdf`, `dag_scaling_L500.pdf`, `dag_scaling_7x7.pdf`
- `density_hops_large.pdf`, `density_plu_large.pdf`
- `noint_density_large.pdf`

No figure regeneration is needed.

## Source data

The paper distills numbers and figures from these existing reports in
`ncsim/docs/`:

- `saga_direct_results.tex` — HEFT-1 vs HEFT-2 SAGA-vs-ncsim (Sec. V-A)
- `dag_scaling_results.tex` — DAG-size scaling, 9 routing schemes (Sec. V-B)
- `random_network_results.tex` — auxiliary metrics on density sweep (Sec. V-C)
- `no_interference_results.tex` — no-interference baseline (Sec. V-D)
- `routing_schemes.tex` — formal definitions of W, S, SH, GS, GC, GB, GO, GSD, GSD-D

## Things to verify before submission

1. All entries in `references.bib` (titles, page ranges, years). Per the
   project's citation-integrity rule (`CLAUDE.md`), no DOIs are listed yet;
   they must be added from authoritative sources (Crossref, publisher pages)
   rather than from memory.
2. Page count. Target is 6 pages for IEEE Milcom; first draft is allowed to
   be slightly longer for trimming.
3. Author affiliations and emails (currently no email fields).

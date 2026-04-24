# arXiv Submission Package

Self-contained source tree for uploading the `ncsim` paper to arXiv.

## Contents

- `ncsim_paper.tex` - main LaTeX source (full author version with
  acknowledgments)
- `ncsim_refs.bib` - bibliography source (uses inline `\bibitem{}` in
  the `.tex`; this file is kept as a parallel record)
- `figures/` - all figure files referenced by the paper

## Build

```
pdflatex ncsim_paper.tex
pdflatex ncsim_paper.tex
```

Two passes are sufficient because the bibliography is inline; no
BibTeX invocation is required.

## Upload to arXiv

Create a tarball of this directory and upload as the source:

```
tar -czf ncsim_arxiv.tar.gz ncsim_paper.tex ncsim_refs.bib figures/
```

arXiv will run pdflatex automatically. Primary category: `cs.DC`
(Distributed, Parallel, and Cluster Computing). Suggested cross-lists:
`cs.NI` (Networking and Internet Architecture), `cs.PF` (Performance).

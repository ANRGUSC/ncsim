# SEC Anonymous Submission

Double-blind-anonymized version of the `ncsim` paper for submission to
the ACM/IEEE Symposium on Edge Computing (SEC).

## Contents

- `ncsim_paper.tex` - main LaTeX source (anonymized)
- `ncsim_refs.bib` - bibliography source (uses inline `\bibitem{}` in
  the `.tex`; this file is kept as a parallel record)
- `figures/` - all figure files referenced by the paper

## Anonymization changes relative to the full version

- Author block replaced with `Anonymous Author(s)` / affiliation withheld
- Email addresses removed
- GitHub repository URL replaced with "URL withheld for double-blind
  review" (both the footnote in the introduction and the closing
  sentence of the conclusion)
- Acknowledgment section removed (funding agency and grant number
  would identify the author group)
- URL in the SAGA software citation removed (identifies authors' GitHub
  organization)

Citations to prior Coleman/Krishnamachari papers remain in the
references but are referred to only in the third person in the body
text, consistent with ACM/IEEE double-blind practice.

## Build

```
pdflatex ncsim_paper.tex
pdflatex ncsim_paper.tex
```

Two passes are sufficient because the bibliography is inline; no
BibTeX invocation is required.

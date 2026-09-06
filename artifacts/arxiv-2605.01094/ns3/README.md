# Packet experiments

These sources target ns-3.41. The `main/` sources match the 29.5-second
measurements in Figure 6. The `additional/` sources match the supplementary
packet configurations. Their contents are copied without edits, even where
the filenames differ when installed in ns-3's scratch directory.

No packet simulation is needed to compile the manuscript, regenerate plots
from saved CSVs, or check the Python flow model.

## Explicit rerun

From this directory, build `docker build -t ncsim-study-packets .`.
Mount an empty host output directory at `/results`, then run:

```text
docker run --rm -v ABSOLUTE_OUTPUT_PATH:/results ncsim-study-packets main --seed 1
```

Replace `main` with `short_contention`, `overlapping`, `rate_overhead`, or
`dynamic` for the other suites. Omit `--seed 1` only when intending to run all
20 seeds. Use a new output directory for each rerun; nonempty suite directories
are rejected. Do not mount the artifact's saved results directory as output.
`--dry-run` prints commands without creating outputs or executing ns-3.
The Docker recipe is supplied for rebuilding; this packaging pass did not
build its image or rerun packet simulations.

| Suite | Configurations | Traffic window | Goodput denominator |
| --- | --- | --- | --- |
| main | 8 contention + 16 fixed-MCS separations | 0.5 to 30 s | 29.5 s |
| short_contention | 8 contention settings | 0.5 to 5 s | 4.5 s |
| overlapping | 3 parallel links | 0.5 to 5 s | 4.5 s |
| rate_overhead | MCS 0/11, RTS off/on | 0.5 to 5.5 s | 5 s |
| dynamic | 40 m and 80 m separation | A: 0.5 to 5.5 s; B: 2 to 4 s | 0.1 s bins; specified windows |

Each setting uses seeds 1 through 20. The dynamic program runs until 6 s to
record post-source drainage. Its analysis uses the paper's stated bins and
stable windows. The full 29.5-second window must not be replaced with a short
pilot measurement when comparing with the saved Figure 6 observations.

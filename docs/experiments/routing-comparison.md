# Routing Comparison

The `run_routing_comparison.py` script compares **widest_path** vs
**shortest_path** routing under HEFT scheduling with `csma_bianchi` WiFi
interference. It runs 18 simulations across a grid of network sizes, DAG sizes,
and routing strategies, then prints detailed comparison tables.

---

## Running the Script

```bash
python run_routing_comparison.py
```

Output directory: `/tmp/ncsim_routing_comparison` (configurable via the `OUTDIR`
variable in the script).

---

## Experiment Design

The experiment is a full factorial design: **3 network sizes x 3 DAG sizes x
2 routing strategies = 18 simulations**.

All simulations use the same fixed configuration:

| Parameter | Value |
|---|---|
| Scheduler | HEFT |
| Interference model | `csma_bianchi` |
| Routing strategies | `widest_path`, `shortest_path` |
| Seed | 42 |
| Compute cost per task | 500 |
| Data size per edge | 10 MB |
| Grid spacing | 40m between adjacent nodes |

### Network Sizes

Networks are **grid meshes** with bidirectional links (grid edges + diagonals):

| Size | Grid | Nodes | Description |
|---|---|---|---|
| Small | 2x2 | 4 | Minimal grid |
| Medium | 3x3 | 9 | Moderate grid |
| Large | 4x4 | 16 | Larger grid |

!!! info "Grid topology details"
    - **Grid edges:** horizontal and vertical links between adjacent nodes
      (40m apart).
    - **Diagonal links:** added in a checkerboard pattern. Diagonal distance
      is approximately 56.6m (`40 * sqrt(2)`), which yields a different PHY
      rate than the 40m grid edges under the WiFi model.
    - **Bidirectional:** every undirected edge generates two directed links
      (`l_nA_nB` and `l_nB_nA`).
    - **Heterogeneous compute:** node compute capacities are cycled from a
      fixed list: `[200, 100, 150, 80, 300, 120, 250, 180, 160, 90, 220,
      140, 280, 110, 190, 170]`.

### DAG Sizes

| Size | Tasks | Pattern | Structure |
|---|---|---|---|
| Small | 5 | Fork-join | 1 source -> 3 parallel -> 1 sink |
| Medium | 10 | Diamond pipeline | 1 source -> 4 parallel -> 4 parallel (selective cross-connections) -> 1 sink |
| Large | 20 | Multi-level | 5 stages with branching: 1 -> 4 -> 6 -> 6 -> 3 |

All tasks have `compute_cost=500`. All edges have `data_size=10` MB.

---

## Output Format

The script produces three levels of output:

### Per-Network Tables

For each network size, a table comparing widest path vs shortest path makespan
across all DAG sizes:

```
  Network: 3x3 (9 nodes)
  ----------------------------------------------------------
  DAG Size      Widest(s)    Shortest(s)     Diff(%)
  small           X.XXXX       X.XXXX        +X.X%
  medium          X.XXXX       X.XXXX        -X.X%
  large           X.XXXX       X.XXXX        +X.X%
```

The `Diff(%)` column shows `(widest - shortest) / shortest * 100`. A negative
value means widest path achieved a lower (better) makespan.

### Summary Table

A compact matrix showing `widest/shortest` makespan pairs for every
(network, DAG) combination:

```
  Summary Table (makespan in seconds, W=widest / S=shortest):
                  2x2 (4 nodes)  3x3 (9 nodes)  4x4 (16 nodes)
  small DAG         W.WW/S.SS       W.WW/S.SS       W.WW/S.SS
  medium DAG        W.WW/S.SS       W.WW/S.SS       W.WW/S.SS
  large DAG         W.WW/S.SS       W.WW/S.SS       W.WW/S.SS
```

### Winner-Per-Cell Analysis

Identifies which routing strategy achieved the lower makespan in each cell,
with a tie threshold of 0.1%:

```
  Winner per cell (lower makespan):
                  2x2 (4 nodes)  3x3 (9 nodes)  4x4 (16 nodes)
  small DAG           WIDEST         SHORTEST         WIDEST
  medium DAG          WIDEST         WIDEST           WIDEST
  large DAG           WIDEST         WIDEST           TIE

  Wins: widest_path=7, shortest_path=1, ties=1
```

---

## Visualization

After running `run_routing_comparison.py`, generate side-by-side visual
comparisons with:

```bash
python visualize_routing_comparison.py
```

This generates one PNG figure per (network, DAG) combination (9 figures total)
in `/tmp/ncsim_routing_comparison/figures/`. Each figure has two columns
(widest vs shortest) with three rows:

| Row | Content |
|---|---|
| **Network topology** | Nodes and links colored/thickened by flow count. Unused links shown in gray. |
| **Gantt chart** | Timeline of task executions and data transfers per node. |
| **Link utilization** | Bar chart showing how many flows used each directed link. |

!!! tip "Reading the topology panels"
    - **Blue circles** are nodes that have tasks assigned to them.
    - **Gray circles** are unused nodes.
    - **Link color intensity** and **thickness** scale with the number of flows
      routed over that link.
    - Numbers on links show the bidirectional flow count.

---

## Interpreting Results

The relative performance of the two routing strategies depends on the
characteristics of the workload:

| Factor | Favors widest_path | Favors shortest_path |
|---|---|---|
| **Large data transfers** | Higher bandwidth routes reduce transfer time | -- |
| **Small data transfers** | -- | Fewer hops reduce end-to-end latency |
| **Dense interference** | Avoids congested links, finds higher-capacity paths | Minimizes exposure to interference by taking fewer hops |
| **Heterogeneous link rates** | Exploits fast links even if longer | May traverse slow links if they are topologically shorter |

### General Observations

- **Widest path** tends to win when transfers are bandwidth-dominated (large
  `data_size` relative to `compute_cost`), because it selects routes with the
  highest bottleneck bandwidth.
- **Shortest path** may win when transfers are latency-dominated (small
  `data_size`), because fewer hops mean fewer per-hop processing delays.
- The grid topology with diagonal links creates interesting routing choices:
  diagonal links are ~56.6m (lower PHY rate) vs grid edges at 40m (higher PHY
  rate), so widest path avoids diagonals while shortest path may prefer them.
- The `csma_bianchi` interference model adds realistic WiFi contention effects
  that penalize routes through high-traffic areas, which widest path is
  better at avoiding.

!!! warning "Simulation failures"
    If any of the 18 simulations fail (e.g., due to disconnected routes), the
    script reports the count of failures and exits with a non-zero return code.
    Check the stderr output printed for each failed run.

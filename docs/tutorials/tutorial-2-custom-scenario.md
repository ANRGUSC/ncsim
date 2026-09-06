# Tutorial 2: Build a Custom Scenario

This tutorial walks you through creating a complete ncsim scenario from scratch --
a 4-node mesh network with a fork-join DAG -- and running it with different
schedulers, routing algorithms, and interference models.

---

## What You Will Learn

- Design a network topology with heterogeneous compute capacities
- Create a task dependency graph (DAG) with fork-join parallelism
- Write a complete scenario YAML file
- Run and analyze your custom scenario
- Experiment with different schedulers, routing, and interference settings

## Prerequisites

- ncsim installed ([Tutorial 1](tutorial-1-first-sim.md))
- Familiarity with YAML syntax

---

## The Scenario

We will build a **4-node mesh network** arranged in a square. Each node has a
different compute capacity, and the links between them have varying bandwidths.
A **fork-join DAG** of 6 tasks will be scheduled across the network:

```
         T_src
       / | | \
     W0  W1 W2  W3
       \ | | /
        T_sink
```

One source task fans out to four parallel workers, which all fan back into a
single sink task.

---

## Step 1: Define the Network

Our 4 nodes form a square with 20-meter sides. Each node has a different compute
capacity to make scheduling decisions interesting:

```yaml
nodes:
  - id: n0
    compute_capacity: 200
    position: {x: 0, y: 0}
  - id: n1
    compute_capacity: 100
    position: {x: 20, y: 0}
  - id: n2
    compute_capacity: 150
    position: {x: 0, y: 20}
  - id: n3
    compute_capacity: 80
    position: {x: 20, y: 20}
```

!!! info "Compute Capacity"
    `compute_capacity` is in **compute units per second** (cu/s). A task with
    `compute_cost: 500` running on a node with `compute_capacity: 200` takes
    500 / 200 = **2.5 seconds** to complete.

The heterogeneous capacities create a tradeoff: n0 is the fastest node (200 cu/s),
but the scheduler must balance load across all nodes when there are more tasks than
n0 can handle sequentially.

---

## Step 2: Define the Links

A full mesh of 4 nodes requires 6 bidirectional connections, which means 12
directional links. We give each direction its own link with varying bandwidths
to create asymmetry:

```yaml
links:
  # n0 <-> n1 (horizontal top)
  - {id: l01, from: n0, to: n1, bandwidth: 500, latency: 0.001}
  - {id: l10, from: n1, to: n0, bandwidth: 500, latency: 0.001}
  # n0 <-> n2 (vertical left)
  - {id: l02, from: n0, to: n2, bandwidth: 400, latency: 0.001}
  - {id: l20, from: n2, to: n0, bandwidth: 400, latency: 0.001}
  # n0 <-> n3 (diagonal)
  - {id: l03, from: n0, to: n3, bandwidth: 300, latency: 0.002}
  - {id: l30, from: n3, to: n0, bandwidth: 300, latency: 0.002}
  # n1 <-> n2 (diagonal)
  - {id: l12, from: n1, to: n2, bandwidth: 300, latency: 0.002}
  - {id: l21, from: n2, to: n1, bandwidth: 300, latency: 0.002}
  # n1 <-> n3 (vertical right)
  - {id: l13, from: n1, to: n3, bandwidth: 400, latency: 0.001}
  - {id: l31, from: n3, to: n1, bandwidth: 400, latency: 0.001}
  # n2 <-> n3 (horizontal bottom)
  - {id: l23, from: n2, to: n3, bandwidth: 500, latency: 0.001}
  - {id: l32, from: n3, to: n2, bandwidth: 500, latency: 0.001}
```

!!! tip "Bandwidth Units"
    Bandwidth is in **MB/s** (megabytes per second). Latency is in **seconds**.
    Transfer time = `data_size / bandwidth + latency`.

The topology looks like this:

```
    n0 ---500--- n1
    |  \       / |
   400  300 300  400
    |  /       \ |
    n2 ---500--- n3
```

Side links (500 MB/s) are faster than diagonal links (300 MB/s), reflecting the
longer physical distance of the diagonals.

---

## Step 3: Design the DAG

The fork-join pattern is common in data-parallel workloads: a source task produces
data, four workers process it in parallel, and a sink task aggregates the results.

```yaml
tasks:
  - {id: T_src, compute_cost: 100}
  - {id: W0, compute_cost: 500}
  - {id: W1, compute_cost: 600}
  - {id: W2, compute_cost: 400}
  - {id: W3, compute_cost: 700}
  - {id: T_sink, compute_cost: 100}
```

The workers have **different compute costs** (400--700 cu), simulating uneven
workloads. This makes scheduling non-trivial -- a good scheduler should assign
heavier tasks to faster nodes.

```yaml
edges:
  # Fan-out: T_src sends 20 MB to each worker
  - {from: T_src, to: W0, data_size: 20}
  - {from: T_src, to: W1, data_size: 20}
  - {from: T_src, to: W2, data_size: 20}
  - {from: T_src, to: W3, data_size: 20}
  # Fan-in: each worker sends 10 MB to T_sink
  - {from: W0, to: T_sink, data_size: 10}
  - {from: W1, to: T_sink, data_size: 10}
  - {from: W2, to: T_sink, data_size: 10}
  - {from: W3, to: T_sink, data_size: 10}
```

!!! note "Data Size"
    `data_size` is in **MB** (megabytes). When two tasks are on different nodes,
    this amount of data must be transferred over the network. When both tasks
    are on the same node, the transfer is local (instant, no network cost).

---

## Step 4: Write the Complete YAML

Create the file `scenarios/my_custom.yaml` with the complete scenario:

```yaml
# Custom fork-join scenario: 4-node mesh with heterogeneous compute
# T_src -> {W0, W1, W2, W3} -> T_sink

scenario:
  name: "Custom Fork-Join Mesh"

  network:
    nodes:
      - id: n0
        compute_capacity: 200
        position: {x: 0, y: 0}
      - id: n1
        compute_capacity: 100
        position: {x: 20, y: 0}
      - id: n2
        compute_capacity: 150
        position: {x: 0, y: 20}
      - id: n3
        compute_capacity: 80
        position: {x: 20, y: 20}
    links:
      # n0 <-> n1 (horizontal top)
      - {id: l01, from: n0, to: n1, bandwidth: 500, latency: 0.001}
      - {id: l10, from: n1, to: n0, bandwidth: 500, latency: 0.001}
      # n0 <-> n2 (vertical left)
      - {id: l02, from: n0, to: n2, bandwidth: 400, latency: 0.001}
      - {id: l20, from: n2, to: n0, bandwidth: 400, latency: 0.001}
      # n0 <-> n3 (diagonal)
      - {id: l03, from: n0, to: n3, bandwidth: 300, latency: 0.002}
      - {id: l30, from: n3, to: n0, bandwidth: 300, latency: 0.002}
      # n1 <-> n2 (diagonal)
      - {id: l12, from: n1, to: n2, bandwidth: 300, latency: 0.002}
      - {id: l21, from: n2, to: n1, bandwidth: 300, latency: 0.002}
      # n1 <-> n3 (vertical right)
      - {id: l13, from: n1, to: n3, bandwidth: 400, latency: 0.001}
      - {id: l31, from: n3, to: n1, bandwidth: 400, latency: 0.001}
      # n2 <-> n3 (horizontal bottom)
      - {id: l23, from: n2, to: n3, bandwidth: 500, latency: 0.001}
      - {id: l32, from: n3, to: n2, bandwidth: 500, latency: 0.001}

  dags:
    - id: dag_1
      inject_at: 0.0
      tasks:
        - {id: T_src, compute_cost: 100}
        - {id: W0, compute_cost: 500}
        - {id: W1, compute_cost: 600}
        - {id: W2, compute_cost: 400}
        - {id: W3, compute_cost: 700}
        - {id: T_sink, compute_cost: 100}
      edges:
        - {from: T_src, to: W0, data_size: 20}
        - {from: T_src, to: W1, data_size: 20}
        - {from: T_src, to: W2, data_size: 20}
        - {from: T_src, to: W3, data_size: 20}
        - {from: W0, to: T_sink, data_size: 10}
        - {from: W1, to: T_sink, data_size: 10}
        - {from: W2, to: T_sink, data_size: 10}
        - {from: W3, to: T_sink, data_size: 10}

  config:
    scheduler: heft
    seed: 42
```

Save this file, then verify it parses correctly:

```bash
ncsim --scenario scenarios/my_custom.yaml --output results/tutorial2/heft
```

---

## Step 5: Run with Different Schedulers

Ncsim 1.1.0 discovers the scheduler catalog provided by the installed SAGA
version. With the SAGA 2.1.0 setup from Tutorial 1, compare five representative
choices on this scenario:

```bash
ncsim --scenario scenarios/my_custom.yaml \
      --output results/tutorial2/heft \
      --scheduler heft

ncsim --scenario scenarios/my_custom.yaml \
      --output results/tutorial2/cpop \
      --scheduler cpop

ncsim --scenario scenarios/my_custom.yaml \
      --output results/tutorial2/peft \
      --scheduler peft

ncsim --scenario scenarios/my_custom.yaml \
      --output results/tutorial2/minmin \
      --scheduler minmin

ncsim --scenario scenarios/my_custom.yaml \
      --output results/tutorial2/rr \
      --scheduler round_robin
```

Compare the makespans:

| Scheduler | Strategy | Expected Behavior |
|-----------|----------|-------------------|
| **heft** | Assigns each task to the node that gives the earliest finish time | Tends to place heavy tasks on fast nodes; balances compute vs. transfer cost |
| **cpop** | Identifies the critical path and assigns critical tasks to the fastest node | Prioritizes the critical path; may leave non-critical tasks on slower nodes |
| **peft** | Uses an optimistic cost table to estimate downstream finish times | Communication-aware alternative to HEFT for heterogeneous workflows |
| **minmin** | Repeatedly schedules the task with the smallest minimum completion time | Favors tasks that can finish soon; useful as a list-scheduling baseline |
| **round_robin** | Assigns tasks to nodes in rotation (n0, n1, n2, n3, n0, ...) | Ignores compute capacity and transfer cost; useful as a baseline |

!!! tip "Examining the placement"
    Run with `--verbose` (or `-v`) to see which tasks are assigned to which nodes:

    ```bash
    ncsim --scenario scenarios/my_custom.yaml \
          --output results/tutorial2/heft_verbose \
          --scheduler heft -v
    ```

    Look for the `SAGA HEFT assignments:` line in the log output. The prefix
    changes with the selected SAGA algorithm, for example `SAGA PEFT assignments:`.

!!! info "The complete scheduler catalog"
    `ncsim --help` prints every valid scheduler name. With SAGA 2.1.0, the set is:
    `bil`, `brute_force`, `cpop`, `dps`, `duplex`, `etf`, `fastest_node`,
    `fcp`, `flb`, `gdl`, `hbmct`, `heft`, `maxmin`, `mct`, `met`, `minmin`,
    `msbc`, `mst`, `olb`, `peft`, `smt`, `sufferage`, and `wba`.
    The built-in choices are `round_robin` and `manual`. SAGA 2.0.4 omits
    `peft`; install the tagged SAGA 2.1.0 release as shown in Tutorial 1 to add it.

Use the Gantt chart to visualize how each scheduler distributes work:

```bash
python analyze_trace.py results/tutorial2/heft/trace.jsonl --gantt
python analyze_trace.py results/tutorial2/rr/trace.jsonl --gantt
```

---

## Step 6: Try Different Routing

By default, ncsim uses **direct routing** -- data can only travel over a single
explicit link between two nodes. With a full mesh, every node pair has a direct
link, so all transfers are single-hop.

Try **widest-path routing**, which finds multi-hop paths that maximize bottleneck
bandwidth:

```bash
ncsim --scenario scenarios/my_custom.yaml \
      --output results/tutorial2/widest \
      --routing widest_path

ncsim --scenario scenarios/my_custom.yaml \
      --output results/tutorial2/direct \
      --routing direct
```

!!! info "When does routing matter?"
    In a full mesh, widest-path routing has the same result as direct routing
    because every node pair already has a direct link. Routing makes a bigger
    difference in **linear** or **tree** topologies where some node pairs lack
    direct connections. See the `parallel_spread.yaml` scenario for an example.

To see routing effects, try the parallel spread scenario with both routing modes:

```bash
ncsim --scenario scenarios/parallel_spread.yaml \
      --output results/tutorial2/spread_direct \
      --routing direct

ncsim --scenario scenarios/parallel_spread.yaml \
      --output results/tutorial2/spread_widest \
      --routing widest_path
```

In the linear topology, widest-path routing enables HEFT to spread tasks across
all 5 nodes (reaching n0 and n4 via multi-hop), while direct routing limits
placement to 3 adjacent nodes.

---

## Step 7: Add Interference

Interference models simulate the effect of shared wireless spectrum. When nearby
links are active simultaneously, they reduce each other's effective bandwidth.

### Proximity Interference

The simplest model: links whose midpoints are within a given radius share
bandwidth equally.

```bash
# Default radius (15m)
ncsim --scenario scenarios/my_custom.yaml \
      --output results/tutorial2/prox_15 \
      --interference proximity

# Smaller radius (10m) -- less interference
ncsim --scenario scenarios/my_custom.yaml \
      --output results/tutorial2/prox_10 \
      --interference proximity --interference-radius 10

# Larger radius (30m) -- more interference
ncsim --scenario scenarios/my_custom.yaml \
      --output results/tutorial2/prox_30 \
      --interference proximity --interference-radius 30

# No interference
ncsim --scenario scenarios/my_custom.yaml \
      --output results/tutorial2/no_interf \
      --interference none
```

!!! note "How proximity interference works"
    With radius R, if k active links have midpoints within R meters of each
    other, each gets its bandwidth reduced by a factor of 1/k. This is a
    simple model -- for a physically accurate WiFi model, see
    [Tutorial 3](tutorial-3-wifi-experiment.md).

Compare the makespans at different radii:

| Interference | Radius | Effect |
|-------------|--------|--------|
| **none** | -- | All links get full bandwidth at all times |
| **proximity** | 10m | Only very close links interfere (side links, not diagonals) |
| **proximity** | 15m | Default; most adjacent links interfere |
| **proximity** | 30m | All links in the mesh interfere with each other |

Larger radius means more contention, which increases transfer times and may
change the optimal scheduler placement.

---

## Summary

In this tutorial you built a complete ncsim scenario from scratch:

1. **Network**: 4 nodes in a square with heterogeneous compute capacities (80--200 cu/s)
2. **Links**: Full mesh with 12 directional links and varying bandwidths (300--500 MB/s)
3. **DAG**: Fork-join pattern with 6 tasks and uneven worker compute costs (400--700 cu)
4. **Experimented** with representative SAGA schedulers (HEFT, CPOP, PEFT,
   Min-Min), the round-robin baseline, two routing modes (direct, widest-path),
   and multiple interference settings

### Key Takeaways

| Concept | Lesson |
|---------|--------|
| Heterogeneous nodes | Create non-trivial scheduling decisions |
| Fork-join DAGs | Expose parallelism that smart schedulers exploit |
| Full mesh topology | Gives direct routing access to all node pairs |
| Interference radius | Controls how aggressively links share bandwidth |

## Complete Configuration Reference

For the full YAML schema and all available options, see the
[YAML Reference](../scenarios/yaml-reference.md).

## What's Next

| Tutorial | Topic |
|----------|-------|
| [Tutorial 3: WiFi Experiment](tutorial-3-wifi-experiment.md) | Use the physically-grounded CSMA/CA Bianchi WiFi model |
| [Tutorial 4: Compare Schedulers](tutorial-4-compare-schedulers.md) | Systematic scheduler comparison across multiple scenarios |

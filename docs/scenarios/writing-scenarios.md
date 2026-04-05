# Writing Your Own Scenarios

This tutorial walks through designing a custom ncsim scenario from scratch. By the end, you will have a complete YAML file ready to run.

---

## Step 1: Define Your Network

Start by choosing a topology: how many nodes you need and how they connect.

**Key decisions:**

- **Node count and compute capacities** -- heterogeneous capacities create interesting scheduling trade-offs.
- **Link topology** -- fully connected, line, ring, mesh, star, or tree.
- **Link properties** -- bandwidth (MB/s) and latency (seconds).
- **Positions** -- required if you plan to use interference models. Coordinates are in meters.

!!! tip
    Links in ncsim are **directional**. If you need bidirectional communication between two nodes, define two links (one in each direction).

**Example: 4-node mesh**

```yaml
network:
  nodes:
    - {id: n0, compute_capacity: 100, position: {x: 0,  y: 0}}
    - {id: n1, compute_capacity: 150, position: {x: 20, y: 0}}
    - {id: n2, compute_capacity: 100, position: {x: 0,  y: 20}}
    - {id: n3, compute_capacity: 200, position: {x: 20, y: 20}}
  links:
    # Horizontal links (bidirectional)
    - {id: l01, from: n0, to: n1, bandwidth: 100, latency: 0.001}
    - {id: l10, from: n1, to: n0, bandwidth: 100, latency: 0.001}
    - {id: l23, from: n2, to: n3, bandwidth: 100, latency: 0.001}
    - {id: l32, from: n3, to: n2, bandwidth: 100, latency: 0.001}
    # Vertical links (bidirectional)
    - {id: l02, from: n0, to: n2, bandwidth: 50,  latency: 0.002}
    - {id: l20, from: n2, to: n0, bandwidth: 50,  latency: 0.002}
    - {id: l13, from: n1, to: n3, bandwidth: 50,  latency: 0.002}
    - {id: l31, from: n3, to: n1, bandwidth: 50,  latency: 0.002}
```

This creates a 4-node mesh where horizontal links are faster (100 MB/s) than vertical links (50 MB/s), giving the scheduler something to optimize around.

---

## Step 2: Design Your DAG

Define the computation tasks and the data dependencies between them.

**Key decisions:**

- **Task compute costs** -- in compute units. Runtime = `compute_cost / node.compute_capacity`.
- **Edge data sizes** -- in MB. Transfer time = `data_size / effective_bandwidth + latency`.
- **DAG shape** -- chain, fork-join, diamond, parallel, or a custom structure.
- **Pinning** -- optionally force tasks onto specific nodes with `pinned_to`.

!!! tip
    If both the source and destination tasks of an edge run on the **same node**, no network transfer occurs -- the data dependency is resolved locally with zero transfer time.

**Example: fork-join DAG**

```yaml
dags:
  - id: dag1
    inject_at: 0.0
    tasks:
      - {id: start,  compute_cost: 50}
      - {id: work_a, compute_cost: 500}
      - {id: work_b, compute_cost: 300}
      - {id: work_c, compute_cost: 400}
      - {id: finish, compute_cost: 50}
    edges:
      - {from: start,  to: work_a, data_size: 10}
      - {from: start,  to: work_b, data_size: 10}
      - {from: start,  to: work_c, data_size: 10}
      - {from: work_a, to: finish, data_size: 20}
      - {from: work_b, to: finish, data_size: 20}
      - {from: work_c, to: finish, data_size: 20}
```

---

## Step 3: Configure Settings

Choose the scheduler, routing algorithm, interference model, and random seed.

**Scheduler options:**

| Scheduler | Best for |
|-----------|----------|
| `heft` | General use. Optimizes for earliest finish time on heterogeneous nodes. |
| `cpop` | Critical-path-aware. Good when one path through the DAG dominates. |
| `round_robin` | Baseline comparison. Simple round-robin assignment. |

**Routing options:**

| Routing | Best for |
|---------|----------|
| `direct` | Fully connected topologies (every node has a direct link to every other). |
| `widest_path` | Multi-hop topologies. Maximizes bottleneck bandwidth along the path. |
| `shortest_path` | Multi-hop topologies where latency matters more than throughput. |

**Interference options:**

| Interference | Best for |
|--------------|----------|
| `none` | Wired networks or baseline comparison. |
| `proximity` | Simple wireless model. Nearby links share bandwidth as 1/k. |
| `csma_clique` | 802.11 static model. Uses conflict graph + clique-based fair share. |
| `csma_bianchi` | 802.11 dynamic model. SINR-aware rate + Bianchi MAC efficiency. |

!!! tip
    Set `seed` to a fixed value for reproducible results. Different seeds may produce different scheduler tie-breaking or shadow fading.

**Example configuration:**

```yaml
config:
  scheduler: heft
  routing: widest_path
  interference: none
  seed: 42
```

---

## Step 4: Put It Together

Combining the network, DAG, and config sections from the previous steps into a complete scenario file:

```yaml
scenario:
  name: "Custom 4-Node Mesh with Fork-Join"

  network:
    nodes:
      - {id: n0, compute_capacity: 100, position: {x: 0,  y: 0}}
      - {id: n1, compute_capacity: 150, position: {x: 20, y: 0}}
      - {id: n2, compute_capacity: 100, position: {x: 0,  y: 20}}
      - {id: n3, compute_capacity: 200, position: {x: 20, y: 20}}
    links:
      # Horizontal (fast)
      - {id: l01, from: n0, to: n1, bandwidth: 100, latency: 0.001}
      - {id: l10, from: n1, to: n0, bandwidth: 100, latency: 0.001}
      - {id: l23, from: n2, to: n3, bandwidth: 100, latency: 0.001}
      - {id: l32, from: n3, to: n2, bandwidth: 100, latency: 0.001}
      # Vertical (slower)
      - {id: l02, from: n0, to: n2, bandwidth: 50,  latency: 0.002}
      - {id: l20, from: n2, to: n0, bandwidth: 50,  latency: 0.002}
      - {id: l13, from: n1, to: n3, bandwidth: 50,  latency: 0.002}
      - {id: l31, from: n3, to: n1, bandwidth: 50,  latency: 0.002}

  dags:
    - id: dag1
      inject_at: 0.0
      tasks:
        - {id: start,  compute_cost: 50}
        - {id: work_a, compute_cost: 500}
        - {id: work_b, compute_cost: 300}
        - {id: work_c, compute_cost: 400}
        - {id: finish, compute_cost: 50}
      edges:
        - {from: start,  to: work_a, data_size: 10}
        - {from: start,  to: work_b, data_size: 10}
        - {from: start,  to: work_c, data_size: 10}
        - {from: work_a, to: finish, data_size: 20}
        - {from: work_b, to: finish, data_size: 20}
        - {from: work_c, to: finish, data_size: 20}

  config:
    scheduler: heft
    routing: widest_path
    interference: none
    seed: 42
```

---

## Step 5: Run and Verify

### Run the scenario

```bash
ncsim --scenario my_scenario.yaml --output results/my_run
```

### Check the output

The output directory will contain:

- `trace.jsonl` -- event-by-event trace of the simulation
- `metrics.json` -- summary metrics including makespan, task counts, and transfer counts
- `scenario.yaml` -- copy of the input scenario for reproducibility

### Compare with different settings

Use CLI overrides to compare schedulers and routing algorithms without modifying the YAML:

```bash
# Compare schedulers
ncsim --scenario my_scenario.yaml --output results/heft   --scheduler heft
ncsim --scenario my_scenario.yaml --output results/cpop   --scheduler cpop
ncsim --scenario my_scenario.yaml --output results/rr     --scheduler round_robin

# Compare routing
ncsim --scenario my_scenario.yaml --output results/direct  --routing direct
ncsim --scenario my_scenario.yaml --output results/widest  --routing widest_path

# Compare interference models
ncsim --scenario my_scenario.yaml --output results/no_intf    --interference none
ncsim --scenario my_scenario.yaml --output results/proximity  --interference proximity
```

---

## Tips

!!! tip "Start simple, add complexity gradually"
    Begin with 2-3 nodes and a simple chain DAG. Verify the output matches your hand calculations, then scale up the network and DAG complexity.

!!! tip "Use deterministic seeds"
    Always set `seed` in your YAML or via `--seed` on the CLI. This ensures identical results across runs, making debugging and comparison straightforward.

!!! tip "Isolate interference effects"
    Run the same scenario with `interference: none` and `interference: proximity` (or a WiFi model) to measure exactly how much interference impacts makespan.

!!! tip "Use pinned_to for controlled experiments"
    When investigating network behavior (routing, interference, bandwidth contention), pin tasks to specific nodes to remove scheduler variability from the equation. Once the network layer behaves as expected, remove the pins and let the scheduler optimize.

!!! tip "Bidirectional links require two entries"
    A link from n0 to n1 does not automatically create a link from n1 to n0. If your DAG requires data flow in both directions (or the scheduler needs to consider reverse paths), define both explicitly.

---

## Common Patterns

### Topology Patterns

#### Chain (line)

A simple linear topology where each node connects to its neighbor:

```yaml
nodes:
  - {id: n0, compute_capacity: 100, position: {x: 0,  y: 0}}
  - {id: n1, compute_capacity: 100, position: {x: 10, y: 0}}
  - {id: n2, compute_capacity: 100, position: {x: 20, y: 0}}
links:
  - {id: l01, from: n0, to: n1, bandwidth: 100, latency: 0.001}
  - {id: l12, from: n1, to: n2, bandwidth: 100, latency: 0.001}
```

#### Star

A central hub connected to all other nodes:

```yaml
nodes:
  - {id: hub,  compute_capacity: 200, position: {x: 10, y: 10}}
  - {id: edge0, compute_capacity: 50, position: {x: 0,  y: 10}}
  - {id: edge1, compute_capacity: 50, position: {x: 20, y: 10}}
  - {id: edge2, compute_capacity: 50, position: {x: 10, y: 0}}
  - {id: edge3, compute_capacity: 50, position: {x: 10, y: 20}}
links:
  - {id: l_h0, from: hub, to: edge0, bandwidth: 100, latency: 0.001}
  - {id: l_0h, from: edge0, to: hub, bandwidth: 100, latency: 0.001}
  - {id: l_h1, from: hub, to: edge1, bandwidth: 100, latency: 0.001}
  - {id: l_1h, from: edge1, to: hub, bandwidth: 100, latency: 0.001}
  - {id: l_h2, from: hub, to: edge2, bandwidth: 100, latency: 0.001}
  - {id: l_2h, from: edge2, to: hub, bandwidth: 100, latency: 0.001}
  - {id: l_h3, from: hub, to: edge3, bandwidth: 100, latency: 0.001}
  - {id: l_3h, from: edge3, to: hub, bandwidth: 100, latency: 0.001}
```

#### Diamond

Two paths between source and destination, useful for routing comparisons:

```yaml
nodes:
  - {id: src,    compute_capacity: 100, position: {x: 0,  y: 5}}
  - {id: top,    compute_capacity: 100, position: {x: 5,  y: 0}}
  - {id: bottom, compute_capacity: 100, position: {x: 5,  y: 10}}
  - {id: dst,    compute_capacity: 100, position: {x: 10, y: 5}}
links:
  - {id: l_st, from: src, to: top,    bandwidth: 50,  latency: 0.001}
  - {id: l_td, from: top, to: dst,    bandwidth: 50,  latency: 0.001}
  - {id: l_sb, from: src, to: bottom, bandwidth: 200, latency: 0.01}
  - {id: l_bd, from: bottom, to: dst, bandwidth: 200, latency: 0.01}
```

#### Ring

Every node connects to the next, forming a loop:

```yaml
nodes:
  - {id: n0, compute_capacity: 100, position: {x: 10, y: 0}}
  - {id: n1, compute_capacity: 100, position: {x: 20, y: 10}}
  - {id: n2, compute_capacity: 100, position: {x: 10, y: 20}}
  - {id: n3, compute_capacity: 100, position: {x: 0,  y: 10}}
links:
  - {id: l01, from: n0, to: n1, bandwidth: 100, latency: 0.001}
  - {id: l12, from: n1, to: n2, bandwidth: 100, latency: 0.001}
  - {id: l23, from: n2, to: n3, bandwidth: 100, latency: 0.001}
  - {id: l30, from: n3, to: n0, bandwidth: 100, latency: 0.001}
```

---

### DAG Patterns

#### Chain

Sequential tasks, each depending on the previous:

```yaml
tasks:
  - {id: A, compute_cost: 100}
  - {id: B, compute_cost: 200}
  - {id: C, compute_cost: 100}
edges:
  - {from: A, to: B, data_size: 10}
  - {from: B, to: C, data_size: 10}
```

#### Fork-join (fan-out / fan-in)

One task distributes work to many, then collects results:

```yaml
tasks:
  - {id: scatter, compute_cost: 50}
  - {id: w0, compute_cost: 500}
  - {id: w1, compute_cost: 500}
  - {id: w2, compute_cost: 500}
  - {id: gather, compute_cost: 50}
edges:
  - {from: scatter, to: w0, data_size: 10}
  - {from: scatter, to: w1, data_size: 10}
  - {from: scatter, to: w2, data_size: 10}
  - {from: w0, to: gather, data_size: 20}
  - {from: w1, to: gather, data_size: 20}
  - {from: w2, to: gather, data_size: 20}
```

#### Diamond

Two parallel paths converge at a single sink:

```yaml
tasks:
  - {id: root, compute_cost: 50}
  - {id: left, compute_cost: 300}
  - {id: right, compute_cost: 200}
  - {id: sink, compute_cost: 50}
edges:
  - {from: root, to: left,  data_size: 10}
  - {from: root, to: right, data_size: 10}
  - {from: left, to: sink,  data_size: 15}
  - {from: right, to: sink, data_size: 15}
```

#### Independent parallel tasks

Multiple entry-point tasks with no dependencies (useful for throughput testing):

```yaml
tasks:
  - {id: T0, compute_cost: 1000}
  - {id: T1, compute_cost: 1000}
  - {id: T2, compute_cost: 1000}
  - {id: T3, compute_cost: 1000}
edges: []
```

#### Multi-stage pipeline

A deeper DAG with sequential stages:

```yaml
tasks:
  - {id: ingest,    compute_cost: 100}
  - {id: parse,     compute_cost: 200}
  - {id: transform, compute_cost: 500}
  - {id: validate,  compute_cost: 100}
  - {id: store,     compute_cost: 50}
edges:
  - {from: ingest,    to: parse,     data_size: 50}
  - {from: parse,     to: transform, data_size: 30}
  - {from: transform, to: validate,  data_size: 20}
  - {from: validate,  to: store,     data_size: 10}
```

# YAML Reference

This page documents every field available in an ncsim scenario YAML file, with a complete annotated example and a field-by-field reference table.

---

## Complete Annotated Example

The following YAML shows every supported field with inline comments explaining its purpose:

```yaml
scenario:
  name: "My Experiment"

  network:
    nodes:
      - id: n0
        compute_capacity: 100      # compute units per second
        position: {x: 0, y: 0}     # meters (for interference and viz)
      - id: n1
        compute_capacity: 50
        position: {x: 10, y: 0}

    links:
      - id: l01
        from: n0                    # directional: n0 -> n1
        to: n1
        bandwidth: 100              # MB/s
        latency: 0.001              # seconds

  dags:
    - id: dag_1
      inject_at: 0.0               # simulation time to inject
      tasks:
        - id: T0
          compute_cost: 100         # compute units (runtime = cost / capacity)
          pinned_to: n0             # optional: force task to this node
        - id: T1
          compute_cost: 200
      edges:
        - from: T0
          to: T1
          data_size: 50             # MB

  config:
    scheduler: heft                 # heft | cpop | round_robin
    seed: 42
    routing: direct                 # direct | widest_path | shortest_path
    interference: proximity         # none | proximity | csma_clique | csma_bianchi
    interference_radius: 15.0       # meters (proximity model only)
    rf:                             # WiFi models only
      tx_power_dBm: 20
      freq_ghz: 5.0
      path_loss_exponent: 3.0
      noise_floor_dBm: -95
      cca_threshold_dBm: -82
      channel_width_mhz: 20
      wifi_standard: ax
      shadow_fading_sigma: 0
      rts_cts: false
```

---

## Field-by-Field Reference

### Scenario Root

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `scenario.name` | string | No | File stem | Human-readable name for the scenario. Used in CLI output and result metadata. |

### Nodes (`scenario.network.nodes[]`)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `nodes[].id` | string | **Yes** | -- | Unique identifier for the node. Referenced by links, `pinned_to`, and routing. |
| `nodes[].compute_capacity` | float | **Yes** | -- | Processing speed in compute units per second. Task runtime = `compute_cost / compute_capacity`. |
| `nodes[].position` | object | No | `{x: 0, y: 0}` | 2D position in meters. Used by interference models (proximity, CSMA) and the visualization. Contains `x` and `y` float fields. |

### Links (`scenario.network.links[]`)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `links[].id` | string | **Yes** | -- | Unique identifier for the link. |
| `links[].from` | string | **Yes** | -- | Source node ID. Links are directional: data flows from `from` to `to`. |
| `links[].to` | string | **Yes** | -- | Destination node ID. |
| `links[].bandwidth` | float | No | Derived from RF | Link capacity in MB/s. When using `csma_clique` or `csma_bianchi`, links without explicit bandwidth derive their rate from RF parameters. Links WITH explicit bandwidth keep their stated value (useful for mixed wired/wireless topologies). |
| `links[].latency` | float | No | `0.0` | Fixed propagation delay in seconds, added to every transfer on this link. |

### DAGs (`scenario.dags[]`)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `dags[].id` | string | **Yes** | -- | Unique identifier for the DAG. |
| `dags[].inject_at` | float | No | `0.0` | Simulation time (in seconds) at which this DAG is injected into the system. |

### Tasks (`scenario.dags[].tasks[]`)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `tasks[].id` | string | **Yes** | -- | Unique identifier for the task within its DAG. |
| `tasks[].compute_cost` | float | **Yes** | -- | Total compute work in compute units. Runtime on a node = `compute_cost / node.compute_capacity`. |
| `tasks[].pinned_to` | string | No | `null` | Node ID to force this task onto. Overrides the scheduler's placement decision. Useful for controlled experiments. |

### Edges (`scenario.dags[].edges[]`)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `edges[].from` | string | **Yes** | -- | Source task ID. This task must complete before the destination task can start. |
| `edges[].to` | string | **Yes** | -- | Destination task ID. |
| `edges[].data_size` | float | **Yes** | -- | Amount of data to transfer in MB. Transfer time = `data_size / effective_bandwidth + latency`. If both tasks run on the same node, no transfer occurs. |

### Config (`scenario.config`)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `config.scheduler` | string | No | `heft` | Scheduling algorithm. Options: `heft` (Heterogeneous Earliest Finish Time), `cpop` (Critical Path on a Processor), `round_robin`. |
| `config.seed` | int | No | `42` | Random seed for reproducibility. Affects shadow fading, tie-breaking, and any stochastic behavior. |
| `config.routing` | string | No | `direct` | Routing algorithm. Options: `direct` (single-hop only), `widest_path` (maximize bottleneck bandwidth), `shortest_path` (minimize hop count/latency). |
| `config.interference` | string | No | `proximity` | Interference model. Options: `none`, `proximity` (distance-based 1/k sharing), `csma_clique` (static 802.11 clique model), `csma_bianchi` (dynamic 802.11 SINR + Bianchi MAC). |
| `config.interference_radius` | float | No | `15.0` | Radius in meters for the `proximity` interference model. Links whose midpoints are within this distance interfere with each other. Ignored by other models. |

### RF Parameters (`scenario.config.rf`)

!!! info "WiFi models only"
    The `rf` section is only used when `interference` is set to `csma_clique` or `csma_bianchi`. It configures the 802.11 physical layer model.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `rf.tx_power_dBm` | float | No | `20.0` | Transmit power in dBm. |
| `rf.freq_ghz` | float | No | `5.0` | Carrier frequency in GHz. Affects free-space path loss. |
| `rf.path_loss_exponent` | float | No | `3.0` | Path loss exponent for the log-distance model. 2.0 = free space, 3.0 = typical indoor/outdoor, 4.0+ = heavy obstruction. |
| `rf.noise_floor_dBm` | float | No | `-95.0` | Receiver noise floor in dBm. Used for SNR/SINR computation. |
| `rf.cca_threshold_dBm` | float | No | `-82.0` | Clear Channel Assessment threshold in dBm. Determines carrier sensing range: nodes that receive above this threshold defer transmission. |
| `rf.channel_width_mhz` | int | No | `20` | Channel bandwidth in MHz. Wider channels support higher PHY rates. |
| `rf.wifi_standard` | string | No | `ax` | WiFi standard for MCS table lookup. Options: `n` (802.11n), `ac` (802.11ac), `ax` (802.11ax/Wi-Fi 6). |
| `rf.shadow_fading_sigma` | float | No | `0.0` | Standard deviation of log-normal shadow fading in dB. Set to `0` for deterministic propagation. Non-zero values add per-link random fading (seeded by `config.seed`). |
| `rf.rts_cts` | bool | No | `false` | Enable RTS/CTS handshake. When true, the conflict graph is extended to protect receivers from hidden terminals. |

---

## Notes

!!! note "WiFi link bandwidth"
    When using `csma_clique` or `csma_bianchi`, links **without** an explicit `bandwidth` field derive their data rate from the RF parameters (transmit power, distance, path loss, MCS table). Links **with** an explicit `bandwidth` keep their stated value unchanged. This allows mixed wired/wireless topologies where some links are modeled as wired (fixed bandwidth) and others as wireless (RF-derived bandwidth).

!!! note "CLI overrides"
    The following CLI flags override the corresponding `config` section values at runtime:

    - `--scheduler` overrides `config.scheduler`
    - `--routing` overrides `config.routing`
    - `--interference` overrides `config.interference`
    - `--interference-radius` overrides `config.interference_radius`
    - `--seed` overrides `config.seed`
    - `--tx-power` overrides `rf.tx_power_dBm`
    - `--freq` overrides `rf.freq_ghz`
    - `--path-loss-exponent` overrides `rf.path_loss_exponent`
    - `--wifi-standard` overrides `rf.wifi_standard`
    - `--rts-cts` overrides `rf.rts_cts`

!!! note "Units summary"

    | Quantity | Unit |
    |----------|------|
    | `compute_capacity` | compute units / second |
    | `compute_cost` | compute units |
    | `bandwidth` | MB/s |
    | `latency` | seconds |
    | `data_size` | MB |
    | `position` (x, y) | meters |
    | `interference_radius` | meters |
    | `tx_power_dBm` | dBm |
    | `freq_ghz` | GHz |
    | `noise_floor_dBm` | dBm |
    | `cca_threshold_dBm` | dBm |
    | `channel_width_mhz` | MHz |
    | `shadow_fading_sigma` | dB |

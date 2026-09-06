# Tutorial 3: WiFi Interference Experiment

This tutorial explores ncsim's 802.11 WiFi interference models. You will run
the same scenario under different interference models, vary RF parameters, and
observe how distance, transmit power, WiFi standard, and RTS/CTS affect
simulation outcomes.

---

## What You Will Learn

- Use the `csma_bianchi` and `csma_clique` interference models
- Understand how physical distance affects WiFi data rates
- Observe contention effects between parallel links
- Vary TX power, WiFi standard, and RTS/CTS settings
- Compare the Bianchi model against the simpler clique model

## Prerequisites

- ncsim installed ([Tutorial 1](tutorial-1-first-sim.md))
- Familiarity with running simulations and reading output ([Tutorial 1](tutorial-1-first-sim.md))

---

## Background: WiFi Models in ncsim

ncsim provides two 802.11 CSMA/CA interference models that derive link bandwidths
from RF physics rather than requiring explicit bandwidth values in the YAML:

| Model | CLI Flag | How It Works |
|-------|----------|-------------|
| **csma_bianchi** | `--interference csma_bianchi` | SINR-based rate selection + Bianchi MAC efficiency model. Dynamic: interference factor changes as links become active/inactive. |
| **csma_clique** | `--interference csma_clique` | Static: PHY rate / max clique size. Simpler but less accurate. |

Both models use the same **RF propagation chain**:

1. **Distance** between TX and RX nodes
2. **Log-distance path loss**: PL(d) = PL(d0) + 10 * n * log10(d/d0)
3. **SNR** = received power - noise floor
4. **MCS rate selection**: highest modulation/coding scheme whose SNR threshold is met
5. **Conflict graph**: links that can carrier-sense each other cannot transmit simultaneously

!!! info "When to use which model"
    - **csma_bianchi** is the recommended of the two WiFi-specific models. It captures
      both contention-domain time-sharing (via Bianchi's saturation throughput model)
      and hidden-terminal SINR degradation.
    - **csma_clique** is faster to compute and useful for quick estimates. It divides
      the PHY rate by the maximum clique size, giving a static worst-case throughput.

---

## Step 1: Run the WiFi Bianchi Scenario

ncsim ships with a purpose-built WiFi test scenario. Examine it first:

```bash
cat scenarios/wifi_test.yaml
```

```yaml
scenario:
  name: "WiFi CSMA Bianchi Test"
  description: >
    Tests the csma_bianchi interference model. Two parallel links at 30m
    spacing with bandwidth derived from RF parameters. The conflict graph
    should show both links contending, and SINR + Bianchi efficiency
    should reduce effective throughput compared to SNR-only rates.

  network:
    nodes:
      - id: n0
        compute_capacity: 1000
        position: {x: 0, y: 0}
      - id: n1
        compute_capacity: 1000
        position: {x: 30, y: 0}
      - id: n2
        compute_capacity: 1000
        position: {x: 0, y: 30}
      - id: n3
        compute_capacity: 1000
        position: {x: 30, y: 30}
    links:
      # No explicit bandwidth -- derived from RF model
      - {id: l01, from: n0, to: n1, latency: 0.0}
      - {id: l23, from: n2, to: n3, latency: 0.0}

  dags:
    - id: dag_1
      inject_at: 0.0
      tasks:
        - {id: T0, compute_cost: 10, pinned_to: n0}
        - {id: T1, compute_cost: 10, pinned_to: n1}
        - {id: T2, compute_cost: 10, pinned_to: n2}
        - {id: T3, compute_cost: 10, pinned_to: n3}
      edges:
        - {from: T0, to: T1, data_size: 50}
        - {from: T2, to: T3, data_size: 50}

  config:
    scheduler: round_robin
    seed: 42
    interference: csma_bianchi
    rf:
      tx_power_dBm: 20
      freq_ghz: 5.0
      path_loss_exponent: 3.0
      noise_floor_dBm: -95
      cca_threshold_dBm: -82
      channel_width_mhz: 20
      wifi_standard: "ax"
      shadow_fading_sigma: 0.0
      rts_cts: false
```

!!! note "Key features of the WiFi scenario"
    - **No explicit bandwidth** on links -- bandwidth is derived from RF parameters
    - **`pinned_to`** forces task placement so we can control which links are used
    - **Two parallel links** (l01 and l23) that will contend for the wireless channel
    - **High compute capacity** (1000 cu/s) makes compute time negligible (0.01s)
      so the experiment focuses on transfer time

Run it:

```bash
ncsim --scenario scenarios/wifi_test.yaml \
      --output results/tutorial3/bianchi -v
```

Key lines from the verbose output:

```
RF config: tx_power=20dBm, freq=5.0GHz, n=3.0, standard=ax, BW=20MHz, rts_cts=False
Carrier sensing range: 71.2m
Conflict graph: 2 links, 1 conflict pairs
```

The generated `metrics.json` records the derived PHY rates under
`link_phy_rates_MBps`: both `l01` and `l23` are **8.6 MB/s**.

```
=== Simulation Complete ===
Scenario: WiFi CSMA Bianchi Test
Scheduler: round_robin
Routing: direct
Interference: csma_bianchi
  WiFi: ax @ 5.0GHz, TX=20dBm, n=3.0
  CS range: 71.22m, RTS/CTS: False
Seed: 42
Makespan: 25.760176 seconds
Total events: 17
Status: completed
```

### Understanding the Output

The RF model computed:

| Parameter | Value | Explanation |
|-----------|-------|-------------|
| PHY rate (each link) | 8.60 MB/s | 802.11ax MCS 0 at 30m: SNR is sufficient for 8.6 Mbps (68.8 Mbps / 8) |
| Carrier sensing range | 71.2m | Maximum distance at which a transmission triggers CCA |
| Conflict pairs | 1 | l01 and l23 can sense each other (nodes are within 71.2m) |

Since both links are in the same **contention domain**, the Bianchi model applies:

- **n=2 contending stations**: both links share the channel
- The Bianchi saturation model accounts for successful airtime, collisions,
  backoff, and idle slots
- Each 50 MB transfer takes 25.740176 seconds, an observed effective rate of
  approximately **1.94 MB/s** per link

---

## Step 2: Run the WiFi Clique Scenario

The clique model uses a simpler formula: PHY rate / max_clique_size.

```bash
ncsim --scenario scenarios/wifi_clique_test.yaml \
      --output results/tutorial3/clique -v
```

Key verbose output:

```
Link l01: PHY=8.60 MB/s, clique=2, effective=4.30 MB/s
Link l23: PHY=8.60 MB/s, clique=2, effective=4.30 MB/s
```

```
=== Simulation Complete ===
Scenario: WiFi CSMA Clique Test
Scheduler: round_robin
Routing: direct
Interference: csma_clique
  WiFi: ax @ 5.0GHz, TX=20dBm, n=3.0
  CS range: 71.22m, RTS/CTS: False
Seed: 42
Makespan: 11.647907 seconds
Total events: 17
Status: completed
```

### Bianchi vs. Clique Comparison

| Model | Effective Rate per Link | Makespan | How Rate Is Computed |
|-------|------------------------|----------|---------------------|
| **csma_bianchi** | ~1.94 MB/s (dynamic) | 25.76s | Dynamic Bianchi sharing with contention and MAC overhead. |
| **csma_clique** | 4.30 MB/s (static) | 11.65s | PHY rate / clique_size = 8.60/2. Assumes perfect time-division. |

!!! warning "Why Bianchi is slower"
    The Bianchi model is more realistic because it accounts for CSMA/CA overhead:
    collision probability, exponential backoff, and idle slots. With 2 contending
    stations, the MAC efficiency eta(2) is less than 1.0, so each station gets
    less than half the channel capacity. The clique model optimistically assumes
    perfect 1/N sharing.

---

## Step 3: Run Without Interference

To see what happens without any interference model:

```bash
ncsim --scenario scenarios/wifi_test.yaml \
      --output results/tutorial3/no_interf \
      --interference none -v
```

```
=== Simulation Complete ===
Scenario: WiFi CSMA Bianchi Test
Scheduler: round_robin
Routing: direct
Interference: none
Seed: 42
Makespan: 50.020000 seconds
Total events: 17
Status: completed
```

!!! warning "Why is 'no interference' slower?"
    When you override interference to `none`, the WiFi RF model is **not invoked**
    at all. Links keep their placeholder bandwidth of 1.0 MB/s (the default when
    no explicit bandwidth is specified in YAML). This is much slower than the
    8.60 MB/s PHY rate. Transfer time: 50 MB / 1.0 MB/s = 50s.

    To test "WiFi rates without contention," use `csma_bianchi` with a scenario
    where only one link is active at a time, or increase the node spacing beyond
    the carrier sensing range.

### Three-Way Comparison

| Configuration | Effective Rate | Makespan | Notes |
|--------------|---------------|----------|-------|
| csma_bianchi | ~1.94 MB/s | 25.76s | Realistic WiFi with contention overhead |
| csma_clique | 4.30 MB/s | 11.65s | Idealized time-division sharing |
| none (no WiFi model) | 1.00 MB/s | 50.02s | Placeholder bandwidth only |

---

## Step 4: Vary Node Distances

Distance directly affects path loss, which determines SNR and therefore the MCS
rate. To experiment with different distances, create modified scenario files.

Create `scenarios/wifi_dist_10m.yaml` with positions at 10m spacing:

```yaml
scenario:
  name: "WiFi Distance Test - 10m"
  network:
    nodes:
      - {id: n0, compute_capacity: 1000, position: {x: 0, y: 0}}
      - {id: n1, compute_capacity: 1000, position: {x: 10, y: 0}}
      - {id: n2, compute_capacity: 1000, position: {x: 0, y: 10}}
      - {id: n3, compute_capacity: 1000, position: {x: 10, y: 10}}
    links:
      - {id: l01, from: n0, to: n1, latency: 0.0}
      - {id: l23, from: n2, to: n3, latency: 0.0}
  dags:
    - id: dag_1
      inject_at: 0.0
      tasks:
        - {id: T0, compute_cost: 10, pinned_to: n0}
        - {id: T1, compute_cost: 10, pinned_to: n1}
        - {id: T2, compute_cost: 10, pinned_to: n2}
        - {id: T3, compute_cost: 10, pinned_to: n3}
      edges:
        - {from: T0, to: T1, data_size: 50}
        - {from: T2, to: T3, data_size: 50}
  config:
    scheduler: round_robin
    seed: 42
    interference: csma_bianchi
    rf:
      tx_power_dBm: 20
      freq_ghz: 5.0
      path_loss_exponent: 3.0
      noise_floor_dBm: -95
      cca_threshold_dBm: -82
      channel_width_mhz: 20
      wifi_standard: "ax"
      shadow_fading_sigma: 0.0
      rts_cts: false
```

Create similar files for 20m, 50m, and 80m by changing the position coordinates.
For example, for 50m spacing, use `{x: 50, y: 0}` for n1 and `{x: 50, y: 50}` for n3.

Then run each:

```bash
ncsim --scenario scenarios/wifi_dist_10m.yaml \
      --output results/tutorial3/dist_10m -v

ncsim --scenario scenarios/wifi_dist_20m.yaml \
      --output results/tutorial3/dist_20m -v
# (after creating the 20m, 50m, 80m variants)
```

### How Distance Affects WiFi Rate

The SNR decreases with distance due to log-distance path loss. The MCS rate
selection picks the highest modulation whose SNR threshold is met:

| Distance | Path Loss (approx) | SNR (approx) | 802.11ax MCS | PHY Rate (Mbps) | PHY Rate (MB/s) |
|----------|-------------------|--------------|-------------|----------------|----------------|
| 10m | 76 dB | 39 dB | MCS 10 (1024-QAM 3/4) | 129.0 | 16.13 |
| 20m | 85 dB | 30 dB | MCS 7 (64-QAM 5/6) | 86.0 | 10.75 |
| 30m | 91 dB | 24 dB | MCS 5 (64-QAM 2/3) | 68.8 | 8.60 |
| 50m | 97 dB | 17.6 dB | MCS 3 (16-QAM 1/2) | 34.4 | 4.30 |
| 80m | 103 dB | 12 dB | MCS 2 (QPSK 3/4) | 25.8 | 3.23 |

!!! info "MCS Rate Tables"
    ncsim includes standard MCS rate tables for 802.11n, 802.11ac, and 802.11ax.
    Each MCS level has a minimum SNR threshold. The simulator selects the highest
    MCS whose threshold is met, similar to real WiFi rate adaptation.

At closer distances, the higher PHY rate means faster transfers. But closer nodes
are also more likely to be within carrier sensing range of each other, creating
more contention.

---

## Step 5: Vary TX Power

TX power affects both the data rate (higher power = higher SNR = higher MCS) and
the carrier sensing range (higher power = wider interference zone):

```bash
ncsim --scenario scenarios/wifi_test.yaml \
      --output results/tutorial3/tx15 --tx-power 15 -v

ncsim --scenario scenarios/wifi_test.yaml \
      --output results/tutorial3/tx20 --tx-power 20 -v

ncsim --scenario scenarios/wifi_test.yaml \
      --output results/tutorial3/tx23 --tx-power 23 -v
```

### TX Power Results

| TX Power | CS Range | PHY Rate | Makespan | Notes |
|----------|----------|----------|----------|-------|
| 15 dBm | 48.5m | 6.45 MB/s | 34.34s | Lower SNR at 30m reduces MCS; shorter CS range |
| 20 dBm | 71.2m | 8.60 MB/s | 25.76s | Default; both links contend |
| 23 dBm | 89.7m | 9.68 MB/s | 22.90s | Higher SNR improves MCS; wider CS range but better rates compensate |

!!! tip "The TX power tradeoff"
    Higher TX power increases the data rate (better SNR at the receiver) but
    also increases the carrier sensing range (more links detect each other as
    busy). In dense networks, this tradeoff can go either way. In this
    2-link scenario, the rate improvement from higher power outweighs the
    contention cost.

---

## Step 6: Compare WiFi Standards

ncsim supports three WiFi standards, each with different MCS rate tables:

```bash
ncsim --scenario scenarios/wifi_test.yaml \
      --output results/tutorial3/wifi_n --wifi-standard n -v

ncsim --scenario scenarios/wifi_test.yaml \
      --output results/tutorial3/wifi_ac --wifi-standard ac -v

ncsim --scenario scenarios/wifi_test.yaml \
      --output results/tutorial3/wifi_ax --wifi-standard ax -v
```

### WiFi Standard Comparison

| Standard | Max MCS | Highest Rate (20 MHz, 1SS) | Makespan |
|----------|---------|---------------------------|----------|
| **802.11n** | MCS 7 (64-QAM 5/6) | 65.0 Mbps | 34.08s |
| **802.11ac** | MCS 9 (256-QAM 5/6) | 86.7 Mbps | 34.08s |
| **802.11ax** | MCS 11 (1024-QAM 5/6) | 143.4 Mbps | 25.76s |

!!! info "Why n and ac have the same makespan"
    At 30m with the default RF parameters, the SNR (~24 dB) only supports up to
    MCS 5 (64-QAM 2/3). Both 802.11n and 802.11ac have the same rate at MCS 5
    (52.0 Mbps). The higher MCS levels in 802.11ac (MCS 8-9) require SNR above
    32 dB, which is not achievable at this distance. 802.11ax has higher rates
    at the same MCS indices due to OFDMA improvements (e.g., MCS 5 = 68.8 Mbps
    in ax vs. 52.0 Mbps in n/ac).

---

## Step 7: Enable RTS/CTS

RTS/CTS (Request to Send / Clear to Send) is a mechanism that extends the conflict
graph to protect receivers, not just transmitters:

```bash
# Without RTS/CTS (default)
ncsim --scenario scenarios/wifi_test.yaml \
      --output results/tutorial3/no_rts -v

# With RTS/CTS
ncsim --scenario scenarios/wifi_test.yaml \
      --output results/tutorial3/rts --rts-cts -v
```

### How RTS/CTS Affects the Conflict Graph

| Mode | Conflict Rule | Effect |
|------|--------------|--------|
| **No RTS/CTS** | tx(A) senses any node of B, OR tx(B) senses any node of A | Only transmitter-to-node distances matter |
| **RTS/CTS** | ANY node of A senses ANY node of B | All four node-to-node distances matter |

In the `wifi_test.yaml` scenario, all nodes are within 71.2m of each other
(the 30m square has a maximum diagonal of ~42m), so both modes produce the same
conflict graph. The effect of RTS/CTS becomes visible in scenarios where transmitters
are close but receivers are far apart -- RTS/CTS would add conflicts that the
basic mode misses.

!!! info "When RTS/CTS matters"
    RTS/CTS is most important in scenarios with **hidden terminal** problems:
    two transmitters cannot sense each other but interfere at a common receiver.
    RTS/CTS extends the conflict zone to prevent this. In compact topologies
    (like our 30m square), it has minimal effect.

---

## Summary: Full Comparison Table

| Experiment | Model | Settings | Makespan |
|-----------|-------|----------|----------|
| Bianchi (default) | csma_bianchi | ax, 20dBm, 30m | 25.76s |
| Clique | csma_clique | ax, 20dBm, 30m | 11.65s |
| No interference | none | (placeholder 1 MB/s) | 50.02s |
| TX power 15 dBm | csma_bianchi | ax, 15dBm, 30m | 34.34s |
| TX power 23 dBm | csma_bianchi | ax, 23dBm, 30m | 22.90s |
| 802.11n | csma_bianchi | n, 20dBm, 30m | 34.08s |
| 802.11ac | csma_bianchi | ac, 20dBm, 30m | 34.08s |
| 802.11ax | csma_bianchi | ax, 20dBm, 30m | 25.76s |
| RTS/CTS enabled | csma_bianchi | ax, 20dBm, 30m, rts_cts | 25.76s |

---

## RF Configuration Reference

All RF parameters can be set in the scenario YAML or overridden via CLI flags:

| Parameter | YAML Key | CLI Flag | Default | Unit |
|-----------|----------|----------|---------|------|
| Transmit power | `tx_power_dBm` | `--tx-power` | 20.0 | dBm |
| Carrier frequency | `freq_ghz` | `--freq` | 5.0 | GHz |
| Path loss exponent | `path_loss_exponent` | `--path-loss-exponent` | 3.0 | -- |
| Noise floor | `noise_floor_dBm` | -- | -95.0 | dBm |
| CCA threshold | `cca_threshold_dBm` | -- | -82.0 | dBm |
| Channel width | `channel_width_mhz` | -- | 20 | MHz |
| WiFi standard | `wifi_standard` | `--wifi-standard` | ax | n/ac/ax |
| Shadow fading | `shadow_fading_sigma` | -- | 0.0 | dB |
| RTS/CTS | `rts_cts` | `--rts-cts` | false | -- |

!!! tip "YAML rf section example"
    ```yaml
    config:
      interference: csma_bianchi
      rf:
        tx_power_dBm: 20
        freq_ghz: 5.0
        path_loss_exponent: 3.0
        noise_floor_dBm: -95
        cca_threshold_dBm: -82
        channel_width_mhz: 20
        wifi_standard: "ax"
        shadow_fading_sigma: 0.0
        rts_cts: false
    ```

---

## Key Concepts Recap

| Concept | Description |
|---------|-------------|
| **PHY rate** | Physical layer data rate, determined by SNR and MCS table |
| **Conflict graph** | Graph of links that cannot transmit simultaneously (within CS range) |
| **Bianchi efficiency** | Fraction of channel time carrying successful payload (accounts for collisions, backoff, idle slots) |
| **Max clique size** | Largest set of mutually-conflicting links; used by csma_clique model |
| **Carrier sensing range** | Maximum distance at which CCA detects a transmission |
| **Hidden terminal** | Active link not in the conflict graph that degrades SINR at a receiver |

## What's Next

| Tutorial | Topic |
|----------|-------|
| [Tutorial 4: Compare Schedulers](tutorial-4-compare-schedulers.md) | Systematic scheduler comparison across multiple scenarios |
| [Tutorial 5: Viz Walkthrough](tutorial-5-viz-walkthrough.md) | Visualize simulation results in the browser |

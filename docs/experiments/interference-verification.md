# Interference Verification

The `run_interference_verification.py` script validates the `csma_bianchi` WiFi
interference model by comparing simulation results against analytical predictions
computed directly from the WiFi RF functions. It runs **nine experiments**
covering single-link PHY rates, parallel-link contention, hidden terminal SINR
degradation, multi-phase rate transitions, bandwidth sharing, and combined
effects.

---

## Running the Script

```bash
python run_interference_verification.py
```

Output directory: `/tmp/ncsim_interference_verification` (configurable via the
`OUTDIR` variable in the script).

!!! info "Default RF Configuration"
    All experiments use the same default `RFConfig`:

    | Parameter | Value |
    |---|---|
    | TX power | 20 dBm |
    | Frequency | 5 GHz |
    | Path loss exponent | 3.0 |
    | Noise floor | -95 dBm |
    | CCA threshold | -82 dBm |
    | Channel width | 20 MHz |
    | WiFi standard | 802.11ax |
    | Shadow fading | 0 (disabled) |
    | RTS/CTS | disabled |

    Data size per transfer: **10 MB**. Tolerance for all checks: **1%**.

---

## Experiment 1: Link Length vs Data Rate (Single Link)

Varies the distance between a single transmitter-receiver pair (`n0` to `n1`)
with no other links present.

- **Purpose:** Verify that the PHY rate matches the analytical SNR-to-MCS
  prediction when there is zero interference.
- **Distances tested:** 1m, 3m, 5m, 8m, 12m, 16m, 20m, 25m, 30m, 36m, 42m,
  50m, 58m, 66m, 75m, 85m, 95m, 105m, 120m, 140m.
- **Analytical prediction:**
  `rate_mbps_to_MBps(snr_to_rate_mbps(snr_dB(received_power_dBm(tx, d, rf), noise)))`
- **Verification:** Simulated data rate (computed as `data_size / duration`)
  matches the predicted rate within 1%.

At distances beyond the minimum MCS threshold (SNR < 5 dB), the PHY rate drops
to zero and the simulator uses a 0.001 MB/s fallback.

---

## Experiment 2: Parallel Link Separation vs Interference

Two parallel 30m horizontal links separated by a variable vertical distance.

```
Link A: n0(0,0) -----> n1(30,0)

                 separation (varies)

Link B: n2(0,sep) ---> n3(30,sep)
```

- **Purpose:** Test both contention (within carrier sensing range) and hidden
  terminal (outside carrier sensing range) effects.
- **Separations tested:** 5m, 10m, 15m, 20m, 30m, 40m, 50m, 60m, 65m, 70m,
  75m, 80m, 100m, 140m, 200m.

### Key Behaviors

| Regime | Condition | Behavior |
|---|---|---|
| **Contention** | Separation <= carrier sensing range | Both links in conflict graph. Share airtime via Bianchi MAC: each gets `base_rate * eta(2) / 2`. |
| **Hidden terminal** | Separation > carrier sensing range | Links outside conflict graph. Transmit simultaneously, causing SINR degradation at receivers. |
| **No interference** | Separation very large | Interferer power negligible. Both links approach solo PHY rate. |

- **Verification:** Both links' effective rates match analytical predictions
  (Bianchi contention factor for in-conflict, SINR-based rate for hidden
  terminal) within 1%.

!!! note "Symmetry"
    By construction, both links in this experiment always see identical
    interference geometry. The script verifies that both links produce the same
    rate.

---

## Experiment 3: Two Transmitters to Same Receiver

Two transmitting nodes send to a shared receiver at the origin, with
transmitters placed at 90 degrees apart at equal distance.

```
           n1(d, 0)
            \
             \  link l10
              v
               n0(0, 0)  <-- shared receiver
              ^
             /  link l20
            /
           n2(0, d)
```

- **Purpose:** Test SINR calculation when multiple transmitters target the same
  receiver.
- **Distances tested:** 5m to 130m.
- **Key insight:** When both links are in the conflict graph, they share airtime
  via Bianchi. When they are hidden terminals, both transmitters cause
  equal-power interference at the shared receiver, resulting in very low SINR
  (the model clamps the interference factor to `MIN_FACTOR`).
- **Verification:** Both links' rates match predictions within 1%.

---

## Experiment 4: Three Parallel Links

Three parallel 30m links stacked vertically at equal spacing.

```
Link A: n0(0, 0)     -----> n1(30, 0)
Link B: n2(0, sep)   -----> n3(30, sep)
Link C: n4(0, 2*sep) -----> n5(30, 2*sep)
```

- **Purpose:** Validate multi-interferer SINR, combined Bianchi + SINR factors,
  and symmetry between outer links A and C.
- **Separations tested:** 10m, 20m, 35m, 40m, 50m, 60m, 70m, 75m, 80m, 100m,
  150m.

### Three Regimes

| Regime | Condition | Description |
|---|---|---|
| `all_conf` | All three pairs in conflict graph | 3-way Bianchi contention. All links get `base_rate * eta(3) / 3`. |
| `mixed` | AB and BC in conflict, but AC not | Center link B contends with both; outer links A and C also see each other as hidden terminals. Multi-phase completion. |
| `all_hid` | No conflict graph edges | All interference is SINR-based. Multiple interferers with different distances. Multi-phase completion as links finish. |

- **Verification:** Predicted multi-phase effective rates match simulation
  within 1%. Outer links A and C always have symmetric (equal) rates.

---

## Experiment 5: Staggered Transfer Start

Two parallel 30m links at 100m separation (hidden terminals), with Transfer A
starting later than Transfer B due to a high compute cost on T0.

- **Purpose:** Test dynamic recalculation of SINR when transfers start and
  complete at different times.
- **Key phases:**
    1. **Phase 1:** B transmits solo at base rate for `delta` seconds.
    2. **Phase 2:** Both A and B active; both degrade to SINR rate.
    3. **Phase 3:** After B completes, A returns to solo base rate.
- **Delay costs tested:** 10000, 30000, 50000, 80000 (producing different
  stagger durations).
- **Verification:** Both transfer durations match the multi-phase analytical
  prediction within 1%. A and B always have equal total durations (by symmetry
  of phases).

---

## Experiment 6: Per-Link Bandwidth Sharing

Multiple flows with different data sizes share a single 30m link (`l01`).

- **Purpose:** Verify that concurrent flows on the same link fairly share
  bandwidth, and that when faster flows complete, remaining flows see increased
  bandwidth (multi-phase fair sharing).
- **Test cases:**
    - 3-flow: data sizes 5, 10, 15 MB
    - 3-flow-eq: data sizes 5, 5, 15 MB (two finish simultaneously)
    - 4-flow: data sizes 3, 6, 9, 12 MB
- **Verification:** Each flow's duration matches the multi-phase prediction from
  `predict_fair_share_durations()` within 1%.

---

## Experiment 7: N-Way Bianchi Scaling

N parallel 30m links at 5m vertical separation (all within carrier sensing
range, forming a complete conflict graph).

- **Purpose:** Verify that Bianchi efficiency scales correctly from N=2 through
  N=8 contending stations.
- **Analytical prediction:** Each link gets `base_rate * eta(N) / N`.
- **Verification:** All N links have the same rate, matching the Bianchi
  prediction within 1%.

| N | eta(N) | Per-link share: eta(N)/N |
|---|---|---|
| 2 | ~0.94 | ~0.47 |
| 3 | ~0.88 | ~0.29 |
| 4 | ~0.82 | ~0.21 |
| 5 | ~0.77 | ~0.15 |
| 8 | ~0.65 | ~0.08 |

---

## Experiment 8: Five-Link Hidden Terminal Cascade

Five parallel 30m links at 100m vertical separation (all hidden terminals to
each other) with data sizes 2, 4, 6, 8, and 10 MB.

- **Purpose:** Test `data_remaining` tracking through 4+ recalculation phases,
  SINR recomputation with a shrinking active link set, and correct completion
  ordering with asymmetric geometry (links at different vertical positions see
  different aggregate interference).
- **Verification:** Each link's total duration matches the cascading multi-phase
  prediction from `predict_hidden_cascade_durations()` within 1%.

---

## Experiment 9: Combined Bandwidth Sharing + Hidden Terminal Interference

Two flows share link `l01` while a third flow on link `l23` (100m away) acts as
a hidden terminal.

- **Purpose:** Test the interaction between per-link fair sharing and inter-link
  SINR interference, including multi-phase transitions as flows complete.
- **Test cases:**
    - `case1`: l01 flows 5/10 MB, l23 flow 8 MB
    - `case2`: l01 flows 5/10 MB, l23 flow 3 MB (l23 finishes earliest)
    - `case3`: l01 flows 3/15 MB, l23 flow 20 MB (l01 flow finishes first)
- **Verification:** All three flow durations match the multi-phase analytical
  prediction within 1%.

---

## Tolerance

All experiments use a **1% tolerance** for matching simulation output to
analytical predictions. The comparison functions are:

- `rates_match(sim, pred)` -- checks `|sim - pred| / pred <= 0.01`
- `durations_match(sim, pred)` -- same relative tolerance on transfer durations

---

## Interpreting Results

Each experiment prints a detailed comparison table with predicted vs. actual
values and a per-row `OK` / `FAIL` indicator.

| Result | Meaning |
|---|---|
| **PASS** | All rows in the experiment match within tolerance. The interference model implementation is correct for this scenario class. |
| **FAIL** | At least one row does not match. Indicates a bug in the interference model, SINR calculation, Bianchi efficiency, or multi-phase rate tracking. |

The final summary at the end of the script reports the pass/fail status for all
nine experiments:

```
  Summary
  ============================
  Experiment 1 (Link Length vs Rate):            PASS
  Experiment 2 (Parallel Link Separation):       PASS
  Experiment 3 (Two TX to Same RX):              PASS
  Experiment 4 (Three Parallel Links):           PASS
  Experiment 5 (Staggered Transfer Start):       PASS
  Experiment 6 (Per-Link Bandwidth Sharing):     PASS
  Experiment 7 (N-Way Bianchi Scaling):          PASS
  Experiment 8 (Five-Link Hidden Cascade):       PASS
  Experiment 9 (Combined Sharing+Interference):  PASS

  Overall: ALL PASS
```

!!! warning "If any experiment fails"
    A failure indicates a regression in the interference model. Check the
    printed comparison table to identify which specific distance or separation
    value failed, then investigate the corresponding analytical helper and the
    `csma_bianchi` implementation in `ncsim/models/interference.py` and
    `ncsim/models/wifi.py`.

---

## Key Imports

The script imports the following from `ncsim.models.wifi` for analytical
predictions:

```python
from ncsim.models.wifi import (
    RFConfig,
    received_power_dBm,
    snr_dB,
    sinr_dB,
    snr_to_rate_mbps,
    rate_mbps_to_MBps,
    carrier_sensing_range,
    bianchi_efficiency,
    path_loss_dB,
    MCS_TABLE_AX,
)
```

| Function | Purpose |
|---|---|
| `RFConfig` | Dataclass holding all RF parameters (TX power, frequency, path loss exponent, etc.) |
| `received_power_dBm` | Compute received power at a given distance: `P_tx - PL(d)` |
| `snr_dB` | Signal-to-noise ratio: `P_rx - noise_floor` |
| `sinr_dB` | Signal-to-interference-plus-noise ratio (linear domain aggregation) |
| `snr_to_rate_mbps` | MCS table lookup: highest rate whose minimum SNR requirement is met |
| `rate_mbps_to_MBps` | Unit conversion from Mbps to MB/s (ncsim's internal unit) |
| `carrier_sensing_range` | Maximum distance at which CCA detects a transmission |
| `bianchi_efficiency` | Bianchi MAC saturation throughput efficiency for N contending stations |
| `path_loss_dB` | Log-distance path loss model |
| `MCS_TABLE_AX` | 802.11ax MCS rate table (min_snr, rate_mbps) pairs |

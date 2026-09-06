# ns-3 20 MHz Experiment Run — Status

**Started:** 2026-04-04 ~1:55 AM
**Completed:** 2026-04-04 ~10:00 AM
**Container:** ns3-ncsim (Docker)
**Config:** 20 MHz channel width, HeMcs5, 30s simTime, 20 seeds each

## What changed (vs previous 80MHz runs)
1. `contention_scaling.cc` + `separation_sweep.cc`: Added `phy.Set("ChannelSettings", StringValue("{0, 20, BAND_5GHZ, 0}"));`
2. `ncsim/models/wifi.py` Bianchi model fixes:
   - Preamble: 52→44μs (correct HE SU PPDU)
   - ACK: 44→28μs (legacy OFDM at 24 Mbps)
   - DIFS→AIFS: 34→43μs (AC_BE: SIFS + 3×slot)
   - Numerator: T_success → goodput_dur (correct Bianchi S formula)
   - T_collision: AIFS → EIFS (SIFS + ACK + AIFS, matching ns-3 behavior)
   - Added OFDM symbol math (ceiling to integer symbols)
   - PSDU = 1542 bytes (MAC26+LLC/SNAP8+IP20+UDP8+payload1472+FCS4+delimiter4)
3. Old 80MHz results backed up to `paper/ns3/results_80mhz_backup/`

## Completion Status
- **Exp 1 (Contention Scaling): COMPLETE** — 160/160 CSVs (n=1..8, 20 seeds each)
- **Exp 2 (Separation Sweep): COMPLETE** — 320/320 CSVs (16 separations × 20 seeds)

## Results Summary

### Contention Scaling (n=1..8)
| n | ncsim (MB/s) | ns-3 (MB/s) | 95% CI | Error |
|---|---|---|---|---|
| 1 | 3.783 | 3.770 | ±0.001 | 0.3% |
| 2 | 1.942 | 1.922 | ±0.002 | 1.1% |
| 3 | 1.274 | 1.238 | ±0.012 | 2.9% |
| 4 | 0.936 | 0.885 | ±0.007 | 5.4% |
| 5 | 0.734 | 0.689 | ±0.003 | 6.2% |
| 6 | 0.601 | 0.559 | ±0.010 | 7.0% |
| 7 | 0.507 | 0.469 | ±0.002 | 7.6% |
| 8 | 0.411 | 0.405 | ±0.013 | 1.5% |

**Mean error: 4.0%, Max: 7.6%** (down from 15-20% before fixes)

### Separation Sweep
| sep (m) | Regime | ncsim (MB/s) | ns-3 (MB/s) | 95% CI | Error |
|---|---|---|---|---|---|
| 10–20 | contention | 1.942 | 1.922 | ±0.002 | 1.1% |
| 30–60 | contention | 1.942 | 2.058 | ±0.001 | 5.9% |
| 65–70 | contention | 1.942 | 2.009 | ±0.003 | 3.4% |
| 72–90 | hidden terminal | 1.504 | 1.34–1.36 | varies | 10–11% |
| 100 | hidden terminal | 1.504 | 1.496 | ±0.005 | 0.5% |
| 120 | hidden terminal | 3.783 | 3.616 | ±0.001 | 4.4% |
| 150–200 | hidden terminal | 3.783 | 3.770 | ±0.001 | 0.3% |

### Key Findings
- **Contention regime (sep ≤ 70m):** Excellent agreement, mean error ~3%
- **Hidden terminal collapse (sep=72–100m):** Capture model correctly predicts frame loss. Max error 11% at sep=72–90 (residual due to simplified airtime model).
- **Hidden terminal recovery (sep ≥ 120m):** Capture threshold model correctly predicts sharp recovery to solo rate. SINR crosses the MCS5 decode threshold (17 dB) between sep=100 and sep=120, matching ns-3's behavior.

### Capture Effect Model (added 2026-04-04)
Replaced continuous SINR-to-rate mapping with threshold-based capture model:
- **Decode threshold** = MCS selection threshold − 5 dB (capture margin)
- **Frame success** = binary: succeed if SINR ≥ decode threshold, fail otherwise
- **Temporal overlap** = interferer transmits data ~60% of the time (Bianchi n=1 timing)
- **Throughput** = solo_rate × [(1 − f_busy) + f_busy × p_capture]

Rationale: 802.11 frames succeed or fail at their selected MCS — there is no "partial success" at a lower rate. The 5 dB capture margin accounts for implementation/fading margins built into rate selection thresholds. See `CAPTURE_EFFECT_REFERENCES.md` for full justification.

### Known Model Differences
1. **Bianchi overestimate at high n**: ~5-8% at n=4..7. Known limitation of the stationary fixed-point approximation.
2. **Capture effect in contention**: ncsim's Bianchi model assumes all collisions fail. ns-3 allows preamble capture when SIR > ~4 dB, boosting throughput by ~6% at sep=30–70m.
3. **Hidden terminal airtime**: The Bianchi n=1 duty cycle (~60%) slightly underestimates frame loss at sep=72–90m. Additional loss may come from ACK interference and retransmission-induced backoff changes.

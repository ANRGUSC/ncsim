#!/usr/bin/env python3
"""Generate ncsim baseline predictions for ns-3 cross-validation.

Produces JSON files with ncsim's analytical predictions for:
  - Experiment 1: N-way contention scaling (n=1..8)
  - Experiment 2: Two-link separation sweep (s=10..200m)

These are the "ground truth" from ncsim's model to overlay against ns-3 results.
"""

import json
import math
import sys
from pathlib import Path

# Import ncsim WiFi model
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from ncsim.models.wifi import (
    RFConfig,
    received_power_dBm,
    snr_dB,
    sinr_dB,
    snr_to_rate_mbps,
    rate_mbps_to_MBps,
    carrier_sensing_range,
    bianchi_efficiency,
    euclidean_distance,
    path_loss_dB,
    capture_sinr_threshold,
    saturated_airtime_fraction,
    hidden_terminal_success_rate,
)
from ncsim.models.network import Position

RF = RFConfig()  # defaults match ns-3 config exactly
LINK_DISTANCE = 30.0  # meters


def compute_base_rate():
    """Base PHY rate for a 30m link with default RF config."""
    rx_pow = received_power_dBm(RF.tx_power_dBm, LINK_DISTANCE, RF)
    link_snr = snr_dB(rx_pow, RF.noise_floor_dBm)
    rate_mbps = snr_to_rate_mbps(link_snr, RF.wifi_standard, RF.channel_width_mhz)
    rate_MBps = rate_mbps_to_MBps(rate_mbps)
    return rate_mbps, rate_MBps, link_snr


def experiment1_predictions():
    """N-way contention scaling: n=1..8 co-located links."""
    rate_mbps, rate_MBps, link_snr = compute_base_rate()
    cs_range = carrier_sensing_range(RF)

    results = {
        "experiment": "contention_scaling",
        "description": "N co-located 30m links, all within CS range, pure contention",
        "parameters": {
            "link_distance_m": LINK_DISTANCE,
            "vertical_separation_m": 5.0,
            "base_rate_Mbps": rate_mbps,
            "base_rate_MBps": round(rate_MBps, 4),
            "snr_dB": round(link_snr, 2),
            "cs_range_m": round(cs_range, 2),
            "CWmin": 16,
            "CWmax": 1024,
        },
        "predictions": [],
    }

    for n in range(1, 9):
        eta = bianchi_efficiency(n)
        per_link_factor = eta / n
        per_link_MBps = rate_MBps * per_link_factor
        per_link_Mbps = rate_mbps * per_link_factor

        results["predictions"].append({
            "n": n,
            "eta_n": round(eta, 4),
            "eta_n_over_n": round(per_link_factor, 4),
            "per_link_MBps": round(per_link_MBps, 4),
            "per_link_Mbps": round(per_link_Mbps, 4),
        })

    return results


def experiment2_predictions():
    """Two-link separation sweep: s=10..200m."""
    rate_mbps, rate_MBps, link_snr = compute_base_rate()
    cs_range = carrier_sensing_range(RF)

    separations = [10, 20, 30, 40, 50, 60, 65, 70, 72, 75, 80, 90, 100, 120, 150, 200]

    results = {
        "experiment": "separation_sweep",
        "description": "Two parallel 30m links at varying vertical separation",
        "parameters": {
            "link_distance_m": LINK_DISTANCE,
            "base_rate_Mbps": rate_mbps,
            "base_rate_MBps": round(rate_MBps, 4),
            "snr_dB": round(link_snr, 2),
            "cs_range_m": round(cs_range, 2),
        },
        "predictions": [],
    }

    for sep in separations:
        # Check if links are within CS range (any node pair)
        # Link A: STA(0,0) -> AP(30,0)
        # Link B: STA(0,sep) -> AP(30,sep)
        # Distances to check (no RTS/CTS):
        #   tx_A(0,0) to tx_B(0,sep) = sep
        #   tx_A(0,0) to rx_B(30,sep) = sqrt(900+sep^2)
        #   tx_B(0,sep) to tx_A(0,0) = sep
        #   tx_B(0,sep) to rx_A(30,0) = sqrt(900+sep^2)
        d_tx_tx = sep
        d_tx_rx = math.sqrt(LINK_DISTANCE**2 + sep**2)

        in_cs_range = (d_tx_tx <= cs_range) or (d_tx_rx <= cs_range)

        if in_cs_range:
            # Contention regime: Bianchi with n=2
            eta = bianchi_efficiency(2)
            factor = eta / 2.0
            regime = "contention"
            per_link_MBps = rate_MBps * factor
            per_link_Mbps = rate_mbps * factor
        else:
            # Hidden terminal regime: capture-threshold model
            #
            # 802.11 frames succeed or fail at their selected MCS.
            # When interference is present, if SINR >= decode threshold
            # the frame is captured (succeeds).  Otherwise it fails.
            # The interferer only transmits for a fraction of the time
            # (saturated airtime), so some frames see no interference.
            #
            # Refs: Daneshgaran et al. (2008) DOI:10.1109/tcomm.2008.060397
            #       Zorzi & Rao (1994)        DOI:10.1109/49.329345
            i_dist = math.sqrt(LINK_DISTANCE**2 + sep**2)
            rx_pow = received_power_dBm(RF.tx_power_dBm, LINK_DISTANCE, RF)
            i_pow = received_power_dBm(RF.tx_power_dBm, i_dist, RF)
            link_sinr = sinr_dB(rx_pow, [i_pow], RF.noise_floor_dBm)

            # Solo rate (Bianchi n=1, MAC-limited)
            solo_eta = bianchi_efficiency(1)
            solo_MBps = rate_MBps * solo_eta

            # Capture threshold for the link's operating MCS
            ct = capture_sinr_threshold(
                rate_mbps, RF.wifi_standard, RF.channel_width_mhz
            )

            # Interferer's data transmission duty cycle
            f_busy = saturated_airtime_fraction()

            # Frame success rate (temporal overlap + capture)
            p_success = hidden_terminal_success_rate(link_sinr, ct, f_busy)

            regime = "hidden_terminal"
            per_link_MBps = solo_MBps * p_success
            per_link_Mbps = per_link_MBps * 8.0
            factor = per_link_MBps / rate_MBps

        results["predictions"].append({
            "separation_m": sep,
            "regime": regime,
            "in_cs_range": in_cs_range,
            "factor": round(factor, 4),
            "per_link_MBps": round(per_link_MBps, 4),
            "per_link_Mbps": round(per_link_Mbps, 4),
        })

    return results


def main():
    outdir = Path(__file__).resolve().parent.parent / "ns3" / "results"
    outdir.mkdir(parents=True, exist_ok=True)

    exp1 = experiment1_predictions()
    exp2 = experiment2_predictions()

    with open(outdir / "ncsim_contention_predictions.json", "w") as f:
        json.dump(exp1, f, indent=2)
    print(f"Wrote {outdir / 'ncsim_contention_predictions.json'}")

    with open(outdir / "ncsim_separation_predictions.json", "w") as f:
        json.dump(exp2, f, indent=2)
    print(f"Wrote {outdir / 'ncsim_separation_predictions.json'}")

    # Print summary
    print("\n=== Experiment 1: Contention Scaling ===")
    print(f"Base rate: {exp1['parameters']['base_rate_MBps']} MB/s "
          f"({exp1['parameters']['base_rate_Mbps']} Mbps)")
    print(f"CS range: {exp1['parameters']['cs_range_m']} m")
    print(f"{'n':>3}  {'eta(n)':>8}  {'eta/n':>8}  {'MB/s':>8}  {'Mbps':>8}")
    for p in exp1["predictions"]:
        print(f"{p['n']:3d}  {p['eta_n']:8.4f}  {p['eta_n_over_n']:8.4f}  "
              f"{p['per_link_MBps']:8.4f}  {p['per_link_Mbps']:8.4f}")

    print("\n=== Experiment 2: Separation Sweep ===")
    print(f"{'sep':>5}  {'regime':>15}  {'factor':>8}  {'MB/s':>8}  {'Mbps':>8}")
    for p in exp2["predictions"]:
        print(f"{p['separation_m']:5d}  {p['regime']:>15}  {p['factor']:8.4f}  "
              f"{p['per_link_MBps']:8.4f}  {p['per_link_Mbps']:8.4f}")


if __name__ == "__main__":
    main()

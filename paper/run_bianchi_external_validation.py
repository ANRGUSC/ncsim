#!/usr/bin/env python3
"""
External validation against Bianchi (2000) JSAC Table 1.

Reproduces the normalized saturation throughput S for 802.11 DCF basic access
using the exact FHSS 1 Mbps parameters from:

  G. Bianchi, "Performance Analysis of the IEEE 802.11 Distributed
  Coordination Function," IEEE Journal on Selected Areas in
  Communications, vol. 18, no. 3, pp. 535-547, March 2000.

This script is self-contained (no ncsim imports). It implements Bianchi's
fixed-point solver and throughput formula from scratch using the paper's
notation, then compares the computed values against the published Table 1
results.

Parameters from Bianchi (2000), Table 1 (FHSS system at 1 Mbps):
  - Slot time (sigma):       50 us
  - SIFS:                    28 us
  - DIFS:                    128 us
  - Propagation delay (delta): 1 us
  - Packet payload E[P*]:    8184 bits
  - MAC header:              272 bits
  - PHY header:              128 bits
  - ACK frame:               112 bits + PHY header (128 bits)
  - Channel rate:            1 Mbps

Two configurations are tested:
  - W=32, m=5   (CWmin=32, CWmax=32*2^5=1024)
  - W=128, m=3  (CWmin=128, CWmax=128*2^3=1024)

For n = 5, 10, 15, 20, 25, 30, 35, 40, 45, 50 contending stations.
"""

import json
import os
import sys
from typing import Tuple, Dict, List, Any


# ─── Bianchi Fixed-Point Solver ─────────────────────────────────────────────
#
# The Bianchi (2000) model couples two equations:
#
#   tau = 2(1-2p) / [(1-2p)(W+1) + pW(1-(2p)^m)]     ... eq. (8)
#   p   = 1 - (1 - tau)^(n-1)                          ... eq. (6)
#
# where:
#   tau = transmission probability in a random slot
#   p   = conditional collision probability
#   n   = number of contending stations
#   W   = CWmin (minimum contention window)
#   m   = maximum backoff stage (CWmax = W * 2^m)
#
# We solve via fixed-point iteration: start with tau = 2/(W+1) (the
# collision-free value), then alternate updating p from tau and tau from p
# until convergence.

def _tau_from_p(p: float, W: int, m: int) -> float:
    """Compute tau from p using Bianchi eq. (8).

    tau = 2(1-2p) / [(1-2p)(W+1) + pW(1-(2p)^m)]
    """
    denom_factor = 1.0 - 2.0 * p
    if abs(denom_factor) < 1e-15:
        return 2.0 / (W + 1)
    numerator = 2.0 * denom_factor
    denominator = denom_factor * (W + 1) + p * W * (1.0 - (2.0 * p) ** m)
    if abs(denominator) < 1e-15:
        return 2.0 / (W + 1)
    return max(numerator / denominator, 1e-15)


def bianchi_solve_tau_p(
    n: int,
    W: int,
    m: int,
    max_iter: int = 200,
    tol: float = 1e-12,
) -> Tuple[float, float]:
    """Solve Bianchi's coupled fixed-point equations for tau and p.

    Uses bisection on tau for robust convergence. The simple fixed-point
    iteration tau -> p -> tau can oscillate (derivative > 1) for small W
    and large n, so bisection is used instead.

    Define f(tau) = tau - g(tau), where g(tau) maps:
      tau -> p = 1-(1-tau)^(n-1) -> tau' via eq. (8)
    We find the root of f(tau) = 0 by bisection on (0, 1).

    Args:
        n: Number of contending stations (>= 2 for meaningful collisions).
        W: CWmin (minimum contention window size).
        m: Maximum backoff stage. CWmax = W * 2^m.
        max_iter: Maximum bisection iterations.
        tol: Convergence tolerance on interval width.

    Returns:
        (tau, p) -- the transmission probability and collision probability.
    """
    if n <= 1:
        tau = 2.0 / (W + 1)
        return tau, 0.0

    def f(tau_val: float) -> float:
        """Residual: tau - g(tau). Root gives the fixed point."""
        p_val = 1.0 - (1.0 - tau_val) ** (n - 1)
        p_val = min(max(p_val, 1e-15), 1.0 - 1e-15)
        tau_prime = _tau_from_p(p_val, W, m)
        return tau_val - tau_prime

    # Bisection bounds: tau must be in (0, 1)
    lo, hi = 1e-10, 1.0 - 1e-10

    # Verify sign change (f should be negative near 0 and positive near 1)
    f_lo, f_hi = f(lo), f(hi)
    if f_lo * f_hi > 0:
        # Fallback: try narrower bounds
        lo, hi = 1e-10, 2.0 / (W + 1) * 5
        hi = min(hi, 1.0 - 1e-10)
        f_lo, f_hi = f(lo), f(hi)

    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        f_mid = f(mid)
        if abs(f_mid) < tol or (hi - lo) < tol:
            tau = mid
            break
        if f_mid * f(lo) < 0:
            hi = mid
        else:
            lo = mid
    else:
        tau = (lo + hi) / 2.0

    p = 1.0 - (1.0 - tau) ** (n - 1)
    return tau, p


# ─── Throughput Computation ─────────────────────────────────────────────────
#
# Bianchi (2000) eq. (7): Normalized saturation throughput for basic access.
#
#   S = P_s * P_tr * E[P] / E[slot]
#
# where:
#   P_tr  = 1 - (1-tau)^n           probability that at least one station
#                                     transmits in the slot
#   P_s   = n*tau*(1-tau)^(n-1) / P_tr   conditional probability that a
#                                          transmission is successful (exactly
#                                          one station transmits)
#   E[P]  = payload duration in us
#
#   E[slot] = (1-P_tr)*sigma + P_tr*P_s*T_s + P_tr*(1-P_s)*T_c
#
# For basic access (no RTS/CTS):
#   T_s = H + E[P] + SIFS + delta + ACK_dur + DIFS + delta
#   T_c = H + E[P*] + DIFS + delta
#
# where:
#   sigma  = empty slot time
#   H      = total header duration (PHY + MAC headers at channel rate)
#   E[P]   = payload duration
#   delta  = propagation delay
#   ACK_dur = ACK frame duration (ACK bits + PHY header, at channel rate)
#   E[P*]  = duration of the longest payload involved in a collision
#            (= E[P] for fixed-size packets, which Bianchi assumes)

def bianchi_throughput_S(
    n: int,
    W: int,
    m: int,
    slot_us: float,
    sifs_us: float,
    difs_us: float,
    prop_us: float,
    payload_bits: float,
    mac_header_bits: float,
    phy_header_bits: float,
    ack_bits: float,
    rate_mbps: float,
) -> Dict[str, float]:
    """Compute normalized saturation throughput S per Bianchi (2000).

    All timing parameters are in microseconds. The channel rate converts
    bit counts to durations: duration_us = bits / rate_mbps.

    Args:
        n:               Number of contending stations.
        W:               CWmin (minimum contention window).
        m:               Max backoff stage (CWmax = W * 2^m).
        slot_us:         Empty slot duration (sigma) in us.
        sifs_us:         SIFS duration in us.
        difs_us:         DIFS duration in us.
        prop_us:         One-way propagation delay (delta) in us.
        payload_bits:    Packet payload size in bits (E[P*]).
        mac_header_bits: MAC header size in bits.
        phy_header_bits: PHY header size in bits.
        ack_bits:        ACK frame body size in bits (MAC-level).
        rate_mbps:       Channel data rate in Mbps.

    Returns:
        Dictionary with keys: S, tau, p, P_tr, P_s, T_s, T_c, and all
        intermediate values for inspection.
    """
    # Solve the fixed-point equations
    tau, p = bianchi_solve_tau_p(n, W, m)

    # Probabilities (Bianchi eq. 5-6)
    P_tr = 1.0 - (1.0 - tau) ** n
    if P_tr > 0:
        P_s = n * tau * (1.0 - tau) ** (n - 1) / P_tr
    else:
        P_s = 0.0

    # ─── Frame durations in microseconds ────────────────────────────
    #
    # At 1 Mbps, 1 bit = 1 us, so bits/rate_mbps gives us directly.
    #
    # Header duration H: includes both PHY and MAC headers.
    #   H = (phy_header_bits + mac_header_bits) / rate_mbps
    #
    # Payload duration E[P]:
    #   E[P] = payload_bits / rate_mbps
    #
    # ACK duration: the ACK frame has its own PHY header prepended.
    #   ACK_dur = (ack_bits + phy_header_bits) / rate_mbps
    #
    # For FHSS at 1 Mbps these evaluate to:
    #   H       = (128 + 272) / 1 = 400 us
    #   E[P]    = 8184 / 1       = 8184 us
    #   ACK_dur = (112 + 128) / 1 = 240 us

    header_dur = (phy_header_bits + mac_header_bits) / rate_mbps
    payload_dur = payload_bits / rate_mbps
    ack_dur = (ack_bits + phy_header_bits) / rate_mbps

    # Successful transmission duration T_s (basic access, eq. 7):
    #   T_s = H + E[P] + SIFS + delta + ACK_dur + DIFS + delta
    T_s = header_dur + payload_dur + sifs_us + prop_us + ack_dur + difs_us + prop_us

    # Collision duration T_c (basic access):
    #   T_c = H + E[P*] + DIFS + delta
    # With fixed packet sizes, E[P*] = E[P].
    T_c = header_dur + payload_dur + difs_us + prop_us

    # Expected slot duration E[slot] (denominator of eq. 7):
    #   E[slot] = (1 - P_tr) * sigma
    #           + P_tr * P_s * T_s
    #           + P_tr * (1 - P_s) * T_c
    sigma = slot_us
    E_slot = (
        (1.0 - P_tr) * sigma
        + P_tr * P_s * T_s
        + P_tr * (1.0 - P_s) * T_c
    )

    # Normalized saturation throughput S (eq. 7):
    #   S = P_s * P_tr * E[P] / E[slot]
    # This is the fraction of time the channel carries successful payload.
    if E_slot > 0:
        S = P_s * P_tr * payload_dur / E_slot
    else:
        S = 0.0

    return {
        "S": S,
        "tau": tau,
        "p": p,
        "P_tr": P_tr,
        "P_s": P_s,
        "T_s_us": T_s,
        "T_c_us": T_c,
        "E_slot_us": E_slot,
        "header_dur_us": header_dur,
        "payload_dur_us": payload_dur,
        "ack_dur_us": ack_dur,
    }


# ─── FHSS 1 Mbps Parameters (Bianchi 2000, Table II) ──────────────────────

FHSS_PARAMS = {
    "slot_us": 50.0,            # sigma: slot time
    "sifs_us": 28.0,            # SIFS
    "difs_us": 128.0,           # DIFS = SIFS + 2 * slot
    "prop_us": 1.0,             # delta: propagation delay
    "payload_bits": 8184.0,     # E[P*]: packet payload
    "mac_header_bits": 272.0,   # MAC header
    "phy_header_bits": 128.0,   # PHY header (PLCP preamble + header)
    "ack_bits": 112.0,          # ACK frame body (MAC-level)
    "rate_mbps": 1.0,           # FHSS channel rate
}

# ─── Test Configurations ───────────────────────────────────────────────────
#
# Two configurations matching Bianchi (2000) Figure 6 curves:
#   - W=32, m=5:  CWmin=32, CWmax=1024
#   - W=128, m=3: CWmin=128, CWmax=1024
#
# Plus W=32, m=3 to validate against Table III exact values (n=2,3).

CONFIGS = [
    {"W": 32,  "m": 3, "label": "W=32, m=3 (CWmax=256) [Table III validation]",
     "n_values": [2, 3, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50]},
    {"W": 32,  "m": 5, "label": "W=32, m=5 (CWmax=1024) [Fig. 6]",
     "n_values": [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]},
    {"W": 128, "m": 3, "label": "W=128, m=3 (CWmax=1024) [Fig. 6]",
     "n_values": [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]},
]

# Default station counts for Figure 6 curves
N_VALUES = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]

# ─── Published Values from Bianchi (2000) ─────────────────────────────────
#
# Table III provides exact analytical throughput S for basic access,
# FHSS 1 Mbps, W=32, m=3, at n=2 and n=3 stations. These are the only
# numerical throughput values published in the paper; the n=5..50 curves
# for W=32/m=5 and W=128/m=3 appear only in Figure 6 as plotted curves.
#
# Source: Bianchi, "Performance Analysis of the IEEE 802.11 Distributed
# Coordination Function," IEEE JSAC, vol. 18, no. 3, pp. 535-547,
# March 2000. DOI: 10.1109/49.840210. Table III, column "bas".

PUBLISHED_TABLE_III = {
    # W=32, m=3, basic access, FHSS 1 Mbps
    (32, 3): {
        2: 0.8473,
        3: 0.8368,
    },
}


# ─── Main ──────────────────────────────────────────────────────────────────

def main() -> None:
    """Run external validation and print/save results."""

    print("=" * 78)
    print("External Validation: Bianchi (2000) JSAC")
    print("IEEE 802.11 DCF Basic Access, FHSS 1 Mbps")
    print("Table III exact match + Figure 6 curve reproduction")
    print("=" * 78)
    print()

    # Print the FHSS parameters for transparency
    print("FHSS 1 Mbps System Parameters:")
    print(f"  Slot time (sigma):     {FHSS_PARAMS['slot_us']:.0f} us")
    print(f"  SIFS:                  {FHSS_PARAMS['sifs_us']:.0f} us")
    print(f"  DIFS:                  {FHSS_PARAMS['difs_us']:.0f} us")
    print(f"  Propagation delay:     {FHSS_PARAMS['prop_us']:.0f} us")
    print(f"  Payload (E[P*]):       {FHSS_PARAMS['payload_bits']:.0f} bits")
    print(f"  MAC header:            {FHSS_PARAMS['mac_header_bits']:.0f} bits")
    print(f"  PHY header:            {FHSS_PARAMS['phy_header_bits']:.0f} bits")
    print(f"  ACK body:              {FHSS_PARAMS['ack_bits']:.0f} bits")
    print(f"  Channel rate:          {FHSS_PARAMS['rate_mbps']:.1f} Mbps")
    print()

    # Compute derived durations for display
    H = (FHSS_PARAMS["phy_header_bits"] + FHSS_PARAMS["mac_header_bits"]) / FHSS_PARAMS["rate_mbps"]
    EP = FHSS_PARAMS["payload_bits"] / FHSS_PARAMS["rate_mbps"]
    ACK = (FHSS_PARAMS["ack_bits"] + FHSS_PARAMS["phy_header_bits"]) / FHSS_PARAMS["rate_mbps"]
    T_s = H + EP + FHSS_PARAMS["sifs_us"] + FHSS_PARAMS["prop_us"] + ACK + FHSS_PARAMS["difs_us"] + FHSS_PARAMS["prop_us"]
    T_c = H + EP + FHSS_PARAMS["difs_us"] + FHSS_PARAMS["prop_us"]

    print("Derived Durations:")
    print(f"  Header (H):            {H:.0f} us")
    print(f"  Payload (E[P]):        {EP:.0f} us")
    print(f"  ACK duration:          {ACK:.0f} us")
    print(f"  T_s (success):         {T_s:.0f} us")
    print(f"  T_c (collision):       {T_c:.0f} us")
    print()

    # Collect all results
    all_results: Dict[str, Any] = {
        "description": "External validation against Bianchi (2000) JSAC",
        "paper": "Bianchi, 'Performance Analysis of the IEEE 802.11 DCF', "
                 "IEEE JSAC, vol. 18, no. 3, March 2000. DOI: 10.1109/49.840210",
        "system": "FHSS 1 Mbps, basic access (no RTS/CTS)",
        "parameters": FHSS_PARAMS,
        "derived_durations_us": {
            "header_H": H,
            "payload_EP": EP,
            "ack_duration": ACK,
            "T_s_success": T_s,
            "T_c_collision": T_c,
        },
        "configs": [],
    }

    for config in CONFIGS:
        W = config["W"]
        m = config["m"]
        label = config["label"]
        n_values = config.get("n_values", N_VALUES)

        print("-" * 78)
        print(f"Configuration: {label}")
        print(f"  CWmin = {W}, CWmax = {W * (2 ** m)}")
        print("-" * 78)
        print()

        # Table header
        header_line = (
            f"{'n':>4s}  "
            f"{'S (computed)':>12s}  "
            f"{'S (published)':>13s}  "
            f"{'Rel. Error':>10s}  "
            f"{'tau':>10s}  "
            f"{'p':>10s}  "
            f"{'P_tr':>8s}  "
            f"{'P_s':>8s}"
        )
        print(header_line)
        print("-" * len(header_line))

        config_results = {
            "W": W,
            "m": m,
            "CWmax": W * (2 ** m),
            "label": label,
            "stations": [],
        }

        # Look up published values from Table III
        published_for_config = PUBLISHED_TABLE_III.get((W, m), {})

        for n in n_values:
            # Compute throughput using Bianchi's exact formulas
            result = bianchi_throughput_S(n=n, W=W, m=m, **FHSS_PARAMS)
            S_computed = result["S"]

            # Compare against published values if available
            S_published = published_for_config.get(n)
            if S_published is not None and S_published > 0:
                rel_error = abs(S_computed - S_published) / S_published
                rel_error_str = f"{rel_error:10.4%}"
            else:
                rel_error = None
                rel_error_str = f"{'---':>10s}"

            # Print row
            S_pub_str = f"{S_published:.6f}" if S_published is not None else "---"
            print(
                f"{n:4d}  "
                f"{S_computed:12.6f}  "
                f"{S_pub_str:>13s}  "
                f"{rel_error_str}  "
                f"{result['tau']:10.6f}  "
                f"{result['p']:10.6f}  "
                f"{result['P_tr']:8.4f}  "
                f"{result['P_s']:8.4f}"
            )

            # Store per-station results
            station_result = {
                "n": n,
                "S_computed": round(S_computed, 6),
                "S_published": S_published,
                "relative_error": round(rel_error, 6) if rel_error is not None else None,
                "tau": round(result["tau"], 8),
                "p": round(result["p"], 8),
                "P_tr": round(result["P_tr"], 6),
                "P_s": round(result["P_s"], 6),
                "T_s_us": round(result["T_s_us"], 2),
                "T_c_us": round(result["T_c_us"], 2),
                "E_slot_us": round(result["E_slot_us"], 2),
            }
            config_results["stations"].append(station_result)

        print()
        all_results["configs"].append(config_results)

    # ─── Summary: Table III Validation ────────────────────────────────────
    print("=" * 78)
    print("Table III Validation (exact numerical comparison)")
    print("=" * 78)
    print()

    table_iii_results = all_results["configs"][0]  # W=32, m=3
    for s in table_iii_results["stations"]:
        if s["S_published"] is not None:
            print(f"  n={s['n']}: computed={s['S_computed']:.6f}, "
                  f"published={s['S_published']:.4f}, "
                  f"error={s['relative_error']:.4%}")
    print()

    # ─── Summary: Figure 6 Curves ────────────────────────────────────────
    print("=" * 78)
    print("Figure 6 Curve Data (no exact published values available)")
    print("=" * 78)
    print()
    print("Bianchi (2000) presents throughput curves for W=32/m=5 and W=128/m=3")
    print("in Figure 6 as plots, not tabulated values. Our computed values")
    print("reproduce these curves analytically.")
    print()

    # ─── Cross-check: known analytical properties ───────────────────────
    print("-" * 78)
    print("Analytical Cross-Checks")
    print("-" * 78)
    print()

    # Check 1: S should generally decrease with n (except possible
    # non-monotonicity at small n with large CWmin, which is a known
    # property of the Bianchi model)
    for config_result in all_results["configs"]:
        S_values = [s["S_computed"] for s in config_result["stations"]]
        is_monotonic = all(
            S_values[i] >= S_values[i + 1] for i in range(len(S_values) - 1)
        )
        status = "PASS" if is_monotonic else "NOTE"
        label = config_result['label']
        if not is_monotonic:
            print(f"  [{status}] S non-monotonic at small n ({label})")
            print(f"         (known Bianchi model property: large CWmin leaves")
            print(f"          idle slots at small n; adding stations fills them)")
        else:
            print(f"  [{status}] S is monotonically decreasing with n ({label})")

    # Check 2: tau should be in (0, 1)
    for config_result in all_results["configs"]:
        taus = [s["tau"] for s in config_result["stations"]]
        valid_range = all(0 < t < 1 for t in taus)
        status = "PASS" if valid_range else "FAIL"
        print(f"  [{status}] tau in (0,1) for all n ({config_result['label']})")

    # Check 3: S should be bounded by theoretical max
    S_max = EP / T_s
    print(f"\n  Theoretical single-station efficiency (E[P]/T_s): {S_max:.6f}")
    for config_result in all_results["configs"]:
        all_below = all(s["S_computed"] <= S_max + 1e-9 for s in config_result["stations"])
        status = "PASS" if all_below else "FAIL"
        print(f"  [{status}] S <= theoretical max for all n ({config_result['label']})")

    print()

    # ─── Save Results to JSON ───────────────────────────────────────────
    script_dir = os.path.dirname(os.path.abspath(__file__))
    results_dir = os.path.join(script_dir, "_results")
    os.makedirs(results_dir, exist_ok=True)

    output_path = os.path.join(results_dir, "bianchi_validation.json")
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"Results saved to: {output_path}")
    print()


if __name__ == "__main__":
    main()

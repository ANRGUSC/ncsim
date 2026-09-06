from typing import Tuple, Dict
def bianchi_solve_tau_p(n: int, W: int, m: int, **_unused) -> Tuple[float, float]:
    """Use the production solver; independent reference tests live in tests/."""
    from ncsim.models.wifi import bianchi_fixed_point
    return bianchi_fixed_point(n, W, m)


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

"""
802.11 CSMA/CA wireless link model.

Provides RF propagation, MCS rate selection, conflict graph construction,
Bianchi MAC efficiency, and support for two link model variants:
  - csma_clique: Static PHY rate / max_clique_size
  - csma_bianchi: SINR-based dynamic rate * Bianchi efficiency

Physical layer models:
  - Log-distance path loss with Friis reference at d0=1m
  - SNR and SINR computation (linear domain for interference aggregation)
  - MCS rate tables for 802.11n, 802.11ac, 802.11ax (1 spatial stream)
  - Bianchi saturation throughput model for MAC efficiency

References:
  - Bianchi, "Performance Analysis of the IEEE 802.11 DCF", IEEE JSAC, 2000
  - Gupta & Kumar, "The Capacity of Wireless Networks", IEEE Trans IT, 2000
  - Garetto, Salonidis, Knightly, "Modeling Per-Flow Throughput", IEEE/ACM ToN, 2008
"""

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Optional, FrozenSet

from ncsim.models.network import Network, Node, Link, Position


# ─── RF Configuration ────────────────────────────────────────────

@dataclass(frozen=True)
class RFConfig:
    """802.11 RF parameters. Immutable after creation.

    Attributes:
        tx_power_dBm: Transmit power in dBm (typical AP: 15-23)
        freq_ghz: Carrier frequency in GHz (2.4 or 5.0)
        path_loss_exponent: Path loss exponent n (2.0=free space, 3-4=indoor)
        noise_floor_dBm: Effective noise floor including receiver noise figure
        cca_threshold_dBm: Clear Channel Assessment signal detect threshold
        channel_width_mhz: Channel width (20, 40, 80, 160)
        wifi_standard: MCS table selection ("n", "ac", "ax")
        shadow_fading_sigma: Std dev of log-normal shadow fading in dB (0=none)
        rts_cts: Enable RTS/CTS (extends conflict zone to protect receivers)
    """
    tx_power_dBm: float = 20.0
    freq_ghz: float = 5.0
    path_loss_exponent: float = 3.0
    noise_floor_dBm: float = -95.0
    cca_threshold_dBm: float = -82.0
    channel_width_mhz: int = 20
    wifi_standard: str = "ax"
    shadow_fading_sigma: float = 0.0
    rts_cts: bool = False


# ─── Path Loss Model ─────────────────────────────────────────────

def friis_reference_loss_dB(freq_ghz: float, d0: float = 1.0) -> float:
    """Free-space path loss at reference distance d0 (Friis equation).

    PL(d0) = 20*log10(4*pi*d0*f/c)

    At 5 GHz, d0=1m: ~46.4 dB
    At 2.4 GHz, d0=1m: ~40.0 dB
    """
    freq_hz = freq_ghz * 1e9
    c = 3e8
    return 20 * math.log10(4 * math.pi * d0 * freq_hz / c)


def path_loss_dB(
    distance: float,
    freq_ghz: float,
    path_loss_exponent: float,
    d0: float = 1.0,
) -> float:
    """Log-distance path loss model.

    PL(d) = PL(d0) + 10*n*log10(d/d0)

    Args:
        distance: TX-RX distance in meters (must be > 0)
        freq_ghz: Carrier frequency in GHz
        path_loss_exponent: Path loss exponent n
        d0: Reference distance in meters
    """
    if distance <= 0:
        return 0.0
    if distance < d0:
        distance = d0
    pl_d0 = friis_reference_loss_dB(freq_ghz, d0)
    return pl_d0 + 10 * path_loss_exponent * math.log10(distance / d0)


def received_power_dBm(
    tx_power_dBm: float,
    distance: float,
    rf: RFConfig,
    shadow_fading_dB: float = 0.0,
) -> float:
    """Compute received power at a given distance.

    P_rx = P_tx - PL(d) - shadow_fading
    """
    pl = path_loss_dB(distance, rf.freq_ghz, rf.path_loss_exponent)
    return tx_power_dBm - pl - shadow_fading_dB


def snr_dB(rx_power_dBm: float, noise_floor_dBm: float) -> float:
    """Signal-to-noise ratio in dB."""
    return rx_power_dBm - noise_floor_dBm


def sinr_dB(
    rx_power_dBm: float,
    interference_powers_dBm: List[float],
    noise_floor_dBm: float,
) -> float:
    """Signal-to-interference-plus-noise ratio in dB.

    SINR = P_signal / (P_noise + sum(P_interferers))
    Computed in linear domain for correct power addition.
    """
    signal_mw = 10 ** (rx_power_dBm / 10)
    noise_mw = 10 ** (noise_floor_dBm / 10)
    interference_mw = sum(10 ** (p / 10) for p in interference_powers_dBm)

    denominator = noise_mw + interference_mw
    if denominator <= 0:
        return float('inf')
    return 10 * math.log10(signal_mw / denominator)


def euclidean_distance(p1: Position, p2: Position) -> float:
    """2D Euclidean distance between two positions."""
    return math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2)


# ─── Carrier Sensing Range ───────────────────────────────────────

def carrier_sensing_range(rf: RFConfig, d0: float = 1.0) -> float:
    """Maximum distance at which a transmission is detected by CCA.

    Solves: tx_power - PL(d_cs) = cca_threshold
    => d_cs = d0 * 10^((tx_power - cca_threshold - PL(d0)) / (10*n))
    """
    pl_d0 = friis_reference_loss_dB(rf.freq_ghz, d0)
    max_path_loss = rf.tx_power_dBm - rf.cca_threshold_dBm
    if max_path_loss <= pl_d0:
        return d0
    exponent = (max_path_loss - pl_d0) / (10 * rf.path_loss_exponent)
    return d0 * (10 ** exponent)


def communication_range(rf: RFConfig, min_snr_dB: float = 5.0, d0: float = 1.0) -> float:
    """Maximum distance at which the minimum MCS can be used.

    Solves: tx_power - PL(d) - noise_floor = min_snr
    => d = d0 * 10^((tx_power - noise_floor - min_snr - PL(d0)) / (10*n))
    """
    pl_d0 = friis_reference_loss_dB(rf.freq_ghz, d0)
    max_path_loss = rf.tx_power_dBm - rf.noise_floor_dBm - min_snr_dB
    if max_path_loss <= pl_d0:
        return d0
    exponent = (max_path_loss - pl_d0) / (10 * rf.path_loss_exponent)
    return d0 * (10 ** exponent)


# ─── MCS Rate Tables ─────────────────────────────────────────────
#
# Each entry: (min_snr_dB, rate_mbps_at_20MHz)
# 1 spatial stream, long guard interval
# Sources: IEEE 802.11n/ac/ax standard rate tables

MCS_TABLE_N: List[Tuple[float, float]] = [
    # 802.11n HT, 20 MHz, 1SS, 800ns GI
    (5.0,   6.5),    # MCS 0: BPSK 1/2
    (8.0,   13.0),   # MCS 1: QPSK 1/2
    (11.0,  19.5),   # MCS 2: QPSK 3/4
    (14.0,  26.0),   # MCS 3: 16-QAM 1/2
    (18.0,  39.0),   # MCS 4: 16-QAM 3/4
    (22.0,  52.0),   # MCS 5: 64-QAM 2/3
    (25.0,  58.5),   # MCS 6: 64-QAM 3/4
    (29.0,  65.0),   # MCS 7: 64-QAM 5/6
]

MCS_TABLE_AC: List[Tuple[float, float]] = [
    # 802.11ac VHT, 20 MHz, 1SS, 800ns GI
    (5.0,   6.5),    # MCS 0: BPSK 1/2
    (8.0,   13.0),   # MCS 1: QPSK 1/2
    (11.0,  19.5),   # MCS 2: QPSK 3/4
    (14.0,  26.0),   # MCS 3: 16-QAM 1/2
    (18.0,  39.0),   # MCS 4: 16-QAM 3/4
    (22.0,  52.0),   # MCS 5: 64-QAM 2/3
    (25.0,  58.5),   # MCS 6: 64-QAM 3/4
    (29.0,  65.0),   # MCS 7: 64-QAM 5/6
    (32.0,  78.0),   # MCS 8: 256-QAM 3/4
    (35.0,  86.7),   # MCS 9: 256-QAM 5/6
]

MCS_TABLE_AX: List[Tuple[float, float]] = [
    # 802.11ax HE, 20 MHz, 1SS, 3.2us GI
    (5.0,   8.6),    # MCS 0: BPSK 1/2
    (8.0,   17.2),   # MCS 1: QPSK 1/2
    (11.0,  25.8),   # MCS 2: QPSK 3/4
    (14.0,  34.4),   # MCS 3: 16-QAM 1/2
    (18.0,  51.6),   # MCS 4: 16-QAM 3/4
    (22.0,  68.8),   # MCS 5: 64-QAM 2/3
    (25.0,  77.4),   # MCS 6: 64-QAM 3/4
    (29.0,  86.0),   # MCS 7: 64-QAM 5/6
    (32.0,  103.2),  # MCS 8: 256-QAM 3/4
    (35.0,  114.7),  # MCS 9: 256-QAM 5/6
    (38.0,  129.0),  # MCS 10: 1024-QAM 3/4
    (41.0,  143.4),  # MCS 11: 1024-QAM 5/6
]

MCS_TABLES: Dict[str, List[Tuple[float, float]]] = {
    "n": MCS_TABLE_N,
    "ac": MCS_TABLE_AC,
    "ax": MCS_TABLE_AX,
}


def snr_to_rate_mbps(
    snr: float,
    wifi_standard: str = "ax",
    channel_width_mhz: int = 20,
) -> float:
    """Select PHY data rate from SNR using MCS table.

    Picks the highest MCS whose minimum SNR requirement is met.
    Scales linearly for wider channels (approximate but standard).

    Returns 0.0 if SNR is below minimum MCS threshold (link not viable).
    """
    table = MCS_TABLES.get(wifi_standard, MCS_TABLE_AX)

    selected_rate = 0.0
    for min_snr, rate in table:
        if snr >= min_snr:
            selected_rate = rate
        else:
            break

    # Scale for channel width (20 MHz is the base)
    cw_factor = channel_width_mhz / 20.0
    return selected_rate * cw_factor


def rate_mbps_to_MBps(rate_mbps: float) -> float:
    """Convert Mbps to MB/s. ncsim uses MB/s for bandwidth."""
    return rate_mbps / 8.0


# ─── Bianchi MAC Efficiency ──────────────────────────────────────

def _bianchi_efficiency_compute(n: int, W: int = 16, m: int = 6) -> float:
    """Compute Bianchi saturation throughput efficiency for n contending stations.

    Based on Bianchi (2000). Solves the coupled equations:
      tau = 2(1-2p) / ((1-2p)(W+1) + pW(1-(2p)^m))
      p = 1 - (1-tau)^(n-1)

    Returns the fraction of channel time used for successful payload
    delivery (MAC efficiency), in (0, 1].

    Args:
        n: Number of contending stations (>= 1)
        W: CWmin (minimum contention window, default 16 for 802.11)
        m: Max backoff stage (CWmax = W * 2^m, default 6 -> CWmax=1024)
    """
    if n <= 0:
        return 1.0
    if n == 1:
        return 1.0

    # Iterative fixed-point solution for tau and p
    tau = 2.0 / (W + 1)

    for _ in range(200):
        p = 1.0 - (1.0 - tau) ** (n - 1)
        p = min(max(p, 1e-12), 1.0 - 1e-12)

        denom_factor = 1.0 - 2.0 * p
        if abs(denom_factor) < 1e-12:
            # p = 0.5 edge case
            tau_new = 2.0 / (W + 1)
        else:
            numerator = 2.0 * denom_factor
            denominator = denom_factor * (W + 1) + p * W * (1.0 - (2.0 * p) ** m)
            if abs(denominator) < 1e-12:
                break
            tau_new = numerator / denominator
            tau_new = max(tau_new, 1e-12)

        if abs(tau_new - tau) < 1e-10:
            break
        tau = tau_new

    # Compute throughput efficiency
    p_idle = (1.0 - tau) ** n
    p_success = n * tau * (1.0 - tau) ** (n - 1)
    p_collision = 1.0 - p_idle - p_success

    # Slot durations (5 GHz OFDM PHY)
    T_slot_us = 9.0       # Empty slot
    T_success_us = 500.0  # Typical successful frame (DATA + SIFS + ACK)
    T_collision_us = 500.0  # Collision duration (similar, no ACK)

    E_slot_us = (p_idle * T_slot_us
                 + p_success * T_success_us
                 + p_collision * T_collision_us)

    if E_slot_us <= 0:
        return 0.01

    # Efficiency = fraction of time channel carries successful payload
    efficiency = (p_success * T_success_us) / E_slot_us
    return max(0.01, min(1.0, efficiency))


# Precomputed lookup table (lazy init)
_BIANCHI_TABLE: Optional[List[float]] = None
_BIANCHI_MAX_N = 100


def bianchi_efficiency(n: int) -> float:
    """Look up precomputed Bianchi MAC efficiency for n contending stations.

    Returns efficiency factor in (0, 1]. For n=1, returns 1.0 (no contention).
    """
    global _BIANCHI_TABLE
    if _BIANCHI_TABLE is None:
        _BIANCHI_TABLE = [1.0]  # Index 0 unused
        for i in range(1, _BIANCHI_MAX_N + 1):
            _BIANCHI_TABLE.append(_bianchi_efficiency_compute(i))

    if n <= 0:
        return 1.0
    if n >= len(_BIANCHI_TABLE):
        return _BIANCHI_TABLE[-1]
    return _BIANCHI_TABLE[n]


# ─── Conflict Graph ──────────────────────────────────────────────

@dataclass
class ConflictGraph:
    """Static conflict graph over all links in the network.

    Two links conflict if they cannot transmit simultaneously under
    the 802.11 protocol model (carrier sensing).

    Attributes:
        conflicts: Adjacency lists — link_id -> set of conflicting link_ids
        max_clique_sizes: link_id -> size of largest clique containing it
    """
    conflicts: Dict[str, Set[str]]
    max_clique_sizes: Dict[str, int]


def build_conflict_graph(
    network: Network,
    rf: RFConfig,
    shadow_fading_map: Optional[Dict[Tuple[str, str], float]] = None,
) -> ConflictGraph:
    """Build static conflict graph from network topology and RF config.

    Protocol model conflict definition:
    - Without RTS/CTS: tx(A) can sense any node of link B, OR
      tx(B) can sense any node of link A.
    - With RTS/CTS: ANY node of link A can sense ANY node of link B.

    "Can sense" means received power >= CCA threshold, i.e., within
    carrier sensing range.
    """
    cs_range = carrier_sensing_range(rf)

    # Position lookup
    node_pos: Dict[str, Position] = {
        nid: node.position for nid, node in network.nodes.items()
    }

    # Build conflict adjacency lists
    link_ids = list(network.links.keys())
    conflicts: Dict[str, Set[str]] = {lid: set() for lid in link_ids}

    for i, lid_a in enumerate(link_ids):
        link_a = network.links[lid_a]
        tx_a = link_a.from_node
        rx_a = link_a.to_node

        for j in range(i + 1, len(link_ids)):
            lid_b = link_ids[j]
            link_b = network.links[lid_b]
            tx_b = link_b.from_node
            rx_b = link_b.to_node

            has_conflict = False

            if rf.rts_cts:
                # RTS/CTS: any node of A senses any node of B
                nodes_a = [tx_a, rx_a]
                nodes_b = [tx_b, rx_b]
                for na in nodes_a:
                    for nb in nodes_b:
                        if na != nb:
                            d = euclidean_distance(node_pos[na], node_pos[nb])
                            if d <= cs_range:
                                has_conflict = True
                                break
                    if has_conflict:
                        break
            else:
                # No RTS/CTS: only transmitters sense other link's nodes
                # tx(A) senses tx(B) or rx(B)
                for nb in [tx_b, rx_b]:
                    if tx_a != nb:
                        d = euclidean_distance(node_pos[tx_a], node_pos[nb])
                        if d <= cs_range:
                            has_conflict = True
                            break
                # tx(B) senses tx(A) or rx(A)
                if not has_conflict:
                    for na in [tx_a, rx_a]:
                        if tx_b != na:
                            d = euclidean_distance(node_pos[tx_b], node_pos[na])
                            if d <= cs_range:
                                has_conflict = True
                                break

            if has_conflict:
                conflicts[lid_a].add(lid_b)
                conflicts[lid_b].add(lid_a)

    # Compute max clique sizes
    max_clique_sizes = _compute_max_clique_sizes(conflicts, link_ids)

    return ConflictGraph(
        conflicts=conflicts,
        max_clique_sizes=max_clique_sizes,
    )


def _compute_max_clique_sizes(
    conflicts: Dict[str, Set[str]],
    link_ids: List[str],
) -> Dict[str, int]:
    """Compute max clique size containing each link.

    Uses exact Bron-Kerbosch with pivoting for small networks (<=50 links).
    Falls back to greedy approximation for larger networks.
    """
    max_clique: Dict[str, int] = {lid: 1 for lid in link_ids}

    if len(link_ids) <= 50:
        # Exact: Bron-Kerbosch with pivoting
        all_cliques: List[Set[str]] = []

        def bron_kerbosch(R: Set[str], P: Set[str], X: Set[str]):
            if not P and not X:
                all_cliques.append(R.copy())
                return
            # Pivot: vertex in P|X with most connections to P
            pivot_candidates = P | X
            if not pivot_candidates:
                return
            pivot = max(pivot_candidates, key=lambda v: len(conflicts[v] & P))
            for v in list(P - conflicts[pivot]):
                neighbors = conflicts[v]
                bron_kerbosch(R | {v}, P & neighbors, X & neighbors)
                P = P - {v}
                X = X | {v}

        bron_kerbosch(set(), set(link_ids), set())

        for clique in all_cliques:
            for lid in clique:
                max_clique[lid] = max(max_clique[lid], len(clique))
    else:
        # Greedy approximation for larger networks
        for lid in link_ids:
            clique = {lid}
            candidates = sorted(
                conflicts[lid],
                key=lambda c: len(conflicts[c] & clique),
                reverse=True,
            )
            for candidate in candidates:
                if all(candidate in conflicts[c] for c in clique):
                    clique.add(candidate)
            max_clique[lid] = len(clique)

    return max_clique


# ─── Shadow Fading Map ───────────────────────────────────────────

def generate_shadow_fading_map(
    network: Network,
    sigma: float,
    seed: int,
) -> Dict[Tuple[str, str], float]:
    """Generate deterministic shadow fading values for all node pairs.

    Log-normal shadow fading: in dB domain, values are N(0, sigma).
    Symmetric: fading(A, B) = fading(B, A).

    Returns empty dict if sigma <= 0 (no fading).
    """
    if sigma <= 0:
        return {}

    rng = random.Random(seed)
    fading_map: Dict[Tuple[str, str], float] = {}

    node_ids = sorted(network.nodes.keys())
    for i, na in enumerate(node_ids):
        for j in range(i + 1, len(node_ids)):
            nb = node_ids[j]
            val = rng.gauss(0, sigma)
            fading_map[(na, nb)] = val
            fading_map[(nb, na)] = val

    return fading_map


# ─── Per-Link PHY Rate Computation ───────────────────────────────

def compute_link_phy_rates(
    network: Network,
    rf: RFConfig,
    shadow_fading_map: Optional[Dict[Tuple[str, str], float]] = None,
) -> Dict[str, float]:
    """Compute PHY data rate for each link based on SNR.

    Rate is in MB/s (ncsim units): distance -> path loss -> SNR -> MCS -> Mbps -> MB/s.

    Returns dict mapping link_id -> PHY rate in MB/s (0.0 if link out of range).
    """
    rates: Dict[str, float] = {}

    for link_id, link in network.links.items():
        from_node = network.nodes[link.from_node]
        to_node = network.nodes[link.to_node]

        dist = euclidean_distance(from_node.position, to_node.position)

        # Shadow fading
        fading = 0.0
        if shadow_fading_map:
            fading = shadow_fading_map.get((link.from_node, link.to_node), 0.0)

        # Received power and SNR
        rx_power = received_power_dBm(rf.tx_power_dBm, dist, rf, fading)
        link_snr = snr_dB(rx_power, rf.noise_floor_dBm)

        # MCS rate selection
        rate_mbps = snr_to_rate_mbps(link_snr, rf.wifi_standard, rf.channel_width_mhz)
        rates[link_id] = rate_mbps_to_MBps(rate_mbps)

    return rates

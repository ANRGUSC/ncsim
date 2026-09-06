"""Canonical wireless-mode setup shared by the CLI and experiments."""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Set, Tuple

from ncsim.models.interference import (
    InterferenceModel,
    canonicalize_wireless_mode,
    create_interference_model,
)
from ncsim.models.network import Network
from ncsim.models.wifi import (
    ConflictGraph,
    RFConfig,
    bianchi_efficiency,
    build_conflict_graph,
    carrier_sensing_range,
    compute_link_phy_rates,
    generate_shadow_fading_map,
)


@dataclass
class WirelessSetup:
    """Configured wireless model and complete provenance metadata."""

    requested_mode: str
    canonical_mode: str
    interference_model: InterferenceModel
    conflict_graph: ConflictGraph
    rf_config: RFConfig
    shadow_fading_map: Dict[Tuple[str, str], float]
    raw_phy_rates_MBps: Dict[str, float]
    solo_80211_rates_MBps: Dict[str, float]
    metadata: Dict[str, Any]


def configure_wireless(
    network: Network,
    mode: str,
    rf_config: Optional[RFConfig] = None,
    seed: int = 42,
    explicit_bandwidth_links: Optional[Set[str]] = None,
    components: str = "combined",
    outage_floor_factor: Optional[float] = None,
    hidden_terminal_model: str = "effective_rate",
) -> WirelessSetup:
    """Configure a network for a canonical wireless comparison mode.

    ``raw_phy`` uses clean PHY-derived rates. ``solo_80211`` and
    ``full_wireless`` both install the same clean single-link goodput matrix,
    obtained by multiplying the raw rate by Bianchi ``eta(1)``. Only the full
    mode adds degradation from concurrent contention and hidden terminals.

    Legacy names ``none`` and ``csma_bianchi`` are accepted and recorded, but
    all result metadata uses their canonical names as well.

    ``hidden_terminal_model="fixed_capture_overlap"`` opts into the experimental
    fixed-MCS single-hidden-interferer approximation. The default is unchanged.
    """
    if components not in {"combined", "contention-only", "hidden-only"}:
        raise ValueError(
            "components must be combined, contention-only, or hidden-only"
        )

    requested_mode = mode
    canonical_mode = canonicalize_wireless_mode(mode)
    if canonical_mode not in {"raw_phy", "solo_80211", "full_wireless"}:
        raise ValueError(f"Not a canonical wireless comparison mode: {mode}")
    if hidden_terminal_model not in {"effective_rate", "fixed_capture_overlap"}:
        raise ValueError(f"Unknown hidden-terminal model: {hidden_terminal_model}")
    if hidden_terminal_model != "effective_rate" and canonical_mode != "full_wireless":
        raise ValueError("An optional hidden-terminal model requires full_wireless")

    rf = rf_config or RFConfig()
    explicit = explicit_bandwidth_links or set()
    shadow_map = generate_shadow_fading_map(
        network, rf.shadow_fading_sigma, seed
    )
    computed_rates = compute_link_phy_rates(network, rf, shadow_map)
    raw_rates = {
        link_id: (
            network.links[link_id].bandwidth
            if link_id in explicit
            else computed_rates[link_id]
        )
        for link_id in network.links
    }
    eta_one = {
        link_id: bianchi_efficiency(1, rate * 8, rts_cts=rf.rts_cts)
        if rate > 0 else 0.0
        for link_id, rate in raw_rates.items()
    }
    solo_rates = {
        link_id: rate * eta_one[link_id] for link_id, rate in raw_rates.items()
    }
    conflict_graph = build_conflict_graph(network, rf, shadow_map)

    selected_rates = (
        raw_rates if canonical_mode == "raw_phy" else solo_rates
    )
    for link_id, rate in selected_rates.items():
        network.links[link_id].bandwidth = rate

    if canonical_mode == "full_wireless":
        model = create_interference_model(
            canonical_mode,
            conflict_graph=conflict_graph,
            rf_config=rf,
            network=network,
            shadow_fading_map=shadow_map,
            contention_enabled=components != "hidden-only",
            hidden_terminals_enabled=components != "contention-only",
            outage_floor_factor=outage_floor_factor,
            base_rates=raw_rates,
            hidden_terminal_model=hidden_terminal_model,
        )
    else:
        model = create_interference_model(canonical_mode)
        model.conflict_graph = conflict_graph
    model.raw_phy_rates_MBps = raw_rates
    model.rf_config = rf

    conflicts = sum(
        len(neighbors) for neighbors in conflict_graph.conflicts.values()
    ) // 2
    metadata = {
        "wireless_mode_requested": requested_mode,
        "wireless_mode_canonical": canonical_mode,
        "wireless_components": components,
        "outage_policy": (
            "diagnostic_floor"
            if outage_floor_factor is not None
            else "stall_until_active_set_changes"
        ),
        "outage_floor_factor": outage_floor_factor,
        "eta_one_by_link": eta_one,
        "rate_model_version": 2,
        "carrier_sensing_range_m": carrier_sensing_range(rf),
        "conflict_pairs": conflicts,
        "raw_phy_rates_MBps": raw_rates,
        "solo_80211_rates_MBps": solo_rates,
        "rf_config": {
            "tx_power_dBm": rf.tx_power_dBm,
            "freq_ghz": rf.freq_ghz,
            "path_loss_exponent": rf.path_loss_exponent,
            "noise_floor_dBm": rf.noise_floor_dBm,
            "cca_threshold_dBm": rf.cca_threshold_dBm,
            "channel_width_mhz": rf.channel_width_mhz,
            "wifi_standard": rf.wifi_standard,
            "shadow_fading_sigma": rf.shadow_fading_sigma,
            "rts_cts": rf.rts_cts,
            "capture_margin_dB": rf.capture_margin_dB,
            "interference_cutoff_dBm": rf.interference_cutoff_dBm,
        },
    }
    # Preserve existing default metadata byte-for-byte in saved experiments.
    if hidden_terminal_model != "effective_rate":
        metadata["hidden_terminal_model"] = hidden_terminal_model
        metadata["hidden_terminal_model_version"] = 1
        metadata["hidden_terminal_model_scope"] = "fixed-MCS isolated hidden pairs; ax/20MHz; no RTS/CTS"
    return WirelessSetup(
        requested_mode=requested_mode,
        canonical_mode=canonical_mode,
        interference_model=model,
        conflict_graph=conflict_graph,
        rf_config=rf,
        shadow_fading_map=shadow_map,
        raw_phy_rates_MBps=raw_rates,
        solo_80211_rates_MBps=solo_rates,
        metadata=metadata,
    )

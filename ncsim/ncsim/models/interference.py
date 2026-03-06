"""
Inter-link interference models for wireless spectrum contention.

Provides modular interference models that reduce effective link bandwidth
when nearby links are simultaneously active. This is orthogonal to
per-link fair sharing (N flows on one link each get bandwidth/N).

Combined effect: link base bandwidth B, with interference factor f,
then N flows on that link each get (B*f)/N.

Models:
  - NoInterference: factor = 1.0 always
  - ProximityInterference: simple 1/k based on midpoint distance
  - CsmaCliqueInterference: 802.11 conflict graph, static clique fair share
  - CsmaBianchiInterference: 802.11 SINR-aware + Bianchi MAC efficiency
"""

import math
from abc import ABC, abstractmethod
from typing import Dict, Optional, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ncsim.models.network import Network
    from ncsim.models.wifi import ConflictGraph, RFConfig


class InterferenceModel(ABC):
    """Abstract base class for inter-link interference models."""

    @abstractmethod
    def get_interference_factor(
        self,
        link_id: str,
        active_link_ids: Set[str],
        network: "Network"
    ) -> float:
        """Compute interference factor for a link.

        Args:
            link_id: The link to compute interference for
            active_link_ids: Set of all currently active link IDs
            network: Network topology (for position/distance info)

        Returns:
            Multiplier in (0, 1.0] to apply to the link's base bandwidth.
            1.0 means no interference.
        """
        pass

    @abstractmethod
    def get_affected_links(
        self,
        changed_link_id: str,
        active_link_ids: Set[str],
        network: "Network"
    ) -> Set[str]:
        """Return active links whose interference factor changed.

        Called when a link becomes active or inactive. Returns the set of
        other active links that need their completion times recalculated.

        Args:
            changed_link_id: The link that started or completed a transfer
            active_link_ids: Set of all currently active link IDs
            network: Network topology

        Returns:
            Set of link IDs that need recalculation.
        """
        pass


class NoInterference(InterferenceModel):
    """No inter-link interference. Always returns factor 1.0."""

    def get_interference_factor(
        self,
        link_id: str,
        active_link_ids: Set[str],
        network: "Network"
    ) -> float:
        return 1.0

    def get_affected_links(
        self,
        changed_link_id: str,
        active_link_ids: Set[str],
        network: "Network"
    ) -> Set[str]:
        return set()


class ProximityInterference(InterferenceModel):
    """Proximity-based interference: nearby active links reduce bandwidth.

    Links whose midpoints are within ``interference_radius`` of each other
    interfere. If k active links (including self) are within radius,
    each gets bandwidth reduced by factor 1/k.

    Args:
        interference_radius: Maximum distance between link midpoints
            for interference to apply.
    """

    def __init__(self, interference_radius: float = 10.0):
        self.interference_radius = interference_radius

    def _link_midpoint(self, link_id: str, network: "Network") -> tuple:
        """Compute midpoint of a link from its endpoint positions."""
        link = network.links[link_id]
        from_node = network.nodes[link.from_node]
        to_node = network.nodes[link.to_node]
        mx = (from_node.position.x + to_node.position.x) / 2
        my = (from_node.position.y + to_node.position.y) / 2
        return (mx, my)

    def _distance(self, p1: tuple, p2: tuple) -> float:
        """Euclidean distance between two points."""
        return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

    def get_interference_factor(
        self,
        link_id: str,
        active_link_ids: Set[str],
        network: "Network"
    ) -> float:
        if link_id not in active_link_ids:
            return 1.0

        mid = self._link_midpoint(link_id, network)
        k = 0
        for other_id in active_link_ids:
            other_mid = self._link_midpoint(other_id, network)
            if self._distance(mid, other_mid) <= self.interference_radius:
                k += 1

        return 1.0 / k if k > 0 else 1.0

    def get_affected_links(
        self,
        changed_link_id: str,
        active_link_ids: Set[str],
        network: "Network"
    ) -> Set[str]:
        mid = self._link_midpoint(changed_link_id, network)
        affected = set()
        for other_id in active_link_ids:
            if other_id == changed_link_id:
                continue
            other_mid = self._link_midpoint(other_id, network)
            if self._distance(mid, other_mid) <= self.interference_radius:
                affected.add(other_id)
        return affected


class CsmaCliqueInterference(InterferenceModel):
    """802.11 CSMA/CA interference: conflict graph + clique fair share.

    Variant 1 (csma_clique): static model where the clique-based sharing
    is baked into link.bandwidth at setup time (PHY_rate / max_clique_size).
    The interference factor is always 1.0.

    This model exists to provide correct get_affected_links() behavior
    and to clearly identify the interference model in use.
    """

    def __init__(self, conflict_graph: "ConflictGraph"):
        self.conflict_graph = conflict_graph

    def get_interference_factor(
        self,
        link_id: str,
        active_link_ids: Set[str],
        network: "Network"
    ) -> float:
        # Clique sharing is baked into link.bandwidth; factor stays 1.0
        return 1.0

    def get_affected_links(
        self,
        changed_link_id: str,
        active_link_ids: Set[str],
        network: "Network"
    ) -> Set[str]:
        # Static model: no dynamic recalculation needed
        return set()


class CsmaBianchiInterference(InterferenceModel):
    """802.11 CSMA/CA interference: SINR-aware rate + Bianchi MAC efficiency.

    Variant 2 (csma_bianchi, default WiFi model): dynamic model that
    correctly separates two interference mechanisms:

    1. **Contention domain (conflict graph neighbors)**: CSMA prevents
       simultaneous transmission. These links share airtime via Bianchi's
       model. Each of n contending links gets eta(n)/n of the channel.
       No SINR degradation from these links (they don't transmit together).

    2. **Hidden terminals (active links NOT in conflict graph)**: These
       may transmit simultaneously, causing SINR degradation at the
       receiver. MCS is selected based on SINR including only hidden
       terminal interference.

    The factor is computed as:
        factor = (sinr_rate / base_rate) * (eta(n) / n)

    where sinr_rate accounts for hidden terminal interference only,
    and eta(n)/n accounts for contention domain time-sharing.
    """

    def __init__(
        self,
        conflict_graph: "ConflictGraph",
        rf_config: "RFConfig",
        network: "Network",
        shadow_fading_map: Optional[Dict[Tuple[str, str], float]] = None,
    ):
        self.conflict_graph = conflict_graph
        self.rf = rf_config
        self.network_ref = network
        self.shadow_fading_map = shadow_fading_map or {}

        # Cache base SNR-only PHY rates (what link.bandwidth is set to)
        from ncsim.models.wifi import compute_link_phy_rates
        self._base_rates = compute_link_phy_rates(
            network, rf_config, shadow_fading_map
        )

    def get_interference_factor(
        self,
        link_id: str,
        active_link_ids: Set[str],
        network: "Network"
    ) -> float:
        from ncsim.models.wifi import (
            euclidean_distance, received_power_dBm, sinr_dB,
            snr_to_rate_mbps, rate_mbps_to_MBps, bianchi_efficiency,
        )

        if link_id not in active_link_ids:
            return 1.0

        base_rate = self._base_rates.get(link_id, 0.0)
        if base_rate <= 0:
            return 0.01  # Link not viable

        link = network.links[link_id]
        rx_node = network.nodes[link.to_node]
        tx_node = network.nodes[link.from_node]
        conflict_neighbors = self.conflict_graph.conflicts.get(link_id, set())

        # Separate active links into contention domain vs hidden terminals
        contending_active = active_link_ids & conflict_neighbors
        hidden_active = (active_link_ids - conflict_neighbors) - {link_id}

        # SINR degradation from hidden terminals ONLY
        # (contending links don't transmit simultaneously under CSMA)
        sinr_factor = 1.0
        if hidden_active:
            dist = euclidean_distance(tx_node.position, rx_node.position)
            fading = self.shadow_fading_map.get(
                (link.from_node, link.to_node), 0.0
            )
            desired_power = received_power_dBm(
                self.rf.tx_power_dBm, dist, self.rf, fading
            )

            interference_powers = []
            for interferer_id in hidden_active:
                interferer = network.links[interferer_id]
                interferer_tx = network.nodes[interferer.from_node]
                i_dist = euclidean_distance(
                    interferer_tx.position, rx_node.position
                )
                i_fading = self.shadow_fading_map.get(
                    (interferer.from_node, link.to_node), 0.0
                )
                i_power = received_power_dBm(
                    self.rf.tx_power_dBm, i_dist, self.rf, i_fading
                )
                interference_powers.append(i_power)

            link_sinr = sinr_dB(
                desired_power, interference_powers, self.rf.noise_floor_dBm
            )
            sinr_rate_mbps = snr_to_rate_mbps(
                link_sinr, self.rf.wifi_standard, self.rf.channel_width_mhz
            )
            sinr_rate_MBps = rate_mbps_to_MBps(sinr_rate_mbps)

            if sinr_rate_MBps <= 0:
                return 0.01  # Hidden terminal destroyed the link
            sinr_factor = sinr_rate_MBps / base_rate

        # Bianchi contention domain sharing
        # n contending stations share the channel: each gets eta(n)/n
        n_contending = 1 + len(contending_active)
        eta = bianchi_efficiency(n_contending)
        contention_factor = eta / n_contending

        factor = sinr_factor * contention_factor
        return max(0.01, min(1.0, factor))

    def get_affected_links(
        self,
        changed_link_id: str,
        active_link_ids: Set[str],
        network: "Network"
    ) -> Set[str]:
        # All other active links need recalculation — both conflict-graph
        # neighbors (Bianchi contention) and hidden terminals (SINR).
        # Previously only conflict neighbors were returned, which meant
        # hidden terminals never triggered recalculation of already-active
        # transfers, producing asymmetric rates in symmetric topologies.
        return active_link_ids - {changed_link_id}


def create_interference_model(model_type: str, **kwargs) -> InterferenceModel:
    """Factory function to create interference models.

    Args:
        model_type: "none", "proximity", "csma_clique", or "csma_bianchi"
        **kwargs: Model-specific parameters:
            - interference_radius: for "proximity"
            - conflict_graph: for "csma_clique" and "csma_bianchi"
            - rf_config: for "csma_bianchi"
            - network: for "csma_bianchi"
            - shadow_fading_map: for "csma_bianchi" (optional)

    Returns:
        InterferenceModel instance

    Raises:
        ValueError: If model_type is unknown
    """
    if model_type == "none":
        return NoInterference()
    elif model_type == "proximity":
        radius = kwargs.get("interference_radius", 10.0)
        return ProximityInterference(interference_radius=radius)
    elif model_type == "csma_clique":
        return CsmaCliqueInterference(
            conflict_graph=kwargs["conflict_graph"],
        )
    elif model_type == "csma_bianchi":
        return CsmaBianchiInterference(
            conflict_graph=kwargs["conflict_graph"],
            rf_config=kwargs["rf_config"],
            network=kwargs["network"],
            shadow_fading_map=kwargs.get("shadow_fading_map"),
        )
    else:
        raise ValueError(f"Unknown interference model: {model_type}")

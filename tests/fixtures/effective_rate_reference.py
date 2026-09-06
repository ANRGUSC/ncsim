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


WIRELESS_MODE_ALIASES = {
    "none": "raw_phy",
    "raw_phy": "raw_phy",
    "solo_80211": "solo_80211",
    "csma_bianchi": "full_wireless",
    "full_wireless": "full_wireless",
}


def canonicalize_wireless_mode(model_type: str) -> str:
    """Return the canonical name for a wireless comparison mode."""
    return WIRELESS_MODE_ALIASES.get(model_type, model_type)


class WirelessOutageError(RuntimeError):
    """Raised when active interference makes a link undecodable."""

    def __init__(self, link_id: str, sinr_dB: float, minimum_sinr_dB: float):
        self.link_id = link_id
        self.sinr_dB = sinr_dB
        self.minimum_sinr_dB = minimum_sinr_dB
        super().__init__(
            f"link {link_id} is in wireless outage: SINR={sinr_dB:.3f} dB, "
            f"minimum={minimum_sinr_dB:.3f} dB"
        )


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

    canonical_mode = "raw_phy"

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


class Solo80211Interference(InterferenceModel):
    """No concurrent-link degradation on a MAC-normalized link matrix."""

    canonical_mode = "solo_80211"

    def get_interference_factor(
        self,
        link_id: str,
        active_link_ids: Set[str],
        network: "Network"
    ) -> float:
        if link_id not in active_link_ids:
            return 1.0
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
    """Local flow-level approximation of 802.11 wireless goodput.

    The clean rate is selected from SNR. Active conflict-graph neighbors
    reduce airtime through ``eta(n) / n``. Active non-conflicting transmitters
    in the local interference neighborhood are combined in linear power, and
    the resulting SINR selects an effective MCS no faster than the clean MCS.
    The effective-MCS step approximates inter-frame rate adaptation for
    sustained bulk transfers.

    Bianchi's saturated homogeneous-domain model is applied independently to
    each local neighborhood. For an undirected conflict graph, shares bounded
    by 1/(degree+1) are fractionally schedulable; overlap alone does not imply
    infeasibility. Local estimates can nevertheless misestimate DCF throughput
    and fairness, and the graph can omit physical interference constraints.
    """

    canonical_mode = "full_wireless"

    def __init__(
        self,
        conflict_graph: "ConflictGraph",
        rf_config: "RFConfig",
        network: "Network",
        shadow_fading_map: Optional[Dict[Tuple[str, str], float]] = None,
        contention_enabled: bool = True,
        hidden_terminals_enabled: bool = True,
        outage_floor_factor: Optional[float] = None,
        base_rates: Optional[Dict[str, float]] = None,
    ):
        self.conflict_graph = conflict_graph
        self.rf = rf_config
        self.network_ref = network
        self.shadow_fading_map = shadow_fading_map or {}
        self.contention_enabled = contention_enabled
        self.hidden_terminals_enabled = hidden_terminals_enabled
        if outage_floor_factor is not None and not (0.0 < outage_floor_factor <= 1.0):
            raise ValueError("outage_floor_factor must be in (0, 1]")
        self.outage_floor_factor = outage_floor_factor

        from ncsim.models.wifi import (
            compute_link_phy_rates, euclidean_distance, received_power_dBm,
        )
        self._base_rates = dict(base_rates) if base_rates is not None else (
            compute_link_phy_rates(network, rf_config, self.shadow_fading_map)
        )

        # Directed dependency map used for local causal recalculation.
        self._hidden_neighbors: Dict[str, Set[str]] = {
            link_id: set() for link_id in network.links
        }
        for target_id, target in network.links.items():
            target_rx = network.nodes[target.to_node]
            conflicts = self.conflict_graph.conflicts.get(target_id, set())
            for interferer_id, interferer in network.links.items():
                if interferer_id == target_id or interferer_id in conflicts:
                    continue
                interferer_tx = network.nodes[interferer.from_node]
                distance = euclidean_distance(
                    interferer_tx.position, target_rx.position
                )
                fading = self.shadow_fading_map.get(
                    (interferer.from_node, target.to_node), 0.0
                )
                power = received_power_dBm(
                    self.rf.tx_power_dBm, distance, self.rf, fading
                )
                if power >= self.rf.interference_cutoff_dBm:
                    self._hidden_neighbors[target_id].add(interferer_id)

    def _outage_factor(
        self, link_id: str, link_sinr: float, minimum_sinr: float
    ) -> float:
        if self.outage_floor_factor is not None:
            return self.outage_floor_factor
        return 0.0

    def get_interference_factor(
        self,
        link_id: str,
        active_link_ids: Set[str],
        network: "Network"
    ) -> float:
        from ncsim.models.wifi import (
            MCS_TABLES, bianchi_efficiency, euclidean_distance,
            received_power_dBm, sinr_dB, sinr_to_effective_rate_mbps,
        )

        if link_id not in active_link_ids:
            return 1.0

        table = MCS_TABLES.get(self.rf.wifi_standard, MCS_TABLES["ax"])
        minimum_sinr = table[0][0] - self.rf.capture_margin_dB
        base_rate = self._base_rates.get(link_id, 0.0)
        if base_rate <= 0.0:
            return self._outage_factor(link_id, float("-inf"), minimum_sinr)

        link = network.links[link_id]
        receiver = network.nodes[link.to_node]
        transmitter = network.nodes[link.from_node]
        conflicts = self.conflict_graph.conflicts.get(link_id, set())
        contending_active = active_link_ids & conflicts
        hidden_active = active_link_ids & self._hidden_neighbors.get(link_id, set())

        hidden_factor = 1.0
        effective_rate = base_rate
        if self.hidden_terminals_enabled and hidden_active:
            distance = euclidean_distance(
                transmitter.position, receiver.position
            )
            fading = self.shadow_fading_map.get(
                (link.from_node, link.to_node), 0.0
            )
            desired_power = received_power_dBm(
                self.rf.tx_power_dBm, distance, self.rf, fading
            )
            interference_powers = []
            # Stable summation order prevents process-specific hash ordering
            # from moving a borderline SINR across an MCS threshold.
            for interferer_id in sorted(hidden_active):
                interferer = network.links[interferer_id]
                interferer_tx = network.nodes[interferer.from_node]
                interferer_distance = euclidean_distance(
                    interferer_tx.position, receiver.position
                )
                interferer_fading = self.shadow_fading_map.get(
                    (interferer.from_node, link.to_node), 0.0
                )
                interference_powers.append(received_power_dBm(
                    self.rf.tx_power_dBm,
                    interferer_distance,
                    self.rf,
                    interferer_fading,
                ))

            link_sinr = sinr_dB(
                desired_power, interference_powers, self.rf.noise_floor_dBm
            )
            effective_rate_mbps = sinr_to_effective_rate_mbps(
                link_sinr,
                wifi_standard=self.rf.wifi_standard,
                channel_width_mhz=self.rf.channel_width_mhz,
                capture_margin_dB=self.rf.capture_margin_dB,
            )
            effective_rate = min(base_rate, effective_rate_mbps / 8.0)
            if effective_rate <= 0.0:
                return self._outage_factor(
                    link_id, link_sinr, minimum_sinr
                )
            else:
                hidden_factor = effective_rate / base_rate

        n_contending = 1 + len(contending_active)
        if not self.contention_enabled:
            n_contending = 1
        solo_goodput = base_rate * bianchi_efficiency(
            1, base_rate * 8, rts_cts=self.rf.rts_cts
        )
        goodput = effective_rate * bianchi_efficiency(
            n_contending, effective_rate * 8, rts_cts=self.rf.rts_cts
        ) / n_contending
        return goodput / solo_goodput

    def get_affected_links(
        self,
        changed_link_id: str,
        active_link_ids: Set[str],
        network: "Network"
    ) -> Set[str]:
        affected: Set[str] = set()
        for target_id in sorted(active_link_ids - {changed_link_id}):
            conflicts = self.conflict_graph.conflicts.get(target_id, set())
            hidden = self._hidden_neighbors.get(target_id, set())
            if (
                self.contention_enabled and changed_link_id in conflicts
            ) or (
                self.hidden_terminals_enabled and changed_link_id in hidden
            ):
                affected.add(target_id)
        return affected


def create_interference_model(model_type: str, **kwargs) -> InterferenceModel:
    """Factory function to create interference models.

    Args:
        model_type: Canonical ``raw_phy``, ``solo_80211``, or
            ``full_wireless`` mode, or a supported legacy model name.
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
    canonical = canonicalize_wireless_mode(model_type)
    if canonical == "raw_phy":
        return NoInterference()
    elif canonical == "solo_80211":
        return Solo80211Interference()
    elif model_type == "proximity":
        radius = kwargs.get("interference_radius", 10.0)
        return ProximityInterference(interference_radius=radius)
    elif model_type == "csma_clique":
        return CsmaCliqueInterference(
            conflict_graph=kwargs["conflict_graph"],
        )
    elif canonical == "full_wireless":
        return CsmaBianchiInterference(
            conflict_graph=kwargs["conflict_graph"],
            rf_config=kwargs["rf_config"],
            network=kwargs["network"],
            shadow_fading_map=kwargs.get("shadow_fading_map"),
            contention_enabled=kwargs.get("contention_enabled", True),
            hidden_terminals_enabled=kwargs.get("hidden_terminals_enabled", True),
            outage_floor_factor=kwargs.get("outage_floor_factor"),
            base_rates=kwargs.get("base_rates"),
        )
    else:
        raise ValueError(f"Unknown interference model: {model_type}")

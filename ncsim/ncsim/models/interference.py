"""
Inter-link interference models for wireless spectrum contention.

Provides modular interference models that reduce effective link bandwidth
when nearby links are simultaneously active. This is orthogonal to
per-link fair sharing (N flows on one link each get bandwidth/N).

Combined effect: link base bandwidth B, with k nearby interfering active
links -> B/k, then N flows on that link each get (B/k)/N.
"""

import math
from abc import ABC, abstractmethod
from typing import Set, TYPE_CHECKING

if TYPE_CHECKING:
    from ncsim.models.network import Network


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


def create_interference_model(model_type: str, **kwargs) -> InterferenceModel:
    """Factory function to create interference models.

    Args:
        model_type: "none" or "proximity"
        **kwargs: Model-specific parameters (e.g., interference_radius)

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
    else:
        raise ValueError(f"Unknown interference model: {model_type}")

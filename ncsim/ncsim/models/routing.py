"""
Network routing model definitions.

Defines how data is routed between nodes.
Phase 2: Direct links only (no multi-hop routing).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ncsim.core.execution_engine import NetworkState
    from ncsim.models.network import Network


class RoutingModel(ABC):
    """Abstract base class for network path selection.

    Phase 2: DirectLinkRouting requires explicit direct links.
    Future: ShortestPathRouting, MultiPathRouting, etc.
    """

    @abstractmethod
    def get_path(
        self,
        src_node: str,
        dst_node: str,
        network: "Network",
        network_state: Optional["NetworkState"] = None
    ) -> Optional[List[str]]:
        """Find path from source to destination.

        Args:
            src_node: Source node ID
            dst_node: Destination node ID
            network: Network topology
            network_state: Optional current network state

        Returns:
            List of link IDs forming the path, or None if no path exists
        """
        pass


class DirectLinkRouting(RoutingModel):
    """Phase 2 implementation: Direct link or fail.

    Only allows transfers on explicitly declared links.
    No multi-hop routing - if no direct link exists, transfer fails.
    """

    def get_path(
        self,
        src_node: str,
        dst_node: str,
        network: "Network",
        network_state: Optional["NetworkState"] = None
    ) -> Optional[List[str]]:
        """Return direct link if it exists, None otherwise.

        Args:
            src_node: Source node ID
            dst_node: Destination node ID
            network: Network topology
            network_state: Unused in Phase 2

        Returns:
            List with single link ID, or None if no direct link
        """
        # Same node = local transfer (no network needed)
        if src_node == dst_node:
            return []  # Empty path = local

        # Check for direct link
        link = network.get_link_between(src_node, dst_node)
        if link:
            return [link.id]

        # No direct link = transfer not possible
        return None


class ShortestPathRouting(RoutingModel):
    """Future implementation: Dijkstra-based shortest path routing.

    Not implemented in Phase 2 - placeholder for future.
    """

    def get_path(
        self,
        src_node: str,
        dst_node: str,
        network: "Network",
        network_state: Optional["NetworkState"] = None
    ) -> Optional[List[str]]:
        """Not implemented in Phase 2."""
        raise NotImplementedError("Multi-hop routing not available in Phase 2")

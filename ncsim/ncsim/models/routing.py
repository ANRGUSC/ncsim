"""
Network routing model definitions.

Defines how data is routed between nodes.
Supports direct links (Phase 2) and multi-hop widest-path routing.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING
import heapq

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


class WidestPathRouting(RoutingModel):
    """Multi-hop routing using widest-path (max-min bandwidth) algorithm.

    Finds paths that maximize the bottleneck bandwidth (minimum bandwidth
    along the path). Uses modified Dijkstra with max-min semantics.

    For transfers, the bottleneck bandwidth determines transfer rate,
    and latencies are summed across all links (store-and-forward model).
    """

    def __init__(self):
        """Initialize widest-path routing with caches."""
        self._path_cache: Dict[Tuple[str, str], Optional[List[str]]] = {}
        self._bandwidth_cache: Dict[Tuple[str, str], float] = {}

    def get_path(
        self,
        src_node: str,
        dst_node: str,
        network: "Network",
        network_state: Optional["NetworkState"] = None
    ) -> Optional[List[str]]:
        """Find widest path from source to destination.

        Args:
            src_node: Source node ID
            dst_node: Destination node ID
            network: Network topology
            network_state: Unused (for interface compatibility)

        Returns:
            List of link IDs forming the widest path, or None if no path exists.
            Empty list for same-node (local) transfers.
        """
        # Same node = local transfer
        if src_node == dst_node:
            return []

        # Check cache
        cache_key = (src_node, dst_node)
        if cache_key in self._path_cache:
            return self._path_cache[cache_key]

        # Compute path
        path = self._compute_widest_path(src_node, dst_node, network)
        self._path_cache[cache_key] = path

        return path

    def get_path_bandwidth(self, src_node: str, dst_node: str, network: "Network") -> float:
        """Get the bottleneck bandwidth of the widest path.

        Args:
            src_node: Source node ID
            dst_node: Destination node ID
            network: Network topology

        Returns:
            Bottleneck bandwidth (min bandwidth along path), or 0.0 if no path exists.
            Returns infinity for same-node transfers (local).
        """
        # Same node = local transfer (effectively infinite bandwidth)
        if src_node == dst_node:
            return float('inf')

        # Check cache
        cache_key = (src_node, dst_node)
        if cache_key in self._bandwidth_cache:
            return self._bandwidth_cache[cache_key]

        # Compute path and bandwidth
        path = self.get_path(src_node, dst_node, network)
        if path is None or len(path) == 0:
            bandwidth = 0.0
        else:
            bandwidth = min(network.links[lid].bandwidth for lid in path)

        self._bandwidth_cache[cache_key] = bandwidth
        return bandwidth

    def _compute_widest_path(
        self,
        src: str,
        dst: str,
        network: "Network"
    ) -> Optional[List[str]]:
        """Compute widest path using modified Dijkstra algorithm.

        Uses max-heap to find path that maximizes minimum bandwidth.

        Args:
            src: Source node ID
            dst: Destination node ID
            network: Network topology

        Returns:
            List of link IDs forming the path, or None if no path exists.
        """
        # bandwidth[node] = best bottleneck bandwidth to reach this node
        bandwidth: Dict[str, float] = {node_id: 0.0 for node_id in network.nodes}
        bandwidth[src] = float('inf')

        # predecessor[node] = (prev_node, link_id) for path reconstruction
        predecessor: Dict[str, Optional[Tuple[str, str]]] = {
            node_id: None for node_id in network.nodes
        }

        # Max-heap: (-bandwidth, node_id) - negated for max-heap behavior
        # We want to process highest bandwidth paths first
        heap: List[Tuple[float, str]] = [(-float('inf'), src)]
        visited: set = set()

        while heap:
            neg_bw, current = heapq.heappop(heap)
            current_bw = -neg_bw

            if current in visited:
                continue
            visited.add(current)

            # Found destination
            if current == dst:
                break

            # Skip if we've already found a better path to this node
            if current_bw < bandwidth[current]:
                continue

            # Explore outgoing links
            for link in network.get_links_from(current):
                neighbor = link.to_node
                if neighbor in visited:
                    continue

                # Bottleneck bandwidth through this link
                new_bw = min(current_bw, link.bandwidth)

                # Update if this gives better bandwidth
                if new_bw > bandwidth[neighbor]:
                    bandwidth[neighbor] = new_bw
                    predecessor[neighbor] = (current, link.id)
                    heapq.heappush(heap, (-new_bw, neighbor))

        # Reconstruct path
        if predecessor[dst] is None:
            return None  # No path exists

        path: List[str] = []
        current = dst
        while predecessor[current] is not None:
            prev_node, link_id = predecessor[current]
            path.append(link_id)
            current = prev_node

        path.reverse()
        return path

    def clear_cache(self) -> None:
        """Clear the path and bandwidth caches.

        Call this if the network topology changes.
        """
        self._path_cache.clear()
        self._bandwidth_cache.clear()

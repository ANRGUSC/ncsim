"""
Network routing model definitions.

Defines how data is routed between nodes.
Supports direct links (Phase 2), multi-hop widest-path routing,
shortest-path (minimum latency) routing, and interference-aware routing.
"""

import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING
import heapq

if TYPE_CHECKING:
    from ncsim.core.execution_engine import NetworkState
    from ncsim.models.dag import DAG
    from ncsim.models.interference import InterferenceModel
    from ncsim.models.network import Network
    from ncsim.scheduler.base import PlacementPlan

logger = logging.getLogger(__name__)


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


class ShortestPathRouting(RoutingModel):
    """Multi-hop routing using shortest-path (minimum total latency) algorithm.

    Finds paths that minimize the sum of link latencies along the path.
    Uses standard Dijkstra's algorithm. If all latencies are equal, this
    degenerates to minimum hop count.

    For transfers, latencies are summed across all links (store-and-forward model),
    and the bottleneck bandwidth determines transfer rate.
    """

    def __init__(self):
        """Initialize shortest-path routing with caches."""
        self._path_cache: Dict[Tuple[str, str], Optional[List[str]]] = {}
        self._bandwidth_cache: Dict[Tuple[str, str], float] = {}

    def get_path(
        self,
        src_node: str,
        dst_node: str,
        network: "Network",
        network_state: Optional["NetworkState"] = None
    ) -> Optional[List[str]]:
        """Find shortest path (minimum total latency) from source to destination.

        Args:
            src_node: Source node ID
            dst_node: Destination node ID
            network: Network topology
            network_state: Unused (for interface compatibility)

        Returns:
            List of link IDs forming the shortest path, or None if no path exists.
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
        path = self._compute_shortest_path(src_node, dst_node, network)
        self._path_cache[cache_key] = path

        return path

    def get_path_bandwidth(self, src_node: str, dst_node: str, network: "Network") -> float:
        """Get the bottleneck bandwidth of the shortest path.

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

    def _compute_shortest_path(
        self,
        src: str,
        dst: str,
        network: "Network"
    ) -> Optional[List[str]]:
        """Compute shortest path using Dijkstra's algorithm on link latencies.

        Args:
            src: Source node ID
            dst: Destination node ID
            network: Network topology

        Returns:
            List of link IDs forming the path, or None if no path exists.
        """
        # dist[node] = minimum total latency to reach this node
        dist: Dict[str, float] = {node_id: float('inf') for node_id in network.nodes}
        dist[src] = 0.0

        # predecessor[node] = (prev_node, link_id) for path reconstruction
        predecessor: Dict[str, Optional[Tuple[str, str]]] = {
            node_id: None for node_id in network.nodes
        }

        # Min-heap: (total_latency, node_id)
        heap: List[Tuple[float, str]] = [(0.0, src)]
        visited: set = set()

        while heap:
            current_dist, current = heapq.heappop(heap)

            if current in visited:
                continue
            visited.add(current)

            # Found destination
            if current == dst:
                break

            # Explore outgoing links
            for link in network.get_links_from(current):
                neighbor = link.to_node
                if neighbor in visited:
                    continue

                # Total latency through this link
                new_dist = current_dist + link.latency

                # Update if this gives lower latency
                if new_dist < dist[neighbor]:
                    dist[neighbor] = new_dist
                    predecessor[neighbor] = (current, link.id)
                    heapq.heappush(heap, (new_dist, neighbor))

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


def _build_adjacency(
    network: "Network",
) -> Dict[str, List[Tuple[str, str]]]:
    """Build adjacency list: node -> [(neighbor, link_id), ...].

    Shared helper for interference-aware routing variants.
    """
    adj: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    for link in network.links.values():
        adj[link.from_node].append((link.to_node, link.id))
    return adj


def _enumerate_candidate_paths(
    src: str,
    dst: str,
    adj: Dict[str, List[Tuple[str, str]]],
    network: "Network",
    hop_cutoff: int = 4,
    max_candidates: int = 20,
) -> List[List[str]]:
    """Enumerate simple paths from src to dst up to hop_cutoff.

    Uses iterative DFS. Returns at most max_candidates paths.
    Shared helper for interference-aware routing variants.
    """
    candidates: List[List[str]] = []
    # Stack: (current_node, path_links, visited_nodes)
    stack: List[Tuple[str, List[str], Set[str]]] = [
        (src, [], {src})
    ]

    while stack and len(candidates) < max_candidates:
        current, path, visited = stack.pop()

        if current == dst and path:
            candidates.append(path)
            continue

        if len(path) >= hop_cutoff:
            continue

        for neighbor, link_id in adj.get(current, []):
            if neighbor not in visited:
                stack.append((
                    neighbor,
                    path + [link_id],
                    visited | {neighbor}
                ))

    return candidates


@dataclass
class _RoutedFlow:
    """Internal record of a flow that has been assigned a route."""
    from_task: str
    to_task: str
    src_node: str
    dst_node: str
    data_size: float
    path: List[str]
    est_start: float
    est_end: float


class InterferenceAwareRouting(RoutingModel):
    """Interference-aware multi-hop routing.

    Two-stage approach:
    1. HEFT decides task placement (task -> node)
    2. This router greedily assigns routes for all inter-node flows,
       maximizing system-wide throughput rather than individual flow bandwidth.

    Before plan_routes() is called, delegates to WidestPathRouting for
    HEFT bandwidth estimation. After planning, get_path() returns
    pre-computed routes.
    """

    def __init__(
        self,
        interference_model: "InterferenceModel",
        hop_cutoff: int = 4,
        max_candidates: int = 20
    ):
        self.interference_model = interference_model
        self.hop_cutoff = hop_cutoff
        self.max_candidates = max_candidates
        self._planned_routes: Dict[Tuple[str, str], List[str]] = {}
        self._delegate = WidestPathRouting()
        self._routes_planned = False

    def get_path(
        self,
        src_node: str,
        dst_node: str,
        network: "Network",
        network_state: Optional["NetworkState"] = None
    ) -> Optional[List[str]]:
        """Return pre-computed route or delegate to widest-path.

        Before plan_routes() is called, delegates to WidestPathRouting.
        After planning, returns the pre-computed interference-aware route.
        """
        if src_node == dst_node:
            return []

        if self._routes_planned:
            route = self._planned_routes.get((src_node, dst_node))
            if route is not None:
                return route
            # Fall back to delegate for flows not in the plan
            return self._delegate.get_path(src_node, dst_node, network)

        return self._delegate.get_path(src_node, dst_node, network)

    def get_path_bandwidth(
        self, src_node: str, dst_node: str, network: "Network"
    ) -> float:
        """Delegate bandwidth calculation to WidestPathRouting for HEFT."""
        return self._delegate.get_path_bandwidth(src_node, dst_node, network)

    def plan_routes(
        self,
        dag: "DAG",
        placement_plan: "PlacementPlan",
        network: "Network",
        schedule_timing: Optional[Dict[str, Tuple[float, float]]] = None
    ) -> None:
        """Pre-compute interference-aware routes for all inter-node flows.

        Called after HEFT placement, before execution begins.

        Args:
            dag: The DAG being executed
            placement_plan: HEFT task-to-node assignments
            network: Network topology
            schedule_timing: Optional HEFT timing {task_id: (start, end)}
        """
        flows = self._extract_flows(dag, placement_plan)
        if not flows:
            self._routes_planned = True
            return

        # Estimate time windows for concurrency detection
        windows = self._estimate_flow_windows(
            flows, dag, placement_plan, network, schedule_timing
        )

        # Build adjacency for path enumeration
        adj = _build_adjacency(network)

        # Sort flows by estimated start time (greedy order)
        flows.sort(key=lambda f: windows.get(
            (f["from_task"], f["to_task"]), (0.0, 0.0)
        )[0])

        routed: List[_RoutedFlow] = []

        for flow in flows:
            src = flow["src_node"]
            dst = flow["dst_node"]
            key = (flow["from_task"], flow["to_task"])
            window = windows.get(key, (0.0, float('inf')))

            # Check if we already have a route for this node pair
            if (src, dst) in self._planned_routes:
                path = self._planned_routes[(src, dst)]
                routed.append(_RoutedFlow(
                    from_task=flow["from_task"],
                    to_task=flow["to_task"],
                    src_node=src, dst_node=dst,
                    data_size=flow["data_size"],
                    path=path,
                    est_start=window[0], est_end=window[1]
                ))
                continue

            # Enumerate candidate paths
            candidates = _enumerate_candidate_paths(
                src, dst, adj, network, self.hop_cutoff, self.max_candidates
            )

            if not candidates:
                # No path found; fall back to delegate
                fallback = self._delegate.get_path(src, dst, network)
                if fallback:
                    candidates = [fallback]
                else:
                    logger.warning(
                        f"InterferenceAwareRouting: no path from {src} to {dst}"
                    )
                    continue

            # Find concurrent flows
            concurrent = self._find_concurrent_flows(window, routed)

            # Score each candidate
            best_path = candidates[0]
            best_score = -1.0

            for candidate in candidates:
                score = self._score_candidate(
                    flow, candidate, concurrent, network
                )
                if score > best_score:
                    best_score = score
                    best_path = candidate

            self._planned_routes[(src, dst)] = best_path
            routed.append(_RoutedFlow(
                from_task=flow["from_task"],
                to_task=flow["to_task"],
                src_node=src, dst_node=dst,
                data_size=flow["data_size"],
                path=best_path,
                est_start=window[0], est_end=window[1]
            ))

            logger.debug(
                f"InterferenceAwareRouting: {src}->{dst} via {best_path} "
                f"(score={best_score:.2f})"
            )

        self._routes_planned = True
        logger.info(
            f"InterferenceAwareRouting: planned {len(self._planned_routes)} routes"
        )

    def _extract_flows(
        self, dag: "DAG", plan: "PlacementPlan"
    ) -> List[Dict]:
        """Extract inter-node flows from DAG edges."""
        flows = []
        for edge in dag.edges:
            src_node = plan.get_node_for_task(edge.from_task)
            dst_node = plan.get_node_for_task(edge.to_task)
            if src_node and dst_node and src_node != dst_node:
                flows.append({
                    "from_task": edge.from_task,
                    "to_task": edge.to_task,
                    "src_node": src_node,
                    "dst_node": dst_node,
                    "data_size": edge.data_size,
                })
        return flows

    def _estimate_flow_windows(
        self,
        flows: List[Dict],
        dag: "DAG",
        plan: "PlacementPlan",
        network: "Network",
        schedule_timing: Optional[Dict[str, Tuple[float, float]]]
    ) -> Dict[Tuple[str, str], Tuple[float, float]]:
        """Estimate transfer time windows for concurrency detection.

        Uses HEFT timing if available, otherwise rough estimates from
        task compute costs and bandwidth.
        """
        windows: Dict[Tuple[str, str], Tuple[float, float]] = {}

        for flow in flows:
            key = (flow["from_task"], flow["to_task"])

            if schedule_timing and flow["from_task"] in schedule_timing:
                # Use HEFT's estimate: transfer starts after source task ends
                _, src_end = schedule_timing[flow["from_task"]]
                # Estimate transfer duration from widest-path bandwidth
                bw = self._delegate.get_path_bandwidth(
                    flow["src_node"], flow["dst_node"], network
                )
                if bw > 0 and bw != float('inf'):
                    est_duration = flow["data_size"] / bw
                else:
                    est_duration = flow["data_size"] / 1.0  # fallback
                windows[key] = (src_end, src_end + est_duration)
            else:
                # Rough estimate: source task compute time
                src_task = dag.get_task(flow["from_task"])
                src_node_obj = network.get_node(flow["src_node"])
                if src_task and src_node_obj:
                    start = src_task.compute_cost / src_node_obj.compute_capacity
                else:
                    start = 0.0
                bw = self._delegate.get_path_bandwidth(
                    flow["src_node"], flow["dst_node"], network
                )
                if bw > 0 and bw != float('inf'):
                    est_duration = flow["data_size"] / bw
                else:
                    est_duration = flow["data_size"] / 1.0
                windows[key] = (start, start + est_duration)

        return windows

    def _find_concurrent_flows(
        self,
        window: Tuple[float, float],
        routed: List[_RoutedFlow]
    ) -> List[_RoutedFlow]:
        """Find previously-routed flows with overlapping time windows."""
        concurrent = []
        for rf in routed:
            # Check overlap: windows intersect if start < other_end and end > other_start
            if window[0] < rf.est_end and window[1] > rf.est_start:
                concurrent.append(rf)
        return concurrent

    def _score_candidate(
        self,
        flow: Dict,
        candidate_path: List[str],
        concurrent: List[_RoutedFlow],
        network: "Network"
    ) -> float:
        """Score a candidate path by total system throughput.

        Computes the sum of effective bandwidths across all concurrent
        flows (including this candidate), accounting for interference
        and per-link fair sharing. Higher is better.
        """
        # Build link usage map
        link_usage: Dict[str, int] = defaultdict(int)
        all_active_links: Set[str] = set()

        for cf in concurrent:
            for lid in cf.path:
                link_usage[lid] += 1
                all_active_links.add(lid)

        for lid in candidate_path:
            link_usage[lid] += 1
            all_active_links.add(lid)

        # Sum effective bandwidth across ALL flows
        total_throughput = 0.0

        # Score concurrent flows
        for cf in concurrent:
            eff_bw = float('inf')
            for lid in cf.path:
                factor = self.interference_model.get_interference_factor(
                    lid, all_active_links, network
                )
                link_bw = network.links[lid].bandwidth * factor / link_usage[lid]
                eff_bw = min(eff_bw, link_bw)
            total_throughput += eff_bw

        # Score candidate flow
        eff_bw = float('inf')
        for lid in candidate_path:
            factor = self.interference_model.get_interference_factor(
                lid, all_active_links, network
            )
            link_bw = network.links[lid].bandwidth * factor / link_usage[lid]
            eff_bw = min(eff_bw, link_bw)
        total_throughput += eff_bw

        return total_throughput


class DynamicInterferenceAwareRouting(RoutingModel):
    """Dynamic interference-aware multi-hop routing (GSD).

    Computes routes at transfer start time using actual current link state
    instead of estimated concurrency windows. At each transfer_start event,
    the execution engine passes the real-time network state (active links,
    per-link transfer counts), and GSD picks the path that maximizes this
    flow's bottleneck bandwidth given actual interference.

    Without network_state (e.g. during HEFT scheduling), delegates to
    WidestPathRouting for bandwidth estimation.
    """

    def __init__(
        self,
        interference_model: "InterferenceModel",
        hop_cutoff: int = 4,
        max_candidates: int = 20,
    ):
        self.interference_model = interference_model
        self.hop_cutoff = hop_cutoff
        self.max_candidates = max_candidates
        self._delegate = WidestPathRouting()
        self._adjacency: Optional[Dict[str, List[Tuple[str, str]]]] = None

    def get_path(
        self,
        src_node: str,
        dst_node: str,
        network: "Network",
        network_state: Optional[Dict] = None,
    ) -> Optional[List[str]]:
        """Find best path given current network state.

        Args:
            src_node: Source node ID
            dst_node: Destination node ID
            network: Network topology
            network_state: Dict with 'active_link_ids' (set) and
                'link_transfer_counts' (dict lid->int). If None,
                delegates to WidestPathRouting.

        Returns:
            List of link IDs forming the path, or None if no path exists.
        """
        if src_node == dst_node:
            return []

        # No real-time state -> delegate (used during HEFT scheduling)
        if network_state is None:
            return self._delegate.get_path(src_node, dst_node, network)

        # Build adjacency lazily
        if self._adjacency is None:
            self._adjacency = _build_adjacency(network)

        # Enumerate and score candidates with real-time state
        candidates = _enumerate_candidate_paths(
            src_node, dst_node, self._adjacency, network,
            self.hop_cutoff, self.max_candidates,
        )
        if not candidates:
            return self._delegate.get_path(src_node, dst_node, network)

        active_link_ids = network_state.get("active_link_ids", set())
        link_transfer_counts = network_state.get("link_transfer_counts", {})

        best_path: Optional[List[str]] = None
        best_score = -1.0

        for path in candidates:
            score = self._score_path(
                path, active_link_ids, link_transfer_counts, network
            )
            if score > best_score:
                best_score = score
                best_path = path

        return best_path

    def get_path_bandwidth(
        self, src_node: str, dst_node: str, network: "Network"
    ) -> float:
        """Delegate bandwidth calculation to WidestPathRouting for HEFT."""
        return self._delegate.get_path_bandwidth(src_node, dst_node, network)

    def _score_path(
        self,
        path: List[str],
        active_link_ids: Set[str],
        link_transfer_counts: Dict[str, int],
        network: "Network",
    ) -> float:
        """Score = effective bottleneck bandwidth of this path given current state.

        Considers interference from all currently-active links plus this path's
        links, and fair-sharing with existing transfers on each link.
        """
        all_active = active_link_ids | set(path)
        eff_bw = float('inf')
        for lid in path:
            factor = self.interference_model.get_interference_factor(
                lid, all_active, network
            )
            existing = link_transfer_counts.get(lid, 0)
            link_bw = network.links[lid].bandwidth * factor / (existing + 1)
            eff_bw = min(eff_bw, link_bw)
        return eff_bw

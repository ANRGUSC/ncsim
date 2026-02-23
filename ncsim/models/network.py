"""
Network model definitions.

Defines nodes, links, and the network topology.
Includes abstract LinkModel for bandwidth calculation extensibility.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ncsim.core.execution_engine import NetworkState


@dataclass
class Position:
    """2D position for visualization."""
    x: float
    y: float


@dataclass
class Node:
    """A compute node in the network.

    Attributes:
        id: Unique node identifier
        compute_capacity: Processing speed in compute_units/second
        position: 2D position for visualization
    """
    id: str
    compute_capacity: float
    position: Position = field(default_factory=lambda: Position(0.0, 0.0))

    def __post_init__(self):
        if self.compute_capacity <= 0:
            raise ValueError(f"Node {self.id}: compute_capacity must be positive")


@dataclass
class Link:
    """A network link between two nodes.

    Attributes:
        id: Unique link identifier
        from_node: Source node ID
        to_node: Destination node ID
        bandwidth: Data rate in MB/second
        latency: Propagation delay in seconds
    """
    id: str
    from_node: str
    to_node: str
    bandwidth: float
    latency: float = 0.0

    def __post_init__(self):
        if self.bandwidth <= 0:
            raise ValueError(f"Link {self.id}: bandwidth must be positive")
        if self.latency < 0:
            raise ValueError(f"Link {self.id}: latency cannot be negative")


class LinkModel(ABC):
    """Abstract base class for link bandwidth calculation.

    Phase 2: StaticLinkModel returns fixed bandwidth from link definition.
    Future: PositionBasedLinkModel, InterferenceLinkModel, TDMALinkModel, etc.
    """

    @abstractmethod
    def get_effective_bandwidth(
        self,
        link: Link,
        sim_time: float,
        network_state: Optional["NetworkState"] = None
    ) -> float:
        """Calculate effective bandwidth for a link at a given time.

        Args:
            link: The link to calculate bandwidth for
            sim_time: Current simulation time
            network_state: Optional network state for advanced models

        Returns:
            Effective bandwidth in MB/second
        """
        pass


class StaticLinkModel(LinkModel):
    """Phase 2 implementation: fixed bandwidth from link definition.

    Does not account for interference, position, or time-varying effects.
    Bandwidth contention (sharing) is handled by the execution engine.
    """

    def get_effective_bandwidth(
        self,
        link: Link,
        sim_time: float,
        network_state: Optional["NetworkState"] = None
    ) -> float:
        """Return the link's static bandwidth value."""
        return link.bandwidth


@dataclass
class Network:
    """Network topology with nodes and links.

    Provides lookup methods for nodes, links, and connectivity.
    """
    nodes: Dict[str, Node] = field(default_factory=dict)
    links: Dict[str, Link] = field(default_factory=dict)
    link_model: LinkModel = field(default_factory=StaticLinkModel)

    # Derived indices (built on first access)
    _links_from: Optional[Dict[str, list]] = field(default=None, repr=False)
    _links_to: Optional[Dict[str, list]] = field(default=None, repr=False)
    _link_between: Optional[Dict[tuple, Link]] = field(default=None, repr=False)

    def __post_init__(self):
        # Validate all link endpoints exist
        for link in self.links.values():
            if link.from_node not in self.nodes:
                raise ValueError(f"Link {link.id}: from_node '{link.from_node}' not found")
            if link.to_node not in self.nodes:
                raise ValueError(f"Link {link.id}: to_node '{link.to_node}' not found")

    def _build_indices(self) -> None:
        """Build link lookup indices."""
        if self._links_from is not None:
            return  # Already built

        self._links_from = {}
        self._links_to = {}
        self._link_between = {}

        for node_id in self.nodes:
            self._links_from[node_id] = []
            self._links_to[node_id] = []

        for link in self.links.values():
            self._links_from[link.from_node].append(link)
            self._links_to[link.to_node].append(link)
            self._link_between[(link.from_node, link.to_node)] = link

    def get_node(self, node_id: str) -> Optional[Node]:
        """Get a node by ID."""
        return self.nodes.get(node_id)

    def get_link(self, link_id: str) -> Optional[Link]:
        """Get a link by ID."""
        return self.links.get(link_id)

    def get_link_between(self, from_node: str, to_node: str) -> Optional[Link]:
        """Get the direct link between two nodes, if any.

        Phase 2: Single-hop only, no multi-hop routing.
        """
        self._build_indices()
        return self._link_between.get((from_node, to_node))

    def get_links_from(self, node_id: str) -> list[Link]:
        """Get all links originating from a node."""
        self._build_indices()
        return self._links_from.get(node_id, [])

    def get_links_to(self, node_id: str) -> list[Link]:
        """Get all links terminating at a node."""
        self._build_indices()
        return self._links_to.get(node_id, [])

    def are_connected(self, from_node: str, to_node: str) -> bool:
        """Check if there's a direct link from from_node to to_node."""
        return self.get_link_between(from_node, to_node) is not None

    def get_effective_bandwidth(
        self,
        link: Link,
        sim_time: float,
        network_state: Optional["NetworkState"] = None
    ) -> float:
        """Get effective bandwidth using the network's link model."""
        return self.link_model.get_effective_bandwidth(link, sim_time, network_state)

    @property
    def node_ids(self) -> list[str]:
        """List of all node IDs."""
        return list(self.nodes.keys())

    @property
    def link_ids(self) -> list[str]:
        """List of all link IDs."""
        return list(self.links.keys())

    def __len__(self) -> int:
        """Number of nodes in the network."""
        return len(self.nodes)

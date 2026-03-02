"""
Base scheduler interface and data types.

Defines the abstract Scheduler class and associated data structures.
The scheduler decides WHERE tasks run; the execution engine decides WHEN.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Optional, Any

from ncsim.models.network import Network, Node, Link
from ncsim.models.dag import DAG
from ncsim.models.task import TaskState


@dataclass
class PlacementPlan:
    """Output of scheduler: task-to-node assignments.

    Attributes:
        assignments: Mapping of task_id -> node_id
        metadata: Optional scheduler-specific metadata
    """
    assignments: Dict[str, str]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_node_for_task(self, task_id: str) -> Optional[str]:
        """Get the assigned node for a task."""
        return self.assignments.get(task_id)


@dataclass
class ReschedulePlan:
    """Output of rescheduling: changes to existing assignments.

    Phase 2: Not used (single scheduling at injection).
    Future: Preemptive scheduling, dynamic rescheduling.

    Attributes:
        new_assignments: Updated task -> node mappings
        cancel_tasks: Task IDs to cancel/preempt
        metadata: Optional scheduler-specific metadata
    """
    new_assignments: Dict[str, str] = field(default_factory=dict)
    cancel_tasks: list = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NodeSnapshot:
    """Snapshot of node state for scheduler.

    Attributes:
        node_id: Node identifier
        compute_capacity: Processing speed
        current_task: Task currently executing (None if idle)
        queue_depth: Number of tasks waiting
        utilization: Current utilization (0.0 to 1.0)
    """
    node_id: str
    compute_capacity: float
    current_task: Optional[str] = None
    queue_depth: int = 0
    utilization: float = 0.0


@dataclass
class LinkSnapshot:
    """Snapshot of link state for scheduler.

    Attributes:
        link_id: Link identifier
        from_node: Source node
        to_node: Destination node
        bandwidth: Available bandwidth
        latency: Propagation delay
        active_transfers: Number of current transfers
        utilization: Current utilization (0.0 to 1.0)
    """
    link_id: str
    from_node: str
    to_node: str
    bandwidth: float
    latency: float
    active_transfers: int = 0
    utilization: float = 0.0


@dataclass
class NetworkSnapshot:
    """Complete network state snapshot for scheduler.

    Provides a read-only view of current network state.
    Scheduler uses this to make placement decisions.

    Attributes:
        nodes: Node state snapshots
        links: Link state snapshots
        timestamp: Simulation time of snapshot
    """
    nodes: Dict[str, NodeSnapshot]
    links: Dict[str, LinkSnapshot]
    timestamp: float

    @classmethod
    def from_network(cls, network: Network, timestamp: float = 0.0) -> "NetworkSnapshot":
        """Create snapshot from static network definition.

        Phase 2: No dynamic state, just topology.
        """
        node_snaps = {
            node_id: NodeSnapshot(
                node_id=node_id,
                compute_capacity=node.compute_capacity
            )
            for node_id, node in network.nodes.items()
        }

        link_snaps = {
            link_id: LinkSnapshot(
                link_id=link_id,
                from_node=link.from_node,
                to_node=link.to_node,
                bandwidth=link.bandwidth,
                latency=link.latency
            )
            for link_id, link in network.links.items()
        }

        return cls(nodes=node_snaps, links=link_snaps, timestamp=timestamp)


class Scheduler(ABC):
    """Abstract base class for task scheduling algorithms.

    The scheduler decides WHERE tasks run. It receives DAGs and network
    state, and returns task-to-node assignments.

    Phase 2: Only on_dag_inject is used.
    Future: Hooks for rescheduling on task completion, network changes.
    """

    @abstractmethod
    def on_dag_inject(
        self,
        dag: DAG,
        network_snapshot: NetworkSnapshot
    ) -> PlacementPlan:
        """Called when a new DAG is injected.

        Must return assignments for all tasks in the DAG.

        Args:
            dag: The DAG to schedule
            network_snapshot: Current network state

        Returns:
            PlacementPlan with task -> node assignments
        """
        pass

    def on_task_complete(
        self,
        task_id: str,
        dag_id: str,
        network_snapshot: NetworkSnapshot
    ) -> Optional[ReschedulePlan]:
        """Called when a task completes.

        Override in future schedulers for dynamic rescheduling.
        Phase 2: Returns None (no rescheduling).

        Args:
            task_id: Completed task ID
            dag_id: DAG containing the task
            network_snapshot: Current network state

        Returns:
            ReschedulePlan if rescheduling needed, None otherwise
        """
        return None

    def on_network_change(
        self,
        change_type: str,
        target_id: str,
        network_snapshot: NetworkSnapshot
    ) -> Optional[ReschedulePlan]:
        """Called when network topology changes.

        Override in future schedulers for mobility-aware scheduling.
        Phase 2: Returns None (static network).

        Args:
            change_type: Type of change ("link_down", "node_down", etc.)
            target_id: ID of affected node or link
            network_snapshot: Current network state

        Returns:
            ReschedulePlan if rescheduling needed, None otherwise
        """
        return None


class ManualScheduler(Scheduler):
    """Manual scheduler that uses pinned_to assignments.

    Reads pinned_to from each task. Tasks without pinned_to are assigned
    to the first available node with a warning.
    """

    def on_dag_inject(
        self,
        dag: DAG,
        network_snapshot: NetworkSnapshot
    ) -> PlacementPlan:
        """Assign tasks based on their pinned_to field."""
        node_ids = list(network_snapshot.nodes.keys())
        if not node_ids:
            raise ValueError("No nodes available for scheduling")

        import logging
        logger = logging.getLogger(__name__)

        assignments = {}
        for task_id in dag.topological_order():
            task = dag.get_task(task_id)
            if task.pinned_to and task.pinned_to in node_ids:
                assignments[task_id] = task.pinned_to
            else:
                assignments[task_id] = node_ids[0]
                if task.pinned_to:
                    logger.warning(
                        f"Task {task_id} pinned to unknown node '{task.pinned_to}', "
                        f"assigning to {node_ids[0]}"
                    )
                else:
                    logger.warning(
                        f"Task {task_id} has no pinned_to assignment, "
                        f"assigning to {node_ids[0]}"
                    )

        return PlacementPlan(
            assignments=assignments,
            metadata={"algorithm": "manual"}
        )


class RoundRobinScheduler(Scheduler):
    """Simple round-robin scheduler for testing.

    Assigns tasks to nodes in order, cycling through available nodes.
    """

    def __init__(self):
        self._next_node_idx = 0

    def on_dag_inject(
        self,
        dag: DAG,
        network_snapshot: NetworkSnapshot
    ) -> PlacementPlan:
        """Assign tasks round-robin to nodes."""
        node_ids = list(network_snapshot.nodes.keys())
        if not node_ids:
            raise ValueError("No nodes available for scheduling")

        assignments = {}
        for task_id in dag.topological_order():
            task = dag.get_task(task_id)

            # Check for pinned task
            if task.pinned_to and task.pinned_to in node_ids:
                assignments[task_id] = task.pinned_to
            else:
                # Round-robin assignment
                assignments[task_id] = node_ids[self._next_node_idx % len(node_ids)]
                self._next_node_idx += 1

        return PlacementPlan(assignments=assignments)

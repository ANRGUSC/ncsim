"""
Execution engine for the discrete event simulation.

Handles event processing, node/link state management, and bandwidth sharing.
The scheduler decides WHERE tasks run; this engine decides WHEN.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Callable, Any

from ncsim.core.event_queue import EventQueue, Event, EventType, round_time
from ncsim.models.network import Network, Link
from ncsim.models.dag import DAG, Edge
from ncsim.models.task import Task, TaskState, TaskStatus, FIFOQueueModel
from ncsim.models.routing import DirectLinkRouting, RoutingModel
from ncsim.scheduler.base import Scheduler, PlacementPlan, NetworkSnapshot

logger = logging.getLogger(__name__)


class SimulationError(Exception):
    """Raised when a simulation encounters an unrecoverable error."""
    pass


@dataclass
class ActiveTransfer:
    """State of an in-progress data transfer.

    Attributes:
        dag_id: DAG containing the transfer
        from_task: Source task ID
        to_task: Destination task ID
        link_id: Primary link ID (first link for single-hop, or bottleneck for multi-hop)
        link_ids: All link IDs in the path (for multi-hop transfers)
        data_size: Total data to transfer (MB)
        data_remaining: Data left to transfer (MB)
        started_at: Sim time when transfer started
        scheduled_complete: Currently scheduled completion time
        event_id: Event ID for completion (for cancellation)
        bottleneck_bandwidth: Bottleneck bandwidth of the path (MB/s)
        total_latency: Sum of latencies across all links (seconds)
    """
    dag_id: str
    from_task: str
    to_task: str
    link_id: str
    data_size: float
    data_remaining: float
    started_at: float
    scheduled_complete: float
    event_id: int
    link_ids: List[str] = field(default_factory=list)
    bottleneck_bandwidth: float = 0.0
    total_latency: float = 0.0


@dataclass
class NodeState:
    """Runtime state of a compute node.

    Attributes:
        node_id: Node identifier
        current_task: Task currently executing (None if idle)
        queue: Queued tasks waiting to execute
        total_busy_time: Cumulative time spent executing tasks
    """
    node_id: str
    current_task: Optional[TaskState] = None
    queue: FIFOQueueModel = field(default_factory=FIFOQueueModel)
    total_busy_time: float = 0.0

    def is_idle(self) -> bool:
        """Check if node is not executing a task."""
        return self.current_task is None


@dataclass
class LinkState:
    """Runtime state of a network link.

    Attributes:
        link_id: Link identifier
        active_transfers: List of transfers currently using this link
        total_data_transferred: Cumulative data transferred
    """
    link_id: str
    active_transfers: List[ActiveTransfer] = field(default_factory=list)
    total_data_transferred: float = 0.0

    @property
    def num_transfers(self) -> int:
        """Number of concurrent transfers on this link."""
        return len(self.active_transfers)


@dataclass
class NetworkState:
    """Complete simulation state.

    Used for scheduler snapshots and telemetry.
    """
    sim_time: float
    node_states: Dict[str, NodeState]
    link_states: Dict[str, LinkState]
    task_states: Dict[str, TaskState]  # Keyed by (dag_id, task_id)

    def get_task_state(self, dag_id: str, task_id: str) -> Optional[TaskState]:
        """Get task state by DAG and task ID."""
        return self.task_states.get(f"{dag_id}:{task_id}")


# Type for event listeners
EventListener = Callable[[Event, "ExecutionEngine"], None]


class ExecutionEngine:
    """Core execution engine for discrete event simulation.

    Processes events and maintains simulation state.
    """

    def __init__(
        self,
        network: Network,
        scheduler: Scheduler,
        event_queue: EventQueue,
        routing_model: Optional[RoutingModel] = None
    ):
        """Initialize execution engine.

        Args:
            network: Network topology
            scheduler: Scheduler for task placement
            event_queue: Event queue for simulation
            routing_model: Optional routing model (default: DirectLinkRouting)
        """
        self.network = network
        self.scheduler = scheduler
        self.event_queue = event_queue
        self.routing_model = routing_model or DirectLinkRouting()

        # Initialize node states
        self.node_states: Dict[str, NodeState] = {
            node_id: NodeState(node_id=node_id)
            for node_id in network.nodes
        }

        # Initialize link states
        self.link_states: Dict[str, LinkState] = {
            link_id: LinkState(link_id=link_id)
            for link_id in network.links
        }

        # Task states (keyed by "dag_id:task_id")
        self.task_states: Dict[str, TaskState] = {}

        # Placement plans by DAG ID
        self.placement_plans: Dict[str, PlacementPlan] = {}

        # DAGs by ID
        self.dags: Dict[str, DAG] = {}

        # Event listeners for trace writing
        self._listeners: List[EventListener] = []

        # Simulation time
        self.sim_time = 0.0

    def add_listener(self, listener: EventListener) -> None:
        """Add an event listener."""
        self._listeners.append(listener)

    def _notify_listeners(self, event: Event) -> None:
        """Notify all listeners of an event."""
        for listener in self._listeners:
            listener(event, self)

    def _task_key(self, dag_id: str, task_id: str) -> str:
        """Create unique key for task state lookup."""
        return f"{dag_id}:{task_id}"

    def get_task_state(self, dag_id: str, task_id: str) -> Optional[TaskState]:
        """Get task state by DAG and task ID."""
        return self.task_states.get(self._task_key(dag_id, task_id))

    def get_network_snapshot(self) -> NetworkSnapshot:
        """Create a snapshot of current network state for scheduler."""
        return NetworkSnapshot.from_network(self.network, self.sim_time)

    def get_network_state(self) -> NetworkState:
        """Get complete network state."""
        return NetworkState(
            sim_time=self.sim_time,
            node_states=self.node_states,
            link_states=self.link_states,
            task_states=self.task_states
        )

    def handle_event(self, event: Event) -> None:
        """Dispatch event to appropriate handler."""
        self.sim_time = round_time(event.sim_time)

        handlers = {
            EventType.DAG_INJECT: self._handle_dag_inject,
            EventType.TASK_READY: self._handle_task_ready,
            EventType.TASK_START: self._handle_task_start,
            EventType.TASK_COMPLETE: self._handle_task_complete,
            EventType.TRANSFER_START: self._handle_transfer_start,
            EventType.TRANSFER_COMPLETE: self._handle_transfer_complete,
        }

        handler = handlers.get(event.event_type)
        if handler:
            handler(event)
            self._notify_listeners(event)
        else:
            logger.debug(f"No handler for event type: {event.event_type}")

    def _handle_dag_inject(self, event: Event) -> None:
        """Handle DAG injection event.

        1. Get placement plan from scheduler
        2. Initialize task states
        3. Schedule TASK_READY for root tasks
        """
        dag_id = event.dag_id
        dag = event.data.get("dag")

        if dag is None:
            logger.error(f"DAG_INJECT event missing 'dag' data")
            return

        # Store DAG
        self.dags[dag_id] = dag

        # Get placement from scheduler
        snapshot = self.get_network_snapshot()
        plan = self.scheduler.on_dag_inject(dag, snapshot)
        self.placement_plans[dag_id] = plan
        self._validate_placement(dag, plan)

        logger.info(f"DAG {dag_id} injected with {len(dag.tasks)} tasks")
        logger.debug(f"Placement plan: {plan.assignments}")

        # Initialize task states
        for task_id, task in dag.tasks.items():
            assigned_node = plan.get_node_for_task(task_id)
            if assigned_node is None:
                logger.error(f"No assignment for task {task_id}")
                continue

            predecessors = dag.get_predecessors(task_id)
            task_state = TaskState(
                task_id=task_id,
                dag_id=dag_id,
                assigned_node=assigned_node,
                status=TaskStatus.PENDING,
                compute_remaining=task.compute_cost,
                predecessors_remaining=set(predecessors)
            )
            self.task_states[self._task_key(dag_id, task_id)] = task_state

        # Schedule TASK_READY for root tasks (no predecessors)
        root_tasks = dag.get_root_tasks()
        for task_id in root_tasks:
            self.event_queue.schedule(
                sim_time=self.sim_time,
                event_type=EventType.TASK_READY,
                dag_id=dag_id,
                task_id=task_id
            )
            logger.debug(f"Scheduled TASK_READY for root task {task_id}")

    def _validate_placement(self, dag: DAG, plan: PlacementPlan) -> None:
        """Validate that all DAG edges have valid routes under current routing."""
        errors = []
        for edge in dag.edges:
            src_node = plan.get_node_for_task(edge.from_task)
            dst_node = plan.get_node_for_task(edge.to_task)
            if src_node is None or dst_node is None:
                continue  # Missing assignments caught elsewhere
            if src_node == dst_node:
                continue  # Local transfer, no routing needed
            path = self.routing_model.get_path(src_node, dst_node, self.network)
            if path is None or len(path) == 0:
                errors.append(
                    f"  {edge.from_task}({src_node}) -> {edge.to_task}({dst_node}): "
                    f"no route via {type(self.routing_model).__name__}"
                )
        if errors:
            raise SimulationError(
                f"Placement plan for DAG {dag.id} has {len(errors)} unreachable transfer(s):\n"
                + "\n".join(errors)
            )

    def _handle_task_ready(self, event: Event) -> None:
        """Handle task ready event.

        If assigned node is idle: start task immediately.
        If node is busy: add to node's FIFO queue.
        """
        dag_id = event.dag_id
        task_id = event.task_id

        task_state = self.get_task_state(dag_id, task_id)
        if task_state is None:
            logger.error(f"TASK_READY: task state not found for {dag_id}:{task_id}")
            return

        task_state.status = TaskStatus.READY

        node_id = task_state.assigned_node
        node_state = self.node_states.get(node_id)
        if node_state is None:
            logger.error(f"TASK_READY: node {node_id} not found")
            return

        if node_state.is_idle():
            # Start immediately - mark node as busy NOW to prevent
            # other TASK_READY events at same time from also starting
            node_state.current_task = task_state
            self.event_queue.schedule(
                sim_time=self.sim_time,
                event_type=EventType.TASK_START,
                dag_id=dag_id,
                task_id=task_id,
                node_id=node_id
            )
            logger.debug(f"Task {task_id} starting immediately on {node_id}")
        else:
            # Queue the task
            task_state.status = TaskStatus.QUEUED
            task_state.queued_at = self.sim_time
            node_state.queue.enqueue(task_state)
            logger.debug(f"Task {task_id} queued on {node_id} (queue depth: {len(node_state.queue)})")

    def _handle_task_start(self, event: Event) -> None:
        """Handle task start event.

        Mark node as busy, schedule TASK_COMPLETE.
        """
        dag_id = event.dag_id
        task_id = event.task_id
        node_id = event.node_id

        task_state = self.get_task_state(dag_id, task_id)
        if task_state is None:
            logger.error(f"TASK_START: task state not found for {dag_id}:{task_id}")
            return

        node_state = self.node_states.get(node_id)
        if node_state is None:
            logger.error(f"TASK_START: node {node_id} not found")
            return

        node = self.network.get_node(node_id)
        dag = self.dags.get(dag_id)
        task = dag.get_task(task_id) if dag else None

        if node is None or task is None:
            logger.error(f"TASK_START: node or task not found")
            return

        # Mark task as running
        task_state.status = TaskStatus.RUNNING
        task_state.started_at = self.sim_time
        node_state.current_task = task_state

        # Calculate execution time
        execution_time = task.execution_time(node.compute_capacity)
        complete_time = round_time(self.sim_time + execution_time)

        # Schedule completion
        self.event_queue.schedule(
            sim_time=complete_time,
            event_type=EventType.TASK_COMPLETE,
            dag_id=dag_id,
            task_id=task_id,
            node_id=node_id,
            data={"duration": execution_time}
        )

        logger.debug(f"Task {task_id} started on {node_id}, will complete at {complete_time:.6f}")

    def _handle_task_complete(self, event: Event) -> None:
        """Handle task completion event.

        1. Mark task complete
        2. Schedule output transfers
        3. Start next queued task on node
        """
        dag_id = event.dag_id
        task_id = event.task_id
        node_id = event.node_id
        duration = event.data.get("duration", 0.0)

        task_state = self.get_task_state(dag_id, task_id)
        if task_state is None:
            logger.error(f"TASK_COMPLETE: task state not found for {dag_id}:{task_id}")
            return

        node_state = self.node_states.get(node_id)
        if node_state is None:
            logger.error(f"TASK_COMPLETE: node {node_id} not found")
            return

        dag = self.dags.get(dag_id)
        if dag is None:
            logger.error(f"TASK_COMPLETE: dag {dag_id} not found")
            return

        # Mark task complete
        task_state.status = TaskStatus.COMPLETED
        task_state.completed_at = self.sim_time
        task_state.compute_remaining = 0.0
        node_state.current_task = None
        node_state.total_busy_time += duration

        logger.debug(f"Task {task_id} completed on {node_id} after {duration:.6f}s")

        # Schedule output transfers
        outgoing_edges = dag.get_outgoing_edges(task_id)
        for edge in outgoing_edges:
            self._schedule_transfer_start(dag_id, edge)

        # Start next queued task
        if not node_state.queue.is_empty():
            next_task = node_state.queue.dequeue()
            self.event_queue.schedule(
                sim_time=self.sim_time,
                event_type=EventType.TASK_START,
                dag_id=next_task.dag_id,
                task_id=next_task.task_id,
                node_id=node_id
            )
            logger.debug(f"Starting queued task {next_task.task_id} on {node_id}")

    def _schedule_transfer_start(self, dag_id: str, edge: Edge) -> None:
        """Schedule a transfer start event for a DAG edge."""
        from_task = edge.from_task
        to_task = edge.to_task

        from_state = self.get_task_state(dag_id, from_task)
        to_state = self.get_task_state(dag_id, to_task)

        if from_state is None or to_state is None:
            logger.error(f"Transfer edge references unknown task")
            return

        src_node = from_state.assigned_node
        dst_node = to_state.assigned_node

        # Check if same node (local transfer)
        if src_node == dst_node:
            # No network transfer needed - mark predecessor complete
            self._complete_local_transfer(dag_id, from_task, to_task)
            return

        # Get path for transfer
        path = self.routing_model.get_path(src_node, dst_node, self.network)

        if path is None or len(path) == 0:
            raise SimulationError(
                f"No route from {src_node} to {dst_node} for transfer "
                f"{from_task}->{to_task} (routing={type(self.routing_model).__name__}). "
                f"Check that the routing model supports this topology."
            )

        # Use first link as primary (for trace events), store full path in data
        link_id = path[0]

        # Calculate bottleneck bandwidth and total latency for multi-hop paths
        if len(path) == 1:
            # Single-hop: use link's bandwidth and latency directly
            bottleneck_bw = self.network.links[link_id].bandwidth
            total_latency = self.network.links[link_id].latency
        else:
            # Multi-hop: bottleneck = min bandwidth, latency = sum of all latencies
            bottleneck_bw = min(self.network.links[lid].bandwidth for lid in path)
            total_latency = sum(self.network.links[lid].latency for lid in path)

        self.event_queue.schedule(
            sim_time=self.sim_time,
            event_type=EventType.TRANSFER_START,
            dag_id=dag_id,
            from_task=from_task,
            to_task=to_task,
            link_id=link_id,
            data={
                "data_size": edge.data_size,
                "path": path,
                "bottleneck_bandwidth": bottleneck_bw,
                "total_latency": total_latency
            }
        )

    def _complete_local_transfer(self, dag_id: str, from_task: str, to_task: str) -> None:
        """Handle a local transfer (same node, no network)."""
        to_state = self.get_task_state(dag_id, to_task)
        if to_state is None:
            return

        # Mark predecessor complete
        if to_state.mark_predecessor_complete(from_task):
            # All predecessors done - task is ready
            self.event_queue.schedule(
                sim_time=self.sim_time,
                event_type=EventType.TASK_READY,
                dag_id=dag_id,
                task_id=to_task
            )
            logger.debug(f"Local transfer {from_task}->{to_task}, task {to_task} now ready")

    def _handle_transfer_start(self, event: Event) -> None:
        """Handle transfer start event.

        Add transfer to all links in path, recalculate transfer completion times.
        For multi-hop paths, uses bottleneck bandwidth and summed latencies.
        """
        dag_id = event.dag_id
        from_task = event.from_task
        to_task = event.to_task
        link_id = event.link_id
        data_size = event.data.get("data_size", 0.0)
        path = event.data.get("path", [link_id])
        bottleneck_bw = event.data.get("bottleneck_bandwidth", 0.0)
        total_latency = event.data.get("total_latency", 0.0)

        # Validate all links in path exist
        for lid in path:
            if lid not in self.link_states:
                logger.error(f"TRANSFER_START: link {lid} not found in path")
                return
            if self.network.get_link(lid) is None:
                logger.error(f"TRANSFER_START: link {lid} not in network")
                return

        # For bandwidth sharing, we need to find the effective bandwidth
        # considering contention on ALL links in the path
        # The bottleneck is the minimum effective bandwidth across all links
        effective_bw = bottleneck_bw
        for lid in path:
            link_state = self.link_states[lid]
            link = self.network.links[lid]
            # Each link independently shares bandwidth among concurrent transfers
            num_transfers_on_link = link_state.num_transfers + 1
            link_effective_bw = link.bandwidth / num_transfers_on_link
            effective_bw = min(effective_bw, link_effective_bw)

        # Calculate completion time: transfer time + total latency
        transfer_time = (data_size / effective_bw) + total_latency
        complete_time = round_time(self.sim_time + transfer_time)

        # Schedule completion event
        event_id = self.event_queue.schedule(
            sim_time=complete_time,
            event_type=EventType.TRANSFER_COMPLETE,
            dag_id=dag_id,
            from_task=from_task,
            to_task=to_task,
            link_id=link_id,
            data={"data_size": data_size, "path": path}
        )

        # Track active transfer on ALL links in the path
        transfer = ActiveTransfer(
            dag_id=dag_id,
            from_task=from_task,
            to_task=to_task,
            link_id=link_id,
            link_ids=path,
            data_size=data_size,
            data_remaining=data_size,
            started_at=self.sim_time,
            scheduled_complete=complete_time,
            event_id=event_id,
            bottleneck_bandwidth=bottleneck_bw,
            total_latency=total_latency
        )

        # Add transfer to all links in path
        for lid in path:
            self.link_states[lid].active_transfers.append(transfer)

        if len(path) == 1:
            logger.debug(f"Transfer {from_task}->{to_task} started on {link_id}, "
                        f"effective_bw={effective_bw:.2f}, complete at {complete_time:.6f}")
        else:
            logger.debug(f"Transfer {from_task}->{to_task} started on multi-hop path {path}, "
                        f"bottleneck_bw={bottleneck_bw:.2f}, effective_bw={effective_bw:.2f}, "
                        f"complete at {complete_time:.6f}")

        # Recalculate other transfers on all links in path (bandwidth sharing)
        for lid in path:
            self._recalculate_link_transfers(lid, transfer)

    def _recalculate_link_transfers(
        self,
        link_id: str,
        exclude_transfer: Optional[ActiveTransfer] = None
    ) -> None:
        """Recalculate completion times for all transfers on a link.

        Called when a transfer starts or completes to update bandwidth sharing.
        For multi-hop transfers, recalculates effective bandwidth across entire path.
        """
        link_state = self.link_states.get(link_id)
        link = self.network.get_link(link_id)

        if link_state is None or link is None:
            return

        num_transfers = link_state.num_transfers
        if num_transfers == 0:
            return

        # Track transfers we've already recalculated to avoid duplicates
        recalculated: set = set()

        for transfer in link_state.active_transfers:
            if transfer is exclude_transfer:
                continue  # Don't recalculate the one we just added

            # Use transfer identity to track recalculation
            transfer_key = (transfer.dag_id, transfer.from_task, transfer.to_task)
            if transfer_key in recalculated:
                continue
            recalculated.add(transfer_key)

            # Cancel old completion event
            self.event_queue.cancel(transfer.event_id)

            # For multi-hop, calculate effective bandwidth across ALL links in path
            path = transfer.link_ids if transfer.link_ids else [transfer.link_id]
            effective_bw = transfer.bottleneck_bandwidth if transfer.bottleneck_bandwidth > 0 else link.bandwidth

            for lid in path:
                lid_state = self.link_states.get(lid)
                lid_link = self.network.get_link(lid)
                if lid_state and lid_link:
                    num_on_link = lid_state.num_transfers
                    if num_on_link > 0:
                        link_bw = lid_link.bandwidth / num_on_link
                        effective_bw = min(effective_bw, link_bw)

            # Calculate how much data has been transferred
            elapsed = self.sim_time - transfer.started_at
            if elapsed > 0:
                # Approximate data transferred (for exact we'd need rate history)
                # Use simple approximation based on old effective bandwidth
                old_effective_bw = transfer.bottleneck_bandwidth if transfer.bottleneck_bandwidth > 0 else link.bandwidth
                data_transferred = old_effective_bw * elapsed
                transfer.data_remaining = max(0, transfer.data_size - data_transferred)

            # Calculate new completion time
            total_latency = transfer.total_latency if transfer.total_latency > 0 else link.latency
            if transfer.data_remaining > 0:
                remaining_time = (transfer.data_remaining / effective_bw) + total_latency
                new_complete_time = round_time(self.sim_time + remaining_time)
            else:
                new_complete_time = round_time(self.sim_time + total_latency)

            # Schedule new completion event
            transfer.event_id = self.event_queue.schedule(
                sim_time=new_complete_time,
                event_type=EventType.TRANSFER_COMPLETE,
                dag_id=transfer.dag_id,
                from_task=transfer.from_task,
                to_task=transfer.to_task,
                link_id=transfer.link_id,
                data={"data_size": transfer.data_size, "path": path}
            )
            transfer.scheduled_complete = new_complete_time
            transfer.started_at = self.sim_time  # Reset start time for next recalc

            logger.debug(f"Recalculated transfer {transfer.from_task}->{transfer.to_task}: "
                        f"new complete at {new_complete_time:.6f}")

    def _handle_transfer_complete(self, event: Event) -> None:
        """Handle transfer completion event.

        1. Remove transfer from all links in path
        2. Recalculate other transfers (more bandwidth available)
        3. Check if destination task is now ready
        """
        dag_id = event.dag_id
        from_task = event.from_task
        to_task = event.to_task
        link_id = event.link_id
        data_size = event.data.get("data_size", 0.0)
        path = event.data.get("path", [link_id])

        # Find and remove completed transfer from ALL links in path
        transfer_found = None
        affected_links = []

        for lid in path:
            link_state = self.link_states.get(lid)
            if link_state is None:
                logger.error(f"TRANSFER_COMPLETE: link {lid} not found")
                continue

            # Find and remove transfer from this link
            for i, transfer in enumerate(link_state.active_transfers):
                if (transfer.dag_id == dag_id and
                    transfer.from_task == from_task and
                    transfer.to_task == to_task):
                    if transfer_found is None:
                        transfer_found = transfer
                    link_state.active_transfers.pop(i)
                    affected_links.append(lid)
                    break

        if transfer_found is None:
            logger.warning(f"TRANSFER_COMPLETE: transfer not found in active list")
        else:
            # Calculate actual duration
            duration = self.sim_time - transfer_found.started_at

            # Update stats on all links
            for lid in path:
                link_state = self.link_states.get(lid)
                if link_state:
                    link_state.total_data_transferred += data_size

            if len(path) == 1:
                logger.debug(f"Transfer {from_task}->{to_task} completed on {link_id} "
                            f"after {duration:.6f}s")
            else:
                logger.debug(f"Transfer {from_task}->{to_task} completed on multi-hop path {path} "
                            f"after {duration:.6f}s")

        # Recalculate remaining transfers on all affected links
        for lid in affected_links:
            link_state = self.link_states.get(lid)
            if link_state and link_state.active_transfers:
                self._recalculate_link_transfers(lid)

        # Check if destination task is now ready
        to_state = self.get_task_state(dag_id, to_task)
        if to_state is not None:
            if to_state.mark_predecessor_complete(from_task):
                # All predecessors done - task is ready
                self.event_queue.schedule(
                    sim_time=self.sim_time,
                    event_type=EventType.TASK_READY,
                    dag_id=dag_id,
                    task_id=to_task
                )
                logger.debug(f"Task {to_task} now ready (all predecessors complete)")

    def get_makespan(self) -> float:
        """Calculate makespan (time of last task completion)."""
        max_complete = 0.0
        for task_state in self.task_states.values():
            if task_state.completed_at is not None:
                max_complete = max(max_complete, task_state.completed_at)
        return max_complete

    def get_node_utilization(self, node_id: str) -> float:
        """Calculate utilization for a node (busy_time / total_time)."""
        node_state = self.node_states.get(node_id)
        if node_state is None or self.sim_time == 0:
            return 0.0
        return node_state.total_busy_time / self.sim_time

    def get_link_utilization(self, link_id: str) -> float:
        """Calculate utilization for a link (data_transferred / (bandwidth * time))."""
        link_state = self.link_states.get(link_id)
        link = self.network.get_link(link_id)
        if link_state is None or link is None or self.sim_time == 0:
            return 0.0
        max_data = link.bandwidth * self.sim_time
        if max_data == 0:
            return 0.0
        return min(1.0, link_state.total_data_transferred / max_data)

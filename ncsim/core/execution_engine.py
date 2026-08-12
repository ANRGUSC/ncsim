"""
Execution engine for the discrete event simulation.

Handles event processing, node/link state management, and bandwidth sharing.
The scheduler decides WHERE tasks run; this engine decides WHEN.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Callable, Any

from ncsim.core.event_queue import EventQueue, Event, EventType, round_time
from ncsim.models.network import Network, Link
from ncsim.models.dag import DAG, Edge
from ncsim.models.task import Task, TaskState, TaskStatus, FIFOQueueModel
from ncsim.models.routing import DirectLinkRouting, RoutingModel
from ncsim.models.interference import InterferenceModel
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
    current_effective_rate: float = 0.0


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
        up: Whether the link is currently usable (False after LINK_DOWN)
        bandwidth_factor: Multiplier on base bandwidth (reduced by LINK_DEGRADE)
    """
    link_id: str
    active_transfers: List[ActiveTransfer] = field(default_factory=list)
    total_data_transferred: float = 0.0
    up: bool = True
    bandwidth_factor: float = 1.0

    @property
    def num_transfers(self) -> int:
        """Number of concurrent transfers on this link."""
        return len(self.active_transfers)


@dataclass
class StalledTransfer:
    """A transfer that cannot proceed because no usable route exists.

    Held by the engine until a RECOVERY event makes a route available again.
    An aborted in-flight transfer is retransmitted from scratch (full
    data_size): the connection died, so partial progress is lost.

    Attributes:
        dag_id: DAG containing the transfer
        edge: The DAG edge (from_task, to_task, data_size) to (re)transmit
        stalled_at: Sim time when the transfer stalled
        was_in_flight: True if this transfer was aborted mid-flight
    """
    dag_id: str
    edge: Edge
    stalled_at: float
    was_in_flight: bool = False


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
        routing_model: Optional[RoutingModel] = None,
        interference_model: Optional[InterferenceModel] = None,
        repair_cost_base: float = 0.0,
        repair_cost_per_task: float = 0.0,
    ):
        """Initialize execution engine.

        Args:
            network: Network topology
            scheduler: Scheduler for task placement
            event_queue: Event queue for simulation
            routing_model: Optional routing model (default: DirectLinkRouting)
            interference_model: Optional inter-link interference model
            repair_cost_base: Fixed decision latency charged per repair (seconds)
            repair_cost_per_task: Additional latency per task the plan moves
        """
        self.network = network
        self.scheduler = scheduler
        self.event_queue = event_queue
        self.routing_model = routing_model or DirectLinkRouting()
        self.interference_model = interference_model
        self.repair_cost_base = repair_cost_base
        self.repair_cost_per_task = repair_cost_per_task

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

        # Link disruption state
        self._disruptions_enabled = False  # Set when a disruption model is attached
        self._stalled_transfers: List[StalledTransfer] = []
        self._routable_network_cache: Optional[Network] = None
        self.disruption_stats: Dict[str, int] = {
            "disruptions_applied": 0,
            "transfers_aborted": 0,
            "transfers_stalled": 0,
            "transfers_resumed": 0,
            "tasks_replanned": 0,
            "repairs_superseded": 0,
        }
        # Event id of a repair plan awaiting application (decision latency),
        # so a newer plan can supersede it.
        self._pending_repair_event_id: Optional[int] = None
        # Wall-clock spent inside the repair policy. Reported as a metric,
        # never fed into sim time: sim-time repair cost comes from the
        # deterministic model above, keeping same-seed runs identical.
        self.repair_wall_time_s: float = 0.0

    def add_listener(self, listener: EventListener) -> None:
        """Add an event listener."""
        self._listeners.append(listener)

    def enable_disruptions(self) -> None:
        """Mark this run as disruption-aware.

        Called by the simulation when a disruption model is attached. Missing
        routes then stall transfers instead of failing the run, since a route
        absent now may exist again after a recovery or repair.
        """
        self._disruptions_enabled = True

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
        """Create a snapshot of current network state for scheduler.

        Link bandwidths reflect the current disruption state: a downed link
        reports 0.0, a degraded link reports its reduced bandwidth. This is
        what lets a rescheduling policy see the network it must plan against.
        """
        snapshot = NetworkSnapshot.from_network(self.network, self.sim_time)
        for link_id, link_snap in snapshot.links.items():
            link_state = self.link_states.get(link_id)
            if link_state is None:
                continue
            if not link_state.up:
                link_snap.bandwidth = 0.0
            else:
                link_snap.bandwidth *= link_state.bandwidth_factor
            link_snap.active_transfers = link_state.num_transfers
            link_snap.utilization = self.get_link_utilization(link_id)
        for node_id, node_snap in snapshot.nodes.items():
            node_state = self.node_states.get(node_id)
            if node_state is None:
                continue
            if node_state.current_task is not None:
                node_snap.current_task = node_state.current_task.task_id
            node_snap.queue_depth = len(node_state.queue)
            node_snap.utilization = self.get_node_utilization(node_id)
        return snapshot

    def _routable_network(self) -> Network:
        """Return the network restricted to links that are currently up.

        Routing models consult this view, so path computation naturally avoids
        downed links. Cached and invalidated on every link state change.
        """
        if not self._disruptions_enabled:
            return self.network
        if self._routable_network_cache is None:
            self._routable_network_cache = Network(
                nodes=self.network.nodes,
                links={
                    link_id: link
                    for link_id, link in self.network.links.items()
                    if self.link_states[link_id].up
                },
                link_model=self.network.link_model,
            )
        return self._routable_network_cache

    def get_network_state(self) -> NetworkState:
        """Get complete network state."""
        return NetworkState(
            sim_time=self.sim_time,
            node_states=self.node_states,
            link_states=self.link_states,
            task_states=self.task_states
        )

    def _get_active_link_ids(self) -> Set[str]:
        """Return set of link IDs that have at least one active transfer."""
        return {lid for lid, ls in self.link_states.items() if ls.num_transfers > 0}

    def _get_link_bandwidth(
        self,
        link_id: str,
        extra_active_links: Optional[Set[str]] = None
    ) -> float:
        """Get base bandwidth for a link, accounting for interference.

        Args:
            link_id: Link to query
            extra_active_links: Additional link IDs to treat as active
                (used before a new transfer is added to link_states)

        Returns:
            Effective base bandwidth (before per-link fair sharing)
        """
        link = self.network.links[link_id]
        link_state = self.link_states[link_id]
        if not link_state.up:
            return 0.0
        base_bandwidth = link.bandwidth * link_state.bandwidth_factor
        if self.interference_model is None:
            return base_bandwidth
        active_links = self._get_active_link_ids()
        if extra_active_links:
            active_links = active_links | extra_active_links
        factor = self.interference_model.get_interference_factor(
            link_id, active_links, self.network
        )
        return base_bandwidth * factor

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
            EventType.LINK_STATE_CHANGE: self._handle_link_state_change,
            EventType.RESCHEDULE_TRIGGER: self._handle_reschedule_trigger,
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
            path = self.routing_model.get_path(src_node, dst_node, self._routable_network())
            if path is None or len(path) == 0:
                errors.append(
                    f"  {edge.from_task}({src_node}) -> {edge.to_task}({dst_node}): "
                    f"no route via {type(self.routing_model).__name__}"
                )
        if errors:
            if self._disruptions_enabled:
                # A route missing now may exist after a recovery or repair;
                # the stall machinery holds the affected transfers meanwhile.
                logger.warning(
                    f"Placement plan for DAG {dag.id} has {len(errors)} transfer(s) "
                    f"with no route under the current (disrupted) topology:\n"
                    + "\n".join(errors)
                )
                return
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

        if task_state.status != TaskStatus.PENDING:
            # Idempotency guard: a duplicate TASK_READY would queue the task
            # behind itself and execute it twice.
            logger.warning(
                f"TASK_READY for {dag_id}:{task_id} ignored: status is "
                f"{task_state.status.name}, not PENDING"
            )
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

        # Get path for transfer. Routing sees only links that are up, so a
        # transfer naturally routes around downed links when the routing
        # model supports alternatives.
        path = self.routing_model.get_path(src_node, dst_node, self._routable_network())

        if path is None or len(path) == 0:
            if self._disruptions_enabled:
                # No route *right now*; park the transfer until a recovery
                # (or a repair) makes one available.
                self._stall_transfer(dag_id, edge)
                return
            raise SimulationError(
                f"No route from {src_node} to {dst_node} for transfer "
                f"{from_task}->{to_task} (routing={type(self.routing_model).__name__}). "
                f"Check that the routing model supports this topology."
            )

        # Use first link as primary (for trace events), store full path in data
        link_id = path[0]

        # Calculate bottleneck bandwidth and total latency for multi-hop paths.
        # Bandwidths reflect current degradation factors.
        def current_bandwidth(lid: str) -> float:
            return self.network.links[lid].bandwidth * self.link_states[lid].bandwidth_factor

        if len(path) == 1:
            # Single-hop: use link's bandwidth and latency directly
            bottleneck_bw = current_bandwidth(link_id)
            total_latency = self.network.links[link_id].latency
        else:
            # Multi-hop: bottleneck = min bandwidth, latency = sum of all latencies
            bottleneck_bw = min(current_bandwidth(lid) for lid in path)
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
        # considering contention on ALL links in the path.
        # With interference, base bandwidth is reduced by interference factor,
        # then shared among concurrent transfers on each link.
        extra_active = set(path)  # Treat path links as active for interference calc
        effective_bw = float('inf')
        for lid in path:
            link_state = self.link_states[lid]
            base_bw = self._get_link_bandwidth(lid, extra_active_links=extra_active)
            # Each link independently shares bandwidth among concurrent transfers
            num_transfers_on_link = link_state.num_transfers + 1
            link_effective_bw = base_bw / num_transfers_on_link
            effective_bw = min(effective_bw, link_effective_bw)

        # A link in the path may have gone down at this very instant
        # (LINK_STATE_CHANGE sorts after TRANSFER_START at equal times).
        if effective_bw <= 0:
            self._stall_transfer(
                dag_id,
                Edge(from_task=from_task, to_task=to_task, data_size=data_size),
            )
            return

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
            total_latency=total_latency,
            current_effective_rate=effective_bw
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

        # Recalculate transfers on interfered links (cross-link effects)
        self._recalculate_interfered_transfers(set(path))

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
            # With interference, use _get_link_bandwidth which applies the factor
            path = transfer.link_ids if transfer.link_ids else [transfer.link_id]
            effective_bw = float('inf')

            for lid in path:
                lid_state = self.link_states.get(lid)
                if lid_state:
                    num_on_link = lid_state.num_transfers
                    if num_on_link > 0:
                        base_bw = self._get_link_bandwidth(lid)
                        link_bw = base_bw / num_on_link
                        effective_bw = min(effective_bw, link_bw)

            # Calculate how much data has been transferred since last recalculation
            elapsed = self.sim_time - transfer.started_at
            if elapsed > 0:
                # Use tracked effective rate for accurate elapsed data calculation
                old_effective_rate = transfer.current_effective_rate if transfer.current_effective_rate > 0 else link.bandwidth
                data_transferred = old_effective_rate * elapsed
                transfer.data_remaining = max(0, transfer.data_remaining - data_transferred)

            # Transfers crossing a downed link are aborted before this runs,
            # so a non-positive bandwidth here means an inconsistent state.
            if effective_bw <= 0 or effective_bw == float('inf'):
                logger.error(
                    f"Recalculation of {transfer.from_task}->{transfer.to_task} "
                    f"found unusable bandwidth {effective_bw}; aborting transfer"
                )
                for lid in path:
                    lid_state = self.link_states.get(lid)
                    if lid_state and transfer in lid_state.active_transfers:
                        lid_state.active_transfers.remove(transfer)
                self._stall_transfer(
                    transfer.dag_id,
                    Edge(
                        from_task=transfer.from_task,
                        to_task=transfer.to_task,
                        data_size=transfer.data_size,
                    ),
                )
                continue

            # Update tracked effective rate for next recalculation
            transfer.current_effective_rate = effective_bw

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

        # Recalculate transfers on interfered links (cross-link effects)
        self._recalculate_interfered_transfers(set(path))

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

    def _handle_link_state_change(self, event: Event) -> None:
        """Handle a link disruption or recovery event.

        Event data:
            change: "link_down" | "link_degrade" | "recovery"
            bandwidth_factor: multiplier for link_degrade (default 1.0)
            duration: if set on link_down/link_degrade, a recovery event is
                scheduled automatically at sim_time + duration

        Semantics:
        - link_down: the link becomes unusable. Every in-flight transfer whose
          path crosses it is aborted; the connection is lost, so the transfer
          is retransmitted from scratch once a route exists again.
        - link_degrade: the link stays up at reduced bandwidth; in-flight
          transfers slow down via the normal recalculation cascade.
        - recovery: the link returns to full bandwidth and stalled transfers
          are retried.

        After the state is applied, the scheduler's on_network_change hook is
        consulted for a repair plan (rescheduling policies plug in there).
        """
        link_id = event.link_id
        change = event.data.get("change")
        link_state = self.link_states.get(link_id)

        if link_state is None:
            logger.error(f"LINK_STATE_CHANGE: link {link_id} not found")
            return

        self._disruptions_enabled = True
        self._routable_network_cache = None  # Topology view changed
        self.routing_model.clear_cache()  # Cached paths may cross this link
        self.disruption_stats["disruptions_applied"] += 1

        if change == "link_down":
            link_state.up = False
            logger.info(f"Link {link_id} DOWN at t={self.sim_time:.6f}")
            self._abort_transfers_on_link(link_id)
        elif change == "link_degrade":
            link_state.bandwidth_factor = float(event.data.get("bandwidth_factor", 1.0))
            logger.info(
                f"Link {link_id} DEGRADED to factor "
                f"{link_state.bandwidth_factor} at t={self.sim_time:.6f}"
            )
            # In-flight transfers survive but slow down.
            self._recalculate_link_transfers(link_id)
        elif change == "recovery":
            link_state.up = True
            link_state.bandwidth_factor = 1.0
            logger.info(f"Link {link_id} RECOVERED at t={self.sim_time:.6f}")
            self._retry_stalled_transfers()
        else:
            logger.error(f"LINK_STATE_CHANGE: unknown change '{change}'")
            return

        # Auto-schedule recovery for transient disruptions.
        duration = event.data.get("duration")
        if duration is not None and change in ("link_down", "link_degrade"):
            self.event_queue.schedule(
                sim_time=self.sim_time + float(duration),
                event_type=EventType.LINK_STATE_CHANGE,
                link_id=link_id,
                data={"change": "recovery"},
            )

        # Cross-link interference may shift when this link's traffic changes.
        self._recalculate_interfered_transfers({link_id})

        # Give the scheduling policy a chance to repair the placement.
        wall_start = time.perf_counter()
        plan = self.scheduler.on_network_change(
            change,
            link_id,
            self.get_network_snapshot(),
            network_state=self.get_network_state(),
        )
        self.repair_wall_time_s += time.perf_counter() - wall_start
        if plan is not None:
            self._schedule_repair(plan)

    def _schedule_repair(self, plan) -> None:
        """Schedule a repair plan's application after its decision latency.

        The plan is computed with time-t knowledge but applied at t + delta,
        where delta = repair_cost_base + repair_cost_per_task * |plan|. The
        old schedule keeps executing in the window, and whatever commits
        meanwhile wins: plan application refuses to move started tasks. A
        plan that arrives while another is pending supersedes it -- the newer
        decision has fresher information.
        """
        delay = round_time(
            self.repair_cost_base
            + self.repair_cost_per_task * len(plan.new_assignments)
        )
        if self._pending_repair_event_id is not None:
            if self.event_queue.cancel(self._pending_repair_event_id):
                self.disruption_stats["repairs_superseded"] += 1
                logger.info(
                    "Pending repair superseded by a newer plan at "
                    f"t={self.sim_time:.6f}"
                )
        self._pending_repair_event_id = self.event_queue.schedule(
            sim_time=self.sim_time + delay,
            event_type=EventType.RESCHEDULE_TRIGGER,
            data={"plan": plan},
        )
        logger.info(
            f"Repair plan ({len(plan.new_assignments)} move(s)) will apply "
            f"at t={self.sim_time + delay:.6f} (delta={delay:.6f})"
        )

    def _handle_reschedule_trigger(self, event: Event) -> None:
        """Apply a repair plan whose decision latency has elapsed."""
        if event.event_id == self._pending_repair_event_id:
            self._pending_repair_event_id = None
        plan = event.data.get("plan")
        if plan is None:
            logger.error("RESCHEDULE_TRIGGER event missing 'plan' data")
            return
        self._apply_reschedule_plan(plan)

    def _resolve_task_key(self, key: str) -> Optional[str]:
        """Resolve a ReschedulePlan task key to a task_states key.

        Accepts fully qualified "dag_id:task_id" keys, or bare task ids when
        they are unambiguous across injected DAGs.
        """
        if key in self.task_states:
            return key
        matches = [k for k in self.task_states if k.split(":", 1)[1] == key]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            logger.error(f"Reschedule key '{key}' is ambiguous across DAGs: {matches}")
        else:
            logger.error(f"Reschedule key '{key}' matches no known task")
        return None

    def _apply_reschedule_plan(self, plan) -> None:
        """Apply a ReschedulePlan: move pending/queued tasks to new nodes.

        The subtlety is data placement. A transfer delivers a parent's output
        to the node the child was assigned to *at delivery time*; when the
        child later moves, that delivery is on the wrong node. So for every
        moved task:

        1. Tasks that started (READY/RUNNING/COMPLETED) never move.
        2. A QUEUED task is pulled out of its node's queue first.
        3. In-flight transfers headed to the task are aborted -- they are
           delivering to the old node.
        4. Its predecessor set is rebuilt from the DAG, and for every parent
           that already COMPLETED the input transfer is re-issued toward the
           new node (parents retain their outputs). Local hand-offs resolve
           immediately; parents still running will ship to the new node when
           they finish, because transfers read assignments at completion time.
        """
        if plan.cancel_tasks:
            logger.warning(
                "ReschedulePlan.cancel_tasks is not supported (no preemption); "
                f"ignoring {plan.cancel_tasks}"
            )

        for key, new_node in plan.new_assignments.items():
            task_key = self._resolve_task_key(key)
            if task_key is None:
                continue
            task_state = self.task_states[task_key]
            dag_id, task_id = task_key.split(":", 1)

            if new_node not in self.node_states:
                logger.error(f"Reschedule of {task_key}: unknown node {new_node}")
                continue
            if task_state.assigned_node == new_node:
                continue  # Already there
            if task_state.status not in (TaskStatus.PENDING, TaskStatus.QUEUED):
                logger.warning(
                    f"Reschedule of {task_key} ignored: status "
                    f"{task_state.status.name} is committed"
                )
                continue

            old_node = task_state.assigned_node
            if task_state.status == TaskStatus.QUEUED:
                removed = self.node_states[old_node].queue.remove(task_state)
                if not removed:
                    logger.error(
                        f"Reschedule of {task_key}: QUEUED but absent from "
                        f"{old_node}'s queue; not moving"
                    )
                    continue

            task_state.assigned_node = new_node
            task_state.status = TaskStatus.PENDING
            task_state.queued_at = None
            self.disruption_stats["tasks_replanned"] += 1
            logger.info(
                f"Repair moved {task_key}: {old_node} -> {new_node} "
                f"at t={self.sim_time:.6f}"
            )

            # Abort in-flight transfers delivering to the old location.
            self._abort_transfers_to_task(dag_id, task_id)

            # Drop stalled deliveries; they are re-issued below.
            self._stalled_transfers = [
                entry
                for entry in self._stalled_transfers
                if not (entry.dag_id == dag_id and entry.edge.to_task == task_id)
            ]

            # Rebuild the input state against the new node. Readiness is
            # driven by the deliveries themselves: a re-issued local hand-off
            # or transfer marks its predecessor complete and fires TASK_READY
            # when it was the last one. Only a true DAG root (no predecessors
            # at all) has no delivery to drive it, so it is fired explicitly.
            dag = self.dags[dag_id]
            predecessors = set(dag.get_predecessors(task_id))
            task_state.predecessors_remaining = set(predecessors)
            if predecessors:
                for edge in dag.get_incoming_edges(task_id):
                    parent_state = self.get_task_state(dag_id, edge.from_task)
                    if parent_state and parent_state.status == TaskStatus.COMPLETED:
                        self._schedule_transfer_start(dag_id, edge)
            else:
                self.event_queue.schedule(
                    sim_time=self.sim_time,
                    event_type=EventType.TASK_READY,
                    dag_id=dag_id,
                    task_id=task_id,
                )

    def _abort_transfers_to_task(self, dag_id: str, task_id: str) -> None:
        """Cancel in-flight transfers delivering to a task that just moved."""
        seen: set = set()
        for link_state in self.link_states.values():
            for transfer in list(link_state.active_transfers):
                if transfer.dag_id != dag_id or transfer.to_task != task_id:
                    continue
                transfer_key = (transfer.dag_id, transfer.from_task, transfer.to_task)
                if transfer_key in seen:
                    continue
                seen.add(transfer_key)
                self.event_queue.cancel(transfer.event_id)
                path = transfer.link_ids if transfer.link_ids else [transfer.link_id]
                for lid in path:
                    lid_state = self.link_states.get(lid)
                    if lid_state and transfer in lid_state.active_transfers:
                        lid_state.active_transfers.remove(transfer)
                for lid in path:
                    self._recalculate_link_transfers(lid)
                logger.debug(
                    f"Aborted in-flight transfer {transfer.from_task}->"
                    f"{transfer.to_task}: destination task moved"
                )

    def _abort_transfers_on_link(self, link_id: str) -> None:
        """Abort every in-flight transfer whose path crosses a downed link.

        A transfer is registered on every link of its path, so scanning the
        downed link's active list finds all transfers that cross it. Each is
        cancelled, removed from all its links, and parked as a stalled
        transfer to be retransmitted in full when a route exists again.
        """
        link_state = self.link_states[link_id]
        # Copy: we mutate active_transfers lists while iterating.
        for transfer in list(link_state.active_transfers):
            self.event_queue.cancel(transfer.event_id)
            path = transfer.link_ids if transfer.link_ids else [transfer.link_id]
            for lid in path:
                other_state = self.link_states.get(lid)
                if other_state and transfer in other_state.active_transfers:
                    other_state.active_transfers.remove(transfer)
            self._stalled_transfers.append(
                StalledTransfer(
                    dag_id=transfer.dag_id,
                    edge=Edge(
                        from_task=transfer.from_task,
                        to_task=transfer.to_task,
                        data_size=transfer.data_size,
                    ),
                    stalled_at=self.sim_time,
                    was_in_flight=True,
                )
            )
            self.disruption_stats["transfers_aborted"] += 1
            logger.info(
                f"Transfer {transfer.from_task}->{transfer.to_task} aborted "
                f"(link {link_id} down); will retransmit in full"
            )
            # Survivors on the other links of the path get the freed bandwidth.
            for lid in path:
                if lid != link_id:
                    self._recalculate_link_transfers(lid)

    def _stall_transfer(self, dag_id: str, edge: Edge) -> None:
        """Park a transfer that has no usable route right now."""
        self._stalled_transfers.append(
            StalledTransfer(dag_id=dag_id, edge=edge, stalled_at=self.sim_time)
        )
        self.disruption_stats["transfers_stalled"] += 1
        logger.info(
            f"Transfer {edge.from_task}->{edge.to_task} stalled: no usable "
            f"route at t={self.sim_time:.6f}"
        )

    def _retry_stalled_transfers(self) -> None:
        """Retry every stalled transfer; those still unroutable stall again."""
        stalled, self._stalled_transfers = self._stalled_transfers, []
        for entry in stalled:
            self.disruption_stats["transfers_resumed"] += 1
            self._schedule_transfer_start(entry.dag_id, entry.edge)
            # _schedule_transfer_start re-stalls (and re-counts) on failure;
            # keep resumed/stalled counters consistent for that case.
            if self._stalled_transfers and self._stalled_transfers[-1].edge is entry.edge:
                self.disruption_stats["transfers_resumed"] -= 1

    def _recalculate_interfered_transfers(self, changed_link_ids: Set[str]) -> None:
        """Recalculate transfers on links affected by interference changes.

        When a transfer starts or completes, nearby links may have their
        interference factor change. This method finds and recalculates those.
        """
        if self.interference_model is None:
            return

        active_link_ids = self._get_active_link_ids()
        affected: Set[str] = set()
        for changed_lid in changed_link_ids:
            affected |= self.interference_model.get_affected_links(
                changed_lid, active_link_ids, self.network
            )

        # Don't recalculate links already handled by the per-path recalc
        affected -= changed_link_ids

        for lid in affected:
            link_state = self.link_states.get(lid)
            if link_state and link_state.active_transfers:
                self._recalculate_link_transfers(lid)

    def get_unfinished_task_count(self) -> int:
        """Count tasks that never completed.

        Nonzero after a run means the workload could not finish -- e.g. a
        permanent link failure left transfers stalled with no route. Surfaced
        in metrics so an incomplete run is never mistaken for a fast one.
        """
        return sum(
            1
            for task_state in self.task_states.values()
            if task_state.status != TaskStatus.COMPLETED
        )

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

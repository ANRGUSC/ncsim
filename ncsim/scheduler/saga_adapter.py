"""SAGA static batch scheduler adapter and registry."""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, TYPE_CHECKING

from ncsim.scheduler.base import Scheduler, PlacementPlan, NetworkSnapshot
from ncsim.models.dag import DAG

if TYPE_CHECKING:
    from typing import Union
    from ncsim.models.routing import WidestPathRouting, ShortestPathRouting

logger = logging.getLogger(__name__)

# Try to import SAGA
try:
    from saga.schedulers import (
        BILScheduler,
        BruteForceScheduler,
        CpopScheduler,
        DPSScheduler,
        DuplexScheduler,
        ETFScheduler,
        FastestNodeScheduler,
        FCPScheduler,
        FLBScheduler,
        GDLScheduler,
        HbmctScheduler,
        HeftScheduler,
        MaxMinScheduler,
        MCTScheduler,
        METScheduler,
        MinMinScheduler,
        MsbcScheduler,
        MSTScheduler,
        OLBScheduler,
        PEFTScheduler,
        SMTScheduler,
        SufferageScheduler,
        WBAScheduler,
    )
    from saga import Network as SagaNetwork
    from saga import TaskGraph, NetworkNode, NetworkEdge, TaskGraphNode, TaskGraphEdge
    SAGA_AVAILABLE = True
    logger.debug("SAGA library loaded successfully")
except ImportError as e:
    SAGA_AVAILABLE = False
    logger.warning(f"SAGA library not available: {e}")


# Constants for SAGA network construction
DISCONNECTED_SPEED = 0.001  # Very slow for non-connected pairs (effectively disconnected)
LOCAL_SPEED = 10000.0  # Very fast for same-node transfers


@dataclass(frozen=True)
class SchedulerOption:
    """A constructor option exposed by a registered SAGA scheduler."""

    name: str
    label: str
    value_type: str
    default: Any
    description: str
    nullable: bool = False
    choices: tuple[Any, ...] = ()
    minimum: Optional[float] = None
    maximum: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "type": self.value_type,
            "default": self.default,
            "description": self.description,
            "nullable": self.nullable,
            "choices": list(self.choices),
            "minimum": self.minimum,
            "maximum": self.maximum,
        }


@dataclass(frozen=True)
class SchedulerRegistration:
    """Metadata and implementation class for a SAGA scheduler."""

    name: str
    label: str
    scheduler_class: Any
    description: str
    options: tuple[SchedulerOption, ...] = field(default_factory=tuple)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "kind": "saga",
            "description": self.description,
            "options": [option.as_dict() for option in self.options],
        }


def _build_saga_registry() -> Dict[str, SchedulerRegistration]:
    if not SAGA_AVAILABLE:
        return {}

    registrations = [
        SchedulerRegistration("bil", "BIL", BILScheduler, "Best Imaginary Level scheduling."),
        SchedulerRegistration("brute_force", "Brute Force", BruteForceScheduler, "Exhaustive optimal schedule search for small problems."),
        SchedulerRegistration("cpop", "CPOP", CpopScheduler, "Critical Path on a Processor scheduling."),
        SchedulerRegistration("dps", "DPS", DPSScheduler, "Dynamic priority scheduling."),
        SchedulerRegistration("duplex", "Duplex", DuplexScheduler, "Selects between complementary list schedules."),
        SchedulerRegistration("etf", "ETF", ETFScheduler, "Earliest Task First scheduling."),
        SchedulerRegistration("fastest_node", "Fastest Node", FastestNodeScheduler, "Places work on the fastest compute node."),
        SchedulerRegistration(
            "fcp", "FCP", FCPScheduler, "Fast Critical Path scheduling.",
            options=(SchedulerOption(
                "priority_queue_size", "Priority queue size", "integer", None,
                "Maximum ready tasks considered at each scheduling step.", nullable=True, minimum=1,
            ),),
        ),
        SchedulerRegistration("flb", "FLB", FLBScheduler, "Fast Load Balancing scheduling."),
        SchedulerRegistration(
            "gdl", "GDL", GDLScheduler, "Generalized Dynamic Level scheduling.",
            options=(SchedulerOption(
                "dynamic_level", "Dynamic level", "integer", 2,
                "Dynamic-level formula variant.", choices=(1, 2),
            ),),
        ),
        SchedulerRegistration("hbmct", "HBMCT", HbmctScheduler, "Heterogeneous Balanced Minimum Completion Time scheduling."),
        SchedulerRegistration("heft", "HEFT", HeftScheduler, "Heterogeneous Earliest Finish Time scheduling."),
        SchedulerRegistration("maxmin", "Max-Min", MaxMinScheduler, "Schedules the task with the largest minimum completion time."),
        SchedulerRegistration("mct", "MCT", MCTScheduler, "Minimum Completion Time scheduling."),
        SchedulerRegistration("met", "MET", METScheduler, "Minimum Execution Time scheduling."),
        SchedulerRegistration("minmin", "Min-Min", MinMinScheduler, "Schedules the task with the smallest minimum completion time."),
        SchedulerRegistration("msbc", "MSBC", MsbcScheduler, "Mean standard-deviation based clustering scheduling."),
        SchedulerRegistration("mst", "MST", MSTScheduler, "Minimum Start Time scheduling."),
        SchedulerRegistration("olb", "OLB", OLBScheduler, "Opportunistic Load Balancing scheduling."),
        SchedulerRegistration("peft", "PEFT", PEFTScheduler, "Predict Earliest Finish Time scheduling."),
        SchedulerRegistration(
            "smt", "SMT", SMTScheduler, "Constraint-solver based scheduling.",
            options=(
                SchedulerOption("epsilon", "Epsilon", "number", 0.001, "Solver comparison tolerance.", minimum=0),
                SchedulerOption("solver_name", "Solver name", "string", None, "Optional solver backend name.", nullable=True),
            ),
        ),
        SchedulerRegistration("sufferage", "Sufferage", SufferageScheduler, "Sufferage heuristic scheduling."),
        SchedulerRegistration(
            "wba", "WBA", WBAScheduler, "Workflow-based allocation scheduling.",
            options=(SchedulerOption(
                "alpha", "Alpha", "number", 0.5,
                "Tradeoff weight used by WBA.", minimum=0, maximum=1,
            ),),
        ),
    ]
    return {registration.name: registration for registration in registrations}


SAGA_SCHEDULERS = _build_saga_registry()
BUILTIN_SCHEDULERS = ("round_robin", "manual")


def available_scheduler_names() -> tuple[str, ...]:
    """Return every scheduler accepted by ncsim."""
    return tuple(SAGA_SCHEDULERS) + BUILTIN_SCHEDULERS


def scheduler_catalog() -> list[Dict[str, Any]]:
    """Return JSON-safe scheduler metadata for CLI and UI consumers."""
    builtins = [
        {
            "name": "round_robin", "label": "Round Robin", "kind": "builtin",
            "description": "Assigns ready tasks cyclically across nodes.", "options": [],
        },
        {
            "name": "manual", "label": "Manual", "kind": "builtin",
            "description": "Uses each task's pinned_to assignment.", "options": [],
        },
    ]
    return [registration.as_dict() for registration in SAGA_SCHEDULERS.values()] + builtins


def _validate_scheduler_options(
    registration: SchedulerRegistration,
    values: Dict[str, Any],
) -> None:
    definitions = {option.name: option for option in registration.options}
    unknown_options = set(values) - set(definitions)
    if unknown_options:
        unknown = ", ".join(sorted(unknown_options))
        raise ValueError(f"Unknown option(s) for scheduler '{registration.name}': {unknown}")

    for name, value in values.items():
        option = definitions[name]
        if value is None:
            if option.nullable:
                continue
            raise ValueError(f"Option '{name}' for scheduler '{registration.name}' cannot be null")

        valid_type = {
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "string": isinstance(value, str),
            "boolean": isinstance(value, bool),
        }[option.value_type]
        if not valid_type:
            raise ValueError(
                f"Option '{name}' for scheduler '{registration.name}' must be {option.value_type}"
            )
        if option.choices and value not in option.choices:
            raise ValueError(
                f"Option '{name}' for scheduler '{registration.name}' must be one of "
                f"{', '.join(map(str, option.choices))}"
            )
        if option.minimum is not None and value < option.minimum:
            raise ValueError(
                f"Option '{name}' for scheduler '{registration.name}' must be at least {option.minimum}"
            )
        if option.maximum is not None and value > option.maximum:
            raise ValueError(
                f"Option '{name}' for scheduler '{registration.name}' must be at most {option.maximum}"
            )


class SagaScheduler(Scheduler):
    """Scheduler using a registered SAGA static batch algorithm.

    SAGA requires a fully-connected network graph. We construct one by:
    - Using LOCAL_SPEED for same-node transfers (essentially instant)
    - Using actual link bandwidth for connected node pairs
    - Using widest-path bandwidth for multi-hop paths (if routing provided)
    - Using DISCONNECTED_SPEED for non-connected pairs (very expensive)

    HEFT will naturally avoid placing communicating tasks on disconnected
    nodes due to the high transfer cost.
    """

    def __init__(
        self,
        algorithm: str = "heft",
        routing: Optional["WidestPathRouting"] = None,
        scheduler_options: Optional[Dict[str, Any]] = None,
    ):
        """Initialize SAGA scheduler.

        Args:
            algorithm: Registered SAGA scheduler name
            routing: Optional WidestPathRouting for multi-hop bandwidth calculation
            scheduler_options: Keyword arguments for the SAGA scheduler constructor
        """
        if not SAGA_AVAILABLE:
            raise RuntimeError("SAGA library not available. Install with: pip install anrg-saga")

        self.algorithm = algorithm.lower()
        self.routing = routing
        self.scheduler_options = dict(scheduler_options or {})
        registration = SAGA_SCHEDULERS.get(self.algorithm)
        if registration is None:
            available = ", ".join(SAGA_SCHEDULERS)
            raise ValueError(f"Unknown SAGA scheduler '{algorithm}'. Available: {available}")

        _validate_scheduler_options(registration, self.scheduler_options)

        try:
            self._scheduler = registration.scheduler_class(**self.scheduler_options)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid options for scheduler '{self.algorithm}': {exc}") from exc

    def on_dag_inject(
        self,
        dag: DAG,
        network_snapshot: NetworkSnapshot
    ) -> PlacementPlan:
        """Schedule DAG using SAGA algorithm.

        Args:
            dag: DAG to schedule
            network_snapshot: Current network state

        Returns:
            PlacementPlan with task assignments
        """
        # Build SAGA network model
        saga_network = self._build_saga_network(network_snapshot)

        # Build SAGA task graph
        saga_taskgraph = self._build_saga_taskgraph(dag)

        # Run SAGA scheduler
        logger.debug(f"Running {self.algorithm.upper()} scheduler")
        schedule = self._scheduler.schedule(saga_network, saga_taskgraph)

        # Extract assignments
        assignments = self._extract_assignments(schedule, network_snapshot)

        # Handle pinned tasks (override SAGA assignments)
        for task_id, task in dag.tasks.items():
            if task.pinned_to and task.pinned_to in network_snapshot.nodes:
                assignments[task_id] = task.pinned_to

        logger.info(f"SAGA {self.algorithm.upper()} assignments: {assignments}")
        return PlacementPlan(
            assignments=assignments,
            metadata={"algorithm": self.algorithm, "scheduler_options": self.scheduler_options}
        )

    def _build_saga_network(self, snapshot: NetworkSnapshot) -> "SagaNetwork":
        """Build SAGA Network from network snapshot.

        SAGA requires a fully-connected graph. We create edges for all
        node pairs with appropriate speeds.

        If widest-path routing is configured, uses widest-path bandwidth
        between all node pairs so HEFT makes better placement decisions.
        """
        node_ids = list(snapshot.nodes.keys())
        num_nodes = len(node_ids)

        # Create node name -> index mapping
        node_idx = {node_id: i for i, node_id in enumerate(node_ids)}

        # Build Network object from snapshot for widest-path calculation
        network_for_routing = None
        if self.routing is not None:
            from ncsim.models.network import Network, Node, Link, Position
            nodes = {
                node_id: Node(
                    id=node_id,
                    compute_capacity=node_snap.compute_capacity,
                    position=Position(0, 0)
                )
                for node_id, node_snap in snapshot.nodes.items()
            }
            links = {
                link_id: Link(
                    id=link_id,
                    from_node=link_snap.from_node,
                    to_node=link_snap.to_node,
                    bandwidth=link_snap.bandwidth,
                    latency=link_snap.latency
                )
                for link_id, link_snap in snapshot.links.items()
            }
            network_for_routing = Network(nodes=nodes, links=links)

        # Build connectivity and speed matrices
        # Use link bandwidth for connected pairs, widest-path bandwidth for
        # multi-hop, DISCONNECTED_SPEED for unreachable pairs
        speed_matrix: Dict[tuple, float] = {}
        for i, src_id in enumerate(node_ids):
            for j, dst_id in enumerate(node_ids):
                if i == j:
                    # Same node = local transfer (very fast)
                    speed_matrix[(src_id, dst_id)] = LOCAL_SPEED
                elif self.routing is not None and network_for_routing is not None:
                    # Use widest-path bandwidth
                    bw = self.routing.get_path_bandwidth(src_id, dst_id, network_for_routing)
                    if bw > 0 and bw != float('inf'):
                        speed_matrix[(src_id, dst_id)] = bw
                    else:
                        speed_matrix[(src_id, dst_id)] = DISCONNECTED_SPEED
                else:
                    # Check for direct link only
                    found_link = False
                    for link in snapshot.links.values():
                        if link.from_node == src_id and link.to_node == dst_id:
                            speed_matrix[(src_id, dst_id)] = link.bandwidth
                            found_link = True
                            break
                    if not found_link:
                        # No direct link = very slow (effectively disconnected)
                        speed_matrix[(src_id, dst_id)] = DISCONNECTED_SPEED

        # Create SAGA network nodes
        # Node speed = compute capacity (SAGA uses this for task cost calculation)
        nodes = set()
        for node_id, node_snap in snapshot.nodes.items():
            nodes.add(NetworkNode(
                name=f"node_{node_idx[node_id]}",
                speed=node_snap.compute_capacity
            ))

        # Create SAGA network edges for all pairs
        edges = set()
        for src_id in node_ids:
            for dst_id in node_ids:
                speed = speed_matrix[(src_id, dst_id)]
                edges.add(NetworkEdge(
                    source=f"node_{node_idx[src_id]}",
                    target=f"node_{node_idx[dst_id]}",
                    speed=speed
                ))

        logger.debug(f"Built SAGA network: {len(nodes)} nodes, {len(edges)} edges")
        return SagaNetwork(nodes=frozenset(nodes), edges=frozenset(edges))

    def _build_saga_taskgraph(self, dag: DAG) -> "TaskGraph":
        """Build SAGA TaskGraph from DAG."""
        # Create task nodes
        task_nodes = set()
        for task in dag.tasks.values():
            task_nodes.add(TaskGraphNode(
                name=task.id,
                cost=float(task.compute_cost)
            ))

        # Create dependency edges
        dep_edges = set()
        for edge in dag.edges:
            dep_edges.add(TaskGraphEdge(
                source=edge.from_task,
                target=edge.to_task,
                size=float(edge.data_size)
            ))

        logger.debug(f"Built SAGA task graph: {len(task_nodes)} tasks, {len(dep_edges)} edges")
        return TaskGraph(tasks=frozenset(task_nodes), dependencies=frozenset(dep_edges))

    def _extract_assignments(
        self,
        schedule,
        snapshot: NetworkSnapshot
    ) -> Dict[str, str]:
        """Extract task -> node_id mapping from SAGA schedule.

        SAGA schedule has a 'mapping' attribute: Dict[node_name, List[ScheduledTask]]
        We need to map back from "node_X" names to actual node IDs.
        """
        node_ids = list(snapshot.nodes.keys())
        assignments = {}

        if schedule is None:
            logger.warning("SAGA schedule is None")
            return assignments

        # SAGA Schedule has mapping: Dict[node_name, List[ScheduledTask]]
        if hasattr(schedule, "mapping"):
            for node_name, scheduled_tasks in schedule.mapping.items():
                node_id = self._parse_node_id(node_name, node_ids)
                if node_id is not None:
                    for task in scheduled_tasks:
                        task_name = getattr(task, "name", None)
                        if task_name:
                            assignments[task_name] = node_id
                            logger.debug(f"  {task_name} -> {node_id}")

        logger.debug(f"Extracted {len(assignments)} assignments")
        return assignments

    def _parse_node_id(self, node_info, node_ids: list) -> Optional[str]:
        """Parse actual node ID from SAGA node name.

        SAGA uses names like "node_0", "node_1". We map index back to actual ID.
        """
        if node_info is None:
            return None

        node_name = str(node_info)

        # Extract index from "node_X" format
        if "node_" in node_name:
            try:
                idx = int(node_name.split("node_")[-1].split("_")[0])
                if 0 <= idx < len(node_ids):
                    return node_ids[idx]
            except (ValueError, IndexError):
                pass

        # Try direct index
        try:
            idx = int(node_name) % len(node_ids)
            return node_ids[idx]
        except (ValueError, TypeError):
            pass

        return None


def create_scheduler(
    algorithm: str = "heft",
    routing: Optional["WidestPathRouting"] = None,
    scheduler_options: Optional[Dict[str, Any]] = None,
) -> Scheduler:
    """Factory function to create a scheduler.

    Args:
        algorithm: Registered SAGA scheduler or built-in scheduler name
        routing: Optional WidestPathRouting for multi-hop bandwidth calculation
        scheduler_options: Keyword arguments for the SAGA scheduler constructor

    Returns:
        Scheduler instance
    """
    algorithm = algorithm.lower()

    if algorithm == "manual":
        if scheduler_options:
            raise ValueError("The manual scheduler does not accept scheduler options")
        from ncsim.scheduler.base import ManualScheduler
        return ManualScheduler()

    if algorithm == "round_robin":
        if scheduler_options:
            raise ValueError("The round_robin scheduler does not accept scheduler options")
        from ncsim.scheduler.base import RoundRobinScheduler
        return RoundRobinScheduler()

    if not SAGA_AVAILABLE:
        raise RuntimeError("SAGA library not available. Install with: pip install anrg-saga")

    return SagaScheduler(
        algorithm=algorithm,
        routing=routing,
        scheduler_options=scheduler_options,
    )

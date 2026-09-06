"""
Main simulation driver.

Orchestrates the discrete event simulation loop.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable

from ncsim.core.event_queue import EventQueue, Event, EventType, round_time
from ncsim.core.execution_engine import ExecutionEngine, UnroutableTransferError
from ncsim.models.task import TaskStatus
from ncsim.core.telemetry import TelemetryCollector, TraceOnlyCollector
from ncsim.models.network import Network
from ncsim.models.dag import DAG, DAGSource, SingleDAGSource
from ncsim.models.routing import RoutingModel
from ncsim.models.interference import InterferenceModel, WirelessOutageError
from ncsim.scheduler.base import Scheduler

logger = logging.getLogger(__name__)


@dataclass
class SimulationResult:
    """Results from a simulation run.

    Attributes:
        makespan: Time of last task completion
        total_events: Number of events processed
        status: completed, unroutable, blocked_wireless, limit_reached, or error
        error_message: Error description if status is "error"
        node_utilization: Per-node utilization (0.0 to 1.0)
        link_utilization: Per-link utilization (0.0 to 1.0)
        metrics: Additional metrics from telemetry
    """
    makespan: float
    total_events: int
    status: str
    error_message: Optional[str] = None
    node_utilization: Dict[str, float] = field(default_factory=dict)
    link_utilization: Dict[str, float] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)


class Simulation:
    """Main simulation driver.

    Coordinates event queue, execution engine, and telemetry.
    """

    def __init__(
        self,
        network: Network,
        scheduler: Scheduler,
        dag_source: Optional[DAGSource] = None,
        telemetry: Optional[TelemetryCollector] = None,
        routing_model: Optional[RoutingModel] = None,
        interference_model: Optional[InterferenceModel] = None,
        seed: int = 42
    ):
        """Initialize simulation.

        Args:
            network: Network topology
            scheduler: Task scheduler
            dag_source: Source of DAGs to inject (optional if using inject_dag)
            telemetry: Telemetry collector (default: TraceOnlyCollector)
            routing_model: Routing model for multi-hop paths (default: DirectLinkRouting)
            interference_model: Optional inter-link interference model
            seed: Random seed for reproducibility
        """
        self.network = network
        self.scheduler = scheduler
        self.dag_source = dag_source
        self.telemetry = telemetry or TraceOnlyCollector()
        self.routing_model = routing_model
        self.interference_model = interference_model
        self.seed = seed

        # Create event queue and execution engine
        self.event_queue = EventQueue()
        self.engine = ExecutionEngine(
            network=network,
            scheduler=scheduler,
            event_queue=self.event_queue,
            routing_model=routing_model,
            interference_model=interference_model
        )

        # Track events for trace
        self._events_processed = 0
        self._event_listeners: List[Callable[[Event], None]] = []

        # Connect telemetry to engine
        self.engine.add_listener(self._on_event)

    def add_event_listener(self, listener: Callable[[Event], None]) -> None:
        """Add a listener for processed events.

        Used by TraceWriter to capture events.
        """
        self._event_listeners.append(listener)

    def _on_event(self, event: Event, engine: ExecutionEngine) -> None:
        """Internal event handler for telemetry and listeners."""
        self._events_processed += 1
        self.telemetry.on_event(event, engine)

        for listener in self._event_listeners:
            listener(event)

    def inject_dag(self, dag: DAG, inject_at: float = 0.0) -> None:
        """Inject a DAG into the simulation.

        Args:
            dag: DAG to inject
            inject_at: Simulation time to inject (default: 0.0)
        """
        self.event_queue.schedule(
            sim_time=inject_at,
            event_type=EventType.DAG_INJECT,
            dag_id=dag.id,
            data={"dag": dag}
        )
        logger.info(f"Scheduled DAG {dag.id} for injection at t={inject_at}")

    def run(self, max_events: Optional[int] = None,
            max_sim_time: Optional[float] = None) -> SimulationResult:
        """Run the simulation until completion.

        Args:
            max_events: Maximum events to process (safety limit)

        Returns:
            SimulationResult with makespan and metrics
        """
        logger.info("Starting simulation")

        # Inject DAGs from source
        if self.dag_source is not None:
            injection = self.dag_source.get_next_injection(0.0)
            while injection is not None:
                inject_time, dag = injection
                self.inject_dag(dag, inject_time)
                injection = self.dag_source.get_next_injection(inject_time + 0.000001)

        if max_events is not None and max_events < 0:
            raise ValueError("max_events must be nonnegative")
        if max_sim_time is not None and max_sim_time < 0:
            raise ValueError("max_sim_time must be nonnegative")
        limit_reached = False
        try:
            while not self.event_queue.is_empty():
                if max_events is not None and self._events_processed >= max_events:
                    logger.warning(f"Reached max events limit: {max_events}")
                    limit_reached = True
                    break

                event = self.event_queue.pop()
                if event is None:
                    break
                if max_sim_time is not None and event.sim_time > max_sim_time:
                    self.engine.sim_time = max_sim_time
                    limit_reached = True
                    break

                self.engine.handle_event(event)

            # Calculate results
            makespan = self.engine.get_makespan()
            status = "completed"
            error_message = None
            if limit_reached:
                status = "limit_reached"
                error_message = "Execution stopped at the configured event/time limit"
            elif any(task.status != TaskStatus.COMPLETED
                     for task in self.engine.task_states.values()):
                active = self.engine._get_active_link_ids()
                status = "blocked_wireless" if active else "error"
                error_message = ("Unfinished backlogged transfers with no future event"
                                 if active else "Unfinished tasks with no future event")

        except UnroutableTransferError as e:
            makespan = self.engine.sim_time
            status = "unroutable"
            error_message = str(e)

        except WirelessOutageError as e:
            logger.warning(f"Simulation stopped by modeled wireless outage: {e}")
            makespan = self.engine.sim_time
            status = "blocked_wireless"
            error_message = str(e)

        except Exception as e:
            logger.exception(f"Simulation error: {e}")
            makespan = self.engine.sim_time
            status = "error"
            error_message = str(e)

        # Collect utilization metrics
        node_utilization = {
            node_id: self.engine.get_node_utilization(node_id)
            for node_id in self.network.nodes
        }

        link_utilization = {
            link_id: self.engine.get_link_utilization(link_id)
            for link_id in self.network.links
        }

        # Finalize telemetry
        telemetry_metrics = self.telemetry.finalize(self.engine)

        logger.info(f"Simulation complete: makespan={makespan:.6f}, events={self._events_processed}")

        return SimulationResult(
            makespan=round_time(makespan),
            total_events=self._events_processed,
            status=status,
            error_message=error_message,
            node_utilization=node_utilization,
            link_utilization=link_utilization,
            metrics=telemetry_metrics
        )

    @property
    def sim_time(self) -> float:
        """Current simulation time."""
        return self.engine.sim_time

    @property
    def events_processed(self) -> int:
        """Number of events processed so far."""
        return self._events_processed


def run_simulation(
    network: Network,
    dag: DAG,
    scheduler: Scheduler,
    seed: int = 42
) -> SimulationResult:
    """Convenience function to run a single-DAG simulation.

    Args:
        network: Network topology
        dag: DAG to simulate
        scheduler: Task scheduler
        seed: Random seed

    Returns:
        SimulationResult
    """
    dag_source = SingleDAGSource(dag)
    sim = Simulation(
        network=network,
        scheduler=scheduler,
        dag_source=dag_source,
        seed=seed
    )
    return sim.run()

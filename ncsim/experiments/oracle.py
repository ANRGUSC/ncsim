"""
Oracle baseline: the best run achievable with the failure trace known upfront.

Truly optimal clairvoyant scheduling against a time-varying network is a
time-expanded scheduling problem and intractable; the standard practice is a
strong, well-defined estimate. This oracle is *best-of-portfolio*: because the
disruption trace makes the network piecewise-static, we build one candidate
placement per network phase (the placement a scheduler would choose if that
phase were the whole story), simulate every candidate against the true trace
with no repairs, add the free-repair reactive run (global scope, zero decision
latency), and report the best valid outcome. Every candidate is something a
clairvoyant scheduler could have chosen, so the envelope is a legitimate
"if you had known" reference; it is an estimate, not the optimum.
"""

import copy
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from ncsim.core.simulation import Simulation, SimulationResult
from ncsim.models.dag import DAG, MultiDAGSource, SingleDAGSource
from ncsim.models.disruptions import (
    DisruptionEvent,
    DisruptionType,
    ScheduledDisruptions,
)
from ncsim.models.network import Link, Network
from ncsim.models.routing import RoutingModel
from ncsim.scheduler.base import (
    NetworkSnapshot,
    PlacementPlan,
    Scheduler,
)
from ncsim.scheduler.saga_adapter import SagaScheduler


def phase_networks(
    network: Network, disruptions: Sequence[DisruptionEvent]
) -> List[Tuple[float, Network]]:
    """Split a disruption trace into piecewise-static network views.

    Applies the trace's link events cumulatively and materializes the
    implicit recoveries carried by event durations, exactly as the engine
    would. Each phase's Network carries the effective bandwidths of that
    interval, with downed links absent.

    Args:
        network: The pristine topology
        disruptions: The link disruption trace

    Returns:
        (start_time, network_view) per phase, in time order, starting with
        the pristine network at t=0 (unless the trace changes it at t=0).
    """
    # Expand into (time, link_id, change, factor) steps, materializing the
    # auto-recovery implied by a duration.
    steps: List[Tuple[float, str, str, float]] = []
    for event in disruptions:
        if event.disruption_type == DisruptionType.LINK_DOWN:
            steps.append((event.time, event.target_id, "down", 0.0))
        elif event.disruption_type == DisruptionType.LINK_DEGRADE:
            factor = float(event.parameters.get("bandwidth_factor", 1.0))
            steps.append((event.time, event.target_id, "degrade", factor))
        elif event.disruption_type == DisruptionType.RECOVERY:
            steps.append((event.time, event.target_id, "recovery", 1.0))
        else:
            raise ValueError(f"Unsupported disruption type: {event.disruption_type}")
        if event.duration is not None and event.disruption_type in (
            DisruptionType.LINK_DOWN,
            DisruptionType.LINK_DEGRADE,
        ):
            steps.append(
                (event.time + event.duration, event.target_id, "recovery", 1.0)
            )
    steps.sort(key=lambda s: (s[0], s[1]))

    def build_view(state: Dict[str, float]) -> Network:
        links = {}
        for link_id, link in network.links.items():
            factor = state[link_id]
            if factor <= 0:
                continue  # Downed links are absent from the view
            links[link_id] = Link(
                id=link_id,
                from_node=link.from_node,
                to_node=link.to_node,
                bandwidth=link.bandwidth * factor,
                latency=link.latency,
            )
        return Network(nodes=network.nodes, links=links, link_model=network.link_model)

    state: Dict[str, float] = {link_id: 1.0 for link_id in network.links}
    phases: List[Tuple[float, Network]] = []
    index = 0
    if not steps or steps[0][0] > 0:
        phases.append((0.0, build_view(state)))
    while index < len(steps):
        time = steps[index][0]
        while index < len(steps) and steps[index][0] == time:
            _, link_id, change, factor = steps[index]
            state[link_id] = 0.0 if change == "down" else factor
            index += 1
        phases.append((time, build_view(state)))
    return phases


class FixedPlacementScheduler(Scheduler):
    """Schedules every DAG with a predetermined placement and never repairs.

    Used to simulate an oracle candidate: the placement was chosen with the
    trace in hand, so the run itself is pure execution.
    """

    def __init__(self, assignments: Dict[str, Dict[str, str]]):
        """Initialize with per-DAG assignments.

        Args:
            assignments: dag_id -> {task_id -> node_id}
        """
        self._assignments = assignments

    def on_dag_inject(
        self, dag: DAG, network_snapshot: NetworkSnapshot
    ) -> PlacementPlan:
        """Return the stored placement for this DAG."""
        stored = self._assignments.get(dag.id)
        if stored is None or set(stored) != set(dag.tasks):
            raise ValueError(
                f"FixedPlacementScheduler has no complete placement for DAG {dag.id}"
            )
        return PlacementPlan(
            assignments=dict(stored), metadata={"algorithm": "fixed"}
        )


@dataclass
class OracleResult:
    """Outcome of an oracle evaluation.

    Attributes:
        label: Which candidate won ("phase[t]" or "reactive-global")
        result: The winning run
        candidates: label -> result for every run in the portfolio
    """
    label: str
    result: SimulationResult
    candidates: Dict[str, SimulationResult] = field(default_factory=dict)


def _run_candidate(
    scheduler: Scheduler,
    network: Network,
    dags: Sequence[DAG],
    disruptions: Sequence[DisruptionEvent],
    routing_model: Optional[RoutingModel],
) -> SimulationResult:
    """Simulate one candidate against the true trace."""
    dags = [copy.deepcopy(dag) for dag in dags]
    dag_source = (
        SingleDAGSource(dags[0]) if len(dags) == 1 else MultiDAGSource(list(dags))
    )
    sim = Simulation(
        network=network,
        scheduler=scheduler,
        dag_source=dag_source,
        routing_model=routing_model,
        disruption_model=ScheduledDisruptions(list(disruptions)),
    )
    return sim.run()


def _is_valid(result: SimulationResult) -> bool:
    return (
        result.status == "completed"
        and result.metrics.get("unfinished_tasks", 0) == 0
    )


def oracle_run(
    network: Network,
    dags: Sequence[DAG],
    disruptions: Sequence[DisruptionEvent],
    algorithm: str = "heft",
    routing_model: Optional[RoutingModel] = None,
    saga_routing=None,
    include_reactive: bool = True,
) -> OracleResult:
    """Evaluate the oracle portfolio and return the best valid run.

    Candidates:
    - One fixed placement per network phase: what the scheduler would choose
      if that phase's network were permanent, executed with no repairs
      (transfers stall and resume through outages).
    - Optionally the reactive free-repair run: global scope, zero decision
      latency, which a clairvoyant scheduler could also emulate.

    The best run is the minimum makespan among candidates that completed all
    tasks; if none did, the least-incomplete candidate is returned so a fully
    severed instance still reports something meaningful.

    Args:
        network: The pristine topology
        dags: Workload DAGs
        disruptions: The failure trace the oracle is allowed to know
        algorithm: SAGA algorithm for candidate placements
        routing_model: ncsim routing model used during execution
        saga_routing: Optional routing passed to the SAGA adapter for
            bandwidth-aware placement (WidestPathRouting)
        include_reactive: Include the free-repair reactive run

    Returns:
        OracleResult with the winning label, its run, and all candidate runs
    """
    planner = SagaScheduler(algorithm=algorithm, routing=saga_routing)
    candidates: Dict[str, Dict[str, Dict[str, str]]] = {}
    for start_time, view in phase_networks(network, disruptions):
        snapshot = NetworkSnapshot.from_network(view, timestamp=start_time)
        per_dag = {
            dag.id: dict(planner.on_dag_inject(dag, snapshot).assignments)
            for dag in dags
        }
        label = f"phase[t={start_time:g}]"
        # Identical placements from different phases collapse into one run.
        if per_dag not in candidates.values():
            candidates[label] = per_dag

    results: Dict[str, SimulationResult] = {}
    for label, per_dag in candidates.items():
        results[label] = _run_candidate(
            FixedPlacementScheduler(per_dag), network, dags, disruptions, routing_model
        )

    if include_reactive:
        from ncsim.scheduler.repair import RepairingSagaScheduler

        results["reactive-global"] = _run_candidate(
            RepairingSagaScheduler(
                algorithm=algorithm, routing=saga_routing, scope="global"
            ),
            network,
            dags,
            disruptions,
            routing_model,
        )

    valid = {label: r for label, r in results.items() if _is_valid(r)}
    if valid:
        best_label = min(valid, key=lambda label: valid[label].makespan)
    else:
        best_label = min(
            results,
            key=lambda label: (
                results[label].metrics.get("unfinished_tasks", float("inf")),
                results[label].makespan,
            ),
        )
    return OracleResult(
        label=best_label, result=results[best_label], candidates=results
    )

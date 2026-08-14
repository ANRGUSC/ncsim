"""
Experiment runner for the schedule-repair study.

The matrix is instances x disruption generators x repair policies (x repair
cost for the policies that pay one). Every instance is normalized by its own
undisrupted makespan M0, and disruption processes are parameterized relative
to M0 so a trace disrupts every instance comparably regardless of its scale.

Policies share the same initial placement (plain SAGA HEFT): "reroute" gets
its multi-hop routing only at execution time, so differences between policies
are attributable to how they respond to failures, never to different starting
schedules.

Repair cost is expressed as a fraction of M0 per moved task and converted to
absolute decision latency per instance, so "0.02" means moving one task costs
2% of the undisrupted makespan across every instance.
"""

import copy
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ncsim.core.simulation import Simulation, SimulationResult
from ncsim.experiments.oracle import oracle_run
from ncsim.experiments.workloads import (
    ALL_STRUCTURES,
    STRUCTURES,
    make_workload,
    scale_network_to_ccr,
    spatial_network,
)
from ncsim.models.dag import DAG, SingleDAGSource
from ncsim.models.disruptions import DisruptionEvent, ScheduledDisruptions
from ncsim.models.failure_traces import (
    gilbert_elliott_trace,
    jammer_targeting,
    jamming_trace,
    mobility_trace,
    radio_pairs,
    single_failure_trace,
)
from ncsim.models.mobility import random_waypoint_trajectory
from ncsim.models.network import Network
from ncsim.models.routing import DirectLinkRouting, WidestPathRouting
from ncsim.scheduler.repair import RepairingSagaScheduler

GENERATORS = ("single", "flapping", "mobility", "jamming")
POLICIES = ("wait", "reroute", "local", "global", "oracle")

# Policies that pay decision latency; the others run once at cost zero.
COSTED_POLICIES = ("local", "global")


@dataclass(frozen=True)
class ExperimentConfig:
    """The experiment matrix and its knobs.

    Attributes:
        structures: DAG structures to instantiate
        instances_per_structure: Instances per structure (seeded 0..n-1)
        num_nodes: Network size
        ccrs: Communication-to-computation ratios; every instance runs once
            per value, with link bandwidths rescaled and disruptions
            re-parameterized against that variant's own M0
        generators: Disruption generators to run
        policies: Repair policies to run
        repair_cost_fracs: Per-moved-task decision latency as a fraction of
            M0; costed policies run once per value
        seed: Master seed; instance seeds derive from it
    """

    structures: Sequence[str] = STRUCTURES
    instances_per_structure: int = 10
    num_nodes: int = 5
    ccrs: Sequence[float] = (1.0,)
    generators: Sequence[str] = GENERATORS
    policies: Sequence[str] = POLICIES
    repair_cost_fracs: Sequence[float] = (0.0,)
    seed: int = 42


def _wait_run(
    network: Network, dag: DAG, trace: Sequence[DisruptionEvent]
) -> SimulationResult:
    """Run the wait policy (no repair, direct routing) against a trace."""
    sim = Simulation(
        network=copy.deepcopy(network),
        scheduler=RepairingSagaScheduler(algorithm="heft", scope="none"),
        dag_source=SingleDAGSource(copy.deepcopy(dag)),
        routing_model=DirectLinkRouting(),
        disruption_model=ScheduledDisruptions(list(trace)),
    )
    return sim.run()


def undisrupted_makespan(network: Network, dag: DAG) -> float:
    """M0: the instance's makespan with no disruptions at all."""
    return _wait_run(network, dag, []).makespan


def build_trace(
    generator: str,
    network: Network,
    m0: float,
    seed: int,
) -> List[DisruptionEvent]:
    """Build one disruption trace, parameterized relative to M0.

    single:   one random radio pair fails at U(0.2, 0.5) * M0 for 0.5 * M0.
    flapping: Gilbert-Elliott on every pair, MTBF 0.75 * M0, MTTR 0.08 * M0
              (short outages arriving without warning), horizon 6 * M0.
    mobility: half the nodes roam a 100x100 area by random waypoint at
              speeds that cross it in about one M0; links run full within
              50 units, die beyond 80, degrade in steps between.
    jamming:  an area jammer at a random pair's midpoint (radius 40, which
              blankets the clustered five-node deployment: a total
              blackout) from 0.25 * M0 for 0.6 * M0.
    """
    rng = random.Random(f"trace:{generator}:{seed}")
    pairs = [tuple(sorted(k)) for k in radio_pairs(network) if len(k) == 2]
    pairs.sort()

    if generator == "single":
        pair = rng.choice(pairs)
        return single_failure_trace(
            network,
            pair,
            time=rng.uniform(0.2, 0.5) * m0,
            duration=0.5 * m0,
        )
    if generator == "flapping":
        return gilbert_elliott_trace(
            network, mtbf=0.75 * m0, mttr=0.08 * m0, horizon=6 * m0, seed=seed
        )
    if generator == "mobility":
        node_ids = sorted(network.nodes)
        mobile = rng.sample(node_ids, k=max(1, len(node_ids) // 2))
        trajectories = {
            node_id: random_waypoint_trajectory(
                area=(0.0, 0.0, 100.0, 100.0),
                speed=(80.0 / m0, 120.0 / m0),
                pause=0.05 * m0,
                horizon=6 * m0,
                seed=rng.randrange(2**31),
                start=(
                    network.nodes[node_id].position.x,
                    network.nodes[node_id].position.y,
                ),
            )
            for node_id in mobile
        }
        return mobility_trace(
            network,
            trajectories,
            horizon=6 * m0,
            dt=m0 / 100.0,
            r_full=50.0,
            r_max=80.0,
        )
    if generator == "jamming":
        pair = rng.choice(pairs)
        jammer = jammer_targeting(
            network, pair, radius=40.0, start=0.25 * m0, duration=0.6 * m0
        )
        return jamming_trace(network, [jammer])
    raise ValueError(f"Unknown generator '{generator}'; expected {GENERATORS}")


def _run_policy(
    policy: str,
    network: Network,
    dag: DAG,
    trace: Sequence[DisruptionEvent],
    repair_cost_per_task: float,
) -> Tuple[SimulationResult, Dict[str, object]]:
    """Run one policy against one instance and trace."""
    extra: Dict[str, object] = {}
    if policy == "oracle":
        oracle = oracle_run(
            copy.deepcopy(network),
            [copy.deepcopy(dag)],
            list(trace),
            routing_model=DirectLinkRouting(),
        )
        extra["oracle_label"] = oracle.label
        return oracle.result, extra

    if policy == "wait":
        scope, routing = "none", DirectLinkRouting()
    elif policy == "reroute":
        scope, routing = "none", WidestPathRouting()
    elif policy in ("local", "global"):
        scope, routing = policy, DirectLinkRouting()
    else:
        raise ValueError(f"Unknown policy '{policy}'; expected {POLICIES}")

    sim = Simulation(
        network=copy.deepcopy(network),
        scheduler=RepairingSagaScheduler(algorithm="heft", scope=scope),
        dag_source=SingleDAGSource(copy.deepcopy(dag)),
        routing_model=routing,
        disruption_model=ScheduledDisruptions(list(trace)),
        repair_cost_per_task=repair_cost_per_task,
    )
    return sim.run(), extra


def run_matrix(
    config: ExperimentConfig,
    progress: Optional[Callable[[str], None]] = None,
    on_record: Optional[Callable[[Dict[str, object]], None]] = None,
) -> List[Dict[str, object]]:
    """Run the full experiment matrix and return one record per run.

    Every record carries the instance identity, the policy and its cost, the
    absolute and M0-normalized makespan, completion, and the disruption
    counters, so downstream analysis needs no re-simulation.

    on_record is called with each record as it is produced, so callers can
    checkpoint long runs incrementally instead of only at the end.
    """
    records: List[Dict[str, object]] = []
    say = progress or (lambda _msg: None)

    for structure in config.structures:
        for index in range(config.instances_per_structure):
            # Structure enters the instance identity via the generator seeds
            # (which include structure-derived strings), not via this integer.
            seed = config.seed * 10_000 + index
            instance = f"{structure}-{index}"
            dag = make_workload(structure, seed=seed)

            for ccr in config.ccrs:
              network = spatial_network(config.num_nodes, seed=seed)
              scale_network_to_ccr(network, dag, ccr)
              m0 = undisrupted_makespan(network, dag)
              say(f"{instance} ccr={ccr:g}: M0={m0:.3f}")

              for generator in config.generators:
                 trace = build_trace(generator, network, m0, seed=seed)
                 for policy in config.policies:
                     cost_fracs = (
                         config.repair_cost_fracs
                         if policy in COSTED_POLICIES
                         else (0.0,)
                     )
                     for cost_frac in cost_fracs:
                         result, extra = _run_policy(
                             policy, network, dag, trace, cost_frac * m0
                         )
                         disruptions = result.metrics.get("disruptions", {})
                         unfinished = result.metrics.get("unfinished_tasks", 0)
                         records.append(
                             {
                                 "instance": instance,
                                 "ccr": ccr,
                                 "structure": structure,
                                 "seed": seed,
                                 "generator": generator,
                                 "policy": policy,
                                 "repair_cost_frac": cost_frac,
                                 "m0": m0,
                                 "makespan": result.makespan,
                                 "norm_makespan": (
                                     result.makespan / m0 if m0 > 0 else None
                                 ),
                                 "completed": unfinished == 0
                                 and result.status == "completed",
                                 "unfinished": unfinished,
                                 "tasks_total": len(dag.tasks),
                                 "replanned": disruptions.get("tasks_replanned", 0),
                                 "aborted": disruptions.get("transfers_aborted", 0),
                                 "stalled": disruptions.get("transfers_stalled", 0),
                                 "superseded": disruptions.get(
                                     "repairs_superseded", 0
                                 ),
                                 "repair_wall_s": result.metrics.get(
                                     "repair_wall_time_s", 0.0
                                 ),
                                 **extra,
                             }
                         )
                         if on_record is not None:
                             on_record(records[-1])
                 say(f"{instance}/{generator}: done")
    return records


def save_records(records: List[Dict[str, object]], path: Path) -> None:
    """Write records as JSON lines."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


def load_records(path: Path) -> List[Dict[str, object]]:
    """Read records written by save_records."""
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]

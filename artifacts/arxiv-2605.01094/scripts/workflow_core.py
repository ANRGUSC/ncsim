"""Study execution helpers extracted without computational changes."""
from __future__ import annotations
import copy
import time
from dataclasses import dataclass
from ncsim.core.simulation import Simulation
from ncsim.models.dag import DAG, Edge, SingleDAGSource
from ncsim.models.task import Task
from ncsim.models.routing import MinimumHopRouting, WidestPathRouting
from ncsim.models.wifi import RFConfig
from ncsim.models.wireless import configure_wireless
from ncsim.scheduler.saga_adapter import create_scheduler
HEADLINE_MODES = ('solo_80211', 'full_wireless')
SCHEDULERS = ('heft', 'cpop', 'round_robin')
@dataclass
class Case:
    case_id: str
    topology_family: str
    topology_seed: int
    topology_metadata: dict
    network: object
    workload_family: str
    workload_seed: int
    dag: DAG
    routing: str = "minimum_hop"


def _routing(name: str):
    if name == "minimum_hop":
        return MinimumHopRouting()
    if name == "widest_path":
        return WidestPathRouting()
    raise ValueError(f"Unknown routing metric: {name}")


def run_case(
    case: Case,
    modes: tuple[str, ...] = HEADLINE_MODES,
    schedulers: tuple[str, ...] = SCHEDULERS,
    rf: RFConfig | None = None,
    components: str = "combined",
    outage_floor_factor: float | None = None,
    ablation_id: str | None = None,
) -> list[dict]:
    records = []
    for mode in modes:
        configured_network = copy.deepcopy(case.network)
        setup = configure_wireless(
            configured_network,
            mode,
            rf_config=rf,
            seed=case.topology_seed,
            components=components,
            outage_floor_factor=outage_floor_factor,
        )
        for scheduler_name in schedulers:
            network, local_setup = copy.deepcopy((configured_network, setup))
            routing = _routing(case.routing)
            scheduler = create_scheduler(
                scheduler_name,
                routing=routing,
                conflict_graph=local_setup.conflict_graph,
                wireless_model=local_setup.interference_model,
            )
            dag = copy.deepcopy(case.dag)
            simulation = Simulation(
                network=network,
                scheduler=scheduler,
                dag_source=SingleDAGSource(dag),
                routing_model=routing,
                interference_model=local_setup.interference_model,
                seed=case.workload_seed,
            )
            started = time.perf_counter()
            result = simulation.run()
            elapsed = time.perf_counter() - started
            placement = simulation.engine.placement_plans.get(dag.id)
            remote_bytes = 0
            byte_hops = 0
            if placement is not None:
                for edge in dag.edges:
                    src, dst = (placement.assignments[task]
                                for task in (edge.from_task, edge.to_task))
                    if src != dst:
                        remote_bytes += edge.data_size * 1_000_000
                        path = routing.get_path(src, dst, network)
                        if path is not None:
                            byte_hops += edge.data_size * 1_000_000 * len(path)
            records.append({
                "schema_version": 2,
                "case_id": case.case_id,
                "ablation_id": ablation_id,
                "topology_family": case.topology_family,
                "topology_seed": case.topology_seed,
                "topology_metadata": case.topology_metadata,
                "workload_family": case.workload_family,
                "workload_seed": case.workload_seed,
                "n_tasks": len(dag.tasks),
                "n_dependencies": len(dag.edges),
                "routing": case.routing,
                "scheduler": scheduler_name,
                "wireless_mode_requested": mode,
                "wireless_mode_canonical": local_setup.canonical_mode,
                "wireless_components": components,
                "outage_floor_factor": outage_floor_factor,
                "status": result.status,
                "error_message": result.error_message,
                "makespan_s": result.makespan if result.status == "completed" else None,
                "total_events": result.total_events,
                "wall_time_s": elapsed,
                "occupied_nodes": len(set(placement.assignments.values())) if placement else None,
                "remote_payload_bytes": remote_bytes,
                "byte_hops": byte_hops,
                "served_byte_hops": 1_000_000 * sum(
                    state.total_data_transferred for state in simulation.engine.link_states.values()),
                "placement": placement.assignments if placement else None,
                "wireless_metadata": local_setup.metadata,
            })
    return records
def _build_dag(dag_id: str, tasks: list[dict], edges: list[dict]) -> DAG:
    return DAG(
        id=dag_id,
        tasks={
            task["id"]: Task(
                id=task["id"],
                compute_cost=float(task["compute_cost"]),
                dag_id=dag_id,
            )
            for task in tasks
        },
        edges=[
            Edge(
                from_task=edge["from"],
                to_task=edge["to"],
                data_size=float(edge["data_size"]),
            )
            for edge in edges
        ],
    )

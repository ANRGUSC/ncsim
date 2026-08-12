"""
Workload and network instance generation for the repair experiments.

DAG structures come from SAGA's synthetic generators (out-trees, in-trees,
parallel chains) with seeded weight functions, converted to ncsim DAGs.
Networks are spatial: nodes at seeded positions (mobility and jamming need
geometry), every pair joined by a bidirectional radio link, and bandwidths
scaled to hit a target communication-to-computation ratio so the network
actually matters to the schedule.
"""

import random
from typing import Dict, List, Optional, Tuple

from ncsim.models.dag import DAG, Edge
from ncsim.models.network import Link, Network, Node, Position
from ncsim.models.task import Task

try:
    from saga import TaskGraph as SagaTaskGraph
    from saga.schedulers.data.random import (
        gen_in_trees,
        gen_out_trees,
        gen_parallel_chains,
    )
    SAGA_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without saga
    SAGA_AVAILABLE = False

STRUCTURES = ("out_tree", "in_tree", "parallel_chains")


def saga_taskgraph_to_dag(task_graph: "SagaTaskGraph", dag_id: str) -> DAG:
    """Convert a SAGA TaskGraph to an ncsim DAG.

    SAGA task costs map to compute_cost and dependency sizes to data_size.
    Zero-cost super source/sink nodes added by SAGA to normalize multi-root
    graphs convert as ordinary zero-cost tasks.
    """
    tasks = {
        task.name: Task(id=task.name, compute_cost=float(task.cost), dag_id=dag_id)
        for task in task_graph.tasks
    }
    edges = [
        Edge(
            from_task=dep.source,
            to_task=dep.target,
            data_size=float(dep.size),
        )
        for dep in sorted(task_graph.dependencies, key=lambda d: (d.source, d.target))
    ]
    return DAG(id=dag_id, tasks=tasks, edges=edges)


def synthetic_dag(structure: str, seed: int, dag_id: str = "dag_1") -> DAG:
    """Generate one synthetic DAG of the given structure, deterministically.

    Task costs and dependency sizes are uniform in [0.5, 1.5) from a seeded
    stream, so instances differ by seed but never by process.

    Args:
        structure: One of STRUCTURES
        seed: Instance seed
        dag_id: DAG identifier

    Returns:
        The ncsim DAG
    """
    if not SAGA_AVAILABLE:
        raise RuntimeError("SAGA is required for synthetic workloads")
    rng = random.Random(f"dag:{structure}:{seed}")

    def task_weight(_node) -> float:
        return rng.uniform(0.5, 1.5)

    def dependency_weight(_src, _dst) -> float:
        return rng.uniform(0.5, 1.5)

    if structure == "out_tree":
        graph = gen_out_trees(
            num=1, num_levels=3, branching_factor=2,
            get_task_weight=task_weight, get_dependency_weight=dependency_weight,
        )[0]
    elif structure == "in_tree":
        graph = gen_in_trees(
            num=1, num_levels=3, branching_factor=2,
            get_task_weight=task_weight, get_dependency_weight=dependency_weight,
        )[0]
    elif structure == "parallel_chains":
        graph = gen_parallel_chains(
            num=1, num_chains=3, chain_length=4,
            get_task_weight=task_weight, get_dependency_weight=dependency_weight,
        )[0]
    else:
        raise ValueError(f"Unknown structure '{structure}'; expected {STRUCTURES}")
    return saga_taskgraph_to_dag(graph, dag_id)


def spatial_network(
    num_nodes: int,
    seed: int,
    area: Tuple[float, float] = (100.0, 100.0),
    cluster: Tuple[float, float, float, float] = (35.0, 35.0, 65.0, 65.0),
    capacity: Tuple[float, float] = (0.5, 1.5),
    bandwidth: float = 1.0,
) -> Network:
    """A spatial full-mesh radio network with seeded positions and capacities.

    Nodes start inside a central cluster (so every radio pair opens in range
    under the mobility model's thresholds) and carry heterogeneous compute
    capacities. Every pair gets a bidirectional radio link at a uniform
    bandwidth; scale_network_to_ccr then sets the bandwidth that makes the
    target CCR hold.

    Args:
        num_nodes: Number of nodes
        seed: Instance seed
        area: Overall area (informational; mobility patterns roam it)
        cluster: (x_min, y_min, x_max, y_max) box for initial positions
        capacity: (min, max) uniform compute capacity
        bandwidth: Initial bandwidth for every link

    Returns:
        The network
    """
    rng = random.Random(f"net:{seed}")
    nodes = {}
    for i in range(num_nodes):
        nodes[f"n{i}"] = Node(
            id=f"n{i}",
            compute_capacity=rng.uniform(*capacity),
            position=Position(
                rng.uniform(cluster[0], cluster[2]),
                rng.uniform(cluster[1], cluster[3]),
            ),
        )
    links = {}
    ids = sorted(nodes)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            links[f"l_{a}_{b}"] = Link(
                id=f"l_{a}_{b}", from_node=a, to_node=b, bandwidth=bandwidth
            )
            links[f"l_{b}_{a}"] = Link(
                id=f"l_{b}_{a}", from_node=b, to_node=a, bandwidth=bandwidth
            )
    return Network(nodes=nodes, links=links)


def scale_network_to_ccr(network: Network, dag: DAG, ccr: float) -> None:
    """Scale every link bandwidth so mean comm time = ccr * mean comp time.

    CCR is the knob that makes the network matter: at ccr << 1 placement is
    compute-bound and failures barely register; around 1 the trade-off is
    live. Mutates the network's links in place.

    Args:
        network: The network to scale
        dag: The workload whose costs define the ratio
        ccr: Target communication-to-computation ratio

    Raises:
        ValueError: If the DAG has no positive-size edges or ccr <= 0
    """
    if ccr <= 0:
        raise ValueError("ccr must be positive")
    sizes = [edge.data_size for edge in dag.edges if edge.data_size > 0]
    if not sizes:
        raise ValueError("DAG has no positive-size edges; CCR is undefined")
    mean_capacity = sum(n.compute_capacity for n in network.nodes.values()) / len(
        network.nodes
    )
    costs = [t.compute_cost for t in dag.tasks.values() if t.compute_cost > 0]
    mean_comp_time = (sum(costs) / len(costs)) / mean_capacity
    mean_size = sum(sizes) / len(sizes)
    target_bandwidth = mean_size / (ccr * mean_comp_time)
    for link in network.links.values():
        link.bandwidth = target_bandwidth

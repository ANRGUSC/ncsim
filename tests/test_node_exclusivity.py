"""Regression test: a node never executes two tasks at once.

The race: at a TASK_COMPLETE the engine dequeued the next task and scheduled
its TASK_START without claiming the node, so a TASK_READY at the same instant
saw the node idle and started a second task alongside it. Both ran
concurrently -- silently understating makespans whenever a queued task and a
newly-ready task collided at a completion instant.
"""

import pytest

from ncsim.core.simulation import Simulation
from ncsim.models.dag import DAG, Edge, SingleDAGSource
from ncsim.models.network import Link, Network, Node
from ncsim.models.routing import DirectLinkRouting
from ncsim.models.task import Task
from ncsim.scheduler.base import ManualScheduler


def assert_node_exclusive(sim: Simulation) -> None:
    """No two tasks on one node may have overlapping execution windows."""
    by_node = {}
    for task_state in sim.engine.task_states.values():
        if task_state.started_at is None:
            continue
        by_node.setdefault(task_state.assigned_node, []).append(
            (task_state.started_at, task_state.completed_at, task_state.task_id)
        )
    for node, spans in by_node.items():
        spans.sort()
        for (s1, e1, t1), (s2, e2, t2) in zip(spans, spans[1:]):
            assert e1 is not None and s2 >= e1 - 1e-9, (
                f"{t1} [{s1}, {e1}] and {t2} [{s2}, {e2}] overlap on {node}"
            )


def test_dequeue_and_same_instant_ready_do_not_double_start():
    """Minimal reproduction of the race.

    One node. A and B are roots: A starts at 0, B queues behind it. C is A's
    local child, so C becomes READY at the exact instant A completes -- the
    same instant B is dequeued. Before the fix, B and C ran concurrently and
    the makespan came out at 2.0; serialized correctly it is 3.0.
    """
    network = Network(
        nodes={"n0": Node(id="n0", compute_capacity=1)},
        links={},
    )
    tasks = {
        "A": Task(id="A", compute_cost=1, dag_id="d", pinned_to="n0"),
        "B": Task(id="B", compute_cost=1, dag_id="d", pinned_to="n0"),
        "C": Task(id="C", compute_cost=1, dag_id="d", pinned_to="n0"),
    }
    dag = DAG(id="d", tasks=tasks, edges=[Edge(from_task="A", to_task="C", data_size=1)])

    sim = Simulation(
        network=network,
        scheduler=ManualScheduler(),
        dag_source=SingleDAGSource(dag),
        routing_model=DirectLinkRouting(),
    )
    result = sim.run()

    assert_node_exclusive(sim)
    assert result.makespan == pytest.approx(3.0)


def test_wide_fan_out_stays_exclusive():
    """Many same-instant readiness collisions on few nodes."""
    network = Network(
        nodes={
            "n0": Node(id="n0", compute_capacity=1),
            "n1": Node(id="n1", compute_capacity=1),
        },
        links={
            "l01": Link(id="l01", from_node="n0", to_node="n1", bandwidth=100),
            "l10": Link(id="l10", from_node="n1", to_node="n0", bandwidth=100),
        },
    )
    tasks = {"root": Task(id="root", compute_cost=1, dag_id="d", pinned_to="n0")}
    edges = []
    for i in range(6):
        node = "n0" if i % 2 == 0 else "n1"
        tasks[f"P{i}"] = Task(id=f"P{i}", compute_cost=1, dag_id="d", pinned_to=node)
        edges.append(Edge(from_task="root", to_task=f"P{i}", data_size=0.001))
    dag = DAG(id="d", tasks=tasks, edges=edges)

    sim = Simulation(
        network=network,
        scheduler=ManualScheduler(),
        dag_source=SingleDAGSource(dag),
        routing_model=DirectLinkRouting(),
    )
    result = sim.run()

    assert_node_exclusive(sim)
    # 1 (root) + 3 tasks serialized per node.
    assert result.makespan == pytest.approx(4.0, abs=0.01)

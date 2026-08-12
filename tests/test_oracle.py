"""Tests for the oracle baseline (best-of-portfolio with the trace known)."""

import pytest

from ncsim.experiments import (
    FixedPlacementScheduler,
    oracle_run,
    phase_networks,
)
from ncsim.models.dag import DAG, Edge
from ncsim.models.disruptions import DisruptionEvent, DisruptionType
from ncsim.models.network import Link, Network, Node
from ncsim.models.routing import DirectLinkRouting
from ncsim.models.task import Task
from ncsim.scheduler.saga_adapter import SAGA_AVAILABLE

pytestmark = pytest.mark.skipif(not SAGA_AVAILABLE, reason="SAGA not installed")


def make_network() -> Network:
    """Two nodes joined by a bidirectional radio pair."""
    nodes = {f"n{i}": Node(id=f"n{i}", compute_capacity=100) for i in range(2)}
    links = {
        "l01": Link(id="l01", from_node="n0", to_node="n1", bandwidth=100),
        "l10": Link(id="l10", from_node="n1", to_node="n0", bandwidth=100),
    }
    return Network(nodes=nodes, links=links)


def make_fan_out_dag() -> DAG:
    """root fans out to two heavy tasks that join (small transfer edges)."""
    tasks = {
        "root": Task(id="root", compute_cost=10, dag_id="dag_1"),
        "P1": Task(id="P1", compute_cost=100, dag_id="dag_1"),
        "P2": Task(id="P2", compute_cost=100, dag_id="dag_1"),
        "join": Task(id="join", compute_cost=10, dag_id="dag_1"),
    }
    edges = [
        Edge(from_task="root", to_task="P1", data_size=1),
        Edge(from_task="root", to_task="P2", data_size=1),
        Edge(from_task="P1", to_task="join", data_size=1),
        Edge(from_task="P2", to_task="join", data_size=1),
    ]
    return DAG(id="dag_1", tasks=tasks, edges=edges)


def pair_down(time: float, duration=None) -> list:
    return [
        DisruptionEvent(
            time=time,
            target_type="link",
            target_id=link_id,
            disruption_type=DisruptionType.LINK_DOWN,
            duration=duration,
        )
        for link_id in ("l01", "l10")
    ]


class TestPhaseNetworks:
    def test_no_disruptions_yields_one_pristine_phase(self):
        phases = phase_networks(make_network(), [])
        assert len(phases) == 1
        assert phases[0][0] == 0.0
        assert set(phases[0][1].links) == {"l01", "l10"}

    def test_transient_failure_yields_three_phases(self):
        """down at 1.0 for 2.0 -> pristine, severed, recovered."""
        phases = phase_networks(make_network(), pair_down(1.0, duration=2.0))
        assert [t for t, _ in phases] == [0.0, 1.0, 3.0]
        assert set(phases[0][1].links) == {"l01", "l10"}
        assert set(phases[1][1].links) == set()
        assert set(phases[2][1].links) == {"l01", "l10"}

    def test_degrade_scales_bandwidth_in_the_view(self):
        degrade = [
            DisruptionEvent(
                time=1.0,
                target_type="link",
                target_id="l01",
                disruption_type=DisruptionType.LINK_DEGRADE,
                parameters={"bandwidth_factor": 0.25},
            )
        ]
        phases = phase_networks(make_network(), degrade)
        assert phases[1][1].links["l01"].bandwidth == pytest.approx(25.0)
        assert phases[1][1].links["l10"].bandwidth == pytest.approx(100.0)

    def test_simultaneous_events_form_one_phase(self):
        phases = phase_networks(make_network(), pair_down(1.0))
        assert [t for t, _ in phases] == [0.0, 1.0]


class TestFixedPlacementScheduler:
    def test_returns_the_stored_placement(self):
        from ncsim.scheduler.base import NetworkSnapshot

        dag = make_fan_out_dag()
        placement = {task_id: "n0" for task_id in dag.tasks}
        scheduler = FixedPlacementScheduler({"dag_1": placement})
        snapshot = NetworkSnapshot.from_network(make_network())
        assert scheduler.on_dag_inject(dag, snapshot).assignments == placement

    def test_incomplete_placement_is_rejected(self):
        from ncsim.scheduler.base import NetworkSnapshot

        scheduler = FixedPlacementScheduler({"dag_1": {"root": "n0"}})
        snapshot = NetworkSnapshot.from_network(make_network())
        with pytest.raises(ValueError, match="no complete placement"):
            scheduler.on_dag_inject(make_fan_out_dag(), snapshot)


class TestOracleRun:
    def test_oracle_completes_a_permanently_severed_instance(self):
        """The severed-phase candidate places everything on one node and the
        workload completes with zero repairs: 0.1 + 1 + 1 + 0.1 = 2.2."""
        oracle = oracle_run(
            make_network(),
            [make_fan_out_dag()],
            pair_down(0.05),
            routing_model=DirectLinkRouting(),
        )
        assert oracle.result.metrics["unfinished_tasks"] == 0
        assert oracle.result.makespan == pytest.approx(2.2)

    def test_oracle_is_no_worse_than_reactive_global_repair(self):
        """The reactive run is in the portfolio, so the envelope can only be
        at least as good."""
        oracle = oracle_run(
            make_network(),
            [make_fan_out_dag()],
            pair_down(0.05, duration=5.0),
            routing_model=DirectLinkRouting(),
        )
        reactive = oracle.candidates["reactive-global"]
        assert oracle.result.makespan <= reactive.makespan

    def test_oracle_on_a_clean_run_matches_plain_heft(self):
        """With no disruptions the portfolio is the pristine placement and
        the reactive run; both are ordinary HEFT executions."""
        oracle = oracle_run(
            make_network(),
            [make_fan_out_dag()],
            [],
            routing_model=DirectLinkRouting(),
        )
        assert oracle.result.metrics.get("unfinished_tasks", 0) == 0
        for result in oracle.candidates.values():
            assert oracle.result.makespan <= result.makespan

    def test_all_candidates_are_reported(self):
        oracle = oracle_run(
            make_network(),
            [make_fan_out_dag()],
            pair_down(1.0, duration=2.0),
            routing_model=DirectLinkRouting(),
        )
        assert "reactive-global" in oracle.candidates
        assert any(label.startswith("phase[") for label in oracle.candidates)
        assert oracle.label in oracle.candidates

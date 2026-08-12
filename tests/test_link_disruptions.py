"""
Integration tests for link disruptions in the execution engine.

Fixture geometry (used throughout): a line topology

    n0 --l01-- n1 --l12-- n2      (plus l02 in the triangle variants)

with T0 pinned to n0 and T1 pinned to n1, connected by a 100 MB edge over
100 MB/s links, so the baseline timeline is exact and easy to reason about:

    T0 runs 0->1, transfer 1->2 on l01, T1 runs 2->3, makespan 3.0
"""

import pytest

from ncsim.core.simulation import Simulation
from ncsim.models.dag import DAG, Edge, SingleDAGSource
from ncsim.models.disruptions import (
    DisruptionEvent,
    DisruptionType,
    ScheduledDisruptions,
)
from ncsim.models.network import Link, Network, Node
from ncsim.models.routing import DirectLinkRouting, WidestPathRouting
from ncsim.models.task import Task
from ncsim.scheduler.base import ManualScheduler


def make_network(triangle: bool = False) -> Network:
    """Line topology n0--n1--n2; `triangle` adds the n0--n2 detour link."""
    nodes = {
        "n0": Node(id="n0", compute_capacity=100),
        "n1": Node(id="n1", compute_capacity=100),
        "n2": Node(id="n2", compute_capacity=100),
    }
    links = {
        "l01": Link(id="l01", from_node="n0", to_node="n1", bandwidth=100),
        "l12": Link(id="l12", from_node="n1", to_node="n2", bandwidth=100),
    }
    if triangle:
        links["l02"] = Link(id="l02", from_node="n0", to_node="n2", bandwidth=100)
        links["l21"] = Link(id="l21", from_node="n2", to_node="n1", bandwidth=100)
    return Network(nodes=nodes, links=links)


def make_dag() -> DAG:
    """T0 on n0 feeds T1 on n1 with a 100 MB result."""
    tasks = {
        "T0": Task(id="T0", compute_cost=100, dag_id="dag_1", pinned_to="n0"),
        "T1": Task(id="T1", compute_cost=100, dag_id="dag_1", pinned_to="n1"),
    }
    edges = [Edge(from_task="T0", to_task="T1", data_size=100)]
    return DAG(id="dag_1", tasks=tasks, edges=edges)


def link_down(time: float, link: str, duration=None) -> DisruptionEvent:
    return DisruptionEvent(
        time=time,
        target_type="link",
        target_id=link,
        disruption_type=DisruptionType.LINK_DOWN,
        duration=duration,
    )


def run_with_disruptions(disruptions, network=None, routing=None):
    """Run the fixture DAG with the given disruption list."""
    sim = Simulation(
        network=network or make_network(),
        scheduler=ManualScheduler(),
        dag_source=SingleDAGSource(make_dag()),
        routing_model=routing or DirectLinkRouting(),
        disruption_model=ScheduledDisruptions(disruptions),
    )
    return sim


class TestBaseline:
    """The disruption machinery must not perturb undisrupted runs."""

    def test_empty_disruption_model_matches_baseline(self):
        without = Simulation(
            network=make_network(),
            scheduler=ManualScheduler(),
            dag_source=SingleDAGSource(make_dag()),
            routing_model=DirectLinkRouting(),
        ).run()
        with_empty = run_with_disruptions([]).run()
        assert without.makespan == pytest.approx(3.0)
        assert with_empty.makespan == pytest.approx(without.makespan)

    def test_disruption_runs_are_deterministic(self):
        events = [link_down(1.5, "l01", duration=2.0)]
        first = run_with_disruptions(list(events)).run()
        second = run_with_disruptions(list(events)).run()
        assert first.makespan == pytest.approx(second.makespan)
        assert first.total_events == second.total_events


class TestLinkDownSemantics:
    def test_failure_before_transfer_stalls_until_recovery(self):
        """Down before the transfer starts: it waits out the outage.

        Down [0.5, 2.5]; the transfer wants to start at 1.0 but has no route,
        so it starts at recovery: 2.5->3.5, T1 3.5->4.5.
        """
        result = run_with_disruptions([link_down(0.5, "l01", duration=2.0)]).run()
        assert result.makespan == pytest.approx(4.5)
        assert result.metrics["disruptions"]["transfers_stalled"] == 1
        assert result.metrics["disruptions"]["transfers_aborted"] == 0
        assert result.metrics["unfinished_tasks"] == 0

    def test_failure_mid_transfer_aborts_and_retransmits_in_full(self):
        """Down mid-transfer: partial progress is lost, not resumed.

        The transfer runs 1.0->2.0; down at 1.5 kills it half-done. At
        recovery (3.5) it retransmits all 100 MB: 3.5->4.5, T1 4.5->5.5.
        A resume-from-half semantics would instead finish at 4.0 and give
        makespan 5.0 -- the assertion below distinguishes the two.
        """
        result = run_with_disruptions([link_down(1.5, "l01", duration=2.0)]).run()
        assert result.makespan == pytest.approx(5.5)
        assert result.metrics["disruptions"]["transfers_aborted"] == 1

    def test_degrade_slows_inflight_transfer_without_aborting(self):
        """Degrade to half bandwidth mid-transfer: 50 MB remain at 50 MB/s.

        Transfer 1.0->? : full rate until 1.5 (50 MB done), then 50 MB at
        50 MB/s finishes at 2.5. T1 runs 2.5->3.5.
        """
        degrade = DisruptionEvent(
            time=1.5,
            target_type="link",
            target_id="l01",
            disruption_type=DisruptionType.LINK_DEGRADE,
            parameters={"bandwidth_factor": 0.5},
        )
        result = run_with_disruptions([degrade]).run()
        assert result.makespan == pytest.approx(3.5)
        assert result.metrics["disruptions"]["transfers_aborted"] == 0

    def test_permanent_failure_with_no_route_leaves_unfinished_tasks(self):
        """No recovery and no detour: the run drains instead of hanging,
        and the incompleteness is reported rather than hidden."""
        result = run_with_disruptions([link_down(0.5, "l01")]).run()
        assert result.status == "completed"  # The event loop drained cleanly
        assert result.metrics["unfinished_tasks"] == 1
        assert result.makespan == pytest.approx(1.0)  # Only T0 finished


class TestReroutingAroundFailure:
    def test_transfer_routes_around_a_downed_link(self):
        """With a triangle and multi-hop routing, a permanent l01 failure
        forces the n0->n2->n1 detour and the workload still completes."""
        result = run_with_disruptions(
            [link_down(0.5, "l01")],
            network=make_network(triangle=True),
            routing=WidestPathRouting(),
        ).run()
        assert result.metrics["unfinished_tasks"] == 0
        # Two-hop path at the same bandwidth: transfer still takes 1s once
        # it starts; it stalls only if the failure raced it (it starts at 1.0,
        # failure hit at 0.5, so routing already avoids l01).
        assert result.makespan == pytest.approx(3.0)

    def test_direct_routing_cannot_reroute(self):
        """Same triangle, but direct-only routing can't use the detour."""
        result = run_with_disruptions(
            [link_down(0.5, "l01")],
            network=make_network(triangle=True),
            routing=DirectLinkRouting(),
        ).run()
        assert result.metrics["unfinished_tasks"] == 1


class TestSnapshotAndRecovery:
    def test_snapshot_reflects_disruption_state(self):
        """The scheduler-facing snapshot must show the disrupted bandwidths,
        otherwise a repair policy would plan against a healthy network."""
        sim = run_with_disruptions([link_down(0.5, "l01", duration=2.0)])
        seen = {}

        def spy(event):
            if event.event_type.name == "LINK_STATE_CHANGE":
                snapshot = sim.engine.get_network_snapshot()
                seen[event.data["change"]] = snapshot.links["l01"].bandwidth

        sim.add_event_listener(spy)
        sim.run()
        assert seen["link_down"] == pytest.approx(0.0)
        assert seen["recovery"] == pytest.approx(100.0)

    def test_recovery_is_auto_scheduled_from_duration(self):
        """A duration on link_down implies a recovery event; both appear in
        the disruption count (1 down + 1 auto recovery)."""
        result = run_with_disruptions([link_down(0.5, "l01", duration=2.0)]).run()
        assert result.metrics["disruptions"]["disruptions_applied"] == 2


class TestScenarioLoader:
    def test_demo_scenario_parses_and_matches_hand_computed_makespan(self):
        from pathlib import Path
        from ncsim.io.scenario_loader import load_scenario

        scenario_path = (
            Path(__file__).parent.parent / "scenarios" / "demo_link_failure.yaml"
        )
        scenario = load_scenario(str(scenario_path))
        assert len(scenario.disruptions) == 1
        assert scenario.disruptions[0].disruption_type == DisruptionType.LINK_DOWN

        sim = Simulation(
            network=scenario.network,
            scheduler=ManualScheduler(),
            dag_source=SingleDAGSource(scenario.dags[0]),
            routing_model=DirectLinkRouting(),
            disruption_model=ScheduledDisruptions(scenario.disruptions),
        )
        assert sim.run().makespan == pytest.approx(5.5)

    def test_disruption_referencing_unknown_link_is_rejected(self):
        import tempfile
        from ncsim.io.scenario_loader import load_scenario

        yaml_text = """
scenario:
  name: bad
  network:
    nodes:
      - {id: n0, compute_capacity: 100}
      - {id: n1, compute_capacity: 100}
    links:
      - {id: l01, from: n0, to: n1, bandwidth: 100}
  dags:
    - id: d
      tasks:
        - {id: T0, compute_cost: 1}
      edges: []
  disruptions:
    - {time: 1.0, link: no_such_link, type: link_down}
"""
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(yaml_text)
            path = f.name
        with pytest.raises(ValueError, match="unknown link"):
            load_scenario(path)

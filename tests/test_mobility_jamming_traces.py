"""Tests for the mobility (G3) and jamming (G4) trace generators."""

import pytest

from ncsim.core.simulation import Simulation
from ncsim.models.dag import DAG, Edge, SingleDAGSource
from ncsim.models.disruptions import DisruptionType, ScheduledDisruptions
from ncsim.models.failure_traces import (
    Jammer,
    jammer_targeting,
    jamming_trace,
    mobility_trace,
)
from ncsim.models.mobility import (
    Waypoints,
    convoy_trajectories,
    random_waypoint_trajectory,
)
from ncsim.models.network import Link, Network, Node, Position
from ncsim.models.routing import DirectLinkRouting
from ncsim.models.task import Task
from ncsim.scheduler.base import ManualScheduler


def make_network(positions) -> Network:
    """Nodes at given positions, radio pairs between all of them."""
    nodes = {
        node_id: Node(id=node_id, compute_capacity=100, position=Position(x, y))
        for node_id, (x, y) in positions.items()
    }
    links = {}
    ids = sorted(positions)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            links[f"l_{a}_{b}"] = Link(id=f"l_{a}_{b}", from_node=a, to_node=b, bandwidth=100)
            links[f"l_{b}_{a}"] = Link(id=f"l_{b}_{a}", from_node=b, to_node=a, bandwidth=100)
    return Network(nodes=nodes, links=links)


class TestWaypoints:
    def test_interpolates_linearly_and_clamps(self):
        path = Waypoints(points=((0.0, 0.0, 0.0), (10.0, 100.0, 0.0)))
        assert path.position(-1.0) == (0.0, 0.0)
        assert path.position(5.0) == (50.0, 0.0)
        assert path.position(99.0) == (100.0, 0.0)

    def test_rejects_non_increasing_times(self):
        with pytest.raises(ValueError, match="strictly increasing"):
            Waypoints(points=((0.0, 0, 0), (0.0, 1, 1)))

    def test_random_waypoint_is_deterministic_and_stays_in_area(self):
        area = (0.0, 0.0, 50.0, 50.0)
        a = random_waypoint_trajectory(area, speed=(1, 5), pause=1.0, horizon=100.0, seed=3)
        b = random_waypoint_trajectory(area, speed=(1, 5), pause=1.0, horizon=100.0, seed=3)
        assert a.points == b.points
        assert a.points[-1][0] >= 100.0
        assert all(0 <= x <= 50 and 0 <= y <= 50 for _, x, y in a.points)

    def test_convoy_holds_formation(self):
        road = Waypoints(points=((0.0, 0.0, 0.0), (10.0, 100.0, 0.0)))
        group = convoy_trajectories(road, {"lead": (0, 0), "tail": (-5, 2)})
        for t in (0.0, 3.7, 10.0):
            lx, ly = group["lead"].position(t)
            tx, ty = group["tail"].position(t)
            assert (tx - lx, ty - ly) == pytest.approx((-5.0, 2.0))


class TestMobilityTrace:
    def test_static_nodes_in_range_produce_no_events(self):
        network = make_network({"a": (0, 0), "b": (5, 0)})
        assert mobility_trace(network, {}, horizon=10.0, r_full=10, r_max=20) == []

    def test_receding_node_degrades_before_disconnecting(self):
        """The signature property of G3: a warning precedes the failure."""
        network = make_network({"a": (0, 0), "b": (5, 0)})
        # b drives from x=5 to x=45 over 40s: crosses r_full=10 at t=5,
        # r_max=20 at t=15.
        away = Waypoints(points=((0.0, 5.0, 0.0), (40.0, 45.0, 0.0)))
        events = mobility_trace(
            network, {"b": away}, horizon=40.0, dt=0.5, r_full=10, r_max=20
        )
        kinds = [e.disruption_type for e in events]
        first_degrade = kinds.index(DisruptionType.LINK_DEGRADE)
        first_down = kinds.index(DisruptionType.LINK_DOWN)
        assert first_degrade < first_down
        # Degradation is monotone on the way out.
        factors = [
            e.parameters["bandwidth_factor"]
            for e in events
            if e.disruption_type == DisruptionType.LINK_DEGRADE and e.target_id == "l_a_b"
        ]
        assert factors == sorted(factors, reverse=True)

    def test_returning_node_recovers_the_link(self):
        network = make_network({"a": (0, 0), "b": (5, 0)})
        out_and_back = Waypoints(
            points=((0.0, 5.0, 0.0), (20.0, 45.0, 0.0), (40.0, 5.0, 0.0))
        )
        events = mobility_trace(
            network, {"b": out_and_back}, horizon=40.0, dt=0.5, r_full=10, r_max=20
        )
        kinds = [e.disruption_type for e in events]
        assert DisruptionType.LINK_DOWN in kinds
        down_at = max(e.time for e in events if e.disruption_type == DisruptionType.LINK_DOWN)
        recoveries = [e for e in events if e.disruption_type == DisruptionType.RECOVERY]
        assert any(e.time > down_at for e in recoveries), "link comes back on approach"
        # Trace ends at full bandwidth: the last state-change for the pair is
        # a recovery, not a degrade.
        last = [e for e in events if e.target_id == "l_a_b"][-1]
        assert last.disruption_type == DisruptionType.RECOVERY

    def test_pair_out_of_range_at_start_is_closed_at_t0(self):
        network = make_network({"a": (0, 0), "b": (100, 0)})
        events = mobility_trace(network, {}, horizon=5.0, r_full=10, r_max=20)
        assert events and events[0].time == 0.0
        assert events[0].disruption_type == DisruptionType.LINK_DOWN

    def test_trace_is_deterministic(self):
        network = make_network({"a": (0, 0), "b": (5, 0), "c": (0, 8)})
        rwp = random_waypoint_trajectory(
            (0, 0, 60, 60), speed=(2, 8), pause=0.5, horizon=30.0, seed=11
        )
        a = mobility_trace(network, {"c": rwp}, horizon=30.0)
        b = mobility_trace(network, {"c": rwp}, horizon=30.0)
        assert [(e.time, e.target_id, e.disruption_type) for e in a] == [
            (e.time, e.target_id, e.disruption_type) for e in b
        ]

    def test_end_to_end_transfer_survives_a_drive_by(self):
        """A transfer stalls while the carrier is out of range and completes
        after it returns -- the whole pipeline, generator to makespan."""
        network = make_network({"a": (0, 0), "b": (5, 0)})
        out_and_back = Waypoints(
            points=((0.0, 5.0, 0.0), (20.0, 45.0, 0.0), (40.0, 5.0, 0.0))
        )
        trace = mobility_trace(
            network, {"b": out_and_back}, horizon=40.0, dt=0.5, r_full=10, r_max=20
        )
        tasks = {
            "T0": Task(id="T0", compute_cost=100, dag_id="d", pinned_to="a"),
            "T1": Task(id="T1", compute_cost=100, dag_id="d", pinned_to="b"),
        }
        # 600 MB: through the degradation staircase (100 -> 75 -> 50 -> 25
        # MB/s) only ~431 MB moves before the link dies at t=7.5, so the
        # transfer aborts and retransmits in full after b returns (~32.5
        # onward, stepping back up the staircase).
        dag = DAG(id="d", tasks=tasks, edges=[Edge(from_task="T0", to_task="T1", data_size=600)])
        sim = Simulation(
            network=network,
            scheduler=ManualScheduler(),
            dag_source=SingleDAGSource(dag),
            routing_model=DirectLinkRouting(),
            disruption_model=ScheduledDisruptions(trace),
        )
        result = sim.run()
        assert result.metrics["unfinished_tasks"] == 0
        assert result.metrics["disruptions"]["transfers_aborted"] >= 1
        # Undisrupted this instance finishes at 6.0; with the drive-by the
        # retransmit cannot even begin before b re-enters range around 32.5.
        assert result.makespan > 30.0


class TestJammingTrace:
    def test_jams_every_pair_with_an_endpoint_in_range(self):
        network = make_network({"a": (0, 0), "b": (10, 0), "c": (100, 0)})
        jammer = Jammer(x=0, y=0, radius=15, start=2.0, duration=3.0)
        events = jamming_trace(network, [jammer])
        downed_pairs = {e.target_id for e in events}
        # a and b are in range: a-b, a-c, b-c all have an endpoint jammed.
        assert downed_pairs == {
            "l_a_b", "l_b_a", "l_a_c", "l_c_a", "l_b_c", "l_c_b"
        }
        assert all(e.time == 2.0 and e.duration == 3.0 for e in events)

    def test_simultaneous_multi_link_outage_is_the_signature(self):
        """All affected pairs fail at the same instant -- the spatial
        correlation that distinguishes G4 from G2's independent failures."""
        network = make_network({"a": (0, 0), "b": (10, 0), "c": (0, 10)})
        events = jamming_trace(network, [Jammer(x=0, y=0, radius=12, start=1.0, duration=2.0)])
        assert len({e.time for e in events}) == 1

    def test_out_of_range_jammer_is_harmless(self):
        network = make_network({"a": (0, 0), "b": (10, 0)})
        assert jamming_trace(network, [Jammer(x=500, y=500, radius=15, start=0, duration=5)]) == []

    def test_overlapping_jammers_merge_into_one_outage(self):
        network = make_network({"a": (0, 0), "b": (10, 0)})
        jammers = [
            Jammer(x=0, y=0, radius=15, start=1.0, duration=2.0),
            Jammer(x=0, y=0, radius=15, start=2.5, duration=2.0),
        ]
        events = jamming_trace(network, jammers)
        per_link = [e for e in events if e.target_id == "l_a_b"]
        assert len(per_link) == 1
        assert per_link[0].time == 1.0
        assert per_link[0].duration == pytest.approx(3.5)

    def test_targeted_jammer_sits_at_the_link_midpoint(self):
        network = make_network({"a": (0, 0), "b": (10, 0), "c": (100, 0)})
        jammer = jammer_targeting(network, ("a", "b"), radius=6, start=0.5, duration=1.0)
        assert (jammer.x, jammer.y) == (5.0, 0.0)
        events = jamming_trace(network, [jammer])
        # Radius 6 from (5,0) reaches a and b but not c: only pairs touching
        # a or b fall, which here is every pair -- so shrink to isolate:
        assert {e.target_id for e in events} >= {"l_a_b", "l_b_a"}

    def test_rejects_invalid_jammer(self):
        with pytest.raises(ValueError):
            Jammer(x=0, y=0, radius=0, start=0, duration=1)

"""
Unit tests for routing models.
"""

import pytest
from ncsim.models.routing import (
    DirectLinkRouting, WidestPathRouting, ShortestPathRouting,
    InterferenceAwareRouting, DynamicInterferenceAwareRouting,
    DeferralDynamicRouting,
)
from ncsim.models.network import Network, Node, Link, Position
from ncsim.models.interference import ProximityInterference, NoInterference
from ncsim.models.dag import DAG, Edge
from ncsim.models.task import Task
from ncsim.scheduler.base import PlacementPlan


def make_network(nodes_data, links_data):
    """Helper to create a Network from simple data."""
    nodes = {
        n["id"]: Node(
            id=n["id"],
            compute_capacity=n.get("compute_capacity", 100),
            position=Position(
                n.get("x", 0),
                n.get("y", 0)
            )
        )
        for n in nodes_data
    }
    links = {
        l["id"]: Link(
            id=l["id"],
            from_node=l["from"],
            to_node=l["to"],
            bandwidth=l["bandwidth"],
            latency=l.get("latency", 0.0)
        )
        for l in links_data
    }
    return Network(nodes=nodes, links=links)


class TestDirectLinkRouting:
    """Tests for DirectLinkRouting."""

    def test_same_node_returns_empty_path(self):
        """Same node should return empty path (local transfer)."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}],
            [{"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100}]
        )
        routing = DirectLinkRouting()
        path = routing.get_path("n0", "n0", network)
        assert path == []

    def test_direct_link_returns_single_link(self):
        """Direct link should return path with single link."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}],
            [{"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100}]
        )
        routing = DirectLinkRouting()
        path = routing.get_path("n0", "n1", network)
        assert path == ["l01"]

    def test_no_direct_link_returns_none(self):
        """No direct link should return None."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}, {"id": "n2"}],
            [
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100},
                {"id": "l12", "from": "n1", "to": "n2", "bandwidth": 100}
            ]
        )
        routing = DirectLinkRouting()
        path = routing.get_path("n0", "n2", network)
        assert path is None


class TestWidestPathRouting:
    """Tests for WidestPathRouting."""

    def test_same_node_returns_empty_path(self):
        """Same node should return empty path (local transfer)."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}],
            [{"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100}]
        )
        routing = WidestPathRouting()
        path = routing.get_path("n0", "n0", network)
        assert path == []

    def test_direct_link_returns_single_link(self):
        """Direct link should return path with single link."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}],
            [{"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100}]
        )
        routing = WidestPathRouting()
        path = routing.get_path("n0", "n1", network)
        assert path == ["l01"]

    def test_widest_path_finds_indirect_route(self):
        """Should find multi-hop path when no direct link exists."""
        # n0 -> n1 -> n2 (no direct n0 -> n2)
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}, {"id": "n2"}],
            [
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100},
                {"id": "l12", "from": "n1", "to": "n2", "bandwidth": 100}
            ]
        )
        routing = WidestPathRouting()
        path = routing.get_path("n0", "n2", network)
        assert path == ["l01", "l12"]

    def test_widest_path_prefers_higher_bandwidth(self):
        """Should prefer path with higher bottleneck bandwidth."""
        # Path A: n0 -> n1 -> n2 with 100 -> 50 (bottleneck 50)
        # Path B: n0 -> n3 -> n2 with 80 -> 80 (bottleneck 80)
        # Should choose Path B
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}, {"id": "n2"}, {"id": "n3"}],
            [
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100},
                {"id": "l12", "from": "n1", "to": "n2", "bandwidth": 50},
                {"id": "l03", "from": "n0", "to": "n3", "bandwidth": 80},
                {"id": "l32", "from": "n3", "to": "n2", "bandwidth": 80}
            ]
        )
        routing = WidestPathRouting()
        path = routing.get_path("n0", "n2", network)
        # Should choose path through n3 (bottleneck 80 > 50)
        assert path == ["l03", "l32"]

    def test_widest_path_bandwidth_calculation(self):
        """Should correctly calculate bottleneck bandwidth."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}, {"id": "n2"}],
            [
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100},
                {"id": "l12", "from": "n1", "to": "n2", "bandwidth": 60}
            ]
        )
        routing = WidestPathRouting()
        bandwidth = routing.get_path_bandwidth("n0", "n2", network)
        assert bandwidth == 60  # Bottleneck is l12

    def test_widest_path_bandwidth_same_node(self):
        """Same node bandwidth should be infinite."""
        network = make_network(
            [{"id": "n0"}],
            []
        )
        routing = WidestPathRouting()
        bandwidth = routing.get_path_bandwidth("n0", "n0", network)
        assert bandwidth == float('inf')

    def test_widest_path_bandwidth_no_path(self):
        """No path should return 0 bandwidth."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}],
            []  # No links
        )
        routing = WidestPathRouting()
        bandwidth = routing.get_path_bandwidth("n0", "n1", network)
        assert bandwidth == 0.0

    def test_no_path_returns_none(self):
        """Should return None when no path exists."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}],
            []  # No links
        )
        routing = WidestPathRouting()
        path = routing.get_path("n0", "n1", network)
        assert path is None

    def test_path_caching(self):
        """Should cache computed paths."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}],
            [{"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100}]
        )
        routing = WidestPathRouting()

        # First call computes path
        path1 = routing.get_path("n0", "n1", network)
        # Second call should use cache
        path2 = routing.get_path("n0", "n1", network)

        assert path1 == path2
        assert ("n0", "n1") in routing._path_cache

    def test_clear_cache(self):
        """Should be able to clear caches."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}],
            [{"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100}]
        )
        routing = WidestPathRouting()

        routing.get_path("n0", "n1", network)
        assert len(routing._path_cache) > 0

        routing.clear_cache()
        assert len(routing._path_cache) == 0
        assert len(routing._bandwidth_cache) == 0

    def test_longer_path_with_higher_bandwidth(self):
        """Should prefer longer path if bandwidth is higher."""
        # Direct path: n0 -> n2 with bandwidth 30
        # Indirect path: n0 -> n1 -> n2 with bandwidth 100 -> 100 (bottleneck 100)
        # Should choose indirect path
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}, {"id": "n2"}],
            [
                {"id": "l02", "from": "n0", "to": "n2", "bandwidth": 30},
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100},
                {"id": "l12", "from": "n1", "to": "n2", "bandwidth": 100}
            ]
        )
        routing = WidestPathRouting()
        path = routing.get_path("n0", "n2", network)
        bandwidth = routing.get_path_bandwidth("n0", "n2", network)

        # Should choose the path with higher bottleneck bandwidth (100 vs 30)
        assert path == ["l01", "l12"]
        assert bandwidth == 100


class TestShortestPathRouting:
    """Tests for ShortestPathRouting."""

    def test_same_node_returns_empty_path(self):
        """Same node should return empty path (local transfer)."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}],
            [{"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100, "latency": 0.01}]
        )
        routing = ShortestPathRouting()
        path = routing.get_path("n0", "n0", network)
        assert path == []

    def test_direct_link_returns_single_link(self):
        """Direct link should return path with single link."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}],
            [{"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100, "latency": 0.01}]
        )
        routing = ShortestPathRouting()
        path = routing.get_path("n0", "n1", network)
        assert path == ["l01"]

    def test_shortest_path_finds_indirect_route(self):
        """Should find multi-hop path when no direct link exists."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}, {"id": "n2"}],
            [
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100, "latency": 0.01},
                {"id": "l12", "from": "n1", "to": "n2", "bandwidth": 100, "latency": 0.01}
            ]
        )
        routing = ShortestPathRouting()
        path = routing.get_path("n0", "n2", network)
        assert path == ["l01", "l12"]

    def test_shortest_path_prefers_higher_bandwidth(self):
        """Should prefer path with lower sum(1/bw) — i.e. higher bandwidth."""
        # Path A: n0 -> n1 -> n2, bw=50:  sum(1/bw) = 1/50 + 1/50 = 0.04
        # Path B: n0 -> n3 -> n2, bw=200: sum(1/bw) = 1/200 + 1/200 = 0.01
        # SP should choose Path B (lower delay cost), even though B has higher latency
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}, {"id": "n2"}, {"id": "n3"}],
            [
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 50,  "latency": 0.01},
                {"id": "l12", "from": "n1", "to": "n2", "bandwidth": 50,  "latency": 0.01},
                {"id": "l03", "from": "n0", "to": "n3", "bandwidth": 200, "latency": 0.1},
                {"id": "l32", "from": "n3", "to": "n2", "bandwidth": 200, "latency": 0.1}
            ]
        )
        routing = ShortestPathRouting()
        path = routing.get_path("n0", "n2", network)
        # Should choose path through n3 (sum(1/bw) = 0.01 < 0.04)
        assert path == ["l03", "l32"]

    def test_shortest_path_prefers_indirect_high_bandwidth(self):
        """Should prefer indirect high-bandwidth path over direct slow link."""
        # Direct: n0 -> n2 with bw=30:  sum(1/bw) = 1/30 ≈ 0.033
        # Indirect: n0 -> n1 -> n2 with bw=100 each: sum(1/bw) = 0.01 + 0.01 = 0.02
        # Should choose indirect (lower delay cost)
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}, {"id": "n2"}],
            [
                {"id": "l02", "from": "n0", "to": "n2", "bandwidth": 30,  "latency": 0.005},
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100, "latency": 0.001},
                {"id": "l12", "from": "n1", "to": "n2", "bandwidth": 100, "latency": 0.001}
            ]
        )
        routing = ShortestPathRouting()
        path = routing.get_path("n0", "n2", network)
        # Indirect path has lower delay cost (0.02 < 0.033)
        assert path == ["l01", "l12"]

    def test_shortest_path_bandwidth_calculation(self):
        """Should correctly calculate bottleneck bandwidth along shortest path."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}, {"id": "n2"}],
            [
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100, "latency": 0.01},
                {"id": "l12", "from": "n1", "to": "n2", "bandwidth": 60, "latency": 0.01}
            ]
        )
        routing = ShortestPathRouting()
        bandwidth = routing.get_path_bandwidth("n0", "n2", network)
        assert bandwidth == 60  # Bottleneck is l12

    def test_shortest_path_bandwidth_same_node(self):
        """Same node bandwidth should be infinite."""
        network = make_network(
            [{"id": "n0"}],
            []
        )
        routing = ShortestPathRouting()
        bandwidth = routing.get_path_bandwidth("n0", "n0", network)
        assert bandwidth == float('inf')

    def test_shortest_path_bandwidth_no_path(self):
        """No path should return 0 bandwidth."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}],
            []  # No links
        )
        routing = ShortestPathRouting()
        bandwidth = routing.get_path_bandwidth("n0", "n1", network)
        assert bandwidth == 0.0

    def test_no_path_returns_none(self):
        """Should return None when no path exists."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}],
            []  # No links
        )
        routing = ShortestPathRouting()
        path = routing.get_path("n0", "n1", network)
        assert path is None

    def test_path_caching(self):
        """Should cache computed paths."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}],
            [{"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100, "latency": 0.01}]
        )
        routing = ShortestPathRouting()

        # First call computes path
        path1 = routing.get_path("n0", "n1", network)
        # Second call should use cache
        path2 = routing.get_path("n0", "n1", network)

        assert path1 == path2
        assert ("n0", "n1") in routing._path_cache

    def test_clear_cache(self):
        """Should be able to clear caches."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}],
            [{"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100, "latency": 0.01}]
        )
        routing = ShortestPathRouting()

        routing.get_path("n0", "n1", network)
        assert len(routing._path_cache) > 0

        routing.clear_cache()
        assert len(routing._path_cache) == 0
        assert len(routing._bandwidth_cache) == 0


class TestInterferenceAwareRouting:
    """Tests for InterferenceAwareRouting."""

    def test_same_node_returns_empty_path(self):
        """Same node should return empty path (local transfer)."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}],
            [{"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100}]
        )
        im = NoInterference()
        routing = InterferenceAwareRouting(im)
        path = routing.get_path("n0", "n0", network)
        assert path == []

    def test_fallback_before_planning(self):
        """Before plan_routes(), should delegate to WidestPathRouting."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}, {"id": "n2"}],
            [
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100},
                {"id": "l12", "from": "n1", "to": "n2", "bandwidth": 100}
            ]
        )
        im = NoInterference()
        routing = InterferenceAwareRouting(im)
        assert not routing._routes_planned
        path = routing.get_path("n0", "n2", network)
        assert path == ["l01", "l12"]

    def test_plan_routes_basic(self):
        """After plan_routes(), should return pre-computed route."""
        # Simple chain: n0 -> n1 -> n2
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}, {"id": "n2"}],
            [
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100},
                {"id": "l12", "from": "n1", "to": "n2", "bandwidth": 100}
            ]
        )
        dag = DAG(
            id="dag1",
            tasks={
                "T0": Task(id="T0", compute_cost=10, dag_id="dag1"),
                "T1": Task(id="T1", compute_cost=10, dag_id="dag1"),
            },
            edges=[Edge(from_task="T0", to_task="T1", data_size=50)]
        )
        plan = PlacementPlan(assignments={"T0": "n0", "T1": "n2"})

        im = NoInterference()
        routing = InterferenceAwareRouting(im)
        routing.plan_routes(dag, plan, network)

        assert routing._routes_planned
        path = routing.get_path("n0", "n2", network)
        assert path == ["l01", "l12"]

    def test_get_path_bandwidth_delegates(self):
        """get_path_bandwidth should delegate to WidestPathRouting."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}, {"id": "n2"}],
            [
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100},
                {"id": "l12", "from": "n1", "to": "n2", "bandwidth": 60}
            ]
        )
        im = NoInterference()
        routing = InterferenceAwareRouting(im)
        bw = routing.get_path_bandwidth("n0", "n2", network)
        assert bw == 60  # Bottleneck is l12

    def test_hop_cutoff_respected(self):
        """Paths longer than hop_cutoff should not be enumerated."""
        # Chain: n0 -> n1 -> n2 -> n3 (3 hops)
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}, {"id": "n2"}, {"id": "n3"}],
            [
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100},
                {"id": "l12", "from": "n1", "to": "n2", "bandwidth": 100},
                {"id": "l23", "from": "n2", "to": "n3", "bandwidth": 100},
            ]
        )
        dag = DAG(
            id="dag1",
            tasks={
                "T0": Task(id="T0", compute_cost=10, dag_id="dag1"),
                "T1": Task(id="T1", compute_cost=10, dag_id="dag1"),
            },
            edges=[Edge(from_task="T0", to_task="T1", data_size=50)]
        )
        plan = PlacementPlan(assignments={"T0": "n0", "T1": "n3"})

        # With hop_cutoff=2, the 3-hop path should not be found by enumeration
        # but fallback to delegate should find it
        im = NoInterference()
        routing = InterferenceAwareRouting(im, hop_cutoff=2)
        routing.plan_routes(dag, plan, network)

        path = routing.get_path("n0", "n3", network)
        # Should still find a path via delegate fallback
        assert path is not None
        assert path == ["l01", "l12", "l23"]

    def test_concurrent_flow_detection(self):
        """Flows with overlapping time windows should be detected as concurrent."""
        from ncsim.models.routing import _RoutedFlow
        im = NoInterference()
        routing = InterferenceAwareRouting(im)

        routed = [
            _RoutedFlow("T0", "T1", "n0", "n1", 100, ["l01"],
                        est_start=0.0, est_end=5.0),
            _RoutedFlow("T2", "T3", "n2", "n3", 100, ["l23"],
                        est_start=10.0, est_end=15.0),
        ]

        # Window overlapping with first flow only
        concurrent = routing._find_concurrent_flows((1.0, 4.0), routed)
        assert len(concurrent) == 1
        assert concurrent[0].from_task == "T0"

        # Window overlapping with neither
        concurrent = routing._find_concurrent_flows((6.0, 9.0), routed)
        assert len(concurrent) == 0

        # Window overlapping with both
        concurrent = routing._find_concurrent_flows((0.0, 15.0), routed)
        assert len(concurrent) == 2

    def test_avoids_interference(self):
        """Should pick non-interfering paths when alternatives exist.

        Topology: two separate direct corridors (top y=0, bottom y=200)
        plus a shared center hub (y=100). Two flows:
        - Flow 1: n0(0,0) -> n1(200,0)
        - Flow 2: n2(0,200) -> n3(200,200)

        Each flow can go direct (1 hop, no interference between corridors)
        or via center nc(100,100) (2 hops, center links interfere).

        With radius=120, center links from both flows interfere (dist ~100).
        Direct corridors are 200 apart -> no interference.
        Router should prefer direct corridors for higher total throughput.
        """
        network = make_network(
            [
                {"id": "n0", "x": 0, "y": 0},
                {"id": "n1", "x": 200, "y": 0},
                {"id": "n2", "x": 0, "y": 200},
                {"id": "n3", "x": 200, "y": 200},
                {"id": "nc", "x": 100, "y": 100},
            ],
            [
                # Direct corridors (1-hop, far apart)
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100},
                {"id": "l23", "from": "n2", "to": "n3", "bandwidth": 100},
                # Center hub paths (2-hop, close together -> interfere)
                {"id": "l0c", "from": "n0", "to": "nc", "bandwidth": 100},
                {"id": "lc1", "from": "nc", "to": "n1", "bandwidth": 100},
                {"id": "l2c", "from": "n2", "to": "nc", "bandwidth": 100},
                {"id": "lc3", "from": "nc", "to": "n3", "bandwidth": 100},
            ]
        )

        dag = DAG(
            id="dag1",
            tasks={
                "T_src1": Task(id="T_src1", compute_cost=1, dag_id="dag1"),
                "T_dst1": Task(id="T_dst1", compute_cost=1, dag_id="dag1"),
                "T_src2": Task(id="T_src2", compute_cost=1, dag_id="dag1"),
                "T_dst2": Task(id="T_dst2", compute_cost=1, dag_id="dag1"),
            },
            edges=[
                Edge(from_task="T_src1", to_task="T_dst1", data_size=100),
                Edge(from_task="T_src2", to_task="T_dst2", data_size=100),
            ]
        )
        plan = PlacementPlan(assignments={
            "T_src1": "n0", "T_dst1": "n1",
            "T_src2": "n2", "T_dst2": "n3",
        })

        im = ProximityInterference(interference_radius=120)
        routing = InterferenceAwareRouting(im, hop_cutoff=4)
        routing.plan_routes(dag, plan, network)

        path_n0_n1 = routing.get_path("n0", "n1", network)
        path_n2_n3 = routing.get_path("n2", "n3", network)

        # Both should use direct corridors (no interference) rather than center hub
        center_links = {"l0c", "lc1", "l2c", "lc3"}
        path1_uses_center = any(lid in center_links for lid in path_n0_n1)
        path2_uses_center = any(lid in center_links for lid in path_n2_n3)
        assert not path1_uses_center, f"Flow 1 should use direct corridor, got {path_n0_n1}"
        assert not path2_uses_center, f"Flow 2 should use direct corridor, got {path_n2_n3}"
        assert path_n0_n1 == ["l01"]
        assert path_n2_n3 == ["l23"]

    def test_no_flows_plans_immediately(self):
        """When all tasks on same node, plan_routes completes with no routes."""
        network = make_network(
            [{"id": "n0"}],
            []
        )
        dag = DAG(
            id="dag1",
            tasks={
                "T0": Task(id="T0", compute_cost=10, dag_id="dag1"),
                "T1": Task(id="T1", compute_cost=10, dag_id="dag1"),
            },
            edges=[Edge(from_task="T0", to_task="T1", data_size=50)]
        )
        plan = PlacementPlan(assignments={"T0": "n0", "T1": "n0"})

        im = NoInterference()
        routing = InterferenceAwareRouting(im)
        routing.plan_routes(dag, plan, network)
        assert routing._routes_planned
        assert len(routing._planned_routes) == 0


class TestDynamicInterferenceAwareRouting:
    """Tests for DynamicInterferenceAwareRouting (GSD)."""

    def test_same_node_returns_empty_path(self):
        """Same node should return empty path (local transfer)."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}],
            [{"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100}]
        )
        im = NoInterference()
        routing = DynamicInterferenceAwareRouting(im)
        path = routing.get_path("n0", "n0", network)
        assert path == []

    def test_delegates_without_network_state(self):
        """Without network_state, should delegate to WidestPathRouting."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}, {"id": "n2"}],
            [
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100},
                {"id": "l12", "from": "n1", "to": "n2", "bandwidth": 100}
            ]
        )
        im = NoInterference()
        routing = DynamicInterferenceAwareRouting(im)
        # No network_state -> delegates to WidestPathRouting
        path = routing.get_path("n0", "n2", network)
        assert path == ["l01", "l12"]

    def test_picks_least_interfered_path(self):
        """Should pick the path with less interference from active links.

        Topology: n0 can reach n3 via two paths:
          Path A: n0 -> n1 -> n3 (links l01, l13) — near active link la
          Path B: n0 -> n2 -> n3 (links l02, l23) — far from active link la

        With proximity interference (radius=50), path A links interfere
        with la (midpoints within 50), path B links don't.
        GSD should pick path B for higher effective bandwidth.
        """
        network = make_network(
            [
                {"id": "n0", "x": 0, "y": 0},
                {"id": "n1", "x": 20, "y": 0},    # Path A: close to active link
                {"id": "n2", "x": 0, "y": 200},    # Path B: far from active link
                {"id": "n3", "x": 20, "y": 200},
                {"id": "na", "x": 10, "y": -10},   # Active link endpoints
                {"id": "nb", "x": 30, "y": -10},
            ],
            [
                # Path A
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100},
                {"id": "l13", "from": "n1", "to": "n3", "bandwidth": 100},
                # Path B
                {"id": "l02", "from": "n0", "to": "n2", "bandwidth": 100},
                {"id": "l23", "from": "n2", "to": "n3", "bandwidth": 100},
                # Active link (near path A)
                {"id": "la", "from": "na", "to": "nb", "bandwidth": 100},
            ]
        )
        im = ProximityInterference(interference_radius=50)
        routing = DynamicInterferenceAwareRouting(im, hop_cutoff=4)

        network_state = {
            "active_link_ids": {"la"},
            "link_transfer_counts": {"la": 1},
        }
        path = routing.get_path("n0", "n3", network, network_state)
        # Should pick path B (far from active link, no interference)
        assert path == ["l02", "l23"], f"Expected path B, got {path}"

    def test_accounts_for_link_sharing(self):
        """Path with existing transfers should score lower.

        Two paths of equal raw bandwidth, but one has existing transfers
        that reduce the effective bandwidth via fair sharing.
        """
        network = make_network(
            [
                {"id": "n0", "x": 0, "y": 0},
                {"id": "n1", "x": 100, "y": 0},
                {"id": "n2", "x": 0, "y": 200},
                {"id": "n3", "x": 100, "y": 200},
            ],
            [
                # Path A (direct, but has existing transfer)
                {"id": "l_direct", "from": "n0", "to": "n1", "bandwidth": 100},
                # Path B (via n2->n3->n1, no existing transfers)
                {"id": "l02", "from": "n0", "to": "n2", "bandwidth": 100},
                {"id": "l23", "from": "n2", "to": "n3", "bandwidth": 100},
                {"id": "l31", "from": "n3", "to": "n1", "bandwidth": 100},
            ]
        )
        im = NoInterference()
        routing = DynamicInterferenceAwareRouting(im, hop_cutoff=4)

        # l_direct has 2 existing transfers -> adding 1 more gives 100/3 = 33.3
        # Path B has 0 existing transfers -> each link gives 100/1 = 100
        network_state = {
            "active_link_ids": {"l_direct"},
            "link_transfer_counts": {"l_direct": 2},
        }
        path = routing.get_path("n0", "n1", network, network_state)
        # Should pick path B (higher effective bandwidth)
        assert path != ["l_direct"], f"Should avoid congested direct link, got {path}"
        assert len(path) > 1  # Multi-hop path

    def test_get_path_bandwidth_delegates(self):
        """get_path_bandwidth should delegate to WidestPathRouting."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}, {"id": "n2"}],
            [
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100},
                {"id": "l12", "from": "n1", "to": "n2", "bandwidth": 60}
            ]
        )
        im = NoInterference()
        routing = DynamicInterferenceAwareRouting(im)
        bw = routing.get_path_bandwidth("n0", "n2", network)
        assert bw == 60  # Bottleneck is l12


class TestGreedyOrderVariants:
    """Tests for GC (criticality), GB (bytes), GO (overlap) greedy orderings."""

    def _make_chain_dag_and_plan(self):
        """Create a 4-task chain DAG with placement across 3 nodes.

        T0(n0, cost=100) --10MB--> T1(n1, cost=200) --20MB--> T2(n2, cost=50) --5MB--> T3(n0, cost=100)
        """
        network = make_network(
            [
                {"id": "n0", "x": 0, "y": 0, "compute_capacity": 100},
                {"id": "n1", "x": 40, "y": 0, "compute_capacity": 100},
                {"id": "n2", "x": 80, "y": 0, "compute_capacity": 100},
            ],
            [
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100},
                {"id": "l12", "from": "n1", "to": "n2", "bandwidth": 100},
                {"id": "l20", "from": "n2", "to": "n0", "bandwidth": 100},
            ]
        )
        dag = DAG(
            id="dag1",
            tasks={
                "T0": Task(id="T0", compute_cost=100, dag_id="dag1"),
                "T1": Task(id="T1", compute_cost=200, dag_id="dag1"),
                "T2": Task(id="T2", compute_cost=50, dag_id="dag1"),
                "T3": Task(id="T3", compute_cost=100, dag_id="dag1"),
            },
            edges=[
                Edge(from_task="T0", to_task="T1", data_size=10),
                Edge(from_task="T1", to_task="T2", data_size=20),
                Edge(from_task="T2", to_task="T3", data_size=5),
            ]
        )
        plan = PlacementPlan(assignments={
            "T0": "n0", "T1": "n1", "T2": "n2", "T3": "n0"
        })
        return network, dag, plan

    def test_invalid_greedy_order_raises(self):
        """Invalid greedy_order should raise ValueError."""
        im = NoInterference()
        with pytest.raises(ValueError, match="greedy_order"):
            InterferenceAwareRouting(im, greedy_order="invalid")

    def test_gs_sorts_by_start_time(self):
        """GS (start) should sort flows by estimated start time ascending."""
        network, dag, plan = self._make_chain_dag_and_plan()
        im = NoInterference()
        routing = InterferenceAwareRouting(im, greedy_order="start")
        routing.plan_routes(dag, plan, network)
        assert routing._routes_planned

    def test_gc_sorts_by_criticality(self):
        """GC (criticality) routes most-critical flows first.

        In a chain T0->T1->T2->T3, ranku(T1) > ranku(T2) > ranku(T3).
        The flow to T1 should be routed before the flow to T2.
        """
        network, dag, plan = self._make_chain_dag_and_plan()
        im = NoInterference()
        routing = InterferenceAwareRouting(im, greedy_order="criticality")

        # Verify ranku ordering
        ranku = routing._compute_ranku(dag, plan, network)
        # T1 has more downstream work than T2, T2 has more than T3
        assert ranku["T1"] > ranku["T2"], f"ranku T1={ranku['T1']:.2f} should > T2={ranku['T2']:.2f}"
        assert ranku["T2"] > ranku["T3"], f"ranku T2={ranku['T2']:.2f} should > T3={ranku['T3']:.2f}"

        routing.plan_routes(dag, plan, network)
        assert routing._routes_planned

    def test_gb_sorts_by_bytes(self):
        """GB (bytes) routes largest flows first.

        Flows: T0->T1 (10MB), T1->T2 (20MB), T2->T3 (5MB).
        GB should route T1->T2 first (20MB), then T0->T1 (10MB), then T2->T3 (5MB).
        """
        network, dag, plan = self._make_chain_dag_and_plan()
        im = NoInterference()
        routing = InterferenceAwareRouting(im, greedy_order="bytes")
        routing.plan_routes(dag, plan, network)
        assert routing._routes_planned

    def test_go_sorts_by_overlap(self):
        """GO (overlap) routes most-congested flows first.

        Create a DAG where some flows have overlapping time windows.
        """
        network, dag, plan = self._make_chain_dag_and_plan()
        im = NoInterference()
        routing = InterferenceAwareRouting(im, greedy_order="overlap")
        routing.plan_routes(dag, plan, network)
        assert routing._routes_planned

    def test_gc_ranku_leaf_task(self):
        """Leaf task should have ranku = compute_cost / capacity."""
        network, dag, plan = self._make_chain_dag_and_plan()
        im = NoInterference()
        routing = InterferenceAwareRouting(im, greedy_order="criticality")
        ranku = routing._compute_ranku(dag, plan, network)
        # T3 is a leaf: ranku = 100/100 = 1.0
        assert abs(ranku["T3"] - 1.0) < 0.01, f"ranku(T3)={ranku['T3']:.2f}, expected 1.0"

    def test_overlap_degrees_non_overlapping(self):
        """Non-overlapping flows should have zero overlap degree."""
        flows = [
            {"from_task": "A", "to_task": "B", "data_size": 10},
            {"from_task": "C", "to_task": "D", "data_size": 10},
        ]
        windows = {
            ("A", "B"): (0.0, 5.0),
            ("C", "D"): (10.0, 15.0),
        }
        degrees = InterferenceAwareRouting._compute_overlap_degrees(flows, windows)
        assert degrees[("A", "B")] == 0.0
        assert degrees[("C", "D")] == 0.0

    def test_overlap_degrees_overlapping(self):
        """Overlapping flows should have positive overlap degree."""
        flows = [
            {"from_task": "A", "to_task": "B", "data_size": 10},
            {"from_task": "C", "to_task": "D", "data_size": 10},
            {"from_task": "E", "to_task": "F", "data_size": 10},
        ]
        windows = {
            ("A", "B"): (0.0, 10.0),
            ("C", "D"): (5.0, 15.0),
            ("E", "F"): (20.0, 25.0),
        }
        degrees = InterferenceAwareRouting._compute_overlap_degrees(flows, windows)
        # A-B overlaps with C-D by 5.0s, not with E-F
        assert degrees[("A", "B")] == 5.0
        # C-D overlaps with A-B by 5.0s, not with E-F
        assert degrees[("C", "D")] == 5.0
        # E-F overlaps with nobody
        assert degrees[("E", "F")] == 0.0

    def test_all_variants_produce_valid_routes(self):
        """All greedy orderings should produce valid routes for same DAG."""
        network, dag, plan = self._make_chain_dag_and_plan()
        im = NoInterference()

        for order in InterferenceAwareRouting.GREEDY_ORDERS:
            routing = InterferenceAwareRouting(im, greedy_order=order)
            routing.plan_routes(dag, plan, network)
            assert routing._routes_planned, f"order={order} failed to plan"
            # Every flow should have a route
            for edge in dag.edges:
                src = plan.assignments[edge.from_task]
                dst = plan.assignments[edge.to_task]
                if src != dst:
                    path = routing.get_path(src, dst, network)
                    assert path is not None, f"order={order}: no path {src}->{dst}"
                    assert len(path) > 0, f"order={order}: empty path {src}->{dst}"


class TestDeferralDynamicRouting:
    """Tests for DeferralDynamicRouting (GSD-D)."""

    def test_same_node_returns_empty_path(self):
        """Same node should return empty path (local transfer)."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}],
            [{"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100}]
        )
        im = NoInterference()
        routing = DeferralDynamicRouting(im)
        path = routing.get_path("n0", "n0", network)
        assert path == []
        assert not routing.should_defer

    def test_supports_deferral_property(self):
        """DeferralDynamicRouting should report supports_deferral=True."""
        im = NoInterference()
        routing = DeferralDynamicRouting(im)
        assert routing.supports_deferral is True
        assert routing.is_dynamic is True

    def test_delegates_without_network_state(self):
        """Without network_state, should delegate to WidestPathRouting."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}, {"id": "n2"}],
            [
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100},
                {"id": "l12", "from": "n1", "to": "n2", "bandwidth": 100}
            ]
        )
        im = NoInterference()
        routing = DeferralDynamicRouting(im)
        path = routing.get_path("n0", "n2", network)
        assert path == ["l01", "l12"]
        assert not routing.should_defer

    def test_no_defer_when_uncongested(self):
        """Should NOT defer when path has good bandwidth (no interference)."""
        network = make_network(
            [
                {"id": "n0", "x": 0, "y": 0},
                {"id": "n1", "x": 100, "y": 0},
            ],
            [
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100},
            ]
        )
        im = NoInterference()
        routing = DeferralDynamicRouting(im, deferral_threshold=0.3)
        # No active links → effective BW = 100 = no-contention BW → ratio=1.0 > 0.3
        network_state = {
            "active_link_ids": set(),
            "link_transfer_counts": {},
        }
        path = routing.get_path("n0", "n1", network, network_state)
        assert path == ["l01"]
        assert not routing.should_defer

    def test_defers_when_heavily_congested(self):
        """Should defer when effective BW is far below no-contention BW."""
        network = make_network(
            [
                {"id": "n0", "x": 0, "y": 0},
                {"id": "n1", "x": 10, "y": 0},
            ],
            [
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100},
            ]
        )
        # Use proximity interference with small radius so l01 interferes with itself
        # when other nearby links are active
        im = ProximityInterference(interference_radius=50)
        routing = DeferralDynamicRouting(im, deferral_threshold=0.3)

        # 5 existing transfers on the link + heavy interference
        # Effective BW: 100 * interference_factor / (5+1)
        # With proximity interference from many active nearby links, factor < 1
        network_state = {
            "active_link_ids": {"l01"},
            "link_transfer_counts": {"l01": 5},
        }
        path = routing.get_path("n0", "n1", network, network_state)
        assert path == ["l01"]
        # With 5 existing transfers: effective = 100 * factor / 6
        # No-contention = 100
        # ratio = factor/6 ≈ 0.5/6 ≈ 0.083 < 0.3 → should defer
        assert routing.should_defer

    def test_threshold_boundary(self):
        """Test deferral with different thresholds."""
        network = make_network(
            [
                {"id": "n0", "x": 0, "y": 0},
                {"id": "n1", "x": 100, "y": 0},
            ],
            [
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100},
            ]
        )
        im = NoInterference()
        # 2 existing transfers: effective = 100/(2+1) = 33.3
        # No-contention = 100, ratio = 0.333
        network_state = {
            "active_link_ids": {"l01"},
            "link_transfer_counts": {"l01": 2},
        }
        # Threshold 0.3 → ratio 0.333 > 0.3 → should NOT defer
        routing_low = DeferralDynamicRouting(im, deferral_threshold=0.3)
        routing_low.get_path("n0", "n1", network, network_state)
        assert not routing_low.should_defer

        # Threshold 0.5 → ratio 0.333 < 0.5 → should defer
        routing_high = DeferralDynamicRouting(im, deferral_threshold=0.5)
        routing_high.get_path("n0", "n1", network, network_state)
        assert routing_high.should_defer

    def test_get_path_bandwidth_delegates(self):
        """get_path_bandwidth should delegate to WidestPathRouting."""
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}, {"id": "n2"}],
            [
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100},
                {"id": "l12", "from": "n1", "to": "n2", "bandwidth": 60}
            ]
        )
        im = NoInterference()
        routing = DeferralDynamicRouting(im)
        bw = routing.get_path_bandwidth("n0", "n2", network)
        assert bw == 60

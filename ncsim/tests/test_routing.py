"""
Unit tests for routing models.
"""

import pytest
from ncsim.models.routing import (
    DirectLinkRouting, WidestPathRouting, ShortestPathRouting,
    InterferenceAwareRouting, DynamicInterferenceAwareRouting,
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

    def test_shortest_path_prefers_lower_latency(self):
        """Should prefer path with lower total latency over wider path."""
        # Path A: n0 -> n1 -> n2 with latency 0.01 + 0.01 = 0.02, bandwidth 50
        # Path B: n0 -> n3 -> n2 with latency 0.1 + 0.1 = 0.2, bandwidth 200
        # Shortest path should choose Path A (lower latency), even though B has more bandwidth
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}, {"id": "n2"}, {"id": "n3"}],
            [
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 50, "latency": 0.01},
                {"id": "l12", "from": "n1", "to": "n2", "bandwidth": 50, "latency": 0.01},
                {"id": "l03", "from": "n0", "to": "n3", "bandwidth": 200, "latency": 0.1},
                {"id": "l32", "from": "n3", "to": "n2", "bandwidth": 200, "latency": 0.1}
            ]
        )
        routing = ShortestPathRouting()
        path = routing.get_path("n0", "n2", network)
        # Should choose path through n1 (total latency 0.02 < 0.2)
        assert path == ["l01", "l12"]

    def test_shortest_path_prefers_direct_low_latency(self):
        """Should prefer direct low-latency link over indirect high-bandwidth path."""
        # Direct: n0 -> n2 with latency 0.005, bandwidth 30
        # Indirect: n0 -> n1 -> n2 with latency 0.001 + 0.001 = 0.002, bandwidth 100
        # Should choose indirect (lower total latency)
        network = make_network(
            [{"id": "n0"}, {"id": "n1"}, {"id": "n2"}],
            [
                {"id": "l02", "from": "n0", "to": "n2", "bandwidth": 30, "latency": 0.005},
                {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100, "latency": 0.001},
                {"id": "l12", "from": "n1", "to": "n2", "bandwidth": 100, "latency": 0.001}
            ]
        )
        routing = ShortestPathRouting()
        path = routing.get_path("n0", "n2", network)
        # Indirect path has lower total latency (0.002 < 0.005)
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

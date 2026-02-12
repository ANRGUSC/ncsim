"""
Unit tests for routing models.
"""

import pytest
from ncsim.models.routing import DirectLinkRouting, WidestPathRouting, ShortestPathRouting
from ncsim.models.network import Network, Node, Link, Position


def make_network(nodes_data, links_data):
    """Helper to create a Network from simple data."""
    nodes = {
        n["id"]: Node(
            id=n["id"],
            compute_capacity=n.get("compute_capacity", 100),
            position=Position(0, 0)
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

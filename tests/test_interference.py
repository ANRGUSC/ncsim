"""Unit tests for interference models."""

import pytest

from ncsim.models.network import Node, Link, Network, Position
from ncsim.models.interference import (
    NoInterference,
    ProximityInterference,
    CsmaCliqueInterference,
    CsmaBianchiInterference,
    create_interference_model,
)
from ncsim.models.wifi import (
    RFConfig,
    build_conflict_graph,
    compute_link_phy_rates,
    ConflictGraph,
    bianchi_efficiency,
)


# ─── Helpers ──────────────────────────────────────────────────────

def _make_positioned_network(node_specs, link_specs):
    """Build a Network from simplified specs.

    node_specs: list of (id, x, y)
    link_specs: list of (id, from, to, bandwidth)
    """
    nodes = {}
    for nid, x, y in node_specs:
        nodes[nid] = Node(nid, 100, Position(x, y))
    links = {}
    for lid, fn, tn, bw in link_specs:
        links[lid] = Link(lid, fn, tn, bw, 0.0)
    return Network(nodes=nodes, links=links)


# ─── NoInterference ──────────────────────────────────────────────

class TestNoInterference:
    def test_factor_is_1(self):
        model = NoInterference()
        net = _make_positioned_network(
            [("n0", 0, 0), ("n1", 5, 0)],
            [("l01", "n0", "n1", 100)],
        )
        assert model.get_interference_factor("l01", {"l01"}, net) == 1.0

    def test_affected_links_empty(self):
        model = NoInterference()
        net = _make_positioned_network(
            [("n0", 0, 0), ("n1", 5, 0)],
            [("l01", "n0", "n1", 100)],
        )
        assert model.get_affected_links("l01", {"l01"}, net) == set()


# ─── ProximityInterference ───────────────────────────────────────

class TestProximityInterference:
    def test_default_radius(self):
        model = ProximityInterference()
        assert model.interference_radius == 10.0

    def test_custom_radius(self):
        model = ProximityInterference(interference_radius=25.0)
        assert model.interference_radius == 25.0

    def test_single_link_factor_1(self):
        model = ProximityInterference(interference_radius=50.0)
        net = _make_positioned_network(
            [("n0", 0, 0), ("n1", 5, 0)],
            [("l01", "n0", "n1", 100)],
        )
        f = model.get_interference_factor("l01", {"l01"}, net)
        assert f == 1.0

    def test_two_nearby_links_factor_half(self):
        """Two nearby active links => each gets factor 0.5."""
        model = ProximityInterference(interference_radius=50.0)
        net = _make_positioned_network(
            [("n0", 0, 0), ("n1", 5, 0), ("n2", 1, 0), ("n3", 6, 0)],
            [("l01", "n0", "n1", 100), ("l23", "n2", "n3", 100)],
        )
        f = model.get_interference_factor("l01", {"l01", "l23"}, net)
        assert abs(f - 0.5) < 1e-9

    def test_three_nearby_links_factor_third(self):
        """Three nearby active links => factor 1/3."""
        model = ProximityInterference(interference_radius=50.0)
        net = _make_positioned_network(
            [("n0", 0, 0), ("n1", 5, 0),
             ("n2", 1, 0), ("n3", 6, 0),
             ("n4", 2, 0), ("n5", 7, 0)],
            [("l01", "n0", "n1", 100),
             ("l23", "n2", "n3", 100),
             ("l45", "n4", "n5", 100)],
        )
        f = model.get_interference_factor("l01", {"l01", "l23", "l45"}, net)
        assert abs(f - 1.0 / 3) < 1e-9

    def test_distant_link_no_interference(self):
        """A link beyond radius doesn't interfere."""
        model = ProximityInterference(interference_radius=5.0)
        net = _make_positioned_network(
            [("n0", 0, 0), ("n1", 2, 0), ("n2", 100, 0), ("n3", 102, 0)],
            [("l01", "n0", "n1", 100), ("l23", "n2", "n3", 100)],
        )
        f = model.get_interference_factor("l01", {"l01", "l23"}, net)
        assert f == 1.0  # only l01 is within radius of l01

    def test_inactive_link_factor_1(self):
        """If link is not in active set, factor = 1.0."""
        model = ProximityInterference(interference_radius=50.0)
        net = _make_positioned_network(
            [("n0", 0, 0), ("n1", 5, 0)],
            [("l01", "n0", "n1", 100)],
        )
        f = model.get_interference_factor("l01", set(), net)
        assert f == 1.0

    def test_affected_links_within_radius(self):
        model = ProximityInterference(interference_radius=50.0)
        net = _make_positioned_network(
            [("n0", 0, 0), ("n1", 5, 0), ("n2", 1, 0), ("n3", 6, 0)],
            [("l01", "n0", "n1", 100), ("l23", "n2", "n3", 100)],
        )
        affected = model.get_affected_links("l01", {"l01", "l23"}, net)
        assert "l23" in affected

    def test_affected_excludes_self(self):
        model = ProximityInterference(interference_radius=50.0)
        net = _make_positioned_network(
            [("n0", 0, 0), ("n1", 5, 0), ("n2", 1, 0), ("n3", 6, 0)],
            [("l01", "n0", "n1", 100), ("l23", "n2", "n3", 100)],
        )
        affected = model.get_affected_links("l01", {"l01", "l23"}, net)
        assert "l01" not in affected


# ─── CsmaCliqueInterference ─────────────────────────────────────

class TestCsmaCliqueInterference:
    def test_factor_always_1(self):
        cg = ConflictGraph(conflicts={"l01": set()}, max_clique_sizes={"l01": 1})
        model = CsmaCliqueInterference(conflict_graph=cg)
        net = _make_positioned_network(
            [("n0", 0, 0), ("n1", 5, 0)],
            [("l01", "n0", "n1", 100)],
        )
        assert model.get_interference_factor("l01", {"l01"}, net) == 1.0

    def test_affected_links_empty(self):
        cg = ConflictGraph(conflicts={"l01": set()}, max_clique_sizes={"l01": 1})
        model = CsmaCliqueInterference(conflict_graph=cg)
        net = _make_positioned_network(
            [("n0", 0, 0), ("n1", 5, 0)],
            [("l01", "n0", "n1", 100)],
        )
        assert model.get_affected_links("l01", {"l01"}, net) == set()


# ─── CsmaBianchiInterference ────────────────────────────────────

class TestCsmaBianchiInterference:
    """Tests for CsmaBianchiInterference with a small WiFi network."""

    @pytest.fixture
    def wifi_setup(self):
        """3-node WiFi network with 2 links, close enough to conflict."""
        net = _make_positioned_network(
            [("n0", 0, 0), ("n1", 10, 0), ("n2", 20, 0)],
            [("l01", "n0", "n1", 1.0), ("l12", "n1", "n2", 1.0)],
        )
        rf = RFConfig()
        shadow_map = {}
        cg = build_conflict_graph(net, rf, shadow_map)
        phy_rates = compute_link_phy_rates(net, rf, shadow_map)

        # Set link bandwidths to PHY rates (as main.py does for csma_bianchi)
        for lid, rate in phy_rates.items():
            net.links[lid].bandwidth = max(rate, 0.001)

        model = CsmaBianchiInterference(
            conflict_graph=cg,
            rf_config=rf,
            network=net,
            shadow_fading_map=shadow_map,
        )
        return model, net, cg

    def test_single_link_factor_near_1(self, wifi_setup):
        """Single active link -> factor ~ bianchi_efficiency(1)."""
        model, net, cg = wifi_setup
        f = model.get_interference_factor("l01", {"l01"}, net)
        expected = bianchi_efficiency(1) / 1
        assert abs(f - expected) < 0.01

    def test_two_contending_links_factor_less_1(self, wifi_setup):
        """Two contending active links -> factor < 1.0."""
        model, net, cg = wifi_setup
        f = model.get_interference_factor("l01", {"l01", "l12"}, net)
        assert f < 1.0

    def test_inactive_link_factor_1(self, wifi_setup):
        """If link is not active, factor = 1.0."""
        model, net, cg = wifi_setup
        f = model.get_interference_factor("l01", {"l12"}, net)
        assert f == 1.0

    def test_factor_clamped_to_range(self, wifi_setup):
        """Factor should be in [0.01, 1.0]."""
        model, net, cg = wifi_setup
        f = model.get_interference_factor("l01", {"l01", "l12"}, net)
        assert 0.01 <= f <= 1.0

    def test_affected_links_returns_all_others(self, wifi_setup):
        """affected_links returns all active links except self."""
        model, net, cg = wifi_setup
        affected = model.get_affected_links("l01", {"l01", "l12"}, net)
        assert affected == {"l12"}


# ─── create_interference_model factory ───────────────────────────

class TestCreateInterferenceModel:
    def test_none_returns_no_interference(self):
        model = create_interference_model("none")
        assert isinstance(model, NoInterference)

    def test_proximity_default_radius(self):
        model = create_interference_model("proximity")
        assert isinstance(model, ProximityInterference)
        assert model.interference_radius == 10.0

    def test_proximity_custom_radius(self):
        model = create_interference_model("proximity", interference_radius=25.0)
        assert isinstance(model, ProximityInterference)
        assert model.interference_radius == 25.0

    def test_csma_clique_with_conflict_graph(self):
        cg = ConflictGraph(conflicts={}, max_clique_sizes={})
        model = create_interference_model("csma_clique", conflict_graph=cg)
        assert isinstance(model, CsmaCliqueInterference)

    def test_csma_bianchi_with_all_kwargs(self):
        net = _make_positioned_network(
            [("n0", 0, 0), ("n1", 10, 0)],
            [("l01", "n0", "n1", 1.0)],
        )
        rf = RFConfig()
        cg = build_conflict_graph(net, rf, {})
        model = create_interference_model(
            "csma_bianchi",
            conflict_graph=cg,
            rf_config=rf,
            network=net,
        )
        assert isinstance(model, CsmaBianchiInterference)

    def test_unknown_type_raises_valueerror(self):
        with pytest.raises(ValueError, match="Unknown interference model"):
            create_interference_model("magic")

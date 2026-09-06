"""Unit tests for interference models."""

import pytest

from ncsim.models.network import Node, Link, Network, Position
from ncsim.models.interference import (
    NoInterference,
    Solo80211Interference,
    ProximityInterference,
    CsmaCliqueInterference,
    CsmaBianchiInterference,
    WirelessOutageError,
    canonicalize_wireless_mode,
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

        # This low-level fixture installs PHY rates directly; canonical setup
        # tests below verify MAC-normalized solo and full modes.
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
        """Single active link is already MAC-normalized by setup."""
        model, net, cg = wifi_setup
        f = model.get_interference_factor("l01", {"l01"}, net)
        assert f == pytest.approx(1.0)

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
        """A feasible factor stays in [0, 1] without a positive clamp."""
        model, net, cg = wifi_setup
        f = model.get_interference_factor("l01", {"l01", "l12"}, net)
        assert 0.0 <= f <= 1.0

    def test_affected_links_returns_all_others(self, wifi_setup):
        """A conflicting active neighbor is causally affected."""
        model, net, cg = wifi_setup
        affected = model.get_affected_links("l01", {"l01", "l12"}, net)
        assert affected == {"l12"}


class TestCanonicalWirelessModes:
    def test_legacy_aliases_are_canonicalized(self):
        assert canonicalize_wireless_mode("none") == "raw_phy"
        assert canonicalize_wireless_mode("csma_bianchi") == "full_wireless"
        assert canonicalize_wireless_mode("solo_80211") == "solo_80211"

    def test_solo_and_full_have_same_single_link_goodput(self):
        net = _make_positioned_network(
            [("tx", 0, 0), ("rx", 30, 0)],
            [("link", "tx", "rx", 1.0)],
        )
        rf = RFConfig()
        phy_rate = compute_link_phy_rates(net, rf)["link"]
        net.links["link"].bandwidth = phy_rate
        graph = ConflictGraph(
            conflicts={"link": set()}, max_clique_sizes={"link": 1}
        )
        solo = Solo80211Interference()
        full = CsmaBianchiInterference(graph, rf, net)
        active = {"link"}
        assert solo.get_interference_factor("link", active, net) == pytest.approx(
            full.get_interference_factor("link", active, net)
        )
        assert full.get_interference_factor("link", active, net) == pytest.approx(1.0)

    @pytest.fixture
    def hidden_setup(self):
        net = _make_positioned_network(
            [
                ("a_tx", 0, 0), ("a_rx", 30, 0),
                ("mid_tx", 30, 70), ("mid_rx", 60, 70),
                ("strong_tx", 30, 10), ("strong_rx", 60, 10),
                ("far_tx", 1000, 1000), ("far_rx", 1030, 1000),
            ],
            [
                ("a", "a_tx", "a_rx", 1.0),
                ("mid", "mid_tx", "mid_rx", 1.0),
                ("strong", "strong_tx", "strong_rx", 1.0),
                ("far", "far_tx", "far_rx", 1.0),
            ],
        )
        rf = RFConfig(interference_cutoff_dBm=-105.0)
        rates = compute_link_phy_rates(net, rf)
        for link_id, rate in rates.items():
            net.links[link_id].bandwidth = rate
        graph = ConflictGraph(
            conflicts={link_id: set() for link_id in net.links},
            max_clique_sizes={link_id: 1 for link_id in net.links},
        )
        return net, rf, graph

    def test_hidden_sinr_reselects_lower_effective_mcs(self, hidden_setup):
        net, rf, graph = hidden_setup
        model = CsmaBianchiInterference(graph, rf, net)
        factor = model.get_interference_factor("a", {"a", "mid"}, net)
        assert 0.0 < factor < 1.0

    def test_below_minimum_mcs_returns_zero_service(self, hidden_setup):
        net, rf, graph = hidden_setup
        model = CsmaBianchiInterference(graph, rf, net)
        assert model.get_interference_factor("a", {"a", "strong"}, net) == 0.0

    def test_diagnostic_floor_is_opt_in(self, hidden_setup):
        net, rf, graph = hidden_setup
        model = CsmaBianchiInterference(
            graph, rf, net, outage_floor_factor=0.02
        )
        factor = model.get_interference_factor("a", {"a", "strong"}, net)
        assert factor == pytest.approx(0.02)

    def test_local_dependency_excludes_irrelevant_far_link(self, hidden_setup):
        net, rf, graph = hidden_setup
        model = CsmaBianchiInterference(graph, rf, net)
        active = {"a", "mid", "far"}
        assert model.get_affected_links("mid", active, net) == {"a"}
        assert "a" not in model.get_affected_links("far", active, net)

    def test_component_ablation_preserves_solo_overhead(self, hidden_setup):
        net, rf, graph = hidden_setup
        hidden_only = CsmaBianchiInterference(
            graph, rf, net, contention_enabled=False
        )
        no_hidden_activity = hidden_only.get_interference_factor("a", {"a"}, net)
        assert no_hidden_activity == pytest.approx(1.0)


# ─── create_interference_model factory ───────────────────────────

class TestCreateInterferenceModel:
    def test_none_returns_no_interference(self):
        model = create_interference_model("none")
        assert isinstance(model, NoInterference)

    def test_solo_80211_returns_mac_normalized_model(self):
        model = create_interference_model("solo_80211")
        assert isinstance(model, Solo80211Interference)

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

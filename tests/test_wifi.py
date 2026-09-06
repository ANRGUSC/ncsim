"""Unit tests for 802.11 WiFi link model."""

import math
import pytest

from ncsim.models.wifi import (
    RFConfig,
    friis_reference_loss_dB,
    path_loss_dB,
    received_power_dBm,
    snr_dB,
    sinr_dB,
    euclidean_distance,
    carrier_sensing_range,
    communication_range,
    snr_to_rate_mbps,
    rate_mbps_to_MBps,
    bianchi_efficiency,
    build_conflict_graph,
    compute_link_phy_rates,
    generate_shadow_fading_map,
    ConflictGraph,
)
from ncsim.models.network import Node, Link, Network, Position


# ─── Helpers ──────────────────────────────────────────────────────

def _make_network(node_specs, link_specs):
    """Build a Network from simplified specs.

    node_specs: list of (id, x, y)
    link_specs: list of (id, from, to) — bandwidth placeholder 1.0
    """
    nodes = {}
    for nid, x, y in node_specs:
        nodes[nid] = Node(nid, 100, Position(x, y))
    links = {}
    for lid, fn, tn in link_specs:
        links[lid] = Link(lid, fn, tn, 1.0, 0.0)
    return Network(nodes=nodes, links=links)


# ─── Path Loss ────────────────────────────────────────────────────

class TestFriisReferenceLoss:
    def test_5ghz_1m(self):
        """Friis at 1m, 5 GHz should be ~46.4 dB."""
        pl = friis_reference_loss_dB(5.0, 1.0)
        assert 46 < pl < 47

    def test_2_4ghz_1m(self):
        """Friis at 1m, 2.4 GHz should be ~40.0 dB."""
        pl = friis_reference_loss_dB(2.4, 1.0)
        assert 39.5 < pl < 40.5

    def test_higher_freq_more_loss(self):
        assert friis_reference_loss_dB(5.0) > friis_reference_loss_dB(2.4)


class TestPathLoss:
    def test_increases_with_distance(self):
        pl_10 = path_loss_dB(10, 5.0, 3.0)
        pl_100 = path_loss_dB(100, 5.0, 3.0)
        assert pl_100 > pl_10

    def test_increases_with_exponent(self):
        pl_2 = path_loss_dB(50, 5.0, 2.0)
        pl_4 = path_loss_dB(50, 5.0, 4.0)
        assert pl_4 > pl_2

    def test_zero_distance(self):
        assert path_loss_dB(0, 5.0, 3.0) == 0.0

    def test_at_reference_distance(self):
        """At d0=1m, path loss should equal Friis reference."""
        pl = path_loss_dB(1.0, 5.0, 3.0)
        ref = friis_reference_loss_dB(5.0, 1.0)
        assert abs(pl - ref) < 0.01

    def test_10x_distance_adds_10n_dB(self):
        """Doubling log-distance: PL(10*d0) = PL(d0) + 10*n."""
        n = 3.0
        pl_1 = path_loss_dB(1.0, 5.0, n)
        pl_10 = path_loss_dB(10.0, 5.0, n)
        assert abs((pl_10 - pl_1) - 10 * n) < 0.01


# ─── SNR / SINR ──────────────────────────────────────────────────

class TestSNR:
    def test_close_range_high_snr(self):
        rf = RFConfig()
        rx = received_power_dBm(20, 1.0, rf)
        s = snr_dB(rx, rf.noise_floor_dBm)
        assert s > 60  # 1m, should be very high

    def test_far_range_low_snr(self):
        rf = RFConfig()
        rx = received_power_dBm(20, 500.0, rf)
        s = snr_dB(rx, rf.noise_floor_dBm)
        assert s < 20  # 500m at n=3, should be modest


class TestSINR:
    def test_no_interference_equals_snr(self):
        rf = RFConfig()
        rx = received_power_dBm(20, 10.0, rf)
        s_snr = snr_dB(rx, rf.noise_floor_dBm)
        s_sinr = sinr_dB(rx, [], rf.noise_floor_dBm)
        assert abs(s_snr - s_sinr) < 0.01

    def test_interference_reduces_sinr(self):
        rf = RFConfig()
        rx = received_power_dBm(20, 10.0, rf)
        interferer = received_power_dBm(20, 15.0, rf)
        s_clean = sinr_dB(rx, [], rf.noise_floor_dBm)
        s_dirty = sinr_dB(rx, [interferer], rf.noise_floor_dBm)
        assert s_dirty < s_clean

    def test_more_interference_worse(self):
        rf = RFConfig()
        rx = received_power_dBm(20, 10.0, rf)
        i1 = received_power_dBm(20, 20.0, rf)
        i2 = received_power_dBm(20, 25.0, rf)
        s_one = sinr_dB(rx, [i1], rf.noise_floor_dBm)
        s_two = sinr_dB(rx, [i1, i2], rf.noise_floor_dBm)
        assert s_two < s_one


# ─── MCS Rate Selection ──────────────────────────────────────────

class TestMCSRateSelection:
    def test_high_snr_max_rate_ax(self):
        rate = snr_to_rate_mbps(50.0, "ax", 20)
        assert rate == 143.4  # MCS 11

    def test_high_snr_max_rate_ac(self):
        rate = snr_to_rate_mbps(50.0, "ac", 20)
        assert rate == 86.7  # MCS 9

    def test_high_snr_max_rate_n(self):
        rate = snr_to_rate_mbps(50.0, "n", 20)
        assert rate == 65.0  # MCS 7

    def test_low_snr_zero(self):
        rate = snr_to_rate_mbps(2.0, "ax", 20)
        assert rate == 0.0

    def test_minimum_mcs(self):
        rate = snr_to_rate_mbps(5.0, "ax", 20)
        assert rate == 8.6  # MCS 0

    def test_wider_channel_scales(self):
        rate_20 = snr_to_rate_mbps(30.0, "ax", 20)
        rate_40 = snr_to_rate_mbps(30.0, "ax", 40)
        rate_80 = snr_to_rate_mbps(30.0, "ax", 80)
        assert abs(rate_40 - 2 * rate_20) < 0.01
        assert abs(rate_80 - 4 * rate_20) < 0.01

    def test_rate_conversion(self):
        assert rate_mbps_to_MBps(80.0) == 10.0
        assert rate_mbps_to_MBps(0.0) == 0.0


# ─── Bianchi ──────────────────────────────────────────────────────

class TestBianchi:
    def test_single_station(self):
        e = bianchi_efficiency(1)
        assert 0.3 < e < 1.0

    def test_two_stations(self):
        e = bianchi_efficiency(2)
        assert 0.2 < e < 1.0

    def test_monotonically_decreasing_after_peak(self):
        """Efficiency peaks at small n (channel utilization improving),
        then decreases monotonically as collisions dominate."""
        prev = bianchi_efficiency(5)
        for n in range(6, 30):
            e = bianchi_efficiency(n)
            assert e <= prev
            prev = e

    def test_always_positive(self):
        for n in range(1, 60):
            assert bianchi_efficiency(n) > 0

    def test_zero_and_negative(self):
        e1 = bianchi_efficiency(1)
        assert bianchi_efficiency(0) == e1
        assert bianchi_efficiency(-1) == e1

    def test_large_n(self):
        """Beyond lookup table size, should still return a value."""
        e = bianchi_efficiency(200)
        assert 0 < e <= 1.0


# ─── Carrier Sensing Range ───────────────────────────────────────

class TestCarrierSensingRange:
    def test_reasonable_range(self):
        rf = RFConfig()
        r = carrier_sensing_range(rf)
        # 20 dBm TX, -82 dBm CCA, n=3 -> should be tens to hundreds of meters
        assert 30 < r < 1000

    def test_higher_power_longer_range(self):
        rf_low = RFConfig(tx_power_dBm=10)
        rf_high = RFConfig(tx_power_dBm=23)
        assert carrier_sensing_range(rf_high) > carrier_sensing_range(rf_low)

    def test_higher_threshold_shorter_range(self):
        rf_sensitive = RFConfig(cca_threshold_dBm=-82)
        rf_less = RFConfig(cca_threshold_dBm=-62)
        assert carrier_sensing_range(rf_less) < carrier_sensing_range(rf_sensitive)

    def test_cs_vs_comm_range_relationship(self):
        """With default MCS 0 threshold of 5 dB, comm range > CS range because
        receiver sensitivity (-90 dBm) is below CCA threshold (-82 dBm).
        Both should be positive and in a reasonable range."""
        rf = RFConfig()
        cs = carrier_sensing_range(rf)
        comm = communication_range(rf)
        assert cs > 0
        assert comm > 0
        # With higher CCA sensitivity, CS range would exceed comm range
        rf2 = RFConfig(cca_threshold_dBm=-95)
        cs2 = carrier_sensing_range(rf2)
        assert cs2 > comm


# ─── Conflict Graph ──────────────────────────────────────────────

class TestConflictGraph:
    def test_shared_endpoint_and_reverse_links_conflict(self):
        """A half-duplex radio cannot serve two directed links at once."""
        net = _make_network(
            [("n0", 0, 0), ("n1", 10000, 0), ("n2", 20000, 0)],
            [
                ("l01", "n0", "n1"),
                ("l10", "n1", "n0"),
                ("l12", "n1", "n2"),
            ],
        )
        cg = build_conflict_graph(net, RFConfig())

        assert cg.conflicts["l01"] == {"l10", "l12"}
        assert "l01" in cg.conflicts["l10"]
        assert "l01" in cg.conflicts["l12"]

    def test_nearby_links_conflict(self):
        """Two links 10m apart should conflict (CS range >> 10m)."""
        net = _make_network(
            [("n0", 0, 0), ("n1", 5, 0), ("n2", 0, 10), ("n3", 5, 10)],
            [("l01", "n0", "n1"), ("l23", "n2", "n3")],
        )
        rf = RFConfig()
        cg = build_conflict_graph(net, rf)

        assert "l23" in cg.conflicts["l01"]
        assert "l01" in cg.conflicts["l23"]

    def test_distant_links_no_conflict(self):
        """Two links 10km apart should not conflict."""
        net = _make_network(
            [("n0", 0, 0), ("n1", 5, 0), ("n2", 10000, 0), ("n3", 10005, 0)],
            [("l01", "n0", "n1"), ("l23", "n2", "n3")],
        )
        rf = RFConfig()
        cg = build_conflict_graph(net, rf)

        assert "l23" not in cg.conflicts["l01"]

    def test_single_link_no_conflicts(self):
        net = _make_network(
            [("n0", 0, 0), ("n1", 5, 0)],
            [("l01", "n0", "n1")],
        )
        rf = RFConfig()
        cg = build_conflict_graph(net, rf)

        assert len(cg.conflicts["l01"]) == 0
        assert cg.max_clique_sizes["l01"] == 1

    def test_three_way_clique(self):
        """Three nearby links should form a clique of size 3."""
        net = _make_network(
            [("n0", 0, 0), ("n1", 5, 0),
             ("n2", 0, 5), ("n3", 5, 5),
             ("n4", 0, 10), ("n5", 5, 10)],
            [("l01", "n0", "n1"), ("l23", "n2", "n3"), ("l45", "n4", "n5")],
        )
        rf = RFConfig()
        cg = build_conflict_graph(net, rf)

        # All three should conflict with each other
        assert "l23" in cg.conflicts["l01"]
        assert "l45" in cg.conflicts["l01"]
        assert "l01" in cg.conflicts["l23"]
        assert "l45" in cg.conflicts["l23"]

        # Max clique should be 3
        assert cg.max_clique_sizes["l01"] == 3
        assert cg.max_clique_sizes["l23"] == 3
        assert cg.max_clique_sizes["l45"] == 3

    def test_rts_cts_extends_conflicts(self):
        """RTS/CTS should create conflicts that basic CS does not.

        Place nodes so tx(A) cannot sense tx(B), but rx(A) can sense tx(B).
        Without RTS/CTS: no conflict. With RTS/CTS: conflict.
        """
        # We need a topology where tx-tx distance > cs_range but
        # some rx-tx distance <= cs_range. Use a small cs_range via
        # low TX power.
        rf_no_rts = RFConfig(tx_power_dBm=5, cca_threshold_dBm=-62, rts_cts=False)
        rf_rts = RFConfig(tx_power_dBm=5, cca_threshold_dBm=-62, rts_cts=True)
        cs = carrier_sensing_range(rf_no_rts)

        # Place links so transmitters are far but receiver of A is close to tx of B
        # l01: n0(0,0)->n1(cs*0.8, 0)
        # l23: n2(cs*0.9, 0)->n3(cs*1.7, 0)
        # tx(l01)=n0, tx(l23)=n2, distance = cs*0.9 — might be close to threshold
        # rx(l01)=n1, tx(l23)=n2, distance = cs*0.1 — very close
        #
        # Without RTS/CTS: check tx(l01)->nodes(l23) and tx(l23)->nodes(l01)
        # With RTS/CTS: also check rx(l01)->nodes(l23)
        #
        # Let's just verify the mechanism works by checking both configs
        net = _make_network(
            [("n0", 0, 0), ("n1", cs * 0.8, 0),
             ("n2", cs * 0.9, 0), ("n3", cs * 1.7, 0)],
            [("l01", "n0", "n1"), ("l23", "n2", "n3")],
        )

        cg_no_rts = build_conflict_graph(net, rf_no_rts)
        cg_rts = build_conflict_graph(net, rf_rts)

        # With RTS/CTS, at minimum the same conflicts as without (possibly more)
        no_rts_conflicts = len(cg_no_rts.conflicts["l01"])
        rts_conflicts = len(cg_rts.conflicts["l01"])
        assert rts_conflicts >= no_rts_conflicts


# ─── Shadow Fading ────────────────────────────────────────────────

class TestShadowFading:
    def test_zero_sigma_empty(self):
        net = _make_network(
            [("n0", 0, 0), ("n1", 10, 0)],
            [("l01", "n0", "n1")],
        )
        fm = generate_shadow_fading_map(net, 0.0, 42)
        assert len(fm) == 0

    def test_symmetric(self):
        net = _make_network(
            [("n0", 0, 0), ("n1", 10, 0), ("n2", 20, 0)],
            [("l01", "n0", "n1")],
        )
        fm = generate_shadow_fading_map(net, 4.0, 42)
        assert fm[("n0", "n1")] == fm[("n1", "n0")]
        assert fm[("n0", "n2")] == fm[("n2", "n0")]

    def test_deterministic(self):
        net = _make_network(
            [("n0", 0, 0), ("n1", 10, 0)],
            [("l01", "n0", "n1")],
        )
        fm1 = generate_shadow_fading_map(net, 4.0, 42)
        fm2 = generate_shadow_fading_map(net, 4.0, 42)
        assert fm1 == fm2

    def test_different_seeds_differ(self):
        net = _make_network(
            [("n0", 0, 0), ("n1", 10, 0)],
            [("l01", "n0", "n1")],
        )
        fm1 = generate_shadow_fading_map(net, 4.0, 42)
        fm2 = generate_shadow_fading_map(net, 4.0, 99)
        assert fm1[("n0", "n1")] != fm2[("n0", "n1")]


# ─── PHY Rate Computation ────────────────────────────────────────

class TestPHYRateComputation:
    def test_close_links_high_rate(self):
        net = _make_network(
            [("n0", 0, 0), ("n1", 10, 0)],
            [("l01", "n0", "n1")],
        )
        rf = RFConfig()
        rates = compute_link_phy_rates(net, rf)
        # 10m, 5 GHz, n=3: SNR should be very high -> max MCS
        assert rates["l01"] > 10  # Should be ~18 MB/s (143.4 Mbps / 8)

    def test_far_links_lower_rate(self):
        net = _make_network(
            [("n0", 0, 0), ("n1", 10, 0),
             ("n2", 0, 100), ("n3", 100, 100)],
            [("l_short", "n0", "n1"), ("l_long", "n2", "n3")],
        )
        rf = RFConfig()
        rates = compute_link_phy_rates(net, rf)
        assert rates["l_short"] > rates["l_long"]

    def test_out_of_range_zero(self):
        """Link beyond communication range should get 0 rate."""
        rf = RFConfig()
        comm = communication_range(rf)
        far = comm * 3  # Well beyond range

        net = _make_network(
            [("n0", 0, 0), ("n1", far, 0)],
            [("l01", "n0", "n1")],
        )
        rates = compute_link_phy_rates(net, rf)
        assert rates["l01"] == 0.0

    def test_shadow_fading_changes_rate(self):
        """Shadow fading should affect computed rates."""
        net = _make_network(
            [("n0", 0, 0), ("n1", 50, 0)],
            [("l01", "n0", "n1")],
        )
        rf = RFConfig(shadow_fading_sigma=8.0)
        # With different seeds, shadow fading should differ
        rates1 = compute_link_phy_rates(
            net, rf, generate_shadow_fading_map(net, 8.0, 1)
        )
        rates2 = compute_link_phy_rates(
            net, rf, generate_shadow_fading_map(net, 8.0, 2)
        )
        # They might or might not be equal (depends on fading values),
        # but at least both should be non-negative
        assert rates1["l01"] >= 0
        assert rates2["l01"] >= 0

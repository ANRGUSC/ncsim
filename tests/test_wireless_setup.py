"""Tests for canonical wireless comparison setup."""

import pytest

from ncsim.models.network import Link, Network, Node, Position
from ncsim.models.wifi import RFConfig, bianchi_efficiency
from ncsim.models.wireless import configure_wireless


def _network():
    return Network(
        nodes={
            "tx": Node("tx", 1.0, Position(0, 0)),
            "rx": Node("rx", 1.0, Position(30, 0)),
        },
        links={"l": Link("l", "tx", "rx", 1.0)},
    )


def test_solo_and_full_install_identical_clean_matrix():
    solo_network = _network()
    full_network = _network()
    solo = configure_wireless(solo_network, "solo_80211")
    full = configure_wireless(full_network, "full_wireless")
    assert solo_network.links["l"].bandwidth == pytest.approx(
        full_network.links["l"].bandwidth
    )
    assert solo_network.links["l"].bandwidth == pytest.approx(
        solo.raw_phy_rates_MBps["l"] * bianchi_efficiency(
            1, solo.raw_phy_rates_MBps["l"] * 8
        )
    )


def test_raw_phy_is_diagnostic_reference_without_mac_overhead():
    network = _network()
    setup = configure_wireless(network, "none")
    assert setup.requested_mode == "none"
    assert setup.canonical_mode == "raw_phy"
    assert network.links["l"].bandwidth == pytest.approx(
        setup.raw_phy_rates_MBps["l"]
    )


def test_ablation_and_outage_policy_are_recorded():
    setup = configure_wireless(
        _network(),
        "full_wireless",
        rf_config=RFConfig(capture_margin_dB=3.0),
        components="hidden-only",
        outage_floor_factor=0.02,
    )
    assert setup.metadata["wireless_components"] == "hidden-only"
    assert setup.metadata["outage_policy"] == "diagnostic_floor"
    assert setup.metadata["rf_config"]["capture_margin_dB"] == 3.0

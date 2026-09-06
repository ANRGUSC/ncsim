"""MAC/PHY predictions shared by retained validation analyses."""
from ncsim.models.interference import WirelessOutageError
from ncsim.models.network import Link, Network, Node, Position
from ncsim.models.wifi import RFConfig, bianchi_efficiency
from ncsim.models.wireless import configure_wireless


def contention_predictions() -> dict[int, float]:
    raw_rate_MBps = 68.8 / 8.0
    return {
        n_links: raw_rate_MBps * bianchi_efficiency(n_links) / n_links
        for n_links in range(1, 9)
    }


def parallel_network(separations: list[float]) -> dict[float, dict[str, float | None]]:
    predictions = {}
    for separation in separations:
        network = Network(
            nodes={
                "a_tx": Node("a_tx", 1, Position(0, 0)),
                "a_rx": Node("a_rx", 1, Position(30, 0)),
                "b_tx": Node("b_tx", 1, Position(0, separation)),
                "b_rx": Node("b_rx", 1, Position(30, separation)),
            },
            links={
                "A": Link("A", "a_tx", "a_rx", 1.0),
                "B": Link("B", "b_tx", "b_rx", 1.0),
            },
        )
        setup = configure_wireless(network, "full_wireless", rf_config=RFConfig())
        rates = {}
        for link_id in ("A", "B"):
            try:
                factor = setup.interference_model.get_interference_factor(
                    link_id, {"A", "B"}, network
                )
                rates[link_id] = network.links[link_id].bandwidth * factor
            except WirelessOutageError:
                rates[link_id] = None
        predictions[separation] = rates
    return predictions


def asymmetric_prediction() -> dict:
    positions = {
        "a_tx": (0, 0), "a_rx": (30, 0),
        "b_tx": (0, 60), "b_rx": (30, 60),
        "c_tx": (0, 120), "c_rx": (30, 120),
    }
    network = Network(
        nodes={
            name: Node(name, 1, Position(*position))
            for name, position in positions.items()
        },
        links={
            "A": Link("A", "a_tx", "a_rx", 1.0),
            "B": Link("B", "b_tx", "b_rx", 1.0),
            "C": Link("C", "c_tx", "c_rx", 1.0),
        },
    )
    setup = configure_wireless(network, "full_wireless", rf_config=RFConfig())
    rates = {}
    for link_id in ("A", "B", "C"):
        try:
            factor = setup.interference_model.get_interference_factor(
                link_id, {"A", "B", "C"}, network
            )
            rates[link_id] = network.links[link_id].bandwidth * factor
        except WirelessOutageError:
            rates[link_id] = None
    solo = setup.solo_80211_rates_MBps["A"]
    feasibility = {
        "A_plus_B_over_solo": (
            (rates["A"] + rates["B"]) / solo
            if rates["A"] is not None and rates["B"] is not None else None
        ),
        "B_plus_C_over_solo": (
            (rates["B"] + rates["C"]) / solo
            if rates["B"] is not None and rates["C"] is not None else None
        ),
    }
    return {
        "per_link_MBps": rates,
        "aggregate_MBps": sum(rate for rate in rates.values() if rate is not None),
        "solo_MBps": solo,
        "conflicts": {
            key: sorted(value) for key, value in setup.conflict_graph.conflicts.items()
        },
        "feasibility_checks": feasibility,
    }

"""Tests for the failure trace generators (G1 single failure, G2 Gilbert-Elliott)."""

import pytest

from ncsim.models.disruptions import DisruptionType, ScheduledDisruptions
from ncsim.models.failure_traces import (
    gilbert_elliott_trace,
    radio_pairs,
    single_failure_trace,
)
from ncsim.models.network import Link, Network, Node


def make_network() -> Network:
    """Triangle of radio pairs (each modeled as two directed links)."""
    nodes = {f"n{i}": Node(id=f"n{i}", compute_capacity=100) for i in range(3)}
    links = {}
    for a, b in ((0, 1), (1, 2), (0, 2)):
        links[f"l{a}{b}"] = Link(
            id=f"l{a}{b}", from_node=f"n{a}", to_node=f"n{b}", bandwidth=100
        )
        links[f"l{b}{a}"] = Link(
            id=f"l{b}{a}", from_node=f"n{b}", to_node=f"n{a}", bandwidth=100
        )
    return Network(nodes=nodes, links=links)


class TestRadioPairs:
    def test_groups_directed_links_into_pairs(self):
        pairs = radio_pairs(make_network())
        assert len(pairs) == 3
        assert sorted(pairs[frozenset(("n0", "n1"))]) == ["l01", "l10"]

    def test_one_way_link_forms_a_singleton_pair(self):
        network = Network(
            nodes={"a": Node(id="a", compute_capacity=1), "b": Node(id="b", compute_capacity=1)},
            links={"ab": Link(id="ab", from_node="a", to_node="b", bandwidth=1)},
        )
        assert radio_pairs(network) == {frozenset(("a", "b")): ["ab"]}


class TestSingleFailure:
    def test_emits_both_directions(self):
        events = single_failure_trace(make_network(), ("n0", "n1"), time=1.0, duration=2.0)
        assert [e.target_id for e in events] == ["l01", "l10"]
        assert all(e.disruption_type == DisruptionType.LINK_DOWN for e in events)
        assert all(e.time == 1.0 and e.duration == 2.0 for e in events)

    def test_degrade_variant_carries_the_factor(self):
        events = single_failure_trace(
            make_network(), ("n1", "n2"), time=0.5, bandwidth_factor=0.25
        )
        assert all(e.disruption_type == DisruptionType.LINK_DEGRADE for e in events)
        assert all(e.parameters["bandwidth_factor"] == 0.25 for e in events)

    def test_unknown_pair_is_rejected(self):
        network = make_network()
        with pytest.raises(ValueError, match="No link between"):
            single_failure_trace(network, ("n0", "nX"), time=1.0)

    def test_feeds_scheduled_disruptions(self):
        """The generator output is directly consumable by the simulator."""
        events = single_failure_trace(make_network(), ("n0", "n1"), time=1.0)
        model = ScheduledDisruptions(events)
        first = model.get_next_disruption(0.0)
        assert first is not None and first.time == 1.0


class TestGilbertElliott:
    def test_same_seed_gives_identical_trace(self):
        network = make_network()
        a = gilbert_elliott_trace(network, mtbf=10.0, mttr=2.0, horizon=100.0, seed=7)
        b = gilbert_elliott_trace(network, mtbf=10.0, mttr=2.0, horizon=100.0, seed=7)
        assert [(e.time, e.target_id, e.duration) for e in a] == [
            (e.time, e.target_id, e.duration) for e in b
        ]

    def test_different_seeds_differ(self):
        network = make_network()
        a = gilbert_elliott_trace(network, mtbf=10.0, mttr=2.0, horizon=100.0, seed=1)
        b = gilbert_elliott_trace(network, mtbf=10.0, mttr=2.0, horizon=100.0, seed=2)
        assert [(e.time, e.target_id) for e in a] != [(e.time, e.target_id) for e in b]

    def test_events_come_in_direction_pairs_with_shared_timing(self):
        events = gilbert_elliott_trace(
            make_network(), mtbf=5.0, mttr=1.0, horizon=50.0, seed=3
        )
        assert events, "expected failures within the horizon"
        assert len(events) % 2 == 0
        for first, second in zip(events[0::2], events[1::2]):
            assert first.time == second.time
            assert first.duration == second.duration
            # The two directions of the same radio pair
            assert first.target_id != second.target_id

    def test_trace_is_time_ordered_and_within_horizon(self):
        events = gilbert_elliott_trace(
            make_network(), mtbf=3.0, mttr=1.0, horizon=30.0, seed=11
        )
        times = [e.time for e in events]
        assert times == sorted(times)
        assert all(0 <= t < 30.0 for t in times)
        assert all(e.duration is not None and e.duration > 0 for e in events)

    def test_failure_rate_tracks_mtbf(self):
        """Loose statistical check: expected failures per pair over the
        horizon is roughly horizon / (mtbf + mttr)."""
        mtbf, mttr, horizon = 10.0, 2.0, 2000.0
        events = gilbert_elliott_trace(
            make_network(), mtbf=mtbf, mttr=mttr, horizon=horizon, seed=5
        )
        failures_per_pair = (len(events) / 2) / 3  # pairs of events, 3 radio pairs
        expected = horizon / (mtbf + mttr)
        assert expected * 0.7 < failures_per_pair < expected * 1.3

    def test_pair_restriction(self):
        events = gilbert_elliott_trace(
            make_network(), mtbf=5.0, mttr=1.0, horizon=100.0, seed=3,
            pairs=[("n0", "n1")],
        )
        assert {e.target_id for e in events} == {"l01", "l10"}

    def test_pair_streams_are_independent_of_selection(self):
        """Restricting to one pair reproduces exactly that pair's stream from
        the full trace -- adding pairs never perturbs the others."""
        network = make_network()
        full = gilbert_elliott_trace(network, mtbf=5.0, mttr=1.0, horizon=100.0, seed=9)
        only = gilbert_elliott_trace(
            network, mtbf=5.0, mttr=1.0, horizon=100.0, seed=9, pairs=[("n0", "n1")]
        )
        full_restricted = [
            (e.time, e.target_id, e.duration)
            for e in full
            if e.target_id in ("l01", "l10")
        ]
        assert full_restricted == [(e.time, e.target_id, e.duration) for e in only]

    def test_rejects_nonpositive_parameters(self):
        with pytest.raises(ValueError):
            gilbert_elliott_trace(make_network(), mtbf=0, mttr=1, horizon=10)

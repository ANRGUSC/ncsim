"""Unit tests for disruption models."""

import pytest

from ncsim.models.disruptions import (
    DisruptionType,
    DisruptionEvent,
    NoDisruptions,
    ScheduledDisruptions,
)


class TestDisruptionType:
    """Tests for DisruptionType enum."""

    def test_all_six_values_exist(self):
        expected = {"LINK_DOWN", "LINK_DEGRADE", "NODE_DOWN", "NODE_DEGRADE", "JAMMING", "RECOVERY"}
        actual = {e.name for e in DisruptionType}
        assert actual == expected

    def test_values_are_distinct(self):
        values = [e.value for e in DisruptionType]
        assert len(values) == len(set(values))


class TestDisruptionEvent:
    """Tests for DisruptionEvent dataclass."""

    def test_valid_link_target(self):
        e = DisruptionEvent(
            time=1.0,
            target_type="link",
            target_id="l01",
            disruption_type=DisruptionType.LINK_DOWN,
        )
        assert e.target_type == "link"
        assert e.target_id == "l01"

    def test_valid_node_target(self):
        e = DisruptionEvent(
            time=2.0,
            target_type="node",
            target_id="n0",
            disruption_type=DisruptionType.NODE_DOWN,
        )
        assert e.target_type == "node"

    def test_rejects_invalid_target_type(self):
        with pytest.raises(ValueError, match="target_type must be"):
            DisruptionEvent(
                time=0.0,
                target_type="switch",
                target_id="x",
                disruption_type=DisruptionType.LINK_DOWN,
            )

    def test_default_duration_is_none(self):
        e = DisruptionEvent(
            time=0.0, target_type="link", target_id="l0",
            disruption_type=DisruptionType.LINK_DOWN,
        )
        assert e.duration is None

    def test_default_parameters_is_empty(self):
        e = DisruptionEvent(
            time=0.0, target_type="link", target_id="l0",
            disruption_type=DisruptionType.LINK_DOWN,
        )
        assert e.parameters == {}

    def test_stores_all_fields(self):
        e = DisruptionEvent(
            time=5.5,
            target_type="node",
            target_id="n1",
            disruption_type=DisruptionType.NODE_DEGRADE,
            duration=10.0,
            parameters={"capacity_factor": 0.5},
        )
        assert e.time == 5.5
        assert e.disruption_type == DisruptionType.NODE_DEGRADE
        assert e.duration == 10.0
        assert e.parameters == {"capacity_factor": 0.5}


class TestNoDisruptions:
    """Tests for NoDisruptions model."""

    def test_always_returns_none(self):
        model = NoDisruptions()
        assert model.get_next_disruption(0.0) is None
        assert model.get_next_disruption(100.0) is None
        assert model.get_next_disruption(999999.0) is None

    def test_reset_is_noop(self):
        model = NoDisruptions()
        model.reset()  # should not raise
        assert model.get_next_disruption(0.0) is None


class TestScheduledDisruptions:
    """Tests for ScheduledDisruptions model."""

    def _make_event(self, time, target_id="l0"):
        return DisruptionEvent(
            time=time,
            target_type="link",
            target_id=target_id,
            disruption_type=DisruptionType.LINK_DOWN,
        )

    def test_returns_in_time_order(self):
        """Unsorted input should be returned in sorted order."""
        events = [self._make_event(3.0, "l2"), self._make_event(1.0, "l0"), self._make_event(2.0, "l1")]
        model = ScheduledDisruptions(events)

        d1 = model.get_next_disruption(0.0)
        assert d1.target_id == "l0"
        d2 = model.get_next_disruption(0.0)
        assert d2.target_id == "l1"
        d3 = model.get_next_disruption(0.0)
        assert d3.target_id == "l2"

    def test_returns_none_when_exhausted(self):
        events = [self._make_event(1.0)]
        model = ScheduledDisruptions(events)
        model.get_next_disruption(0.0)
        assert model.get_next_disruption(0.0) is None

    def test_reset_restarts_sequence(self):
        events = [self._make_event(1.0)]
        model = ScheduledDisruptions(events)
        model.get_next_disruption(0.0)
        assert model.get_next_disruption(0.0) is None

        model.reset()
        d = model.get_next_disruption(0.0)
        assert d is not None
        assert d.time == 1.0

    def test_returns_none_when_disruption_time_before_current(self):
        """If current_time > disruption.time, should return None."""
        events = [self._make_event(1.0)]
        model = ScheduledDisruptions(events)
        # current_time=5.0 > disruption.time=1.0
        assert model.get_next_disruption(5.0) is None

    def test_empty_list_always_returns_none(self):
        model = ScheduledDisruptions([])
        assert model.get_next_disruption(0.0) is None
        assert model.get_next_disruption(100.0) is None

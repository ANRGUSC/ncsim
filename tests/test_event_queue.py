"""
Unit tests for the event queue.
"""

import pytest
from ncsim.core.event_queue import EventQueue, Event, EventType, round_time


class TestRoundTime:
    """Tests for round_time function."""

    def test_rounds_to_microseconds(self):
        assert round_time(1.1234567890) == 1.123457

    def test_preserves_exact_values(self):
        assert round_time(1.0) == 1.0
        assert round_time(0.0) == 0.0

    def test_handles_small_values(self):
        assert round_time(0.000001) == 0.000001
        assert round_time(0.0000001) == 0.0


class TestEvent:
    """Tests for Event class."""

    def test_creates_basic_event(self):
        event = Event(
            sim_time=1.0,
            event_type=EventType.TASK_START,
            event_id=0
        )
        assert event.sim_time == 1.0
        assert event.event_type == EventType.TASK_START
        assert event.event_id == 0

    def test_creates_event_with_all_fields(self):
        event = Event(
            sim_time=1.5,
            event_type=EventType.TRANSFER_START,
            event_id=5,
            dag_id="dag_1",
            task_id="T0",
            node_id="n0",
            link_id="l01",
            from_task="T0",
            to_task="T1",
            data={"size": 100}
        )
        assert event.dag_id == "dag_1"
        assert event.from_task == "T0"
        assert event.data["size"] == 100

    def test_sort_key_orders_by_time_first(self):
        e1 = Event(sim_time=1.0, event_type=EventType.TASK_START, event_id=0)
        e2 = Event(sim_time=2.0, event_type=EventType.TASK_START, event_id=1)
        assert e1.sort_key < e2.sort_key

    def test_sort_key_orders_by_priority_second(self):
        e1 = Event(sim_time=1.0, event_type=EventType.TASK_COMPLETE, event_id=0)  # priority 1
        e2 = Event(sim_time=1.0, event_type=EventType.TASK_START, event_id=1)  # priority 4
        assert e1.sort_key < e2.sort_key

    def test_sort_key_orders_by_event_id_third(self):
        e1 = Event(sim_time=1.0, event_type=EventType.TASK_START, event_id=0)
        e2 = Event(sim_time=1.0, event_type=EventType.TASK_START, event_id=1)
        assert e1.sort_key < e2.sort_key

    def test_comparison_operators(self):
        e1 = Event(sim_time=1.0, event_type=EventType.TASK_START, event_id=0)
        e2 = Event(sim_time=2.0, event_type=EventType.TASK_START, event_id=1)
        assert e1 < e2
        assert e1 <= e2


class TestEventQueue:
    """Tests for EventQueue class."""

    def test_creates_empty_queue(self):
        eq = EventQueue()
        assert eq.is_empty()
        assert len(eq) == 0

    def test_schedule_returns_event_id(self):
        eq = EventQueue()
        event_id = eq.schedule(1.0, EventType.TASK_START)
        assert event_id == 0

    def test_schedule_increments_event_id(self):
        eq = EventQueue()
        id1 = eq.schedule(1.0, EventType.TASK_START)
        id2 = eq.schedule(2.0, EventType.TASK_START)
        assert id2 == id1 + 1

    def test_pop_returns_earliest_event(self):
        eq = EventQueue()
        eq.schedule(2.0, EventType.TASK_START)
        eq.schedule(1.0, EventType.TASK_COMPLETE)
        event = eq.pop()
        assert event.sim_time == 1.0

    def test_pop_respects_priority_at_same_time(self):
        eq = EventQueue()
        # Schedule in reverse priority order
        eq.schedule(1.0, EventType.TASK_START)  # priority 4
        eq.schedule(1.0, EventType.TASK_COMPLETE)  # priority 1

        event = eq.pop()
        assert event.event_type == EventType.TASK_COMPLETE

    def test_pop_respects_fifo_at_same_time_and_priority(self):
        eq = EventQueue()
        id1 = eq.schedule(1.0, EventType.TASK_START, task_id="first")
        id2 = eq.schedule(1.0, EventType.TASK_START, task_id="second")

        event = eq.pop()
        assert event.task_id == "first"
        assert event.event_id == id1

    def test_pop_returns_none_when_empty(self):
        eq = EventQueue()
        assert eq.pop() is None

    def test_cancel_skips_event(self):
        eq = EventQueue()
        id1 = eq.schedule(1.0, EventType.TASK_START, task_id="first")
        eq.schedule(2.0, EventType.TASK_START, task_id="second")

        eq.cancel(id1)

        event = eq.pop()
        assert event.task_id == "second"

    def test_cancel_updates_length(self):
        eq = EventQueue()
        id1 = eq.schedule(1.0, EventType.TASK_START)
        assert len(eq) == 1

        eq.cancel(id1)
        assert len(eq) == 0

    def test_cancel_returns_false_for_already_cancelled(self):
        eq = EventQueue()
        event_id = eq.schedule(1.0, EventType.TASK_START)

        assert eq.cancel(event_id) is True
        assert eq.cancel(event_id) is False

    def test_peek_returns_next_event_without_removing(self):
        eq = EventQueue()
        eq.schedule(1.0, EventType.TASK_START)

        event = eq.peek()
        assert event is not None
        assert len(eq) == 1  # Still there

    def test_peek_skips_cancelled_events(self):
        eq = EventQueue()
        id1 = eq.schedule(1.0, EventType.TASK_START, task_id="first")
        eq.schedule(2.0, EventType.TASK_START, task_id="second")

        eq.cancel(id1)

        event = eq.peek()
        assert event.task_id == "second"

    def test_clear_removes_all_events(self):
        eq = EventQueue()
        eq.schedule(1.0, EventType.TASK_START)
        eq.schedule(2.0, EventType.TASK_START)

        eq.clear()

        assert eq.is_empty()
        assert len(eq) == 0

    def test_next_event_time(self):
        eq = EventQueue()
        eq.schedule(2.0, EventType.TASK_START)
        eq.schedule(1.0, EventType.TASK_COMPLETE)

        assert eq.next_event_time == 1.0

    def test_next_event_time_none_when_empty(self):
        eq = EventQueue()
        assert eq.next_event_time is None

    def test_iteration_preserves_order(self):
        eq = EventQueue()
        eq.schedule(3.0, EventType.TASK_START)
        eq.schedule(1.0, EventType.TASK_START)
        eq.schedule(2.0, EventType.TASK_START)

        times = [e.sim_time for e in eq]
        assert times == [1.0, 2.0, 3.0]


class TestEventTypePriority:
    """Tests for event type priorities."""

    def test_dag_inject_highest_priority(self):
        assert EventType.DAG_INJECT < EventType.TASK_COMPLETE

    def test_complete_before_ready(self):
        assert EventType.TASK_COMPLETE < EventType.TASK_READY
        assert EventType.TRANSFER_COMPLETE < EventType.TASK_READY

    def test_ready_before_start(self):
        assert EventType.TASK_READY < EventType.TASK_START

    def test_start_before_transfer_start(self):
        assert EventType.TASK_START < EventType.TRANSFER_START

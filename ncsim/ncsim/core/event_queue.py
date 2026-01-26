"""
Event queue implementation for discrete event simulation.

The event queue maintains events in priority order:
1. Primary: simulation time (microsecond precision)
2. Secondary: event type priority (lower = higher priority)
3. Tertiary: insertion order (FIFO for same time and priority)
"""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional, Iterator
import heapq


def round_time(t: float) -> float:
    """Round time to microsecond precision (6 decimal places).

    This ensures deterministic behavior by avoiding floating-point
    precision issues in time comparisons.
    """
    return round(t, 6)


class EventType(IntEnum):
    """Event types with their priority values.

    Lower values = higher priority (processed first at same sim_time).
    Order matters for correct simulation semantics:
    - DAG_INJECT first to set up initial state
    - TASK_COMPLETE before TRANSFER_COMPLETE (task must finish before output transfers)
    - TRANSFER_COMPLETE before TASK_READY (inputs must arrive before task can start)
    - TASK_READY before TASK_START (ready check before execution)
    - TASK_START before TRANSFER_START (task begins before its output transfers)
    """
    DAG_INJECT = 0
    TASK_COMPLETE = 1
    TRANSFER_COMPLETE = 2
    TASK_READY = 3
    TASK_START = 4
    TRANSFER_START = 5

    # Future event types (handlers no-op until implemented)
    MOBILITY_UPDATE = 100
    LINK_STATE_CHANGE = 101
    RESCHEDULE_TRIGGER = 102
    TDMA_SLOT_START = 103


@dataclass(order=False)
class Event:
    """An event in the simulation.

    Attributes:
        sim_time: When the event occurs (seconds, microsecond precision)
        event_type: Type of event (determines priority and handler)
        event_id: Unique identifier for FIFO ordering and cancellation
        dag_id: DAG this event belongs to (if applicable)
        task_id: Task this event relates to (if applicable)
        node_id: Node this event relates to (if applicable)
        link_id: Link this event relates to (if applicable)
        from_task: Source task for transfers
        to_task: Destination task for transfers
        data: Additional event-specific data
    """
    sim_time: float
    event_type: EventType
    event_id: int
    dag_id: Optional[str] = None
    task_id: Optional[str] = None
    node_id: Optional[str] = None
    link_id: Optional[str] = None
    from_task: Optional[str] = None
    to_task: Optional[str] = None
    data: dict = field(default_factory=dict)

    def __lt__(self, other: "Event") -> bool:
        """Compare events for heap ordering."""
        return self.sort_key < other.sort_key

    def __le__(self, other: "Event") -> bool:
        return self.sort_key <= other.sort_key

    @property
    def sort_key(self) -> tuple:
        """Return sort key for priority queue ordering.

        Order: (time, priority, event_id)
        """
        return (round_time(self.sim_time), int(self.event_type), self.event_id)

    def __repr__(self) -> str:
        parts = [f"Event({self.event_type.name}@{self.sim_time:.6f}"]
        if self.dag_id:
            parts.append(f"dag={self.dag_id}")
        if self.task_id:
            parts.append(f"task={self.task_id}")
        if self.node_id:
            parts.append(f"node={self.node_id}")
        if self.link_id:
            parts.append(f"link={self.link_id}")
        if self.from_task and self.to_task:
            parts.append(f"transfer={self.from_task}->{self.to_task}")
        return ", ".join(parts) + ")"


class EventQueue:
    """Priority queue for simulation events.

    Events are ordered by (time, priority, event_id) using a min-heap.
    Supports event cancellation via a cancelled set.
    """

    def __init__(self):
        self._heap: list[Event] = []
        self._next_id: int = 0
        self._cancelled: set[int] = set()
        self._size: int = 0  # Track non-cancelled events

    def schedule(self, sim_time: float, event_type: EventType, **kwargs) -> int:
        """Schedule a new event.

        Args:
            sim_time: When the event should occur
            event_type: Type of event
            **kwargs: Additional event attributes (dag_id, task_id, etc.)

        Returns:
            event_id: Unique identifier for this event (for cancellation)
        """
        event_id = self._next_id
        self._next_id += 1

        event = Event(
            sim_time=round_time(sim_time),
            event_type=event_type,
            event_id=event_id,
            **kwargs
        )

        heapq.heappush(self._heap, event)
        self._size += 1

        return event_id

    def cancel(self, event_id: int) -> bool:
        """Cancel an event by its ID.

        The event remains in the heap but will be skipped when popped.

        Args:
            event_id: ID of event to cancel

        Returns:
            True if event was cancelled, False if already cancelled or not found
        """
        if event_id in self._cancelled:
            return False
        self._cancelled.add(event_id)
        self._size -= 1
        return True

    def pop(self) -> Optional[Event]:
        """Remove and return the next event.

        Skips cancelled events.

        Returns:
            Next event, or None if queue is empty
        """
        while self._heap:
            event = heapq.heappop(self._heap)
            if event.event_id not in self._cancelled:
                return event
            # Event was cancelled, discard and continue
        return None

    def peek(self) -> Optional[Event]:
        """Return the next event without removing it.

        Skips cancelled events (but doesn't remove them).

        Returns:
            Next event, or None if queue is empty
        """
        # Find first non-cancelled event
        for event in self._heap:
            if event.event_id not in self._cancelled:
                return event
        return None

    def is_empty(self) -> bool:
        """Check if queue has no pending events."""
        return self._size <= 0

    def __len__(self) -> int:
        """Return number of pending (non-cancelled) events."""
        return max(0, self._size)

    def __iter__(self) -> Iterator[Event]:
        """Iterate over events in priority order (does not remove them)."""
        # Create sorted copy without cancelled events
        events = [e for e in self._heap if e.event_id not in self._cancelled]
        events.sort(key=lambda e: e.sort_key)
        return iter(events)

    def clear(self) -> None:
        """Remove all events from the queue."""
        self._heap.clear()
        self._cancelled.clear()
        self._size = 0

    @property
    def next_event_time(self) -> Optional[float]:
        """Return the time of the next event, or None if empty."""
        event = self.peek()
        return event.sim_time if event else None

"""
Task model definitions.

Defines tasks, their execution state, and node queueing models.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, List
from collections import deque


class TaskStatus(Enum):
    """Execution status of a task."""
    PENDING = auto()      # Not yet ready (waiting for predecessors)
    READY = auto()        # All predecessors complete, waiting for node
    QUEUED = auto()       # In node queue, waiting for execution
    RUNNING = auto()      # Currently executing on a node
    COMPLETED = auto()    # Finished execution
    FAILED = auto()       # Failed during execution
    PREEMPTED = auto()    # Interrupted (future: preemptive scheduling)


@dataclass
class Task:
    """A compute task in a DAG.

    Attributes:
        id: Unique task identifier (within the DAG)
        compute_cost: Total compute units required
        dag_id: ID of the DAG this task belongs to
        pinned_to: Optional node ID to force assignment
    """
    id: str
    compute_cost: float
    dag_id: str = ""
    pinned_to: Optional[str] = None

    def __post_init__(self):
        if self.compute_cost < 0:
            raise ValueError(f"Task {self.id}: compute_cost cannot be negative")

    def execution_time(self, compute_capacity: float) -> float:
        """Calculate execution time on a node with given capacity.

        Args:
            compute_capacity: Node's compute capacity (compute_units/second)

        Returns:
            Execution time in seconds
        """
        if compute_capacity <= 0:
            raise ValueError("compute_capacity must be positive")
        return self.compute_cost / compute_capacity


@dataclass
class TaskState:
    """Runtime state of a task during simulation.

    Tracks execution progress and enables future preemption.

    Attributes:
        task_id: ID of the task
        dag_id: ID of the DAG
        assigned_node: Node ID where task is assigned (from scheduler)
        status: Current execution status
        compute_remaining: Remaining compute units (for preemption)
        started_at: Sim time when execution started
        completed_at: Sim time when execution finished
        queued_at: Sim time when added to node queue
        predecessors_remaining: Set of predecessor task IDs not yet complete
    """
    task_id: str
    dag_id: str
    assigned_node: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    compute_remaining: Optional[float] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    queued_at: Optional[float] = None
    predecessors_remaining: set = field(default_factory=set)

    def is_ready(self) -> bool:
        """Check if all predecessors have completed."""
        return len(self.predecessors_remaining) == 0

    def mark_predecessor_complete(self, pred_task_id: str) -> bool:
        """Mark a predecessor as complete.

        Returns:
            True if this was the last predecessor (task now ready)
        """
        self.predecessors_remaining.discard(pred_task_id)
        return self.is_ready()


class QueueModel(ABC):
    """Abstract base class for node task queueing.

    Phase 2: FIFOQueueModel with single-task execution.
    Future: PriorityQueueModel, MultiSlotQueueModel, etc.
    """

    @abstractmethod
    def enqueue(self, task_state: TaskState, priority: float = 0) -> None:
        """Add a task to the queue."""
        pass

    @abstractmethod
    def dequeue(self) -> Optional[TaskState]:
        """Remove and return the next task to execute."""
        pass

    @abstractmethod
    def peek(self) -> Optional[TaskState]:
        """Return the next task without removing it."""
        pass

    @abstractmethod
    def is_empty(self) -> bool:
        """Check if queue is empty."""
        pass

    @abstractmethod
    def __len__(self) -> int:
        """Return number of queued tasks."""
        pass

    @abstractmethod
    def can_start_task(self, current_task: Optional[TaskState]) -> bool:
        """Check if node can start another task.

        Args:
            current_task: Currently executing task (None if idle)

        Returns:
            True if a new task can start
        """
        pass


class FIFOQueueModel(QueueModel):
    """Phase 2 implementation: Simple FIFO queue with single-task execution.

    Only one task executes at a time. Tasks wait in FIFO order.
    No preemption: running tasks complete before queued tasks start.
    """

    def __init__(self):
        self._queue: deque[TaskState] = deque()

    def enqueue(self, task_state: TaskState, priority: float = 0) -> None:
        """Add task to end of queue (priority ignored in FIFO)."""
        self._queue.append(task_state)

    def dequeue(self) -> Optional[TaskState]:
        """Remove and return the first task in queue."""
        if self._queue:
            return self._queue.popleft()
        return None

    def peek(self) -> Optional[TaskState]:
        """Return the first task without removing it."""
        if self._queue:
            return self._queue[0]
        return None

    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return len(self._queue) == 0

    def __len__(self) -> int:
        """Return number of queued tasks."""
        return len(self._queue)

    def can_start_task(self, current_task: Optional[TaskState]) -> bool:
        """Node can start if no task is currently running."""
        return current_task is None

    def clear(self) -> None:
        """Remove all tasks from queue."""
        self._queue.clear()

    def __iter__(self):
        """Iterate over queued tasks."""
        return iter(self._queue)

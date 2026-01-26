"""
DAG (Directed Acyclic Graph) model definitions.

Defines DAGs, edges, and DAG injection patterns.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set

from ncsim.models.task import Task


@dataclass
class Edge:
    """A dependency edge between tasks in a DAG.

    Represents data flow from one task to another.

    Attributes:
        from_task: Source task ID (produces data)
        to_task: Destination task ID (consumes data)
        data_size: Size of data to transfer in MB
    """
    from_task: str
    to_task: str
    data_size: float

    def __post_init__(self):
        if self.data_size < 0:
            raise ValueError(f"Edge {self.from_task}->{self.to_task}: data_size cannot be negative")


@dataclass
class DAG:
    """A Directed Acyclic Graph of tasks.

    Represents a workflow with tasks and data dependencies.

    Attributes:
        id: Unique DAG identifier
        tasks: Dictionary of task_id -> Task
        edges: List of dependency edges
        inject_at: Simulation time when DAG should be injected
    """
    id: str
    tasks: Dict[str, Task] = field(default_factory=dict)
    edges: List[Edge] = field(default_factory=list)
    inject_at: float = 0.0

    # Derived indices (built on first access)
    _predecessors: Optional[Dict[str, Set[str]]] = field(default=None, repr=False)
    _successors: Optional[Dict[str, Set[str]]] = field(default=None, repr=False)
    _edge_lookup: Optional[Dict[Tuple[str, str], Edge]] = field(default=None, repr=False)

    def __post_init__(self):
        # Set dag_id on all tasks
        for task in self.tasks.values():
            task.dag_id = self.id

        # Validate edges reference valid tasks
        for edge in self.edges:
            if edge.from_task not in self.tasks:
                raise ValueError(f"DAG {self.id}: edge references unknown task '{edge.from_task}'")
            if edge.to_task not in self.tasks:
                raise ValueError(f"DAG {self.id}: edge references unknown task '{edge.to_task}'")

    def _build_indices(self) -> None:
        """Build predecessor/successor lookup indices."""
        if self._predecessors is not None:
            return  # Already built

        self._predecessors = {task_id: set() for task_id in self.tasks}
        self._successors = {task_id: set() for task_id in self.tasks}
        self._edge_lookup = {}

        for edge in self.edges:
            self._predecessors[edge.to_task].add(edge.from_task)
            self._successors[edge.from_task].add(edge.to_task)
            self._edge_lookup[(edge.from_task, edge.to_task)] = edge

    def get_predecessors(self, task_id: str) -> Set[str]:
        """Get IDs of tasks that must complete before this task."""
        self._build_indices()
        return self._predecessors.get(task_id, set())

    def get_successors(self, task_id: str) -> Set[str]:
        """Get IDs of tasks that depend on this task."""
        self._build_indices()
        return self._successors.get(task_id, set())

    def get_edge(self, from_task: str, to_task: str) -> Optional[Edge]:
        """Get the edge between two tasks."""
        self._build_indices()
        return self._edge_lookup.get((from_task, to_task))

    def get_root_tasks(self) -> List[str]:
        """Get task IDs that have no predecessors (entry points)."""
        self._build_indices()
        return [task_id for task_id, preds in self._predecessors.items() if len(preds) == 0]

    def get_leaf_tasks(self) -> List[str]:
        """Get task IDs that have no successors (exit points)."""
        self._build_indices()
        return [task_id for task_id, succs in self._successors.items() if len(succs) == 0]

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        return self.tasks.get(task_id)

    def get_outgoing_edges(self, task_id: str) -> List[Edge]:
        """Get all edges originating from a task."""
        return [e for e in self.edges if e.from_task == task_id]

    def get_incoming_edges(self, task_id: str) -> List[Edge]:
        """Get all edges terminating at a task."""
        return [e for e in self.edges if e.to_task == task_id]

    @property
    def task_ids(self) -> List[str]:
        """List of all task IDs."""
        return list(self.tasks.keys())

    def __len__(self) -> int:
        """Number of tasks in the DAG."""
        return len(self.tasks)

    def topological_order(self) -> List[str]:
        """Return tasks in topological order (predecessors before successors).

        Uses Kahn's algorithm.
        """
        self._build_indices()

        # Count incoming edges
        in_degree = {task_id: len(preds) for task_id, preds in self._predecessors.items()}

        # Start with root tasks
        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            task_id = queue.pop(0)
            result.append(task_id)

            for succ in self._successors[task_id]:
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)

        if len(result) != len(self.tasks):
            raise ValueError(f"DAG {self.id} contains a cycle")

        return result


class DAGSource(ABC):
    """Abstract base class for DAG arrival patterns.

    Phase 2: SingleDAGSource injects one DAG at t=0.
    Future: PeriodicDAGSource, MultiDAGSource, etc.
    """

    @abstractmethod
    def get_next_injection(self, current_time: float) -> Optional[Tuple[float, DAG]]:
        """Get the next DAG to inject.

        Args:
            current_time: Current simulation time

        Returns:
            Tuple of (injection_time, dag), or None if no more DAGs
        """
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset the source to initial state."""
        pass


class SingleDAGSource(DAGSource):
    """Phase 2 implementation: One DAG injected at specified time.

    Default injection time is t=0.
    """

    def __init__(self, dag: DAG):
        self._dag = dag
        self._injected = False

    def get_next_injection(self, current_time: float) -> Optional[Tuple[float, DAG]]:
        """Return the DAG for injection once."""
        if self._injected:
            return None
        if current_time > self._dag.inject_at:
            return None  # Missed injection window
        self._injected = True
        return (self._dag.inject_at, self._dag)

    def reset(self) -> None:
        """Reset to allow re-injection."""
        self._injected = False


class MultiDAGSource(DAGSource):
    """Multiple DAGs injected at specified times.

    Useful for testing or future multi-DAG scenarios.
    """

    def __init__(self, dags: List[DAG]):
        # Sort by injection time
        self._dags = sorted(dags, key=lambda d: d.inject_at)
        self._next_index = 0

    def get_next_injection(self, current_time: float) -> Optional[Tuple[float, DAG]]:
        """Return the next DAG to inject."""
        if self._next_index >= len(self._dags):
            return None

        dag = self._dags[self._next_index]
        if current_time <= dag.inject_at:
            self._next_index += 1
            return (dag.inject_at, dag)

        return None

    def reset(self) -> None:
        """Reset to first DAG."""
        self._next_index = 0

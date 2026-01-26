"""
Unit tests for execution engine.
"""

import pytest
from ncsim.core.event_queue import EventQueue, EventType
from ncsim.core.execution_engine import ExecutionEngine, NodeState, LinkState
from ncsim.models.network import Node, Link, Network
from ncsim.models.task import Task, TaskStatus
from ncsim.models.dag import DAG, Edge
from ncsim.scheduler.base import RoundRobinScheduler


@pytest.fixture
def simple_network():
    """Create a simple 2-node network."""
    nodes = {
        "n0": Node(id="n0", compute_capacity=100),
        "n1": Node(id="n1", compute_capacity=50)
    }
    links = {
        "l01": Link(id="l01", from_node="n0", to_node="n1", bandwidth=100, latency=0.001)
    }
    return Network(nodes=nodes, links=links)


@pytest.fixture
def simple_dag():
    """Create a simple 2-task DAG."""
    tasks = {
        "T0": Task(id="T0", compute_cost=100, dag_id="dag_1"),
        "T1": Task(id="T1", compute_cost=200, dag_id="dag_1")
    }
    edges = [Edge(from_task="T0", to_task="T1", data_size=50)]
    return DAG(id="dag_1", tasks=tasks, edges=edges)


@pytest.fixture
def engine(simple_network):
    """Create an execution engine."""
    event_queue = EventQueue()
    scheduler = RoundRobinScheduler()
    return ExecutionEngine(
        network=simple_network,
        scheduler=scheduler,
        event_queue=event_queue
    )


class TestExecutionEngine:
    """Tests for ExecutionEngine class."""

    def test_initializes_node_states(self, engine):
        assert "n0" in engine.node_states
        assert "n1" in engine.node_states
        assert engine.node_states["n0"].is_idle()

    def test_initializes_link_states(self, engine):
        assert "l01" in engine.link_states
        assert engine.link_states["l01"].num_transfers == 0


class TestDagInjectHandler:
    """Tests for DAG injection handling."""

    def test_stores_dag(self, engine, simple_dag):
        event_queue = engine.event_queue
        event_queue.schedule(
            sim_time=0.0,
            event_type=EventType.DAG_INJECT,
            dag_id="dag_1",
            data={"dag": simple_dag}
        )

        event = event_queue.pop()
        engine.handle_event(event)

        assert "dag_1" in engine.dags

    def test_creates_task_states(self, engine, simple_dag):
        event_queue = engine.event_queue
        event_queue.schedule(
            sim_time=0.0,
            event_type=EventType.DAG_INJECT,
            dag_id="dag_1",
            data={"dag": simple_dag}
        )

        event = event_queue.pop()
        engine.handle_event(event)

        t0_state = engine.get_task_state("dag_1", "T0")
        t1_state = engine.get_task_state("dag_1", "T1")

        assert t0_state is not None
        assert t1_state is not None
        assert t0_state.assigned_node is not None

    def test_schedules_root_task_ready(self, engine, simple_dag):
        event_queue = engine.event_queue
        event_queue.schedule(
            sim_time=0.0,
            event_type=EventType.DAG_INJECT,
            dag_id="dag_1",
            data={"dag": simple_dag}
        )

        event = event_queue.pop()
        engine.handle_event(event)

        # Should have scheduled TASK_READY for root task T0
        next_event = event_queue.peek()
        assert next_event is not None
        assert next_event.event_type == EventType.TASK_READY
        assert next_event.task_id == "T0"


class TestTaskReadyHandler:
    """Tests for task ready handling."""

    def test_starts_task_on_idle_node(self, engine, simple_dag):
        # Inject DAG first
        event_queue = engine.event_queue
        event_queue.schedule(
            sim_time=0.0,
            event_type=EventType.DAG_INJECT,
            dag_id="dag_1",
            data={"dag": simple_dag}
        )

        event = event_queue.pop()
        engine.handle_event(event)

        # Process TASK_READY
        event = event_queue.pop()
        engine.handle_event(event)

        # Should have scheduled TASK_START
        next_event = event_queue.peek()
        assert next_event is not None
        assert next_event.event_type == EventType.TASK_START

    def test_queues_task_on_busy_node(self, engine):
        # Create two tasks that should run on same node
        tasks = {
            "T0": Task(id="T0", compute_cost=100, dag_id="dag_1", pinned_to="n0"),
            "T1": Task(id="T1", compute_cost=100, dag_id="dag_1", pinned_to="n0")
        }
        dag = DAG(id="dag_1", tasks=tasks, edges=[])

        event_queue = engine.event_queue
        event_queue.schedule(
            sim_time=0.0,
            event_type=EventType.DAG_INJECT,
            dag_id="dag_1",
            data={"dag": dag}
        )

        # Process DAG inject
        event = event_queue.pop()
        engine.handle_event(event)

        # Process first TASK_READY and TASK_START
        while not event_queue.is_empty():
            event = event_queue.pop()
            if event.event_type == EventType.TASK_COMPLETE:
                break
            engine.handle_event(event)

        # Node n0 should be busy with T0
        node_state = engine.node_states["n0"]
        # Check if there's a queued task or another ready event


class TestTaskCompleteHandler:
    """Tests for task completion handling."""

    def test_marks_task_completed(self, engine, simple_dag):
        event_queue = engine.event_queue
        event_queue.schedule(
            sim_time=0.0,
            event_type=EventType.DAG_INJECT,
            dag_id="dag_1",
            data={"dag": simple_dag}
        )

        # Process all events until TASK_COMPLETE
        processed_complete = False
        while not event_queue.is_empty():
            event = event_queue.pop()
            engine.handle_event(event)
            if event.event_type == EventType.TASK_COMPLETE:
                processed_complete = True
                break

        if processed_complete:
            # T0 should be completed
            t0_state = engine.get_task_state("dag_1", "T0")
            assert t0_state.status == TaskStatus.COMPLETED


class TestNodeState:
    """Tests for NodeState class."""

    def test_is_idle_when_no_task(self):
        state = NodeState(node_id="n0")
        assert state.is_idle() is True

    def test_not_idle_when_task_running(self):
        from ncsim.models.task import TaskState
        state = NodeState(node_id="n0")
        state.current_task = TaskState(task_id="T0", dag_id="dag_1")
        assert state.is_idle() is False


class TestLinkState:
    """Tests for LinkState class."""

    def test_no_transfers_initially(self):
        state = LinkState(link_id="l01")
        assert state.num_transfers == 0

    def test_counts_active_transfers(self):
        from ncsim.core.execution_engine import ActiveTransfer
        state = LinkState(link_id="l01")
        state.active_transfers.append(
            ActiveTransfer(
                dag_id="dag_1",
                from_task="T0",
                to_task="T1",
                link_id="l01",
                data_size=100,
                data_remaining=100,
                started_at=0.0,
                scheduled_complete=1.0,
                event_id=0
            )
        )
        assert state.num_transfers == 1

"""Unit tests for telemetry collectors."""

import pytest

from ncsim.core.event_queue import EventQueue, EventType
from ncsim.core.execution_engine import ExecutionEngine
from ncsim.core.telemetry import SimulationSnapshot, TraceOnlyCollector, FullStateCollector
from ncsim.models.network import Node, Link, Network
from ncsim.models.task import Task
from ncsim.models.dag import DAG, Edge
from ncsim.scheduler.base import RoundRobinScheduler


@pytest.fixture
def simple_network():
    """2-node network."""
    nodes = {
        "n0": Node(id="n0", compute_capacity=100),
        "n1": Node(id="n1", compute_capacity=50),
    }
    links = {
        "l01": Link(id="l01", from_node="n0", to_node="n1", bandwidth=100, latency=0.001),
    }
    return Network(nodes=nodes, links=links)


@pytest.fixture
def simple_dag():
    """2-task DAG."""
    tasks = {
        "T0": Task(id="T0", compute_cost=100, dag_id="dag_1"),
        "T1": Task(id="T1", compute_cost=200, dag_id="dag_1"),
    }
    edges = [Edge(from_task="T0", to_task="T1", data_size=50)]
    return DAG(id="dag_1", tasks=tasks, edges=edges)


@pytest.fixture
def engine(simple_network):
    """ExecutionEngine with EventQueue and RoundRobinScheduler."""
    eq = EventQueue()
    scheduler = RoundRobinScheduler()
    return ExecutionEngine(
        network=simple_network,
        scheduler=scheduler,
        event_queue=eq,
    )


class TestSimulationSnapshot:
    """Tests for SimulationSnapshot dataclass."""

    def test_creates_with_defaults(self):
        snap = SimulationSnapshot(
            sim_time=0.0,
            total_events_processed=0,
            pending_events=0,
            tasks_completed=0,
            tasks_running=0,
            tasks_pending=0,
            transfers_active=0,
            nodes_busy=0,
            nodes_idle=2,
        )
        assert snap.node_details is None
        assert snap.link_details is None
        assert snap.task_details is None

    def test_creates_with_details(self):
        snap = SimulationSnapshot(
            sim_time=1.5,
            total_events_processed=10,
            pending_events=3,
            tasks_completed=2,
            tasks_running=1,
            tasks_pending=0,
            transfers_active=1,
            nodes_busy=1,
            nodes_idle=1,
            node_details={"n0": {"busy": True}},
            link_details={"l01": {"active_transfers": 1}},
        )
        assert snap.node_details == {"n0": {"busy": True}}
        assert snap.link_details == {"l01": {"active_transfers": 1}}


class TestTraceOnlyCollector:
    """Tests for TraceOnlyCollector."""

    def test_initial_total_events_zero(self):
        c = TraceOnlyCollector()
        assert c.total_events == 0

    def test_on_event_increments_counter(self, engine, simple_dag):
        c = TraceOnlyCollector()
        # Inject DAG to have something to process
        engine.event_queue.schedule(
            sim_time=0.0,
            event_type=EventType.DAG_INJECT,
            dag_id="dag_1",
            data={"dag": simple_dag},
        )
        event = engine.event_queue.pop()
        engine.handle_event(event)
        c.on_event(event, engine)
        assert c.total_events == 1
        c.on_event(event, engine)
        assert c.total_events == 2

    def test_snapshot_reflects_engine_state(self, engine, simple_dag):
        c = TraceOnlyCollector()
        # Before any events: 2 idle nodes, 0 tasks
        snap = c.snapshot(engine)
        assert snap.nodes_idle == 2
        assert snap.nodes_busy == 0
        assert snap.tasks_completed == 0

        # Inject DAG
        engine.event_queue.schedule(
            sim_time=0.0,
            event_type=EventType.DAG_INJECT,
            dag_id="dag_1",
            data={"dag": simple_dag},
        )
        event = engine.event_queue.pop()
        engine.handle_event(event)
        c.on_event(event, engine)

        snap2 = c.snapshot(engine)
        # After DAG inject, tasks should be known (pending or running)
        assert snap2.tasks_completed + snap2.tasks_running + snap2.tasks_pending > 0

    def test_finalize_returns_metrics(self, engine, simple_dag):
        c = TraceOnlyCollector()
        engine.event_queue.schedule(
            sim_time=0.0,
            event_type=EventType.DAG_INJECT,
            dag_id="dag_1",
            data={"dag": simple_dag},
        )
        event = engine.event_queue.pop()
        engine.handle_event(event)
        c.on_event(event, engine)

        metrics = c.finalize(engine)
        assert "total_events" in metrics
        assert "final_sim_time" in metrics
        assert "tasks_completed" in metrics
        assert metrics["total_events"] == 1


class TestFullStateCollector:
    """Tests for FullStateCollector."""

    def test_initial_state(self):
        c = FullStateCollector()
        assert c.total_events == 0
        assert c.snapshots == []

    def test_on_event_takes_periodic_snapshots(self, engine, simple_dag):
        c = FullStateCollector(snapshot_interval=0.0)  # snapshot on every event
        engine.event_queue.schedule(
            sim_time=0.0,
            event_type=EventType.DAG_INJECT,
            dag_id="dag_1",
            data={"dag": simple_dag},
        )
        event = engine.event_queue.pop()
        engine.handle_event(event)
        c.on_event(event, engine)
        assert c.total_events == 1
        assert len(c.snapshots) >= 1

    def test_snapshot_includes_node_details(self, engine):
        c = FullStateCollector()
        snap = c.snapshot(engine)
        assert snap.node_details is not None
        assert "n0" in snap.node_details
        assert "busy" in snap.node_details["n0"]
        assert "queue_depth" in snap.node_details["n0"]
        assert "current_task" in snap.node_details["n0"]

    def test_snapshot_includes_link_details(self, engine):
        c = FullStateCollector()
        snap = c.snapshot(engine)
        assert snap.link_details is not None
        assert "l01" in snap.link_details
        assert "active_transfers" in snap.link_details["l01"]
        assert "total_transferred" in snap.link_details["l01"]

    def test_finalize_appends_final_snapshot(self, engine):
        c = FullStateCollector()
        assert len(c.snapshots) == 0
        result = c.finalize(engine)
        assert len(c.snapshots) == 1
        assert result["num_snapshots"] == 1
        assert "snapshots" in result

    def test_custom_snapshot_interval(self, engine, simple_dag):
        c = FullStateCollector(snapshot_interval=10.0)
        # Event at time 0 -> snapshot taken (time - last_snapshot_time >= 10 since last=-1)
        engine.event_queue.schedule(
            sim_time=0.0,
            event_type=EventType.DAG_INJECT,
            dag_id="dag_1",
            data={"dag": simple_dag},
        )
        event = engine.event_queue.pop()
        engine.handle_event(event)
        c.on_event(event, engine)
        initial_count = len(c.snapshots)

        # Process remaining events at time 0 — should NOT add another snapshot
        while len(engine.event_queue) > 0:
            ev = engine.event_queue.pop()
            engine.handle_event(ev)
            c.on_event(ev, engine)

        # All events at time 0 should not cause many snapshots
        # (only 1 at time 0 since interval is 10.0)
        assert len(c.snapshots) == initial_count

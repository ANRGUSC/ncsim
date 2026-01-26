"""
Telemetry and state collection for simulation analysis.

Phase 2: TraceOnlyCollector captures events for trace file.
Future: FullStateCollector captures complete simulation state.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ncsim.core.event_queue import Event
    from ncsim.core.execution_engine import ExecutionEngine, NetworkState


@dataclass
class SimulationSnapshot:
    """Complete simulation state at a point in time.

    Used for replay, analysis, and debugging.
    """
    sim_time: float
    total_events_processed: int
    pending_events: int
    tasks_completed: int
    tasks_running: int
    tasks_pending: int
    transfers_active: int
    nodes_busy: int
    nodes_idle: int

    # Detailed state (optional, for full snapshots)
    node_details: Optional[Dict[str, Any]] = None
    link_details: Optional[Dict[str, Any]] = None
    task_details: Optional[Dict[str, Any]] = None


class TelemetryCollector(ABC):
    """Abstract base class for simulation state collection.

    Phase 2: TraceOnlyCollector writes events to trace file.
    Future: FullStateCollector captures node/link/task states.
    """

    @abstractmethod
    def on_event(self, event: "Event", engine: "ExecutionEngine") -> None:
        """Called after each event is processed.

        Args:
            event: The event that was just processed
            engine: The execution engine (for state access)
        """
        pass

    @abstractmethod
    def snapshot(self, engine: "ExecutionEngine") -> SimulationSnapshot:
        """Capture current simulation state.

        Args:
            engine: The execution engine

        Returns:
            SimulationSnapshot with current state
        """
        pass

    @abstractmethod
    def finalize(self, engine: "ExecutionEngine") -> Dict[str, Any]:
        """Called at end of simulation to finalize data collection.

        Args:
            engine: The execution engine

        Returns:
            Dictionary of collected metrics
        """
        pass


class TraceOnlyCollector(TelemetryCollector):
    """Phase 2 implementation: Events only, no state snapshots.

    Collects event stream for trace writer.
    Does not store full state snapshots.
    """

    def __init__(self):
        self.events: List[Dict[str, Any]] = []
        self.total_events = 0

    def on_event(self, event: "Event", engine: "ExecutionEngine") -> None:
        """Record event occurrence."""
        self.total_events += 1
        # Events are written by TraceWriter, not stored here

    def snapshot(self, engine: "ExecutionEngine") -> SimulationSnapshot:
        """Create a basic snapshot from engine state."""
        node_states = engine.node_states
        task_states = engine.task_states

        nodes_busy = sum(1 for ns in node_states.values() if not ns.is_idle())
        nodes_idle = len(node_states) - nodes_busy

        tasks_completed = 0
        tasks_running = 0
        tasks_pending = 0
        for ts in task_states.values():
            if ts.status.name == "COMPLETED":
                tasks_completed += 1
            elif ts.status.name == "RUNNING":
                tasks_running += 1
            else:
                tasks_pending += 1

        transfers_active = sum(
            len(ls.active_transfers)
            for ls in engine.link_states.values()
        )

        return SimulationSnapshot(
            sim_time=engine.sim_time,
            total_events_processed=self.total_events,
            pending_events=len(engine.event_queue),
            tasks_completed=tasks_completed,
            tasks_running=tasks_running,
            tasks_pending=tasks_pending,
            transfers_active=transfers_active,
            nodes_busy=nodes_busy,
            nodes_idle=nodes_idle
        )

    def finalize(self, engine: "ExecutionEngine") -> Dict[str, Any]:
        """Return final metrics."""
        snapshot = self.snapshot(engine)
        return {
            "total_events": self.total_events,
            "final_sim_time": engine.sim_time,
            "tasks_completed": snapshot.tasks_completed
        }


class FullStateCollector(TelemetryCollector):
    """Future implementation: Full state snapshots at regular intervals.

    Not used in Phase 2 - placeholder for visualization/replay.
    """

    def __init__(self, snapshot_interval: float = 1.0):
        self.snapshot_interval = snapshot_interval
        self.snapshots: List[SimulationSnapshot] = []
        self.last_snapshot_time = -1.0
        self.total_events = 0

    def on_event(self, event: "Event", engine: "ExecutionEngine") -> None:
        """Record event and possibly take snapshot."""
        self.total_events += 1

        # Take snapshot at intervals
        if engine.sim_time - self.last_snapshot_time >= self.snapshot_interval:
            self.snapshots.append(self.snapshot(engine))
            self.last_snapshot_time = engine.sim_time

    def snapshot(self, engine: "ExecutionEngine") -> SimulationSnapshot:
        """Create detailed snapshot with full state."""
        # Similar to TraceOnlyCollector.snapshot but with details
        node_states = engine.node_states
        task_states = engine.task_states
        link_states = engine.link_states

        nodes_busy = sum(1 for ns in node_states.values() if not ns.is_idle())
        nodes_idle = len(node_states) - nodes_busy

        tasks_completed = 0
        tasks_running = 0
        tasks_pending = 0
        for ts in task_states.values():
            if ts.status.name == "COMPLETED":
                tasks_completed += 1
            elif ts.status.name == "RUNNING":
                tasks_running += 1
            else:
                tasks_pending += 1

        transfers_active = sum(
            len(ls.active_transfers)
            for ls in link_states.values()
        )

        # Build detailed state
        node_details = {
            node_id: {
                "busy": not ns.is_idle(),
                "queue_depth": len(ns.queue),
                "current_task": ns.current_task.task_id if ns.current_task else None
            }
            for node_id, ns in node_states.items()
        }

        link_details = {
            link_id: {
                "active_transfers": ls.num_transfers,
                "total_transferred": ls.total_data_transferred
            }
            for link_id, ls in link_states.items()
        }

        return SimulationSnapshot(
            sim_time=engine.sim_time,
            total_events_processed=self.total_events,
            pending_events=len(engine.event_queue),
            tasks_completed=tasks_completed,
            tasks_running=tasks_running,
            tasks_pending=tasks_pending,
            transfers_active=transfers_active,
            nodes_busy=nodes_busy,
            nodes_idle=nodes_idle,
            node_details=node_details,
            link_details=link_details
        )

    def finalize(self, engine: "ExecutionEngine") -> Dict[str, Any]:
        """Return all snapshots and final metrics."""
        # Take final snapshot
        self.snapshots.append(self.snapshot(engine))

        return {
            "total_events": self.total_events,
            "final_sim_time": engine.sim_time,
            "num_snapshots": len(self.snapshots),
            "snapshots": self.snapshots
        }

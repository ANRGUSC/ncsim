"""
Trace file writer for simulation output.

Writes JSONL trace files per CLAUDE.md section 4 specification.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO, Optional, Dict, Any, List

from ncsim.core.event_queue import Event, EventType, round_time


@dataclass
class TraceWriter:
    """Writes simulation events to a JSONL trace file.

    Each line is a JSON object with required fields:
    - seq: Monotonically increasing sequence number
    - sim_time: Simulation time in seconds
    - type: Event type name

    Additional fields vary by event type.
    """
    output_path: Path
    scenario_name: str
    scenario_hash: str
    seed: int
    trace_version: str = "1.0"

    _file: Optional[TextIO] = field(default=None, repr=False)
    _seq: int = field(default=0, repr=False)
    _events: List[Dict[str, Any]] = field(default_factory=list, repr=False)
    _closed: bool = field(default=False, repr=False)

    def __post_init__(self):
        self.output_path = Path(self.output_path)

    def open(self) -> None:
        """Open the trace file for writing."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.output_path, "w", encoding="utf-8")
        self._seq = 0
        self._closed = False

    def close(self) -> None:
        """Close the trace file."""
        if self._file and not self._closed:
            self._file.close()
            self._closed = True

    def __enter__(self) -> "TraceWriter":
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def _write_event(self, event_dict: Dict[str, Any]) -> None:
        """Write a single event to the trace file."""
        if self._file is None:
            raise RuntimeError("TraceWriter not open")

        event_dict["seq"] = self._seq
        self._seq += 1

        # Round sim_time to microseconds
        if "sim_time" in event_dict:
            event_dict["sim_time"] = round_time(event_dict["sim_time"])

        line = json.dumps(event_dict, separators=(",", ":"))
        self._file.write(line + "\n")
        self._events.append(event_dict)

    def write_sim_start(self) -> None:
        """Write sim_start event (must be first)."""
        self._write_event({
            "sim_time": 0.0,
            "type": "sim_start",
            "trace_version": self.trace_version,
            "seed": self.seed,
            "scenario": self.scenario_name,
            "scenario_hash": self.scenario_hash
        })

    def write_sim_end(self, status: str, makespan: float, total_events: int) -> None:
        """Write sim_end event (must be last)."""
        self._write_event({
            "sim_time": round_time(makespan),
            "type": "sim_end",
            "status": status,
            "makespan": round_time(makespan),
            "total_events": total_events
        })

    def write_dag_inject(
        self,
        sim_time: float,
        dag_id: str,
        task_ids: List[str]
    ) -> None:
        """Write dag_inject event."""
        self._write_event({
            "sim_time": sim_time,
            "type": "dag_inject",
            "dag_id": dag_id,
            "task_ids": task_ids
        })

    def write_task_scheduled(
        self,
        sim_time: float,
        dag_id: str,
        task_id: str,
        node_id: str
    ) -> None:
        """Write task_scheduled event."""
        self._write_event({
            "sim_time": sim_time,
            "type": "task_scheduled",
            "dag_id": dag_id,
            "task_id": task_id,
            "node_id": node_id
        })

    def write_task_start(
        self,
        sim_time: float,
        dag_id: str,
        task_id: str,
        node_id: str
    ) -> None:
        """Write task_start event."""
        self._write_event({
            "sim_time": sim_time,
            "type": "task_start",
            "dag_id": dag_id,
            "task_id": task_id,
            "node_id": node_id
        })

    def write_task_complete(
        self,
        sim_time: float,
        dag_id: str,
        task_id: str,
        node_id: str,
        duration: float
    ) -> None:
        """Write task_complete event."""
        self._write_event({
            "sim_time": sim_time,
            "type": "task_complete",
            "dag_id": dag_id,
            "task_id": task_id,
            "node_id": node_id,
            "duration": round_time(duration)
        })

    def write_transfer_start(
        self,
        sim_time: float,
        dag_id: str,
        from_task: str,
        to_task: str,
        link_id: str,
        data_size: float,
        route: list[str] | None = None,
    ) -> None:
        """Write transfer_start event."""
        event: dict = {
            "sim_time": sim_time,
            "type": "transfer_start",
            "dag_id": dag_id,
            "from_task": from_task,
            "to_task": to_task,
            "link_id": link_id,
            "data_size": data_size,
        }
        if route and len(route) > 1:
            event["route"] = route
        self._write_event(event)

    def write_transfer_complete(
        self,
        sim_time: float,
        dag_id: str,
        from_task: str,
        to_task: str,
        link_id: str,
        duration: float,
        route: list[str] | None = None,
    ) -> None:
        """Write transfer_complete event."""
        event: dict = {
            "sim_time": sim_time,
            "type": "transfer_complete",
            "dag_id": dag_id,
            "from_task": from_task,
            "to_task": to_task,
            "link_id": link_id,
            "duration": round_time(duration),
        }
        if route and len(route) > 1:
            event["route"] = route
        self._write_event(event)

    def on_event(self, event: Event) -> None:
        """Handle an event from the simulation.

        Maps Event objects to trace file entries.
        """
        if event.event_type == EventType.DAG_INJECT:
            dag = event.data.get("dag")
            task_ids = list(dag.tasks.keys()) if dag else []
            self.write_dag_inject(
                sim_time=event.sim_time,
                dag_id=event.dag_id,
                task_ids=task_ids
            )
            # Write task_scheduled for each task
            if dag:
                from ncsim.scheduler.base import PlacementPlan
                # Scheduler info comes via engine listener
                pass

        elif event.event_type == EventType.TASK_START:
            self.write_task_start(
                sim_time=event.sim_time,
                dag_id=event.dag_id,
                task_id=event.task_id,
                node_id=event.node_id
            )

        elif event.event_type == EventType.TASK_COMPLETE:
            duration = event.data.get("duration", 0.0)
            self.write_task_complete(
                sim_time=event.sim_time,
                dag_id=event.dag_id,
                task_id=event.task_id,
                node_id=event.node_id,
                duration=duration
            )

        elif event.event_type == EventType.TRANSFER_START:
            data_size = event.data.get("data_size", 0.0)
            self.write_transfer_start(
                sim_time=event.sim_time,
                dag_id=event.dag_id,
                from_task=event.from_task,
                to_task=event.to_task,
                link_id=event.link_id,
                data_size=data_size
            )

        elif event.event_type == EventType.TRANSFER_COMPLETE:
            data_size = event.data.get("data_size", 0.0)
            # Calculate duration from transfer state or estimate
            # Note: actual duration tracking is in engine
            self.write_transfer_complete(
                sim_time=event.sim_time,
                dag_id=event.dag_id,
                from_task=event.from_task,
                to_task=event.to_task,
                link_id=event.link_id,
                duration=0.0  # Updated below
            )

    @property
    def event_count(self) -> int:
        """Number of events written."""
        return self._seq


class TraceEventAdapter:
    """Adapter to connect simulation to trace writer.

    Handles task_scheduled events and transfer duration tracking.
    """

    def __init__(self, trace_writer: TraceWriter):
        self.trace_writer = trace_writer
        self._transfer_starts: Dict[tuple, float] = {}  # (dag_id, from, to) -> start_time
        self._transfer_paths: Dict[tuple, list] = {}   # (dag_id, from, to) -> path
        self._task_assignments: Dict[tuple, str] = {}  # (dag_id, task_id) -> node_id

    def on_event(self, event: Event) -> None:
        """Handle simulation event."""
        if event.event_type == EventType.DAG_INJECT:
            dag = event.data.get("dag")
            if dag:
                task_ids = list(dag.tasks.keys())
                self.trace_writer.write_dag_inject(
                    sim_time=event.sim_time,
                    dag_id=event.dag_id,
                    task_ids=task_ids
                )

        elif event.event_type == EventType.TASK_START:
            # Write task_scheduled if not already written
            key = (event.dag_id, event.task_id)
            if key not in self._task_assignments:
                self._task_assignments[key] = event.node_id
                self.trace_writer.write_task_scheduled(
                    sim_time=event.sim_time,
                    dag_id=event.dag_id,
                    task_id=event.task_id,
                    node_id=event.node_id
                )

            self.trace_writer.write_task_start(
                sim_time=event.sim_time,
                dag_id=event.dag_id,
                task_id=event.task_id,
                node_id=event.node_id
            )

        elif event.event_type == EventType.TASK_COMPLETE:
            duration = event.data.get("duration", 0.0)
            self.trace_writer.write_task_complete(
                sim_time=event.sim_time,
                dag_id=event.dag_id,
                task_id=event.task_id,
                node_id=event.node_id,
                duration=duration
            )

        elif event.event_type == EventType.TRANSFER_START:
            data_size = event.data.get("data_size", 0.0)
            path = event.data.get("path")
            key = (event.dag_id, event.from_task, event.to_task)
            self._transfer_starts[key] = event.sim_time
            self._transfer_paths[key] = path

            self.trace_writer.write_transfer_start(
                sim_time=event.sim_time,
                dag_id=event.dag_id,
                from_task=event.from_task,
                to_task=event.to_task,
                link_id=event.link_id,
                data_size=data_size,
                route=path,
            )

        elif event.event_type == EventType.TRANSFER_COMPLETE:
            key = (event.dag_id, event.from_task, event.to_task)
            start_time = self._transfer_starts.pop(key, event.sim_time)
            path = self._transfer_paths.pop(key, None)
            duration = event.sim_time - start_time

            self.trace_writer.write_transfer_complete(
                sim_time=event.sim_time,
                dag_id=event.dag_id,
                from_task=event.from_task,
                to_task=event.to_task,
                link_id=event.link_id,
                duration=duration,
                route=path,
            )

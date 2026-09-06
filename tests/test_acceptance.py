"""
Acceptance tests for ncsim.

These tests verify the overall behavior of the simulation system
per CLAUDE.md section 6.3.
"""

import pytest
import json
import tempfile
from pathlib import Path

from ncsim.io.scenario_loader import load_scenario
from ncsim.io.trace_writer import TraceWriter, TraceEventAdapter
from ncsim.models.dag import SingleDAGSource
from ncsim.models.network import Node, Link, Network
from ncsim.models.task import Task
from ncsim.models.dag import DAG, Edge
from ncsim.core.simulation import Simulation, run_simulation
from ncsim.scheduler.base import RoundRobinScheduler
from ncsim.models.routing import DirectLinkRouting
from ncsim.models.interference import InterferenceModel, WirelessOutageError
from ncsim.scheduler.saga_adapter import create_scheduler, SAGA_AVAILABLE


class _AlwaysOutage(InterferenceModel):
    def get_interference_factor(self, link_id, active_link_ids, network):
        raise WirelessOutageError(link_id, -3.0, 0.0)

    def get_affected_links(self, changed_link_id, active_link_ids, network):
        return set()


def test_wireless_outage_has_structured_result_status():
    nodes = {
        "n0": Node(id="n0", compute_capacity=100),
        "n1": Node(id="n1", compute_capacity=100),
    }
    links = {
        "l01": Link(
            id="l01", from_node="n0", to_node="n1",
            bandwidth=100, latency=0.0,
        )
    }
    network = Network(nodes=nodes, links=links)
    tasks = {
        "T0": Task(
            id="T0", compute_cost=1, dag_id="outage", pinned_to="n0"
        ),
        "T1": Task(
            id="T1", compute_cost=1, dag_id="outage", pinned_to="n1"
        ),
    }
    dag = DAG(
        id="outage", tasks=tasks,
        edges=[Edge(from_task="T0", to_task="T1", data_size=1)],
    )
    sim = Simulation(
        network=network,
        scheduler=RoundRobinScheduler(),
        dag_source=SingleDAGSource(dag),
        interference_model=_AlwaysOutage(),
    )
    result = sim.run()
    assert result.status == "blocked_wireless"
    assert "wireless outage" in result.error_message


def test_unused_clean_zero_rate_does_not_abort_run():
    """An unused RF-derived unavailable link does not invalidate a run."""
    nodes = {
        "n0": Node(id="n0", compute_capacity=100),
        "n1": Node(id="n1", compute_capacity=100),
    }
    link = Link(
        id="l01", from_node="n0", to_node="n1",
        bandwidth=1.0, latency=0.0,
    )
    link.bandwidth = 0.0
    network = Network(nodes=nodes, links={"l01": link})
    result = Simulation(network, RoundRobinScheduler()).run()

    assert result.status == "completed"
    assert result.error_message is None


class TestDeterminism:
    """Test 2: Same seed = identical trace."""

    def test_same_seed_produces_identical_results(self):
        """Two runs with same seed should produce identical makespan."""
        nodes = {
            "n0": Node(id="n0", compute_capacity=100),
            "n1": Node(id="n1", compute_capacity=50)
        }
        links = {
            "l01": Link(id="l01", from_node="n0", to_node="n1", bandwidth=100, latency=0.001)
        }
        network = Network(nodes=nodes, links=links)

        tasks = {
            "T0": Task(id="T0", compute_cost=100, dag_id="dag_1"),
            "T1": Task(id="T1", compute_cost=200, dag_id="dag_1")
        }
        edges = [Edge(from_task="T0", to_task="T1", data_size=50)]
        dag = DAG(id="dag_1", tasks=tasks, edges=edges)

        scheduler1 = RoundRobinScheduler()
        result1 = run_simulation(network, dag, scheduler1, seed=42)

        scheduler2 = RoundRobinScheduler()
        result2 = run_simulation(network, dag, scheduler2, seed=42)

        assert result1.makespan == result2.makespan
        assert result1.total_events == result2.total_events


class TestDependencyOrdering:
    """Test 3: No task_start before all predecessor transfer_complete."""

    def test_task_waits_for_predecessors(self):
        """Task T1 should not start until T0 completes and transfer finishes."""
        nodes = {
            "n0": Node(id="n0", compute_capacity=100),
            "n1": Node(id="n1", compute_capacity=100)
        }
        links = {
            "l01": Link(id="l01", from_node="n0", to_node="n1", bandwidth=100, latency=0.0)
        }
        network = Network(nodes=nodes, links=links)

        # T0 pinned to n0, T1 pinned to n1 - forces transfer
        tasks = {
            "T0": Task(id="T0", compute_cost=100, dag_id="dag_1", pinned_to="n0"),
            "T1": Task(id="T1", compute_cost=100, dag_id="dag_1", pinned_to="n1")
        }
        edges = [Edge(from_task="T0", to_task="T1", data_size=100)]
        dag = DAG(id="dag_1", tasks=tasks, edges=edges)

        scheduler = RoundRobinScheduler()
        dag_source = SingleDAGSource(dag)

        # Capture events
        events = []

        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "trace.jsonl"
            trace_writer = TraceWriter(
                output_path=trace_path,
                scenario_name="test",
                scenario_hash="test123",
                seed=42
            )
            trace_adapter = TraceEventAdapter(trace_writer)

            sim = Simulation(
                network=network,
                scheduler=scheduler,
                dag_source=dag_source,
                seed=42
            )

            trace_writer.open()
            trace_writer.write_sim_start()
            sim.add_event_listener(trace_adapter.on_event)

            result = sim.run()

            trace_writer.write_sim_end("completed", result.makespan, trace_writer.event_count)
            trace_writer.close()

            # Read trace file
            with open(trace_path) as f:
                events = [json.loads(line) for line in f]

        # Verify ordering
        transfer_complete_time = None
        t1_start_time = None

        for event in events:
            if event["type"] == "transfer_complete" and event.get("to_task") == "T1":
                transfer_complete_time = event["sim_time"]
            if event["type"] == "task_start" and event.get("task_id") == "T1":
                t1_start_time = event["sim_time"]

        # T1 should start at or after transfer completes
        if transfer_complete_time is not None and t1_start_time is not None:
            assert t1_start_time >= transfer_complete_time


class TestMakespanCalculation:
    """Test 5: Makespan = max(task_complete times)."""

    def test_makespan_matches_last_task(self):
        """Makespan should equal the completion time of the last task."""
        nodes = {"n0": Node(id="n0", compute_capacity=100)}
        network = Network(nodes=nodes, links={})

        # Sequential tasks: T0 (1s) -> T1 (2s)
        tasks = {
            "T0": Task(id="T0", compute_cost=100, dag_id="dag_1"),  # 1 second
            "T1": Task(id="T1", compute_cost=200, dag_id="dag_1")   # 2 seconds
        }
        # No data transfer (same node)
        edges = [Edge(from_task="T0", to_task="T1", data_size=0)]
        dag = DAG(id="dag_1", tasks=tasks, edges=edges)

        scheduler = RoundRobinScheduler()
        result = run_simulation(network, dag, scheduler, seed=42)

        # T0: 0 -> 1s, T1: 1 -> 3s
        assert result.makespan == 3.0


class TestSimpleDAGExecution:
    """Basic simulation execution tests."""

    def test_single_task_dag(self):
        """Single task should complete with correct timing."""
        nodes = {"n0": Node(id="n0", compute_capacity=100)}
        network = Network(nodes=nodes, links={})

        tasks = {"T0": Task(id="T0", compute_cost=100, dag_id="dag_1")}
        dag = DAG(id="dag_1", tasks=tasks, edges=[])

        scheduler = RoundRobinScheduler()
        result = run_simulation(network, dag, scheduler, seed=42)

        # 100 compute units / 100 capacity = 1 second
        assert result.makespan == 1.0
        assert result.status == "completed"

    def test_parallel_tasks(self):
        """Independent tasks on different nodes should run in parallel."""
        nodes = {
            "n0": Node(id="n0", compute_capacity=100),
            "n1": Node(id="n1", compute_capacity=100)
        }
        network = Network(nodes=nodes, links={})

        # Two independent tasks
        tasks = {
            "T0": Task(id="T0", compute_cost=100, dag_id="dag_1", pinned_to="n0"),
            "T1": Task(id="T1", compute_cost=100, dag_id="dag_1", pinned_to="n1")
        }
        dag = DAG(id="dag_1", tasks=tasks, edges=[])

        scheduler = RoundRobinScheduler()
        result = run_simulation(network, dag, scheduler, seed=42)

        # Both tasks run in parallel, complete at t=1
        assert result.makespan == 1.0

    def test_sequential_tasks_same_node(self):
        """Dependent tasks on same node run sequentially."""
        nodes = {"n0": Node(id="n0", compute_capacity=100)}
        network = Network(nodes=nodes, links={})

        tasks = {
            "T0": Task(id="T0", compute_cost=100, dag_id="dag_1"),
            "T1": Task(id="T1", compute_cost=100, dag_id="dag_1")
        }
        edges = [Edge(from_task="T0", to_task="T1", data_size=0)]
        dag = DAG(id="dag_1", tasks=tasks, edges=edges)

        scheduler = RoundRobinScheduler()
        result = run_simulation(network, dag, scheduler, seed=42)

        # T0: 0->1, T1: 1->2
        assert result.makespan == 2.0


class TestTransferTiming:
    """Tests for data transfer timing."""

    def test_transfer_time_calculation(self):
        """Transfer time should include bandwidth and latency."""
        nodes = {
            "n0": Node(id="n0", compute_capacity=1000),  # Fast compute
            "n1": Node(id="n1", compute_capacity=1000)
        }
        links = {
            "l01": Link(id="l01", from_node="n0", to_node="n1", bandwidth=100, latency=0.5)
        }
        network = Network(nodes=nodes, links=links)

        tasks = {
            "T0": Task(id="T0", compute_cost=100, dag_id="dag_1", pinned_to="n0"),
            "T1": Task(id="T1", compute_cost=100, dag_id="dag_1", pinned_to="n1")
        }
        # 100 MB at 100 MB/s = 1 second + 0.5 second latency = 1.5 seconds
        edges = [Edge(from_task="T0", to_task="T1", data_size=100)]
        dag = DAG(id="dag_1", tasks=tasks, edges=edges)

        scheduler = RoundRobinScheduler()
        result = run_simulation(network, dag, scheduler, seed=42)

        # T0: 0 -> 0.1s (100/1000)
        # Transfer: 0.1 -> 1.6s (100/100 + 0.5 latency)
        # T1: 1.6 -> 1.7s (100/1000)
        expected_makespan = 0.1 + 1.0 + 0.5 + 0.1  # 1.7
        assert abs(result.makespan - expected_makespan) < 0.001


@pytest.mark.skipif(not SAGA_AVAILABLE, reason="SAGA not installed")
class TestHEFTScheduling:
    """Tests for HEFT scheduler behavior."""

    def test_heft_assigns_all_tasks(self):
        """HEFT should assign all tasks to valid nodes."""
        nodes = {
            "n0": Node(id="n0", compute_capacity=100),
            "n1": Node(id="n1", compute_capacity=50)
        }
        links = {
            "l01": Link(id="l01", from_node="n0", to_node="n1", bandwidth=100, latency=0.001)
        }
        network = Network(nodes=nodes, links=links)

        tasks = {
            "T0": Task(id="T0", compute_cost=100, dag_id="dag_1"),
            "T1": Task(id="T1", compute_cost=200, dag_id="dag_1"),
            "T2": Task(id="T2", compute_cost=150, dag_id="dag_1")
        }
        edges = [
            Edge(from_task="T0", to_task="T1", data_size=50),
            Edge(from_task="T0", to_task="T2", data_size=50)
        ]
        dag = DAG(id="dag_1", tasks=tasks, edges=edges)

        scheduler = create_scheduler("heft")
        result = run_simulation(network, dag, scheduler, seed=42)

        assert result.status == "completed"
        assert result.makespan > 0


class TestDirectRoutingUnreachable:
    """Direct routing on topology requiring multi-hop should report error."""

    def test_direct_routing_multi_hop_forced_reports_error(self):
        """multi_hop_forced topology with direct routing should fail, not silently succeed."""
        # 3-node chain: n0 -> n1 -> n2 (no direct n0 -> n2 link)
        nodes = {
            "n0": Node(id="n0", compute_capacity=100),
            "n1": Node(id="n1", compute_capacity=100),
            "n2": Node(id="n2", compute_capacity=100),
        }
        links = {
            "l01": Link(id="l01", from_node="n0", to_node="n1", bandwidth=100, latency=0.01),
            "l12": Link(id="l12", from_node="n1", to_node="n2", bandwidth=100, latency=0.01),
        }
        network = Network(nodes=nodes, links=links)

        # Pin T0 to n0, T1 to n2 — forces transfer across n0->n2 (no direct link)
        tasks = {
            "T0": Task(id="T0", compute_cost=100, dag_id="dag1", pinned_to="n0"),
            "T1": Task(id="T1", compute_cost=100, dag_id="dag1", pinned_to="n2"),
        }
        edges = [Edge(from_task="T0", to_task="T1", data_size=50)]
        dag = DAG(id="dag1", tasks=tasks, edges=edges)

        scheduler = RoundRobinScheduler()
        dag_source = SingleDAGSource(dag)

        sim = Simulation(
            network=network,
            scheduler=scheduler,
            dag_source=dag_source,
            routing_model=DirectLinkRouting(),
            seed=42,
        )

        result = sim.run()

        assert result.status == "unroutable"
        assert "unreachable" in result.error_message.lower() or "no route" in result.error_message.lower()

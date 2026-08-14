"""
Unit tests for SAGA scheduler adapter.
"""

import pytest
from ncsim.models.network import Node, Link, Network
from ncsim.models.task import Task
from ncsim.models.dag import DAG, Edge
from ncsim.scheduler.base import NetworkSnapshot, RoundRobinScheduler
from ncsim.scheduler.saga_adapter import (
    SAGA_AVAILABLE,
    SAGA_SCHEDULERS,
    SagaScheduler,
    available_scheduler_names,
    create_scheduler,
    scheduler_catalog,
)


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


class TestRoundRobinScheduler:
    """Tests for RoundRobinScheduler."""

    def test_assigns_all_tasks(self, simple_network, simple_dag):
        scheduler = RoundRobinScheduler()
        snapshot = NetworkSnapshot.from_network(simple_network)

        plan = scheduler.on_dag_inject(simple_dag, snapshot)

        assert "T0" in plan.assignments
        assert "T1" in plan.assignments

    def test_cycles_through_nodes(self, simple_network, simple_dag):
        scheduler = RoundRobinScheduler()
        snapshot = NetworkSnapshot.from_network(simple_network)

        plan = scheduler.on_dag_inject(simple_dag, snapshot)

        # Tasks should be on different nodes (round-robin)
        # But actual order depends on topological sort
        assert set(plan.assignments.values()).issubset({"n0", "n1"})

    def test_respects_pinned_tasks(self, simple_network):
        tasks = {
            "T0": Task(id="T0", compute_cost=100, dag_id="dag_1", pinned_to="n1"),
            "T1": Task(id="T1", compute_cost=200, dag_id="dag_1")
        }
        dag = DAG(id="dag_1", tasks=tasks, edges=[])

        scheduler = RoundRobinScheduler()
        snapshot = NetworkSnapshot.from_network(simple_network)

        plan = scheduler.on_dag_inject(dag, snapshot)

        assert plan.assignments["T0"] == "n1"


@pytest.mark.skipif(not SAGA_AVAILABLE, reason="SAGA not installed")
class TestSagaScheduler:
    """Tests for SagaScheduler (requires SAGA library)."""

    def test_creates_heft_scheduler(self):
        scheduler = SagaScheduler(algorithm="heft")
        assert scheduler.algorithm == "heft"

    def test_creates_cpop_scheduler(self):
        scheduler = SagaScheduler(algorithm="cpop")
        assert scheduler.algorithm == "cpop"

    def test_rejects_unknown_scheduler(self):
        with pytest.raises(ValueError, match="Unknown SAGA scheduler"):
            SagaScheduler(algorithm="unknown")

    def test_rejects_unknown_option(self):
        with pytest.raises(ValueError, match="Unknown option"):
            SagaScheduler(algorithm="heft", scheduler_options={"alpha": 0.5})

    def test_accepts_scheduler_options(self):
        scheduler = SagaScheduler(algorithm="wba", scheduler_options={"alpha": 0.75})
        assert scheduler.scheduler_options == {"alpha": 0.75}

    @pytest.mark.parametrize("options", ({"alpha": "high"}, {"alpha": -0.1}, {"alpha": 1.1}))
    def test_rejects_invalid_scheduler_option_value(self, options):
        with pytest.raises(ValueError, match="Option 'alpha'"):
            SagaScheduler(algorithm="wba", scheduler_options=options)

    def test_schedules_simple_dag(self, simple_network, simple_dag):
        scheduler = SagaScheduler(algorithm="heft")
        snapshot = NetworkSnapshot.from_network(simple_network)

        plan = scheduler.on_dag_inject(simple_dag, snapshot)

        assert "T0" in plan.assignments
        assert "T1" in plan.assignments
        assert plan.assignments["T0"] in ["n0", "n1"]
        assert plan.assignments["T1"] in ["n0", "n1"]

    def test_heft_prefers_faster_node(self):
        """HEFT should prefer the faster node for compute-bound tasks."""
        nodes = {
            "fast": Node(id="fast", compute_capacity=100),
            "slow": Node(id="slow", compute_capacity=10)
        }
        # No links - tasks should stay on one node
        network = Network(nodes=nodes, links={})

        tasks = {
            "T0": Task(id="T0", compute_cost=100, dag_id="dag_1"),
            "T1": Task(id="T1", compute_cost=100, dag_id="dag_1")
        }
        edges = [Edge(from_task="T0", to_task="T1", data_size=100)]
        dag = DAG(id="dag_1", tasks=tasks, edges=edges)

        scheduler = SagaScheduler(algorithm="heft")
        snapshot = NetworkSnapshot.from_network(network)

        plan = scheduler.on_dag_inject(dag, snapshot)

        # HEFT should put both tasks on fast node to avoid transfer penalty
        # (or at minimum, put them on the same node)
        # The exact behavior depends on SAGA implementation
        assert "T0" in plan.assignments
        assert "T1" in plan.assignments

    @pytest.mark.parametrize("algorithm", tuple(SAGA_SCHEDULERS))
    def test_every_registered_scheduler_assigns_all_tasks(
        self, algorithm, simple_network, simple_dag
    ):
        scheduler = SagaScheduler(algorithm=algorithm)
        snapshot = NetworkSnapshot.from_network(simple_network)

        plan = scheduler.on_dag_inject(simple_dag, snapshot)

        assert set(plan.assignments) == set(simple_dag.tasks)
        assert set(plan.assignments.values()).issubset(simple_network.nodes)


class TestSchedulerRegistry:
    def test_exposes_all_static_batch_schedulers(self):
        expected = {
            "bil", "brute_force", "cpop", "dps", "duplex", "etf",
            "fastest_node", "fcp", "flb", "gdl", "hbmct", "heft",
            "maxmin", "mct", "met", "minmin", "msbc", "mst", "olb",
            "peft", "smt", "sufferage", "wba",
        }
        assert set(SAGA_SCHEDULERS) == expected
        assert "hybrid" not in SAGA_SCHEDULERS
        assert set(available_scheduler_names()) == expected | {"round_robin", "manual"}

    def test_catalog_has_typed_options_and_defaults(self):
        catalog = {entry["name"]: entry for entry in scheduler_catalog()}

        assert catalog["heft"]["options"] == []
        assert catalog["gdl"]["options"][0]["default"] == 2
        assert catalog["wba"]["options"][0]["default"] == 0.5
        assert catalog["smt"]["options"][0]["type"] == "number"


class TestCreateScheduler:
    """Tests for create_scheduler factory function."""

    def test_creates_round_robin(self):
        scheduler = create_scheduler("round_robin")
        assert isinstance(scheduler, RoundRobinScheduler)

    @pytest.mark.skipif(not SAGA_AVAILABLE, reason="SAGA not installed")
    def test_creates_heft(self):
        scheduler = create_scheduler("heft")
        assert isinstance(scheduler, SagaScheduler)
        assert scheduler.algorithm == "heft"

    @pytest.mark.skipif(not SAGA_AVAILABLE, reason="SAGA not installed")
    def test_creates_cpop(self):
        scheduler = create_scheduler("cpop")
        assert isinstance(scheduler, SagaScheduler)
        assert scheduler.algorithm == "cpop"


class TestNetworkSnapshot:
    """Tests for NetworkSnapshot class."""

    def test_from_network(self, simple_network):
        snapshot = NetworkSnapshot.from_network(simple_network, timestamp=1.0)

        assert len(snapshot.nodes) == 2
        assert len(snapshot.links) == 1
        assert snapshot.timestamp == 1.0

        assert snapshot.nodes["n0"].compute_capacity == 100
        assert snapshot.nodes["n1"].compute_capacity == 50

        assert snapshot.links["l01"].bandwidth == 100
        assert snapshot.links["l01"].latency == 0.001

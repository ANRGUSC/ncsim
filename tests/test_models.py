"""
Unit tests for data models.
"""

import pytest
from ncsim.models.network import Node, Link, Network, Position, StaticLinkModel
from ncsim.models.task import Task, TaskState, TaskStatus, FIFOQueueModel
from ncsim.models.dag import DAG, Edge, SingleDAGSource


class TestNode:
    """Tests for Node class."""

    def test_creates_node(self):
        node = Node(id="n0", compute_capacity=100)
        assert node.id == "n0"
        assert node.compute_capacity == 100

    def test_creates_node_with_position(self):
        node = Node(id="n0", compute_capacity=100, position=Position(1.0, 2.0))
        assert node.position.x == 1.0
        assert node.position.y == 2.0

    def test_rejects_zero_capacity(self):
        with pytest.raises(ValueError):
            Node(id="n0", compute_capacity=0)

    def test_rejects_negative_capacity(self):
        with pytest.raises(ValueError):
            Node(id="n0", compute_capacity=-100)


class TestLink:
    """Tests for Link class."""

    def test_creates_link(self):
        link = Link(id="l01", from_node="n0", to_node="n1", bandwidth=100)
        assert link.id == "l01"
        assert link.from_node == "n0"
        assert link.to_node == "n1"
        assert link.bandwidth == 100
        assert link.latency == 0.0

    def test_creates_link_with_latency(self):
        link = Link(id="l01", from_node="n0", to_node="n1", bandwidth=100, latency=0.01)
        assert link.latency == 0.01

    def test_rejects_zero_bandwidth(self):
        with pytest.raises(ValueError):
            Link(id="l01", from_node="n0", to_node="n1", bandwidth=0)

    def test_rejects_negative_latency(self):
        with pytest.raises(ValueError):
            Link(id="l01", from_node="n0", to_node="n1", bandwidth=100, latency=-1)


class TestNetwork:
    """Tests for Network class."""

    def test_creates_empty_network(self):
        network = Network()
        assert len(network) == 0

    def test_creates_network_with_nodes(self):
        nodes = {
            "n0": Node(id="n0", compute_capacity=100),
            "n1": Node(id="n1", compute_capacity=50)
        }
        network = Network(nodes=nodes)
        assert len(network) == 2

    def test_get_node(self):
        nodes = {"n0": Node(id="n0", compute_capacity=100)}
        network = Network(nodes=nodes)
        assert network.get_node("n0").id == "n0"
        assert network.get_node("n1") is None

    def test_get_link_between(self):
        nodes = {
            "n0": Node(id="n0", compute_capacity=100),
            "n1": Node(id="n1", compute_capacity=50)
        }
        links = {
            "l01": Link(id="l01", from_node="n0", to_node="n1", bandwidth=100)
        }
        network = Network(nodes=nodes, links=links)

        link = network.get_link_between("n0", "n1")
        assert link.id == "l01"

        # No reverse link
        assert network.get_link_between("n1", "n0") is None

    def test_are_connected(self):
        nodes = {
            "n0": Node(id="n0", compute_capacity=100),
            "n1": Node(id="n1", compute_capacity=50)
        }
        links = {
            "l01": Link(id="l01", from_node="n0", to_node="n1", bandwidth=100)
        }
        network = Network(nodes=nodes, links=links)

        assert network.are_connected("n0", "n1") is True
        assert network.are_connected("n1", "n0") is False

    def test_validates_link_endpoints(self):
        nodes = {"n0": Node(id="n0", compute_capacity=100)}
        links = {
            "l01": Link(id="l01", from_node="n0", to_node="n1", bandwidth=100)
        }
        with pytest.raises(ValueError, match="to_node 'n1' not found"):
            Network(nodes=nodes, links=links)


class TestStaticLinkModel:
    """Tests for StaticLinkModel class."""

    def test_returns_static_bandwidth(self):
        link = Link(id="l01", from_node="n0", to_node="n1", bandwidth=100)
        model = StaticLinkModel()
        assert model.get_effective_bandwidth(link, 0.0) == 100
        assert model.get_effective_bandwidth(link, 1000.0) == 100


class TestTask:
    """Tests for Task class."""

    def test_creates_task(self):
        task = Task(id="T0", compute_cost=100)
        assert task.id == "T0"
        assert task.compute_cost == 100

    def test_execution_time(self):
        task = Task(id="T0", compute_cost=100)
        assert task.execution_time(100) == 1.0
        assert task.execution_time(50) == 2.0

    def test_rejects_negative_cost(self):
        with pytest.raises(ValueError):
            Task(id="T0", compute_cost=-100)

    def test_accepts_zero_cost(self):
        task = Task(id="T0", compute_cost=0)
        assert task.compute_cost == 0


class TestTaskState:
    """Tests for TaskState class."""

    def test_creates_pending_state(self):
        state = TaskState(task_id="T0", dag_id="dag_1")
        assert state.status == TaskStatus.PENDING
        assert state.is_ready() is True  # No predecessors

    def test_tracks_predecessors(self):
        state = TaskState(
            task_id="T1",
            dag_id="dag_1",
            predecessors_remaining={"T0"}
        )
        assert state.is_ready() is False

    def test_mark_predecessor_complete(self):
        state = TaskState(
            task_id="T2",
            dag_id="dag_1",
            predecessors_remaining={"T0", "T1"}
        )

        result = state.mark_predecessor_complete("T0")
        assert result is False  # Still waiting for T1
        assert state.is_ready() is False

        result = state.mark_predecessor_complete("T1")
        assert result is True  # Now ready
        assert state.is_ready() is True


class TestFIFOQueueModel:
    """Tests for FIFOQueueModel class."""

    def test_creates_empty_queue(self):
        queue = FIFOQueueModel()
        assert queue.is_empty()
        assert len(queue) == 0

    def test_enqueue_dequeue(self):
        queue = FIFOQueueModel()
        state1 = TaskState(task_id="T0", dag_id="dag_1")
        state2 = TaskState(task_id="T1", dag_id="dag_1")

        queue.enqueue(state1)
        queue.enqueue(state2)

        assert len(queue) == 2
        assert queue.dequeue().task_id == "T0"
        assert queue.dequeue().task_id == "T1"

    def test_peek(self):
        queue = FIFOQueueModel()
        state = TaskState(task_id="T0", dag_id="dag_1")
        queue.enqueue(state)

        assert queue.peek().task_id == "T0"
        assert len(queue) == 1  # Still there

    def test_can_start_task(self):
        queue = FIFOQueueModel()
        assert queue.can_start_task(None) is True  # No current task

        state = TaskState(task_id="T0", dag_id="dag_1")
        assert queue.can_start_task(state) is False  # Has current task


class TestDAG:
    """Tests for DAG class."""

    def test_creates_empty_dag(self):
        dag = DAG(id="dag_1")
        assert dag.id == "dag_1"
        assert len(dag) == 0

    def test_creates_dag_with_tasks(self):
        tasks = {
            "T0": Task(id="T0", compute_cost=100),
            "T1": Task(id="T1", compute_cost=200)
        }
        dag = DAG(id="dag_1", tasks=tasks)
        assert len(dag) == 2

    def test_get_predecessors(self):
        tasks = {
            "T0": Task(id="T0", compute_cost=100),
            "T1": Task(id="T1", compute_cost=200)
        }
        edges = [Edge(from_task="T0", to_task="T1", data_size=50)]
        dag = DAG(id="dag_1", tasks=tasks, edges=edges)

        assert dag.get_predecessors("T0") == set()
        assert dag.get_predecessors("T1") == {"T0"}

    def test_get_successors(self):
        tasks = {
            "T0": Task(id="T0", compute_cost=100),
            "T1": Task(id="T1", compute_cost=200)
        }
        edges = [Edge(from_task="T0", to_task="T1", data_size=50)]
        dag = DAG(id="dag_1", tasks=tasks, edges=edges)

        assert dag.get_successors("T0") == {"T1"}
        assert dag.get_successors("T1") == set()

    def test_get_root_tasks(self):
        tasks = {
            "T0": Task(id="T0", compute_cost=100),
            "T1": Task(id="T1", compute_cost=200)
        }
        edges = [Edge(from_task="T0", to_task="T1", data_size=50)]
        dag = DAG(id="dag_1", tasks=tasks, edges=edges)

        assert dag.get_root_tasks() == ["T0"]

    def test_topological_order(self):
        tasks = {
            "T0": Task(id="T0", compute_cost=100),
            "T1": Task(id="T1", compute_cost=200),
            "T2": Task(id="T2", compute_cost=150)
        }
        edges = [
            Edge(from_task="T0", to_task="T1", data_size=50),
            Edge(from_task="T0", to_task="T2", data_size=50),
            Edge(from_task="T1", to_task="T2", data_size=50)
        ]
        dag = DAG(id="dag_1", tasks=tasks, edges=edges)

        order = dag.topological_order()
        assert order.index("T0") < order.index("T1")
        assert order.index("T0") < order.index("T2")
        assert order.index("T1") < order.index("T2")

    def test_validates_edge_tasks(self):
        tasks = {"T0": Task(id="T0", compute_cost=100)}
        edges = [Edge(from_task="T0", to_task="T1", data_size=50)]

        with pytest.raises(ValueError, match="unknown task 'T1'"):
            DAG(id="dag_1", tasks=tasks, edges=edges)


class TestEdge:
    """Tests for Edge class."""

    def test_creates_edge(self):
        edge = Edge(from_task="T0", to_task="T1", data_size=50)
        assert edge.from_task == "T0"
        assert edge.to_task == "T1"
        assert edge.data_size == 50

    def test_rejects_negative_data_size(self):
        with pytest.raises(ValueError):
            Edge(from_task="T0", to_task="T1", data_size=-50)


class TestSingleDAGSource:
    """Tests for SingleDAGSource class."""

    def test_returns_dag_once(self):
        dag = DAG(id="dag_1", inject_at=0.0)
        source = SingleDAGSource(dag)

        result = source.get_next_injection(0.0)
        assert result is not None
        assert result[0] == 0.0
        assert result[1].id == "dag_1"

        # Second call returns None
        result = source.get_next_injection(0.0)
        assert result is None

    def test_reset_allows_reinjection(self):
        dag = DAG(id="dag_1", inject_at=0.0)
        source = SingleDAGSource(dag)

        source.get_next_injection(0.0)
        source.reset()

        result = source.get_next_injection(0.0)
        assert result is not None

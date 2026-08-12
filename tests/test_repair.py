"""
Integration tests for schedule repair after link disruptions.

Two layers are under test:

1. Plan application in the engine (`_apply_reschedule_plan`): moving a
   pending task must rebuild its input state -- already-delivered inputs are
   re-issued toward the new node, in-flight deliveries to the old node are
   aborted, and committed tasks never move.
2. The repair policies (`RepairingSagaScheduler`): scope="global" replans all
   movable tasks, scope="local" replans only tasks the failure reached (plus
   movable descendants), scope="none" never repairs.
"""

import pytest

from ncsim.core.simulation import Simulation
from ncsim.models.dag import DAG, Edge, SingleDAGSource
from ncsim.models.disruptions import (
    DisruptionEvent,
    DisruptionType,
    ScheduledDisruptions,
)
from ncsim.models.network import Link, Network, Node
from ncsim.models.routing import DirectLinkRouting
from ncsim.models.task import Task, TaskStatus
from ncsim.scheduler.base import ManualScheduler, ReschedulePlan
from ncsim.scheduler.repair import RepairingSagaScheduler
from ncsim.scheduler.saga_adapter import SAGA_AVAILABLE

pytestmark = pytest.mark.skipif(not SAGA_AVAILABLE, reason="SAGA not installed")


def make_network(num_nodes: int = 2) -> Network:
    """Line topology n0 -- n1 [-- n2], unit-speed nodes, 100 MB/s links.

    ncsim links are directed; a bidirectional radio link is modeled as a pair
    of directed links, so each hop gets l{i}{i+1} and l{i+1}{i}.
    """
    nodes = {
        f"n{i}": Node(id=f"n{i}", compute_capacity=100) for i in range(num_nodes)
    }
    links = {}
    for i in range(num_nodes - 1):
        links[f"l{i}{i+1}"] = Link(
            id=f"l{i}{i+1}", from_node=f"n{i}", to_node=f"n{i+1}", bandwidth=100
        )
        links[f"l{i+1}{i}"] = Link(
            id=f"l{i+1}{i}", from_node=f"n{i+1}", to_node=f"n{i}", bandwidth=100
        )
    return Network(nodes=nodes, links=links)


def make_fan_out_dag() -> DAG:
    """root fans out to two heavy tasks that join.

    Fan-out/fan-in edges are small (1 MB) so HEFT spreads the heavy tasks
    across nodes; the interesting transfers are the placement-induced ones.
    """
    tasks = {
        "root": Task(id="root", compute_cost=10, dag_id="dag_1"),
        "P1": Task(id="P1", compute_cost=100, dag_id="dag_1"),
        "P2": Task(id="P2", compute_cost=100, dag_id="dag_1"),
        "join": Task(id="join", compute_cost=10, dag_id="dag_1"),
    }
    edges = [
        Edge(from_task="root", to_task="P1", data_size=1),
        Edge(from_task="root", to_task="P2", data_size=1),
        Edge(from_task="P1", to_task="join", data_size=1),
        Edge(from_task="P2", to_task="join", data_size=1),
    ]
    return DAG(id="dag_1", tasks=tasks, edges=edges)


def radio_link_down(time: float, i: int, j: int, duration=None) -> list:
    """Fail both directions of the radio link between n{i} and n{j}.

    A wireless link failure takes out the pair; ncsim models the pair as two
    directed links, so the generator emits two events.
    """
    return [
        DisruptionEvent(
            time=time,
            target_type="link",
            target_id=f"l{a}{b}",
            disruption_type=DisruptionType.LINK_DOWN,
            duration=duration,
        )
        for a, b in ((i, j), (j, i))
    ]


def run(scheduler, dag, disruptions, network=None, **costs):
    sim = Simulation(
        network=network or make_network(),
        scheduler=scheduler,
        dag_source=SingleDAGSource(dag),
        routing_model=DirectLinkRouting(),
        disruption_model=ScheduledDisruptions(disruptions),
        **costs,
    )
    return sim, sim.run()


class TestPlanApplication:
    """Engine-level semantics of applying a ReschedulePlan, isolated from any
    placement policy by a scheduler that returns a fixed plan."""

    class FixedPlanScheduler(ManualScheduler):
        """Moves dag_1:J to n0 on the first link event."""

        def on_network_change(self, change_type, target_id, network_snapshot,
                              network_state=None):
            return ReschedulePlan(new_assignments={"dag_1:J": "n0"})

    @staticmethod
    def make_join_dag() -> DAG:
        """W1 (fast, n0) and W2 (slow, n1) feed J (pinned n1 initially)."""
        tasks = {
            "W1": Task(id="W1", compute_cost=10, dag_id="dag_1", pinned_to="n0"),
            "W2": Task(id="W2", compute_cost=200, dag_id="dag_1", pinned_to="n1"),
            "J": Task(id="J", compute_cost=10, dag_id="dag_1", pinned_to="n1"),
        }
        edges = [
            Edge(from_task="W1", to_task="J", data_size=10),
            Edge(from_task="W2", to_task="J", data_size=100),
        ]
        return DAG(id="dag_1", tasks=tasks, edges=edges)

    def test_moved_task_reacquires_delivered_inputs_and_completes(self):
        """Hand-computed timeline for the delivered-input re-issue semantics.

        W1 runs 0->0.1 on n0; its 10 MB output reaches J on n1 at 0.2. At
        t=1.0 a degrade event fires and the plan moves J to n0. W1's output
        was delivered to the WRONG node now -- it must be re-acquired at n0,
        which is a local hand-off (W1 ran there). W2 finishes at 2.0 and ships
        100 MB back over the healthy reverse link l10 (1.0s), landing 3.0;
        J runs 3.0->3.1. A broken implementation that forgets re-delivery
        would leave W1 in J's predecessor set forever and J would never run.
        """
        degrade = DisruptionEvent(
            time=1.0,
            target_type="link",
            target_id="l01",
            disruption_type=DisruptionType.LINK_DEGRADE,
            parameters={"bandwidth_factor": 0.5},
        )
        sim, result = run(self.FixedPlanScheduler(), self.make_join_dag(), [degrade])

        j_state = sim.engine.get_task_state("dag_1", "J")
        assert j_state.status == TaskStatus.COMPLETED
        assert j_state.assigned_node == "n0"
        assert result.makespan == pytest.approx(3.1)
        assert result.metrics["disruptions"]["tasks_replanned"] == 1

    def test_moved_task_aborts_inflight_delivery_to_old_node(self):
        """A transfer in flight toward the old node is useless; it must be
        aborted and re-issued toward the new node.

        W1 completes at 0.1 and its transfer to J@n1 runs 0.1->0.2. The event
        fires at 0.15, mid-delivery. J moves to n0: the in-flight transfer is
        cancelled and W1's input becomes a local hand-off. If the stale
        delivery were left alone, J would be marked ready by data on n1.
        """
        degrade = DisruptionEvent(
            time=0.15,
            target_type="link",
            target_id="l01",
            disruption_type=DisruptionType.LINK_DEGRADE,
            parameters={"bandwidth_factor": 1.0},
        )
        sim, result = run(self.FixedPlanScheduler(), self.make_join_dag(), [degrade])

        j_state = sim.engine.get_task_state("dag_1", "J")
        assert j_state.status == TaskStatus.COMPLETED
        assert j_state.assigned_node == "n0"
        # W2 -> J now crosses l01 at full rate: W2 done at 2.0, +1s transfer,
        # J runs 3.0->3.1.
        assert result.makespan == pytest.approx(3.1)

    def test_committed_tasks_are_never_moved(self):
        """A plan targeting a RUNNING task is refused."""

        class MovesRunningTask(ManualScheduler):
            def on_network_change(self, change_type, target_id, network_snapshot,
                                  network_state=None):
                return ReschedulePlan(new_assignments={"dag_1:W2": "n0"})

        degrade = DisruptionEvent(
            time=1.0,
            target_type="link",
            target_id="l01",
            disruption_type=DisruptionType.LINK_DEGRADE,
            parameters={"bandwidth_factor": 1.0},
        )
        sim, result = run(MovesRunningTask(), self.make_join_dag(), [degrade])
        w2_state = sim.engine.get_task_state("dag_1", "W2")
        assert w2_state.assigned_node == "n1"  # unmoved
        assert result.metrics["disruptions"]["tasks_replanned"] == 0


class TestRepairPolicies:
    def test_scope_none_leaves_a_severed_workload_unfinished(self):
        """The failure cuts root's output off from one branch; without repair
        the branch and the join never run."""
        scheduler = RepairingSagaScheduler(algorithm="heft", scope="none")
        _, result = run(scheduler, make_fan_out_dag(), radio_link_down(0.05, 0, 1))
        assert result.metrics["unfinished_tasks"] == 2  # one branch + join
        assert result.metrics["disruptions"]["tasks_replanned"] == 0

    def test_global_repair_rescues_a_severed_workload(self):
        """Global repair pulls every pending task onto the surviving side.

        The link dies at 0.05 while only root has started, so all of P1, P2,
        join are movable; they serialize on root's node and the workload
        completes: 0.1 + 1 + 1 + 0.1 = 2.2.
        """
        scheduler = RepairingSagaScheduler(algorithm="heft", scope="global")
        _, result = run(scheduler, make_fan_out_dag(), radio_link_down(0.05, 0, 1))
        assert result.metrics["unfinished_tasks"] == 0
        assert result.metrics["disruptions"]["tasks_replanned"] >= 1
        assert result.makespan == pytest.approx(2.2)

    def test_global_repair_beats_waiting_out_a_long_outage(self):
        """With recovery at 5.05, waiting eventually finishes -- but far later
        than repairing at the moment of failure."""
        events = radio_link_down(0.05, 0, 1, duration=5.0)
        waited = run(
            RepairingSagaScheduler(algorithm="heft", scope="none"),
            make_fan_out_dag(), list(events),
        )[1]
        repaired = run(
            RepairingSagaScheduler(algorithm="heft", scope="global"),
            make_fan_out_dag(), list(events),
        )[1]
        assert waited.metrics["unfinished_tasks"] == 0
        assert repaired.makespan < waited.makespan

    def test_local_repair_moves_only_the_affected_chain(self):
        """Two independent pinned chains; the failure reaches only one.

        Chain X: X1@n0 -> X2@n1 crosses the failed l01 -- X2 must move.
        Chain Y: Y1@n1 -> Y2@n2 uses the healthy l12 -- Y2 must stay put.
        """
        tasks = {
            "X1": Task(id="X1", compute_cost=10, dag_id="dag_1", pinned_to="n0"),
            "X2": Task(id="X2", compute_cost=100, dag_id="dag_1", pinned_to="n1"),
            "Y1": Task(id="Y1", compute_cost=10, dag_id="dag_1", pinned_to="n1"),
            "Y2": Task(id="Y2", compute_cost=100, dag_id="dag_1", pinned_to="n2"),
        }
        edges = [
            Edge(from_task="X1", to_task="X2", data_size=10),
            Edge(from_task="Y1", to_task="Y2", data_size=10),
        ]
        dag = DAG(id="dag_1", tasks=tasks, edges=edges)

        scheduler = RepairingSagaScheduler(algorithm="heft", scope="local")
        sim, result = run(
            scheduler, dag, radio_link_down(0.05, 0, 1), network=make_network(3)
        )

        x2_state = sim.engine.get_task_state("dag_1", "X2")
        y2_state = sim.engine.get_task_state("dag_1", "Y2")
        assert x2_state.assigned_node == "n0", "affected task moves off the cut"
        assert y2_state.assigned_node == "n2", "unaffected task keeps its node"
        assert result.metrics["unfinished_tasks"] == 0
        assert result.metrics["disruptions"]["tasks_replanned"] == 1

    def test_local_repair_replans_movable_descendants_too(self):
        """Moving a task moves where its output lands: its movable descendants
        are part of the repair, mirroring the descendant closure in saga."""
        tasks = {
            "X1": Task(id="X1", compute_cost=10, dag_id="dag_1", pinned_to="n0"),
            "X2": Task(id="X2", compute_cost=100, dag_id="dag_1", pinned_to="n1"),
            "X3": Task(id="X3", compute_cost=100, dag_id="dag_1", pinned_to="n2"),
        }
        edges = [
            Edge(from_task="X1", to_task="X2", data_size=10),
            Edge(from_task="X2", to_task="X3", data_size=10),
        ]
        dag = DAG(id="dag_1", tasks=tasks, edges=edges)

        scheduler = RepairingSagaScheduler(algorithm="heft", scope="local")
        sim, result = run(
            scheduler, dag, radio_link_down(0.05, 0, 1), network=make_network(3)
        )
        assert result.metrics["unfinished_tasks"] == 0
        assert result.metrics["disruptions"]["tasks_replanned"] == 2  # X2 and X3

    def test_rejects_unknown_scope(self):
        with pytest.raises(ValueError, match="scope"):
            RepairingSagaScheduler(scope="everything")


class TestRepairCost:
    """Decision latency: a plan computed at t applies at t + delta, where
    delta = repair_cost_base + repair_cost_per_task * |plan|. The old schedule
    keeps executing in the window and commitments win."""

    @pytest.mark.parametrize(
        "per_task_cost, expected_node, expected_makespan",
        [
            # Applied at 1.5: J is still pending (W2 runs to 2.0), so the
            # move lands; W2's output crosses l10 (1s) and J runs 3.0->3.1.
            (0.5, "n0", 3.1),
            # Applied at 2.5: too late. W2 finished at 2.0 next to J on n1,
            # J started immediately (committed) and the move is refused.
            (1.5, "n1", 2.1),
        ],
    )
    def test_per_task_cost_can_flip_the_outcome(
        self, per_task_cost, expected_node, expected_makespan
    ):
        """The identical plan helps or fizzles depending only on how long the
        decision takes -- the mechanism behind charging repair to makespan."""
        degrade = DisruptionEvent(
            time=1.0,
            target_type="link",
            target_id="l01",
            disruption_type=DisruptionType.LINK_DEGRADE,
            parameters={"bandwidth_factor": 1.0},
        )
        sim, result = run(
            TestPlanApplication.FixedPlanScheduler(),
            TestPlanApplication.make_join_dag(),
            [degrade],
            repair_cost_per_task=per_task_cost,  # plan moves exactly 1 task
        )
        j_state = sim.engine.get_task_state("dag_1", "J")
        assert j_state.status == TaskStatus.COMPLETED
        assert j_state.assigned_node == expected_node
        assert result.makespan == pytest.approx(expected_makespan)

    def test_costly_global_repair_still_rescues_but_later(self):
        """The severed fan-out is still saved, at 4.15 instead of 2.2.

        The plan (computed at 0.05) applies at 3.05. The co-located branch ran
        meanwhile (0.1->1.1, committed); the stranded branch waits for the
        repair, runs 3.05->4.05, and the join lands 4.05->4.15. The second
        failure event of the radio pair supersedes the first plan.
        """
        scheduler = RepairingSagaScheduler(algorithm="heft", scope="global")
        _, result = run(
            scheduler,
            make_fan_out_dag(),
            radio_link_down(0.05, 0, 1),
            repair_cost_base=3.0,
        )
        assert result.metrics["unfinished_tasks"] == 0
        assert result.makespan == pytest.approx(4.15)
        assert result.metrics["disruptions"]["repairs_superseded"] == 1
        assert result.metrics["repair_wall_time_s"] >= 0.0

    def test_zero_cost_is_the_free_repair_baseline(self):
        """Defaults reproduce the free-repair makespan exactly."""
        scheduler = RepairingSagaScheduler(algorithm="heft", scope="global")
        _, result = run(scheduler, make_fan_out_dag(), radio_link_down(0.05, 0, 1))
        assert result.makespan == pytest.approx(2.2)

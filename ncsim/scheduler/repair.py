"""
Repairing scheduler: replans task placements when a link is disrupted.

Implements the repair-scope policies of the schedule-repair study:

- scope="none":   never repair; transfers stall and retry (the engine's
                  default behavior), and multi-hop routing may still detour.
- scope="local":  replan only the movable tasks the disruption actually
                  reached -- those with an undelivered input whose endpoints
                  straddle the changed link -- plus their movable descendants.
                  Every other pending task keeps its node.
- scope="global": replan every movable task against the disrupted network.

Both repair scopes delegate the actual placement to the SAGA scheduler with
the committed tasks pinned as a partial schedule, so the placement algorithm
is identical across scopes; only *how much* of the schedule may move differs.
Kept tasks are held in place via SAGA's node constraints, which means local
repair plans the affected tasks in the context of the placements it is
preserving rather than pretending the rest of the schedule moved too.
"""

import logging
from typing import Dict, Optional, Set, TYPE_CHECKING

from ncsim.models.dag import DAG
from ncsim.models.task import TaskStatus
from ncsim.scheduler.base import (
    NetworkSnapshot,
    PlacementPlan,
    ReschedulePlan,
)
from ncsim.scheduler.saga_adapter import SagaScheduler, SAGA_AVAILABLE

if TYPE_CHECKING:
    from ncsim.core.execution_engine import NetworkState
    from ncsim.models.routing import WidestPathRouting

logger = logging.getLogger(__name__)

if SAGA_AVAILABLE:
    from saga import Schedule as SagaSchedule
    from saga import ScheduledTask as SagaScheduledTask

# Task states a repair may move. Anything else is committed: it started (or
# is starting this instant) on its node, and repair never moves history.
MOVABLE = (TaskStatus.PENDING, TaskStatus.QUEUED)

REPAIR_SCOPES = ("none", "local", "global")


class RepairingSagaScheduler(SagaScheduler):
    """SAGA-backed scheduler that also repairs placements on link disruptions.

    Scheduling at injection is inherited unchanged from SagaScheduler; this
    class adds the on_network_change policy.
    """

    def __init__(
        self,
        algorithm: str = "heft",
        routing: Optional["WidestPathRouting"] = None,
        scope: str = "global",
    ):
        """Initialize the repairing scheduler.

        Args:
            algorithm: SAGA algorithm for placement ("heft" or "cpop")
            routing: Optional multi-hop routing for bandwidth-aware planning
            scope: Repair scope -- "none", "local", or "global"
        """
        super().__init__(algorithm=algorithm, routing=routing)
        if scope not in REPAIR_SCOPES:
            raise ValueError(f"scope must be one of {REPAIR_SCOPES}, got '{scope}'")
        self.scope = scope
        self._dags: Dict[str, DAG] = {}

    def on_dag_inject(
        self, dag: DAG, network_snapshot: NetworkSnapshot
    ) -> PlacementPlan:
        """Schedule as usual, remembering the DAG for later repairs."""
        self._dags[dag.id] = dag
        return super().on_dag_inject(dag, network_snapshot)

    def on_network_change(
        self,
        change_type: str,
        target_id: str,
        network_snapshot: NetworkSnapshot,
        network_state: Optional["NetworkState"] = None,
    ) -> Optional[ReschedulePlan]:
        """Repair the placement after a link event, per the configured scope."""
        if self.scope == "none" or network_state is None:
            return None
        if change_type not in ("link_down", "link_degrade", "recovery"):
            return None

        new_assignments: Dict[str, str] = {}
        for dag_id, dag in self._dags.items():
            replan = self._select_replan_set(
                dag_id, dag, target_id, network_snapshot, network_state
            )
            if not replan:
                continue
            new_assignments.update(
                self._replan_dag(
                    dag_id, dag, replan, network_snapshot, network_state
                )
            )

        if not new_assignments:
            return None
        logger.info(
            f"{self.scope} repair after {change_type} on {target_id}: "
            f"moving {sorted(new_assignments)}"
        )
        return ReschedulePlan(
            new_assignments=new_assignments,
            metadata={"scope": self.scope, "trigger": change_type, "link": target_id},
        )

    def _movable_tasks(self, dag_id: str, network_state: "NetworkState") -> Set[str]:
        """Task ids in `dag_id` that have not started and so may move."""
        movable = set()
        for key, task_state in network_state.task_states.items():
            key_dag, task_id = key.split(":", 1)
            if key_dag == dag_id and task_state.status in MOVABLE:
                movable.add(task_id)
        return movable

    def _select_replan_set(
        self,
        dag_id: str,
        dag: DAG,
        link_id: str,
        snapshot: NetworkSnapshot,
        network_state: "NetworkState",
    ) -> Set[str]:
        """Choose which of the DAG's movable tasks this repair may move."""
        movable = self._movable_tasks(dag_id, network_state)
        if not movable:
            return set()
        if self.scope == "global":
            return movable

        # Local scope: a task is affected when one of its *undelivered* inputs
        # would cross the changed link -- its parent sits on one endpoint and
        # the task itself on the other. (With multi-hop routing a transfer may
        # cross the link on a longer path too; the endpoint test is the direct
        # criterion, mirroring saga's changed-links repair semantics.)
        link = snapshot.links.get(link_id)
        if link is None:
            return set()
        endpoints = {link.from_node, link.to_node}

        affected: Set[str] = set()
        for task_id in movable:
            task_state = network_state.get_task_state(dag_id, task_id)
            if task_state is None:
                continue
            for parent_id in task_state.predecessors_remaining:
                parent_state = network_state.get_task_state(dag_id, parent_id)
                if parent_state is None:
                    continue
                if {parent_state.assigned_node, task_state.assigned_node} == endpoints:
                    affected.add(task_id)
                    break

        # Moving a task moves where its output lands, so movable descendants
        # are replanned with it; without this closure a kept child could sit
        # waiting for data on a node its parent no longer sends to.
        closure = set(affected)
        frontier = list(affected)
        while frontier:
            task_id = frontier.pop()
            for successor in dag.get_successors(task_id):
                if successor in movable and successor not in closure:
                    closure.add(successor)
                    frontier.append(successor)
        return closure

    def _replan_dag(
        self,
        dag_id: str,
        dag: DAG,
        replan: Set[str],
        snapshot: NetworkSnapshot,
        network_state: "NetworkState",
    ) -> Dict[str, str]:
        """Replan `replan` within one DAG; returns dag-qualified assignments.

        Committed tasks enter the SAGA schedule with their actual execution
        windows; kept movable tasks are constrained to their current node; the
        replan set is left free. SAGA then plans everything unscheduled
        against the disrupted network, and only the replan set's placements
        are extracted.
        """
        node_ids = list(snapshot.nodes.keys())
        node_idx = {node_id: i for i, node_id in enumerate(node_ids)}
        saga_name = {node_id: f"node_{node_idx[node_id]}" for node_id in node_ids}

        saga_network = self._build_saga_network(snapshot)
        saga_taskgraph = self._build_saga_taskgraph(dag)

        movable = self._movable_tasks(dag_id, network_state)
        kept = movable - replan
        constraints = {}
        for task_id in kept:
            task_state = network_state.get_task_state(dag_id, task_id)
            if task_state and task_state.assigned_node:
                constraints[task_id] = {saga_name[task_state.assigned_node]}

        partial = SagaSchedule(
            saga_taskgraph, saga_network, node_constraints=constraints or None
        )
        for task_id in dag.tasks:
            task_state = network_state.get_task_state(dag_id, task_id)
            if task_state is None or task_state.status in MOVABLE:
                continue
            start, end = self._execution_window(task_state, dag, snapshot)
            partial.add_task(
                SagaScheduledTask(
                    node=saga_name[task_state.assigned_node],
                    name=task_id,
                    start=start,
                    end=end,
                )
            )

        schedule = self._scheduler.schedule(
            saga_network,
            saga_taskgraph,
            schedule=partial,
            min_start_time=network_state.sim_time,
        )

        assignments = self._extract_assignments(schedule, snapshot)
        return {
            f"{dag_id}:{task_id}": assignments[task_id]
            for task_id in replan
            if task_id in assignments
        }

    def _execution_window(
        self, task_state, dag: DAG, snapshot: NetworkSnapshot
    ) -> tuple:
        """The (start, end) window a committed task occupies on its node.

        COMPLETED tasks have both timestamps. RUNNING (and READY, which starts
        this instant) tasks end after their remaining execution time; without
        preemption that estimate is exact under the related-machines model.
        """
        task = dag.get_task(task_state.task_id)
        capacity = snapshot.nodes[task_state.assigned_node].compute_capacity
        if task_state.status == TaskStatus.COMPLETED:
            return task_state.started_at, task_state.completed_at
        start = (
            task_state.started_at
            if task_state.started_at is not None
            else snapshot.timestamp
        )
        return start, start + task.execution_time(capacity)

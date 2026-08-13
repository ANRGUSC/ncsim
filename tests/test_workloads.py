"""Tests for experiment workload generation across the three families."""

import pytest

from ncsim.experiments.workloads import (
    ALL_STRUCTURES,
    RIOTBENCH_STRUCTURES,
    STRUCTURES,
    WFCOMMONS_STRUCTURES,
    make_workload,
    scale_network_to_ccr,
    spatial_network,
)
from ncsim.scheduler.saga_adapter import SAGA_AVAILABLE

pytestmark = pytest.mark.skipif(not SAGA_AVAILABLE, reason="SAGA not installed")


def costs_of(dag):
    return {task_id: task.compute_cost for task_id, task in dag.tasks.items()}


class TestFamilies:
    @pytest.mark.parametrize("structure", STRUCTURES + RIOTBENCH_STRUCTURES)
    def test_same_seed_same_workload(self, structure):
        """Every family must be reproducible from (structure, seed) alone."""
        assert costs_of(make_workload(structure, seed=5)) == costs_of(
            make_workload(structure, seed=5)
        )

    @pytest.mark.parametrize("structure", STRUCTURES + RIOTBENCH_STRUCTURES)
    def test_different_seeds_differ(self, structure):
        assert costs_of(make_workload(structure, seed=5)) != costs_of(
            make_workload(structure, seed=6)
        )

    def test_wfcommons_deterministic_and_min_size_respected(self):
        """WfCommons recipes have per-recipe minimum sizes above our cap
        (montage needs 60); generation must clamp, not fail. One recipe keeps
        the suite fast; determinism logic is shared across recipes."""
        first = make_workload("epigenomics", seed=5)
        second = make_workload("epigenomics", seed=5)
        assert costs_of(first) == costs_of(second)
        assert len(first.tasks) >= 2

    def test_workload_seeding_does_not_leak_global_rng_state(self):
        """The scoped global seeding inside generators must restore state."""
        import random

        random.seed(123)
        expected = [random.random() for _ in range(3)]
        random.seed(123)
        make_workload("etl", seed=9)
        observed = [random.random() for _ in range(3)]
        assert observed == expected

    def test_unknown_structure_rejected(self):
        with pytest.raises(ValueError, match="Unknown structure"):
            make_workload("no_such_thing", seed=1)

    def test_all_structures_registry_is_consistent(self):
        assert set(ALL_STRUCTURES) == (
            set(STRUCTURES) | set(RIOTBENCH_STRUCTURES) | set(WFCOMMONS_STRUCTURES)
        )


class TestCcrScaling:
    @pytest.mark.parametrize("structure", ["out_tree", "etl"])
    def test_target_ccr_holds(self, structure):
        dag = make_workload(structure, seed=2)
        network = spatial_network(5, seed=2)
        scale_network_to_ccr(network, dag, ccr=1.0)

        mean_capacity = sum(n.compute_capacity for n in network.nodes.values()) / 5
        costs = [t.compute_cost for t in dag.tasks.values() if t.compute_cost > 0]
        sizes = [e.data_size for e in dag.edges if e.data_size > 0]
        mean_comp = (sum(costs) / len(costs)) / mean_capacity
        bandwidth = next(iter(network.links.values())).bandwidth
        mean_comm = (sum(sizes) / len(sizes)) / bandwidth
        assert mean_comm / mean_comp == pytest.approx(1.0)

"""Experiment machinery for the schedule-repair study."""

from ncsim.experiments.oracle import (
    FixedPlacementScheduler,
    OracleResult,
    oracle_run,
    phase_networks,
)
from ncsim.experiments.runner import (
    ExperimentConfig,
    GENERATORS,
    POLICIES,
    build_trace,
    load_records,
    run_matrix,
    save_records,
    undisrupted_makespan,
)
from ncsim.experiments.workloads import (
    ALL_STRUCTURES,
    RIOTBENCH_STRUCTURES,
    STRUCTURES,
    WFCOMMONS_STRUCTURES,
    make_workload,
    riotbench_dag,
    scale_network_to_ccr,
    spatial_network,
    synthetic_dag,
    wfcommons_dag,
)

__all__ = [
    "ALL_STRUCTURES",
    "ExperimentConfig",
    "FixedPlacementScheduler",
    "GENERATORS",
    "OracleResult",
    "POLICIES",
    "RIOTBENCH_STRUCTURES",
    "STRUCTURES",
    "WFCOMMONS_STRUCTURES",
    "build_trace",
    "load_records",
    "make_workload",
    "oracle_run",
    "phase_networks",
    "riotbench_dag",
    "run_matrix",
    "save_records",
    "scale_network_to_ccr",
    "spatial_network",
    "synthetic_dag",
    "undisrupted_makespan",
    "wfcommons_dag",
]

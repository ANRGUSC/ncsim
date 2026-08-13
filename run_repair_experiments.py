"""
Run the schedule-repair experiment matrix and save records.

Usage:
    python run_repair_experiments.py --output results/repair [options]

Writes records.jsonl (one record per simulated run) and config.json into the
output directory. Plot with plot_repair_experiments.py.
"""

import argparse
import json
import time
from pathlib import Path

from ncsim.experiments import ExperimentConfig, run_matrix, save_records
from ncsim.experiments.runner import GENERATORS, POLICIES
from ncsim.experiments.workloads import ALL_STRUCTURES, STRUCTURES


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--instances", type=int, default=10,
                        help="Instances per DAG structure (default: 10)")
    parser.add_argument("--nodes", type=int, default=5,
                        help="Network size (default: 5)")
    parser.add_argument("--ccrs", nargs="+", type=float,
                        default=[0.2, 0.5, 1.0, 2.0, 5.0],
                        help="Communication-to-computation ratios; every "
                             "instance runs once per value")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--structures", nargs="+", default=list(STRUCTURES),
                        choices=list(ALL_STRUCTURES),
                        help="Workload structures; synthetic by default. Also "
                             "available: RIoTBench pipelines (etl, stats, "
                             "train, predict) and WfCommons workflows "
                             "(epigenomics, montage, seismology)")
    parser.add_argument("--generators", nargs="+", default=list(GENERATORS),
                        choices=list(GENERATORS))
    parser.add_argument("--policies", nargs="+", default=list(POLICIES),
                        choices=list(POLICIES))
    parser.add_argument("--repair-costs", nargs="+", type=float,
                        default=[0.0, 0.01, 0.02, 0.05, 0.1],
                        help="Per-moved-task decision latency as fractions of "
                             "M0 (costed policies run once per value)")
    args = parser.parse_args()

    config = ExperimentConfig(
        structures=tuple(args.structures),
        instances_per_structure=args.instances,
        num_nodes=args.nodes,
        ccrs=tuple(args.ccrs),
        generators=tuple(args.generators),
        policies=tuple(args.policies),
        repair_cost_fracs=tuple(args.repair_costs),
        seed=args.seed,
    )

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    started = time.time()
    records = run_matrix(config, progress=print)
    elapsed = time.time() - started

    save_records(records, output / "records.jsonl")
    with open(output / "config.json", "w", encoding="utf-8") as handle:
        json.dump(
            {
                "structures": list(config.structures),
                "instances_per_structure": config.instances_per_structure,
                "num_nodes": config.num_nodes,
                "ccrs": list(config.ccrs),
                "generators": list(config.generators),
                "policies": list(config.policies),
                "repair_cost_fracs": list(config.repair_cost_fracs),
                "seed": config.seed,
                "records": len(records),
                "wall_seconds": round(elapsed, 1),
            },
            handle,
            indent=2,
        )
    print(f"\n{len(records)} records in {elapsed:.1f}s -> {output / 'records.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

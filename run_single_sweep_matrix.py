"""
Exhaustive single-failure sweep for the main experiment matrix.

For every workload variant (structure x instance x CCR), fail EVERY radio
pair at EVERY start time on a fixed grid, instead of sampling one random
(pair, time) draw per variant. Each (pair, time) cell becomes its own
sample: records carry instance = "structure-idx#pA-Bt0.3" so downstream
aggregation treats cells independently, and swept = true so the plotter can
condition on biting cells.

Usage:
    python run_single_sweep_matrix.py --output DIR [--structures ...]
        [--policies wait reroute local global oracle] [--repair-costs 0.0]

Ladder stage:   default policies at cost 0.
Cost stage:     --policies local global --repair-costs 0.01 0.02 ... 0.5
                (cost-0 runs come from the ladder stage; wait/reroute/oracle
                are cost-independent).

Records stream to records.jsonl with a flush per record, so partial runs
keep everything they finished.
"""

import argparse
import json
import time
from pathlib import Path

from ncsim.experiments.runner import _run_policy, undisrupted_makespan
from ncsim.experiments.workloads import (
    ALL_STRUCTURES,
    make_workload,
    scale_network_to_ccr,
    spatial_network,
)
from ncsim.models.failure_traces import radio_pairs, single_failure_trace

TIME_FRACS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--structures", nargs="+", required=True,
                        choices=list(ALL_STRUCTURES))
    parser.add_argument("--instances", type=int, default=10)
    parser.add_argument("--nodes", type=int, default=5)
    parser.add_argument("--ccrs", nargs="+", type=float,
                        default=[0.2, 0.5, 1.0, 2.0, 5.0])
    parser.add_argument("--policies", nargs="+",
                        default=["wait", "reroute", "local", "global", "oracle"])
    parser.add_argument("--repair-costs", nargs="+", type=float, default=[0.0])
    parser.add_argument("--duration-frac", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    started = time.time()
    written = 0

    with open(output / "records.jsonl", "w", encoding="utf-8") as sink:
        for structure in args.structures:
            for index in range(args.instances):
                seed = args.seed * 10_000 + index
                dag = make_workload(structure, seed=seed)
                for ccr in args.ccrs:
                    network = spatial_network(args.nodes, seed=seed)
                    scale_network_to_ccr(network, dag, ccr)
                    m0 = undisrupted_makespan(network, dag)
                    pairs = sorted(tuple(sorted(k))
                                   for k in radio_pairs(network) if len(k) == 2)
                    for pair in pairs:
                        for tf in TIME_FRACS:
                            trace = single_failure_trace(
                                network, pair, time=tf * m0,
                                duration=args.duration_frac * m0)
                            cell = (f"{structure}-{index}"
                                    f"#p{pair[0]}-{pair[1]}t{tf:g}")
                            for policy in args.policies:
                                costs = (args.repair_costs
                                         if policy in ("local", "global")
                                         else [0.0])
                                for cost_frac in costs:
                                    result, extra = _run_policy(
                                        policy, network, dag, trace,
                                        cost_frac * m0)
                                    disruptions = result.metrics.get(
                                        "disruptions", {})
                                    unfinished = result.metrics.get(
                                        "unfinished_tasks", 0)
                                    record = {
                                        "instance": cell,
                                        "swept": True,
                                        "pair": f"{pair[0]}-{pair[1]}",
                                        "time_frac": tf,
                                        "ccr": ccr,
                                        "structure": structure,
                                        "seed": seed,
                                        "generator": "single",
                                        "policy": policy,
                                        "repair_cost_frac": cost_frac,
                                        "m0": m0,
                                        "makespan": result.makespan,
                                        "norm_makespan": (
                                            result.makespan / m0
                                            if m0 > 0 else None),
                                        "completed": unfinished == 0
                                        and result.status == "completed",
                                        "unfinished": unfinished,
                                        "tasks_total": len(dag.tasks),
                                        "replanned": disruptions.get(
                                            "tasks_replanned", 0),
                                        "aborted": disruptions.get(
                                            "transfers_aborted", 0),
                                        "stalled": disruptions.get(
                                            "transfers_stalled", 0),
                                        **extra,
                                    }
                                    sink.write(json.dumps(record) + "\n")
                                    sink.flush()
                                    written += 1
                    print(f"{structure}-{index} ccr={ccr:g}: done "
                          f"({written} records)", flush=True)

    elapsed = time.time() - started
    with open(output / "config.json", "w", encoding="utf-8") as handle:
        json.dump({
            "structures": args.structures,
            "instances": args.instances,
            "ccrs": args.ccrs,
            "policies": args.policies,
            "repair_cost_fracs": args.repair_costs,
            "time_fracs": list(TIME_FRACS),
            "duration_frac": args.duration_frac,
            "seed": args.seed,
            "records": written,
            "wall_seconds": round(elapsed, 1),
        }, handle, indent=2)
    print(f"\n{written} records in {elapsed:.1f}s -> {output/'records.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

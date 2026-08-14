"""
Jamming duration sweep: the main matrix's targeted jammer with its active
window swept instead of fixed at 0.6 * M0.

The jammer keeps the main experiment's targeting (same seeded pair choice,
same midpoint placement, same radius, same 0.25 * M0 start), so runs at
duration 0.6 reproduce the main matrix's jamming cell exactly; only the
active window varies. Records carry duration_frac and stream to disk.

Usage:
    python run_jamming_duration_sweep.py --output DIR
        [--durations 0.15 0.3 0.6 1.2 2.4] [--structures ...]
"""

import argparse
import json
import random
import time
from pathlib import Path

from ncsim.experiments.runner import _run_policy, undisrupted_makespan
from ncsim.experiments.workloads import (
    ALL_STRUCTURES,
    make_workload,
    scale_network_to_ccr,
    spatial_network,
)
from ncsim.models.failure_traces import (
    jammer_targeting,
    jamming_trace,
    radio_pairs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--structures", nargs="+",
                        default=list(ALL_STRUCTURES),
                        choices=list(ALL_STRUCTURES))
    parser.add_argument("--instances", type=int, default=10)
    parser.add_argument("--nodes", type=int, default=5)
    parser.add_argument("--ccrs", nargs="+", type=float,
                        default=[0.2, 0.5, 1.0, 2.0, 5.0])
    parser.add_argument("--policies", nargs="+",
                        default=["wait", "reroute", "local", "global", "oracle"])
    parser.add_argument("--durations", nargs="+", type=float,
                        default=[0.15, 0.3, 0.6, 1.2, 2.4])
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
                    # Same seeded pair choice as the main matrix's jamming
                    # generator, so duration 0.6 reproduces it exactly.
                    rng = random.Random(f"trace:jamming:{seed}")
                    pairs = [tuple(sorted(k)) for k in radio_pairs(network)
                             if len(k) == 2]
                    pairs.sort()
                    pair = rng.choice(pairs)
                    for dur in args.durations:
                        jammer = jammer_targeting(
                            network, pair, radius=40.0,
                            start=0.25 * m0, duration=dur * m0)
                        trace = jamming_trace(network, [jammer])
                        for policy in args.policies:
                            result, extra = _run_policy(
                                policy, network, dag, trace, 0.0)
                            unfinished = result.metrics.get(
                                "unfinished_tasks", 0)
                            sink.write(json.dumps({
                                "instance": f"{structure}-{index}",
                                "ccr": ccr,
                                "structure": structure,
                                "seed": seed,
                                "generator": "jamming",
                                "duration_frac": dur,
                                "policy": policy,
                                "repair_cost_frac": 0.0,
                                "m0": m0,
                                "makespan": result.makespan,
                                "completed": unfinished == 0
                                and result.status == "completed",
                                "unfinished": unfinished,
                                **extra,
                            }) + "\n")
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
            "durations": args.durations,
            "seed": args.seed,
            "records": written,
            "wall_seconds": round(elapsed, 1),
        }, handle, indent=2)
    print(f"\n{written} records in {elapsed:.1f}s -> {output/'records.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

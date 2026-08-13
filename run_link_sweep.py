"""
Link x time failure sweep for one instance: fail every radio pair at every
failure time, run every policy, and draw the impact heatmaps.

Usage:
    python run_link_sweep.py --output DIR [--structure S] [--seed N] ...

For a single workload instance this answers "where and when does a failure
bite?" exhaustively instead of sampling one random (link, time) draw: rows
are radio pairs ordered by how much planned traffic crosses them, columns
are failure start times (fractions of the undisrupted makespan M0), and the
cell color is the policy's makespan over the per-cell oracle. Failures on
idle links visibly cost nothing; the difference between panels is the value
of repair, cell by cell.
"""

import argparse
import copy
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

from ncsim.core.simulation import Simulation
from ncsim.experiments.oracle import oracle_run
from ncsim.experiments.runner import undisrupted_makespan
from ncsim.experiments.workloads import (
    ALL_STRUCTURES,
    make_workload,
    scale_network_to_ccr,
    spatial_network,
)
from ncsim.models.dag import SingleDAGSource
from ncsim.models.disruptions import ScheduledDisruptions
from ncsim.models.failure_traces import radio_pairs, single_failure_trace
from ncsim.models.routing import DirectLinkRouting, WidestPathRouting
from ncsim.scheduler.repair import RepairingSagaScheduler

POLICIES = ("wait", "reroute", "local", "global")
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"


def run_policy(policy, network, dag, trace):
    if policy == "oracle":
        return oracle_run(
            copy.deepcopy(network), [copy.deepcopy(dag)], list(trace),
            routing_model=DirectLinkRouting(),
        ).result
    scope = {"wait": "none", "reroute": "none",
             "local": "local", "global": "global"}[policy]
    routing = WidestPathRouting() if policy == "reroute" else DirectLinkRouting()
    sim = Simulation(
        network=copy.deepcopy(network),
        scheduler=RepairingSagaScheduler(algorithm="heft", scope=scope),
        dag_source=SingleDAGSource(copy.deepcopy(dag)),
        routing_model=routing,
        disruption_model=ScheduledDisruptions(list(trace)),
    )
    return sim.run()


def planned_traffic(network, dag):
    """Bytes each radio pair carries in the undisrupted plan."""
    sim = Simulation(
        network=copy.deepcopy(network),
        scheduler=RepairingSagaScheduler(algorithm="heft", scope="none"),
        dag_source=SingleDAGSource(copy.deepcopy(dag)),
        routing_model=DirectLinkRouting(),
    )
    sim.run()
    node_of = {k.split(":", 1)[1]: v.assigned_node
               for k, v in sim.engine.task_states.items()}
    traffic = {}
    for edge in dag.edges:
        src, dst = node_of[edge.from_task], node_of[edge.to_task]
        if src != dst:
            key = frozenset((src, dst))
            traffic[key] = traffic.get(key, 0.0) + edge.data_size
    return traffic


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--structure", default="out_tree", choices=ALL_STRUCTURES)
    parser.add_argument("--seed", type=int, default=420000)
    parser.add_argument("--nodes", type=int, default=5)
    parser.add_argument("--ccr", type=float, default=1.0)
    parser.add_argument("--duration-frac", type=float, default=0.5,
                        help="Outage duration as a fraction of M0")
    parser.add_argument("--compact", action="store_true",
                        help="Paper-sized figure: shorter rows, no title")
    parser.add_argument("--time-fracs", nargs="+", type=float,
                        default=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
                        help="Failure start times as fractions of M0")
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    dag = make_workload(args.structure, seed=args.seed)
    network = spatial_network(args.nodes, seed=args.seed)
    scale_network_to_ccr(network, dag, args.ccr)
    m0 = undisrupted_makespan(network, dag)
    traffic = planned_traffic(network, dag)

    pairs = sorted(
        (tuple(sorted(k)) for k in radio_pairs(network) if len(k) == 2),
        key=lambda p: -traffic.get(frozenset(p), 0.0),
    )

    records = []
    for pair in pairs:
        for tf in args.time_fracs:
            trace = single_failure_trace(
                network, pair, time=tf * m0, duration=args.duration_frac * m0
            )
            oracle = run_policy("oracle", network, dag, trace)
            for policy in POLICIES:
                result = run_policy(policy, network, dag, trace)
                records.append({
                    "pair": "-".join(pair),
                    "traffic": traffic.get(frozenset(pair), 0.0),
                    "time_frac": tf,
                    "policy": policy,
                    "makespan": result.makespan,
                    "oracle_makespan": oracle.makespan,
                    "vs_oracle": (result.makespan / oracle.makespan
                                  if oracle.makespan > 0 else None),
                    "vs_m0": result.makespan / m0,
                    "unfinished": result.metrics.get("unfinished_tasks", 0),
                    "replanned": result.metrics.get("disruptions", {}).get(
                        "tasks_replanned", 0),
                })
        print(f"pair {'-'.join(pair)} "
              f"(traffic {traffic.get(frozenset(pair), 0.0):.2f} MB): done")

    with open(output / "sweep_records.jsonl", "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")

    # ------------------------------------------------------------- heatmaps
    # Normalized by M0 so a no-impact cell is exactly 1.0 (blank): the
    # "failures on idle links cost nothing" story is visible, and values
    # below 1.0 (repair beating the original heuristic plan) show as green.
    # Diverging map: green (better) - neutral - blue (worse), neutral at 1.0.
    from matplotlib.colors import TwoSlopeNorm
    ramp = LinearSegmentedColormap.from_list(
        "impact", ["#0f7a52", "#8fd4b8", "#f4f4f2", "#a8c8ee", "#123c6e"]
    )
    by = {(r["pair"], r["time_frac"], r["policy"]): r for r in records}
    vmax = max(r["vs_m0"] for r in records)
    vmin = min(r["vs_m0"] for r in records)
    norm = TwoSlopeNorm(vcenter=1.0, vmin=min(vmin, 0.99), vmax=max(vmax, 1.01))
    pair_labels = [
        f"{'-'.join(p)}  ({traffic.get(frozenset(p), 0.0):.1f} MB)"
        for p in pairs
    ]

    row_height = 0.28 if args.compact else 0.42
    fig, axes = plt.subplots(1, len(POLICIES),
                             figsize=(3.0 * len(POLICIES) + 1.2,
                                      row_height * len(pairs) + 1.3),
                             dpi=150, sharey=True)
    for ax, policy in zip(axes, POLICIES):
        grid = [[by[("-".join(p), tf, policy)]["vs_m0"]
                 for tf in args.time_fracs] for p in pairs]
        im = ax.imshow(grid, cmap=ramp, norm=norm, aspect="auto")
        for i, row in enumerate(grid):
            for j, v in enumerate(row):
                if v is not None and abs(v - 1.0) > 0.005:
                    extreme = (v > 1 + 0.55 * (vmax - 1)) or (
                        vmin < 1 and v < 1 - 0.55 * (1 - vmin))
                    ax.annotate(f"{v:.2f}", (j, i), ha="center", va="center",
                                fontsize=5.5,
                                color="white" if extreme else TEXT_PRIMARY)
        ax.set_title(policy, fontsize=9, color=TEXT_PRIMARY)
        ax.set_xticks(range(len(args.time_fracs)))
        ax.set_xticklabels([f"{tf:g}" for tf in args.time_fracs], fontsize=6.5)
        ax.set_xlabel("failure time (frac. of $M_0$)", fontsize=7.5)
        ax.tick_params(colors=TEXT_SECONDARY)
    axes[0].set_yticks(range(len(pairs)))
    axes[0].set_yticklabels(pair_labels, fontsize=7)
    axes[0].set_ylabel("failed radio pair (planned traffic)", fontsize=8)
    cbar = fig.colorbar(im, ax=axes, fraction=0.02, pad=0.01)
    cbar.set_label("makespan / $M_0$  (green: better than plan)", fontsize=8)
    cbar.ax.tick_params(labelsize=7)
    if not args.compact:
        fig.suptitle(
            f"Link x time failure sweep: {args.structure} seed={args.seed}, "
            f"outage {args.duration_frac:g} M0 (M0={m0:.2f}); blank cells = no impact (= M0)",
            fontsize=9, y=0.99,
        )
    for ext in ("png", "pdf"):
        fig.savefig(output / f"link_sweep.{ext}", bbox_inches="tight")
    plt.close(fig)

    # Console summary: how often does each policy differ from wait?
    bite = sum(1 for p in pairs for tf in args.time_fracs
               if by[("-".join(p), tf, "wait")]["vs_m0"] > 1.001)
    cells = len(pairs) * len(args.time_fracs)
    print(f"\ncells where the failure bites (wait > M0): {bite}/{cells}")
    for policy in ("reroute", "local", "global"):
        wins = sum(
            1 for p in pairs for tf in args.time_fracs
            if by[("-".join(p), tf, policy)]["makespan"]
            < by[("-".join(p), tf, "wait")]["makespan"] - 1e-6)
        print(f"{policy:8s} strictly beats wait in {wins}/{cells} cells")
    print(f"figures -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

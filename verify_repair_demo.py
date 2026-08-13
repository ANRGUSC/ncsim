"""Step-by-step verification of one instance: task graph, network, and
per-policy Gantt charts with disruption events annotated."""

import copy
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
# Match the paper's serif type and hairline axes across every figure.
matplotlib.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "STIXGeneral", "DejaVu Serif"],
    "mathtext.fontset": "stix",
    "axes.linewidth": 0.6,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
})
import matplotlib.pyplot as plt
import networkx as nx

from ncsim.core.simulation import Simulation
from ncsim.core.event_queue import EventType
from ncsim.experiments.oracle import oracle_run, FixedPlacementScheduler
from ncsim.experiments.runner import build_trace, undisrupted_makespan
from ncsim.experiments.workloads import (
    make_workload,
    scale_network_to_ccr,
    spatial_network,
)
from ncsim.models.dag import SingleDAGSource
from ncsim.models.disruptions import ScheduledDisruptions
from ncsim.models.routing import DirectLinkRouting, WidestPathRouting
from ncsim.scheduler.repair import RepairingSagaScheduler

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
OUT.mkdir(parents=True, exist_ok=True)

SEED = 420000  # out_tree instance 0 of the paper experiments
STRUCTURE = "out_tree"

# ---------------------------------------------------------------- instance
dag = make_workload(STRUCTURE, seed=SEED)
network = spatial_network(5, seed=SEED)
scale_network_to_ccr(network, dag, ccr=1.0)
m0 = undisrupted_makespan(network, dag)

MODE = sys.argv[2] if len(sys.argv) > 2 else "experiment"
if MODE == "experiment":
    # The exact trace the experiment used for this instance.
    trace = build_trace("single", network, m0, seed=SEED)
else:
    # Targeted: fail the pair carrying the largest planned transfer, just
    # before that transfer would start, for half of M0.
    from ncsim.models.failure_traces import single_failure_trace
    probe = Simulation(
        network=copy.deepcopy(network),
        scheduler=RepairingSagaScheduler(algorithm="heft", scope="none"),
        dag_source=SingleDAGSource(copy.deepcopy(dag)),
        routing_model=DirectLinkRouting(),
    )
    probe.run()
    states = {k.split(":", 1)[1]: v for k, v in probe.engine.task_states.items()}
    best = None
    for e in dag.edges:
        src, dst = states[e.from_task].assigned_node, states[e.to_task].assigned_node
        if src != dst:
            start = states[e.from_task].completed_at
            if best is None or e.data_size > best[0]:
                best = (e.data_size, (src, dst), start, e.from_task, e.to_task)
    size, pair, start, ft, tt = best
    print(f"Targeting pair {pair} carrying {ft}->{tt} ({size:.2f} MB, "
          f"planned to start at t={start:.3f})")
    trace = single_failure_trace(network, pair, time=max(0.0, start - 0.01),
                                 duration=0.5 * m0)

fail_time = trace[0].time
fail_duration = trace[0].duration
failed_links = sorted(e.target_id for e in trace)
failed_pair = failed_links[0].replace("l_", "").split("_")  # e.g. n0, n4

print(f"M0 (undisrupted makespan): {m0:.3f}")
print(f"Failure: pair {failed_pair[0]}<->{failed_pair[1]} "
      f"({', '.join(failed_links)}) at t={fail_time:.3f} "
      f"for {fail_duration:.3f} (recovery at t={fail_time + fail_duration:.3f})")

# Consistent task colors across every chart.
task_ids = sorted(dag.tasks)
cmap = plt.get_cmap("tab20", len(task_ids))
TASK_COLOR = {t: cmap(i) for i, t in enumerate(task_ids)}

# ---------------------------------------------------------------- task graph
G = nx.DiGraph()
for tid, task in dag.tasks.items():
    G.add_node(tid, cost=task.compute_cost)
for e in dag.edges:
    G.add_edge(e.from_task, e.to_task, size=e.data_size)

# Layer by topological depth for a readable tree layout.
depth = {}
for tid in nx.topological_sort(G):
    depth[tid] = max((depth[p] + 1 for p in G.predecessors(tid)), default=0)
for tid, d in depth.items():
    G.nodes[tid]["layer"] = d
pos = nx.multipartite_layout(G, subset_key="layer", align="horizontal")
pos = {k: (x, -y) for k, (x, y) in pos.items()}  # roots on top

fig, ax = plt.subplots(figsize=(8, 5), dpi=150)
nx.draw_networkx_edges(G, pos, ax=ax, arrows=True, arrowsize=12,
                       edge_color="#52514e", width=1.0)
nx.draw_networkx_nodes(G, pos, ax=ax, node_size=900,
                       node_color=[TASK_COLOR[t] for t in G.nodes],
                       edgecolors="black", linewidths=0.8)
nx.draw_networkx_labels(G, pos, ax=ax, font_size=7,
                        labels={t: t for t in G.nodes})
for tid in G.nodes:
    x, y = pos[tid]
    ax.annotate(f"c={G.nodes[tid]['cost']:.2f}", (x, y), xytext=(0, -16),
                textcoords="offset points", ha="center", fontsize=6,
                color="#52514e")
edge_labels = {(u, v): f"{G.edges[u, v]['size']:.2f}" for u, v in G.edges}
nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, ax=ax,
                             font_size=6, font_color="#52514e")
ax.set_title(f"Task graph: {STRUCTURE} seed={SEED} "
             f"({len(dag.tasks)} tasks; node label = compute cost, "
             f"edge label = data size)", fontsize=9)
ax.axis("off")
fig.tight_layout()
fig.savefig(OUT / "1_task_graph.png")
plt.close(fig)

# ---------------------------------------------------------------- network
fig, ax = plt.subplots(figsize=(6, 5), dpi=150)
bw = next(iter(network.links.values())).bandwidth
drawn = set()
for link in network.links.values():
    key = frozenset((link.from_node, link.to_node))
    if key in drawn:
        continue
    drawn.add(key)
    a, b = network.nodes[link.from_node], network.nodes[link.to_node]
    is_failed = link.id in failed_links or link.id.replace("l_", "") in (
        "_".join(failed_pair), "_".join(reversed(failed_pair)))
    failed = frozenset((f"{failed_pair[0]}", f"{failed_pair[1]}")) == key
    ax.plot([a.position.x, b.position.x], [a.position.y, b.position.y],
            color="#e34948" if failed else "#c8c7c2",
            linewidth=2.5 if failed else 1.2,
            linestyle="--" if failed else "-", zorder=1)
    if failed:
        mx, my = (a.position.x + b.position.x) / 2, (a.position.y + b.position.y) / 2
        ax.annotate(f"FAILS t={fail_time:.2f}..{fail_time+fail_duration:.2f}",
                    (mx, my), fontsize=7, color="#e34948", ha="center",
                    xytext=(0, 6), textcoords="offset points")
for node in network.nodes.values():
    ax.scatter([node.position.x], [node.position.y], s=600, color="#2a78d6",
               edgecolors="black", zorder=2)
    ax.annotate(node.id, (node.position.x, node.position.y), ha="center",
                va="center", fontsize=8, color="white", zorder=3)
    ax.annotate(f"s={node.compute_capacity:.2f}",
                (node.position.x, node.position.y), xytext=(0, -20),
                textcoords="offset points", ha="center", fontsize=7,
                color="#0b0b0b", zorder=3)
ax.set_title(f"Network: 5 nodes, full-mesh radio pairs, all links "
             f"bandwidth={bw:.3f} (CCR=1); failed pair dashed red", fontsize=9)
ax.set_aspect("equal")
ax.margins(0.15)
fig.tight_layout()
fig.savefig(OUT / "2_network.png")
plt.close(fig)

# ---------------------------------------------------------------- runs
def run_policy(policy):
    """Run one policy; return (sim, result, repair_times, extra_label)."""
    repair_times = []
    if policy == "oracle":
        oracle = oracle_run(copy.deepcopy(network), [copy.deepcopy(dag)],
                            list(trace), routing_model=DirectLinkRouting())
        # Re-execute the winning candidate to get its engine state.
        label = oracle.label
        if label == "reactive-global":
            sched = RepairingSagaScheduler(algorithm="heft", scope="global")
        else:
            # Rebuild the fixed placement that won.
            from ncsim.experiments.oracle import phase_networks
            from ncsim.scheduler.base import NetworkSnapshot
            from ncsim.scheduler.saga_adapter import SagaScheduler
            planner = SagaScheduler(algorithm="heft")
            t_of = float(label.split("t=")[1].rstrip("]"))
            phases = phase_networks(network, trace)
            start, view = min(phases, key=lambda sv: abs(sv[0] - t_of))
            snap = NetworkSnapshot.from_network(view, timestamp=start)
            per_dag = {dag.id: dict(
                planner.on_dag_inject(copy.deepcopy(dag), snap).assignments)}
            sched = FixedPlacementScheduler(per_dag)
    else:
        scope = {"wait": "none", "reroute": "none",
                 "local": "local", "global": "global"}[policy]
        sched = RepairingSagaScheduler(algorithm="heft", scope=scope)
        label = None
    routing = WidestPathRouting() if policy == "reroute" else DirectLinkRouting()
    sim = Simulation(
        network=copy.deepcopy(network), scheduler=sched,
        dag_source=SingleDAGSource(copy.deepcopy(dag)),
        routing_model=routing,
        disruption_model=ScheduledDisruptions(list(trace)),
    )
    def listen(event):
        if event.event_type == EventType.RESCHEDULE_TRIGGER:
            repair_times.append(event.sim_time)
    sim.add_event_listener(listen)
    result = sim.run()
    return sim, result, repair_times, label

# The shared plan: same scheduler, no disruptions.
plan_sim = Simulation(
    network=copy.deepcopy(network),
    scheduler=RepairingSagaScheduler(algorithm="heft", scope="none"),
    dag_source=SingleDAGSource(copy.deepcopy(dag)),
    routing_model=DirectLinkRouting(),
)
plan_result = plan_sim.run()
plan_node = {k.split(":", 1)[1]: ts.assigned_node
             for k, ts in plan_sim.engine.task_states.items()}

PAPER = len(sys.argv) > 3 and sys.argv[3] == "paper"
POLICY_SET = ("wait", "local", "global") if PAPER else (
    "wait", "reroute", "local", "global", "oracle")

rows = [("Plan (no failure)" if PAPER else "PLAN (no failure)",
         plan_sim, plan_result, [], None)]
for policy in POLICY_SET:
    sim, result, repairs, label = run_policy(policy)
    name = (policy.capitalize() if PAPER else policy.upper()) + (
        f"  [{label}]" if label else "")
    rows.append((name, sim, result, repairs, policy))
    moved = [t for t, ts in ((k.split(":", 1)[1], v)
             for k, v in sim.engine.task_states.items())
             if ts.assigned_node != plan_node[t]]
    print(f"{policy:8s} makespan={result.makespan:.3f} "
          f"(x{result.makespan/m0:.3f} of M0)  moved={sorted(moved) or '-'}  "
          f"repair applied at={[f'{t:.3f}' for t in repairs] or '-'}")

# ---------------------------------------------------------------- gantts
node_ids = sorted(network.nodes)
row_h = 0.92 if PAPER else 1.75
fig, axes = plt.subplots(len(rows), 1,
                         figsize=(7.0 if PAPER else 11, row_h * len(rows)),
                         dpi=200, sharex=True)
xmax = max(r.makespan for _, _, r, _, _ in rows) * 1.05

for ax, (name, sim, result, repairs, policy) in zip(axes, rows):
    for k, ts in sim.engine.task_states.items():
        tid = k.split(":", 1)[1]
        if ts.started_at is None:
            continue
        if PAPER and ts.completed_at - ts.started_at < 0.005 * xmax:
            # Zero-duration wrapper tasks would render as stray ticks now
            # that every bar has a dark edge.
            continue
        y = node_ids.index(ts.assigned_node)
        moved = ts.assigned_node != plan_node[tid]
        if PAPER:
            # Print styling: neutral fills, with the single accent reserved
            # for the semantic distinction. Unmoved tasks are light gray;
            # tasks moved off the planned node are hatched over a pale brick
            # fill. Task ids sit in white circular badges so they stay
            # legible over the hatch.
            ax.barh(y, ts.completed_at - ts.started_at, left=ts.started_at,
                    height=0.9, color="#e5c4ba" if moved else "#e9e9e6",
                    edgecolor="#262626", linewidth=0.7 if moved else 0.4,
                    hatch="///" if moved else None, zorder=3)
        else:
            ax.barh(y, ts.completed_at - ts.started_at, left=ts.started_at,
                    height=0.62, color=TASK_COLOR[tid],
                    edgecolor="#0b0b0b" if moved else "white",
                    linewidth=1.6 if moved else 0.5,
                    hatch="//" if moved else None, zorder=3)
        if not (PAPER and ts.completed_at - ts.started_at < 0.05):
            # A capsule rather than a circle: a circle around a three-char
            # label is wider (hence taller) than the bar, so it cannot stay
            # inside; the pill keeps the white badge within the rectangle.
            badge = dict(boxstyle="round,pad=0.16,rounding_size=0.9",
                         facecolor="white", edgecolor="#262626",
                         linewidth=0.4) if PAPER else None
            ax.annotate(tid,
                        (ts.started_at + (ts.completed_at - ts.started_at) / 2, y),
                        ha="center", va="center", color="#1a1a1a",
                        fontsize=5 if PAPER else 6, zorder=4, bbox=badge)
    if policy is not None:  # every disrupted run shows the failure window
        fail_c = "#b5573f" if PAPER else "#e34948"
        recover_c = "#3f8264" if PAPER else "#1baf7a"
        ax.axvspan(fail_time, fail_time + fail_duration, color=fail_c,
                   alpha=0.08 if PAPER else 0.10, zorder=1)
        ax.axvline(fail_time, color=fail_c,
                   linewidth=0.9 if PAPER else 1.2, linestyle="--", zorder=2)
        ax.axvline(fail_time + fail_duration, color=recover_c,
                   linewidth=0.9 if PAPER else 1.2, linestyle="--", zorder=2)
        if not PAPER:
            ax.annotate(f"{'+'.join(failed_links)} DOWN\nt={fail_time:.2f}",
                        (fail_time, len(node_ids) - 0.45), fontsize=6,
                        color="#e34948", ha="right", va="top", xytext=(-3, 0),
                        textcoords="offset points")
            ax.annotate(f"recovery\nt={fail_time+fail_duration:.2f}",
                        (fail_time + fail_duration, len(node_ids) - 0.45),
                        fontsize=6, color="#1baf7a", ha="left", va="top",
                        xytext=(3, 0), textcoords="offset points")
    for rt in repairs:
        ax.axvline(rt, color="#55507a", linewidth=1.0 if PAPER else 1.4,
                   linestyle=":", zorder=2)
        if not PAPER:
            ax.annotate(f"repair applied\nt={rt:.2f}", (rt, -0.42), fontsize=6,
                        color="#4a3aa7", ha="center", va="bottom")
    ax.set_yticks(range(len(node_ids)))
    ax.set_yticklabels(node_ids, fontsize=7)
    ax.set_ylim(-0.6, len(node_ids) - 0.3)
    ax.set_title(
        f"{name}   makespan={result.makespan:.2f}"
        + (f"  ({result.makespan / m0:.2f}$\\times M_0$)" if PAPER and policy else ""),
        fontsize=8, loc="left")
    ax.tick_params(labelsize=7)
    ax.xaxis.grid(True, color="#dedede", linewidth=0.4)
    ax.set_axisbelow(True)
axes[-1].set_xlabel("time (s)", fontsize=8)
axes[-1].set_xlim(0, xmax)
if not PAPER:
    fig.suptitle("Hatched black-outlined bars = tasks moved off the planned node",
                 fontsize=8, y=0.995)
fig.tight_layout()
fig.savefig(OUT / "3_gantts.png")
if PAPER:
    fig.savefig(OUT / "gantt_example.pdf")
plt.close(fig)
print(f"\nfigures -> {OUT}")

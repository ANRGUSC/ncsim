#!/usr/bin/env python3
"""Visualize routing comparison: widest_path vs shortest_path.

Generates one figure per DAG×network-size combination (9 total). Each figure
has two side-by-side panels (widest vs shortest) showing:
  - Top: Network topology with links colored/thickened by flow count
  - Middle: Gantt-style timeline of tasks and transfers per node
  - Bottom: Link utilization bar chart showing flow concentration

Run after run_routing_comparison.py has populated /tmp/ncsim_routing_comparison/.
"""

import json
import math
import os
import sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
from matplotlib.collections import LineCollection
import numpy as np

OUTDIR = "/tmp/ncsim_routing_comparison"
FIGDIR = os.path.join(OUTDIR, "figures")

NET_SIZES = ["smallnet", "mediumnet", "largenet"]
DAG_SIZES = ["smalldag", "mediumdag", "largedag"]

NET_LABELS = {"smallnet": "2×2 (4 nodes)", "mediumnet": "3×3 (9 nodes)", "largenet": "4×4 (16 nodes)"}
DAG_LABELS = {"smalldag": "Small DAG (5 tasks)", "mediumdag": "Medium DAG (10 tasks)", "largedag": "Large DAG (20 tasks)"}
ROUTE_LABELS = {"widest_path": "Widest Path", "shortest_path": "Shortest Path"}
GRID_SIZES = {"smallnet": 2, "mediumnet": 3, "largenet": 4}
GRID_SPACING = 40

# Colors
TASK_COLOR = "#4A90D9"
XFER_COLOR = "#E8913A"
NODE_COLOR = "#4A90D9"
NODE_EDGE_COLOR = "#2C5F8A"
UNUSED_LINK_COLOR = "#E0E0E0"
CMAP = plt.cm.YlOrRd

# Heterogeneous compute capacities (same as run_routing_comparison.py)
_CAPACITIES = [200, 100, 150, 80, 300, 120, 250, 180, 160, 90, 220, 140, 280, 110, 190, 170]


def generate_network(grid_size):
    """Generate grid_size x grid_size mesh: nodes and undirected link pairs."""
    n = grid_size
    nodes = {}
    for row in range(n):
        for col in range(n):
            idx = row * n + col
            nodes[f"n{idx}"] = (col * GRID_SPACING, row * GRID_SPACING)

    pairs = set()

    def add_pair(r1, c1, r2, c2):
        if 0 <= r2 < n and 0 <= c2 < n:
            a, b = r1 * n + c1, r2 * n + c2
            pairs.add((min(a, b), max(a, b)))

    for row in range(n):
        for col in range(n):
            add_pair(row, col, row, col + 1)
            add_pair(row, col, row + 1, col)
            if (row + col) % 2 == 0:
                add_pair(row, col, row + 1, col + 1)
            else:
                add_pair(row, col, row + 1, col - 1)

    link_pairs = [(f"n{a}", f"n{b}") for a, b in sorted(pairs)]
    return nodes, link_pairs


def parse_trace(label):
    """Parse a trace file into structured task/transfer/link data."""
    tpath = os.path.join(OUTDIR, label, "trace.jsonl")
    events = [json.loads(line) for line in open(tpath)]

    assignments = {}
    task_starts = {}
    task_completes = {}
    xfer_starts = {}
    transfers = []
    makespan = 0.0

    for e in events:
        t = e["type"]
        if t == "task_scheduled":
            assignments[e["task_id"]] = e["node_id"]
        elif t == "task_start":
            task_starts[e["task_id"]] = e
        elif t == "task_complete":
            task_completes[e["task_id"]] = e
        elif t == "transfer_start":
            xfer_starts[(e["from_task"], e["to_task"])] = e
        elif t == "transfer_complete":
            key = (e["from_task"], e["to_task"])
            s = xfer_starts[key]
            route = s.get("route", [s["link_id"]])
            transfers.append({
                "from": e["from_task"], "to": e["to_task"],
                "route": route, "hops": len(route),
                "start": s["sim_time"], "end": e["sim_time"],
                "dur": e["duration"], "link_id": s["link_id"],
            })
        elif t == "sim_end":
            makespan = e["makespan"]

    tasks = []
    for tid in sorted(task_starts.keys(), key=lambda x: task_starts[x]["sim_time"]):
        ts = task_starts[tid]
        tc = task_completes[tid]
        tasks.append({
            "id": tid, "node": ts["node_id"],
            "start": ts["sim_time"], "end": tc["sim_time"],
            "dur": tc["duration"],
        })

    # Directed link usage counts
    link_usage = defaultdict(int)
    for xf in transfers:
        for lid in xf["route"]:
            link_usage[lid] += 1

    # Aggregate to undirected: for (a,b), sum flows on l_a_b and l_b_a
    undirected_usage = defaultdict(int)
    for lid, count in link_usage.items():
        # lid is like "l_n0_n1"
        parts = lid.split("_")  # ['l', 'n0', 'n1']
        a, b = parts[1], parts[2]
        key = tuple(sorted([a, b]))
        undirected_usage[key] += count

    return {
        "assignments": assignments, "tasks": tasks, "transfers": transfers,
        "makespan": makespan, "link_usage": dict(link_usage),
        "undirected_usage": dict(undirected_usage),
    }


def draw_topology(ax, net_size, data, routing, max_flow_global):
    """Draw network topology with links colored by flow count."""
    grid_size = GRID_SIZES[net_size]
    nodes, link_pairs = generate_network(grid_size)
    undirected_usage = data["undirected_usage"]
    assignments = data["assignments"]
    makespan = data["makespan"]

    # Determine which nodes are used (have tasks assigned)
    used_nodes = set(assignments.values())

    # Draw unused links first (gray, thin)
    for a, b in link_pairs:
        key = tuple(sorted([a, b]))
        if key not in undirected_usage:
            x0, y0 = nodes[a]
            x1, y1 = nodes[b]
            ax.plot([x0, x1], [y0, y1], color=UNUSED_LINK_COLOR,
                    linewidth=1.0, zorder=1, solid_capstyle="round")

    # Draw used links (colored, thick)
    if undirected_usage and max_flow_global > 0:
        norm = mcolors.Normalize(vmin=0, vmax=max_flow_global)
        for a, b in link_pairs:
            key = tuple(sorted([a, b]))
            if key in undirected_usage:
                count = undirected_usage[key]
                x0, y0 = nodes[a]
                x1, y1 = nodes[b]
                color = CMAP(norm(count) * 0.8 + 0.15)
                lw = 1.5 + (count / max_flow_global) * 6.0
                ax.plot([x0, x1], [y0, y1], color=color,
                        linewidth=lw, zorder=2, solid_capstyle="round")
                # Flow count label at midpoint
                mx, my = (x0 + x1) / 2, (y0 + y1) / 2
                # Offset diagonals slightly to avoid overlap
                dx, dy = x1 - x0, y1 - y0
                length = math.sqrt(dx * dx + dy * dy)
                if length > 0:
                    ox, oy = -dy / length * 2.5, dx / length * 2.5
                else:
                    ox, oy = 0, 0
                ax.text(mx + ox, my + oy, str(count), ha="center", va="center",
                        fontsize=6, fontweight="bold",
                        color=color, zorder=5,
                        bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                                  edgecolor="none", alpha=0.8))

    # Draw nodes
    for nid, (x, y) in nodes.items():
        if nid in used_nodes:
            ax.plot(x, y, "o", markersize=12, color=NODE_COLOR,
                    markeredgecolor=NODE_EDGE_COLOR, markeredgewidth=1.5, zorder=10)
        else:
            ax.plot(x, y, "o", markersize=8, color="#CCCCCC",
                    markeredgecolor="#999999", markeredgewidth=1.0, zorder=10)
        ax.text(x, y, nid.replace("n", ""), ha="center", va="center",
                fontsize=5.5, fontweight="bold", color="white" if nid in used_nodes else "#666666",
                zorder=11)

    # Stats
    hops = [xf["hops"] for xf in data["transfers"]]
    avg_hops = sum(hops) / len(hops) if hops else 0
    max_hops = max(hops) if hops else 0
    unique_links = len(undirected_usage)

    ax.set_title(f"{ROUTE_LABELS[routing]}  —  {makespan:.1f}s\n"
                 f"avg {avg_hops:.1f} hops, max {max_hops}, {unique_links} links used",
                 fontsize=8, fontweight="bold")
    ax.set_aspect("equal")
    margin = GRID_SPACING * 0.4
    max_coord = (grid_size - 1) * GRID_SPACING
    ax.set_xlim(-margin, max_coord + margin)
    ax.set_ylim(-margin, max_coord + margin)
    ax.invert_yaxis()
    ax.axis("off")


def draw_gantt(ax, data, routing, makespan_both):
    """Draw Gantt chart on given axes."""
    tasks = data["tasks"]
    transfers = data["transfers"]
    makespan = data["makespan"]
    assignments = data["assignments"]

    all_nodes = sorted(set(t["node"] for t in tasks))
    node_y = {n: i for i, n in enumerate(all_nodes)}
    n_nodes = len(all_nodes)

    for t in tasks:
        y = node_y[t["node"]]
        ax.barh(y, t["dur"], left=t["start"], height=0.4,
                color=TASK_COLOR, edgecolor="white", linewidth=0.5, zorder=3)
        bar_frac = t["dur"] / makespan_both if makespan_both > 0 else 0
        if bar_frac > 0.04:
            ax.text(t["start"] + t["dur"] / 2, y, t["id"],
                    ha="center", va="center", fontsize=5.5,
                    color="white", fontweight="bold", zorder=4)

    for xf in transfers:
        src_node = assignments[xf["from"]]
        dst_node = assignments[xf["to"]]
        if src_node in node_y and dst_node in node_y:
            y_src = node_y[src_node]
            y_dst = node_y[dst_node]
            ax.barh(y_src, xf["dur"], left=xf["start"], height=0.2,
                    color=XFER_COLOR, alpha=0.7, edgecolor="none",
                    zorder=2, align="edge")
            if y_src != y_dst:
                ax.annotate("", xy=(xf["end"], y_dst + 0.1),
                            xytext=(xf["end"], y_src + 0.2),
                            arrowprops=dict(arrowstyle="->", color=XFER_COLOR,
                                            lw=0.8, alpha=0.6),
                            zorder=2)

    ax.set_yticks(range(n_nodes))
    ax.set_yticklabels(all_nodes, fontsize=7)
    ax.set_xlim(0, makespan_both * 1.02)
    ax.set_ylim(-0.5, n_nodes - 0.5)
    ax.invert_yaxis()
    ax.set_xlabel("Time (s)", fontsize=7)
    ax.tick_params(axis="x", labelsize=6)
    ax.grid(axis="x", alpha=0.3, linewidth=0.5)


def draw_link_bars(ax, data, max_flow_global):
    """Draw link usage bar chart on given axes."""
    link_usage = data["link_usage"]
    if not link_usage:
        ax.text(0.5, 0.5, "No transfers", ha="center", va="center",
                transform=ax.transAxes, fontsize=8)
        return

    sorted_links = sorted(link_usage.items(), key=lambda x: -x[1])
    if len(sorted_links) > 15:
        sorted_links = sorted_links[:15]

    link_names = [l[0].replace("l_", "") for l in sorted_links]
    counts = [l[1] for l in sorted_links]

    norm = mcolors.Normalize(vmin=0, vmax=max(max_flow_global, 1))
    colors = [CMAP(norm(c) * 0.8 + 0.15) for c in counts]
    ax.barh(range(len(link_names)), counts, color=colors,
            edgecolor="white", linewidth=0.3)
    ax.set_yticks(range(len(link_names)))
    ax.set_yticklabels(link_names, fontsize=5.5)
    ax.invert_yaxis()
    ax.set_xlabel("# flows using link", fontsize=7)
    ax.tick_params(axis="x", labelsize=6)
    ax.set_xlim(0, max_flow_global * 1.1 if max_flow_global else 1)


def generate_figure(net_size, dag_size):
    """Generate one comparison figure for a (network, DAG) combination."""
    label_w = f"{net_size}_{dag_size}_widest_path"
    label_s = f"{net_size}_{dag_size}_shortest_path"

    data_w = parse_trace(label_w)
    data_s = parse_trace(label_s)

    makespan_both = max(data_w["makespan"], data_s["makespan"])

    # Global max flow count for consistent color scaling across both panels
    all_directed = list(data_w["link_usage"].values()) + list(data_s["link_usage"].values())
    max_flow_directed = max(all_directed) if all_directed else 1
    all_undirected = list(data_w["undirected_usage"].values()) + list(data_s["undirected_usage"].values())
    max_flow_undirected = max(all_undirected) if all_undirected else 1

    fig = plt.figure(figsize=(16, 11))
    gs = fig.add_gridspec(3, 2, height_ratios=[1.2, 1.5, 0.8],
                          hspace=0.30, wspace=0.25,
                          left=0.06, right=0.97, top=0.92, bottom=0.05)

    ax_topo_w = fig.add_subplot(gs[0, 0])
    ax_topo_s = fig.add_subplot(gs[0, 1])
    ax_gantt_w = fig.add_subplot(gs[1, 0])
    ax_gantt_s = fig.add_subplot(gs[1, 1])
    ax_bars_w = fig.add_subplot(gs[2, 0])
    ax_bars_s = fig.add_subplot(gs[2, 1])

    fig.suptitle(f"{NET_LABELS[net_size]}  ×  {DAG_LABELS[dag_size]}",
                 fontsize=14, fontweight="bold")

    draw_topology(ax_topo_w, net_size, data_w, "widest_path", max_flow_undirected)
    draw_topology(ax_topo_s, net_size, data_s, "shortest_path", max_flow_undirected)
    draw_gantt(ax_gantt_w, data_w, "widest_path", makespan_both)
    draw_gantt(ax_gantt_s, data_s, "shortest_path", makespan_both)
    draw_link_bars(ax_bars_w, data_w, max_flow_directed)
    draw_link_bars(ax_bars_s, data_s, max_flow_directed)

    # Legend
    task_patch = mpatches.Patch(color=TASK_COLOR, label="Task execution")
    xfer_patch = mpatches.Patch(color=XFER_COLOR, alpha=0.7, label="Data transfer")
    used_node = plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=NODE_COLOR,
                           markeredgecolor=NODE_EDGE_COLOR, markersize=8, label="Used node")
    unused_node = plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="#CCCCCC",
                              markeredgecolor="#999999", markersize=6, label="Unused node")
    fig.legend(handles=[task_patch, xfer_patch, used_node, unused_node],
               loc="lower center", ncol=4, fontsize=8, frameon=False)

    # Colorbar for link usage
    sm = plt.cm.ScalarMappable(cmap=CMAP,
                                norm=mcolors.Normalize(vmin=0, vmax=max_flow_undirected))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=[ax_topo_w, ax_topo_s], location="bottom",
                         fraction=0.04, pad=0.08, shrink=0.4, aspect=30)
    cbar.set_label("Flows per link (bidirectional)", fontsize=7)
    cbar.ax.tick_params(labelsize=6)

    fname = f"{net_size}_{dag_size}.png"
    fpath = os.path.join(FIGDIR, fname)
    fig.savefig(fpath, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return fpath


def main():
    os.makedirs(FIGDIR, exist_ok=True)

    print()
    print("=" * 70)
    print("  Generating routing comparison visualizations")
    print("=" * 70)
    print()

    for net_size in NET_SIZES:
        for dag_size in DAG_SIZES:
            label = f"{net_size} × {dag_size}"
            print(f"  {label}...", end=" ", flush=True)
            fpath = generate_figure(net_size, dag_size)
            print(f"-> {fpath}")

    print()
    print(f"  All figures saved to: {FIGDIR}")
    print()


if __name__ == "__main__":
    main()

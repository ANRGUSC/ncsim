"""Shared, deterministic infrastructure for the revision-1 experiments.

This module deliberately keeps topology, workload, placement, and simulator
randomness in separate namespaces.  Random geometric graphs are accepted only
when the radius-limited graph is connected; no synthetic bridge links are added.
"""
from __future__ import annotations

import json
import math
import os
import random
import re
import subprocess
import sys
import threading
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

NCSIM_COMMIT = "18b88aa227c354ee7f60551ed97d61ffc031fa5e"
NCSIM_SOURCE = os.environ.get("NCSIM_SOURCE")
if NCSIM_SOURCE:
    sys.path.insert(0, str(Path(NCSIM_SOURCE).expanduser().resolve()))

from saga import Network as SagaNetwork, NetworkEdge, NetworkNode, Schedule, ScheduledTask
from saga.schedulers.cpop import upward_rank
from saga.schedulers.heft import HeftScheduler, heft_rank_sort

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from run_saga_direct_eval import (  # noqa: E402
    _build_ncsim_network_direct,
    _build_sc_direct,
    _build_taskgraph,
    _saga_nets,
)

PAPER_ROOT = SCRIPTS_DIR.parent
DATA_DIR = PAPER_ROOT / "dataset"
RUN_ROOT = PAPER_ROOT / "tmp" / "rev1_runs"

_WIFI_CACHE_LOCK = threading.Lock()
_WIFI_CONFLICT_CACHE = {}


def _install_wifi_cache():
    """Cache immutable RF conflict graphs by exact topology within this process.

    ncsim rebuilds this O(|L|^2) object on each CLI invocation.  Revision runs
    deliberately reuse a topology across matched scheduler/routing conditions,
    so rebuilding it changes nothing and can dominate total run time.
    """
    import ncsim.models.wifi as wifi
    if getattr(wifi.build_conflict_graph, "_rev1_cached", False):
        return
    original = wifi.build_conflict_graph

    def cached(network, rf, shadow_fading=None):
        nodes = tuple(sorted((node_id, float(n.position.x), float(n.position.y))
                             for node_id, n in network.nodes.items()))
        links = tuple(sorted((link_id, str(link.from_node), str(link.to_node))
                             for link_id, link in network.links.items()))
        rf_key = (rf.tx_power_dBm, rf.freq_ghz, rf.path_loss_exponent,
                  rf.noise_floor_dBm, rf.cca_threshold_dBm, rf.rts_cts)
        shadow_key = tuple(sorted((str(k), float(v)) for k, v in (shadow_fading or {}).items()))
        key = (nodes, links, rf_key, shadow_key)
        with _WIFI_CACHE_LOCK:
            if key not in _WIFI_CONFLICT_CACHE:
                _WIFI_CONFLICT_CACHE[key] = original(network, rf, shadow_fading)
            return _WIFI_CONFLICT_CACHE[key]

    cached._rev1_cached = True
    wifi.build_conflict_graph = cached

NUM_NODES = 50
COMM_RANGE = 80.0
DENSITIES = (150, 200, 250, 300, 350, 400, 500)
CAPACITIES = (200, 100, 150, 80, 300, 120, 250, 180, 160, 90,
              220, 140, 280, 110, 190, 170)
STAGES = {
    8: (1, 6, 1),
    16: (1, 6, 8, 1),
    24: (1, 6, 8, 8, 1),
    30: (1, 6, 8, 8, 6, 1),
    32: (1, 6, 8, 8, 8, 1),
    45: (1, 8, 12, 12, 11, 1),
    60: (1, 10, 14, 14, 10, 10, 1),
}
ROUTES = (
    ("W", "widest_path", None),
    ("S", "shortest_path", None),
    ("SH", "shortest_hop", None),
    ("GS", "interference_aware", "start"),
    ("GC", "interference_aware", "criticality"),
    ("GB", "interference_aware", "bytes"),
    ("GO", "interference_aware", "overlap"),
    ("GSD", "interference_aware_dynamic", None),
    ("GSD-D", "interference_aware_dynamic_deferral", None),
)


def natural_key(value: str):
    return tuple(int(x) if x.isdigit() else x.lower()
                 for x in re.split(r"(\d+)", value))


def _connected(n: int, pairs: set[tuple[int, int]]) -> bool:
    adj = {i: set() for i in range(n)}
    for a, b in pairs:
        adj[a].add(b)
        adj[b].add(a)
    seen, stack = set(), [0]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(adj[cur] - seen)
    return len(seen) == n


def random_topology(side: int, ordinal: int) -> dict:
    """Return the ordinal-th connected, radius-limited RGG for a density."""
    accepted = 0
    rejected = []
    candidate = 1
    while True:
        seed = side * 100000 + candidate
        rng = random.Random(seed)
        pos = [(rng.uniform(0, side), rng.uniform(0, side))
               for _ in range(NUM_NODES)]
        pairs = set()
        for i in range(NUM_NODES):
            for j in range(i + 1, NUM_NODES):
                if math.dist(pos[i], pos[j]) <= COMM_RANGE:
                    pairs.add((i, j))
        if _connected(NUM_NODES, pairs):
            accepted += 1
            if accepted == ordinal:
                break
        else:
            rejected.append(seed)
        candidate += 1
        if candidate > 100000:
            raise RuntimeError(f"Could not find {ordinal} connected L={side} topologies")

    nodes = [{"id": f"n{i}",
              "compute_capacity": CAPACITIES[i % len(CAPACITIES)],
              "x": round(pos[i][0], 3), "y": round(pos[i][1], 3)}
             for i in range(NUM_NODES)]
    links = []
    for a, b in sorted(pairs):
        links.extend([
            {"id": f"l_n{a}_n{b}", "from": f"n{a}", "to": f"n{b}"},
            {"id": f"l_n{b}_n{a}", "from": f"n{b}", "to": f"n{a}"},
        ])
    degrees = [0] * NUM_NODES
    for a, b in pairs:
        degrees[a] += 1
        degrees[b] += 1
    return {
        "kind": "rgg", "label": f"L{side}", "side": side,
        "ordinal": ordinal, "topology_seed": seed,
        "rejected_seeds": rejected, "nodes": nodes, "links": links,
        "n_undirected_links": len(pairs),
        "degree_mean": sum(degrees) / len(degrees),
        "degree_median": sorted(degrees)[len(degrees) // 2],
        "degree_min": min(degrees), "degree_max": max(degrees),
    }


def grid_topology(size: int) -> dict:
    nodes = []
    for row in range(size):
        for col in range(size):
            idx = row * size + col
            nodes.append({"id": f"n{idx}",
                          "compute_capacity": CAPACITIES[idx % len(CAPACITIES)],
                          "x": col * 40.0, "y": row * 40.0})
    pairs = set()
    for row in range(size):
        for col in range(size):
            here = row * size + col
            for rr, cc in ((row, col + 1), (row + 1, col)):
                if rr < size and cc < size:
                    there = rr * size + cc
                    pairs.add((min(here, there), max(here, there)))
            rr, cc = (row + 1, col + 1) if (row + col) % 2 == 0 else (row + 1, col - 1)
            if rr < size and 0 <= cc < size:
                there = rr * size + cc
                pairs.add((min(here, there), max(here, there)))
    links = []
    for a, b in sorted(pairs):
        links.extend([
            {"id": f"l_n{a}_n{b}", "from": f"n{a}", "to": f"n{b}"},
            {"id": f"l_n{b}_n{a}", "from": f"n{b}", "to": f"n{a}"},
        ])
    return {"kind": "grid", "label": f"{size}x{size}", "size": size,
            "topology_seed": 0, "rejected_seeds": [], "nodes": nodes,
            "links": links, "n_undirected_links": len(pairs)}


def workload(n_tasks: int, workload_seed: int) -> tuple[list, list]:
    widths = STAGES[n_tasks]
    if sum(widths) != n_tasks:
        raise ValueError((n_tasks, widths))
    rng = random.Random(10_000_000 + n_tasks * 1000 + workload_seed)
    tasks = [{"id": f"T{i}", "compute_cost": rng.randint(150, 1000)}
             for i in range(n_tasks)]
    layers, offset = [], 0
    for width in widths:
        layers.append(list(range(offset, offset + width)))
        offset += width
    edges = []
    for li in range(len(layers) - 1):
        srcs, dsts = layers[li], layers[li + 1]
        if len(srcs) == 1:
            pairs = [(srcs[0], d) for d in dsts]
        elif len(dsts) == 1:
            pairs = [(s, dsts[0]) for s in srcs]
        else:
            fanout = 2 if max(len(srcs), len(dsts)) <= 12 else 3
            pairs = []
            for i, src in enumerate(srcs):
                for j in range(fanout):
                    pairs.append((src, dsts[(i * fanout + j) % len(dsts)]))
            covered = {d for _, d in pairs}
            for j, dst in enumerate(dsts):
                if dst not in covered:
                    pairs.append((srcs[j % len(srcs)], dst))
        for src, dst in pairs:
            edges.append({"from": f"T{src}", "to": f"T{dst}",
                          "data_size": float(rng.randint(2, 30))})
    return tasks, edges


def adjacency(topology: dict) -> dict[str, set[str]]:
    out = {n["id"]: set() for n in topology["nodes"]}
    for edge in topology["links"]:
        out[edge["from"]].add(edge["to"])
    return out


class LCHeftScheduler:
    """Dominant-parent one-hop constrained HEFT using widest-path costs."""

    def __init__(self, node_name_to_id: dict[str, str], physical_adjacency: dict[str, set[str]]):
        self.node_name_to_id = node_name_to_id
        self.node_id_to_name = {v: k for k, v in node_name_to_id.items()}
        self.physical_adjacency = physical_adjacency
        self.anchors: dict[str, str] = {}

    def schedule(self, network, task_graph):
        order = heft_rank_sort(network, task_graph)
        ranks = upward_rank(network, task_graph)
        schedule = Schedule(task_graph, network)
        assigned: dict[str, str] = {}
        nodes = sorted(network.nodes, key=lambda n: natural_key(n.name))
        for task_name in order:
            incoming = list(task_graph.in_edges(task_name))
            if not incoming:
                candidates = nodes
            else:
                incoming.sort(key=lambda e: (-float(e.size), -float(ranks[e.source]), natural_key(e.source)))
                anchor = incoming[0].source
                self.anchors[task_name] = anchor
                anchor_id = self.node_name_to_id[assigned[anchor]]
                allowed_ids = {anchor_id} | set(self.physical_adjacency[anchor_id])
                allowed_names = {self.node_id_to_name[x] for x in allowed_ids}
                candidates = [n for n in nodes if n.name in allowed_names]
            best = None
            for node in candidates:
                start = schedule.get_earliest_start_time(task=task_name, node=node, append_only=False)
                runtime = task_graph.get_task(task_name).cost / network.get_node(node).speed
                candidate = (start + runtime, natural_key(node.name), start, node)
                if best is None or candidate[:2] < best[:2]:
                    best = candidate
            finish, _, start, node = best
            schedule.add_task(ScheduledTask(node=node.name, name=task_name, start=start, end=finish))
            assigned[task_name] = node.name
        return schedule


def _schedule_assignments(schedule, node_name_to_id: dict[str, str]) -> dict[str, str]:
    assignments = {}
    for node_name, scheduled in schedule.mapping.items():
        node_id = node_name_to_id[str(node_name)]
        for task in scheduled:
            assignments[task.name] = node_id
    return assignments


def schedule_placements(topology: dict, tasks: list, edges: list, phy_seed: int) -> dict:
    sc = _build_sc_direct(topology["nodes"], topology["links"], tasks, edges)
    net = _build_ncsim_network_direct(topology["nodes"], topology["links"], phy_seed)
    sn2, sn1, node_name_to_id, _ = _saga_nets(net)
    tg = _build_taskgraph(sc)
    heft = HeftScheduler()
    schedules = {
        "heft1": heft.schedule(sn1, tg),
        "heft2": heft.schedule(sn2, tg),
    }
    lc = LCHeftScheduler(node_name_to_id, adjacency(topology))
    schedules["lc_heft"] = lc.schedule(sn2, tg)
    result = {
        label: {
            "assignments": _schedule_assignments(schedule, node_name_to_id),
            "predicted_makespan": float(schedule.makespan),
            "diagnostics": placement_diagnostics(topology, tasks, edges, schedule,
                                                   node_name_to_id,
                                                   sn1 if label == "heft1" else sn2),
        }
        for label, schedule in schedules.items()
    }
    result["lc_heft"]["anchors"] = dict(lc.anchors)
    return result


def schedule_heft1_assignments(topology: dict, tasks: list, edges: list, phy_seed: int,
                               penalty: float = 0.001):
    """Fast path for routing sweeps that need only a pinned HEFT-1 placement."""
    sc = _build_sc_direct(topology["nodes"], topology["links"], tasks, edges)
    net = _build_ncsim_network_direct(topology["nodes"], topology["links"], phy_seed)
    node_ids = list(net.nodes)
    index = {node_id: i for i, node_id in enumerate(node_ids)}
    node_name_to_id = {f"node_{i}": node_id for node_id, i in index.items()}
    direct = {(link.from_node, link.to_node): link.bandwidth for link in net.links.values()}
    saga_nodes = frozenset(NetworkNode(name=f"node_{index[node_id]}",
                                       speed=net.nodes[node_id].compute_capacity)
                           for node_id in node_ids)
    saga_edges = frozenset(NetworkEdge(
        source=f"node_{index[src]}", target=f"node_{index[dst]}",
        speed=10000.0 if src == dst else direct.get((src, dst), penalty))
        for src in node_ids for dst in node_ids)
    sn1 = SagaNetwork(nodes=saga_nodes, edges=saga_edges)
    schedule = HeftScheduler().schedule(sn1, _build_taskgraph(sc))
    return _schedule_assignments(schedule, node_name_to_id)


def placement_diagnostics(topology, tasks, edges, schedule, node_name_to_id, saga_net):
    assignments = _schedule_assignments(schedule, node_name_to_id)
    adj = adjacency(topology)
    speed = {(e.source, e.target): float(e.speed) for e in saga_net.edges}
    id_to_name = {v: k for k, v in node_name_to_id.items()}
    counts = {"colocated": 0, "one_hop": 0, "multi_hop": 0}
    volumes = {k: 0.0 for k in counts}
    comm = {k: 0.0 for k in counts}
    max_edge = None
    edge_records = []
    for e in edges:
        src, dst = assignments[e["from"]], assignments[e["to"]]
        if src == dst:
            cls, hops = "colocated", 0
        elif dst in adj[src]:
            cls, hops = "one_hop", 1
        else:
            cls, hops = "multi_hop", shortest_hops(adj, src, dst)
        rate = speed[(id_to_name[src], id_to_name[dst])]
        cost = float(e["data_size"]) / rate
        counts[cls] += 1
        volumes[cls] += float(e["data_size"])
        comm[cls] += cost
        rec = {"from": e["from"], "to": e["to"], "src_node": src,
               "dst_node": dst, "class": cls, "hops": hops,
               "data_mb": float(e["data_size"]), "rate_mbps": rate,
               "estimated_seconds": cost}
        edge_records.append(rec)
        if max_edge is None or cost > max_edge["estimated_seconds"]:
            max_edge = rec
    timing = {}
    processor = {}
    for node_name, scheduled in schedule.mapping.items():
        node_id = node_name_to_id[str(node_name)]
        busy = sum(float(t.end - t.start) for t in scheduled)
        latest = max((float(t.end) for t in scheduled), default=0.0)
        processor[node_id] = {"busy_seconds": busy, "idle_to_last_finish": latest - busy,
                              "last_finish": latest, "task_count": len(scheduled)}
        for t in scheduled:
            timing[t.name] = {"node": node_id, "start": float(t.start), "end": float(t.end)}
    # Reconstruct the binding predecessor/processor chain behind the final
    # finish time.  This is diagnostic (ties can yield another valid chain),
    # but unlike an upward-rank value it is anchored in the produced schedule.
    incoming = defaultdict(list)
    for e in edges:
        incoming[e["to"]].append(e)
    chain = []
    current = max(timing, key=lambda x: timing[x]["end"], default=None)
    seen = set()
    while current is not None and current not in seen:
        seen.add(current)
        info = timing[current]
        causes = []
        for pred_edge in incoming[current]:
            pred = pred_edge["from"]
            src_name = id_to_name[assignments[pred]]
            dst_name = id_to_name[assignments[current]]
            ready = timing[pred]["end"] + float(pred_edge["data_size"]) / speed[(src_name, dst_name)]
            causes.append((ready, pred, "dependency"))
        same_node_prior = [(v["end"], task, "processor") for task, v in timing.items()
                           if task != current and v["node"] == info["node"]
                           and v["end"] <= info["start"] + 1e-9]
        causes.extend(same_node_prior)
        cause = max(causes, default=None)
        chain.append({"task": current, "node": info["node"],
                      "start": info["start"], "end": info["end"],
                      "binding_cause": cause[2] if cause else "entry",
                      "predecessor": cause[1] if cause else None})
        current = cause[1] if cause else None
    chain.reverse()
    return {"edge_count": len(edges), "counts": counts, "data_mb": volumes,
            "estimated_comm_seconds": comm, "maximum_edge": max_edge,
            "edges": edge_records, "processors": processor, "task_timing": timing,
            "critical_chain": chain,
            "max_task_finish": max((v["end"] for v in timing.values()), default=0.0)}


def shortest_hops(adj: dict[str, set[str]], src: str, dst: str) -> int | None:
    seen, queue = {src}, [(src, 0)]
    while queue:
        cur, dist = queue.pop(0)
        if cur == dst:
            return dist
        for nxt in sorted(adj[cur], key=natural_key):
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, dist + 1))
    return None


def make_yaml(name, topology, tasks, edges, interference="csma_bianchi", pinned=None):
    pinned = pinned or {}
    lines = ["scenario:", f"  name: {name}", "  network:", "    nodes:"]
    for n in topology["nodes"]:
        lines.append(f"      - {{id: {n['id']}, compute_capacity: {n['compute_capacity']}, position: {{x: {n['x']}, y: {n['y']}}}}}")
    lines.append("    links:")
    for link in topology["links"]:
        lines.append(f"      - {{id: {link['id']}, from: {link['from']}, to: {link['to']}}}")
    lines.extend(["  dags:", "    - id: dag_1", "      inject_at: 0.0", "      tasks:"])
    for task in tasks:
        pin = f", pinned_to: {pinned[task['id']]}" if task["id"] in pinned else ""
        lines.append(f"        - {{id: {task['id']}, compute_cost: {task['compute_cost']}{pin}}}")
    lines.append("      edges:")
    for e in edges:
        lines.append(f"        - {{from: {e['from']}, to: {e['to']}, data_size: {e['data_size']}}}")
    lines.extend(["  config:", "    scheduler: heft1", "    seed: 1",
                  "    routing: shortest_hop", f"    interference: {interference}"])
    return "\n".join(lines) + "\n"


def run_ncsim(run_id, topology, tasks, edges, scheduler, routing, sim_seed,
              interference="csma_bianchi", greedy_order=None,
              data_size_scale=1.0, placement=None):
    run_dir = RUN_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    # ncsim preserves its input scenario as ``output/scenario.yaml``.  Keep the
    # source outside the output directory so Windows does not try to copy a file
    # onto itself (which raises WinError 32).
    input_dir = RUN_ROOT / "_inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = input_dir / f"{run_id}.yaml"
    yaml_path.write_text(make_yaml(run_id, topology, tasks, edges, interference,
                                   pinned=placement),
                         encoding="utf-8")
    actual_scheduler = "manual" if placement is not None else scheduler
    cmd = [sys.executable, "-m", "ncsim", "--scenario", str(yaml_path),
           "--output", str(run_dir), "--scheduler", actual_scheduler,
           "--routing", routing, "--interference", interference,
           "--seed", str(sim_seed)]
    if greedy_order:
        cmd += ["--greedy-order", greedy_order]
    if data_size_scale != 1.0:
        cmd += ["--data-size-scale", str(data_size_scale)]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(NCSIM_SOURCE) + os.pathsep + env.get("PYTHONPATH", "")
    metrics_path = run_dir / "metrics.json"
    if metrics_path.exists():
        metrics_path.unlink()
    # Run through ncsim's public CLI entry point in-process so identical
    # topology conflict graphs can be reused across matched conditions.
    try:
        _install_wifi_cache()
        import logging
        from ncsim.main import main as ncsim_main
        logging.disable(logging.CRITICAL)
        returncode = ncsim_main(cmd[3:])
    except (Exception, SystemExit) as exc:  # preserve invalid-CLI runs for retry
        return {"status": "error", "returncode": 1, "error": repr(exc)}
    if returncode or not metrics_path.exists():
        return {"status": "error", "returncode": returncode,
                "error": "ncsim did not produce metrics.json"}
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metric_status = metrics.get("status", "completed")
    return {"status": "ok" if metric_status in ("ok", "completed") else metric_status,
            "makespan": metrics.get("makespan"), "run_dir": str(run_dir)}


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

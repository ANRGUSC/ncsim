#!/usr/bin/env python3
"""Run interference impact experiments: none vs csma_bianchi across 9 grid scenarios.

Uses shortest_path routing (generally best) for all runs.
Computes WiFi PHY rates and includes them as explicit bandwidths so that
"none" and "csma_bianchi" share the same base link rates.
"""

import json
import math
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ncsim.models.wifi import (
    RFConfig, received_power_dBm, snr_dB, snr_to_rate_mbps,
    rate_mbps_to_MBps, path_loss_dB,
)

OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_interference_results")

COMPUTE_COST = 500
DATA_SIZE = 10.0
_CAPACITIES = [200, 100, 150, 80, 300, 120, 250, 180, 160, 90, 220, 140, 280, 110, 190, 170]
GRID_SPACING = 40
RF = RFConfig()  # defaults: 20dBm, 5GHz, n=3.0, ax


def euclidean_distance(x1, y1, x2, y2):
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def compute_wifi_rate(dist):
    """Compute WiFi PHY rate in MB/s for a given distance."""
    rx_power = received_power_dBm(RF.tx_power_dBm, dist, RF, 0.0)
    link_snr = snr_dB(rx_power, RF.noise_floor_dBm)
    rate_mbps = snr_to_rate_mbps(link_snr, RF.wifi_standard, RF.channel_width_mhz)
    return rate_mbps_to_MBps(rate_mbps)


def generate_network(grid_size):
    n = grid_size
    nodes = []
    for row in range(n):
        for col in range(n):
            idx = row * n + col
            nodes.append({
                "id": f"n{idx}",
                "compute_capacity": _CAPACITIES[idx % len(_CAPACITIES)],
                "x": col * GRID_SPACING,
                "y": row * GRID_SPACING,
            })
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

    links = []
    for a, b in sorted(pairs):
        na, nb = f"n{a}", f"n{b}"
        # Compute WiFi rate for this link
        na_node = nodes[a]
        nb_node = nodes[b]
        dist = euclidean_distance(na_node["x"], na_node["y"], nb_node["x"], nb_node["y"])
        rate = compute_wifi_rate(dist)
        links.append({"id": f"l_{na}_{nb}", "from": na, "to": nb, "bandwidth": rate, "dist": dist})
        links.append({"id": f"l_{nb}_{na}", "from": nb, "to": na, "bandwidth": rate, "dist": dist})

    return nodes, links


def _make_dag_small():
    tasks = [{"id": f"T{i}", "compute_cost": COMPUTE_COST} for i in range(5)]
    edges = [
        {"from": "T0", "to": "T1", "data_size": DATA_SIZE},
        {"from": "T0", "to": "T2", "data_size": DATA_SIZE},
        {"from": "T0", "to": "T3", "data_size": DATA_SIZE},
        {"from": "T1", "to": "T4", "data_size": DATA_SIZE},
        {"from": "T2", "to": "T4", "data_size": DATA_SIZE},
        {"from": "T3", "to": "T4", "data_size": DATA_SIZE},
    ]
    return tasks, edges

def _make_dag_medium():
    tasks = [{"id": f"T{i}", "compute_cost": COMPUTE_COST} for i in range(10)]
    edges = []
    for i in range(1, 5):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": DATA_SIZE})
    for i in range(1, 5):
        for j in range(5, 9):
            if (i + j) % 2 == 0:
                edges.append({"from": f"T{i}", "to": f"T{j}", "data_size": DATA_SIZE})
    for i in range(5, 9):
        edges.append({"from": f"T{i}", "to": "T9", "data_size": DATA_SIZE})
    return tasks, edges

def _make_dag_large():
    tasks = [{"id": f"T{i}", "compute_cost": COMPUTE_COST} for i in range(20)]
    edges = []
    for i in range(1, 5):
        edges.append({"from": "T0", "to": f"T{i}", "data_size": DATA_SIZE})
    stage1_to_2 = {1: [5, 6], 2: [6, 7], 3: [8, 9], 4: [9, 10]}
    for src, dsts in stage1_to_2.items():
        for dst in dsts:
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": DATA_SIZE})
    stage2_to_3 = {5: [11, 12], 6: [12, 13], 7: [13, 14], 8: [14, 15], 9: [15, 16], 10: [16, 11]}
    for src, dsts in stage2_to_3.items():
        for dst in dsts:
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": DATA_SIZE})
    stage3_to_4 = {11: [17], 12: [17], 13: [18], 14: [18], 15: [19], 16: [19]}
    for src, dsts in stage3_to_4.items():
        for dst in dsts:
            edges.append({"from": f"T{src}", "to": f"T{dst}", "data_size": DATA_SIZE})
    return tasks, edges


NETWORK_SIZES = {"small": (2, "2x2"), "medium": (3, "3x3"), "large": (4, "4x4")}
DAG_GENERATORS = {"small": _make_dag_small, "medium": _make_dag_medium, "large": _make_dag_large}


def generate_scenario_yaml(net_size_label, dag_size):
    grid_size, _ = NETWORK_SIZES[net_size_label]
    nodes, links = generate_network(grid_size)
    tasks, edges = DAG_GENERATORS[dag_size]()

    yaml = "scenario:\n"
    yaml += f'  name: "intf_{net_size_label}net_{dag_size}dag"\n'
    yaml += "  network:\n    nodes:\n"
    for n in nodes:
        yaml += (f"      - {{id: {n['id']}, compute_capacity: {n['compute_capacity']}, "
                 f"position: {{x: {n['x']}, y: {n['y']}}}}}\n")
    yaml += "    links:\n"
    for link in links:
        yaml += (f"      - {{id: {link['id']}, from: {link['from']}, to: {link['to']}, "
                 f"bandwidth: {link['bandwidth']:.4f}}}\n")
    yaml += "  dags:\n    - id: dag_1\n      inject_at: 0.0\n      tasks:\n"
    for t in tasks:
        yaml += f"        - {{id: {t['id']}, compute_cost: {t['compute_cost']}}}\n"
    yaml += "      edges:\n"
    for e in edges:
        yaml += f"        - {{from: {e['from']}, to: {e['to']}, data_size: {e['data_size']}}}\n"
    yaml += "  config:\n    scheduler: heft\n    seed: 42\n    routing: shortest_path\n    interference: none\n"
    return yaml


def run_scenario(yaml_str, run_label, interference):
    outdir = os.path.join(OUTDIR, run_label)
    os.makedirs(outdir, exist_ok=True)
    input_dir = os.path.join(OUTDIR, "_inputs", run_label)
    os.makedirs(input_dir, exist_ok=True)
    yaml_path = os.path.join(input_dir, "scenario.yaml")
    with open(yaml_path, "w") as f:
        f.write(yaml_str)
    cmd = [
        sys.executable, "-m", "ncsim",
        "--scenario", yaml_path,
        "--output", outdir,
        "--interference", interference,
        "--scheduler", "heft",
        "--routing", "shortest_path",
        "--seed", "42",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr[-300:]}", file=sys.stderr)
        return None
    return outdir


def get_makespan(outdir):
    path = os.path.join(outdir, "metrics.json")
    try:
        with open(path) as f:
            data = json.load(f)
        if data.get("status") == "error":
            return None
        return data["makespan"]
    except Exception:
        return None


def main():
    os.makedirs(OUTDIR, exist_ok=True)

    # Print WiFi rate info
    dist_40 = compute_wifi_rate(40)
    dist_diag = compute_wifi_rate(40 * math.sqrt(2))
    print(f"WiFi rates: 40m={dist_40:.3f} MB/s, 56.6m(diag)={dist_diag:.3f} MB/s")

    net_sizes = ["small", "medium", "large"]
    dag_sizes = ["small", "medium", "large"]
    interferences = ["none", "csma_bianchi"]

    results = {}
    total = len(net_sizes) * len(dag_sizes) * len(interferences)
    count = 0

    for net_size in net_sizes:
        for dag_size in dag_sizes:
            yaml_str = generate_scenario_yaml(net_size, dag_size)
            for intf in interferences:
                count += 1
                label = f"{net_size}net_{dag_size}dag_{intf}"
                print(f"  [{count:>2d}/{total}] {label}...", end=" ", flush=True)
                outdir = run_scenario(yaml_str, label, intf)
                if outdir is None:
                    results[(net_size, dag_size, intf)] = None
                    print("FAILED")
                else:
                    ms = get_makespan(outdir)
                    results[(net_size, dag_size, intf)] = ms
                    if ms is not None:
                        print(f"{ms:.4f}s")
                    else:
                        print("ERROR")

    print()

    # Print results table
    for net_size in net_sizes:
        grid_size, net_desc = NETWORK_SIZES[net_size]
        n_nodes = grid_size * grid_size
        _, links = generate_network(grid_size)
        n_links = len(links)
        for dag_size in dag_sizes:
            n_tasks = {"small": 5, "medium": 10, "large": 20}[dag_size]
            none_ms = results.get((net_size, dag_size, "none"))
            bian_ms = results.get((net_size, dag_size, "csma_bianchi"))
            none_str = f"{none_ms:.2f}" if none_ms else "ERR"
            bian_str = f"{bian_ms:.2f}" if bian_ms else "ERR"
            if none_ms and bian_ms:
                slowdown = ((bian_ms - none_ms) / none_ms) * 100
                slow_str = f"+{slowdown:.1f}%" if slowdown >= 0 else f"{slowdown:.1f}%"
            else:
                slow_str = "n/a"
            print(f"  {net_desc} ({n_nodes}n,{n_links}l) | {n_tasks:>2d} tasks | none={none_str:>8s} | bianchi={bian_str:>8s} | {slow_str}")

    # Save as JSON
    json_results = {}
    for (ns, ds, intf), ms in results.items():
        json_results[f"{ns}_{ds}_{intf}"] = ms
    results_path = os.path.join(OUTDIR, "results.json")
    with open(results_path, "w") as f:
        json.dump(json_results, f, indent=2)
    print(f"\nResults saved to {results_path}")


if __name__ == "__main__":
    main()

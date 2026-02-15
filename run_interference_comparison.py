#!/usr/bin/env python3
"""Run routing x interference comparison across all scenarios."""

import json
import os
import subprocess
import sys
from pathlib import Path

OUTDIR = "/tmp/ncsim_interference_comparison"
RADIUS = 15
SCENARIOS = [
    # (label, scenario_file, scheduler, has_multihop_scenarios)
    ("A: demo_simple",         "scenarios/demo_simple.yaml",          "heft",        True),
    ("B: bandwidth_contention","scenarios/bandwidth_contention.yaml", "round_robin", True),
    ("C: multi_hop_forced",    "scenarios/multi_hop_forced.yaml",     "heft",        True),
    ("D: multi_hop_test",      "scenarios/multi_hop_test.yaml",       "heft",        True),
    ("E: multihop_advantage",  "scenarios/multihop_advantage.yaml",   "round_robin", True),
    ("F: parallel_spread",     "scenarios/parallel_spread.yaml",      "heft",        True),
    ("G: widest_vs_shortest",  "scenarios/widest_vs_shortest.yaml",   "round_robin", True),
    ("H: interference_test",   "scenarios/interference_test.yaml",    "round_robin", False),
]

ROUTINGS = ["direct", "widest_path", "shortest_path"]


def run_scenario(name, scenario, routing, scheduler, interference="none", radius=0):
    outdir = os.path.join(OUTDIR, name)
    os.makedirs(outdir, exist_ok=True)
    cmd = [
        sys.executable, "-m", "ncsim",
        "--scenario", scenario,
        "--output", outdir,
        "--routing", routing,
        "--scheduler", scheduler,
        "--seed", "42",
        "--interference", interference,
    ]
    if interference != "none":
        cmd += ["--interference-radius", str(radius)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    # Print last line of stdout (the status line)
    lines = result.stdout.strip().split("\n")
    if lines:
        return lines[-1]
    return ""


def get_makespan(dirname):
    path = os.path.join(OUTDIR, dirname, "metrics.json")
    try:
        with open(path) as f:
            data = json.load(f)
        if data.get("status") == "error":
            return None
        return data["makespan"]
    except Exception:
        return None


def fmt(v):
    if v is None:
        return "ERROR"
    return f"{v:.3f}s"


def impact(base, with_interf):
    if base is None or with_interf is None:
        return "n/a"
    if base == 0:
        return "n/a"
    if base == with_interf:
        return "same"
    return f"{((with_interf - base) / base) * 100:+.1f}%"


def make_key(label, routing, interf):
    safe = label.split(":")[1].strip().replace(" ", "_")
    r = routing.replace("_", "")
    i = "none" if interf == "none" else "prox"
    return f"{safe}_{r}_{i}"


def main():
    os.makedirs(OUTDIR, exist_ok=True)

    print("=" * 90)
    print(f"  ncsim Routing x Interference Comparison")
    print(f"  Interference model: proximity (radius={RADIUS})")
    print("=" * 90)
    print()

    # Run all combinations
    results = {}  # key -> dirname
    for label, scenario, scheduler, has_multi in SCENARIOS:
        routings = ROUTINGS if has_multi else ["direct"]
        for routing in routings:
            for interf in ["none", "proximity"]:
                key = make_key(label, routing, interf)
                print(f"  Running {key}...", end=" ", flush=True)
                run_scenario(key, scenario, routing, scheduler, interf, RADIUS)
                ms = get_makespan(key)
                results[key] = ms
                print(fmt(ms))

    print()

    # Table 1: No interference
    print("=" * 90)
    print("  Table 1: NO Interference (baseline)")
    print("=" * 90)
    print(f"{'Scenario':<28s} {'Direct':>10s} {'WidestPath':>12s} {'ShortestPath':>14s}")
    print(f"{'--------':<28s} {'------':>10s} {'----------':>12s} {'------------':>14s}")
    for label, _, _, has_multi in SCENARIOS:
        d = results.get(make_key(label, "direct", "none"))
        w = results.get(make_key(label, "widest_path", "none")) if has_multi else None
        s = results.get(make_key(label, "shortest_path", "none")) if has_multi else None
        wd = fmt(w) if has_multi else "n/a"
        sd = fmt(s) if has_multi else "n/a"
        print(f"{label:<28s} {fmt(d):>10s} {wd:>12s} {sd:>14s}")

    print()

    # Table 2: With interference
    print("=" * 90)
    print(f"  Table 2: WITH Proximity Interference (radius={RADIUS})")
    print("=" * 90)
    print(f"{'Scenario':<28s} {'Direct':>10s} {'WidestPath':>12s} {'ShortestPath':>14s}")
    print(f"{'--------':<28s} {'------':>10s} {'----------':>12s} {'------------':>14s}")
    for label, _, _, has_multi in SCENARIOS:
        d = results.get(make_key(label, "direct", "proximity"))
        w = results.get(make_key(label, "widest_path", "proximity")) if has_multi else None
        s = results.get(make_key(label, "shortest_path", "proximity")) if has_multi else None
        wd = fmt(w) if has_multi else "n/a"
        sd = fmt(s) if has_multi else "n/a"
        print(f"{label:<28s} {fmt(d):>10s} {wd:>12s} {sd:>14s}")

    print()

    # Table 3: Impact
    print("=" * 90)
    print("  Table 3: Interference Impact (% change, + = slower with interference)")
    print("=" * 90)
    print(f"{'Scenario':<28s} {'Direct':>10s} {'WidestPath':>12s} {'ShortestPath':>14s}")
    print(f"{'--------':<28s} {'------':>10s} {'----------':>12s} {'------------':>14s}")
    for label, _, _, has_multi in SCENARIOS:
        d_n = results.get(make_key(label, "direct", "none"))
        d_p = results.get(make_key(label, "direct", "proximity"))
        if has_multi:
            w_n = results.get(make_key(label, "widest_path", "none"))
            w_p = results.get(make_key(label, "widest_path", "proximity"))
            s_n = results.get(make_key(label, "shortest_path", "none"))
            s_p = results.get(make_key(label, "shortest_path", "proximity"))
        else:
            w_n = w_p = s_n = s_p = None
        wd = impact(w_n, w_p) if has_multi else "n/a"
        sd = impact(s_n, s_p) if has_multi else "n/a"
        print(f"{label:<28s} {impact(d_n, d_p):>10s} {wd:>12s} {sd:>14s}")

    print()
    print(f"Trace files saved to: {OUTDIR}")


if __name__ == "__main__":
    main()

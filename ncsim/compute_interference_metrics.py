#!/usr/bin/env python3
"""Post-process csma_bianchi eval runs to extract per-seed makespans (for std dev)
plus extra metrics (hops, peak link util, xfer duration).

Reads from:
  /tmp/ncsim_full_eval/   — grid eval (3240 runs)
  /tmp/ncsim_random_eval/ — random network eval (8820 runs)

Saves:
  /tmp/ncsim_full_eval/grid_augmented.json
  /tmp/ncsim_random_eval/random_augmented.json

Each JSON maps combo-key → {mean, std, mean_hops, max_hops,
                             peak_link_util, mean_active_link_util,
                             peak_node_util, mean_xfer_duration, mean_queue_wait}
"""

import json
import math
import os
import statistics
from pathlib import Path

GRID_DIR   = Path("/tmp/ncsim_full_eval")
RAND_DIR   = Path("/tmp/ncsim_random_eval")
NUM_SEEDS  = 30

SCHEDULERS       = ["heft", "heft1", "heft2"]
GRID_EXPERIMENTS = ["4x4_small", "4x4_large", "7x7_small", "7x7_large"]
GRID_STRATEGIES  = [
    ("W",     "widest_path",                         None),
    ("S",     "shortest_path",                       None),
    ("SH",    "shortest_hop",                        None),
    ("GS",    "interference_aware",                  "start"),
    ("GC",    "interference_aware",                  "criticality"),
    ("GB",    "interference_aware",                  "bytes"),
    ("GO",    "interference_aware",                  "overlap"),
    ("GSD",   "interference_aware_dynamic",          None),
    ("GSD-D", "interference_aware_dynamic_deferral", None),
]
GRID_LABELS = [s[0] for s in GRID_STRATEGIES]

DENSITIES    = ["L150","L200","L250","L300","L350","L400","L500"]
RAND_DAGS    = ["small","large"]
RAND_STRATEGIES = [
    ("W",     "widest_path",                         None),
    ("S",     "shortest_path",                       None),
    ("SH",    "shortest_hop",                        None),
    ("GO",    "interference_aware",                  "overlap"),
    ("GS",    "interference_aware",                  "start"),
    ("GSD",   "interference_aware_dynamic",          None),
    ("GSD-D", "interference_aware_dynamic_deferral", None),
]
RAND_LABELS = [s[0] for s in RAND_STRATEGIES]


# ── Per-run extraction ────────────────────────────────────────────────────────

def extract_run(rundir: Path) -> dict | None:
    mpath = rundir / "metrics.json"
    tpath = rundir / "trace.jsonl"
    if not mpath.exists():
        return None
    try:
        with open(mpath) as f:
            m = json.load(f)
    except Exception:
        return None
    if m.get("status") == "error":
        return None

    makespan = m.get("makespan")
    if makespan is None:
        return None

    link_utils = list(m.get("link_utilization", {}).values())
    node_utils = list(m.get("node_utilization", {}).values())
    peak_link_util        = max(link_utils) if link_utils else 0.0
    active_lu = [v for v in link_utils if v > 0]
    mean_active_link_util = statistics.mean(active_lu) if active_lu else 0.0
    peak_node_util        = max(node_utils) if node_utils else 0.0

    hops, xfer_durations, queue_waits, scheduled_at = [], [], [], {}
    if tpath.exists():
        try:
            with open(tpath) as f:
                for line in f:
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    t = ev.get("type")
                    if t == "task_scheduled":
                        scheduled_at[ev["task_id"]] = ev["sim_time"]
                    elif t == "task_start":
                        tid = ev["task_id"]
                        if tid in scheduled_at:
                            queue_waits.append(ev["sim_time"] - scheduled_at.pop(tid))
                    elif t == "transfer_start":
                        route = ev.get("route")
                        hops.append(len(route) if route else 1)
                    elif t == "transfer_complete":
                        xfer_durations.append(ev["duration"])
        except Exception:
            pass

    return {
        "makespan":              makespan,
        "peak_link_util":        round(peak_link_util, 4),
        "mean_active_link_util": round(mean_active_link_util, 4),
        "peak_node_util":        round(peak_node_util, 4),
        "mean_hops":             round(statistics.mean(hops), 3) if hops else 0.0,
        "max_hops":              max(hops) if hops else 0,
        "mean_xfer_duration":    round(statistics.mean(xfer_durations), 4) if xfer_durations else 0.0,
        "mean_queue_wait":       round(statistics.mean(queue_waits), 4) if queue_waits else 0.0,
    }


def aggregate(runs: list[dict]) -> dict:
    if not runs:
        return {}
    makespans = [r["makespan"] for r in runs]
    mean_ms = statistics.mean(makespans)
    std_ms  = statistics.stdev(makespans) if len(makespans) > 1 else 0.0
    result  = {"mean": round(mean_ms, 4), "std": round(std_ms, 4)}
    for k in ["peak_link_util","mean_active_link_util","peak_node_util",
               "mean_hops","max_hops","mean_xfer_duration","mean_queue_wait"]:
        vals = [r[k] for r in runs if k in r]
        if vals:
            result[k] = round(statistics.mean(vals), 4)
    return result


# ── Grid ─────────────────────────────────────────────────────────────────────

def collect_grid():
    print("  Grid eval ...")
    out   = {}
    total = len(GRID_EXPERIMENTS) * len(SCHEDULERS) * len(GRID_STRATEGIES)
    done  = 0
    for exp in GRID_EXPERIMENTS:
        for sched in SCHEDULERS:
            for label, routing, go in GRID_STRATEGIES:
                done += 1
                go_sfx = f"_{go}" if go else ""
                runs = []
                for seed in range(1, NUM_SEEDS + 1):
                    d = GRID_DIR / f"{exp}_{sched}_{routing}{go_sfx}_s{seed}"
                    r = extract_run(d)
                    if r:
                        runs.append(r)
                key = f"{exp}|{sched}|{label}"
                out[key] = aggregate(runs)
                if done % 20 == 0:
                    print(f"    {done}/{total}", flush=True)
    return out


# ── Random ───────────────────────────────────────────────────────────────────

def collect_random():
    print("  Random eval ...")
    out   = {}
    total = len(DENSITIES) * len(RAND_DAGS) * len(SCHEDULERS) * len(RAND_STRATEGIES)
    done  = 0
    for dl in DENSITIES:
        for dag in RAND_DAGS:
            for sched in SCHEDULERS:
                for label, routing, go in RAND_STRATEGIES:
                    done += 1
                    go_sfx = f"_{go}" if go else ""
                    runs   = []
                    for seed in range(1, NUM_SEEDS + 1):
                        d = RAND_DIR / f"{dl}_{dag}_{sched}_{routing}{go_sfx}_s{seed}"
                        r = extract_run(d)
                        if r:
                            runs.append(r)
                    key = f"{dl}|{dag}|{sched}|{label}"
                    out[key] = aggregate(runs)
                    if done % 40 == 0:
                        print(f"    {done}/{total}", flush=True)
    return out


def main():
    print("\n  csma_bianchi metric extraction (no re-runs)\n")
    grid = collect_grid()
    rand = collect_random()

    with open(GRID_DIR / "grid_augmented.json", "w") as f:
        json.dump(grid, f, indent=2)
    print(f"  Grid   → {GRID_DIR/'grid_augmented.json'}  ({len(grid)} combos)")

    with open(RAND_DIR / "random_augmented.json", "w") as f:
        json.dump(rand, f, indent=2)
    print(f"  Random → {RAND_DIR/'random_augmented.json'}  ({len(rand)} combos)\n")


if __name__ == "__main__":
    main()

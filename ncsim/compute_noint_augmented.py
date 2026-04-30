#!/usr/bin/env python3
"""Post-process /tmp/ncsim_no_interference_eval to get per-combo mean ± std
for makespan AND mean extra metrics (hops, util, xfer duration, queue wait).

Mirrors compute_interference_metrics.py but for the no-interference eval.
Directory naming: grid_{exp}_{sched}_{routing}[_{go}]_s{seed}
                  rand_{dl}_{dag}_{sched}_{routing}[_{go}]_s{seed}

Output: /tmp/ncsim_no_interference_eval/noint_augmented.json
  keys: "{exp}|{sched}|{label}"      (grid)
        "{dl}|{dag}|{sched}|{label}" (random)
  values: {mean, std, mean_hops, max_hops, peak_link_util,
           mean_active_link_util, peak_node_util, mean_xfer_duration,
           mean_queue_wait}
"""

import json
import statistics
from pathlib import Path

RUNDIR    = Path("/tmp/ncsim_no_interference_eval")
OUT       = RUNDIR / "noint_augmented.json"
NUM_SEEDS = 30

SCHEDULERS = ["heft", "heft1", "heft2"]

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

DENSITIES       = ["L150","L200","L250","L300","L350","L400","L500"]
RAND_DAGS       = ["small","large"]
RAND_STRATEGIES = [
    ("W",     "widest_path",                         None),
    ("S",     "shortest_path",                       None),
    ("SH",    "shortest_hop",                        None),
    ("GO",    "interference_aware",                  "overlap"),
    ("GS",    "interference_aware",                  "start"),
    ("GSD",   "interference_aware_dynamic",          None),
    ("GSD-D", "interference_aware_dynamic_deferral", None),
]


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
    active_lu             = [v for v in link_utils if v > 0]
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
    result = {
        "mean": round(statistics.mean(makespans), 4),
        "std":  round(statistics.stdev(makespans), 4) if len(makespans) > 1 else 0.0,
        "n":    len(makespans),
    }
    for k in ["peak_link_util", "mean_active_link_util", "peak_node_util",
              "mean_hops", "max_hops", "mean_xfer_duration", "mean_queue_wait"]:
        vals = [r[k] for r in runs if k in r]
        if vals:
            result[k] = round(statistics.mean(vals), 4)
    return result


def collect_grid():
    print("  Grid ...")
    out = {}
    total = len(GRID_EXPERIMENTS) * len(SCHEDULERS) * len(GRID_STRATEGIES)
    done  = 0
    for exp in GRID_EXPERIMENTS:
        for sched in SCHEDULERS:
            for label, routing, go in GRID_STRATEGIES:
                done += 1
                go_sfx = f"_{go}" if go else ""
                runs = []
                for seed in range(1, NUM_SEEDS + 1):
                    d = RUNDIR / f"grid_{exp}_{sched}_{routing}{go_sfx}_s{seed}"
                    r = extract_run(d)
                    if r:
                        runs.append(r)
                out[f"{exp}|{sched}|{label}"] = aggregate(runs)
                if done % 20 == 0:
                    print(f"    {done}/{total}", flush=True)
    return out


def collect_random():
    print("  Random ...")
    out = {}
    total = len(DENSITIES) * len(RAND_DAGS) * len(SCHEDULERS) * len(RAND_STRATEGIES)
    done  = 0
    for dl in DENSITIES:
        for dag in RAND_DAGS:
            for sched in SCHEDULERS:
                for label, routing, go in RAND_STRATEGIES:
                    done += 1
                    go_sfx = f"_{go}" if go else ""
                    runs = []
                    for seed in range(1, NUM_SEEDS + 1):
                        d = RUNDIR / f"rand_{dl}_{dag}_{sched}_{routing}{go_sfx}_s{seed}"
                        r = extract_run(d)
                        if r:
                            runs.append(r)
                    out[f"{dl}|{dag}|{sched}|{label}"] = aggregate(runs)
                    if done % 40 == 0:
                        print(f"    {done}/{total}", flush=True)
    return out


def main():
    print("\n  No-interference augmented metric extraction\n")
    grid   = collect_grid()
    random = collect_random()
    result = {"grid": grid, "random": random}
    with open(OUT, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n  Saved → {OUT}")
    print(f"  Grid combos: {len(grid)}  |  Random combos: {len(random)}")


if __name__ == "__main__":
    main()

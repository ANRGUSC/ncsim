#!/usr/bin/env python3
"""Post-process /tmp/ncsim_no_interference_eval runs to extract additional metrics.

Reads existing trace.jsonl + metrics.json files for all 12 060 runs
(no re-running) and computes per-combo averages of:
  - mean_hops          : mean path length (hops) per transfer
  - max_hops           : max path length seen in any transfer
  - peak_link_util     : max link_utilization across all links
  - mean_active_link_util : mean utilization of links that carried traffic
  - peak_node_util     : max node_utilization across all nodes
  - mean_active_node_util : mean utilization of nodes that did work
  - mean_queue_wait    : mean (task_start - task_scheduled) in seconds
  - mean_xfer_duration : mean transfer duration in seconds

Saves augmented JSON to /tmp/ncsim_no_interference_eval/extra_metrics.json.
"""

import json
import os
import statistics
from pathlib import Path

RUNDIR = Path("/tmp/ncsim_no_interference_eval")
OUT    = RUNDIR / "extra_metrics.json"

# ── Reproduce the combo-to-dir naming from run_no_interference_eval.py ────────

GRID_EXPERIMENTS = [
    ("4x4_small", 4, "small"),
    ("4x4_large", 4, "large"),
    ("7x7_small", 7, "small"),
    ("7x7_large", 7, "large"),
]
SCHEDULERS = ["heft", "heft1", "heft2"]
GRID_STRATEGIES = [
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
DENSITIES = ["L150","L200","L250","L300","L350","L400","L500"]
RAND_DAGS = ["small","large"]
RAND_STRATEGIES = [
    ("W",     "widest_path",                         None),
    ("S",     "shortest_path",                       None),
    ("SH",    "shortest_hop",                        None),
    ("GO",    "interference_aware",                  "overlap"),
    ("GS",    "interference_aware",                  "start"),
    ("GSD",   "interference_aware_dynamic",          None),
    ("GSD-D", "interference_aware_dynamic_deferral", None),
]
NUM_SEEDS = 30


# ── Per-run metric extraction ─────────────────────────────────────────────────

def extract_run_metrics(rundir: Path) -> dict | None:
    mpath = rundir / "metrics.json"
    tpath = rundir / "trace.jsonl"
    if not mpath.exists() or not tpath.exists():
        return None

    try:
        with open(mpath) as f:
            m = json.load(f)
    except Exception:
        return None

    if m.get("status") == "error":
        return None

    # ── Link + node utilisation ───────────────────────────────────────────────
    link_utils = list(m.get("link_utilization", {}).values())
    node_utils = list(m.get("node_utilization", {}).values())

    peak_link_util        = max(link_utils) if link_utils else 0.0
    active_lu = [v for v in link_utils if v > 0]
    mean_active_link_util = statistics.mean(active_lu) if active_lu else 0.0
    active_link_count     = len(active_lu)

    peak_node_util        = max(node_utils) if node_utils else 0.0
    active_nu = [v for v in node_utils if v > 0]
    mean_active_node_util = statistics.mean(active_nu) if active_nu else 0.0

    # ── Trace parsing ─────────────────────────────────────────────────────────
    hops          = []
    xfer_durations = []
    scheduled_at  = {}   # task_id -> sim_time
    queue_waits   = []

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
                    h = len(route) if route else 1
                    hops.append(h)

                elif t == "transfer_complete":
                    xfer_durations.append(ev["duration"])
    except Exception:
        pass

    return {
        "peak_link_util":        round(peak_link_util, 4),
        "mean_active_link_util": round(mean_active_link_util, 4),
        "active_link_count":     active_link_count,
        "peak_node_util":        round(peak_node_util, 4),
        "mean_active_node_util": round(mean_active_node_util, 4),
        "mean_hops":             round(statistics.mean(hops), 3)        if hops else 0.0,
        "max_hops":              max(hops)                               if hops else 0,
        "mean_xfer_duration":    round(statistics.mean(xfer_durations), 4) if xfer_durations else 0.0,
        "mean_queue_wait":       round(statistics.mean(queue_waits), 4)  if queue_waits else 0.0,
    }


def avg_metrics(runs: list[dict]) -> dict:
    """Average a list of per-run metric dicts."""
    if not runs:
        return {}
    keys = runs[0].keys()
    result = {}
    for k in keys:
        vals = [r[k] for r in runs if r.get(k) is not None]
        if vals:
            result[k] = round(statistics.mean(vals), 4) if isinstance(vals[0], float) \
                        else round(sum(vals) / len(vals), 2)
    return result


# ── Grid combos ───────────────────────────────────────────────────────────────

def collect_grid():
    print("  Collecting grid metrics ...")
    result = {}
    total = len(GRID_EXPERIMENTS) * len(SCHEDULERS) * len(GRID_STRATEGIES)
    done = 0
    for exp_name, grid, dag_label in GRID_EXPERIMENTS:
        for sched in SCHEDULERS:
            for label, routing, greedy_order in GRID_STRATEGIES:
                done += 1
                go_sfx = f"_{greedy_order}" if greedy_order else ""
                runs = []
                for seed in range(1, NUM_SEEDS + 1):
                    d = RUNDIR / f"grid_{exp_name}_{sched}_{routing}{go_sfx}_s{seed}"
                    m = extract_run_metrics(d)
                    if m:
                        runs.append(m)
                if runs:
                    result[(exp_name, sched, label)] = avg_metrics(runs)
                if done % 20 == 0:
                    print(f"    grid {done}/{total} combos processed", flush=True)
    return result


# ── Random combos ─────────────────────────────────────────────────────────────

def collect_random():
    print("  Collecting random-network metrics ...")
    result = {}
    total = len(DENSITIES) * len(RAND_DAGS) * len(SCHEDULERS) * len(RAND_STRATEGIES)
    done = 0
    for dlabel in DENSITIES:
        for dag_label in RAND_DAGS:
            for sched in SCHEDULERS:
                for rlabel, routing, greedy_order in RAND_STRATEGIES:
                    done += 1
                    go_sfx = f"_{greedy_order}" if greedy_order else ""
                    runs = []
                    for seed in range(1, NUM_SEEDS + 1):
                        d = RUNDIR / f"rand_{dlabel}_{dag_label}_{sched}_{routing}{go_sfx}_s{seed}"
                        m = extract_run_metrics(d)
                        if m:
                            runs.append(m)
                    if runs:
                        result[(dlabel, dag_label, sched, rlabel)] = avg_metrics(runs)
                    if done % 30 == 0:
                        print(f"    random {done}/{total} combos processed", flush=True)
    return result


def main():
    print("\n  Extra-metric extraction (reading existing trace files, no re-runs)")
    print(f"  Run directory: {RUNDIR}\n")

    grid_metrics   = collect_grid()
    random_metrics = collect_random()

    # Serialise (tuple keys → strings)
    out = {
        "grid":   {f"{e}|{s}|{l}": v for (e, s, l), v in grid_metrics.items()},
        "random": {f"{d}|{g}|{s}|{r}": v for (d, g, s, r), v in random_metrics.items()},
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n  Saved → {OUT}")
    print(f"  Grid combos: {len(grid_metrics)}  |  Random combos: {len(random_metrics)}")


if __name__ == "__main__":
    main()

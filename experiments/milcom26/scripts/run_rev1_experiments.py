#!/usr/bin/env python3
"""Run the paper revision experiments with resumable JSON output."""
from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import io
import json
import os
import statistics
import time
from pathlib import Path

from rev1_common import (DATA_DIR, DENSITIES, NCSIM_COMMIT, ROUTES, grid_topology,
                         _install_wifi_cache, random_topology, run_ncsim, schedule_placements,
                         schedule_heft1_assignments, workload, write_json)

OUT = DATA_DIR / "rev1_results.json"
MANIFEST = DATA_DIR / "rev1_manifest.json"
SCHEDULERS = ("heft1", "lc_heft", "heft2")
DESIGN_VERSION = 2
RUN_PREFIX = f"r{DESIGN_VERSION}_"


def load_records():
    if not OUT.exists():
        return {}
    payload = json.loads(OUT.read_text(encoding="utf-8"))
    return {r["run_id"]: r for r in payload.get("records", [])}


def save(records, manifest):
    write_json(OUT, {"schema_version": 1, "records": list(records.values())})
    write_json(MANIFEST, manifest)


def execute_job(job):
    """Execute one self-contained simulation job inside a worker process."""
    job = dict(job)
    # ncsim's CLI prints a human summary for each run.  The structured metrics
    # are retained below; suppress thousands of duplicate console summaries in
    # non-interactive ensemble workers.
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_ncsim(
            job["run_id"], job.pop("topology"), job.pop("tasks"), job.pop("edges"),
            job["scheduler"], job["routing"], job["simulation_seed"],
            interference=job.get("interference", "csma_bianchi"),
            greedy_order=job.get("greedy_order"), placement=job.pop("placement"),
        )
    return {"design_version": DESIGN_VERSION, **job, **result}


def execute_topology_group(group):
    """Reuse the RF cache for all matched jobs on one physical topology."""
    _install_wifi_cache()
    return [execute_job(job) for job in group]


def run_jobs(jobs, records, manifest, workers=8):
    # Successful records are resumable; failed or interrupted records are
    # deliberately retried after a harness fix.
    pending = [j for j in jobs
               if j["run_id"] not in records
               or records[j["run_id"]].get("status") not in ("ok", "completed")]
    print(f"  {len(pending)} pending / {len(jobs)} defined")

    groups = {}
    for job in pending:
        key = (job["network"], job["topology_ordinal"], job["topology_seed"])
        # The regular grid has 1,620 routing runs but only one topology.  Split
        # it by DAG size so those independent matched blocks can run in
        # parallel; each worker still reuses its grid conflict graph internally.
        if job["network"] == "7x7" and job.get("experiment") == "routing":
            key += (job["dag_size"],)
        groups.setdefault(key, []).append(job)
    completed = 0
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(execute_topology_group, group): key
                   for key, group in groups.items()}
        for fut in concurrent.futures.as_completed(futures):
            batch = fut.result()
            for rec in batch:
                records[rec["run_id"]] = rec
            completed += len(batch)
            errors = sum(r.get("status") == "error" for r in records.values())
            print(f"    completed {completed}/{len(pending)}; total errors={errors}", flush=True)
            save(records, manifest)
    save(records, manifest)


def topology_ensemble(k):
    out = {}
    for side in DENSITIES:
        out[side] = [random_topology(side, i) for i in range(1, k + 1)]
    return out


def base_manifest(ensembles, k, m):
    topology_manifest = {}
    for side, tops in ensembles.items():
        accepted = [{x: t[x] for x in ("ordinal", "topology_seed",
                                        "n_undirected_links", "degree_mean",
                                        "degree_median", "degree_min", "degree_max")}
                    for t in tops]
        topology_manifest[f"L{side}"] = {
            "accepted": accepted,
            "rejected_seeds": sorted({seed for t in tops for seed in t["rejected_seeds"]}),
            "ensemble_degree_mean": statistics.mean(t["degree_mean"] for t in tops),
            "ensemble_degree_median": statistics.median(t["degree_median"] for t in tops),
        }
    return {
        "software": {"ncsim_commit": NCSIM_COMMIT, "python_hash_seed": 0,
                     "design_version": DESIGN_VERSION},
        "design": {"topologies_per_density": k, "workloads_per_topology": m,
                   "connectivity": "reject disconnected radius-limited draws",
                   "communication_range_m": 80, "simulation_seed": "1000 + workload_seed"},
        "topologies": topology_manifest,
        "workloads": {},
    }


def sched_jobs(ensembles, manifest, m):
    jobs = []
    for side, tops in ensembles.items():
        for topo in tops:
            for ws in range(1, m + 1):
                tasks, edges = workload(30, ws)
                manifest["workloads"][f"30|{ws}"] = {"tasks": tasks, "edges": edges}
                placements = schedule_placements(topo, tasks, edges, 7000 + ws)
                for sched in SCHEDULERS:
                    rid = f"{RUN_PREFIX}scheduler_L{side}_t{topo['ordinal']}_w{ws}_{sched}"
                    jobs.append({"run_id": rid, "experiment": "scheduler_density",
                                 "network": f"L{side}", "topology_ordinal": topo["ordinal"],
                                 "topology_seed": topo["topology_seed"], "workload_seed": ws,
                                 "simulation_seed": 1000 + ws, "dag_size": 30,
                                 "scheduler": sched, "routing": "shortest_hop",
                                 "predicted_makespan": placements[sched]["predicted_makespan"],
                                 "diagnostics": placements[sched]["diagnostics"],
                                 "placement": placements[sched]["assignments"],
                                 "topology": topo, "tasks": tasks, "edges": edges})
    return jobs


def table_jobs(manifest):
    jobs = []
    for size in (4, 7):
        topo = grid_topology(size)
        for n_tasks, tag in ((8, "S"), (30, "L")):
            for ws in range(1, 31):
                tasks, edges = workload(n_tasks, ws)
                manifest["workloads"][f"{n_tasks}|{ws}"] = {"tasks": tasks, "edges": edges}
                placements = schedule_placements(topo, tasks, edges, 7000 + ws)
                for sched in SCHEDULERS:
                    rid = f"{RUN_PREFIX}table_{size}x{size}_{tag}_{sched}_s{ws}"
                    jobs.append({"run_id": rid, "experiment": "table_iii",
                                 "network": f"{size}x{size}", "topology_ordinal": 0,
                                 "topology_seed": 0, "workload_seed": ws,
                                 "simulation_seed": ws, "dag_size": n_tasks,
                                 "scheduler": sched, "routing": "shortest_hop",
                                 "predicted_makespan": placements[sched]["predicted_makespan"],
                                 "diagnostics": placements[sched]["diagnostics"],
                                 "placement": placements[sched]["assignments"],
                                 "topology": topo, "tasks": tasks, "edges": edges})
    return jobs


def routing_jobs(ensembles, manifest, m, grid_reps=30):
    jobs = []
    selected = {150: ensembles[150], 500: ensembles[500]}
    for side, tops in selected.items():
        for topo in tops:
            for n_tasks in (8, 16, 24, 32, 45, 60):
                for ws in range(1, m + 1):
                    tasks, edges = workload(n_tasks, ws)
                    manifest["workloads"][f"{n_tasks}|{ws}"] = {"tasks": tasks, "edges": edges}
                    placement = schedule_heft1_assignments(topo, tasks, edges, 7000 + ws)
                    for label, route, order in ROUTES:
                        rid = f"{RUN_PREFIX}routing_L{side}_t{topo['ordinal']}_n{n_tasks}_w{ws}_{label}"
                        jobs.append({"run_id": rid, "experiment": "routing",
                                     "network": f"L{side}", "topology_ordinal": topo["ordinal"],
                                     "topology_seed": topo["topology_seed"], "workload_seed": ws,
                                     "simulation_seed": 1000 + ws, "dag_size": n_tasks,
                                     "scheduler": "heft1", "routing": route,
                                     "routing_label": label, "greedy_order": order,
                                     "placement": placement,
                                     "topology": topo, "tasks": tasks, "edges": edges})
    topo = grid_topology(7)
    for n_tasks in (8, 16, 24, 32, 45, 60):
        for ws in range(1, grid_reps + 1):
            tasks, edges = workload(n_tasks, ws)
            manifest["workloads"][f"{n_tasks}|{ws}"] = {"tasks": tasks, "edges": edges}
            placement = schedule_heft1_assignments(topo, tasks, edges, 7000 + ws)
            for label, route, order in ROUTES:
                rid = f"{RUN_PREFIX}routing_7x7_n{n_tasks}_w{ws}_{label}"
                jobs.append({"run_id": rid, "experiment": "routing",
                             "network": "7x7", "topology_ordinal": 0, "topology_seed": 0,
                             "workload_seed": ws, "simulation_seed": 2000 + ws,
                             "dag_size": n_tasks, "scheduler": "heft1", "routing": route,
                             "routing_label": label, "greedy_order": order,
                             "placement": placement,
                             "topology": topo, "tasks": tasks, "edges": edges})
    return jobs


def nointerference_jobs(ensembles, manifest, m):
    jobs = []
    for side, tops in ensembles.items():
        for topo in tops:
            for ws in range(1, m + 1):
                tasks, edges = workload(30, ws)
                placements = schedule_placements(topo, tasks, edges, 7000 + ws)
                for sched in SCHEDULERS:
                    rid = f"{RUN_PREFIX}noint_L{side}_t{topo['ordinal']}_w{ws}_{sched}"
                    jobs.append({"run_id": rid, "experiment": "no_interference",
                                 "network": f"L{side}", "topology_ordinal": topo["ordinal"],
                                 "topology_seed": topo["topology_seed"], "workload_seed": ws,
                                 "simulation_seed": 1000 + ws, "dag_size": 30,
                                 "scheduler": sched, "routing": "shortest_hop",
                                 "interference": "none",
                                 "placement": placements[sched]["assignments"],
                                 "topology": topo, "tasks": tasks, "edges": edges})
    return jobs


def commcomp_jobs(ensembles, manifest, m):
    jobs = []
    for side in (150, 500):
        for topo in ensembles[side]:
            for ws in range(1, m + 1):
                base_tasks, base_edges = workload(30, ws)
                for scale in (0.1, 1.0, 10.0):
                    edges = [{**e, "data_size": e["data_size"] * scale} for e in base_edges]
                    placements = schedule_placements(topo, base_tasks, edges, 7000 + ws)
                    for sched in ("heft1", "heft2"):
                        rid = f"{RUN_PREFIX}commcomp_L{side}_t{topo['ordinal']}_w{ws}_x{scale}_{sched}"
                        jobs.append({"run_id": rid, "experiment": "commcomp",
                                     "network": f"L{side}", "topology_ordinal": topo["ordinal"],
                                     "topology_seed": topo["topology_seed"], "workload_seed": ws,
                                     "simulation_seed": 1000 + ws, "dag_size": 30,
                                     "data_scale": scale, "scheduler": sched,
                                     "routing": "shortest_hop",
                                     "placement": placements[sched]["assignments"],
                                     "topology": topo, "tasks": base_tasks, "edges": edges})
    return jobs


def penalty_jobs(ensembles, manifest, m):
    jobs = []
    for side in (150, 500):
        for topo in ensembles[side]:
            for ws in range(1, m + 1):
                tasks, edges = workload(30, ws)
                for penalty in (0.0001, 0.001, 0.01, 0.1, 1.0):
                    placement = schedule_heft1_assignments(
                        topo, tasks, edges, 7000 + ws, penalty=penalty)
                    tag = f"{penalty:g}"
                    rid = f"{RUN_PREFIX}penalty_L{side}_t{topo['ordinal']}_w{ws}_p{tag}"
                    jobs.append({"run_id": rid, "experiment": "penalty",
                                 "network": f"L{side}", "topology_ordinal": topo["ordinal"],
                                 "topology_seed": topo["topology_seed"], "workload_seed": ws,
                                 "simulation_seed": 1000 + ws, "dag_size": 30,
                                 "penalty_rate": penalty, "scheduler": "heft1",
                                 "routing": "shortest_hop", "placement": placement,
                                 "topology": topo, "tasks": tasks, "edges": edges})
    return jobs


def main():
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise SystemExit("Set PYTHONHASHSEED=0 before starting the revision runner")
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("smoke", "scheduler", "table", "routing", "ablations", "all"), default="all")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    k, m = ((1, 1) if args.mode == "smoke" else (10, 3))
    print(f"Generating {k} connected topologies per density ...")
    ensembles = topology_ensemble(k)
    manifest = base_manifest(ensembles, k, m)
    records = load_records()
    jobs = []
    if args.mode in ("smoke", "scheduler", "all"):
        jobs += sched_jobs(ensembles, manifest, m)
    if args.mode in ("table", "all"):
        jobs += table_jobs(manifest)
    if args.mode in ("routing", "all"):
        jobs += routing_jobs(ensembles, manifest, m, grid_reps=1 if args.mode == "smoke" else 30)
    if args.mode in ("ablations", "all"):
        jobs += nointerference_jobs(ensembles, manifest, m)
        jobs += commcomp_jobs(ensembles, manifest, m)
        jobs += penalty_jobs(ensembles, manifest, m)
    if args.mode == "smoke":
        jobs = jobs[:12]
    print(f"Running {len(jobs)} jobs with {args.workers} workers")
    run_jobs(jobs, records, manifest, args.workers)
    print(f"Wrote {OUT} and {MANIFEST}")


if __name__ == "__main__":
    main()

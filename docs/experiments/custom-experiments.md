# Custom Experiments

This guide shows how to design your own parameter sweep experiments using ncsim.
Whether you are comparing schedulers, varying RF parameters, or scaling network
size, the pattern is the same: generate scenarios, run ncsim via subprocess (or
import it as a library), and collect results.

---

## Experiment Design Principles

1. **Define your hypothesis.** For example: "HEFT outperforms CPOP on
   heterogeneous networks with high communication-to-computation ratio."
2. **Identify independent variables** -- what you vary (scheduler, network size,
   data size, RF parameters, etc.).
3. **Identify dependent variables** -- what you measure. Usually **makespan**,
   but you can also extract per-transfer durations, link utilization, or task
   placement from the trace file.
4. **Control variables** -- keep everything else fixed. Use the same random seed
   across runs to eliminate scheduling variability from a single trial.
5. **Replicate with multiple seeds** to average out stochastic effects.

---

## Template: Parameter Sweep Script

The following template demonstrates the standard pattern used by all ncsim
experiment scripts. It invokes ncsim as a subprocess with CLI overrides, then
reads `metrics.json` to extract results.

```python
#!/usr/bin/env python3
"""Template for ncsim parameter sweep experiments."""

import json
import os
import subprocess
import sys
from pathlib import Path

OUTDIR = "/tmp/ncsim_my_experiment"


def run_scenario(yaml_path, output_dir, **overrides):
    """Run ncsim with optional CLI overrides.

    Args:
        yaml_path: Path to scenario YAML file.
        output_dir: Directory for trace and metrics output.
        **overrides: CLI flag overrides (e.g., scheduler="heft", seed=42).

    Returns:
        output_dir on success, None on failure.
    """
    cmd = [
        sys.executable, "-m", "ncsim",
        "--scenario", str(yaml_path),
        "--output", str(output_dir),
    ]
    for key, value in overrides.items():
        cmd.extend([f"--{key.replace('_', '-')}", str(value)])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: {result.stderr[-200:]}")
        return None
    return output_dir


def get_makespan(output_dir):
    """Extract makespan from metrics.json."""
    metrics_path = os.path.join(output_dir, "metrics.json")
    with open(metrics_path) as f:
        return json.load(f)["makespan"]


def main():
    os.makedirs(OUTDIR, exist_ok=True)

    # Example: sweep schedulers across multiple seeds
    schedulers = ["heft", "cpop", "round_robin"]
    seeds = [1, 2, 3, 4, 5]

    results = {}
    for sched in schedulers:
        makespans = []
        for seed in seeds:
            outdir = os.path.join(OUTDIR, f"{sched}_s{seed}")
            run_scenario(
                "scenarios/parallel_spread.yaml", outdir,
                scheduler=sched, seed=seed
            )
            makespans.append(get_makespan(outdir))
        results[sched] = makespans
        avg = sum(makespans) / len(makespans)
        print(f"{sched}: avg makespan = {avg:.3f}s")


if __name__ == "__main__":
    main()
```

!!! tip "CLI overrides"
    Any scenario YAML parameter can be overridden from the command line. Common
    overrides include `--scheduler`, `--routing`, `--interference`, `--seed`,
    `--tx-power`, `--freq`, `--path-loss-exponent`, and `--wifi-standard`. See
    the [CLI Reference](../cli/cli-reference.md) for the full list.

---

## Example Experiments

### 1. Scheduler Comparison

Vary the scheduler across multiple scenarios and seeds to find which algorithm
performs best under different workload characteristics.

```python
schedulers = ["heft", "cpop", "round_robin"]
scenarios = [
    "scenarios/parallel_spread.yaml",
    "scenarios/demo_simple.yaml",
    "scenarios/bandwidth_contention.yaml",
]
seeds = range(1, 11)  # 10 seeds for statistical significance

for scenario in scenarios:
    for sched in schedulers:
        for seed in seeds:
            outdir = f"/tmp/sched_cmp/{Path(scenario).stem}/{sched}_s{seed}"
            run_scenario(scenario, outdir, scheduler=sched, seed=seed)
```

### 2. Interference Radius Sweep

Vary the proximity interference radius from 5m to 50m to understand how
interference range affects makespan.

```python
radii = [5, 10, 15, 20, 25, 30, 40, 50]
for radius in radii:
    outdir = f"/tmp/radius_sweep/r{radius}"
    run_scenario(
        "scenarios/interference_test.yaml", outdir,
        interference="proximity",
        interference_radius=radius,
    )
```

### 3. WiFi Parameter Sensitivity

Vary TX power, frequency, or path loss exponent to study their impact on
network capacity and makespan.

```python
# TX power sweep
for tx_power in [10, 15, 20, 23]:
    outdir = f"/tmp/txpower_sweep/p{tx_power}"
    run_scenario(
        "scenarios/wifi_test.yaml", outdir,
        interference="csma_bianchi",
        tx_power=tx_power,
    )

# Path loss exponent sweep
for n in [2.0, 2.5, 3.0, 3.5, 4.0]:
    outdir = f"/tmp/pathloss_sweep/n{n}"
    run_scenario(
        "scenarios/wifi_test.yaml", outdir,
        interference="csma_bianchi",
        path_loss_exponent=n,
    )
```

### 4. Network Scaling

Programmatically generate larger networks and measure how scheduler performance
scales with node count. See `run_routing_comparison.py` for a complete example
of generating grid topologies in code.

### 5. Data Size Sensitivity

Vary `data_size` on DAG edges to find the crossover point where widest_path
routing begins to outperform shortest_path (bandwidth-dominated vs
latency-dominated workloads).

---

## Using ncsim as a Library

For tighter integration or custom analysis, you can import ncsim modules
directly instead of invoking the CLI:

```python
from ncsim.models.wifi import (
    RFConfig,
    snr_to_rate_mbps,
    rate_mbps_to_MBps,
    bianchi_efficiency,
    carrier_sensing_range,
    received_power_dBm,
    snr_dB,
    sinr_dB,
    path_loss_dB,
)

# Compute PHY rate at a given distance
rf = RFConfig(tx_power_dBm=20, freq_ghz=5.0, path_loss_exponent=3.0)
distance = 40.0  # meters
rx_power = received_power_dBm(rf.tx_power_dBm, distance, rf)
snr = snr_dB(rx_power, rf.noise_floor_dBm)
rate = snr_to_rate_mbps(snr, rf.wifi_standard, rf.channel_width_mhz)
print(f"PHY rate at {distance}m: {rate:.1f} Mbps ({rate_mbps_to_MBps(rate):.2f} MB/s)")

# Carrier sensing range
cs_range = carrier_sensing_range(rf)
print(f"Carrier sensing range: {cs_range:.1f}m")

# Bianchi MAC efficiency for N contending stations
for n in range(1, 6):
    eta = bianchi_efficiency(n)
    print(f"  eta({n}) = {eta:.4f}, per-station share = {eta/n:.4f}")
```

This is the approach used by `run_interference_verification.py` to compute
analytical predictions that are compared against simulation output.

!!! note "Library vs CLI"
    Using ncsim as a library gives you direct access to the WiFi model functions
    for analytical calculations, but the full simulation pipeline (scenario
    loading, scheduling, trace writing) is easiest to drive through the CLI.

---

## Analyzing Results

Collect results from multiple runs into a structured format for analysis. Here
is a pattern using pandas DataFrames:

```python
import json
import os
import pandas as pd

def collect_results(base_dir):
    """Scan output directories and build a DataFrame of results."""
    rows = []
    for run_name in sorted(os.listdir(base_dir)):
        metrics_path = os.path.join(base_dir, run_name, "metrics.json")
        if not os.path.exists(metrics_path):
            continue
        with open(metrics_path) as f:
            metrics = json.load(f)
        rows.append({
            "run": run_name,
            "makespan": metrics["makespan"],
            "status": metrics.get("status", "unknown"),
            "total_events": metrics.get("total_events", 0),
        })
    return pd.DataFrame(rows)

df = collect_results("/tmp/ncsim_my_experiment")
print(df.groupby("run")["makespan"].describe())
```

### Generating Comparison Plots

```python
import matplotlib.pyplot as plt

# Example: bar chart comparing schedulers
fig, ax = plt.subplots(figsize=(8, 5))
for sched in ["heft", "cpop", "round_robin"]:
    subset = df[df["run"].str.startswith(sched)]
    ax.bar(sched, subset["makespan"].mean(),
           yerr=subset["makespan"].std(), capsize=5)
ax.set_ylabel("Makespan (s)")
ax.set_title("Scheduler Comparison")
fig.savefig("/tmp/ncsim_my_experiment/scheduler_comparison.png", dpi=150)
```

---

## Extracting Trace Data

For more detailed analysis, parse the `trace.jsonl` file to extract per-task
and per-transfer timing:

```python
import json

def parse_trace(trace_path):
    """Parse trace.jsonl into task and transfer records."""
    tasks = {}
    transfers = {}

    with open(trace_path) as f:
        for line in f:
            event = json.loads(line)
            etype = event["type"]

            if etype == "task_start":
                tasks[event["task_id"]] = {
                    "node": event["node_id"],
                    "start": event["sim_time"],
                }
            elif etype == "task_complete":
                tasks[event["task_id"]]["end"] = event["sim_time"]
                tasks[event["task_id"]]["duration"] = event["duration"]

            elif etype == "transfer_start":
                key = (event["from_task"], event["to_task"])
                transfers[key] = {
                    "link": event["link_id"],
                    "data_size": event["data_size"],
                    "start": event["sim_time"],
                }
            elif etype == "transfer_complete":
                key = (event["from_task"], event["to_task"])
                transfers[key]["end"] = event["sim_time"]
                transfers[key]["duration"] = event["duration"]

    return tasks, transfers
```

This gives you access to individual task execution times, transfer durations,
link assignments, and scheduling decisions for any analysis you need.

---

## Best Practices

!!! abstract "Checklist for reliable experiments"

    - **Use fixed seeds for reproducibility.** Every run should specify
      `--seed N` so results can be exactly reproduced.
    - **Run multiple seeds** (at least 5-10) to average out scheduling
      variability and get statistically meaningful results.
    - **Save all output.** Each output directory contains a copy of
      `scenario.yaml`, enabling exact reproduction of any run.
    - **Use meaningful output directory names.** Encode the variable values in
      the directory path (e.g., `heft_s42`, `txpower_20_freq_5`).
    - **Print progress indicators** for long sweeps so you know which run is
      currently executing.
    - **Check for failures.** Always verify that `metrics.json` exists and that
      `status` is not `"error"` before using the makespan value.
    - **Control one variable at a time.** When comparing schedulers, keep
      routing, interference, and all RF parameters constant (and vice versa).
    - **Use the same scenario YAML** across compared runs, varying only the CLI
      override for the parameter under study.

### Directory Structure Convention

A well-organized experiment output looks like this:

```
/tmp/ncsim_my_experiment/
    heft_s1/
        scenario.yaml
        trace.jsonl
        metrics.json
    heft_s2/
        ...
    cpop_s1/
        ...
    figures/
        scheduler_comparison.png
```

### Scaling to Large Sweeps

For sweeps with hundreds of runs, consider:

- **Parallelizing** with Python's `concurrent.futures.ProcessPoolExecutor`
  (each ncsim invocation is independent).
- **Skipping completed runs** by checking if `metrics.json` already exists
  before launching a subprocess.
- **Writing results incrementally** to a CSV or JSON file after each run
  completes, so partial results survive interruptions.

```python
from concurrent.futures import ProcessPoolExecutor, as_completed

def run_one(args):
    yaml_path, outdir, overrides = args
    if os.path.exists(os.path.join(outdir, "metrics.json")):
        return outdir  # skip completed
    return run_scenario(yaml_path, outdir, **overrides)

jobs = []
for sched in schedulers:
    for seed in range(1, 101):
        outdir = f"/tmp/large_sweep/{sched}_s{seed}"
        jobs.append(("scenarios/parallel_spread.yaml", outdir,
                      {"scheduler": sched, "seed": seed}))

with ProcessPoolExecutor(max_workers=4) as pool:
    futures = [pool.submit(run_one, job) for job in jobs]
    for f in as_completed(futures):
        result = f.result()
        if result:
            print(f"Completed: {result}")
```

# Batch Experiments

Running many simulations with different parameters is a common workflow for
comparing schedulers, sweeping interference settings, or gathering statistics
across random seeds. This page shows patterns for batch execution, result
collection, and output organization.

---

## Bash Loops

The simplest approach uses nested shell loops. Each combination of scheduler and
seed gets its own output directory.

```bash
for sched in heft cpop round_robin; do
  for seed in 1 2 3 4 5; do
    ncsim --scenario scenarios/parallel_spread.yaml \
          --output "output/sweep/${sched}_s${seed}" \
          --scheduler "$sched" --seed "$seed"
  done
done
```

!!! tip "Parallel execution"
    ncsim runs are independent and can be parallelized with GNU `parallel` or
    `xargs`:

    ```bash
    parallel -j4 ncsim --scenario scenarios/parallel_spread.yaml \
        --output output/sweep/{1}_s{2} \
        --scheduler {1} --seed {2} \
        ::: heft cpop round_robin \
        ::: 1 2 3 4 5
    ```

---

## Python Script

For more control over parameter combinations, use Python with `itertools.product`:

```python
import subprocess
import itertools

scenarios = ["demo_simple", "parallel_spread"]
schedulers = ["heft", "cpop"]
seeds = [1, 2, 3, 4, 5]

for scen, sched, seed in itertools.product(scenarios, schedulers, seeds):
    output_dir = f"output/{scen}_{sched}_s{seed}"
    result = subprocess.run([
        "ncsim",
        "--scenario", f"scenarios/{scen}.yaml",
        "--output", output_dir,
        "--scheduler", sched,
        "--seed", str(seed),
    ], check=True)
    print(f"Completed: {output_dir}")
```

!!! note "Error handling"
    Using `check=True` causes the script to stop on the first failure. For
    long sweeps where you want to continue past errors, catch
    `subprocess.CalledProcessError` and log the failure instead:

    ```python
    try:
        subprocess.run([...], check=True)
    except subprocess.CalledProcessError as e:
        print(f"FAILED: {output_dir} (exit code {e.returncode})")
    ```

---

## Collecting Results

After a batch run, parse the `metrics.json` files from each output directory
to build a comparison table.

### Basic collection

```python
import json
from pathlib import Path

results = []
for metrics_path in sorted(Path("output/sweep").rglob("metrics.json")):
    with open(metrics_path) as f:
        metrics = json.load(f)
    # Extract run parameters from directory name
    run_name = metrics_path.parent.name
    metrics["run"] = run_name
    results.append(metrics)

# Print summary table
print(f"{'Run':<25} {'Makespan':>10} {'Status':<10}")
print("-" * 50)
for r in results:
    print(f"{r['run']:<25} {r['makespan']:>10.4f} {r['status']:<10}")
```

### Aggregating with pandas

```python
import json
import pandas as pd
from pathlib import Path

rows = []
for metrics_path in Path("output/sweep").rglob("metrics.json"):
    with open(metrics_path) as f:
        m = json.load(f)
    # Parse scheduler and seed from directory name (e.g., "heft_s3")
    parts = metrics_path.parent.name.rsplit("_s", 1)
    rows.append({
        "scheduler": parts[0],
        "seed": int(parts[1]),
        "makespan": m["makespan"],
        "total_events": m["total_events"],
        "status": m["status"],
    })

df = pd.DataFrame(rows)

# Summary statistics per scheduler
summary = df.groupby("scheduler")["makespan"].agg(["mean", "std", "min", "max"])
print(summary.to_string())
```

Example output:

```
              mean       std    min     max
scheduler
cpop         3.210     0.015  3.190   3.230
heft         3.501     0.000  3.501   3.501
round_robin  4.002     0.003  3.998   4.005
```

---

## Parameter Sweeps

### Interference radius sweep

Explore how proximity interference radius affects makespan:

```bash
for radius in 5 10 15 20 25 30 40 50; do
  ncsim --scenario scenarios/interference_test.yaml \
        --output "output/radius_sweep/r${radius}" \
        --interference proximity \
        --interference-radius "$radius"
done
```

### WiFi parameter sweep

Vary transmit power and path loss exponent with the Bianchi model:

```bash
for tx in 10 15 20 25; do
  for n in 2.0 2.5 3.0 3.5 4.0; do
    ncsim --scenario scenarios/wifi_test.yaml \
          --output "output/wifi_sweep/tx${tx}_n${n}" \
          --interference csma_bianchi \
          --tx-power "$tx" \
          --path-loss-exponent "$n"
  done
done
```

### WiFi frequency and standard sweep

Compare WiFi standards across frequency bands:

```bash
for std in n ac ax; do
  for freq in 2.4 5.0; do
    ncsim --scenario scenarios/wifi_test.yaml \
          --output "output/wifi_std/${std}_${freq}ghz" \
          --interference csma_bianchi \
          --wifi-standard "$std" \
          --freq "$freq"
  done
done
```

### Scheduler comparison across scenarios

Run every scheduler on every scenario:

```python
import subprocess
import itertools
from pathlib import Path

scenario_dir = Path("scenarios")
scenarios = [p.stem for p in scenario_dir.glob("*.yaml")]
schedulers = ["heft", "cpop", "round_robin"]
seeds = range(1, 11)  # 10 seeds for statistical significance

for scen, sched, seed in itertools.product(scenarios, schedulers, seeds):
    output_dir = f"output/full_sweep/{scen}/{sched}/s{seed}"
    subprocess.run([
        "ncsim",
        "--scenario", f"scenarios/{scen}.yaml",
        "--output", output_dir,
        "--scheduler", sched,
        "--seed", str(seed),
    ], check=True)
```

---

## Organizing Output

### Recommended directory structure

Use a hierarchical structure that groups by experiment, then by varying
parameter:

```
output/
  scheduler_comparison/
    heft_s1/
      scenario.yaml
      trace.jsonl
      metrics.json
    heft_s2/
    ...
    cpop_s1/
    ...
  radius_sweep/
    r5/
    r10/
    r15/
    ...
  wifi_sweep/
    tx10_n2.0/
    tx10_n2.5/
    ...
```

### Best practices

!!! info "Naming conventions"
    - Include the varying parameter(s) in directory names (e.g., `heft_s42`,
      `r25`, `tx15_n3.0`).
    - Use underscores as separators. Avoid spaces in directory names.
    - Prefix seed values with `s` for clarity (e.g., `s1`, `s42`).

!!! info "Version control"
    - Add `output/` to your `.gitignore`. Trace files can be large.
    - The `scenario.yaml` copy in each output folder ensures reproducibility
      even if the original scenario file changes.
    - For important results, archive the entire output folder (e.g., as a
      `.tar.gz`).

!!! info "Disk usage"
    - Each run produces a `trace.jsonl` file whose size is proportional to the
      number of events. A simple 2-task scenario produces roughly 1 KB; a
      scenario with hundreds of tasks can produce several MB.
    - For very large sweeps, consider deleting trace files after extracting
      metrics if you only need the summary statistics:

    ```bash
    # Keep only metrics.json from a completed sweep
    find output/sweep -name "trace.jsonl" -delete
    ```

### Collecting results into CSV

For downstream analysis or plotting, export collected metrics to CSV:

```python
import json
import csv
from pathlib import Path

rows = []
for metrics_path in Path("output/full_sweep").rglob("metrics.json"):
    with open(metrics_path) as f:
        m = json.load(f)
    parts = metrics_path.parts
    # Extract scenario, scheduler, seed from path hierarchy
    rows.append({
        "scenario": parts[-4],
        "scheduler": parts[-3],
        "seed": parts[-2],
        "makespan": m["makespan"],
        "status": m["status"],
    })

with open("output/full_sweep/results.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["scenario", "scheduler", "seed", "makespan", "status"])
    writer.writeheader()
    writer.writerows(rows)

print(f"Wrote {len(rows)} rows to results.csv")
```

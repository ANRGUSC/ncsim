# Tutorial 4: Compare Schedulers

Systematic comparison of HEFT vs CPOP vs Round Robin across multiple
scenarios, with statistical analysis using multiple seeds.

---

## What You Will Learn

- Run the same scenario with all three scheduling algorithms
- Understand scheduler strengths and weaknesses on different DAG structures
- Use multiple seeds for statistical comparison
- Analyze results across different DAG structures using Python scripts

---

## Prerequisites

- ncsim installed (`pip install -e .`)
- Three built-in scenarios available in `scenarios/`
- Python 3.12+ with the `json` and `statistics` standard library modules

---

## Step 1: Choose Test Scenarios

We will use three built-in scenarios that stress different aspects of the
scheduling problem:

| Scenario | File | Nodes | Tasks | Characteristics |
|---|---|---|---|---|
| Simple Demo | `demo_simple.yaml` | 2 | 2 | Minimal chain -- one dependency, trivial |
| Parallel Spread | `parallel_spread.yaml` | 5 | 10 | Fan-out/fan-in -- 8 parallel tasks |
| Bandwidth Contention | `bandwidth_contention.yaml` | 3 | 3 | Shared link -- contention-heavy |

!!! info "Why these three?"
    Each scenario isolates a different scheduling challenge.
    **Simple Demo** is a baseline where all schedulers should perform
    similarly. **Parallel Spread** rewards schedulers that balance load
    across heterogeneous nodes. **Bandwidth Contention** tests how
    schedulers handle shared network resources.

---

## Step 2: Run All Combinations

Run each scenario with each of the three schedulers. We use `widest_path`
routing to ensure multi-hop scenarios work correctly:

```bash
for scenario in demo_simple parallel_spread bandwidth_contention; do
  for sched in heft cpop round_robin; do
    ncsim --scenario "scenarios/${scenario}.yaml" \
          --output "results/tutorial4/${scenario}_${sched}" \
          --scheduler "$sched" \
          --routing widest_path
  done
done
```

This produces 9 output directories (3 scenarios x 3 schedulers), each
containing `metrics.json`, `trace.jsonl`, and `scenario.yaml`.

!!! tip "Check the output"
    After the loop completes, verify that all 9 directories were created:

    ```bash
    ls results/tutorial4/
    ```

    You should see directories like `demo_simple_heft`,
    `demo_simple_cpop`, `demo_simple_round_robin`, and so on.

---

## Step 3: Collect Results

Use this Python script to extract makespans from all `metrics.json` files
and build a comparison table:

```python
import json
import os

scenarios = ["demo_simple", "parallel_spread", "bandwidth_contention"]
schedulers = ["heft", "cpop", "round_robin"]
base_dir = "results/tutorial4"

# Collect makespans
results = {}
for scenario in scenarios:
    results[scenario] = {}
    for sched in schedulers:
        metrics_path = os.path.join(base_dir, f"{scenario}_{sched}", "metrics.json")
        with open(metrics_path) as f:
            metrics = json.load(f)
        results[scenario][sched] = metrics["makespan"]

# Print comparison table
print(f"{'Scenario':<25} {'HEFT':>10} {'CPOP':>10} {'Round Robin':>12} {'Winner':>12}")
print("-" * 72)
for scenario in scenarios:
    makespans = results[scenario]
    winner = min(makespans, key=makespans.get)
    print(f"{scenario:<25} {makespans['heft']:>10.3f} {makespans['cpop']:>10.3f} "
          f"{makespans['round_robin']:>12.3f} {winner:>12}")
```

Save this as `compare_schedulers.py` and run it:

```bash
python compare_schedulers.py
```

---

## Step 4: Analyze Results

### Simple Demo (2 tasks, chain)

With only two tasks and two nodes, there is very little room for
scheduling decisions. HEFT typically assigns both tasks to the faster
node to avoid transfer overhead. CPOP does the same -- the critical path
is the entire DAG, and it maps everything to the fastest processor.
Round Robin cycles tasks across nodes, potentially introducing an
unnecessary transfer.

**Expected outcome:** HEFT and CPOP produce identical makespans. Round
Robin may match them or be slightly worse.

### Parallel Spread (10 tasks, fan-out/fan-in)

This scenario has 8 independent parallel tasks between a root and a sink.
The 5 nodes have heterogeneous compute capacities (80, 90, 100, 90, 80
units/s). A good scheduler will distribute the 8 parallel tasks across
all nodes proportionally to their speeds.

- **HEFT** evaluates each task independently using Earliest Finish Time,
  spreading work across all available nodes.
- **CPOP** concentrates the critical path on the fastest node. Since the
  parallel tasks form multiple paths of equal length, the critical path
  selection may not provide an advantage.
- **Round Robin** distributes tasks cyclically without considering node
  speed or transfer costs.

**Expected outcome:** HEFT produces the best makespan by exploiting
heterogeneity. CPOP is close but may over-concentrate work. Round Robin
is the worst because it ignores node capacity differences.

### Bandwidth Contention (3 tasks, shared link)

Three tasks with pinned placement force two concurrent transfers through
a single shared link. The scheduler's choice is constrained by the
`pinned_to` fields, so all three schedulers produce identical results.

**Expected outcome:** All schedulers produce the same makespan because
the placement is fully determined by `pinned_to` constraints.

!!! note "Pinned tasks override the scheduler"
    When tasks have `pinned_to` set, the scheduler cannot change their
    placement. This scenario tests the simulation engine's bandwidth
    sharing, not the scheduler's intelligence.

### Summary Table

| Scenario | HEFT | CPOP | Round Robin | Winner |
|---|---|---|---|---|
| demo_simple | Best or tied | Best or tied | Same or worse | HEFT / CPOP |
| parallel_spread | Best | Close second | Worst | HEFT |
| bandwidth_contention | Tied | Tied | Tied | All equal |

---

## Step 5: Statistical Comparison with Multiple Seeds

A single run may not tell the full story. When shadow fading or other
stochastic elements are enabled, running with multiple seeds provides
statistical confidence. Even for deterministic scenarios, sweeping seeds
is good practice to verify consistency.

Run each scenario-scheduler combination with seeds 1 through 10:

```bash
for scenario in demo_simple parallel_spread; do
  for sched in heft cpop round_robin; do
    for seed in $(seq 1 10); do
      ncsim --scenario "scenarios/${scenario}.yaml" \
            --output "results/tutorial4/sweep/${scenario}_${sched}_s${seed}" \
            --scheduler "$sched" \
            --routing widest_path \
            --seed "$seed"
    done
  done
done
```

!!! warning "Number of runs"
    This loop produces 60 simulation runs (2 scenarios x 3 schedulers x
    10 seeds). Each run completes in under a second, so the total wall
    time is modest.

### Compute Mean and Standard Deviation

Use this script to aggregate results across seeds:

```python
import json
import os
from statistics import mean, stdev

scenarios = ["demo_simple", "parallel_spread"]
schedulers = ["heft", "cpop", "round_robin"]
seeds = range(1, 11)
base_dir = "results/tutorial4/sweep"

print(f"{'Scenario':<25} {'Scheduler':<14} {'Mean':>10} {'Std Dev':>10} {'Min':>10} {'Max':>10}")
print("-" * 82)

for scenario in scenarios:
    for sched in schedulers:
        makespans = []
        for seed in seeds:
            path = os.path.join(
                base_dir, f"{scenario}_{sched}_s{seed}", "metrics.json"
            )
            with open(path) as f:
                metrics = json.load(f)
            makespans.append(metrics["makespan"])

        avg = mean(makespans)
        sd = stdev(makespans) if len(makespans) > 1 else 0.0
        lo = min(makespans)
        hi = max(makespans)
        print(f"{scenario:<25} {sched:<14} {avg:>10.3f} {sd:>10.4f} {lo:>10.3f} {hi:>10.3f}")
    print()
```

Save this as `sweep_analysis.py` and run it:

```bash
python sweep_analysis.py
```

!!! tip "Interpreting standard deviation"
    For deterministic scenarios (no shadow fading), all seeds produce the
    same makespan, so the standard deviation is 0. When
    `shadow_fading_sigma > 0`, the standard deviation reflects how much
    the wireless environment affects performance.

---

## Step 6: Interpret the Results

### When Does HEFT Win?

HEFT is the best general-purpose scheduler. It evaluates every task on
every node and selects the placement that minimizes the Earliest Finish
Time. This makes it particularly strong when:

- The network has **heterogeneous** node capacities
- The DAG has **multiple independent paths** that can be parallelized
- Communication costs are significant and co-locating tasks helps

### When Does CPOP Win?

CPOP excels in specific conditions:

- The DAG has a **dominant critical path** (one long chain of dependent
  tasks that determines the makespan)
- One node is **significantly faster** than the others
- Running the critical path entirely on the fastest node avoids
  inter-node transfer overhead

!!! note "CPOP can underperform HEFT"
    When the DAG has multiple paths of similar length, CPOP may
    overload the fast processor with critical-path tasks while leaving
    other nodes idle. HEFT's per-task EFT evaluation avoids this
    imbalance.

### When Are They Equivalent?

HEFT and CPOP produce identical results when:

- The scenario is trivially small (1--2 tasks)
- All tasks are pinned to specific nodes (`pinned_to`)
- The network is homogeneous (all nodes have equal capacity)

### Round Robin as Baseline

Round Robin assigns tasks in cyclic order without considering compute
capacity, data dependencies, or transfer costs. It exists solely to
provide a lower bound on scheduler intelligence. In any non-trivial
scenario, HEFT and CPOP should outperform Round Robin.

---

## Summary

| Scheduler | Strengths | Weaknesses | Best For |
|---|---|---|---|
| HEFT | Communication-aware, exploits heterogeneity, parallelism | Slightly higher scheduling overhead | General-purpose default |
| CPOP | Optimizes dominant critical path, minimizes critical-path transfers | Can overload one node, ignores parallel paths | Single dominant critical path + one fast node |
| Round Robin | Simple, predictable, fast to compute | Ignores everything -- capacity, data, topology | Baseline comparisons only |

**Recommendation:** Use HEFT as the default scheduler. Switch to CPOP
only when you have a clear dominant critical path and a single fast node.
Use Round Robin exclusively as a comparison baseline.

---

## Next Steps

- **[Tutorial 5: Viz Walkthrough](tutorial-5-viz-walkthrough.md)** --
  Visualize these results in the web UI
- **[Scheduling Concepts](../concepts/scheduling.md)** -- Deep dive into
  three representative algorithms: HEFT, CPOP, and Round Robin
- **[Batch Experiments](../cli/batch-experiments.md)** -- Automate
  large-scale parameter sweeps

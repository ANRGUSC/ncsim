# Tutorial 4: Compare Schedulers

Ncsim 1.1.0 discovers the static batch scheduler catalog exposed by the installed
SAGA version. This tutorial uses SAGA 2.1.0, compares a representative set, shows
how to discover all 23 algorithms, and demonstrates scheduler-specific options.

---

## What You Will Learn

- Discover every scheduler available in the installed Ncsim/SAGA combination
- Run the same scenarios with several scheduler families
- Aggregate makespans from `metrics.json`
- Interpret ties, placement differences, and routing constraints
- Pass scheduler options from YAML and the command line
- Use seed sweeps only when the scenario contains stochastic behavior

## Prerequisites

- Ncsim installed from the repository with `pip install -e .`
- SAGA 2.1.0 installed with
  `python -m pip install "anrg-saga @ git+https://github.com/ANRGUSC/saga.git@v2.1.0"`
- Python 3.12 or later

---

## Step 1: Inspect the Scheduler Catalog

Run:

```bash
ncsim --help
```

With SAGA 2.1.0, the `--scheduler` choice contains 23 SAGA schedulers:

```text
bil, brute_force, cpop, dps, duplex, etf, fastest_node, fcp, flb,
gdl, hbmct, heft, maxmin, mct, met, minmin, msbc, mst, olb, peft,
smt, sufferage, wba
```

The base Ncsim dependency accepts SAGA 2.0.4, whose PyPI build exposes the same
catalog without `peft`. Always treat `ncsim --help` as authoritative for the
installed environment.

Ncsim also supplies two built-in choices:

| Scheduler | Purpose |
|---|---|
| `round_robin` | Cycles ready tasks across nodes without estimating compute or communication cost |
| `manual` | Uses each task's `pinned_to` value; every task must have a valid assignment |

The visualization UI obtains the same catalog from `GET /api/schedulers`, so
the CLI and browser present the installed SAGA algorithms consistently.

!!! warning "Use exhaustive methods on small problems"
    `brute_force` searches the placement space exhaustively and is intended for
    small validation cases. `smt` invokes a constraint solver. Start with the
    heuristic schedulers for larger DAGs.

---

## Step 2: Choose Scenarios and Schedulers

We will use three included scenarios:

| Scenario | File | Nodes | Tasks | What It Exercises |
|---|---|---:|---:|---|
| Simple Demo | `demo_simple.yaml` | 2 | 2 | Small chain and transfer avoidance |
| Parallel Spread | `parallel_spread.yaml` | 5 | 10 | Fan-out/fan-in placement across heterogeneous nodes |
| Bandwidth Contention | `bandwidth_contention.yaml` | 3 | 3 | Pinned placement and shared-link behavior |

Compare five representative schedulers:

| Scheduler | Idea |
|---|---|
| `heft` | Heterogeneous Earliest Finish Time |
| `cpop` | Critical Path on a Processor |
| `peft` | Predict Earliest Finish Time using an optimistic cost table |
| `minmin` | Repeatedly selects the task with the smallest minimum completion time |
| `round_robin` | Cost-unaware built-in baseline |

This is a teaching subset, not a claim that the other SAGA algorithms are less
useful. Add names from `ncsim --help` to the loop whenever your experiment calls
for a broader comparison.

---

## Step 3: Run Every Combination

Use `widest_path` so every placement in the line topology can reach its
dependencies through multi-hop routes:

```bash
for scenario in demo_simple parallel_spread bandwidth_contention; do
  for sched in heft cpop peft minmin round_robin; do
    ncsim --scenario "scenarios/${scenario}.yaml" \
          --output "results/tutorial4/${scenario}_${sched}" \
          --scheduler "$sched" \
          --routing widest_path
  done
done
```

This creates 15 output directories. Each contains `scenario.yaml`,
`trace.jsonl`, and `metrics.json`.

!!! important "Routing is part of a fair comparison"
    With `direct` routing, a scheduler may produce a placement whose dependent
    tasks have no direct link. Ncsim validates the plan and reports every
    unreachable transfer instead of silently changing the placement. Keep the
    routing mode fixed across scheduler runs.

---

## Step 4: Aggregate the Results

Save this as `compare_schedulers.py` in the repository root:

```python
import json
from pathlib import Path

scenarios = ["demo_simple", "parallel_spread", "bandwidth_contention"]
schedulers = ["heft", "cpop", "peft", "minmin", "round_robin"]
root = Path("results/tutorial4")

header = ["Scenario", *schedulers, "Winner(s)"]
widths = [24, *([13] * len(schedulers)), 28]

def row(values):
    return " ".join(str(value).ljust(width) for value, width in zip(values, widths))

print(row(header))
print("-" * (sum(widths) + len(widths) - 1))

for scenario in scenarios:
    makespans = {}
    for scheduler in schedulers:
        path = root / f"{scenario}_{scheduler}" / "metrics.json"
        metrics = json.loads(path.read_text(encoding="utf-8"))
        if metrics["status"] != "completed":
            raise RuntimeError(f"{scenario}/{scheduler}: {metrics['status']}")
        makespans[scheduler] = metrics["makespan"]

    best = min(makespans.values())
    winners = ", ".join(
        name for name, value in makespans.items() if abs(value - best) < 1e-9
    )
    values = [
        scenario,
        *(f"{makespans[name]:.6f}" for name in schedulers),
        winners,
    ]
    print(row(values))
```

Run it:

```bash
python compare_schedulers.py
```

With Ncsim 1.1.0, SAGA 2.1.0, and seed 42, the verified makespans are:

| Scenario | HEFT | CPOP | PEFT | Min-Min | Round Robin |
|---|---:|---:|---:|---:|---:|
| `demo_simple` | 3.000000 | 3.000000 | 3.000000 | 3.000000 | 5.501000 |
| `parallel_spread` | 24.246722 | 24.246722 | 24.246722 | 24.246722 | 24.764472 |
| `bandwidth_contention` | 2.020000 | 2.020000 | 2.020000 | 2.020000 | 2.020000 |

Your results should match when the scenario files, seed, routing, and dependency
versions match.

---

## Step 5: Interpret the Results

### Simple Demo

HEFT, CPOP, PEFT, and Min-Min all keep the two-task chain on `n0`, avoiding a
network transfer. Round Robin places `T1` on `n1`, adding a 50 MB transfer and
running the larger task on the slower node.

### Parallel Spread

The four SAGA heuristics produce different valid task-to-node assignments but
the same makespan in this symmetric fan-out/fan-in case. Round Robin is slightly
slower. This is an important experimental lesson: **different placements do not
necessarily produce different makespans**.

Inspect the assignments and timing rather than relying only on the final scalar:

```bash
ncsim --scenario scenarios/parallel_spread.yaml \
      --output results/tutorial4/parallel_peft_verbose \
      --scheduler peft --routing widest_path --verbose

python analyze_trace.py \
       results/tutorial4/parallel_peft_verbose/trace.jsonl --gantt --tasks
```

### Bandwidth Contention

The tasks have `pinned_to` assignments, so every scheduler receives the same
placement constraints and produces the same makespan. This scenario evaluates
execution and bandwidth sharing, not scheduler intelligence.

!!! note "A tie can be the correct result"
    Never force a ranking when the measurements tie. Report the scenario,
    routing, seed, scheduler options, and dependency versions alongside the
    result so another researcher can reproduce it.

---

## Step 6: Use Scheduler-Specific Options

Four SAGA schedulers currently expose constructor settings through Ncsim:

| Scheduler | Option | Type / Range | Default |
|---|---|---|---|
| `fcp` | `priority_queue_size` | integer >= 1 or null | library default |
| `gdl` | `dynamic_level` | `1` or `2` | `2` |
| `smt` | `epsilon` | number >= 0 | `0.001` |
| `smt` | `solver_name` | string or null | library default |
| `wba` | `alpha` | number from 0 to 1 | `0.5` |

Set options in YAML:

```yaml
config:
  scheduler: wba
  scheduler_options:
    alpha: 0.3
  routing: widest_path
  seed: 42
```

Or override them from the CLI. Repeat `--scheduler-option` for multiple values:

```bash
ncsim --scenario scenarios/parallel_spread.yaml \
      --output results/tutorial4/wba_alpha_03 \
      --scheduler wba \
      --scheduler-option alpha=0.3 \
      --routing widest_path

ncsim --scenario scenarios/parallel_spread.yaml \
      --output results/tutorial4/gdl_level_1 \
      --scheduler gdl \
      --scheduler-option dynamic_level=1 \
      --routing widest_path
```

Values use YAML scalar parsing, so numbers and booleans keep their types. If the
CLI changes the scheduler named in the scenario, Ncsim clears options belonging
to the old scheduler before applying the CLI options.

---

## Step 7: Add Seed Sweeps When They Matter

The three scenarios above are deterministic, so changing the seed does not alter
their placements or makespans. A seed sweep becomes informative when the scenario
uses a stochastic feature such as non-zero WiFi shadow fading.

For such a scenario, run multiple seeds and report a distribution:

```bash
for sched in heft cpop peft minmin; do
  for seed in $(seq 1 10); do
    ncsim --scenario scenarios/my_stochastic_wifi.yaml \
          --output "results/tutorial4/sweep/${sched}_s${seed}" \
          --scheduler "$sched" \
          --routing widest_path \
          --seed "$seed"
  done
done
```

Record the mean, standard deviation, minimum, and maximum makespan. Keep the same
seed set for every scheduler so each algorithm sees the same randomized
environment.

---

## Summary

You learned how to:

1. Discover the installed SAGA catalog and two built-in schedulers with `ncsim --help`
2. Compare a representative scheduler subset with a fixed routing mode
3. Validate run status before aggregating `metrics.json`
4. Interpret ties and placement differences instead of assuming a universal winner
5. Configure FCP, GDL, SMT, and WBA through `scheduler_options`
6. Reserve seed sweeps for scenarios with stochastic inputs

## Next Steps

- **[Tutorial 5: Viz Walkthrough](tutorial-5-viz-walkthrough.md)** -- compare
  scheduler choices and options in the web UI
- **[Scheduling Concepts](../concepts/scheduling.md)** -- scheduler design and
  placement concepts
- **[Batch Experiments](../cli/batch-experiments.md)** -- larger experiment sweeps

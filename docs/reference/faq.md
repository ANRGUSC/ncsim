# FAQ

Frequently asked questions about ncsim, organized by topic.

---

## General

**Q: What is ncsim?**

A: ncsim is a headless discrete-event simulator for evaluating task
scheduling algorithms on heterogeneous networked computing systems. It
models compute nodes with different capacities, network links with
bandwidth sharing and WiFi interference, and DAG-structured task graphs
with data dependencies.

---

**Q: Who develops ncsim?**

A: ncsim is developed by the Autonomous Networks Research Group (ANRG) at
the University of Southern California. Contributors: Bhaskar
Krishnamachari, Maya Gutierrez, Jared Coleman.

---

**Q: Is ncsim free to use?**

A: Yes. ncsim is open source under the MIT license. You can use,
modify, and distribute it freely.

---

**Q: What Python version is required?**

A: Python 3.12 or later. Check your version with `python --version`.

---

**Q: How do I cite ncsim?**

A: Cite the [ncsim paper](https://arxiv.org/abs/2605.01094) and the
[versioned software release](https://doi.org/10.5281/zenodo.19138224).
The `CITATION.cff` file in the repository root provides machine-readable
citation metadata.

---

## Simulation

**Q: Is the simulation deterministic?**

A: Yes. Given the same inputs (scenario YAML) and the same seed
(`--seed`), ncsim produces identical event sequences and results every
time. This determinism is guaranteed by:

- Microsecond time precision (6 decimal places) to prevent
  floating-point drift
- Deterministic event ordering via `(time, priority, insertion_id)`
  tuples in the priority queue
- Seeded random number generation for stochastic elements like shadow
  fading

!!! tip "Verify determinism"
    Run the same scenario twice with the same seed and diff the traces:

    ```bash
    ncsim --scenario scenarios/demo_simple.yaml --output out/a --seed 42
    ncsim --scenario scenarios/demo_simple.yaml --output out/b --seed 42
    diff out/a/trace.jsonl out/b/trace.jsonl
    ```

    The diff should produce no output.

---

**Q: What does "makespan" mean?**

A: Makespan is the total simulation time from the start of the first
task to the completion of the last task. It is the primary performance
metric for comparing scheduling algorithms. Lower is better.

---

**Q: Can I simulate multiple DAGs?**

A: Yes. The YAML format supports multiple DAGs under the `dags:` section.
Each DAG has its own `inject_at` time, allowing you to model workflows
that arrive at different points during the simulation.

```yaml
dags:
  - id: dag_1
    inject_at: 0.0
    tasks: [...]
    edges: [...]
  - id: dag_2
    inject_at: 5.0
    tasks: [...]
    edges: [...]
```

---

**Q: What units are used throughout ncsim?**

A: All units are consistent across the simulator:

| Quantity | Unit |
|---|---|
| Compute capacity | units per second |
| Compute cost | units (runtime = cost / capacity) |
| Bandwidth | MB/s |
| Latency | seconds |
| Data size | MB |
| Positions | meters (x, y coordinates) |
| Makespan / duration | seconds |
| Transmit power | dBm |
| Frequency | GHz |
| Noise floor | dBm |
| CCA threshold | dBm |

---

**Q: How does bandwidth sharing work?**

A: When N data transfers share a single link simultaneously, each
transfer receives `bandwidth / N` of the link's effective bandwidth.
Transfer completion times are recalculated dynamically whenever a new
transfer starts or an existing transfer completes on the same link.

For example, on a 100 MB/s link:

- 1 transfer: 100 MB/s each
- 2 concurrent transfers: 50 MB/s each
- 3 concurrent transfers: 33.3 MB/s each

This fair-sharing model stacks with the interference factor:

```
effective_bw_per_flow = (base_bandwidth * interference_factor) / num_flows
```

---

**Q: What happens when a task has no predecessors?**

A: Tasks with no incoming edges are considered entry tasks. They become
ready for execution as soon as their DAG is injected (at the `inject_at`
time). If the assigned node is idle, execution starts immediately.

---

## Scheduling

**Q: Which scheduler should I use?**

A: Use **HEFT** as the default general-purpose scheduler. ncsim also
registers 21 other SAGA algorithms with SAGA 2.0.4, optional PEFT with
SAGA 2.1.0, and two built-in schedulers:

| Situation | Recommended Scheduler |
|---|---|
| General purpose | HEFT |
| Dominant critical path + one fast node | CPOP |
| Baseline comparison | Round Robin |
| Controlled experiment with fixed placement | Manual (`pinned_to`) |

See the [Scheduling Concepts](../concepts/scheduling.md) page for a
detailed comparison.

---

**Q: What does `pinned_to` do?**

A: The `pinned_to` field in a task definition forces that task to run on
a specific node, overriding the scheduler's placement decision. It works
with all schedulers:

```yaml
tasks:
  - id: T0
    compute_cost: 100
    pinned_to: n0    # Always runs on n0, regardless of scheduler
```

This is useful for controlled experiments where you want to test a
specific placement, or for modeling tasks that must run on particular
hardware.

---

**Q: What happens if anrg-saga is not installed?**

A: If `anrg-saga` is unavailable or incompatible, ncsim exposes only the
built-in `round_robin` and `manual` schedulers. It does not silently replace a
requested SAGA algorithm; a scenario that requests one fails with a clear
error. Install SAGA 2.0.4 or later to restore the SAGA registry:

```bash
pip install "anrg-saga>=2.0.4"
```

If `peft` is missing, install the tagged SAGA 2.1.0 source:

```bash
pip install "anrg-saga @ git+https://github.com/ANRGUSC/saga.git@v2.1.0"
```

---

## WiFi and Interference

**Q: When should I use `csma_bianchi` vs `csma_clique`?**

A: Choose based on the level of realism you need:

| Model | Realism | Dynamic | Best For |
|---|---|---|---|
| `csma_bianchi` | High | Yes (recalculates per transfer) | Research-quality results, realistic WiFi |
| `csma_clique` | Medium | No (static worst-case) | Quick WiFi-aware approximation |

`csma_bianchi` is more realistic because it dynamically separates
contention domain time-sharing (Bianchi MAC efficiency) from hidden
terminal SINR degradation. `csma_clique` applies a static worst-case
bandwidth reduction based on the maximum clique size.

!!! info "Performance consideration"
    `csma_bianchi` recalculates interference factors whenever any
    transfer starts or completes, which adds computational overhead for
    large networks. `csma_clique` computes bandwidth once at setup time
    and never recalculates.

---

**Q: What happens if WiFi links have no explicit bandwidth?**

A: When using `csma_clique` or `csma_bianchi`, links without a
`bandwidth` field in the YAML derive their data rate from the RF model:

1. Node positions determine distance
2. Distance determines path loss
3. Path loss determines received power and SNR
4. SNR selects the highest viable MCS rate
5. MCS rate becomes the link's PHY bandwidth (in MB/s)

This allows you to define a topology with only positions and RF
parameters, and let the WiFi model compute realistic bandwidths
automatically.

---

**Q: Can I mix wired and wireless links?**

A: Yes. Links with an explicit `bandwidth` field in the YAML keep their
specified value -- the WiFi model does not overwrite it. Links without
a `bandwidth` field use the WiFi-derived rate. This allows you to model
mixed wired/wireless scenarios:

```yaml
links:
  - id: ethernet_link
    from: server
    to: switch
    bandwidth: 1000    # 1 GB/s wired -- kept as-is
    latency: 0.0001
  - id: wifi_link
    from: switch
    to: laptop
    latency: 0.001
    # No bandwidth -- derived from RF model
```

---

**Q: What is the conflict graph?**

A: The conflict graph determines which links cannot transmit
simultaneously under the CSMA/CA protocol. Two links conflict if one
transmitter's signal is strong enough to trigger the other's carrier
sensing mechanism. The maximum clique size in this graph determines
worst-case contention. See the
[WiFi Model](../concepts/wifi-model.md) page for details.

---

**Q: Does RTS/CTS change the results?**

A: Yes. Enabling RTS/CTS (`--rts-cts` flag) extends the conflict zone
to protect receivers, not just transmitters. This increases the number
of conflicting links (larger cliques) but reduces hidden terminal
problems. The net effect depends on the topology -- in some cases
RTS/CTS improves throughput by preventing hidden terminal interference;
in others it reduces throughput by increasing contention.

---

## Visualization

**Q: Do I need the viz to use ncsim?**

A: No. The CLI (`ncsim` command) is fully self-contained. It reads a
scenario YAML, runs the simulation, and writes `trace.jsonl`,
`metrics.json`, and a copy of the scenario to the output directory. The
viz is an optional tool for interactive configuration, visual analysis,
and animated replay.

---

**Q: Can I use the viz without the backend?**

A: Partially. The "Visualize Existing" mode can load pre-generated
sample runs from `viz/public/sample-runs/` without the backend if the
files are served as static assets. However, the experiment list API
(`/api/experiments`) requires the backend, and "Configure & Run" mode
always requires the backend to execute simulations.

---

**Q: What browsers are supported?**

A: ncsim-viz is tested on modern versions of Chrome, Firefox, Safari,
and Edge. It requires JavaScript enabled and works best with hardware
acceleration for the D3 visualizations.

---

**Q: Can I export visualizations as images?**

A: The current version does not have a built-in export feature. You can
use your browser's screenshot tools or the developer console to capture
visualizations. The Gantt chart and network graph are rendered as SVG
elements that can be extracted.

---

## Output Files

**Q: What files does each simulation run produce?**

A: Every run writes three files to the `--output` directory:

| File | Format | Contents |
|---|---|---|
| `scenario.yaml` | YAML | Copy of the input scenario (for reproducibility) |
| `trace.jsonl` | JSON Lines | Every simulation event, one JSON object per line |
| `metrics.json` | JSON | Summary metrics: makespan, utilization, counts |

See the [Output Files](../cli/output-files.md) reference for detailed
field descriptions.

---

**Q: Can I load trace files from the CLI into the viz?**

A: Yes. Copy the output directory (containing `scenario.yaml`,
`trace.jsonl`, and `metrics.json`) into `viz/public/sample-runs/` and
it will appear in the experiment browser. You can also use the file
loader to upload individual files directly.

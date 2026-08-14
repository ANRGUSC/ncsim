# CLI Reference

ncsim provides a command-line interface for running discrete-event simulations of
networked computing systems. All simulation parameters can be controlled through
CLI flags, which override values set in the scenario YAML file.

---

## Command Syntax

```
ncsim --scenario PATH --output DIR [options]
```

Alternatively, run as a Python module:

```
python -m ncsim --scenario PATH --output DIR [options]
```

---

## Complete Flag Reference

| Flag | Type | Default | Description |
|---|---|---|---|
| `--scenario` | path | **required** | Path to scenario YAML file |
| `--output` | path | **required** | Output directory for trace and metrics |
| `--seed` | int | from YAML (`42`) | Random seed for reproducibility |
| `--scheduler` | choice | from YAML (`heft`) | Registered SAGA static batch scheduler, `round_robin`, or `manual` |
| `--scheduler-option KEY=VALUE` | repeatable | from YAML | Override a scheduler constructor option; YAML scalar types are accepted |
| `--routing` | choice | from YAML (`direct`) | Routing algorithm: `direct`, `widest_path`, or `shortest_path` |
| `--interference` | choice | from YAML (`proximity`) | Interference model: `none`, `proximity`, `csma_clique`, or `csma_bianchi` |
| `--interference-radius` | float | `15.0` | Radius in meters for the proximity interference model |
| `--tx-power` | float | `20` | WiFi transmit power in dBm |
| `--freq` | float | `5.0` | WiFi carrier frequency in GHz |
| `--path-loss-exponent` | float | `3.0` | Path loss exponent for the log-distance model |
| `--wifi-standard` | choice | `ax` | WiFi standard for MCS rate tables: `n`, `ac`, or `ax` |
| `--rts-cts` | flag | off | Enable RTS/CTS handshake (extends conflict graph to protect receivers) |
| `--verbose`, `-v` | flag | off | Enable verbose/debug logging |
| `--version` | flag | -- | Print version string and exit |

---

## Override Precedence

Parameters are resolved in the following order, where later sources take priority:

```
Built-in defaults  <  Scenario YAML config  <  CLI flags
```

!!! info "How overrides work"
    If you specify `--scheduler cpop` on the command line, it overrides whatever
    `scheduler:` value is set in the scenario YAML file. If you omit a CLI flag,
    the value from the YAML file is used. If the YAML file also omits it, the
    built-in default applies.

    Scheduler options are merged over `config.scheduler_options`. If
    `--scheduler` changes the scheduler, options belonging to the previous
    scheduler are cleared before CLI options are applied.

---

## Example Commands

### 1. Basic run

Run a scenario with all defaults taken from the YAML file:

```bash
ncsim --scenario scenarios/demo_simple.yaml --output output/basic
```

### 2. Override scheduler and routing

Use CPOP scheduling with widest-path routing:

```bash
ncsim --scenario scenarios/parallel_spread.yaml \
      --output output/cpop_widest \
      --scheduler cpop \
      --routing widest_path
```

### 3. Disable interference

Run with no inter-link interference modeling:

```bash
ncsim --scenario scenarios/demo_simple.yaml \
      --output output/no_interference \
      --interference none
```

### 4. Configure a SAGA scheduler

Run WBA with a non-default tradeoff weight:

```bash
ncsim --scenario scenarios/demo_simple.yaml \
      --output output/wba \
      --scheduler wba \
      --scheduler-option alpha=0.75
```

The repeatable option flag is available for FCP (`priority_queue_size`), GDL
(`dynamic_level`), SMT (`epsilon`, `solver_name`), and WBA (`alpha`). Other
registered schedulers use their SAGA defaults and accept no options.

### 5. Custom interference radius with verbose logging

Set a 25-meter proximity interference radius and enable debug output:

```bash
ncsim --scenario scenarios/interference_test.yaml \
      --output output/radius25 \
      --interference proximity \
      --interference-radius 25.0 \
      --verbose
```

### 6. WiFi with Bianchi CSMA/CA model

Use the analytical Bianchi model for CSMA/CA contention:

```bash
ncsim --scenario scenarios/wifi_test.yaml \
      --output output/bianchi \
      --interference csma_bianchi
```

### 7. WiFi with static clique model

Use the max-clique static throughput division model:

```bash
ncsim --scenario scenarios/wifi_clique_test.yaml \
      --output output/clique \
      --interference csma_clique
```

### 8. Override WiFi RF parameters

Customize transmit power, frequency, and path loss exponent:

```bash
ncsim --scenario scenarios/wifi_test.yaml \
      --output output/custom_rf \
      --interference csma_bianchi \
      --tx-power 15 \
      --freq 2.4 \
      --path-loss-exponent 2.5 \
      --wifi-standard n
```

### 9. Enable RTS/CTS

Enable the RTS/CTS handshake to extend the conflict graph and protect
receivers from hidden-node interference:

```bash
ncsim --scenario scenarios/wifi_test.yaml \
      --output output/rts_cts \
      --interference csma_bianchi \
      --rts-cts
```

### 10. Determinism check

Run the same scenario twice with the same seed and verify that the output
traces are identical:

```bash
ncsim --scenario scenarios/demo_simple.yaml \
      --output output/run_a --seed 123

ncsim --scenario scenarios/demo_simple.yaml \
      --output output/run_b --seed 123

diff output/run_a/trace.jsonl output/run_b/trace.jsonl
```

!!! tip "Reproducibility"
    Two runs with the same `--seed`, the same scenario YAML, and the same CLI
    flags will always produce byte-identical `trace.jsonl` files. This makes it
    straightforward to verify that code changes do not alter simulation behavior.

---

## Exit Codes

| Code | Meaning |
|---|---|
| `0` | Simulation completed successfully |
| `1` | Error (file not found, invalid scenario, simulation error, or unexpected exception) |

---

## Logging

By default, ncsim logs at the `INFO` level. Use `--verbose` (or `-v`) to enable
`DEBUG` level output, which includes detailed information about scheduler
decisions, routing paths, interference calculations, and per-link PHY rates.

Log output is written to stderr with timestamps:

```
12:34:56 [INFO] Loading scenario: scenarios/demo_simple.yaml
12:34:56 [INFO] Scenario 'Simple Demo' loaded: 2 nodes, 1 links, 1 DAG(s)
12:34:56 [INFO] Creating routing model: direct
12:34:56 [INFO] Interference model: none
12:34:56 [INFO] Creating scheduler: heft
12:34:56 [INFO] Running simulation...
12:34:56 [INFO] Trace written to: output/basic/trace.jsonl
12:34:56 [INFO] Metrics written to: output/basic/metrics.json
```

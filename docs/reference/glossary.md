# Glossary

Alphabetical reference of key terms used throughout the ncsim
documentation and codebase.

---

## B

**Bandwidth**
:   Data transfer rate of a network link, measured in MB/s. When
    multiple transfers share a link, each receives an equal fraction of
    the available bandwidth. Bandwidth may be reduced by interference
    models.

**Bianchi Model**
:   Analytical model for IEEE 802.11 DCF MAC throughput, derived by
    Giuseppe Bianchi (2000). Computes the MAC efficiency `eta(n)` for
    `n` contending stations by solving coupled equations for
    transmission probability and collision probability. Used by the
    `csma_bianchi` interference model.

## C

**CCA (Clear Channel Assessment)**
:   Mechanism by which a WiFi node determines whether the wireless
    channel is currently busy. A node detects the channel as busy when
    the received signal power exceeds the CCA threshold (default:
    -82 dBm). CCA determines the carrier sensing range and therefore
    the conflict graph.

**Clique**
:   A set of nodes (links) in the conflict graph where every pair is
    connected by an edge -- meaning every pair conflicts. The maximum
    clique size containing a given link determines the worst-case
    number of contenders. Used by both `csma_clique` and `csma_bianchi`
    interference models.

**Compute Capacity**
:   Processing speed of a node, measured in compute units per second.
    A node with capacity 100 completes a task with cost 200 in
    `200 / 100 = 2.0` seconds.

**Compute Cost**
:   Total work required by a task, measured in compute units. The
    runtime on a given node is `compute_cost / compute_capacity`.

**Conflict Graph**
:   An undirected graph where vertices represent network links and
    edges connect pairs of links that cannot transmit simultaneously
    due to carrier sensing. Built from node positions and RF parameters.
    The conflict graph is used by both `csma_clique` and `csma_bianchi`
    interference models to determine contention relationships.

**CPOP (Critical Path on a Processor)**
:   A list-scheduling algorithm that identifies the DAG's critical path
    and assigns all critical-path tasks to the single processor that
    minimizes their total execution time. Non-critical tasks are assigned
    using the Earliest Finish Time heuristic. Implemented via the
    `anrg-saga` library.

## D

**DAG (Directed Acyclic Graph)**
:   A task dependency graph where vertices represent tasks and directed
    edges represent data dependencies. A task cannot start until all its
    predecessor tasks have completed and all required data transfers have
    finished. ncsim supports multiple DAGs injected at different times.

**DES (Discrete Event Simulation)**
:   A simulation paradigm where the system state changes only at
    discrete time points called events. Between events, the system state
    is constant. ncsim uses DES with a priority queue to process events
    in chronological order.

## E

**EFT (Earliest Finish Time)**
:   The earliest time at which a task can complete on a given node,
    accounting for the task's computation time, all required data
    transfer times from predecessor tasks, and the node's current
    availability. Used by HEFT and CPOP for node selection.

**Event Queue**
:   A priority queue that orders simulation events by a tuple of
    `(time, priority, insertion_id)`. The time determines chronological
    order. The priority breaks ties between events at the same time.
    The insertion ID breaks remaining ties to ensure deterministic,
    stable ordering.

## H

**HEFT (Heterogeneous Earliest Finish Time)**
:   The default scheduling algorithm in ncsim. A list-scheduling
    heuristic that sorts tasks by decreasing upward rank and assigns
    each task to the node that minimizes the Earliest Finish Time.
    Communication-aware and heterogeneity-aware. Implemented via the
    `anrg-saga` library.

**Hidden Terminal**
:   A transmitter that is outside the carrier sensing range of another
    transmitter but whose signal can still cause interference at the
    other link's receiver. Hidden terminals affect SINR but are not
    prevented by CSMA. The `csma_bianchi` model explicitly accounts for
    hidden terminal degradation.

## I

**Interference Factor**
:   A multiplicative factor in the range (0, 1] applied to a link's
    base bandwidth due to wireless interference from other active links.
    An interference factor of 0.5 means the link operates at half its
    nominal bandwidth. The factor is computed by the active interference
    model and stacks with per-link fair sharing.

## L

**Latency**
:   Propagation delay on a network link, measured in seconds. For
    multi-hop routes, latencies are summed across all hops
    (store-and-forward model). Total transfer time is
    `(data_size / bandwidth) + latency`.

**Link**
:   A directed communication channel between two nodes. Defined by a
    source node (`from`), destination node (`to`), bandwidth (MB/s),
    and latency (seconds). Multiple concurrent transfers on the same
    link share its bandwidth equally.

## M

**Makespan**
:   Total time from the start of the first task to the completion of the
    last task across all DAGs. The primary performance metric for
    comparing scheduling algorithms and configurations. Lower makespan
    indicates better performance.

**MCS (Modulation and Coding Scheme)**
:   A WiFi PHY layer encoding that determines the data rate achievable
    at a given SNR level. Higher MCS indices use denser modulation
    (e.g., 256-QAM, 1024-QAM) for higher rates but require stronger
    signals. ncsim includes MCS tables for 802.11n, 802.11ac, and
    802.11ax.

**Metrics**
:   Summary statistics written to `metrics.json` after each simulation
    run. Includes makespan, total task and transfer counts, per-node
    utilization, per-link utilization, and (for WiFi models) RF
    configuration details and PHY rates.

**Multi-hop**
:   Routing data through one or more intermediate relay nodes when no
    direct link exists between the source and destination. Enabled by
    `widest_path` or `shortest_path` routing. Intermediate nodes act
    as store-and-forward relays.

## N

**Node**
:   A compute resource in the network. Each node has an ID, a compute
    capacity (units/second), and optionally a position (x, y in meters).
    Tasks are scheduled onto nodes by the scheduling algorithm.

## P

**Path Loss**
:   Signal attenuation as a function of distance. ncsim uses the
    log-distance path loss model with a Friis free-space reference at
    1 meter: `PL(d) = PL(d0) + 10 * n * log10(d / d0)`, where `n` is
    the path loss exponent.

**PHY Rate**
:   Physical layer data rate determined by MCS selection based on the
    received SNR (or SINR under interference). Measured in Mbps and
    converted to MB/s internally (`rate_MBps = rate_Mbps / 8`). Scales
    linearly with channel width.

**Placement Plan**
:   The output of a scheduling algorithm: a mapping from every task ID
    to a node ID. The placement plan determines where each task will
    execute. The execution engine then determines when each task runs
    based on event ordering and node availability.

**Position**
:   Physical location of a node as an `(x, y)` coordinate pair in
    meters. Used for interference calculations (distance-based path
    loss, carrier sensing range) and for node placement in the
    visualization.

## R

**RTS/CTS (Request to Send / Clear to Send)**
:   An optional 802.11 handshake protocol that extends the conflict
    graph to protect receivers, not just transmitters. When enabled
    (`--rts-cts`), any node of link A sensing any node of link B causes
    a conflict. This reduces hidden terminal problems but increases
    contention.

## S

**Scenario**
:   A complete simulation specification in YAML format. Contains the
    network definition (nodes and links), one or more DAGs (tasks and
    edges), and configuration options (scheduler, routing, interference,
    seed, RF parameters).

**Seed**
:   A random seed integer for deterministic simulation reproducibility.
    The same scenario with the same seed always produces identical
    results. Set via `--seed` on the CLI or `seed:` in the YAML config.

**Shadow Fading**
:   Random signal variation modeled as a log-normal distribution
    `N(0, sigma)` in the dB domain. Each node pair receives a
    deterministic fading value (symmetric and seeded). Configured via
    `shadow_fading_sigma` (default: 0.0, meaning no fading).

**SINR (Signal-to-Interference-plus-Noise Ratio)**
:   The ratio of desired signal power to the sum of interference power
    and noise power, measured in dB. Determines the achievable data rate
    under interference from hidden terminals. Lower SINR may force a
    lower MCS selection and reduced throughput.

**SNR (Signal-to-Noise Ratio)**
:   The ratio of received signal power to noise floor power, measured in
    dB: `SNR = Prx - N0`. Determines the achievable data rate in the
    absence of interference. Used for MCS rate selection.

## T

**Task**
:   A unit of computation with a compute cost, scheduled onto a node by
    the scheduling algorithm. Tasks may have data dependencies (edges in
    the DAG) that require transfers to complete before execution can
    begin.

**Trace**
:   The event log written to `trace.jsonl` after each simulation run.
    Contains one JSON object per line, recording every discrete event in
    chronological order. Events include simulation start/end, DAG
    injection, task scheduling/start/completion, and transfer
    start/completion.

## U

**Upward Rank**
:   A metric used by HEFT to prioritize tasks. Defined as the longest
    path (by computation + communication cost) from a task to any exit
    task in the DAG. Tasks with higher upward rank are scheduled first,
    ensuring that critical-path tasks receive priority.

**Utilization**
:   The fraction of the makespan during which a resource (node or link)
    was actively working. Node utilization measures compute time; link
    utilization measures transfer time. Reported as a value between 0.0
    (idle) and 1.0 (fully utilized) in `metrics.json`.

## W

**Widest Path**
:   A routing strategy that finds the path between two nodes that
    maximizes the bottleneck (minimum) bandwidth along the path. Uses a
    modified Dijkstra algorithm with a max-heap. Optimal for large data
    transfers where bandwidth dominates transfer time.

## Y

**YAML**
:   YAML Ain't Markup Language. A human-readable data serialization
    format used for ncsim scenario files. Scenario YAML files define the
    network topology, DAG task graphs, and simulation configuration. See
    the [YAML Reference](../scenarios/yaml-reference.md) for the
    complete format specification.

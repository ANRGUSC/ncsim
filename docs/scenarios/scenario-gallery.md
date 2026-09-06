# Scenario Gallery

This page documents all 10 built-in scenarios included in the `scenarios/` directory. Each entry describes the topology, DAG structure, expected behavior, and includes the full YAML source.

---

## 1. demo_simple.yaml

**Minimal two-node scenario for basic testing.**

- **Nodes:** 2 -- n0 (100 cu/s), n1 (50 cu/s)
- **Links:** 1 -- n0 to n1 at 100 MB/s, 1 ms latency
- **Tasks:** 2 -- T0 (100 cu), T1 (200 cu)
- **Edges:** T0 to T1, 50 MB transfer
- **Scheduler:** HEFT

!!! info "Expected behavior"
    HEFT assigns both tasks to n0 (faster node). T0 runs from 0 to 1.0 s, the 50 MB transfer over the 100 MB/s link takes 0.5 s + 0.001 s latency = 0.501 s (from 1.0 to 1.501 s), and T1 runs from 1.501 to 3.501 s. **Makespan: 3.501 s.**

```yaml
# Demo Simple Scenario
# Two nodes, one link, simple 2-task DAG
# Expected (HEFT assigns both to n0): T0 runs 0->1s, transfer 1->1.501s, T1 runs 1.501->3.501s
# Makespan: 3.501

scenario:
  name: "Simple Demo"

  network:
    nodes:
      - id: n0
        compute_capacity: 100
        position: {x: 0, y: 0}
      - id: n1
        compute_capacity: 50
        position: {x: 10, y: 0}
    links:
      - id: l01
        from: n0
        to: n1
        bandwidth: 100
        latency: 0.001

  dags:
    - id: dag_1
      inject_at: 0.0
      tasks:
        - id: T0
          compute_cost: 100
        - id: T1
          compute_cost: 200
      edges:
        - from: T0
          to: T1
          data_size: 50

  config:
    scheduler: heft
    seed: 42
```

---

## 2. bandwidth_contention.yaml

**Tests concurrent transfers sharing a single link.**

- **Nodes:** 3 -- n0, n1, n2 (all 1000 cu/s)
- **Links:** 1 -- n0 to n2 at 100 MB/s, 0 latency
- **Tasks:** 3 pinned -- T0 on n0, T1 on n0, T2 on n2
- **Edges:** T0 to T2 (100 MB), T1 to T2 (100 MB)
- **Scheduler:** round_robin

!!! info "Expected behavior"
    Both T0 and T1 complete in 0.01 s on n0 (10 cu / 1000 cu/s). Both then transfer 100 MB to T2 on n2 simultaneously over the shared 100 MB/s link. With fair sharing, each transfer gets 50 MB/s and takes 2.0 s. T2 starts after both arrive and runs 0.01 s. **Makespan: ~2.02 s.**

```yaml
# Bandwidth Contention Test Scenario
# Tests that two concurrent transfers SHARE bandwidth correctly
#
# Topology:  n0 --\
#                  >-- l_shared --> n2
#            n1 --/
#
# Both T0->T2 and T1->T2 must go through the shared link.
# Each transfer is 100 MB. Link is 100 MB/s.
# - If sequential: 1 second each = 2 seconds total
# - If concurrent with sharing: each gets 50 MB/s = 2 seconds each (parallel)
# Expected makespan: ~2.02 seconds (0.01 compute + 2.0 transfer + 0.01 compute)

scenario:
  name: "Bandwidth Contention Test"

  network:
    nodes:
      - id: n0
        compute_capacity: 1000  # Very fast to minimize compute time
        position: {x: 0, y: 0}
      - id: n1
        compute_capacity: 1000
        position: {x: 0, y: 10}
      - id: n2
        compute_capacity: 1000
        position: {x: 20, y: 5}
    links:
      # Single shared link - both transfers must use this
      # In reality this models a bottleneck (e.g., shared uplink to n2)
      - id: l_shared
        from: n0
        to: n2
        bandwidth: 100
        latency: 0.0
      # n1 also connects to n2 through the same logical bottleneck
      # For now, we route n1->n2 through n0 conceptually,
      # but since we only have direct links, we need n1->n0->n2
      # Actually, let's make n1 send to n0, and n0 sends to n2
      # This way both T0->T2 and T1->T2 go through l_shared

  dags:
    - id: dag_1
      inject_at: 0.0
      tasks:
        - id: T0
          compute_cost: 10  # 0.01 seconds
          pinned_to: n0
        - id: T1
          compute_cost: 10  # 0.01 seconds
          pinned_to: n0     # CHANGED: T1 also on n0 so both outputs use same link
        - id: T2
          compute_cost: 10  # 0.01 seconds
          pinned_to: n2
      edges:
        # 100 MB each on 100 MB/s link
        # When concurrent, each gets 50 MB/s = 2 seconds each
        - from: T0
          to: T2
          data_size: 100
        - from: T1
          to: T2
          data_size: 100

  config:
    scheduler: round_robin
    seed: 42
```

---

## 3. interference_test.yaml

**Tests wireless interference on parallel links in a square grid.**

- **Nodes:** 4 in a square -- n0 (0,0), n1 (5,0), n2 (0,5), n3 (5,5), all 1000 cu/s
- **Links:** 2 parallel -- l01 (n0 to n1), l23 (n2 to n3), both 100 MB/s
- **Tasks:** 4 pinned -- T0 on n0, T1 on n1, T2 on n2, T3 on n3
- **Edges:** T0 to T1 (100 MB), T2 to T3 (100 MB)
- **Scheduler:** round_robin

!!! info "Expected behavior"
    **Without interference** (`interference: none`): each transfer uses the full 100 MB/s. Transfer time = 1.0 s. Makespan: **1.02 s** (0.01 s compute + 1.0 s transfer + 0.01 s compute).

    **With proximity interference** (`interference: proximity`, `interference_radius: 10`): link midpoints are 5.0 m apart, within the 10 m radius. Both links interfere (k=2), each gets 50 MB/s. Transfer time = 2.0 s. Makespan: **2.02 s.**

```yaml
# Interference Test Scenario
# Tests that two parallel transfers on NEARBY links experience interference
#
# Topology:
#   n0 (0,0) ---l01---> n1 (5,0)
#   n2 (0,5) ---l23---> n3 (5,5)
#
# l01 midpoint: (2.5, 0), l23 midpoint: (2.5, 5)
# Distance between midpoints: 5.0
#
# With interference_radius=10:
#   Both links interfere (distance 5.0 < 10.0), k=2
#   Each link gets bandwidth/2 = 50 MB/s
#
# Without interference (or interference=none):
#   T0 (0.01s) -> transfer l01 (100/100 = 1.0s) -> T1 (0.01s)
#   T2 (0.01s) -> transfer l23 (100/100 = 1.0s) -> T3 (0.01s)
#   Makespan: 1.02s
#
# With proximity interference (radius=10):
#   T0 (0.01s) -> transfer l01 (100/50 = 2.0s) -> T1 (0.01s)
#   T2 (0.01s) -> transfer l23 (100/50 = 2.0s) -> T3 (0.01s)
#   Makespan: 2.02s (transfers take 2x longer due to k=2 interference)

scenario:
  name: "Interference Test"

  network:
    nodes:
      - id: n0
        compute_capacity: 1000
        position: {x: 0, y: 0}
      - id: n1
        compute_capacity: 1000
        position: {x: 5, y: 0}
      - id: n2
        compute_capacity: 1000
        position: {x: 0, y: 5}
      - id: n3
        compute_capacity: 1000
        position: {x: 5, y: 5}
    links:
      - id: l01
        from: n0
        to: n1
        bandwidth: 100
        latency: 0.0
      - id: l23
        from: n2
        to: n3
        bandwidth: 100
        latency: 0.0

  dags:
    - id: dag_1
      inject_at: 0.0
      tasks:
        - {id: T0, compute_cost: 10, pinned_to: n0}
        - {id: T1, compute_cost: 10, pinned_to: n1}
        - {id: T2, compute_cost: 10, pinned_to: n2}
        - {id: T3, compute_cost: 10, pinned_to: n3}
      edges:
        - {from: T0, to: T1, data_size: 100}
        - {from: T2, to: T3, data_size: 100}

  config:
    scheduler: round_robin
    seed: 42
```

---

## 4. multihop_advantage.yaml

**Shows how multi-hop routing reaches a faster remote node.**

- **Nodes:** 3 in a line -- n_src (10 cu/s), n_relay (10 cu/s), n_fast (1000 cu/s)
- **Links:** 2 -- n_src to n_relay (100 MB/s, 10 ms), n_relay to n_fast (100 MB/s, 10 ms)
- **Tasks:** 2 pinned -- T0 on n_src, T1 on n_fast
- **Edges:** T0 to T1 (10 MB)
- **Scheduler:** round_robin, **Routing:** widest_path

!!! info "Expected behavior"
    Without multi-hop routing, there is no direct link from n_src to n_fast, so the transfer would fail or both tasks would run on the slow n_src node (200 s). With `widest_path` routing, the 10 MB transfer hops through n_relay to reach n_fast (100x faster compute). T1 completes in ~1 s instead of ~100 s on n_src. **~49% speedup.**

```yaml
# Multi-hop advantage scenario (pinned tasks, heterogeneous nodes)
#
# Topology: n_src(10 cu/s) -> n_relay(10 cu/s) -> n_fast(1000 cu/s)
# No direct n_src -> n_fast link -- forces multi-hop routing
#
# Without multi-hop: both tasks stuck on n_src -> 200s
# With multi-hop: T1 reaches n_fast (100x faster) -> 101.12s (49% faster)

scenario:
  name: "Multi-Hop Advantage Demo"

  network:
    nodes:
      - {id: n_src,   compute_capacity: 10,   position: {x: 0,  y: 0}}
      - {id: n_relay, compute_capacity: 10,   position: {x: 10, y: 0}}
      - {id: n_fast,  compute_capacity: 1000, position: {x: 20, y: 0}}
    links:
      - {id: l01, from: n_src,   to: n_relay, bandwidth: 100, latency: 0.01}
      - {id: l12, from: n_relay, to: n_fast,  bandwidth: 100, latency: 0.01}

  dags:
    - id: dag1
      inject_at: 0.0
      tasks:
        - {id: T0, compute_cost: 1000, pinned_to: n_src}
        - {id: T1, compute_cost: 1000, pinned_to: n_fast}
      edges:
        - {from: T0, to: T1, data_size: 10}

  config:
    scheduler: round_robin
    routing: widest_path
    seed: 42
```

---

## 5. multi_hop_forced.yaml

**Forces a multi-hop transfer between non-adjacent pinned nodes.**

- **Nodes:** 3 in a line -- n0, n1, n2 (all 100 cu/s)
- **Links:** 2 -- n0 to n1 (100 MB/s, 10 ms), n1 to n2 (100 MB/s, 10 ms)
- **Tasks:** 2 pinned -- T0 on n0, T1 on n2 (no direct link between them)
- **Edges:** T0 to T1 (50 MB)
- **Scheduler:** HEFT, **Routing:** widest_path

!!! info "Expected behavior"
    T0 runs on n0 (1.0 s). The 50 MB transfer must hop through n1 since there is no direct n0-to-n2 link. With `widest_path` routing, the path n0 -> n1 -> n2 is found automatically. T1 then runs on n2 (1.0 s).

```yaml
scenario:
  name: "Multi-Hop Forced Test"

  network:
    nodes:
      - {id: n0, compute_capacity: 100, position: {x: 0, y: 0}}
      - {id: n1, compute_capacity: 100, position: {x: 5, y: 0}}
      - {id: n2, compute_capacity: 100, position: {x: 10, y: 0}}
    links:
      # n0 -> n1 -> n2 (no direct n0 -> n2 link)
      - {id: l01, from: n0, to: n1, bandwidth: 100, latency: 0.01}
      - {id: l12, from: n1, to: n2, bandwidth: 100, latency: 0.01}

  dags:
    - id: dag1
      inject_at: 0.0
      tasks:
        # Pin T0 to n0 and T1 to n2 to force multi-hop transfer
        - {id: T0, compute_cost: 100, pinned_to: n0}
        - {id: T1, compute_cost: 100, pinned_to: n2}
      edges:
        - {from: T0, to: T1, data_size: 50}  # 50 MB transfer

  config:
    scheduler: heft
    routing: widest_path
    seed: 42
```

---

## 6. multi_hop_test.yaml

**Tests multi-hop widest-path routing with unpinned tasks.**

- **Nodes:** 3 in a line -- n0, n1, n2 (all 100 cu/s)
- **Links:** 2 -- n0 to n1 (100 MB/s, 10 ms), n1 to n2 (100 MB/s, 10 ms)
- **Tasks:** 2 unpinned -- T0 (100 cu), T1 (100 cu)
- **Edges:** T0 to T1 (50 MB)
- **Scheduler:** HEFT, **Routing:** widest_path

!!! info "Expected behavior"
    Unlike `multi_hop_forced`, tasks are not pinned. The HEFT scheduler is free to place both tasks on the same node (avoiding transfer entirely) or on adjacent nodes. This scenario tests that multi-hop routing is available when the scheduler needs it.

```yaml
scenario:
  name: "Multi-Hop Test"

  network:
    nodes:
      - {id: n0, compute_capacity: 100, position: {x: 0, y: 0}}
      - {id: n1, compute_capacity: 100, position: {x: 5, y: 0}}
      - {id: n2, compute_capacity: 100, position: {x: 10, y: 0}}
    links:
      # n0 -> n1 -> n2 (no direct n0 -> n2 link)
      - {id: l01, from: n0, to: n1, bandwidth: 100, latency: 0.01}
      - {id: l12, from: n1, to: n2, bandwidth: 100, latency: 0.01}

  dags:
    - id: dag1
      inject_at: 0.0
      tasks:
        - {id: T0, compute_cost: 100}   # 1 second on any node
        - {id: T1, compute_cost: 100}   # 1 second on any node
      edges:
        - {from: T0, to: T1, data_size: 50}  # 50 MB transfer

  config:
    scheduler: heft
    routing: widest_path
    seed: 42
```

---

## 7. parallel_spread.yaml

**Fan-out/fan-in DAG demonstrating HEFT + widest_path advantage.**

- **Nodes:** 5 in a line -- n0 (80 cu/s), n1 (90 cu/s), n2 (100 cu/s), n3 (90 cu/s), n4 (80 cu/s)
- **Links:** 8 bidirectional -- 500 MB/s each, 1 ms latency
- **Tasks:** 10 -- T_root, 8 parallel workers (P0-P7), T_sink
- **Edges:** T_root fans out to all 8 workers (1 MB each), all 8 fan in to T_sink (1 MB each)
- **Scheduler:** HEFT

!!! info "Expected behavior"
    **HEFT + direct routing:** only uses 3 adjacent nodes (limited by direct link visibility). Makespan: **~35.3 s.**

    **HEFT + widest_path routing:** spreads parallel tasks across all 5 nodes via multi-hop paths. Makespan: **~24.2 s** -- a **31% improvement.**

```yaml
# Parallel spread scenario -- demonstrates HEFT + multi-hop advantage
#
# 5 nodes in a line with bidirectional links:
#   n0(80) == n1(90) == n2(100) == n3(90) == n4(80) cu/s
#   All links 500 MB/s, 0.001s latency
#
# DAG: Fan-out/fan-in with 8 parallel tasks
#   T_root -> {P0..P7} -> T_sink
#
# HEFT + direct routing: only uses 3 adjacent nodes (35.3s)
# HEFT + widest_path:    spreads across all 5 nodes (24.2s) -- 31% faster

scenario:
  name: "Parallel Spread (Bidirectional)"

  network:
    nodes:
      - {id: n0, compute_capacity: 80,  position: {x: 0,  y: 0}}
      - {id: n1, compute_capacity: 90,  position: {x: 10, y: 0}}
      - {id: n2, compute_capacity: 100, position: {x: 20, y: 0}}
      - {id: n3, compute_capacity: 90,  position: {x: 30, y: 0}}
      - {id: n4, compute_capacity: 80,  position: {x: 40, y: 0}}
    links:
      - {id: l01, from: n0, to: n1, bandwidth: 500, latency: 0.001}
      - {id: l10, from: n1, to: n0, bandwidth: 500, latency: 0.001}
      - {id: l12, from: n1, to: n2, bandwidth: 500, latency: 0.001}
      - {id: l21, from: n2, to: n1, bandwidth: 500, latency: 0.001}
      - {id: l23, from: n2, to: n3, bandwidth: 500, latency: 0.001}
      - {id: l32, from: n3, to: n2, bandwidth: 500, latency: 0.001}
      - {id: l34, from: n3, to: n4, bandwidth: 500, latency: 0.001}
      - {id: l43, from: n4, to: n3, bandwidth: 500, latency: 0.001}

  dags:
    - id: dag1
      inject_at: 0.0
      tasks:
        - {id: T_root, compute_cost: 100}
        - {id: P0, compute_cost: 1000}
        - {id: P1, compute_cost: 1000}
        - {id: P2, compute_cost: 1000}
        - {id: P3, compute_cost: 1000}
        - {id: P4, compute_cost: 1000}
        - {id: P5, compute_cost: 1000}
        - {id: P6, compute_cost: 1000}
        - {id: P7, compute_cost: 1000}
        - {id: T_sink, compute_cost: 100}
      edges:
        - {from: T_root, to: P0, data_size: 1}
        - {from: T_root, to: P1, data_size: 1}
        - {from: T_root, to: P2, data_size: 1}
        - {from: T_root, to: P3, data_size: 1}
        - {from: T_root, to: P4, data_size: 1}
        - {from: T_root, to: P5, data_size: 1}
        - {from: T_root, to: P6, data_size: 1}
        - {from: T_root, to: P7, data_size: 1}
        - {from: P0, to: T_sink, data_size: 1}
        - {from: P1, to: T_sink, data_size: 1}
        - {from: P2, to: T_sink, data_size: 1}
        - {from: P3, to: T_sink, data_size: 1}
        - {from: P4, to: T_sink, data_size: 1}
        - {from: P5, to: T_sink, data_size: 1}
        - {from: P6, to: T_sink, data_size: 1}
        - {from: P7, to: T_sink, data_size: 1}

  config:
    scheduler: heft
    seed: 42
```

---

## 8. widest_vs_shortest.yaml

**Shows widest-path vs shortest-path routing divergence.**

- **Nodes:** 4 in a diamond -- src (0,5), relay_fast (5,0), relay_wide (5,10), dst (10,5), all 100 cu/s
- **Links:** 4 -- fast path (20 MB/s, 1 ms latency), wide path (200 MB/s, 50 ms latency)
- **Tasks:** 2 pinned -- T0 on src, T1 on dst
- **Edges:** T0 to T1 (100 MB)
- **Scheduler:** round_robin, **Routing:** widest_path

!!! info "Expected behavior"
    Two paths exist from src to dst:

    - **Shortest path** (via relay_fast): low latency (0.002 s) but only 20 MB/s bottleneck. Transfer time: 100/20 + 0.002 = 5.002 s. **Total makespan: 7.002 s.**
    - **Widest path** (via relay_wide): higher latency (0.1 s) but 200 MB/s bottleneck. Transfer time: 100/200 + 0.1 = 0.6 s. **Total makespan: 2.6 s.**

    Widest path is **~2.7x faster** because the large transfer dominates over the latency difference.

```yaml
# Widest-path vs Shortest-path divergence scenario
#
# Diamond topology with asymmetric paths:
#
#            relay_fast (low latency, low BW)
#           /                                \
#    src ---                                  --- dst
#           \                                /
#            relay_wide (high latency, high BW)
#
# Shortest-path picks: src->relay_fast->dst  (latency=0.002s, bottleneck BW=20 MB/s)
# Widest-path picks:   src->relay_wide->dst  (latency=0.1s,   bottleneck BW=200 MB/s)
#
# With 100 MB transfer:
#   Shortest: 1.0 + (100/20 + 0.002) + 1.0 = 7.002s
#   Widest:   1.0 + (100/200 + 0.1)  + 1.0 = 2.6s
#
# Widest-path ~2.7x faster because the large transfer dominates over latency.

scenario:
  name: "Widest vs Shortest Path Divergence"

  network:
    nodes:
      - {id: src,        compute_capacity: 100, position: {x: 0,  y: 5}}
      - {id: relay_fast, compute_capacity: 100, position: {x: 5,  y: 0}}
      - {id: relay_wide, compute_capacity: 100, position: {x: 5,  y: 10}}
      - {id: dst,        compute_capacity: 100, position: {x: 10, y: 5}}
    links:
      # Fast path: low latency, low bandwidth
      - {id: l_src_fast, from: src,        to: relay_fast, bandwidth: 20,  latency: 0.001}
      - {id: l_fast_dst, from: relay_fast, to: dst,        bandwidth: 20,  latency: 0.001}
      # Wide path: high latency, high bandwidth
      - {id: l_src_wide, from: src,        to: relay_wide, bandwidth: 200, latency: 0.05}
      - {id: l_wide_dst, from: relay_wide, to: dst,        bandwidth: 200, latency: 0.05}

  dags:
    - id: dag1
      inject_at: 0.0
      tasks:
        - {id: T0, compute_cost: 100, pinned_to: src}
        - {id: T1, compute_cost: 100, pinned_to: dst}
      edges:
        - {from: T0, to: T1, data_size: 100}

  config:
    scheduler: round_robin
    routing: widest_path
    seed: 42
```

---

## 9. wifi_clique_test.yaml

**Tests the static CSMA clique interference model.**

- **Nodes:** 4 -- n0 (0,0), n1 (30,0), n2 (0,30), n3 (30,30), all 1000 cu/s
- **Links:** 2 parallel -- l01 (n0 to n1), l23 (n2 to n3), no explicit bandwidth (derived from RF)
- **Tasks:** 4 pinned -- T0 on n0, T1 on n1, T2 on n2, T3 on n3
- **Edges:** T0 to T1 (50 MB), T2 to T3 (50 MB)
- **Scheduler:** round_robin
- **Interference:** csma_clique with full RF configuration

!!! info "Expected behavior"
    Both links contend in the same CSMA clique. The PHY rate is derived from RF parameters (802.11ax, 5 GHz, 20 MHz channel, 20 dBm TX power at 30 m). The effective bandwidth is PHY_rate / max_clique_size. **Makespan: ~11.6 s.**

```yaml
scenario:
  name: "WiFi CSMA Clique Test"
  description: >
    Tests the csma_clique interference model. Same topology as wifi_test
    but using the simpler static clique model. Link bandwidth =
    PHY_rate / max_clique_size. No dynamic SINR or Bianchi efficiency.

  network:
    nodes:
      - id: n0
        compute_capacity: 1000
        position: {x: 0, y: 0}
      - id: n1
        compute_capacity: 1000
        position: {x: 30, y: 0}
      - id: n2
        compute_capacity: 1000
        position: {x: 0, y: 30}
      - id: n3
        compute_capacity: 1000
        position: {x: 30, y: 30}
    links:
      - {id: l01, from: n0, to: n1, latency: 0.0}
      - {id: l23, from: n2, to: n3, latency: 0.0}

  dags:
    - id: dag_1
      inject_at: 0.0
      tasks:
        - {id: T0, compute_cost: 10, pinned_to: n0}
        - {id: T1, compute_cost: 10, pinned_to: n1}
        - {id: T2, compute_cost: 10, pinned_to: n2}
        - {id: T3, compute_cost: 10, pinned_to: n3}
      edges:
        - {from: T0, to: T1, data_size: 50}
        - {from: T2, to: T3, data_size: 50}

  config:
    scheduler: round_robin
    seed: 42
    interference: csma_clique
    rf:
      tx_power_dBm: 20
      freq_ghz: 5.0
      path_loss_exponent: 3.0
      noise_floor_dBm: -95
      cca_threshold_dBm: -82
      channel_width_mhz: 20
      wifi_standard: "ax"
      shadow_fading_sigma: 0.0
      rts_cts: false
```

---

## 10. wifi_test.yaml

**Tests the dynamic CSMA Bianchi interference model.**

- **Nodes:** 4 -- n0 (0,0), n1 (30,0), n2 (0,30), n3 (30,30), all 1000 cu/s
- **Links:** 2 parallel -- l01 (n0 to n1), l23 (n2 to n3), no explicit bandwidth (derived from RF)
- **Tasks:** 4 pinned -- T0 on n0, T1 on n1, T2 on n2, T3 on n3
- **Edges:** T0 to T1 (50 MB), T2 to T3 (50 MB)
- **Scheduler:** round_robin
- **Interference:** csma_bianchi with full RF configuration

!!! info "Expected behavior"
    Same topology as `wifi_clique_test` but uses the dynamic Bianchi model. The SINR-aware rate selection and Bianchi MAC efficiency produce a different (typically slower) effective throughput than the static clique model. With 2 contending links, each gets `eta(2)/2` of the channel, which is less than `1/max_clique_size` from the clique model. **Makespan: ~13.2 s** (slower than clique because `eta(2)/2 < 1/omega`).

```yaml
scenario:
  name: "WiFi CSMA Bianchi Test"
  description: >
    Tests the csma_bianchi interference model. Two parallel links at 30m
    spacing with bandwidth derived from RF parameters. The conflict graph
    should show both links contending, and SINR + Bianchi efficiency
    should reduce effective throughput compared to SNR-only rates.

  network:
    nodes:
      - id: n0
        compute_capacity: 1000
        position: {x: 0, y: 0}
      - id: n1
        compute_capacity: 1000
        position: {x: 30, y: 0}
      - id: n2
        compute_capacity: 1000
        position: {x: 0, y: 30}
      - id: n3
        compute_capacity: 1000
        position: {x: 30, y: 30}
    links:
      # No explicit bandwidth -- derived from RF model
      - {id: l01, from: n0, to: n1, latency: 0.0}
      - {id: l23, from: n2, to: n3, latency: 0.0}

  dags:
    - id: dag_1
      inject_at: 0.0
      tasks:
        - {id: T0, compute_cost: 10, pinned_to: n0}
        - {id: T1, compute_cost: 10, pinned_to: n1}
        - {id: T2, compute_cost: 10, pinned_to: n2}
        - {id: T3, compute_cost: 10, pinned_to: n3}
      edges:
        - {from: T0, to: T1, data_size: 50}
        - {from: T2, to: T3, data_size: 50}

  config:
    scheduler: round_robin
    seed: 42
    interference: csma_bianchi
    rf:
      tx_power_dBm: 20
      freq_ghz: 5.0
      path_loss_exponent: 3.0
      noise_floor_dBm: -95
      cca_threshold_dBm: -82
      channel_width_mhz: 20
      wifi_standard: "ax"
      shadow_fading_sigma: 0.0
      rts_cts: false
```

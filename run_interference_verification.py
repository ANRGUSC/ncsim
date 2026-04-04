#!/usr/bin/env python3
"""Interference model verification experiments.

Runs three experiments validating the csma_bianchi WiFi interference model
by comparing simulation results against analytical predictions computed
directly from the WiFi RF functions.

Experiment 1: Link Length vs Data Rate (single link, varying distance)
Experiment 2: Parallel Link Separation vs Interference (two parallel links)
Experiment 3: Two Transmitters to Same Receiver (shared RX node)

Key behavior of csma_bianchi model:
- Links IN the conflict graph contend via Bianchi MAC (symmetric time-sharing)
- Links NOT in the conflict graph are hidden terminals (SINR degradation)
- Hidden terminals cause symmetric SINR degradation: when any link starts or
  completes, ALL other active links are recalculated (not just conflict-graph
  neighbors), so both links in a symmetric hidden-terminal pair see the same
  interference.
"""

import json
import math
import os
import subprocess
import sys
from pathlib import Path

# Analytical prediction helpers — import from ncsim.models.wifi
sys.path.insert(0, str(Path(__file__).parent))
from ncsim.models.wifi import (
    RFConfig,
    received_power_dBm,
    snr_dB,
    sinr_dB,
    snr_to_rate_mbps,
    rate_mbps_to_MBps,
    carrier_sensing_range,
    bianchi_efficiency,
    path_loss_dB,
    MCS_TABLE_AX,
)

OUTDIR = "/tmp/ncsim_interference_verification"
RF = RFConfig()  # defaults: 20dBm, 5GHz, n=3.0, noise=-95dBm, CCA=-82dBm, ax, 20MHz
DATA_SIZE_MB = 10.0
COMPUTE_COST = 1
COMPUTE_CAPACITY = 100000
TOLERANCE = 0.01  # 1% match tolerance
MIN_FACTOR = 0.01  # minimum interference factor in the model


# ─── YAML Scenario Generators ───────────────────────────────────


def _yaml_header(name):
    return (
        f"scenario:\n"
        f"  name: \"{name}\"\n"
    )


def _yaml_config():
    return (
        "  config:\n"
        "    scheduler: round_robin\n"
        "    seed: 42\n"
        "    routing: direct\n"
        "    interference: csma_bianchi\n"
    )


def gen_exp1_yaml(distance):
    """Exp 1: Two nodes at distance d, single transfer n0->n1."""
    return (
        _yaml_header(f"exp1_d{distance}") +
        "  network:\n"
        "    nodes:\n"
        f"      - {{id: n0, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 0, y: 0}}}}\n"
        f"      - {{id: n1, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: {distance}, y: 0}}}}\n"
        "    links:\n"
        "      - {id: l01, from: n0, to: n1}\n"
        "  dags:\n"
        "    - id: dag_1\n"
        "      inject_at: 0.0\n"
        "      tasks:\n"
        f"        - {{id: T0, compute_cost: {COMPUTE_COST}, pinned_to: n0}}\n"
        f"        - {{id: T1, compute_cost: {COMPUTE_COST}, pinned_to: n1}}\n"
        "      edges:\n"
        f"        - {{from: T0, to: T1, data_size: {DATA_SIZE_MB}}}\n" +
        _yaml_config()
    )


def gen_exp2_yaml(separation):
    """Exp 2: Two parallel 30m links separated vertically by `separation`."""
    return (
        _yaml_header(f"exp2_sep{separation}") +
        "  network:\n"
        "    nodes:\n"
        f"      - {{id: n0, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 0, y: 0}}}}\n"
        f"      - {{id: n1, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 30, y: 0}}}}\n"
        f"      - {{id: n2, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 0, y: {separation}}}}}\n"
        f"      - {{id: n3, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 30, y: {separation}}}}}\n"
        "    links:\n"
        "      - {id: l01, from: n0, to: n1}\n"
        "      - {id: l23, from: n2, to: n3}\n"
        "  dags:\n"
        "    - id: dag_1\n"
        "      inject_at: 0.0\n"
        "      tasks:\n"
        f"        - {{id: T0, compute_cost: {COMPUTE_COST}, pinned_to: n0}}\n"
        f"        - {{id: T1, compute_cost: {COMPUTE_COST}, pinned_to: n1}}\n"
        f"        - {{id: T2, compute_cost: {COMPUTE_COST}, pinned_to: n2}}\n"
        f"        - {{id: T3, compute_cost: {COMPUTE_COST}, pinned_to: n3}}\n"
        "      edges:\n"
        f"        - {{from: T0, to: T1, data_size: {DATA_SIZE_MB}}}\n"
        f"        - {{from: T2, to: T3, data_size: {DATA_SIZE_MB}}}\n" +
        _yaml_config()
    )


def gen_exp3_yaml(distance):
    """Exp 3: Two TX nodes at distance d from shared RX at origin, 90 degrees apart."""
    return (
        _yaml_header(f"exp3_d{distance}") +
        "  network:\n"
        "    nodes:\n"
        f"      - {{id: n0, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 0, y: 0}}}}\n"
        f"      - {{id: n1, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: {distance}, y: 0}}}}\n"
        f"      - {{id: n2, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 0, y: {distance}}}}}\n"
        "    links:\n"
        "      - {id: l10, from: n1, to: n0}\n"
        "      - {id: l20, from: n2, to: n0}\n"
        "  dags:\n"
        "    - id: dag_1\n"
        "      inject_at: 0.0\n"
        "      tasks:\n"
        f"        - {{id: T1, compute_cost: {COMPUTE_COST}, pinned_to: n1}}\n"
        f"        - {{id: T1_sink, compute_cost: {COMPUTE_COST}, pinned_to: n0}}\n"
        f"        - {{id: T2, compute_cost: {COMPUTE_COST}, pinned_to: n2}}\n"
        f"        - {{id: T2_sink, compute_cost: {COMPUTE_COST}, pinned_to: n0}}\n"
        "      edges:\n"
        f"        - {{from: T1, to: T1_sink, data_size: {DATA_SIZE_MB}}}\n"
        f"        - {{from: T2, to: T2_sink, data_size: {DATA_SIZE_MB}}}\n" +
        _yaml_config()
    )


def gen_exp4_yaml(separation):
    """Exp 4: Three parallel 30m links separated vertically by `separation`.

    Link A: n0(0,0)->n1(30,0)
    Link B: n2(0,sep)->n3(30,sep)
    Link C: n4(0,2*sep)->n5(30,2*sep)
    """
    sep2 = 2 * separation
    return (
        _yaml_header(f"exp4_sep{separation}") +
        "  network:\n"
        "    nodes:\n"
        f"      - {{id: n0, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 0, y: 0}}}}\n"
        f"      - {{id: n1, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 30, y: 0}}}}\n"
        f"      - {{id: n2, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 0, y: {separation}}}}}\n"
        f"      - {{id: n3, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 30, y: {separation}}}}}\n"
        f"      - {{id: n4, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 0, y: {sep2}}}}}\n"
        f"      - {{id: n5, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 30, y: {sep2}}}}}\n"
        "    links:\n"
        "      - {id: l01, from: n0, to: n1}\n"
        "      - {id: l23, from: n2, to: n3}\n"
        "      - {id: l45, from: n4, to: n5}\n"
        "  dags:\n"
        "    - id: dag_1\n"
        "      inject_at: 0.0\n"
        "      tasks:\n"
        f"        - {{id: T0, compute_cost: {COMPUTE_COST}, pinned_to: n0}}\n"
        f"        - {{id: T1, compute_cost: {COMPUTE_COST}, pinned_to: n1}}\n"
        f"        - {{id: T2, compute_cost: {COMPUTE_COST}, pinned_to: n2}}\n"
        f"        - {{id: T3, compute_cost: {COMPUTE_COST}, pinned_to: n3}}\n"
        f"        - {{id: T4, compute_cost: {COMPUTE_COST}, pinned_to: n4}}\n"
        f"        - {{id: T5, compute_cost: {COMPUTE_COST}, pinned_to: n5}}\n"
        "      edges:\n"
        f"        - {{from: T0, to: T1, data_size: {DATA_SIZE_MB}}}\n"
        f"        - {{from: T2, to: T3, data_size: {DATA_SIZE_MB}}}\n"
        f"        - {{from: T4, to: T5, data_size: {DATA_SIZE_MB}}}\n" +
        _yaml_config()
    )


def gen_exp5_yaml(delay_cost):
    """Exp 5: Two parallel 30m links, 100m apart. T0 has high compute cost to stagger start."""
    sep = 100
    return (
        _yaml_header(f"exp5_delay{delay_cost}") +
        "  network:\n"
        "    nodes:\n"
        f"      - {{id: n0, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 0, y: 0}}}}\n"
        f"      - {{id: n1, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 30, y: 0}}}}\n"
        f"      - {{id: n2, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 0, y: {sep}}}}}\n"
        f"      - {{id: n3, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 30, y: {sep}}}}}\n"
        "    links:\n"
        "      - {id: l01, from: n0, to: n1}\n"
        "      - {id: l23, from: n2, to: n3}\n"
        "  dags:\n"
        "    - id: dag_1\n"
        "      inject_at: 0.0\n"
        "      tasks:\n"
        f"        - {{id: T0, compute_cost: {delay_cost}, pinned_to: n0}}\n"
        f"        - {{id: T1, compute_cost: {COMPUTE_COST}, pinned_to: n1}}\n"
        f"        - {{id: T2, compute_cost: {COMPUTE_COST}, pinned_to: n2}}\n"
        f"        - {{id: T3, compute_cost: {COMPUTE_COST}, pinned_to: n3}}\n"
        "      edges:\n"
        f"        - {{from: T0, to: T1, data_size: {DATA_SIZE_MB}}}\n"
        f"        - {{from: T2, to: T3, data_size: {DATA_SIZE_MB}}}\n" +
        _yaml_config()
    )


# ─── Subprocess Runner ───────────────────────────────────────────


def run_scenario(yaml_str, run_label):
    """Write YAML to temp file, invoke ncsim via subprocess, return output dir."""
    outdir = os.path.join(OUTDIR, run_label)
    os.makedirs(outdir, exist_ok=True)

    # Write YAML to a separate input dir to avoid SameFileError
    # (main.py copies scenario.yaml into the output dir)
    input_dir = os.path.join(OUTDIR, "_inputs", run_label)
    os.makedirs(input_dir, exist_ok=True)
    yaml_path = os.path.join(input_dir, "scenario.yaml")
    with open(yaml_path, "w") as f:
        f.write(yaml_str)

    cmd = [
        sys.executable, "-m", "ncsim",
        "--scenario", yaml_path,
        "--output", outdir,
        "--interference", "csma_bianchi",
        "--scheduler", "round_robin",
        "--routing", "direct",
        "--seed", "42",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR running {run_label}:")
        print(f"    stdout: {result.stdout[-300:] if result.stdout else '(empty)'}")
        print(f"    stderr: {result.stderr[-300:] if result.stderr else '(empty)'}")
        return None
    return outdir


# ─── Trace Parser ────────────────────────────────────────────────


def parse_trace(outdir):
    """Parse trace.jsonl and return list of transfer records sorted by start seq.

    Each record: {from_task, to_task, link_id, data_size, start_time, end_time, duration, seq}
    """
    trace_path = os.path.join(outdir, "trace.jsonl")
    transfers = {}  # (from_task, to_task) -> record
    with open(trace_path) as f:
        for line in f:
            ev = json.loads(line)
            if ev["type"] == "transfer_start":
                key = (ev["from_task"], ev["to_task"])
                transfers[key] = {
                    "from_task": ev["from_task"],
                    "to_task": ev["to_task"],
                    "link_id": ev["link_id"],
                    "data_size": ev["data_size"],
                    "start_time": ev["sim_time"],
                    "seq": ev["seq"],
                }
            elif ev["type"] == "transfer_complete":
                key = (ev["from_task"], ev["to_task"])
                if key in transfers:
                    transfers[key]["end_time"] = ev["sim_time"]
                    transfers[key]["duration"] = ev["duration"]
    return sorted(transfers.values(), key=lambda t: t["seq"])


def get_makespan(outdir):
    """Get makespan from metrics.json."""
    path = os.path.join(outdir, "metrics.json")
    with open(path) as f:
        data = json.load(f)
    return data["makespan"]


# ─── Analytical Helpers ──────────────────────────────────────────


def analytical_rate_at_distance(d):
    """Compute PHY rate in MB/s for a single link at distance d (SNR-only, no interference).

    When PHY rate = 0 (below minimum MCS), the simulator sets link bandwidth
    to 0.001 MB/s fallback, and the Bianchi model returns MIN_FACTOR because
    the cached base_rate is 0. Effective = 0.001 * MIN_FACTOR.
    """
    rx_pow = received_power_dBm(RF.tx_power_dBm, d, RF)
    link_snr = snr_dB(rx_pow, RF.noise_floor_dBm)
    rate_mbps = snr_to_rate_mbps(link_snr, RF.wifi_standard, RF.channel_width_mhz)
    rate = rate_mbps_to_MBps(rate_mbps)
    if rate <= 0:
        # Out of range: simulator uses 0.001 MB/s fallback * MIN_FACTOR
        return 0.001 * MIN_FACTOR
    return rate


def analytical_snr_at_distance(d):
    """Compute SNR in dB at distance d."""
    rx_pow = received_power_dBm(RF.tx_power_dBm, d, RF)
    return snr_dB(rx_pow, RF.noise_floor_dBm)


def analytical_path_loss(d):
    """Compute path loss in dB at distance d."""
    return path_loss_dB(d, RF.freq_ghz, RF.path_loss_exponent)


def snr_to_mcs_index(snr_val):
    """Return MCS index for given SNR (802.11ax)."""
    mcs = -1
    for i, (min_snr, _) in enumerate(MCS_TABLE_AX):
        if snr_val >= min_snr:
            mcs = i
        else:
            break
    return mcs


def compute_sinr_rate(desired_dist, interferer_dist):
    """Compute SINR-based rate in MB/s given desired and interferer distances.

    If SINR drops below minimum MCS threshold (rate=0), the model clamps
    the interference factor to MIN_FACTOR, yielding base_rate * MIN_FACTOR.
    """
    rx_pow = received_power_dBm(RF.tx_power_dBm, desired_dist, RF)
    i_pow = received_power_dBm(RF.tx_power_dBm, interferer_dist, RF)
    link_sinr = sinr_dB(rx_pow, [i_pow], RF.noise_floor_dBm)
    sinr_rate_mbps = snr_to_rate_mbps(link_sinr, RF.wifi_standard, RF.channel_width_mhz)
    sinr_rate = rate_mbps_to_MBps(sinr_rate_mbps)

    base_rate = analytical_rate_at_distance(desired_dist)
    if sinr_rate <= 0 and base_rate > 0:
        # Model clamps factor to MIN_FACTOR
        return base_rate * MIN_FACTOR
    return sinr_rate


def compute_multi_sinr_rate(desired_dist, interferer_dists):
    """Compute SINR-based rate in MB/s with multiple interferers.

    Generalizes compute_sinr_rate to N interferers.
    """
    rx_pow = received_power_dBm(RF.tx_power_dBm, desired_dist, RF)
    i_powers = [received_power_dBm(RF.tx_power_dBm, d, RF)
                for d in interferer_dists]
    link_sinr = sinr_dB(rx_pow, i_powers, RF.noise_floor_dBm)
    sinr_rate_mbps = snr_to_rate_mbps(link_sinr, RF.wifi_standard,
                                       RF.channel_width_mhz)
    sinr_rate = rate_mbps_to_MBps(sinr_rate_mbps)

    base_rate = analytical_rate_at_distance(desired_dist)
    if sinr_rate <= 0 and base_rate > 0:
        return base_rate * MIN_FACTOR
    return sinr_rate


def rates_match(sim, pred):
    """Check if simulated rate matches predicted within tolerance."""
    if pred == 0 and sim == 0:
        return True
    if pred == 0:
        return False
    return abs(sim - pred) / pred <= TOLERANCE


def durations_match(sim, pred):
    """Check if simulated duration matches predicted within tolerance."""
    if pred == 0 and sim == 0:
        return True
    if pred == 0:
        return False
    return abs(sim - pred) / pred <= TOLERANCE


def are_parallel_links_in_conflict(separation):
    """Check if two parallel 30m horizontal links at vertical separation are in conflict.

    Without RTS/CTS: tx(A) senses any node of B, or tx(B) senses any node of A.
    """
    cs = carrier_sensing_range(RF)
    return separation <= cs or math.sqrt(900 + separation**2) <= cs


def are_in_conflict_exp2(separation):
    """Check if the two links in exp2 are in each other's conflict graph.

    Without RTS/CTS, conflict if tx(A) can sense any node of link B, or
    tx(B) can sense any node of link A.

    Link A: n0(0,0)->n1(30,0), Link B: n2(0,sep)->n3(30,sep)
    tx(A) = n0(0,0), tx(B) = n2(0,sep)
    """
    cs = carrier_sensing_range(RF)
    d_n0_n2 = separation
    d_n0_n3 = math.sqrt(900 + separation**2)
    d_n2_n0 = separation
    d_n2_n1 = math.sqrt(900 + separation**2)
    return (d_n0_n2 <= cs or d_n0_n3 <= cs or d_n2_n0 <= cs or d_n2_n1 <= cs)


def are_in_conflict_exp3(distance):
    """Check if the two links in exp3 are in each other's conflict graph.

    Link l10: n1(d,0)->n0(0,0), Link l20: n2(0,d)->n0(0,0)
    tx(l10)=n1, tx(l20)=n2.  Shared node n0 is receiver for both.
    Without RTS/CTS: tx senses other link's nodes.
      tx(l10)=n1 senses n2 at d*sqrt(2) or n0 at d
      tx(l20)=n2 senses n1 at d*sqrt(2) or n0 at d
    """
    cs = carrier_sensing_range(RF)
    return (distance <= cs or distance * math.sqrt(2) <= cs)


# ─── Experiment 1: Link Length vs Data Rate ──────────────────────


def run_exp1():
    """Single link, vary distance, compare predicted vs simulated rate."""
    print("=" * 95)
    print("  Experiment 1: Link Length vs Data Rate")
    print("  Single link n0->n1, varying distance d")
    print("=" * 95)
    print()

    distances = [1, 3, 5, 8, 12, 16, 20, 25, 30, 36, 42, 50,
                 58, 66, 75, 85, 95, 105, 120, 140]

    results = []
    for d in distances:
        label = f"exp1/d{d}"
        print(f"  Running {label}...", end=" ", flush=True)
        yaml = gen_exp1_yaml(d)
        outdir = run_scenario(yaml, label)
        if outdir is None:
            print("FAILED")
            results.append((d, None))
            continue

        transfers = parse_trace(outdir)
        pred_rate = analytical_rate_at_distance(d)
        snr_val = analytical_snr_at_distance(d)
        pl = analytical_path_loss(d)
        mcs = snr_to_mcs_index(snr_val)

        if not transfers:
            # No transfer in trace — link out of range (rate=0)
            sim_rate = 0.0
        else:
            t = transfers[0]
            sim_rate = DATA_SIZE_MB / t["duration"] if t["duration"] > 0 else 0.0

        match = rates_match(sim_rate, pred_rate)
        results.append((d, pl, snr_val, mcs, pred_rate, sim_rate, match))
        print(f"{sim_rate:.4f} MB/s {'OK' if match else 'MISMATCH'}")

    print()
    print(f"  {'Dist(m)':>8s}  {'PathLoss(dB)':>12s}  {'SNR(dB)':>8s}  {'MCS':>3s}  "
          f"{'Predicted(MB/s)':>15s}  {'Simulated(MB/s)':>15s}  {'Match':>5s}")
    print(f"  {'--------':>8s}  {'------------':>12s}  {'-------':>8s}  {'---':>3s}  "
          f"{'---------------':>15s}  {'---------------':>15s}  {'-----':>5s}")

    all_match = True
    for r in results:
        if r[1] is None:
            print(f"  {r[0]:>8.0f}  {'ERROR':>12s}")
            all_match = False
            continue
        d, pl, snr_val, mcs, pred, sim, match = r
        mcs_str = str(mcs) if mcs >= 0 else "n/a"
        match_str = "OK" if match else "FAIL"
        if not match:
            all_match = False
        print(f"  {d:>8.0f}  {pl:>12.2f}  {snr_val:>8.2f}  {mcs_str:>3s}  "
              f"{pred:>15.4f}  {sim:>15.4f}  {match_str:>5s}")

    print()
    cs = carrier_sensing_range(RF)
    print(f"  CS range: {cs:.1f}m")
    print(f"  All match: {'YES' if all_match else 'NO'}")
    print()
    return all_match


# ─── Experiment 2: Parallel Link Separation vs Interference ─────


def run_exp2():
    """Two parallel 30m links, vary vertical separation.

    When in conflict (sep <= CS range): symmetric Bianchi contention.
    When hidden terminal (sep > CS range): symmetric SINR degradation —
    both links see each other as hidden terminals and get the same
    degraded rate based on the interferer distance sqrt(30^2 + sep^2).
    """
    print("=" * 115)
    print("  Experiment 2: Parallel Link Separation vs Interference")
    print("  Link A: n0(0,0)->n1(30,0), Link B: n2(0,sep)->n3(30,sep)")
    print("=" * 115)
    print()

    cs = carrier_sensing_range(RF)
    base_rate = analytical_rate_at_distance(30)
    eta2 = bianchi_efficiency(2)
    print(f"  Carrier sensing range: {cs:.1f}m")
    print(f"  Base PHY rate at 30m: {base_rate:.4f} MB/s")
    print(f"  Bianchi eta(2): {eta2:.4f}, eta(2)/2: {eta2/2:.4f}")
    print()

    separations = [5, 10, 15, 20, 30, 40, 50, 60, 65, 70, 75, 80, 100, 140, 200]

    results = []
    for sep in separations:
        label = f"exp2/sep{sep}"
        print(f"  Running {label}...", end=" ", flush=True)
        yaml = gen_exp2_yaml(sep)
        outdir = run_scenario(yaml, label)
        if outdir is None:
            print("FAILED")
            results.append((sep, None))
            continue

        transfers = parse_trace(outdir)
        makespan = get_makespan(outdir)

        # Find transfers for each link
        sim_a = sim_b = None
        for t in transfers:
            rate = DATA_SIZE_MB / t["duration"]
            if t["link_id"] == "l01":
                sim_a = rate
            elif t["link_id"] == "l23":
                sim_b = rate

        in_conflict = are_in_conflict_exp2(sep)

        if in_conflict:
            # Symmetric Bianchi contention: both links get same rate
            pred_a = base_rate * eta2 / 2
            pred_b = pred_a
        else:
            # Hidden terminal — symmetric SINR degradation:
            # Both links see each other as hidden terminals.
            # Interferer distance is the same for both (by symmetry):
            #   l01 rx=n1(30,0), interferer tx=n2(0,sep) -> sqrt(30^2+sep^2)
            #   l23 rx=n3(30,sep), interferer tx=n0(0,0) -> sqrt(30^2+sep^2)
            i_dist = math.sqrt(30**2 + sep**2)
            pred_a = compute_sinr_rate(30, i_dist)
            pred_b = pred_a

        results.append((sep, in_conflict, pred_a, pred_b, sim_a, sim_b, makespan))
        print(f"A={sim_a:.4f} B={sim_b:.4f} MB/s")

    print()
    print(f"  {'Sep(m)':>7s}  {'InConflict':>10s}  "
          f"{'Pred_A(MB/s)':>12s}  {'Sim_A(MB/s)':>12s}  "
          f"{'Pred_B(MB/s)':>12s}  {'Sim_B(MB/s)':>12s}  "
          f"{'Makespan':>10s}  {'Match':>5s}")
    print(f"  {'-------':>7s}  {'----------':>10s}  "
          f"{'------------':>12s}  {'----------':>12s}  "
          f"{'------------':>12s}  {'----------':>12s}  "
          f"{'--------':>10s}  {'-----':>5s}")

    all_match = True
    for r in results:
        if r[1] is None:
            print(f"  {r[0]:>7.0f}  {'ERROR':>10s}")
            all_match = False
            continue
        sep, in_conflict, pred_a, pred_b, sim_a, sim_b, makespan = r
        conflict_str = "Yes" if in_conflict else "No"
        match_a = rates_match(sim_a, pred_a)
        match_b = rates_match(sim_b, pred_b)
        match = match_a and match_b
        match_str = "OK" if match else "FAIL"
        if not match:
            all_match = False
        print(f"  {sep:>7.0f}  {conflict_str:>10s}  "
              f"{pred_a:>12.4f}  {sim_a:>12.4f}  "
              f"{pred_b:>12.4f}  {sim_b:>12.4f}  "
              f"{makespan:>10.4f}  {match_str:>5s}")

    print()
    print(f"  All match: {'YES' if all_match else 'NO'}")
    print()

    # Save results to JSON for plot scripts
    json_results = []
    solo_rate = base_rate
    for r in results:
        if r[1] is None:
            continue
        sep, in_conflict, pred_a, pred_b, sim_a, sim_b, makespan = r
        regime = "contention" if in_conflict else "hidden_terminal"
        json_results.append({
            "separation_m": sep,
            "in_conflict": in_conflict,
            "regime": regime,
            "predicted_rate_MBps": pred_a,
            "simulated_rate_a_MBps": sim_a,
            "simulated_rate_b_MBps": sim_b,
            "makespan_s": makespan,
        })

    json_out = Path(__file__).parent / "paper" / "_results" / "exp2_separation.json"
    json_out.parent.mkdir(parents=True, exist_ok=True)
    with open(json_out, "w") as f:
        json.dump({
            "experiment": "exp2_parallel_separation",
            "description": "Two parallel 30m links at varying separation",
            "solo_rate_MBps": solo_rate,
            "cs_range_m": cs,
            "results": json_results,
        }, f, indent=2)
    print(f"  Saved {json_out}")
    print()

    return all_match


# ─── Experiment 3: Two Transmitters to Same Receiver ─────────────


def run_exp3():
    """Two TX nodes send to shared RX at origin, varying distance.

    When in conflict (d <= CS range): symmetric Bianchi contention.
    When hidden terminal (d > CS range): symmetric SINR degradation —
    both links share the same receiver n0 and each sees the other's
    transmitter at distance d as interference. Equal-power interferer
    at same distance yields very low SINR, so model clamps to min factor.
    """
    print("=" * 115)
    print("  Experiment 3: Two Transmitters to Same Receiver")
    print("  n1(d,0)->n0(0,0)<-n2(0,d), transmitters at 90 degrees")
    print("=" * 115)
    print()

    cs = carrier_sensing_range(RF)
    eta2 = bianchi_efficiency(2)
    print(f"  Carrier sensing range: {cs:.1f}m")
    print(f"  Bianchi eta(2): {eta2:.4f}")
    print()

    distances = [5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 65, 70, 75, 80, 90, 100, 115, 130]

    results = []
    for d in distances:
        label = f"exp3/d{d}"
        print(f"  Running {label}...", end=" ", flush=True)
        yaml = gen_exp3_yaml(d)
        outdir = run_scenario(yaml, label)
        if outdir is None:
            print("FAILED")
            results.append((d, None))
            continue

        transfers = parse_trace(outdir)

        sim_l10 = sim_l20 = None
        for t in transfers:
            rate = DATA_SIZE_MB / t["duration"]
            if t["link_id"] == "l10":
                sim_l10 = rate
            elif t["link_id"] == "l20":
                sim_l20 = rate

        base_rate = analytical_rate_at_distance(d)
        in_conflict = are_in_conflict_exp3(d)

        if in_conflict:
            # Symmetric Bianchi contention
            pred_l10 = base_rate * eta2 / 2
            pred_l20 = pred_l10
        else:
            # Hidden terminal — symmetric SINR degradation:
            # Both links share receiver n0. Each sees the other's TX at
            # distance d from n0 as interference (equal-power interferer).
            pred_l10 = compute_sinr_rate(d, d)
            pred_l20 = pred_l10

        results.append((d, in_conflict, base_rate, pred_l10, pred_l20, sim_l10, sim_l20))
        print(f"l10={sim_l10:.4f} l20={sim_l20:.4f} MB/s")

    print()
    print(f"  {'Dist(m)':>8s}  {'InConflict':>10s}  {'Base(MB/s)':>10s}  "
          f"{'Pred_l10':>10s}  {'Sim_l10':>10s}  "
          f"{'Pred_l20':>10s}  {'Sim_l20':>10s}  {'Match':>5s}")
    print(f"  {'--------':>8s}  {'----------':>10s}  {'----------':>10s}  "
          f"{'--------':>10s}  {'-------':>10s}  "
          f"{'--------':>10s}  {'-------':>10s}  {'-----':>5s}")

    all_match = True
    for r in results:
        if r[1] is None:
            print(f"  {r[0]:>8.0f}  {'ERROR':>10s}")
            all_match = False
            continue
        d, in_conflict, base, pred_l10, pred_l20, sim_l10, sim_l20 = r
        conflict_str = "Yes" if in_conflict else "No"
        match_10 = rates_match(sim_l10, pred_l10)
        match_20 = rates_match(sim_l20, pred_l20)
        match = match_10 and match_20
        match_str = "OK" if match else "FAIL"
        if not match:
            all_match = False
        print(f"  {d:>8.0f}  {conflict_str:>10s}  {base:>10.4f}  "
              f"{pred_l10:>10.4f}  {sim_l10:>10.4f}  "
              f"{pred_l20:>10.4f}  {sim_l20:>10.4f}  {match_str:>5s}")

    print()
    print(f"  All match: {'YES' if all_match else 'NO'}")
    print()
    return all_match


# ─── Experiment 4: Three Parallel Links ──────────────────────────


def predict_exp4_effective_rates(sep):
    """Compute predicted effective rates for exp4's three parallel 30m links.

    Accounts for multi-phase behavior: when one group of links finishes
    first, remaining links' rates change due to reduced interference.

    Three regimes based on separation:
      all_conf:  All three in conflict graph → same rate, finish together.
      mixed:     AB,BC in conflict, AC hidden → A==C but != B, two phases.
      all_hid:   No conflict edges → A==C but != B, two phases.

    Returns (eff_rate_A, eff_rate_B, eff_rate_C, regime).
    """
    D = DATA_SIZE_MB
    base_rate = analytical_rate_at_distance(30)
    eta2 = bianchi_efficiency(2)
    eta3 = bianchi_efficiency(3)

    ab_conflict = are_parallel_links_in_conflict(sep)
    ac_conflict = are_parallel_links_in_conflict(2 * sep)

    i_near = math.sqrt(900 + sep**2)
    i_far = math.sqrt(900 + 4 * sep**2)

    if ab_conflict and ac_conflict:
        # All-conflict: 3-way Bianchi, same rate, single phase
        r = base_rate * eta3 / 3
        return r, r, r, "all_conf"

    elif ab_conflict and not ac_conflict:
        # Mixed: A,C contend with B (eta(2)/2) + SINR from far hidden terminal
        #        B contends with A and C (eta(3)/3), no hidden terminals
        sinr_rate_far = compute_sinr_rate(30, i_far)
        r1_ac = sinr_rate_far * eta2 / 2
        r1_b = base_rate * eta3 / 3

        t_ac = D / r1_ac
        t_b = D / r1_b

        if t_b <= t_ac:
            # B finishes first → Phase 2: A,C lose contention neighbor B,
            # but remain hidden terminals to each other (AC not in conflict)
            r2_ac = sinr_rate_far  # eta(1)/1 = 1.0, SINR unchanged
            remaining = D - r1_ac * t_b
            total_ac = t_b + remaining / r2_ac
            return D / total_ac, r1_b, D / total_ac, "mixed"
        else:
            # A/C finish first → Phase 2: B solo
            remaining = D - r1_b * t_ac
            total_b = t_ac + remaining / base_rate
            return r1_ac, D / total_b, r1_ac, "mixed"

    else:
        # All-hidden: no conflict edges, all interference is SINR-based
        # A: hidden terminals B(near) + C(far)
        # B: hidden terminals A(near) + C(near) — both equidistant
        # C: symmetric to A
        r1_a = compute_multi_sinr_rate(30, [i_near, i_far])
        r1_b = compute_multi_sinr_rate(30, [i_near, i_near])
        # rate_A >= rate_B always (A has less total interference)

        t_ac = D / r1_a
        t_b = D / r1_b

        if t_b <= t_ac:
            # B finishes first → Phase 2: A,C as hidden terminals to each other only
            r2_ac = compute_sinr_rate(30, i_far)
            remaining = D - r1_a * t_b
            total_ac = t_b + remaining / r2_ac
            return D / total_ac, r1_b, D / total_ac, "all_hid"
        else:
            # A/C finish first → Phase 2: B solo
            remaining = D - r1_b * t_ac
            total_b = t_ac + remaining / base_rate
            return r1_a, D / total_b, r1_a, "all_hid"


def run_exp4():
    """Three parallel 30m links at y=0, y=sep, y=2*sep.

    Tests three interference regimes as separation increases:
    1. All-conflict (sep <= ~35.6m): 3-way Bianchi contention.
    2. Mixed (35.6 < sep <= ~71.2): Adjacent pairs in conflict, outer pair hidden.
    3. All-hidden (sep > ~71.2m): All three are hidden terminals.

    Validates multi-interferer SINR, combined Bianchi + SINR factor,
    and that outer links A and C always have symmetric rates.
    """
    print("=" * 130)
    print("  Experiment 4: Three Parallel Links")
    print("  Link A: n0(0,0)->n1(30,0), Link B: n2(0,sep)->n3(30,sep), Link C: n4(0,2*sep)->n5(30,2*sep)")
    print("=" * 130)
    print()

    cs = carrier_sensing_range(RF)
    base_rate = analytical_rate_at_distance(30)
    eta2 = bianchi_efficiency(2)
    eta3 = bianchi_efficiency(3)
    print(f"  CS range: {cs:.1f}m | Base rate at 30m: {base_rate:.4f} MB/s")
    print(f"  eta(2): {eta2:.4f}, eta(3): {eta3:.4f}")
    print()

    separations = [10, 20, 35, 40, 50, 60, 70, 75, 80, 100, 150]

    results = []
    for sep in separations:
        label = f"exp4/sep{sep}"
        print(f"  Running {label}...", end=" ", flush=True)
        yaml = gen_exp4_yaml(sep)
        outdir = run_scenario(yaml, label)
        if outdir is None:
            print("FAILED")
            results.append((sep, None))
            continue

        transfers = parse_trace(outdir)

        sim_a = sim_b = sim_c = None
        for t in transfers:
            rate = DATA_SIZE_MB / t["duration"]
            if t["link_id"] == "l01":
                sim_a = rate
            elif t["link_id"] == "l23":
                sim_b = rate
            elif t["link_id"] == "l45":
                sim_c = rate

        # Multi-phase prediction accounting for rate changes when links finish
        pred_a, pred_b, pred_c, regime = predict_exp4_effective_rates(sep)

        results.append((sep, regime, pred_a, pred_b, pred_c, sim_a, sim_b, sim_c))
        print(f"A={sim_a:.4f} B={sim_b:.4f} C={sim_c:.4f}")

    print()
    print(f"  {'Sep':>5s}  {'Regime':>8s}  "
          f"{'Pred_A':>8s}  {'Sim_A':>8s}  "
          f"{'Pred_B':>8s}  {'Sim_B':>8s}  "
          f"{'Pred_C':>8s}  {'Sim_C':>8s}  "
          f"{'A==C':>4s}  {'Match':>5s}")
    print(f"  {'-----':>5s}  {'--------':>8s}  "
          f"{'------':>8s}  {'-----':>8s}  "
          f"{'------':>8s}  {'-----':>8s}  "
          f"{'------':>8s}  {'-----':>8s}  "
          f"{'----':>4s}  {'-----':>5s}")

    all_match = True
    for r in results:
        if r[1] is None:
            print(f"  {r[0]:>5.0f}  {'ERROR':>8s}")
            all_match = False
            continue
        sep, regime, pa, pb, pc, sa, sb, sc = r
        match_a = rates_match(sa, pa)
        match_b = rates_match(sb, pb)
        match_c = rates_match(sc, pc)
        sym_ac = rates_match(sa, sc)  # A and C should always be equal
        match = match_a and match_b and match_c and sym_ac
        if not match:
            all_match = False
        print(f"  {sep:>5.0f}  {regime:>8s}  "
              f"{pa:>8.4f}  {sa:>8.4f}  "
              f"{pb:>8.4f}  {sb:>8.4f}  "
              f"{pc:>8.4f}  {sc:>8.4f}  "
              f"{'Y' if sym_ac else 'N':>4s}  "
              f"{'OK' if match else 'FAIL':>5s}")

    print()
    print(f"  All match: {'YES' if all_match else 'NO'}")
    print()
    return all_match


# ─── Experiment 5: Staggered Transfer Start ─────────────────────


def run_exp5():
    """Two parallel 30m links at 100m separation (hidden terminals),
    with staggered transfer start times.

    Transfer B (l23) starts early, Transfer A (l01) starts later.
    Tests dynamic recalculation:
    - When A starts, B must be recalculated with SINR degradation
    - When B finishes, A must be recalculated back to solo rate
    - Both transfer durations should be equal (by symmetry of phases)

    Phase model for predictions:
      Phase 1: B solo at r0 for delta seconds
      Phase 2: Both active at r1 until B finishes
      Phase 3: A solo at r0 until A finishes
      Both durations = delta + (D - delta*r0) / r1
    """
    print("=" * 130)
    print("  Experiment 5: Staggered Transfer Start (Hidden Terminal Dynamic Recalculation)")
    print("  Link A: n0(0,0)->n1(30,0), Link B: n2(0,100)->n3(30,100), hidden terminals")
    print("=" * 130)
    print()

    base_rate = analytical_rate_at_distance(30)
    i_dist = math.sqrt(900 + 10000)  # sqrt(30^2 + 100^2)
    sinr_rate = compute_sinr_rate(30, i_dist)
    print(f"  Base rate (solo): {base_rate:.4f} MB/s")
    print(f"  SINR rate (both active): {sinr_rate:.4f} MB/s")
    print()

    # delay_cost values -> delta = (delay_cost - COMPUTE_COST) / COMPUTE_CAPACITY
    delay_costs = [10000, 30000, 50000, 80000]

    results = []
    for dc in delay_costs:
        label = f"exp5/delay{dc}"
        print(f"  Running {label}...", end=" ", flush=True)
        yaml = gen_exp5_yaml(dc)
        outdir = run_scenario(yaml, label)
        if outdir is None:
            print("FAILED")
            results.append((dc, None))
            continue

        transfers = parse_trace(outdir)

        dur_a = dur_b = None
        for t in transfers:
            if t["link_id"] == "l01":
                dur_a = t["duration"]
            elif t["link_id"] == "l23":
                dur_b = t["duration"]

        # Compute delta precisely
        t_slow = round(dc / COMPUTE_CAPACITY, 6)
        t_fast = round(COMPUTE_COST / COMPUTE_CAPACITY, 6)
        delta = round(t_slow - t_fast, 6)

        # Predicted duration (same for both)
        r0, r1, D = base_rate, sinr_rate, DATA_SIZE_MB
        if delta * r0 >= D:
            pred_dur = D / r0
        else:
            pred_dur = delta + (D - delta * r0) / r1

        results.append((dc, delta, pred_dur, dur_a, dur_b))
        print(f"A={dur_a:.6f}s B={dur_b:.6f}s")

    print()
    print(f"  {'DelayCost':>10s}  {'Delta(s)':>8s}  "
          f"{'Pred_dur':>10s}  {'Dur_A':>10s}  {'Dur_B':>10s}  "
          f"{'A==B':>4s}  {'Match':>5s}")
    print(f"  {'----------':>10s}  {'--------':>8s}  "
          f"{'--------':>10s}  {'-----':>10s}  {'-----':>10s}  "
          f"{'----':>4s}  {'-----':>5s}")

    all_match = True
    for r in results:
        if r[1] is None:
            print(f"  {r[0]:>10d}  {'ERROR':>8s}")
            all_match = False
            continue
        dc, delta, pred, da, db = r
        match_a = durations_match(da, pred)
        match_b = durations_match(db, pred)
        sym = durations_match(da, db)
        match = match_a and match_b and sym
        if not match:
            all_match = False
        print(f"  {dc:>10d}  {delta:>8.4f}  "
              f"{pred:>10.6f}  {da:>10.6f}  {db:>10.6f}  "
              f"{'Y' if sym else 'N':>4s}  "
              f"{'OK' if match else 'FAIL':>5s}")

    print()
    print(f"  All match: {'YES' if all_match else 'NO'}")
    print()
    return all_match


# ─── Multi-Phase Prediction Helpers ───────────────────────────────


def predict_fair_share_durations(data_sizes, bandwidth):
    """Predict transfer durations for N concurrent flows on one link.

    When flows have different data sizes, faster ones complete first,
    giving remaining flows more bandwidth (multi-phase).

    Returns list of predicted durations (seconds) in same order as data_sizes.
    """
    N = len(data_sizes)
    active = list(range(N))
    remaining = [float(d) for d in data_sizes]
    completion_times = [0.0] * N
    current_time = 0.0

    while active:
        n = len(active)
        rate = bandwidth / n
        min_time = min(remaining[i] / rate for i in active)

        finishing = []
        for i in active:
            remaining[i] -= rate * min_time
            if remaining[i] < 1e-10:
                remaining[i] = 0.0
                completion_times[i] = current_time + min_time
                finishing.append(i)

        current_time += min_time
        for i in finishing:
            active.remove(i)

    return completion_times


def predict_hidden_cascade_durations(link_tx_positions, data_sizes, link_length=30):
    """Predict durations for N all-hidden-terminal links with cascading completions.

    As links complete, remaining links' SINR improves (fewer interferers),
    creating multi-phase behavior.

    link_tx_positions: list of (tx_x, tx_y) for each link's transmitter
                       (receiver is at (tx_x + link_length, tx_y))
    data_sizes: list of data sizes in MB

    Returns list of predicted durations (seconds).
    """
    N = len(link_tx_positions)
    active = list(range(N))
    remaining = [float(d) for d in data_sizes]
    completion_times = [0.0] * N
    current_time = 0.0

    while active:
        rates = {}
        for i in active:
            tx_x, tx_y = link_tx_positions[i]
            rx_x, rx_y = tx_x + link_length, tx_y
            interferer_dists = []
            for j in active:
                if j == i:
                    continue
                jtx_x, jtx_y = link_tx_positions[j]
                d = math.sqrt((jtx_x - rx_x)**2 + (jtx_y - rx_y)**2)
                interferer_dists.append(d)
            if interferer_dists:
                rates[i] = compute_multi_sinr_rate(link_length, interferer_dists)
            else:
                rates[i] = analytical_rate_at_distance(link_length)

        min_time = min(remaining[i] / rates[i] for i in active)

        finishing = []
        for i in active:
            remaining[i] -= rates[i] * min_time
            if remaining[i] < 1e-10:
                remaining[i] = 0.0
                completion_times[i] = current_time + min_time
                finishing.append(i)

        current_time += min_time
        for i in finishing:
            active.remove(i)

    return completion_times


# ─── Experiment 6: Per-Link Bandwidth Sharing ─────────────────────


def gen_exp6_yaml(data_sizes):
    """N source tasks on n0 → N sink tasks on n1, all sharing link l01."""
    yaml = (
        _yaml_header("exp6") +
        "  network:\n"
        "    nodes:\n"
        f"      - {{id: n0, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 0, y: 0}}}}\n"
        f"      - {{id: n1, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 30, y: 0}}}}\n"
        "    links:\n"
        "      - {id: l01, from: n0, to: n1}\n"
        "  dags:\n"
        "    - id: dag_1\n"
        "      inject_at: 0.0\n"
        "      tasks:\n"
    )
    for i in range(len(data_sizes)):
        yaml += (
            f"        - {{id: Ts{i}, compute_cost: {COMPUTE_COST}, pinned_to: n0}}\n"
            f"        - {{id: Td{i}, compute_cost: {COMPUTE_COST}, pinned_to: n1}}\n"
        )
    yaml += "      edges:\n"
    for i, ds in enumerate(data_sizes):
        yaml += f"        - {{from: Ts{i}, to: Td{i}, data_size: {ds}}}\n"
    yaml += _yaml_config()
    return yaml


def run_exp6():
    """Multiple flows on single link, tests per-link bandwidth fair sharing.

    Source tasks are FIFO queued on n0, creating a ~10us stagger between
    transfer starts. This is negligible vs ~2s transfer durations.
    """
    print("=" * 130)
    print("  Experiment 6: Per-Link Bandwidth Sharing")
    print("  N flows on link l01 (n0->n1, 30m), different data sizes")
    print("=" * 130)
    print()

    base_rate = analytical_rate_at_distance(30)
    print(f"  Base rate at 30m: {base_rate:.4f} MB/s (no interference, single link)")
    print()

    test_cases = [
        ("3-flow", [5.0, 10.0, 15.0]),
        ("3-flow-eq", [5.0, 5.0, 15.0]),       # Two finish simultaneously
        ("4-flow", [3.0, 6.0, 9.0, 12.0]),
    ]

    all_match = True
    for label, data_sizes in test_cases:
        run_label = f"exp6/{label}"
        print(f"  --- {run_label} (data={data_sizes}) ---")
        yaml = gen_exp6_yaml(data_sizes)
        outdir = run_scenario(yaml, run_label)
        if outdir is None:
            print("    FAILED to run")
            all_match = False
            continue

        transfers = parse_trace(outdir)
        pred_durs = predict_fair_share_durations(data_sizes, base_rate)

        sim_durs = {}
        for t in transfers:
            sim_durs[t["from_task"]] = t["duration"]

        ok = True
        for i, ds in enumerate(data_sizes):
            src_id = f"Ts{i}"
            sd = sim_durs.get(src_id, 0)
            pd = pred_durs[i]
            m = durations_match(sd, pd)
            if not m:
                ok = False
            print(f"    {src_id} ({ds:>5.1f}MB): pred={pd:.6f}s sim={sd:.6f}s {'OK' if m else 'FAIL'}")

        if not ok:
            all_match = False

    print()
    print(f"  All match: {'YES' if all_match else 'NO'}")
    print()
    return all_match


# ─── Experiment 7: N-Way Bianchi Scaling ──────────────────────────


def gen_exp7_yaml(n_links):
    """N parallel 30m links at 5m vertical separation (all within CS range)."""
    sep = 5
    yaml = _yaml_header(f"exp7_n{n_links}") + "  network:\n    nodes:\n"
    for i in range(n_links):
        y = i * sep
        yaml += (
            f"      - {{id: s{i}, compute_capacity: {COMPUTE_CAPACITY}, "
            f"position: {{x: 0, y: {y}}}}}\n"
            f"      - {{id: d{i}, compute_capacity: {COMPUTE_CAPACITY}, "
            f"position: {{x: 30, y: {y}}}}}\n"
        )
    yaml += "    links:\n"
    for i in range(n_links):
        yaml += f"      - {{id: l{i}, from: s{i}, to: d{i}}}\n"
    yaml += "  dags:\n    - id: dag_1\n      inject_at: 0.0\n      tasks:\n"
    for i in range(n_links):
        yaml += (
            f"        - {{id: Ts{i}, compute_cost: {COMPUTE_COST}, pinned_to: s{i}}}\n"
            f"        - {{id: Td{i}, compute_cost: {COMPUTE_COST}, pinned_to: d{i}}}\n"
        )
    yaml += "      edges:\n"
    for i in range(n_links):
        yaml += f"        - {{from: Ts{i}, to: Td{i}, data_size: {DATA_SIZE_MB}}}\n"
    yaml += _yaml_config()
    return yaml


def run_exp7():
    """Verify Bianchi efficiency scales correctly for N=2 through N=8.

    All N links are within carrier sensing range of each other (5m separation),
    forming a complete conflict graph. Same data size → single phase.
    """
    print("=" * 130)
    print("  Experiment 7: N-Way Bianchi Contention Scaling")
    print("  N parallel 30m links at 5m separation (all in conflict graph)")
    print("=" * 130)
    print()

    cs = carrier_sensing_range(RF)
    base_rate = analytical_rate_at_distance(30)
    print(f"  CS range: {cs:.1f}m | Base rate: {base_rate:.4f} MB/s")
    print()

    n_values = [2, 3, 4, 5, 6, 7, 8]

    results = []
    for n in n_values:
        label = f"exp7/n{n}"
        print(f"  Running {label}...", end=" ", flush=True)
        yaml = gen_exp7_yaml(n)
        outdir = run_scenario(yaml, label)
        if outdir is None:
            print("FAILED")
            results.append((n, None))
            continue

        transfers = parse_trace(outdir)
        sim_rates = [DATA_SIZE_MB / t["duration"] for t in transfers]

        eta_n = bianchi_efficiency(n)
        pred_rate = base_rate * eta_n / n

        match = all(rates_match(sr, pred_rate) for sr in sim_rates)
        sym = all(rates_match(sr, sim_rates[0]) for sr in sim_rates)
        avg_sim = sum(sim_rates) / len(sim_rates)
        results.append((n, eta_n, pred_rate, avg_sim, match and sym))
        print(f"avg_rate={avg_sim:.4f} pred={pred_rate:.4f} {'OK' if match and sym else 'FAIL'}")

    print()
    print(f"  {'N':>3s}  {'eta(N)':>8s}  {'eta/N':>8s}  "
          f"{'Pred':>8s}  {'Sim_avg':>8s}  {'Match':>5s}")
    print(f"  {'---':>3s}  {'------':>8s}  {'-----':>8s}  "
          f"{'----':>8s}  {'-------':>8s}  {'-----':>5s}")

    all_match = True
    for r in results:
        if r[1] is None:
            print(f"  {r[0]:>3d}  {'ERROR':>8s}")
            all_match = False
            continue
        n, eta_n, pred, avg_sim, match = r
        if not match:
            all_match = False
        print(f"  {n:>3d}  {eta_n:>8.4f}  {eta_n/n:>8.4f}  "
              f"{pred:>8.4f}  {avg_sim:>8.4f}  {'OK' if match else 'FAIL':>5s}")

    print()
    print(f"  All match: {'YES' if all_match else 'NO'}")
    print()
    return all_match


# ─── Experiment 8: Five-Link Hidden Terminal Cascade ──────────────


def gen_exp8_yaml(data_sizes, sep=100):
    """N parallel 30m links at `sep`m vertical separation, varying data sizes."""
    n_links = len(data_sizes)
    yaml = _yaml_header(f"exp8_n{n_links}") + "  network:\n    nodes:\n"
    for i in range(n_links):
        y = i * sep
        yaml += (
            f"      - {{id: s{i}, compute_capacity: {COMPUTE_CAPACITY}, "
            f"position: {{x: 0, y: {y}}}}}\n"
            f"      - {{id: d{i}, compute_capacity: {COMPUTE_CAPACITY}, "
            f"position: {{x: 30, y: {y}}}}}\n"
        )
    yaml += "    links:\n"
    for i in range(n_links):
        yaml += f"      - {{id: l{i}, from: s{i}, to: d{i}}}\n"
    yaml += "  dags:\n    - id: dag_1\n      inject_at: 0.0\n      tasks:\n"
    for i in range(n_links):
        yaml += (
            f"        - {{id: Ts{i}, compute_cost: {COMPUTE_COST}, pinned_to: s{i}}}\n"
            f"        - {{id: Td{i}, compute_cost: {COMPUTE_COST}, pinned_to: d{i}}}\n"
        )
    yaml += "      edges:\n"
    for i in range(n_links):
        yaml += f"        - {{from: Ts{i}, to: Td{i}, data_size: {data_sizes[i]}}}\n"
    yaml += _yaml_config()
    return yaml


def run_exp8():
    """5 hidden-terminal links with cascading phase transitions.

    Tests data_remaining tracking through 4+ recalculation phases, SINR
    recomputation with shrinking active link sets, and correct completion
    ordering when links have different rates due to asymmetric geometry.
    """
    print("=" * 130)
    print("  Experiment 8: Five-Link Hidden Terminal Cascade")
    print("  5 parallel 30m links at 100m separation, different data sizes")
    print("=" * 130)
    print()

    sep = 100
    base_rate = analytical_rate_at_distance(30)
    print(f"  Base rate (solo): {base_rate:.4f} MB/s | Separation: {sep}m")
    print()

    data_sizes = [2.0, 4.0, 6.0, 8.0, 10.0]
    link_tx_positions = [(0, i * sep) for i in range(len(data_sizes))]

    label = "exp8/cascade5"
    print(f"  Running {label}...", end=" ", flush=True)
    yaml = gen_exp8_yaml(data_sizes, sep)
    outdir = run_scenario(yaml, label)
    if outdir is None:
        print("FAILED")
        return False

    transfers = parse_trace(outdir)
    pred_durs = predict_hidden_cascade_durations(link_tx_positions, data_sizes)

    sim_durs = {}
    for t in transfers:
        sim_durs[t["from_task"]] = t["duration"]

    print("done")
    print()
    print(f"  {'Link':>6s}  {'Data(MB)':>8s}  {'Pred_dur':>10s}  {'Sim_dur':>10s}  {'Match':>5s}")
    print(f"  {'------':>6s}  {'--------':>8s}  {'--------':>10s}  {'-------':>10s}  {'-----':>5s}")

    all_match = True
    for i in range(len(data_sizes)):
        src_id = f"Ts{i}"
        sd = sim_durs.get(src_id, 0)
        pd = pred_durs[i]
        m = durations_match(sd, pd)
        if not m:
            all_match = False
        print(f"  l{i:>5d}  {data_sizes[i]:>8.1f}  {pd:>10.6f}  {sd:>10.6f}  {'OK' if m else 'FAIL':>5s}")

    print()
    print(f"  All match: {'YES' if all_match else 'NO'}")
    print()
    return all_match


# ─── Experiment 9: Combined Bandwidth Sharing + Interference ──────


def gen_exp9_yaml(data_a1, data_a2, data_b):
    """2 flows on link l01 + 1 flow on link l23 (hidden terminal at 100m)."""
    return (
        _yaml_header("exp9") +
        "  network:\n"
        "    nodes:\n"
        f"      - {{id: n0, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 0, y: 0}}}}\n"
        f"      - {{id: n1, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 30, y: 0}}}}\n"
        f"      - {{id: n2, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 0, y: 100}}}}\n"
        f"      - {{id: n3, compute_capacity: {COMPUTE_CAPACITY}, position: {{x: 30, y: 100}}}}\n"
        "    links:\n"
        "      - {id: l01, from: n0, to: n1}\n"
        "      - {id: l23, from: n2, to: n3}\n"
        "  dags:\n"
        "    - id: dag_1\n"
        "      inject_at: 0.0\n"
        "      tasks:\n"
        f"        - {{id: Ta0, compute_cost: {COMPUTE_COST}, pinned_to: n0}}\n"
        f"        - {{id: Ta1, compute_cost: {COMPUTE_COST}, pinned_to: n1}}\n"
        f"        - {{id: Tb0, compute_cost: {COMPUTE_COST}, pinned_to: n0}}\n"
        f"        - {{id: Tb1, compute_cost: {COMPUTE_COST}, pinned_to: n1}}\n"
        f"        - {{id: Tc0, compute_cost: {COMPUTE_COST}, pinned_to: n2}}\n"
        f"        - {{id: Tc1, compute_cost: {COMPUTE_COST}, pinned_to: n3}}\n"
        "      edges:\n"
        f"        - {{from: Ta0, to: Ta1, data_size: {data_a1}}}\n"
        f"        - {{from: Tb0, to: Tb1, data_size: {data_a2}}}\n"
        f"        - {{from: Tc0, to: Tc1, data_size: {data_b}}}\n" +
        _yaml_config()
    )


def predict_exp9_durations(data_a1, data_a2, data_b):
    """Predict durations for 2 flows on l01 + 1 flow on l23 (hidden terminals).

    l01 and l23 are 100m apart (hidden terminals, no conflict graph edge).
    l01 has 2 flows sharing bandwidth via fair share.

    Returns (dur_a1, dur_a2, dur_b).
    """
    base = analytical_rate_at_distance(30)
    i_dist = math.sqrt(900 + 10000)  # sqrt(30^2 + 100^2)
    sinr = compute_sinr_rate(30, i_dist)

    flows = {
        'a1': {'remaining': float(data_a1), 'link': 'l01', 'time': 0.0},
        'a2': {'remaining': float(data_a2), 'link': 'l01', 'time': 0.0},
        'b':  {'remaining': float(data_b),  'link': 'l23', 'time': 0.0},
    }
    current_time = 0.0
    done = set()

    while len(done) < len(flows):
        active = {k: v for k, v in flows.items() if k not in done}

        l01_active = any(f['link'] == 'l01' for f in active.values())
        l23_active = any(f['link'] == 'l23' for f in active.values())

        rates = {}
        for k, f in active.items():
            if f['link'] == 'l01':
                link_bw = sinr if l23_active else base
                n_flows = sum(1 for ff in active.values() if ff['link'] == 'l01')
                rates[k] = link_bw / n_flows
            else:
                link_bw = sinr if l01_active else base
                n_flows = sum(1 for ff in active.values() if ff['link'] == 'l23')
                rates[k] = link_bw / n_flows

        min_time = min(f['remaining'] / rates[k] for k, f in active.items())

        for k, f in active.items():
            f['remaining'] -= rates[k] * min_time
            if f['remaining'] < 1e-10:
                f['remaining'] = 0.0
                f['time'] = current_time + min_time
                done.add(k)
        current_time += min_time

    return flows['a1']['time'], flows['a2']['time'], flows['b']['time']


def run_exp9():
    """Tests combined per-link bandwidth sharing + hidden terminal interference.

    Two flows share link l01 while a third flow on l23 (100m away) acts as
    a hidden terminal. Tests phase transitions as flows complete: interference
    goes away when l23 finishes, bandwidth sharing changes when a l01 flow finishes.
    """
    print("=" * 130)
    print("  Experiment 9: Combined Bandwidth Sharing + Hidden Terminal Interference")
    print("  2 flows on l01 (n0->n1) + 1 flow on l23 (n2->n3), 100m apart")
    print("=" * 130)
    print()

    base_rate = analytical_rate_at_distance(30)
    i_dist = math.sqrt(900 + 10000)
    sinr_rate = compute_sinr_rate(30, i_dist)
    print(f"  Base rate: {base_rate:.4f} MB/s | SINR rate (100m hidden): {sinr_rate:.4f} MB/s")
    print()

    test_cases = [
        ("case1", 5.0, 10.0, 8.0),    # B finishes first
        ("case2", 5.0, 10.0, 3.0),    # B finishes earliest
        ("case3", 3.0, 15.0, 20.0),   # A1 on l01 finishes first
    ]

    all_match = True
    for label, da1, da2, db in test_cases:
        run_label = f"exp9/{label}"
        print(f"  --- {run_label} (l01: {da1}/{da2}MB, l23: {db}MB) ---")
        yaml = gen_exp9_yaml(da1, da2, db)
        outdir = run_scenario(yaml, run_label)
        if outdir is None:
            print("    FAILED to run")
            all_match = False
            continue

        transfers = parse_trace(outdir)
        pred_a1, pred_a2, pred_b = predict_exp9_durations(da1, da2, db)

        sim = {}
        for t in transfers:
            sim[t["from_task"]] = t["duration"]

        sim_a1 = sim.get("Ta0", 0)
        sim_a2 = sim.get("Tb0", 0)
        sim_b = sim.get("Tc0", 0)

        ma1 = durations_match(sim_a1, pred_a1)
        ma2 = durations_match(sim_a2, pred_a2)
        mb = durations_match(sim_b, pred_b)
        ok = ma1 and ma2 and mb
        if not ok:
            all_match = False

        print(f"    Ta0 ({da1:>5.1f}MB l01): pred={pred_a1:.6f} sim={sim_a1:.6f} {'OK' if ma1 else 'FAIL'}")
        print(f"    Tb0 ({da2:>5.1f}MB l01): pred={pred_a2:.6f} sim={sim_a2:.6f} {'OK' if ma2 else 'FAIL'}")
        print(f"    Tc0 ({db:>5.1f}MB l23): pred={pred_b:.6f} sim={sim_b:.6f} {'OK' if mb else 'FAIL'}")

    print()
    print(f"  All match: {'YES' if all_match else 'NO'}")
    print()
    return all_match


# ─── Main ────────────────────────────────────────────────────────


def main():
    os.makedirs(OUTDIR, exist_ok=True)

    cs = carrier_sensing_range(RF)

    print()
    print("=" * 95)
    print("  ncsim Interference Model Verification")
    print(f"  Model: csma_bianchi | Standard: 802.11{RF.wifi_standard}")
    print(f"  TX power: {RF.tx_power_dBm} dBm | Freq: {RF.freq_ghz} GHz | "
          f"Path loss exp: {RF.path_loss_exponent}")
    print(f"  Noise floor: {RF.noise_floor_dBm} dBm | CCA threshold: {RF.cca_threshold_dBm} dBm")
    print(f"  Carrier sensing range: {cs:.1f}m")
    print(f"  Data size: {DATA_SIZE_MB} MB | Tolerance: {TOLERANCE*100:.0f}%")
    print("=" * 95)
    print()

    m1 = run_exp1()
    m2 = run_exp2()
    m3 = run_exp3()
    m4 = run_exp4()
    m5 = run_exp5()
    m6 = run_exp6()
    m7 = run_exp7()
    m8 = run_exp8()
    m9 = run_exp9()

    print("=" * 95)
    print("  Summary")
    print("=" * 95)
    print(f"  Experiment 1 (Link Length vs Rate):            {'PASS' if m1 else 'FAIL'}")
    print(f"  Experiment 2 (Parallel Link Separation):       {'PASS' if m2 else 'FAIL'}")
    print(f"  Experiment 3 (Two TX to Same RX):              {'PASS' if m3 else 'FAIL'}")
    print(f"  Experiment 4 (Three Parallel Links):           {'PASS' if m4 else 'FAIL'}")
    print(f"  Experiment 5 (Staggered Transfer Start):       {'PASS' if m5 else 'FAIL'}")
    print(f"  Experiment 6 (Per-Link Bandwidth Sharing):     {'PASS' if m6 else 'FAIL'}")
    print(f"  Experiment 7 (N-Way Bianchi Scaling):          {'PASS' if m7 else 'FAIL'}")
    print(f"  Experiment 8 (Five-Link Hidden Cascade):       {'PASS' if m8 else 'FAIL'}")
    print(f"  Experiment 9 (Combined Sharing+Interference):  {'PASS' if m9 else 'FAIL'}")
    print()
    all_pass = m1 and m2 and m3 and m4 and m5 and m6 and m7 and m8 and m9
    print(f"  Overall: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
    print()
    print(f"  Trace files saved to: {OUTDIR}")
    print()

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())

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
- Hidden terminals do NOT trigger recalculation of already-active transfers,
  so the first transfer to start sees no interference while the second sees
  the first as a hidden terminal (asymmetric).
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


def rates_match(sim, pred):
    """Check if simulated rate matches predicted within tolerance."""
    if pred == 0 and sim == 0:
        return True
    if pred == 0:
        return False
    return abs(sim - pred) / pred <= TOLERANCE


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
    When hidden terminal (sep > CS range): asymmetric — first-started link
    (l01, by event ordering) sees no interference; second-started link (l23)
    sees SINR degradation from the first. Hidden terminals do not trigger
    recalculation of already-active transfers.
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
            # Hidden terminal — asymmetric:
            # l01 starts first (lower seq), sees no interference -> full base rate
            pred_a = base_rate
            # l23 starts second, sees l01 as hidden terminal -> SINR degradation
            # l23 rx = n3(30,sep), interferer tx = n0(0,0)
            # interferer distance = sqrt(30^2 + sep^2)
            i_dist = math.sqrt(30**2 + sep**2)
            pred_b = compute_sinr_rate(30, i_dist)

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
    return all_match


# ─── Experiment 3: Two Transmitters to Same Receiver ─────────────


def run_exp3():
    """Two TX nodes send to shared RX at origin, varying distance.

    When in conflict (d <= CS range): symmetric Bianchi contention.
    When hidden terminal (d > CS range): asymmetric — l10 (first by seq)
    sees no interference (full base rate), l20 sees SINR degradation
    from l10's transmitter. Equal-power interferer at same distance
    yields SINR ~= -0.25 dB (rate=0), so model clamps to min factor.
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
            # Hidden terminal — asymmetric:
            # l10 starts first (lower seq), no interference -> full base rate
            pred_l10 = base_rate
            # l20 starts second, interferer = n1(d,0) at distance d from n0
            # Equal-power interferer at same distance as desired signal
            pred_l20 = compute_sinr_rate(d, d)

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

    print("=" * 95)
    print("  Summary")
    print("=" * 95)
    print(f"  Experiment 1 (Link Length vs Rate):           {'PASS' if m1 else 'FAIL'}")
    print(f"  Experiment 2 (Parallel Link Separation):      {'PASS' if m2 else 'FAIL'}")
    print(f"  Experiment 3 (Two TX to Same RX):             {'PASS' if m3 else 'FAIL'}")
    print()
    all_pass = m1 and m2 and m3
    print(f"  Overall: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
    print()
    print(f"  Trace files saved to: {OUTDIR}")
    print()

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())

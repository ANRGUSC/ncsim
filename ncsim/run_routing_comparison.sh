#!/usr/bin/env bash
# run_routing_comparison.sh — Compare direct vs widest-path routing across all scenarios
#
# Usage: cd ncsim && bash run_routing_comparison.sh [output_dir]
#
# Runs unit tests, then executes all scenarios with both routing modes
# and prints a comparison table.

set -euo pipefail

OUTDIR="${1:-/tmp/ncsim_routing_comparison}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo " ncsim Routing Comparison Test Suite"
echo "============================================"
echo ""

# ── Step 1: Run pytest ──
echo "── Step 1: Unit & Integration Tests ──"
echo ""
python -m pytest tests/ -v
echo ""

# ── Step 2: Simulation runs ──
echo "── Step 2: Simulation Comparisons ──"
echo ""
echo "Output directory: $OUTDIR"
mkdir -p "$OUTDIR"

run_scenario() {
    local name="$1"
    local scenario="$2"
    local routing="$3"
    local scheduler="${4:-heft}"
    local outdir="$OUTDIR/${name}"
    mkdir -p "$outdir"
    python -m ncsim \
        --scenario "$scenario" \
        --output "$outdir" \
        --routing "$routing" \
        --scheduler "$scheduler" \
        --seed 42 2>&1 | tail -1
}

echo ""
echo "--- Test A: demo_simple (baseline, direct link exists) ---"
run_scenario "demo_simple_direct" "scenarios/demo_simple.yaml" "direct"
run_scenario "demo_simple_wp"     "scenarios/demo_simple.yaml" "widest_path"

echo ""
echo "--- Test B: bandwidth_contention (shared link) ---"
run_scenario "bw_contention_direct" "scenarios/bandwidth_contention.yaml" "direct" "round_robin"
run_scenario "bw_contention_wp"     "scenarios/bandwidth_contention.yaml" "widest_path" "round_robin"

echo ""
echo "--- Test C: multi_hop_forced (pinned tasks, no direct link) ---"
run_scenario "mhop_forced_direct" "scenarios/multi_hop_forced.yaml" "direct"
run_scenario "mhop_forced_wp"     "scenarios/multi_hop_forced.yaml" "widest_path"

echo ""
echo "--- Test D: multi_hop_test (unpinned, 3 homogeneous nodes) ---"
run_scenario "mhop_test_direct" "scenarios/multi_hop_test.yaml" "direct"
run_scenario "mhop_test_wp"     "scenarios/multi_hop_test.yaml" "widest_path"

echo ""
echo "--- Test E: multihop_advantage (pinned, heterogeneous nodes) ---"
run_scenario "advantage_baseline" "scenarios/multihop_advantage.yaml" "direct" "round_robin"
run_scenario "advantage_wp"       "scenarios/multihop_advantage.yaml" "widest_path" "round_robin"

echo ""
echo "--- Test F: parallel_spread (HEFT, 5 nodes, 8 parallel tasks) ---"
run_scenario "parallel_direct" "scenarios/parallel_spread.yaml" "direct"
run_scenario "parallel_wp"     "scenarios/parallel_spread.yaml" "widest_path"

# ── Step 3: Summary table ──
echo ""
echo "============================================"
echo " Results Summary"
echo "============================================"
echo ""
printf "%-30s %10s %10s %10s\n" "Scenario" "Direct" "WidestPath" "Speedup"
printf "%-30s %10s %10s %10s\n" "--------" "------" "----------" "-------"

print_comparison() {
    local label="$1"
    local dir_d="$2"
    local dir_w="$3"
    local ms_d ms_w speedup
    ms_d=$(python -c "import json; print(json.load(open('$OUTDIR/$dir_d/metrics.json'))['makespan'])")
    ms_w=$(python -c "import json; print(json.load(open('$OUTDIR/$dir_w/metrics.json'))['makespan'])")
    speedup=$(python -c "d=$ms_d; w=$ms_w; print(f'{((d-w)/d)*100:.1f}%' if d!=w else 'same')")
    printf "%-30s %9.3fs %9.3fs %10s\n" "$label" "$ms_d" "$ms_w" "$speedup"
}

print_comparison "A: demo_simple"         "demo_simple_direct"   "demo_simple_wp"
print_comparison "B: bandwidth_contention" "bw_contention_direct" "bw_contention_wp"
print_comparison "C: multi_hop_forced"    "mhop_forced_direct"   "mhop_forced_wp"
print_comparison "D: multi_hop_test"      "mhop_test_direct"     "mhop_test_wp"
print_comparison "E: multihop_advantage"  "advantage_baseline"   "advantage_wp"
print_comparison "F: parallel_spread"     "parallel_direct"      "parallel_wp"

echo ""
echo "NOTE: Negative speedup in C means direct routing silently skipped"
echo "the transfer (incorrect result). Widest-path is slower but correct."
echo ""

# ── Step 4: Gantt charts for key scenarios ──
echo "============================================"
echo " Gantt Charts (Key Scenarios)"
echo "============================================"

echo ""
echo "--- E: multihop_advantage (baseline, both on slow node) ---"
python analyze_trace.py "$OUTDIR/advantage_baseline/trace.jsonl" --gantt

echo ""
echo "--- E: multihop_advantage (widest_path, T1 on fast node) ---"
python analyze_trace.py "$OUTDIR/advantage_wp/trace.jsonl" --gantt

echo ""
echo "--- F: parallel_spread (direct, 3 nodes) ---"
python analyze_trace.py "$OUTDIR/parallel_direct/trace.jsonl" --gantt

echo ""
echo "--- F: parallel_spread (widest_path, 5 nodes) ---"
python analyze_trace.py "$OUTDIR/parallel_wp/trace.jsonl" --gantt

echo ""
echo "Trace files saved to: $OUTDIR"
echo "To inspect any trace: python analyze_trace.py <trace.jsonl> --gantt --timeline --tasks"

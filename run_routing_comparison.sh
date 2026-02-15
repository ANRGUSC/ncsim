#!/usr/bin/env bash
# run_routing_comparison.sh — Compare direct vs widest-path vs shortest-path routing across all scenarios
#
# Usage: cd ncsim && bash run_routing_comparison.sh [output_dir]
#
# Runs unit tests, then executes all scenarios with all three routing modes
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
run_scenario "demo_simple_sp"     "scenarios/demo_simple.yaml" "shortest_path"

echo ""
echo "--- Test B: bandwidth_contention (shared link) ---"
run_scenario "bw_contention_direct" "scenarios/bandwidth_contention.yaml" "direct" "round_robin"
run_scenario "bw_contention_wp"     "scenarios/bandwidth_contention.yaml" "widest_path" "round_robin"
run_scenario "bw_contention_sp"     "scenarios/bandwidth_contention.yaml" "shortest_path" "round_robin"

echo ""
echo "--- Test C: multi_hop_forced (pinned tasks, no direct link) ---"
run_scenario "mhop_forced_direct" "scenarios/multi_hop_forced.yaml" "direct"
run_scenario "mhop_forced_wp"     "scenarios/multi_hop_forced.yaml" "widest_path"
run_scenario "mhop_forced_sp"     "scenarios/multi_hop_forced.yaml" "shortest_path"

echo ""
echo "--- Test D: multi_hop_test (unpinned, 3 homogeneous nodes) ---"
run_scenario "mhop_test_direct" "scenarios/multi_hop_test.yaml" "direct"
run_scenario "mhop_test_wp"     "scenarios/multi_hop_test.yaml" "widest_path"
run_scenario "mhop_test_sp"     "scenarios/multi_hop_test.yaml" "shortest_path"

echo ""
echo "--- Test E: multihop_advantage (pinned, heterogeneous nodes) ---"
run_scenario "advantage_baseline" "scenarios/multihop_advantage.yaml" "direct" "round_robin"
run_scenario "advantage_wp"       "scenarios/multihop_advantage.yaml" "widest_path" "round_robin"
run_scenario "advantage_sp"       "scenarios/multihop_advantage.yaml" "shortest_path" "round_robin"

echo ""
echo "--- Test G: widest_vs_shortest (diamond, asymmetric paths — WP and SP diverge) ---"
run_scenario "wvs_direct" "scenarios/widest_vs_shortest.yaml" "direct" "round_robin"
run_scenario "wvs_wp"     "scenarios/widest_vs_shortest.yaml" "widest_path" "round_robin"
run_scenario "wvs_sp"     "scenarios/widest_vs_shortest.yaml" "shortest_path" "round_robin"

echo ""
echo "--- Test F: parallel_spread (HEFT, 5 nodes, 8 parallel tasks) ---"
run_scenario "parallel_direct" "scenarios/parallel_spread.yaml" "direct"
run_scenario "parallel_wp"     "scenarios/parallel_spread.yaml" "widest_path"
run_scenario "parallel_sp"     "scenarios/parallel_spread.yaml" "shortest_path"

# ── Step 3: Summary table ──
echo ""
echo "============================================"
echo " Results Summary"
echo "============================================"
echo ""
printf "%-30s %10s %10s %12s %10s %10s\n" "Scenario" "Direct" "WidestPath" "ShortestPath" "WP vs D" "SP vs D"
printf "%-30s %10s %10s %12s %10s %10s\n" "--------" "------" "----------" "------------" "-------" "-------"

print_comparison() {
    local label="$1"
    local dir_d="$2"
    local dir_w="$3"
    local dir_s="$4"
    local ms_d ms_w ms_s speedup_w speedup_s status_d
    status_d=$(python -c "import json; print(json.load(open('$OUTDIR/$dir_d/metrics.json')).get('status','completed'))")
    if [ "$status_d" = "error" ]; then
        ms_w=$(python -c "import json; print(json.load(open('$OUTDIR/$dir_w/metrics.json'))['makespan'])")
        ms_s=$(python -c "import json; print(json.load(open('$OUTDIR/$dir_s/metrics.json'))['makespan'])")
        printf "%-30s %10s %9.3fs %11.3fs %10s %10s\n" "$label" "ERROR" "$ms_w" "$ms_s" "n/a" "n/a"
        return
    fi
    ms_d=$(python -c "import json; print(json.load(open('$OUTDIR/$dir_d/metrics.json'))['makespan'])")
    ms_w=$(python -c "import json; print(json.load(open('$OUTDIR/$dir_w/metrics.json'))['makespan'])")
    ms_s=$(python -c "import json; print(json.load(open('$OUTDIR/$dir_s/metrics.json'))['makespan'])")
    speedup_w=$(python -c "d=$ms_d; w=$ms_w; print(f'{((d-w)/d)*100:.1f}%' if d!=w else 'same')")
    speedup_s=$(python -c "d=$ms_d; s=$ms_s; print(f'{((d-s)/d)*100:.1f}%' if d!=s else 'same')")
    printf "%-30s %9.3fs %9.3fs %11.3fs %10s %10s\n" "$label" "$ms_d" "$ms_w" "$ms_s" "$speedup_w" "$speedup_s"
}

print_comparison "A: demo_simple"         "demo_simple_direct"   "demo_simple_wp"     "demo_simple_sp"
print_comparison "B: bandwidth_contention" "bw_contention_direct" "bw_contention_wp"   "bw_contention_sp"
print_comparison "C: multi_hop_forced"    "mhop_forced_direct"   "mhop_forced_wp"     "mhop_forced_sp"
print_comparison "D: multi_hop_test"      "mhop_test_direct"     "mhop_test_wp"       "mhop_test_sp"
print_comparison "E: multihop_advantage"  "advantage_baseline"   "advantage_wp"       "advantage_sp"
print_comparison "G: widest_vs_shortest"  "wvs_direct"           "wvs_wp"             "wvs_sp"
print_comparison "F: parallel_spread"     "parallel_direct"      "parallel_wp"        "parallel_sp"

echo ""
echo "NOTE: ERROR means the routing model has no path for that topology."
echo "Direct routing requires explicit links; multi-hop topologies need widest_path or shortest_path."
echo ""

# ── Step 4: Gantt charts for key scenarios ──
echo "============================================"
echo " Gantt Charts (Key Scenarios)"
echo "============================================"

echo ""
echo "--- G: widest_vs_shortest (widest_path — picks wide/slow route, 2.6s) ---"
python analyze_trace.py "$OUTDIR/wvs_wp/trace.jsonl" --gantt

echo ""
echo "--- G: widest_vs_shortest (shortest_path — picks fast/narrow route, 7.0s) ---"
python analyze_trace.py "$OUTDIR/wvs_sp/trace.jsonl" --gantt

echo ""
echo "--- E: multihop_advantage (baseline=direct, errored — no direct link) ---"
echo "  Skipped: direct routing has no path for this topology"

echo ""
echo "--- E: multihop_advantage (widest_path, T1 on fast node) ---"
python analyze_trace.py "$OUTDIR/advantage_wp/trace.jsonl" --gantt

echo ""
echo "--- E: multihop_advantage (shortest_path) ---"
python analyze_trace.py "$OUTDIR/advantage_sp/trace.jsonl" --gantt

echo ""
echo "--- F: parallel_spread (direct, 3 nodes) ---"
python analyze_trace.py "$OUTDIR/parallel_direct/trace.jsonl" --gantt

echo ""
echo "--- F: parallel_spread (widest_path, 5 nodes) ---"
python analyze_trace.py "$OUTDIR/parallel_wp/trace.jsonl" --gantt

echo ""
echo "--- F: parallel_spread (shortest_path, 5 nodes) ---"
python analyze_trace.py "$OUTDIR/parallel_sp/trace.jsonl" --gantt

echo ""
echo "Trace files saved to: $OUTDIR"
echo "To inspect any trace: python analyze_trace.py <trace.jsonl> --gantt --timeline --tasks"

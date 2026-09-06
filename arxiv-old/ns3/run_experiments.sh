#!/bin/bash
# Run ns-3 cross-validation experiments for ncsim paper.
# Executed inside Docker container.
set -e

OUTDIR="/results"
SIMTIME=30
SEEDS=20

echo "=== ns-3 Cross-Validation Experiments ==="
echo "Seeds per point: $SEEDS"
echo "Sim time: ${SIMTIME}s"
echo ""

# ── Experiment 1: N-Way Contention Scaling ──
echo "--- Experiment 1: Contention Scaling (n=1..8) ---"
for n in 1 2 3 4 5 6 7 8; do
    for s in $(seq 1 $SEEDS); do
        ./ns3 run scratch/contention_scaling -- \
            --nLinks=$n --seed=$s --simTime=$SIMTIME --outDir=$OUTDIR
    done
    echo "  n=$n complete ($SEEDS seeds)"
done

# ── Experiment 2a: Separation Sweep (Fixed MCS5) ──
echo ""
echo "--- Experiment 2a: Separation Sweep (Fixed MCS) ---"
for sep in 10 20 30 40 50 60 65 70 72 75 80 90 100 120 150 200; do
    for s in $(seq 1 $SEEDS); do
        ./ns3 run scratch/separation_sweep -- \
            --separation=$sep --seed=$s --simTime=$SIMTIME \
            --idealMcs=false --outDir=$OUTDIR
    done
    echo "  sep=${sep}m complete ($SEEDS seeds)"
done

# ── Experiment 2b: Separation Sweep (Ideal MCS) ──
echo ""
echo "--- Experiment 2b: Separation Sweep (Ideal MCS) ---"
for sep in 10 20 30 40 50 60 65 70 72 75 80 90 100 120 150 200; do
    for s in $(seq 1 $SEEDS); do
        ./ns3 run scratch/separation_sweep -- \
            --separation=$sep --seed=$s --simTime=$SIMTIME \
            --idealMcs=true --outDir=$OUTDIR
    done
    echo "  sep=${sep}m complete ($SEEDS seeds)"
done

echo ""
echo "=== All experiments complete. Results in $OUTDIR ==="

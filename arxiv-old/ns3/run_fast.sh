#!/bin/bash
# Fast experiment runner — calls compiled binaries directly (no ./ns3 run overhead).
set -e

OUTDIR="/results"
SIMTIME=30
SEEDS=20

# Locate compiled binaries
CONT_BIN=$(find /opt/ns-3.41/build -name "*contention_scaling" -type f 2>/dev/null | head -1)
SEP_BIN=$(find /opt/ns-3.41/build -name "*separation_sweep" -type f 2>/dev/null | head -1)

if [ -z "$CONT_BIN" ] || [ -z "$SEP_BIN" ]; then
    echo "ERROR: Cannot find compiled binaries"
    exit 1
fi

echo "Contention binary: $CONT_BIN"
echo "Separation binary: $SEP_BIN"
echo "Seeds: $SEEDS, SimTime: ${SIMTIME}s"
echo ""

# Set ns-3 library path
export LD_LIBRARY_PATH=/opt/ns-3.41/build/lib:$LD_LIBRARY_PATH

# ── Experiment 1: Contention Scaling ──
echo "=== Experiment 1: Contention Scaling (n=1..8) ==="
for n in 1 2 3 4 5 6 7 8; do
    for s in $(seq 1 $SEEDS); do
        $CONT_BIN --nLinks=$n --seed=$s --simTime=$SIMTIME --outDir=$OUTDIR
    done
    # Print sample result for this n
    SAMPLE=$(ls ${OUTDIR}/contention_n${n}_s1.csv 2>/dev/null)
    if [ -n "$SAMPLE" ]; then
        echo "  n=$n done ($SEEDS seeds). Sample: $(tail -1 $SAMPLE)"
    fi
done
echo "Exp 1 complete. Files: $(ls ${OUTDIR}/contention_*.csv 2>/dev/null | wc -l)"

# ── Experiment 2a: Separation Sweep (Fixed MCS) ──
echo ""
echo "=== Experiment 2a: Separation Sweep (Fixed MCS) ==="
for sep in 10 20 30 40 50 60 65 70 72 75 80 90 100 120 150 200; do
    for s in $(seq 1 $SEEDS); do
        $SEP_BIN --separation=$sep --seed=$s --simTime=$SIMTIME --idealMcs=false --outDir=$OUTDIR
    done
    SAMPLE=$(ls ${OUTDIR}/separation_s${sep}_fixed_seed1.csv 2>/dev/null)
    if [ -n "$SAMPLE" ]; then
        echo "  sep=${sep}m done. Sample: $(tail -1 $SAMPLE)"
    fi
done
echo "Exp 2a complete. Files: $(ls ${OUTDIR}/separation_*_fixed_*.csv 2>/dev/null | wc -l)"

# ── Experiment 2b: Separation Sweep (Ideal MCS) ──
echo ""
echo "=== Experiment 2b: Separation Sweep (Ideal MCS) ==="
for sep in 10 20 30 40 50 60 65 70 72 75 80 90 100 120 150 200; do
    for s in $(seq 1 $SEEDS); do
        $SEP_BIN --separation=$sep --seed=$s --simTime=$SIMTIME --idealMcs=true --outDir=$OUTDIR
    done
    SAMPLE=$(ls ${OUTDIR}/separation_s${sep}_ideal_seed1.csv 2>/dev/null)
    if [ -n "$SAMPLE" ]; then
        echo "  sep=${sep}m done. Sample: $(tail -1 $SAMPLE)"
    fi
done
echo "Exp 2b complete. Files: $(ls ${OUTDIR}/separation_*_ideal_*.csv 2>/dev/null | wc -l)"

echo ""
echo "=== ALL DONE ==="
echo "Total CSV files: $(ls ${OUTDIR}/*.csv 2>/dev/null | wc -l)"

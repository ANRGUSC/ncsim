#!/bin/bash
# Build Docker image and run ns-3 experiments.
# Run from paper/ns3/ directory.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"

mkdir -p "$RESULTS_DIR"

echo "Building ns-3 Docker image (first run takes ~10 min)..."
docker build -t ncsim-ns3 "$SCRIPT_DIR"

echo ""
echo "Running experiments (results -> $RESULTS_DIR)..."
docker run --rm \
    -v "$RESULTS_DIR:/results" \
    ncsim-ns3

echo ""
echo "Done. Results in: $RESULTS_DIR/"
ls -la "$RESULTS_DIR"/*.csv 2>/dev/null | head -20
echo "..."
echo "Total CSV files: $(ls "$RESULTS_DIR"/*.csv 2>/dev/null | wc -l)"

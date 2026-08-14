#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
DEMO_OUTPUT="${REPO_ROOT}/results/codespaces-demo"

if ! command -v ncsim >/dev/null 2>&1; then
  echo "ERROR: The ncsim CLI is unavailable. Run: bash .devcontainer/setup.sh" >&2
  exit 1
fi

if [[ ! -d "${REPO_ROOT}/viz/node_modules" ]]; then
  echo "ERROR: Visualization dependencies are unavailable. Run: bash .devcontainer/setup.sh" >&2
  exit 1
fi

for output_file in scenario.yaml trace.jsonl metrics.json; do
  if [[ ! -s "${DEMO_OUTPUT}/${output_file}" ]]; then
    echo "ERROR: Demo output is missing or empty: ${DEMO_OUTPUT}/${output_file}. Run: bash .devcontainer/setup.sh" >&2
    exit 1
  fi
done

cat <<EOF

NCSim Codespaces setup is ready.

UI:
  The visualization starts automatically on forwarded port 5173.
  To open it manually, use the bottom Ports tab, hover over port 5173,
  and select the globe (Open in Browser).
  If port 5173 is absent, run: bash .devcontainer/start-viz.sh

CLI:
  ncsim --scenario scenarios/demo_simple.yaml --output results/my-run
  python analyze_trace.py results/codespaces-demo/trace.jsonl --gantt --timeline --tasks

Demo files:
  results/codespaces-demo/scenario.yaml
  results/codespaces-demo/trace.jsonl
  results/codespaces-demo/metrics.json
EOF

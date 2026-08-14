#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
DEMO_OUTPUT="${REPO_ROOT}/results/codespaces-demo"

echo "==> Installing NCSim and development dependencies"
(
  cd "${REPO_ROOT}"
  python -m pip install --disable-pip-version-check -e ".[dev]"
)

echo "==> Installing the visualization API dependencies"
python -m pip install --disable-pip-version-check \
  -r "${REPO_ROOT}/viz/server/requirements.txt"

echo "==> Installing the visualization UI dependencies"
npm ci --prefix "${REPO_ROOT}/viz"

echo "==> Running the deterministic Codespaces demo"
mkdir -p "${DEMO_OUTPUT}"
ncsim \
  --scenario "${REPO_ROOT}/scenarios/demo_simple.yaml" \
  --output "${DEMO_OUTPUT}" \
  --seed 42

for output_file in scenario.yaml trace.jsonl metrics.json; do
  if [[ ! -s "${DEMO_OUTPUT}/${output_file}" ]]; then
    echo "ERROR: Demo output is missing or empty: ${DEMO_OUTPUT}/${output_file}" >&2
    exit 1
  fi
done

python - "${DEMO_OUTPUT}" <<'PY'
import json
import pathlib
import sys

output_dir = pathlib.Path(sys.argv[1])
json.loads((output_dir / "metrics.json").read_text(encoding="utf-8"))
with (output_dir / "trace.jsonl").open(encoding="utf-8") as trace:
    events = [json.loads(line) for line in trace if line.strip()]
if not events:
    raise SystemExit("Demo trace contains no events")
PY

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

BASHRC="${HOME}/.bashrc"
BANNER_COMMAND="source \"${SCRIPT_DIR}/terminal-banner.sh\""

touch "${BASHRC}"
if ! grep -Fqx "${BANNER_COMMAND}" "${BASHRC}"; then
  printf '\n%s\n' "${BANNER_COMMAND}" >>"${BASHRC}"
fi

bash "${SCRIPT_DIR}/terminal-banner.sh"

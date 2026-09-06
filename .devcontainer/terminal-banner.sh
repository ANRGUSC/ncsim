#!/usr/bin/env bash

if [[ "${NCSIM_CODESPACES_BANNER_SHOWN:-0}" != "1" ]]; then
  export NCSIM_CODESPACES_BANNER_SHOWN=1
  cat <<'EOF'

NCSim Codespaces is ready.

  Start or restart the web UI:  start-viz
  Open the UI manually:         Ports tab -> port 5173 -> globe icon
  Run a CLI simulation:         ncsim --scenario scenarios/demo_simple.yaml --output results/my-run

Port 8000 is the internal API; a "GET / not found" response there is expected.

EOF
fi

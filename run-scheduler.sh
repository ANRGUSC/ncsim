#!/bin/sh
# Start the SAGA scheduler service on port 9999
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$SCRIPT_DIR/saga-service/scheduler_service.py" --scheduler heft "$@"

#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
STATE_DIR="/tmp/ncsim-codespaces-${USER:-vscode}"
BACKEND_PID_FILE="${STATE_DIR}/backend.pid"
FRONTEND_PID_FILE="${STATE_DIR}/frontend.pid"
BACKEND_LOG="${STATE_DIR}/backend.log"
FRONTEND_LOG="${STATE_DIR}/frontend.log"

mkdir -p "${STATE_DIR}"

pid_is_running() {
  local pid_file="$1"
  local pid

  [[ -s "${pid_file}" ]] || return 1
  pid="$(<"${pid_file}")"
  [[ "${pid}" =~ ^[0-9]+$ ]] || return 1
  kill -0 "${pid}" 2>/dev/null
}

url_is_ready() {
  curl --fail --silent --show-error --max-time 2 "$1" >/dev/null 2>&1
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local pid_file="$3"
  local log_file="$4"

  for _ in {1..30}; do
    if url_is_ready "${url}"; then
      echo "==> ${name} is ready at ${url}"
      return 0
    fi
    if [[ -s "${pid_file}" ]] && ! pid_is_running "${pid_file}"; then
      break
    fi
    sleep 1
  done

  echo "ERROR: ${name} did not become ready. Recent log output:" >&2
  tail -n 30 "${log_file}" >&2 || true
  return 1
}

port_is_available() {
  python - "$1" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        raise SystemExit(1)
PY
}

ensure_backend() {
  local url="http://127.0.0.1:8000/api/experiments"

  if url_is_ready "${url}"; then
    echo "==> NCSim API is already running on port 8000"
    return 0
  fi

  if pid_is_running "${BACKEND_PID_FILE}"; then
    echo "==> Waiting for the existing NCSim API process"
    wait_for_url "NCSim API" "${url}" "${BACKEND_PID_FILE}" "${BACKEND_LOG}"
    return
  fi

  rm -f "${BACKEND_PID_FILE}"
  if ! port_is_available 8000; then
    echo "ERROR: Port 8000 is occupied by another process; NCSim API was not started." >&2
    return 1
  fi

  echo "==> Starting the internal NCSim API on port 8000"
  (
    cd "${REPO_ROOT}/viz/server"
    nohup python run.py >"${BACKEND_LOG}" 2>&1 &
    echo "$!" >"${BACKEND_PID_FILE}"
  )
  wait_for_url "NCSim API" "${url}" "${BACKEND_PID_FILE}" "${BACKEND_LOG}"
}

ensure_frontend() {
  local url="http://127.0.0.1:5173"

  if url_is_ready "${url}"; then
    echo "==> NCSim visualization is already running on port 5173"
    return 0
  fi

  if pid_is_running "${FRONTEND_PID_FILE}"; then
    echo "==> Waiting for the existing NCSim visualization process"
    wait_for_url "NCSim visualization" "${url}" "${FRONTEND_PID_FILE}" "${FRONTEND_LOG}"
    return
  fi

  rm -f "${FRONTEND_PID_FILE}"
  if ! port_is_available 5173; then
    echo "ERROR: Port 5173 is occupied by another process; visualization was not started." >&2
    return 1
  fi

  echo "==> Starting the NCSim visualization on port 5173"
  (
    cd "${REPO_ROOT}/viz"
    nohup npm run dev -- --host 0.0.0.0 >"${FRONTEND_LOG}" 2>&1 &
    echo "$!" >"${FRONTEND_PID_FILE}"
  )
  wait_for_url "NCSim visualization" "${url}" "${FRONTEND_PID_FILE}" "${FRONTEND_LOG}"
}

ensure_backend
ensure_frontend

echo
echo "NCSim UI and API are running. Logs:"
echo "  ${FRONTEND_LOG}"
echo "  ${BACKEND_LOG}"

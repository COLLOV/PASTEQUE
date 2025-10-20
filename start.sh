#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: ./start.sh <frontend_port> <backend_port>" >&2
  exit 1
fi

FRONTEND_PORT="$1"
BACKEND_PORT="$2"

is_number() {
  [[ "$1" =~ ^[0-9]+$ ]]
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: Required command '$1' not found in PATH." >&2
    exit 1
  fi
}

free_port() {
  local port="$1"
  local pids

  pids=$(lsof -ti tcp:"$port" || true)

  if [[ -z "$pids" ]]; then
    return
  fi

  # shellcheck disable=SC2206 # intentional word splitting into array
  local pid_array=($pids)

  echo "[start] Terminating processes on port $port: ${pid_array[*]}"
  kill "${pid_array[@]}" >/dev/null 2>&1 || true
  sleep 1

  pids=$(lsof -ti tcp:"$port" || true)
  if [[ -z "$pids" ]]; then
    return
  fi

  pid_array=($pids)

  echo "[start] Forcing termination on port $port: ${pid_array[*]}"
  kill -9 "${pid_array[@]}" >/dev/null 2>&1 || true
  sleep 1
}

cleanup() {
  local code=$?

  if [[ -n "${BACKEND_PID:-}" ]] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    echo "[start] Stopping backend (PID $BACKEND_PID)"
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi

  if [[ -n "${FRONTEND_PID:-}" ]] && kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    echo "[start] Stopping frontend (PID $FRONTEND_PID)"
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
    wait "$FRONTEND_PID" 2>/dev/null || true
  fi

  exit "$code"
}

trap cleanup EXIT INT TERM

for cmd in lsof uv npm; do
  require_command "$cmd"
done

for port in "$FRONTEND_PORT" "$BACKEND_PORT"; do
  if ! is_number "$port"; then
    echo "ERROR: Ports must be numeric. Got '$port'." >&2
    exit 1
  fi
  free_port "$port"
done

echo "[start] Ensuring backend dependencies (uv sync)"
(
  cd backend
  uv sync
)

if [[ ! -d frontend/node_modules ]]; then
  echo "[start] Installing frontend dependencies (npm install)"
  (
    cd frontend
    npm install
  )
else
  echo "[start] Frontend dependencies already installed"
fi

echo "[start] Launching backend on port $BACKEND_PORT"
(
  cd backend
  exec uv run uvicorn insight_backend.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT"
) &
BACKEND_PID=$!

# Allow backend to initialise before starting frontend
sleep 1

echo "[start] Launching frontend on port $FRONTEND_PORT"
(
  cd frontend
  exec npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT"
) &
FRONTEND_PID=$!

wait "$BACKEND_PID"
wait "$FRONTEND_PID"

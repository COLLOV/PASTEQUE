#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: ./start.sh <frontend_port> <backend_port>" >&2
  exit 1
fi

FRONTEND_PORT="$1"
BACKEND_PORT="$2"
SSR_DIR="vis-ssr"
SSR_ENV_FILE="${SSR_DIR}/.env"
SSR_ENV_TEMPLATE="${SSR_DIR}/.env.ssr.example"
BACKEND_ENV_FILE="backend/.env"

is_number() {
  [[ "$1" =~ ^[0-9]+$ ]]
}

read_env_var() {
  local file="$1"
  local key="$2"

  ENV_FILE="$file" ENV_KEY="$key" python3 <<'PY'
import os
from pathlib import Path

path = Path(os.environ["ENV_FILE"])
key = os.environ["ENV_KEY"]
value = ""

if path.exists():
    for raw in path.read_text().splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, val = stripped.split("=", 1)
        if name.strip() == key:
            val = val.strip()
            if (
                (val.startswith('"') and val.endswith('"'))
                or (val.startswith("'") and val.endswith("'"))
            ):
                val = val[1:-1]
            value = val
            break

print(value)
PY
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

  if [[ -n "${SSR_PID:-}" ]] && kill -0 "$SSR_PID" >/dev/null 2>&1; then
    echo "[start] Stopping GPT-Vis SSR (PID $SSR_PID)"
    kill "$SSR_PID" >/dev/null 2>&1 || true
    wait "$SSR_PID" 2>/dev/null || true
  fi

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

for cmd in lsof uv npm python3 curl node; do
  require_command "$cmd"
done

if [[ ! -f "$BACKEND_ENV_FILE" ]]; then
  echo "ERROR: Backend configuration '$BACKEND_ENV_FILE' not found." >&2
  exit 1
fi

CONTAINER_RUNTIME_RAW="$(read_env_var "$BACKEND_ENV_FILE" "CONTAINER_RUNTIME")"

if [[ -z "$CONTAINER_RUNTIME_RAW" ]]; then
  echo "ERROR: CONTAINER_RUNTIME must be defined in '$BACKEND_ENV_FILE'." >&2
  exit 1
fi

# macOS ships Bash 3.2 (no ${var,,}); use POSIX tr instead
CONTAINER_RUNTIME="$(printf '%s' "$CONTAINER_RUNTIME_RAW" | tr '[:upper:]' '[:lower:]')"

case "$CONTAINER_RUNTIME" in
  docker|podman)
    ;;
  *)
    echo "ERROR: Unsupported CONTAINER_RUNTIME '$CONTAINER_RUNTIME_RAW'. Use 'docker' or 'podman'." >&2
    exit 1
    ;;
esac

require_command "$CONTAINER_RUNTIME"
echo "[start] Container runtime -> $CONTAINER_RUNTIME"

for port in "$FRONTEND_PORT" "$BACKEND_PORT"; do
  if ! is_number "$port"; then
    echo "ERROR: Ports must be numeric. Got '$port'." >&2
    exit 1
  fi
  free_port "$port"
done

if [[ ! -d "$SSR_DIR" ]]; then
  echo "ERROR: SSR directory '$SSR_DIR' is missing." >&2
  exit 1
fi

if [[ ! -f "$SSR_ENV_FILE" ]]; then
  echo "ERROR: GPT-Vis SSR configuration '$SSR_ENV_FILE' not found. Copy '$SSR_ENV_TEMPLATE' and set GPT_VIS_SSR_PORT." >&2
  exit 1
fi

SSR_PORT="$(read_env_var "$SSR_ENV_FILE" "GPT_VIS_SSR_PORT")"

if [[ -z "$SSR_PORT" ]]; then
  echo "ERROR: GPT_VIS_SSR_PORT must be defined in '$SSR_ENV_FILE'." >&2
  exit 1
fi

if ! is_number "$SSR_PORT"; then
  echo "ERROR: GPT_VIS_SSR_PORT must be numeric. Got '$SSR_PORT'." >&2
  exit 1
fi

free_port "$SSR_PORT"

ensure_mindsdb() {
  local container="mindsdb_container"

  if "$CONTAINER_RUNTIME" ps -a --filter "name=^${container}$" --format '{{.Names}}' | grep -q .; then
    echo "[start] Resetting existing MindsDB container '$container'"
    "$CONTAINER_RUNTIME" rm -f "$container" >/dev/null 2>&1 || true
  else
    echo "[start] No previous MindsDB container detected"
  fi

  echo "[start] Launching MindsDB container '$container'"
  "$CONTAINER_RUNTIME" run -d --name "$container" \
    -e MINDSDB_APIS=http,mysql \
    -p 47334:47334 -p 47335:47335 \
    mindsdb/mindsdb >/dev/null

  echo "[start] MindsDB container '$container' status"
  "$CONTAINER_RUNTIME" ps --filter "name=^${container}$" --format '  -> {{.ID}} {{.Status}} {{.Ports}}' || true
  echo "[start] MindsDB last logs (tail 10)"
  "$CONTAINER_RUNTIME" logs --tail 10 "$container" 2>/dev/null | sed 's/^/[mindsdb] /' || true
}

wait_for_mindsdb() {
  local max_wait=60
  local elapsed=0
  local url="http://127.0.0.1:47334/api/status"

  echo "[start] Waiting for MindsDB to be ready..."

  while [[ $elapsed -lt $max_wait ]]; do
    if curl -sf "$url" >/dev/null 2>&1; then
      echo "[start] MindsDB is ready!"
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
    echo "[start] Still waiting for MindsDB... (${elapsed}s)"
  done

  echo "[start] WARNING: MindsDB did not become ready after ${max_wait}s"
  return 1
}

ensure_mindsdb
wait_for_mindsdb

echo "[start] Ensuring backend dependencies (uv sync)"
(
  cd backend
  uv sync
)

echo "[start] Syncing local tables into MindsDB"
(
  cd backend
  uv run python - <<'PY'
from insight_backend.services.mindsdb_sync import sync_all_tables

uploaded = sync_all_tables()
if uploaded:
    print("[start] MindsDB sync uploaded:", ", ".join(uploaded))
else:
    print("[start] MindsDB sync uploaded: (aucun fichier)")
PY
)

FRONTEND_ENV_FILE="frontend/.env.development"
API_URL="http://localhost:${BACKEND_PORT}/api/v1"
ALLOWED_ORIGINS_VALUE="http://localhost:${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT}"

ensure_frontend_env() {
  local file="$1"
  local value="$2"

  ENV_FILE="$file" API_URL="$value" python3 <<'PY'
import os
from pathlib import Path

path = Path(os.environ["ENV_FILE"])
value = os.environ["API_URL"]

if path.exists():
    lines = path.read_text().splitlines()
else:
    lines = []

found = False
for idx, line in enumerate(lines):
    if line.startswith("VITE_API_URL="):
        lines[idx] = f"VITE_API_URL={value}"
        found = True

if not found:
    if lines and lines[-1].strip():
        lines.append("")
    lines.append(f"VITE_API_URL={value}")

text = "\n".join(lines)
if text and not text.endswith("\n"):
    text += "\n"
path.write_text(text)
PY
}

ensure_frontend_env "$FRONTEND_ENV_FILE" "$API_URL"
echo "[start] frontend/.env.development -> VITE_API_URL=$API_URL"
echo "[start] backend CORS -> ALLOWED_ORIGINS=$ALLOWED_ORIGINS_VALUE"

if [[ ! -d frontend/node_modules ]]; then
  echo "[start] Installing frontend dependencies (npm install)"
  (
    cd frontend
    npm install
  )
else
  echo "[start] Frontend dependencies already installed"
fi

if [[ ! -f "${SSR_DIR}/package.json" ]]; then
  echo "ERROR: Missing package.json in '$SSR_DIR'." >&2
  exit 1
fi

if [[ ! -d ${SSR_DIR}/node_modules ]]; then
  echo "[start] Installing GPT-Vis SSR dependencies (npm install)"
  (
    cd "$SSR_DIR"
    NODE_TLS_REJECT_UNAUTHORIZED=0 npm_config_strict_ssl=false npm_config_registry=https://registry.npmjs.org npm install
  )
else
  echo "[start] GPT-Vis SSR dependencies already installed"
fi

SSR_IMAGE_DIR="$(read_env_var "$SSR_ENV_FILE" "VIS_IMAGE_DIR")"
if [[ -n "$SSR_IMAGE_DIR" ]]; then
  echo "[start] GPT-Vis SSR images -> $SSR_IMAGE_DIR"
else
  SSR_IMAGE_DIR_DISPLAY="$(cd "$SSR_DIR" && pwd)/charts"
  echo "[start] GPT-Vis SSR images -> $SSR_IMAGE_DIR_DISPLAY (default)"
fi

echo "[start] Launching GPT-Vis SSR on port $SSR_PORT"
(
  cd "$SSR_DIR"
  if [[ -n "$SSR_IMAGE_DIR" ]]; then
    GPT_VIS_SSR_PORT="$SSR_PORT" VIS_IMAGE_DIR="$SSR_IMAGE_DIR" exec npm run start
  else
    GPT_VIS_SSR_PORT="$SSR_PORT" exec npm run start
  fi
) &
SSR_PID=$!

echo "[start] Launching backend on port $BACKEND_PORT"
(
  cd backend
  ALLOWED_ORIGINS="$ALLOWED_ORIGINS_VALUE" exec uv run uvicorn insight_backend.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT"
) &
BACKEND_PID=$!

# Allow backend to initialise before starting frontend
sleep 1

echo "[start] Launching frontend on port $FRONTEND_PORT"
(
  cd frontend
  VITE_API_URL="$API_URL" exec npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT"
) &
FRONTEND_PID=$!

wait "$BACKEND_PID"
wait "$FRONTEND_PID"
wait "$SSR_PID"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -d ".venv" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "[start_public_server] Python not found" >&2
  exit 1
fi

PUBLIC_MODE="${PUBLIC_MODE:-true}"
HOST="${HOST:-}"
PORT="${PORT:-8000}"

if [[ -z "${HOST}" ]]; then
  if [[ "${PUBLIC_MODE}" == "true" ]]; then
    HOST="127.0.0.1"
  else
    HOST="0.0.0.0"
  fi
fi

echo "[start_public_server] Running DB migration..."
PYTHONPATH=src "${PYTHON_BIN}" -m app.db.migrate

echo "[start_public_server] Starting backend on http://${HOST}:${PORT}"
if [[ -n "${PUBLIC_BASE_URL:-}" ]]; then
  echo "[start_public_server] Public URL: ${PUBLIC_BASE_URL}"
fi

exec env PYTHONPATH=src "${PYTHON_BIN}" -m uvicorn app.main:app --app-dir src --host "${HOST}" --port "${PORT}"

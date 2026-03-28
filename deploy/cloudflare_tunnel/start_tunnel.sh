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

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "[start_tunnel] cloudflared is not installed. Install it first." >&2
  exit 1
fi

QUICK_TUNNEL="${QUICK_TUNNEL:-false}"
if [[ "${QUICK_TUNNEL}" == "true" ]]; then
  TARGET_URL="${QUICK_TUNNEL_URL:-http://127.0.0.1:8000}"
  echo "[start_tunnel] Quick mode enabled (trycloudflare)."
  echo "[start_tunnel] Forward target: ${TARGET_URL}"
  echo "[start_tunnel] Wait for a line with: https://<random>.trycloudflare.com"
  exec cloudflared tunnel --url "${TARGET_URL}" --no-autoupdate
fi

if [[ -z "${CLOUDFLARED_CONFIG_PATH:-}" ]]; then
  echo "[start_tunnel] CLOUDFLARED_CONFIG_PATH is not set." >&2
  echo "Example: export CLOUDFLARED_CONFIG_PATH=/absolute/path/to/config.yml" >&2
  exit 1
fi

if [[ ! -f "${CLOUDFLARED_CONFIG_PATH}" ]]; then
  echo "[start_tunnel] Config file not found: ${CLOUDFLARED_CONFIG_PATH}" >&2
  exit 1
fi

echo "[start_tunnel] Running cloudflared with config: ${CLOUDFLARED_CONFIG_PATH}"
exec cloudflared tunnel --config "${CLOUDFLARED_CONFIG_PATH}" run

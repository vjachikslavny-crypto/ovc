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

PUBLIC_URL="${1:-${PUBLIC_BASE_URL:-}}"

if [[ -z "${PUBLIC_URL}" ]]; then
  echo "[verify_public] PUBLIC_BASE_URL is not set and no URL argument passed." >&2
  echo "Usage: ./deploy/cloudflare_tunnel/verify_public.sh https://<random>.trycloudflare.com" >&2
  exit 1
fi

echo "[verify_public] Checking local health endpoint..."
curl -fsS "http://127.0.0.1:8000/healthz" | sed 's/^/[local] /'

echo "[verify_public] Checking public health endpoint..."
curl -fsS "${PUBLIC_URL%/}/healthz" | sed 's/^/[public] /'

echo "[verify_public] OK"

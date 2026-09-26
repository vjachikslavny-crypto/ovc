#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${OVC_PYTHON:-${ROOT_DIR}/.venv/bin/python}" -B "${ROOT_DIR}/scripts/local_data.py" backup "$@"

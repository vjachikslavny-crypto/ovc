#!/usr/bin/env bash
set -euo pipefail

python -m venv .venv
source .venv/bin/activate
pip install -r simple_app/requirements.txt
PYTHONPATH=simple_app python -m app.db.migrate
uvicorn app.main:app --reload --app-dir simple_app

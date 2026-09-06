#!/usr/bin/env bash
# OCEAN 3D backend launcher
set -e
cd "$(dirname "$0")"
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -q -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

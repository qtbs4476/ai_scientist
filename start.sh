#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
python -m pip install -q -r requirements.txt
echo "Open: http://127.0.0.1:8899"
python -m uvicorn src.app:app --host 127.0.0.1 --port 8899

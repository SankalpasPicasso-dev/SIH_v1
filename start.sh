#!/usr/bin/env bash
set -e
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 -m venv "$ROOT_DIR/.venv"
"$ROOT_DIR/.venv/bin/pip" install -r "$ROOT_DIR/backend/requirements.txt"
(cd "$ROOT_DIR/frontend" && npm install)
PYTHONPATH="$ROOT_DIR/backend" "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/scripts/seed_data.py"
echo "Starting API on http://localhost:8000 and UI on http://localhost:5173"
(cd "$ROOT_DIR/backend" && "$ROOT_DIR/.venv/bin/uvicorn" app.main:app --reload) &
(cd "$ROOT_DIR/frontend" && npm run dev)

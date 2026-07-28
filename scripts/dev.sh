#!/usr/bin/env bash
# Serviceflow local dev launcher: seeds the DB, starts the API and a static
# server for the frontend. Ctrl-C stops both.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "▶ Setting up backend…"
cd "$ROOT/backend"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install -q --upgrade pip
  ./.venv/bin/pip install -q -r requirements.txt
fi
./.venv/bin/python -m app.seed

echo "▶ Starting API on http://127.0.0.1:8000  (docs at /docs)"
./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!

echo "▶ Serving frontend on http://127.0.0.1:5173"
cd "$ROOT/frontend"
python3 -m http.server 5173 --bind 127.0.0.1 &
WEB_PID=$!

trap 'echo; echo "Stopping…"; kill $API_PID $WEB_PID 2>/dev/null || true' INT TERM
echo
echo "  Open the app:  http://127.0.0.1:5173"
echo "  Demo login:    admin@apexrepair.com / Password123  (portal: buyer@acmepower.com)"
echo
wait

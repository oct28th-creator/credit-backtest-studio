#!/usr/bin/env bash
# Start the whole thing locally: backend on :8000, frontend on :5173.
#
#   bash scripts/dev.sh
#
# Creates backend/venv on first run, installs whatever is missing, and stops
# both processes on Ctrl-C. Safe to re-run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"

say() { printf '\033[36m▸\033[0m %s\n' "$1"; }
die() { printf '\033[31m✗\033[0m %s\n' "$1" >&2; exit 1; }

command -v python3 >/dev/null || die "python3 not found"
command -v npm >/dev/null || die "npm not found"

port_busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
port_busy "$API_PORT" && die "port $API_PORT is in use (API_PORT=... to change)"
port_busy "$WEB_PORT" && die "port $WEB_PORT is in use (WEB_PORT=... to change)"

# ── backend ─────────────────────────────────────────────────────────────
cd "$BACKEND"
if [ ! -x "venv/bin/python" ]; then
  say "creating backend/venv"
  rm -rf venv
  python3 -m venv venv
fi
if ! ./venv/bin/python -c "import fastapi, numpy, sklearn, scipy" >/dev/null 2>&1; then
  say "installing backend dependencies (first run only)"
  ./venv/bin/pip install -q --upgrade pip
  ./venv/bin/pip install -q -r requirements.txt
fi
[ -f .env ] || { say "creating backend/.env from .env.example"; cp .env.example .env; }

say "starting API on http://localhost:$API_PORT (docs at /docs)"
./venv/bin/uvicorn app.main:app --reload --port "$API_PORT" &
API_PID=$!

# ── frontend ────────────────────────────────────────────────────────────
cd "$FRONTEND"
if [ ! -d node_modules ]; then
  say "installing frontend dependencies (first run only)"
  npm install --no-audit --no-fund
fi

cleanup() {
  say "shutting down"
  kill "$API_PID" 2>/dev/null || true
  wait "$API_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

say "starting UI on http://localhost:$WEB_PORT"
echo
echo "  UI    http://localhost:$WEB_PORT"
echo "  API   http://localhost:$API_PORT/docs"
echo "  agent POST http://localhost:$API_PORT/api/agent/investigate"
echo
npm run dev -- --port "$WEB_PORT"

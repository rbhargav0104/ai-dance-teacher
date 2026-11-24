#!/usr/bin/env bash
# Run API (one worker, :8000) and web (:3000) together. Ctrl-C stops both.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

(cd "$ROOT/backend" && uv run alembic upgrade head)
(cd "$ROOT/backend" && exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload) &
API_PID=$!
(cd "$ROOT/frontend" && exec npm run dev -- --hostname 0.0.0.0) &
WEB_PID=$!
trap 'kill $API_PID $WEB_PID 2>/dev/null || true' EXIT INT TERM
echo "API  http://localhost:8000/api/health   docs: http://localhost:8000/api/docs"
echo "Web  http://localhost:3000"
wait

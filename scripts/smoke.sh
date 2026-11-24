#!/usr/bin/env bash
# Smoke-check a running stack: health, session, /me — directly and through the web proxy.
# Usage: scripts/smoke.sh [api_base] [web_base]
set -euo pipefail
API="${1:-http://localhost:8000}"
WEB="${2:-http://localhost:3000}"
py() { python3 -c "import json,sys; d=json.load(sys.stdin); $1"; }

echo "-- API health"
curl -fsS "$API/api/health" | py 'print(d["status"], "|", d["message"]); assert d["database"]["ok"] and d["storage"]["ok"]'
echo "-- session + /me"
TOKEN="$(curl -fsS -X POST "$API/api/session" | py 'print(d["token"])')"
curl -fsS "$API/api/me" -H "Authorization: Bearer $TOKEN" | py 'print("user", d["user_id"])'
code="$(curl -s -o /dev/null -w '%{http_code}' "$API/api/me")"
[[ "$code" == "401" ]] || { echo "expected 401 without token, got $code"; exit 1; }
echo "-- web + proxy"
curl -fsS "$WEB/" | grep -q "Frame by frame" && echo "landing ok"
curl -fsS "$WEB/api/health" | py 'print("proxied health:", d["status"])'
echo "SMOKE OK"

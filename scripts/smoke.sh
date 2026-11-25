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
echo "-- reference intake through the proxy (sample + delete)"
WTOKEN="$(curl -fsS -X POST "$WEB/api/session" | py 'print(d["token"])')"
SAMPLE="$(curl -fsS "$WEB/api/samples" | py 'print(d[0]["id"])')"
PID="$(curl -fsS -X POST "$WEB/api/projects/sample" -H "Authorization: Bearer $WTOKEN" \
  -H "Content-Type: application/json" -d "{\"sample_id\": \"$SAMPLE\"}" | py 'print(d["id"])')"
curl -fsS "$WEB/api/projects/$PID" -H "Authorization: Bearer $WTOKEN" \
  | py 'r=d["reference"]; print("sample stored:", r["width"], "x", r["height"], r["duration"], "s", "| status", d["status"])'
STATUS="$(curl -fsS "$API/api/health" | py 'print(d["status"])')"
if [[ "$STATUS" == "ready" ]]; then
  echo "-- real analysis of the sample (READY server)"
  for i in $(seq 1 120); do
    PSTATUS="$(curl -fsS "$WEB/api/projects/$PID" -H "Authorization: Bearer $WTOKEN" | py 'print(d["status"])')"
    [[ "$PSTATUS" == "analyzed" || "$PSTATUS" == "failed" ]] && break
    sleep 1
  done
  [[ "$PSTATUS" == "analyzed" ]] || { echo "analysis did not finish: $PSTATUS"; exit 1; }
  curl -fsS "$WEB/api/projects/$PID/poses" -H "Authorization: Bearer $WTOKEN" \
    | py 'v=sum(f["valid"] for f in d["frames"]); print("frames", len(d["frames"]), "valid", v, "coverage", d["coverage"], "warnings", d["quality"]["warnings"]); assert len(d["frames"])>100 and d["coverage"]>0.55'
else
  echo "-- server is $STATUS: analysis must be refused with 503"
  code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$WEB/api/projects/$PID/analysis" -H "Authorization: Bearer $WTOKEN")"
  [[ "$code" == "503" ]] || { echo "expected 503 in LIMITED, got $code"; exit 1; }
fi
URL="$(curl -fsS "$WEB/api/projects/$PID/media/source" -H "Authorization: Bearer $WTOKEN" | py 'print(d["url"])')"
code="$(curl -s -o /dev/null -w '%{http_code}' -H 'Range: bytes=0-99' "$WEB$URL")"
[[ "$code" == "206" ]] || { echo "expected 206 for ranged media, got $code"; exit 1; }
code="$(curl -s -o /dev/null -w '%{http_code}' -X DELETE "$WEB/api/projects/$PID" -H "Authorization: Bearer $WTOKEN")"
[[ "$code" == "204" ]] || { echo "delete failed: $code"; exit 1; }
code="$(curl -s -o /dev/null -w '%{http_code}' "$WEB$URL")"
[[ "$code" == "404" ]] || { echo "media should be gone after delete, got $code"; exit 1; }
echo "intake ok"
echo "SMOKE OK"

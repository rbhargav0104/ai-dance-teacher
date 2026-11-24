#!/usr/bin/env bash
# One-time local setup: backend deps (Python 3.12 via uv), frontend deps, pose model, DB migrations.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

command -v uv >/dev/null || { echo "Install uv first: https://docs.astral.sh/uv/ (curl -LsSf https://astral.sh/uv/install.sh | sh)"; exit 1; }
command -v node >/dev/null || { echo "Install Node.js >= 20.9"; exit 1; }
command -v ffprobe >/dev/null || echo "warning: ffmpeg/ffprobe not found — needed from Outcome 1 (apt install ffmpeg / brew install ffmpeg)"

if [[ "$(uname)" == "Linux" ]] && command -v ldconfig >/dev/null && ! ldconfig -p | grep -q "libEGL.so.1"; then
  echo "warning: libEGL missing — MediaPipe needs it: sudo apt-get install -y libegl1 libgles2 libgl1"
fi

[[ -f .env ]] || cp .env.example .env

echo "== backend dependencies"
(cd backend && uv sync --extra vision)

echo "== frontend dependencies"
(cd frontend && npm ci)

echo "== pose model"
scripts/download_model.sh || echo "warning: model unavailable; the app will run in LIMITED mode"

echo "== database migrations"
(cd backend && uv run alembic upgrade head)

echo "Setup complete. Start everything with: scripts/dev.sh"

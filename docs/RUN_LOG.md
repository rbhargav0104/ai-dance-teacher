# Run log

One entry per build session, newest at the bottom.

## 2026-11-24 00:50 IST — repo seeded (setup chat)
- Added spec (`docs/MASTER_PROMPT.md`), `CLAUDE.md`, `IMPLEMENTATION_PLAN.md`, `PROJECT_STATUS.md`, `DECISIONS.md`, fixture folders.
- No application code yet.
- Next: Outcome 0 in the 01:43 IST session.

## 2026-11-24 01:00 IST — sourcing plan (setup chat)
- Owner constraint: testing only. Verified the sandbox can reach GitHub + PyPI/npm only.
- Verified pose model via GitHub mirrors (SHA-256 4eaa5eb7…c4ad, 9,398,198 bytes) loads and runs with mediapipe 1.2.3 / Python 3.12.
- Found openly licensed stock dance clips on GitHub; wrote `docs/SOURCING.md`. Replaced cloud deployment with Codespaces + docker compose + CI.

## 2026-11-24 16:07–17:00 IST — build session 1 (Outcome 0)
Delivered:
- Monorepo: `backend/` (FastAPI, SQLAlchemy, Alembic 0001 with all spec §10 tables, local signed sessions, private
  local storage, honest `/api/health`, JSON logs) and `frontend/` (Next.js 16, landing + `/studio` shell, READY/LIMITED/OFFLINE pill).
- `scripts/setup.sh`, `dev.sh`, `smoke.sh`, `download_model.sh` (SHA-256 pinned; official URL 403s here, torinmb mirror verified).
- `.env.example`, README run instructions, ARCHITECTURE.md, GitHub Actions CI (backend, frontend, boot smoke).
- Outcome 1 prep: located two downloadable Mixkit dance clips; both are cropped (no feet). Findings in docs/SOURCING.md.

Commands and results:
- `cd backend && uv run pytest` → 35 passed; `uv run ruff check .` / `ruff format --check .` / `uv run mypy` → clean.
- `uv run python -m app.pose.verify` → `{"ok": true, "mediapipe": "1.2.3", "poses_on_blank_frame": 0}`.
- `cd frontend && npm test` → 12 passed; `npm run lint`, `npm run typecheck`, `npm run build` → clean.
- Fresh clone → `scripts/setup.sh` → `scripts/dev.sh` → `scripts/smoke.sh` → SMOKE OK. Playwright desktop/mobile screenshots checked; OFFLINE verified by stopping the API.
- CI run 1: backend job failed — `libEGL.so.1` missing on the runner for MediaPipe. Fixed by installing `libegl1 libgles2 libgl1`; result of run 2 recorded below.

Next (Nov 25, Outcome 1): streaming upload `POST /api/projects` with idempotency key, FFprobe validation, private source
storage, job record, no-residue rejection tests for every invalid-media case, project list/delete, upload UI with
drag-drop/preview, finish fixture sourcing (find a full-body clip) and commit trimmed fixtures + manifest + LICENSES.md.

# Project status

_Last updated: 2026-11-24 ~16:55 IST (build session 1)_

## Outcomes

| # | Outcome | State | Notes |
|---|---|---|---|
| 0 | Engineering foundation | **tested** | Exit gate met: clean clone → `scripts/setup.sh` → `scripts/dev.sh` → health + session + /me reachable directly and via the web proxy (`scripts/smoke.sh`). CI runs the same boot smoke. |
| 1 | Robust private reference intake | planned (prep started) | Two Mixkit reference candidates located + verified downloadable (see `docs/SOURCING.md`); a full-body clip is still needed. |
| 2 | Real reference pose + debugger | planned | Pose model download + real MediaPipe load verified (`python -m app.pose.verify`). |
| 3 | Teachable sections | planned | |
| 4 | Teacher Mode | planned | |
| 5 | Learner capture + real learner pose | planned | |
| 6 | Normalized alignment | planned | |
| 7 | Versioned scoring | planned | |
| 8 | Actionable feedback | planned | |
| 9 | Report, repeat, dashboard | planned | |
| 10 | Production identity + durable infra | planned | |
| 11 | Stable deployment + full acceptance | planned | |

States: planned → implemented → tested → deployed. On schedule (Nov 24 target = Outcome 0).

## What exists today

- **Backend** (`backend/`, Python 3.12, FastAPI): typed settings with production guardrails; SQLAlchemy models for all
  spec §10 tables + Alembic migration `0001`; signed expiring local sessions (`POST /api/session`, `GET /api/me`);
  private local object storage (atomic, 0600, traversal/symlink-safe); `GET /api/health` capability report;
  JSON logs with request IDs; consistent error envelope; OpenAPI at `/api/docs`.
- **Frontend** (`frontend/`, Next.js 16, strict TS, Tailwind v4): landing page in the dark-studio / electric-lime design,
  `/studio` shell with a live system check, persistent READY / LIMITED / OFFLINE pill (desktop + mobile), typed fetch
  layer with a single 401 → new session → retry.
- **Scripts**: `setup.sh`, `dev.sh`, `smoke.sh`, `download_model.sh` (SHA-256 pinned, official URL then GitHub mirrors).
- **CI** (`.github/workflows/ci.yml`): backend ruff + mypy strict + pytest (incl. real model load) + pose smoke;
  frontend eslint + tsc + vitest + build; end-to-end boot smoke.

## Verified claims (this session, in the build sandbox)

- Backend: `uv run pytest` → 35 passed (one test loads the real pose model and runs a MediaPipe inference);
  `ruff check`, `ruff format --check`, `mypy` (strict) clean.
- Frontend: `npm test` → 12 passed; `npm run lint`, `npm run typecheck`, `npm run build` clean.
- Fresh `git clone` + `scripts/setup.sh` + `scripts/dev.sh` + `scripts/smoke.sh` → SMOKE OK.
- Playwright screenshots (1440×900 and iPhone 13) of `/` and `/studio`: no horizontal overflow; OFFLINE state renders
  with retry when the API is stopped.
- Server reports **LIMITED** (honestly): model verified + runtime installed, but the analysis pipeline isn't built yet.

## Known gaps / unverified

- `/api/health` checks MediaPipe is *installed*, not that its native libs *load*; a missing `libEGL` is only caught by
  `python -m app.pose.verify` (CI caught exactly this). Add a cached runtime self-test with Outcome 2.
- No rate limiting yet (Outcome 10). No upload endpoints yet (Outcome 1).
- SQLite returns naive timestamps (UTC by convention); Postgres keeps tz.

## Owner action needed
_None. The owner only tests. Sessions source every asset themselves (see `docs/SOURCING.md`)._

## How Bhargav can test right now

Not much to click yet — this is the foundation. If you want to look:
1. Open the repo's **Actions** tab: the latest **CI** run should be green (backend, frontend, smoke).
2. Optional, on any machine with Node 20+ and [uv](https://docs.astral.sh/uv/): `scripts/setup.sh && scripts/dev.sh`,
   then open http://localhost:3000 (landing) and http://localhost:3000/studio (system check, status pill says LIMITED).

## Owner testing path (target)
- **GitHub Codespaces:** repo page → Code → Codespaces → Create. The devcontainer installs everything, downloads the model, seeds the demo, and starts the app on a forwarded HTTPS URL (webcam works).
- **Local alternative:** `docker compose up`, then open http://localhost:3000.

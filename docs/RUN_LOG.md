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
- CI run 1: backend job failed — `libEGL.so.1` missing on the runner for MediaPipe. Fixed by installing `libegl1 libgles2 libgl1`; CI run 2 (d4c1597) → **green** (backend, frontend, smoke).

Next (Nov 25, Outcome 1): streaming upload `POST /api/projects` with idempotency key, FFprobe validation, private source
storage, job record, no-residue rejection tests for every invalid-media case, project list/delete, upload UI with
drag-drop/preview, finish fixture sourcing (find a full-body clip) and commit trimmed fixtures + manifest + LICENSES.md.

## 2026-11-25 01:43–02:35 IST — build session 2 (Outcome 1)
Start: Outcome 0 gate re-checked — fresh `scripts/setup.sh`, `uv run pytest` 35 passed, `scripts/smoke.sh` SMOKE OK.

Delivered:
- Backend: `app/media/probe.py` (FFprobe argv + timeout, pure `validate_probe` rules), `app/media/upload.py` (streaming
  multipart, limit enforced mid-stream), `app/services/intake.py` (atomic persist + cleanup, idempotency, quota, samples),
  `app/api/projects.py`, `app/api/media.py` (signed URLs, ranges), migration `0002` (source size/codec/container/audio/rotation),
  health reports `media_inspection` + `uploads_available`.
- Frontend: upload panel (drag-drop, preview, metadata, progress, retry, errors), library + delete, `/studio/projects/[id]`
  dance page with private playback and disabled Analyze, `/studio?demo=1` sample picker.
- Fixtures: two Mixkit clips trimmed/transcoded to 1280×720 H.264, no audio, with manifest + licences (sourced by a
  sub-agent; ~20 min search for a full-body clip found none with a verifiable licence — details in docs/SOURCING.md).
- Next proxy body limit raised (default 10 MB truncated uploads → found by a manual 85 MB upload test).
- smoke.sh now covers sample intake, ranged media and delete; CI smoke job installs ffmpeg.

Commands and results:
- `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` → clean; 111 passed.
- `cd frontend && npm run lint && npm run typecheck && npm test && npm run build` → clean; 24 passed.
- `scripts/smoke.sh` (built web + API) → SMOKE OK. Playwright desktop + iPhone 13 screenshots reviewed.

Next (Nov 26, Outcome 2): canonical transcode job (24 fps H.264, ≤1280 px), real MediaPipe extraction on the fixture clips,
quality gates (coverage, multi-person, cropped body — both samples should warn), stored frames, skeleton viewer/debugger,
demo project produced by the real pipeline, cached runtime self-test in /api/health, flip LIMITED → READY only when it all works.
- CI run 4 (30816b5) → **green** (backend, frontend, smoke incl. intake via proxy).

## 2026-11-25 13:44–15:10 IST — build session 3 (Outcome 2, a session early)
Start: Outcome 1 gate re-checked — `scripts/setup.sh`, `uv run pytest` 111 passed (as recorded), repo at be786a6.
The `add_repo`/`register_repo_root` tools weren't offered in this run; the repo was already cloned with push access, so work continued.

Delivered:
- Backend: `media/transcode.py`, `pose/{landmarks,smoothing,features,quality,extract}.py`, `pipeline/reference.py`,
  `jobs/{queue,worker}.py`, migration `0003`, `POST /analysis` (202/200/503), `GET /poses`, `media/{source,canonical,poster}`,
  READY gated on a real load self-test + worker + ffmpeg, GZip for large pose payloads, sample auto-analysis.
- Frontend: live progress ring (polling, survives refresh), skeleton overlay on the canonical video, tracking summary,
  actionable failure states, `/studio/projects/[id]/debug` pose debugger (desktop + mobile).
- CI: smoke job installs the vision stack + model and analyses the sample through the web proxy, then re-runs smoke in LIMITED mode.

Commands and results:
- `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` → clean; 133 passed.
- `cd frontend && npm run lint && npm run typecheck && npm test && npm run build` → clean; 33 passed.
- `scripts/smoke.sh` (READY) → SMOKE OK; sample: 168 frames, 149 valid, coverage 0.887, warnings [cropped_body].
- Playwright 1440×900 + iPhone 13: sample → progress → overlay → debugger; two-dancer upload → `multiple_people` failure; no
  console errors, no horizontal overflow. The skeleton visibly tracks both sample dancers.

Notes: the `frontend-design` skill isn't available in this environment; UI follows the spec tokens already in globals.css.
Still no licence-verified full-body clip (feet) — both references are cropped; leg features are masked honestly.

Next (Nov 26, Outcome 3): automatic section boundaries from motion energy/pauses/pose change, thumbnails (poster per section),
editable timeline (split/merge/drag, persisted, full coverage without gaps/overlap), section loop/speed/mirror playback,
experimental instructions from measured features only. Also library-card poster thumbnails; another full-body fixture search.

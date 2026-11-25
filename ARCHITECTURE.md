# Architecture

## Overview

```
Browser ──/api/*──▶ Next.js (frontend, :3000) ──rewrite──▶ FastAPI (backend, :8000)
                                                              │
                                    ┌─────────────────────────┼──────────────────────┐
                                    ▼                         ▼                      ▼
                           SQLite / PostgreSQL       Private object storage    Pose runtime
                           (metadata, landmarks)     (local dir / Supabase)    (MediaPipe + pinned model)
```

- **Frontend** — Next.js App Router, TypeScript strict, Tailwind v4 tokens from spec §7. A small typed
  fetch layer (`frontend/lib/api.ts`) owns the local session token and the single 401 → refresh → retry.
  `StudioStatusProvider` polls `/api/health` and drives the persistent READY / LIMITED / OFFLINE pill.
- **Backend** — FastAPI app factory (`backend/app/main.py`). Typed settings (`app/config.py`) refuse unsafe
  production configs at startup. Consistent error envelope `{error:{code,message}, request_id}`; no stack traces.
  Structured JSON logs carry a request ID and never include media, tokens or query strings.
- **Auth** — `AUTH_MODE=local`: `POST /api/session` creates a private user and returns a signed, expiring
  bearer token (itsdangerous, salted). Every protected endpoint resolves the user via `get_current_user`.
  Supabase JWT auth arrives in Outcome 10; until then a non-local mode refuses with 503 rather than guessing.
- **Persistence** — SQLAlchemy 2 models for every spec §10 table; Alembic migrations (`backend/migrations`).
  JSON on SQLite, JSONB on Postgres. Deleting a project cascades to derived rows (FK `ON DELETE CASCADE`,
  SQLite `foreign_keys=ON`). A test asserts ORM models and migrations never drift.
- **Storage** — `ObjectStorage` protocol; `LocalObjectStorage` writes atomically with 0600 files under
  `DATA_DIR/objects`, validates server-generated keys, and blocks traversal/symlink escapes. Video bytes never
  enter the database.
- **Pose runtime** — `app/pose/runtime.py` reports model presence, SHA-256 verification and MediaPipe
  availability. `/api/health` is READY only when those *and* the analysis pipeline exist.
  `python -m app.pose.verify` loads the real model and runs a VIDEO-mode inference; `/api/health` runs a cached
  self-test of the same load so missing native libs show as LIMITED.
- **Reference analysis (Outcome 2)** — `app/pipeline/reference.py`: source → `media/transcode.py` canonical copy
  (24 fps H.264 ≤1280 px) + poster → `pose/extract.py` (FFmpeg decodes at 12 fps, MediaPipe VIDEO mode, up to 2
  poses) → `pose/quality.select_track` (one dancer, no silent identity switch) → `pose/features.py` (One-Euro
  smoothing, aspect correction, hip-root/torso-scale normalization, angles, travel, velocity, labelled estimates)
  → `pose/quality.assess` (coverage / multi-person / cropped-body gates) → one `reference_pose_frames` row per
  analysed frame. Failed gates still store frames so the debugger can show *why*.
- **Jobs** — `app/jobs/queue.py` (idempotent enqueue, conditional-UPDATE claim, heartbeat lease, recovery with
  max attempts, stuck-project repair) and `app/jobs/worker.py` (in-process thread when `WORKER_MODE=thread`).

## Planned (by outcome)

- Outcomes 3–9: segmentation, Teacher Mode, learner capture, normalization + bounded DTW, versioned scoring,
  feedback, report/dashboard — pure math in isolated `app/<domain>` modules with deterministic unit tests.
- Outcome 10: Postgres + durable worker (`FOR UPDATE SKIP LOCKED`), Supabase auth/storage adapters, rate limits.
- Outcome 11: Codespaces devcontainer + docker compose, Playwright E2E with a fake webcam.

## Development job model

Development runs **one** API process with the worker as a background thread (SQLite). Claims are conditional
UPDATEs, so even two processes can't run the same job; Outcome 10 adds a dedicated worker process and Postgres
`FOR UPDATE SKIP LOCKED`.

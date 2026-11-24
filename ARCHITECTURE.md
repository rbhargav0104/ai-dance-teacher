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
  `python -m app.pose.verify` loads the real model and runs a VIDEO-mode inference.

## Planned (by outcome)

- Outcome 1: streaming upload + FFprobe validation + no-residue cleanup, project list/delete, job records.
- Outcome 2: canonical transcode (FFmpeg), real pose extraction, quality gates, skeleton debugger.
- Outcomes 3–9: segmentation, Teacher Mode, learner capture, normalization + bounded DTW, versioned scoring,
  feedback, report/dashboard — pure math in isolated `app/<domain>` modules with deterministic unit tests.
- Outcome 10: Postgres + durable worker (`FOR UPDATE SKIP LOCKED`), Supabase auth/storage adapters, rate limits.
- Outcome 11: Codespaces devcontainer + docker compose, Playwright E2E with a fake webcam.

## Development job model

Development runs **one** API process. The durable worker and job claiming arrive with Outcome 1–2 (in-process,
SQLite) and Outcome 10 (Postgres row locking).

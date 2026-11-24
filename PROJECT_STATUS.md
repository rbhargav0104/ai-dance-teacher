# Project status

_Last updated: 2026-11-25 ~02:30 IST (build session 2)_

## Outcomes

| # | Outcome | State | Notes |
|---|---|---|---|
| 0 | Engineering foundation | **tested** | Exit gate met: clean clone → `scripts/setup.sh` → `scripts/dev.sh` → health + session + /me reachable directly and via the web proxy (`scripts/smoke.sh`). CI runs the same boot smoke. |
| 1 | Robust private reference intake | **tested** | Exit gate met (see below). Gap: no licence-verified *full-body* reference clip found yet — both committed samples crop the dancer above the knees. |
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

States: planned → implemented → tested → deployed. On schedule (Nov 25 target = Outcome 1).

### Outcome 1 exit gate — evidence
- *Valid media persists privately*: `test_valid_upload_persists_privately` (object stored 0600, bytes identical, no keys/paths in responses), MP4/MOV/WebM accepted; signed media URLs with range support (`test_media.py`); 85 MB upload through the Next proxy → 201 in 0.3 s (manual).
- *All rejection fixtures leave no residue*: `test_rejections_leave_no_residue` × 11 (txt, wrong/no extension, corrupt bytes, truncated file, audio-only, image-in-mp4, empty, 64×64, 0.4 s, 25 s over a 20 s limit) + oversize-while-streaming, declared Content-Length over limit, missing file, two files, unauthenticated, FFprobe timeout, DB failure mid-persist — each asserts no project/reference/job row, no stored object, no temp file.
- *Refresh preserves project/job state*: `test_list_get_refresh_and_delete_cascade` reads the project + intake job from a fresh app instance; Playwright flow reloads `/studio` and the library shows the uploads.

## What exists today

- **Reference intake (Outcome 1)**: `POST /api/projects` streams multipart to a temp file (byte limit enforced while
  streaming, extension rejected as soon as part headers arrive), FFprobe validates (timeout, argv only), then the source
  is stored privately and project + reference + intake-job rows commit atomically; any failure deletes the prefix.
  Idempotency-Key replays return the same project. `GET/DELETE /api/projects[/{id}]` (owner-scoped, same 404 for
  missing and foreign), `GET /api/projects/{id}/media/source` → 15-min signed URL → `GET /api/media/{token}` with HTTP
  ranges + `private, no-store`. `POST /api/projects/{id}/analysis` returns 503 `analysis_unavailable` (backend-enforced
  LIMITED). `GET /api/samples` + `POST /api/projects/sample` add a committed Mixkit clip through the same checks.
- **Studio UI**: drag-drop/choose, local preview with length/dimensions/size, remove/reselect, optional title, real
  byte-progress upload (XHR) with one 401 refresh, safe manual retry (same idempotency key), actionable errors, URL-import
  placeholder marked unsupported, privacy note; library cards with delete-confirm; dance page with private playback,
  metadata, warnings, disabled **Analyze Choreography** with the reason; `/studio?demo=1` sample picker.
- **Fixtures**: `fixtures/references/` — two Mixkit clips (1280×720, 14 s / 16 s, no audio), provenance + SHA-256 in
  `fixtures/fixture_manifest.json`, attribution in `fixtures/LICENSES.md`.

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

## Verified claims — session 2 (2026-11-25)

- `cd backend && uv run pytest` → 111 passed; ruff check/format + mypy strict clean.
- `cd frontend && npm test` → 24 passed; lint, typecheck, build clean.
- `scripts/smoke.sh` against built web + API → SMOKE OK (now also: sample intake via proxy, ranged media 206, delete → media 404).
- Playwright (1440×900 and iPhone 13): sample picker → dance page with playing video (readyState 4); file select →
  preview + metadata → upload → dance page; library after reload. No console errors, no horizontal overflow.

## Verified claims — session 1 (2026-11-24)

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
- No rate limiting yet (Outcome 10).
- Next's proxy buffers upload bodies in memory (limit raised to MAX_UPLOAD_MB+1). Fine for one user in dev/Codespaces;
  production should send uploads straight to the API or to signed storage uploads (Outcome 10/11).
- Library cards show the clip's real aspect ratio, not a thumbnail (thumbnails come with the canonical transcode, Outcome 2).
- Originals in codecs browsers can't play (e.g. HEVC .mov) show a "can't play the original" message until Outcome 2's playback copy.
- No full-body reference fixture yet (licence-verified). Best lead without a verifiable licence is recorded in docs/SOURCING.md.
- SQLite returns naive timestamps (UTC by convention); Postgres keeps tz.

## Owner action needed
_None. The owner only tests. Sessions source every asset themselves (see `docs/SOURCING.md`)._

## How Bhargav can test right now

The one-click Codespaces path lands on Dec 3. Until then:
1. Open the repo's **Actions** tab: the latest **CI** run should be green (backend, frontend, smoke).
2. Optional, on a machine with Node 20+, [uv](https://docs.astral.sh/uv/) and ffmpeg: `scripts/setup.sh && scripts/dev.sh`, then
   - http://localhost:3000/studio?demo=1 → **Use this sample** → the dance page plays the clip privately;
   - http://localhost:3000/studio → drop any MP4/MOV/WebM → preview → **Upload to studio**; try a .txt or an audio file to see the rejections;
   - delete a dance from its card or page. The pill says LIMITED and **Analyze Choreography** is disabled — expected until Outcome 2.

## Owner testing path (target)
- **GitHub Codespaces:** repo page → Code → Codespaces → Create. The devcontainer installs everything, downloads the model, seeds the demo, and starts the app on a forwarded HTTPS URL (webcam works).
- **Local alternative:** `docker compose up`, then open http://localhost:3000.

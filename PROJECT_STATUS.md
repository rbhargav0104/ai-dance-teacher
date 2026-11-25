# Project status

_Last updated: 2026-11-26 ~02:30 IST (build session 4)_

## Outcomes

| # | Outcome | State | Notes |
|---|---|---|---|
| 0 | Engineering foundation | **tested** | Exit gate met: clean clone → `scripts/setup.sh` → `scripts/dev.sh` → health + session + /me reachable directly and via the web proxy (`scripts/smoke.sh`). CI runs the same boot smoke. |
| 1 | Robust private reference intake | **tested** | Exit gate met (see below). Gap: no licence-verified *full-body* reference clip found yet — both committed samples crop the dancer above the knees. |
| 2 | Real reference pose + debugger | **tested** | Exit gate met (evidence below). Delivered a session early. Postgres `SKIP LOCKED` claiming deferred to Outcome 10 as planned. |
| 3 | Teachable sections | **tested** | Exit gate met (evidence below). Avatar retargeting maths started (`frontend/lib/avatar/retarget.ts`, unit-tested). |
| 4 | Teacher Mode — **3D AI avatar teacher with voice** | planned | Scope changed by the owner on Nov 25 (docs/SPEC_AMENDMENTS.md A1). Target Nov 27–28. |
| 5 | Learner capture + real learner pose | planned | |
| 6 | Normalized alignment | planned | |
| 7 | Versioned scoring | planned | |
| 8 | Actionable feedback | planned | |
| 9 | Report, repeat, dashboard | planned | |
| 10 | Production identity + durable infra | planned | |
| 11 | Stable deployment + full acceptance | planned | |

States: planned → implemented → tested → deployed. On the revised plan: Outcome 3 done in the Nov 26 am session; Outcome 4 (3D avatar) starts next.

### Outcome 3 exit gate — evidence
- *Sections cover the whole video without gap/overlap*: analysis now ends with a `segmenting` stage that suggests
  sections from stored measurements (`app/pose/segmentation.py`: motion energy, local pauses, direction reversals,
  pose transitions; DP prefers 3–7 s, 2–8 s hard limits). Pure tests cover short clip, long continuous movement, clear
  pauses (cuts land within 0.6 s of each pause), no movement, missing pose spans, sparse frames. Real-footage tests
  assert full tiling on the Mixkit clip (2 sections: 0–6.917, 6.917–14.0; boy clip 3 sections).
- *Edits persist*: `PATCH /api/projects/{id}/segments` validated server-side (`sections_gap`, `sections_overlap`,
  `sections_incomplete`, `section_too_short`, `unknown_section`, `too_many_sections` → 422, nothing changed);
  unchanged sections keep thumbnail/instruction/completion, moved ones get fresh midpoint thumbnails + instructions and
  `manual`; split / merge / regenerate tested through the API and in the browser (split → save → reload keeps 3 sections).
- *Every section loops accurately*: player acts one frame (1/24 s) before the section end via `requestVideoFrameCallback`
  (rAF fallback). Playwright at 1× on the 0–6.917 s section for 2.3 loops: max currentTime 6.903 s, 2 wraps, never
  entered the next section. Pure loop rule unit-tested.

### Outcome 2 exit gate — evidence
- *Real sample/upload → correctly aligned skeleton*: `test_sample_reference_yields_aligned_skeleton_and_features` runs the
  real worker + MediaPipe on the committed Mixkit clip: 168 frames at 12 fps, 89% coverage, `cropped_body` warning; for
  sampled valid frames the torso midline lands on the dancer's (non-green) pixels in the canonical video and a background
  point stays green; nose above shoulders above hips on every valid frame; angles in 0–180°, ankle angles null (feet hidden).
- *Inspectable landmarks/angles*: `GET /api/projects/{id}/poses` + `/studio/projects/{id}/debug` (video + skeleton with IDs,
  frame stepping, per-frame confidence/angles/normalized pose/travel/energy/excluded joints, versions). Screenshots reviewed
  at 1440×900 and iPhone 13; no console errors, no horizontal overflow.
- *Low-quality and multi-person clips fail honestly* (real footage, FFmpeg variants generated in the test):
  two dancers side by side → `multiple_people`; dancer hidden for 10 of 14 s → `low_coverage` ("trackable in N%");
  empty scene → `no_dancer_detected`. Failed jobs are non-retryable; frames stay inspectable.
- *Real progress and recovery*: worker heartbeats stage + fraction; lapsed lease → requeue, 3rd interruption → failed/retryable;
  project stuck "processing" without a job → repaired; delete during a job → job stops, no stored objects remain; idempotent
  re-requests return the active job. `scripts/smoke.sh` on a READY server analyses the sample through the web proxy.

### Outcome 1 exit gate — evidence
- *Valid media persists privately*: `test_valid_upload_persists_privately` (object stored 0600, bytes identical, no keys/paths in responses), MP4/MOV/WebM accepted; signed media URLs with range support (`test_media.py`); 85 MB upload through the Next proxy → 201 in 0.3 s (manual).
- *All rejection fixtures leave no residue*: `test_rejections_leave_no_residue` × 11 (txt, wrong/no extension, corrupt bytes, truncated file, audio-only, image-in-mp4, empty, 64×64, 0.4 s, 25 s over a 20 s limit) + oversize-while-streaming, declared Content-Length over limit, missing file, two files, unauthenticated, FFprobe timeout, DB failure mid-persist — each asserts no project/reference/job row, no stored object, no temp file.
- *Refresh preserves project/job state*: `test_list_get_refresh_and_delete_cascade` reads the project + intake job from a fresh app instance; Playwright flow reloads `/studio` and the library shows the uploads.

## What exists today

- **Learn Mode + teachable sections (Outcome 3)**: an analysed dance opens on a section player — large canonical video
  (mirrored by default), Play/Restart/±1 analysed frame, 0.25/0.5/0.75/1× speed, Loop, Mirror, Skeleton toggles; a
  timeline of section chips with midpoint thumbnails and a playhead; **Edit sections** mode with draggable (and
  keyboard ← → / Shift) boundary handles, Split at playhead, Merge with next, Reset to automatic, Save/Cancel. The side
  card shows the section, an **experimental** instruction worded only from measured facts (arm above shoulder, travel,
  knee bend only when legs were tracked, elbow bend, lean, relative pace), which swaps sides between mirror and direct
  view, per-section tracked-frame coverage, "not tracked here" limbs, Mark complete, Previous/Next.
  API: `GET/PATCH /api/projects/{id}/segments`, `PATCH /segments/{sid}` (title/completed), `POST /segments/regenerate`.

- **Reference analysis (Outcome 2)**: **Analyze Choreography** (or picking a sample) queues a durable job. The in-process
  worker makes a 24 fps H.264 canonical copy + poster, runs MediaPipe Pose Landmarker (VIDEO mode, 12 fps, up to 2 people),
  follows one dancer, smooths (One-Euro), normalizes (aspect-corrected, hip root, median torso scale), measures joint angles,
  travel, speed/energy, lean/tilts, an experimental yaw and a labelled centre-of-mass estimate, then applies quality gates.
  The dance page shows live stage/progress (survives refresh), the tracked skeleton over the canonical video, coverage and
  joint confidence ("not a dance score"), and actionable failures. `/studio/projects/{id}/debug` is the developer debugger.

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

## Verified claims — session 4 (2026-11-26 am)

- `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` → clean; 169 passed.
- `cd frontend && npm run lint && npm run typecheck && npm test && npm run build` → clean; 50 passed.
- `scripts/smoke.sh` on built web + API (READY) → SMOKE OK incl. sections: full coverage, thumbnail, edit, 422 on a bad edit, regenerate.
- `node scripts/e2e/learn-mode.cjs` (Playwright, 1440×900 + iPhone 13): loop accuracy above, mirror swaps instruction
  sides, split+save persists across reload, mark complete, no console errors, no horizontal overflow. Screenshots reviewed.

## Verified claims — session 3 (2026-11-25 pm)

- `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` → clean; 133 passed
  (13 pure-math, 8 end-to-end on real footage, ~42 s total).
- `cd frontend && npm run lint && npm run typecheck && npm test && npm run build` → clean; 33 passed.
- `scripts/smoke.sh` against built web + API (READY) → sample analysed through the proxy: 168 frames, 149 valid, coverage 0.887.
- API boots without the vision extra (LIMITED) — checked by import with numpy/mediapipe blocked; CI smoke now runs both modes.
- Playwright desktop + iPhone 13: sample → live progress → skeleton overlay → debugger; two-dancer upload → honest failure.

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

- Not built yet: the 3D avatar teacher (Outcome 4, owner amendment A1). Today a dance page shows the video with a
  skeleton overlay and a developer debugger. Those are analysis views, not the teaching experience.
- Library cards show an empty placeholder instead of the poster frame; studio sample copy still says "once analysis is on".
- Section instructions use 2-D image-plane angles (foreshortening can under-read elbow angles, e.g. "about 20°") and assume
  the dancer faces the camera; labelled experimental. Boundary tuning is checked on 2 real clips + synthetic sequences.
- While editing, chips whose boundaries moved show no thumbnail until saved (server regenerates them).
- World landmarks used by the avatar are stored raw; the avatar will smooth them (One-Euro) client-side in Outcome 4.

- Smoothing parameters and gate thresholds (55%/85% coverage, 20% multi-person, 0.5 visibility) are spec defaults checked
  on 2 clips + variants only; recalibrate with more fixtures (Outcome 7).
- Joint angles are 2-D (image plane); world landmarks are stored but not yet used. Yaw is experimental and labelled so.
- Library cards don't show the new poster thumbnail yet (Outcome 3 thumbnails).
- No rate limiting yet (Outcome 10).
- Next's proxy buffers upload bodies in memory (limit raised to MAX_UPLOAD_MB+1). Fine for one user in dev/Codespaces;
  production should send uploads straight to the API or to signed storage uploads (Outcome 10/11).
- Originals in codecs browsers can't play (e.g. HEVC .mov) play from the canonical copy once analysed; before analysis they show a message.
- No full-body reference fixture yet (licence-verified). Best lead without a verifiable licence is recorded in docs/SOURCING.md.
- SQLite returns naive timestamps (UTC by convention); Postgres keeps tz.

## Owner action needed
_None. The owner only tests. Sessions source every asset themselves (see `docs/SOURCING.md`)._

## How Bhargav can test right now

The one-click Codespaces path lands on Dec 3. Until then:
1. Open the repo's **Actions** tab: the latest **CI** run is green (verified for de45e83) (backend incl. real-footage analysis tests, frontend, smoke
   which analyses the sample end to end on a READY server and checks LIMITED mode without the vision stack).
2. Optional, on a machine with Node 20+, [uv](https://docs.astral.sh/uv/) and ffmpeg (Linux also: `libegl1 libgles2 libgl1`):
   `scripts/setup.sh && scripts/dev.sh`, then
   - http://localhost:3000/studio?demo=1 → **Use this sample** → watch the progress ring (~10 s) → the skeleton tracks the
     dancer on the video → **Open pose debugger** → step frames with ← / →, toggle IDs, click landmarks;
   - on the dance page, pick a section on the timeline, press play (it loops the section at 0.5×), try 0.25×, Mirror off
     (the instruction swaps left/right), **Edit sections** → drag a lime handle / Split at playhead → **Save sections**,
     reload, then **Mark complete** and **Next section**;
   - upload your own MP4/MOV/WebM at http://localhost:3000/studio → **Analyze Choreography**. A clip with two people, or one
     where you leave the frame for most of it, should stop with a clear explanation instead of a result.

## Owner testing path (target)
- **GitHub Codespaces:** repo page → Code → Codespaces → Create. The devcontainer installs everything, downloads the model, seeds the demo, and starts the app on a forwarded HTTPS URL (webcam works).
- **Local alternative:** `docker compose up`, then open http://localhost:3000.

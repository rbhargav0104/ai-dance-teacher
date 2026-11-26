# Project status

_Last updated: 2026-11-27 ~03:00 IST (build session 6)_

## Outcomes

| # | Outcome | State | Notes |
|---|---|---|---|
| 0 | Engineering foundation | **tested** | Exit gate met: clean clone → `scripts/setup.sh` → `scripts/dev.sh` → health + session + /me reachable directly and via the web proxy (`scripts/smoke.sh`). CI runs the same boot smoke. |
| 1 | Robust private reference intake | **tested** | Exit gate met (see below). Gap: no licence-verified *full-body* reference clip found yet — both committed samples crop the dancer above the knees. |
| 2 | Real reference pose + debugger | **tested** | Exit gate met (evidence below). Delivered a session early. Postgres `SKIP LOCKED` claiming deferred to Outcome 10 as planned. |
| 3 | Teachable sections | **tested** | Exit gate met (evidence below). Avatar retargeting maths started (`frontend/lib/avatar/retarget.ts`, unit-tested). |
| 4 | Teacher Mode — **3D AI avatar teacher with voice** | **tested** | Exit gate (A1) met on desktop + iPhone 13 (evidence below), a day early. Unverified: real spoken audio (headless browsers have the API, not speakers) and GPU frame rate on real devices. Optional v2 skinned avatar not started. |
| 5 | Learner capture + real learner pose | **tested** | Exit gate met (evidence below), ~1.5 days ahead of plan. Real webcam path verified with Chromium's fake camera fed real footage; a human webcam + phone camera not tried yet. |
| 6 | Normalized alignment | planned | |
| 7 | Versioned scoring | planned | |
| 8 | Actionable feedback | planned | |
| 9 | Report, repeat, dashboard | planned | |
| 10 | Production identity + durable infra | planned | |
| 11 | Stable deployment + full acceptance | planned | |

States: planned → implemented → tested → deployed. Ahead of the revised plan: Outcome 5 done Nov 27 am (planned Nov 28–29). Next: Outcome 6 normalized alignment.

### Outcome 5 exit gate — evidence ("a learner attempt produces real stored pose data and can be reviewed beside the reference")
- *Webcam → real stored pose*: `node scripts/e2e/practice.cjs` (also in CI) feeds Chromium's fake camera a real fixture
  video, opens the dance → **Practise this section** → Turn on camera (mirrored preview) → Record → 3-2-1 → recording with
  the reference section playing in the corner, elapsed clock → Stop → preview → Record again → Use this take. The attempt
  (WebM, no container duration → stream-copy repair) is analysed by the real worker: 65 frames, 53 valid, coverage 0.82,
  `learner-pose-1`, same model hash as the reference, linked to the section, stored unmirrored.
- *Reviewed beside the reference*: side-by-side page plays the reference section and the attempt in step (drift 0.000 s
  after 2 s of playback), measured skeletons on both, 0.5/0.75/1×, scrub, mirror; tracking stats + notes, "nothing on this
  page is a score". Desktop 1440×900 and iPhone 13: no console errors, no horizontal overflow.
- *Upload path + honest quality*: the real `girl_mirrored` variant uploaded via the file picker → analysed, cropped-legs
  note shown. (The occluded variant lands either side of the 55% coverage gate depending on CPU: 0.73 locally, failed
  `low_coverage` on the CI runner — both honest; the pytest asserts the masked frames in either case.) Camera permission denied → "Camera access is blocked" + upload fallback. Attempt delete from the list → 404.
- *Same pipeline, same gates* (`tests/test_practice_analysis.py`, real MediaPipe on FFmpeg variants of real footage):
  thresholds/smoothing/model identical to the reference; `girl_good` coverage within 0.08 of the reference; skeleton lands on
  the learner's pixels; occluded 5–8 s frames invalid (≥ 80%) and coverage ≥ 0.15 lower; two dancers → `multiple_people`
  (still inspectable); the dance's own status/latest job untouched by attempt jobs; delete while queued removes the job.
- *API contract* (`tests/test_practice_api.py`, 13 tests): 409 before the dance is analysed; private 0600 storage, ranged
  media; LIMITED stores but never analyses (503); idempotent retry; per-dance quota; owner isolation (same 404); 5 rejection
  kinds + bad section + bad capture source leave no row/object/temp file; dance delete cascades attempts and media.

### Outcome 4 exit gate — evidence (docs/SPEC_AMENDMENTS.md A1)
- *Learn a sample section by section from the 3D avatar, desktop + mobile*: `node scripts/e2e/teacher-mode.cjs` (also in CI)
  opens both analysed Mixkit samples at 1440×900 and iPhone 13: avatar stage renders, count-in "5 6 7 8" appears, the
  section plays at 1× with captions ("Raise your right arm above shoulder level."), Side / 3/4 / Front cameras, swap to
  video-main with avatar PiP, Mark complete → Next section → Previous → undo; no console errors, no horizontal overflow.
  Play/loop/0.25–1×/mirror are the Outcome 3 controls, now driving the avatar too (`learn-mode.cjs` still passes).
- *Avatar arm matches the measured landmarks at known timestamps*: rendered bone directions (read back from the meshes)
  vs raw API world landmarks at t = 1, 3, 5.5, 8, 10.5, 12.5 s, mirror on and off. Girl sample: median 2.2°, max 6.1°
  (36 bones). Boy sample: median 3.7–5.5°, max 27.9° (one fast forearm; smoothing + depth noise). Gate: median ≤ 8°, max ≤ 30°.
  Screenshots at those timestamps are uploaded as a CI artifact (`teacher-mode-screenshots`).
- *Untracked limbs visibly marked, not animated*: both samples crop the legs → "Not tracked in this video: legs · shown
  ghosted" (or "lower legs" when a thigh is tracked in most frames, as on the CI runner); every bone in the clip's
  ghosted set reports `untracked` at every checked timestamp (rest pose, 16% opacity).
- *Unit tests of the retargeting maths*: `tests/avatar-retarget.test.ts`, `avatar-track.test.ts` (One-Euro, gap bridging
  ≤ 2 frames, rare-limb ghosting, direction interpolation, fixed lengths, lost/outside, mirror side swap),
  `avatar-cues.test.ts` (perspective wording, caption timing, 8-count, count-in).

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

- **Practice (Outcome 5)**: from a section card (**Practise this section**) or the dance page (**Practise & review attempts**)
  → `/studio/projects/{id}/practice`: pick Full dance or a section; **Record with camera** (setup tips, permission handling,
  mirrored preview saved unmirrored, framing guide, 3-2-1, REC clock with auto-stop at target + 3 s, muted reference guide in
  the corner, stop → preview → record again / use this take) or **Upload a video** (preview, "this video is mirrored").
  Real byte-progress upload with safe retry. `/studio/practice/{id}`: live analysis progress, honest failures with
  re-record, LIMITED "stored, not analysed", and once measured: reference + attempt side by side in step with skeletons,
  tracking stats and notes; attempts list with delete. API: `POST/GET /api/projects/{id}/practice-sessions`,
  `GET/DELETE /api/practice-sessions/{id}`, `POST …/analysis`, `GET …/poses`, `GET …/media/{source|canonical|poster}`.
  No comparison or scoring yet (`scored: false`).

- **Teacher Mode — 3D AI avatar (Outcome 4)**: an analysed dance opens on a studio stage where an original procedural
  mannequin performs the dancer's measured movement (MediaPipe world landmarks, One-Euro smoothed, fixed bone lengths).
  It follows the section player (loop, 0.25–1×, mirror by default), with the real video picture-in-picture (swap with
  **Video ⤢ / Avatar ⤢**), Front / 3/4 / Side cameras plus drag-to-orbit, a coach bar with always-on captions, an even
  8-count, a **Voice** toggle (Web Speech) and a "5, 6, 7, 8" count-in. Untracked limbs are ghosted and labelled;
  unmeasured moments show "Tracking lost here". Without WebGL it says so and keeps the 2-D skeleton on the video.

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

## Verified claims — session 6 (2026-11-27 am)

- `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` → clean; 184 passed.
- `cd frontend && npm run lint && npm run typecheck && npm test && npm run build` → clean; 76 passed.
- Built web + API (READY): `scripts/smoke.sh` → SMOKE OK; `node scripts/e2e/practice.cjs` → PRACTICE CHECK OK;
  `teacher-mode.cjs` → OK (girl median 2.2°, boy max 27.9°); `learn-mode.cjs` → OK. Screenshots reviewed (desktop + iPhone 13).

## Verified claims — session 5 (2026-11-26 pm)

- `cd frontend && npm run lint && npm run typecheck && npm test && npm run build` → clean; 67 passed.
- Backend unchanged this session; `cd backend && uv run pytest -q` at session start → all passed (Outcome 3 gate re-check).
- `scripts/smoke.sh` on built web + API (READY) → SMOKE OK.
- `node scripts/e2e/teacher-mode.cjs` → TEACHER MODE CHECK OK (numbers above); `node scripts/e2e/learn-mode.cjs` → loop max
  6.877 s < 6.917 s, edits persist, no errors/overflow. Screenshots of desktop, mobile, all three camera views, PiP reviewed.

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

- Practice: not yet tried with a human on a real laptop webcam or phone camera (Safari records MP4 — code path exists,
  untested). Side-by-side is lined up from the start only; movement alignment, mirror detection, scores and feedback are
  Outcomes 6–8. Upload goes through the Next proxy (buffers in memory, see below).
- Torso scale measured 0.48× (not 0.6×) on the 60%-scaled variant (hips on the frame edge) — Outcome 6 normalization input.

- Avatar: spoken audio not verified by a human ear yet (headless Chromium exposes speechSynthesis but has no speakers);
  real-device GPU frame rate not measured (headless SwiftShader software GL renders ~37 fps). Avatar stays hip-centred
  (no floor travel). Torso twist comes from the shoulder line only. Skinned v2 avatar not started (optional per A1).
- Library cards show an empty placeholder instead of the poster frame.
- Section instructions use 2-D image-plane angles (foreshortening can under-read elbow angles, e.g. "about 20°") and assume
  the dancer faces the camera; labelled experimental. Boundary tuning is checked on 2 real clips + synthetic sequences.
- While editing, chips whose boundaries moved show no thumbnail until saved (server regenerates them).

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
1. Open the repo's **Actions** tab → latest **CI** run. The *smoke* job runs the Teacher Mode and Practice browser checks;
   download the **teacher-mode-screenshots** artifact (practice screenshots are in its `practice/` folder).
2. Optional, on a machine with Node 20+, [uv](https://docs.astral.sh/uv/) and ffmpeg (Linux also: `libegl1 libgles2 libgl1`):
   `scripts/setup.sh && scripts/dev.sh`, then
   - http://localhost:3000/studio?demo=1 → **Use this sample** → wait ~10 s for the analysis → the 3D avatar appears;
   - press play: you hear/see "5, 6, 7, 8", then the avatar dances the section at 0.5× while the video plays small in the
     corner and the coach bar captions (and speaks) the measured cue. Try 0.25×, **Mirror** off, **Side** / **3/4**, drag to
     orbit, **Video ⤢** to swap, **Voice** off; the legs are ghosted with a "not tracked in this video" label because the
     sample crops them;
   - **Mark complete** → **Next section**; **Edit sections** still lets you drag/split boundaries;
   - on a phone (same Wi-Fi, http://<laptop-ip>:3000) the stage switches to a tall layout;
   - **Practise this section** → Turn on camera → Record → dance along with the corner video → Stop → Use this take →
     ~10 s later you and the reference play side by side with skeletons. (Camera needs localhost or https; on a phone over
     plain http use **Upload a video** instead.)

## Owner testing path (target)
- **GitHub Codespaces:** repo page → Code → Codespaces → Create. The devcontainer installs everything, downloads the model, seeds the demo, and starts the app on a forwarded HTTPS URL (webcam works).
- **Local alternative:** `docker compose up`, then open http://localhost:3000.

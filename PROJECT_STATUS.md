# Project status

_Last updated: 2026-11-28 ~16:00 IST (build session 9)_

## Outcomes

| # | Outcome | State | Notes |
|---|---|---|---|
| 0 | Engineering foundation | **tested** | Exit gate met: clean clone → `scripts/setup.sh` → `scripts/dev.sh` → health + session + /me reachable directly and via the web proxy (`scripts/smoke.sh`). CI runs the same boot smoke. |
| 1 | Robust private reference intake | **tested** | Exit gate met (see below). Gap: no licence-verified *full-body* reference clip found yet — both committed samples crop the dancer above the knees. |
| 2 | Real reference pose + debugger | **tested** | Exit gate met (evidence below). Delivered a session early. Postgres `SKIP LOCKED` claiming deferred to Outcome 10 as planned. |
| 3 | Teachable sections | **tested** | Exit gate met (evidence below). Avatar retargeting maths started (`frontend/lib/avatar/retarget.ts`, unit-tested). |
| 4 | Teacher Mode — **3D AI avatar teacher with voice** | **tested** | Exit gate (A1) met on desktop + iPhone 13 (evidence below), a day early. Unverified: real spoken audio (headless browsers have the API, not speakers) and GPU frame rate on real devices. Optional v2 skinned avatar not started. |
| 5 | Learner capture + real learner pose | **tested** | Exit gate met (evidence below), ~1.5 days ahead of plan. Real webcam path verified with Chromium's fake camera fed real footage; a human webcam + phone camera not tried yet. |
| 6 | Normalized alignment | **tested** | Exit gate met on real footage (evidence below). |
| A2 | Choose the dancer (multi-person videos) | **tested** | Amendment exit gate met on real composited footage + Playwright desktop/mobile (evidence below). Scores follow automatically once Outcome 7 exists. |
| 7 | Versioned scoring | **tested** | Exit gate met on real footage, 2 references (evidence below), two days ahead of plan. Gap: no third reference dance and no real wrong-limb fixture (synthetic tests cover wrong arm/elbow). |
| 8 | Actionable feedback | planned | |
| 9 | Report, repeat, dashboard | planned | |
| 10 | Production identity + durable infra | planned | |
| 11 | Stable deployment + full acceptance | planned | |

States: planned → implemented → tested → deployed. Ahead of the revised plan: Outcome 6 done Nov 27 pm (planned Nov 29). A2 (choose the dancer) done Nov 28 early. Outcome 7 done Nov 28 pm (planned Nov 30). Next: Outcome 8 actionable feedback.

### Outcome 7 exit gate — evidence ("scores are deterministic, bounded, evidence-linked, and suppressed/qualified when data quality is inadequate")
- *Golden relationships on real footage* (`tests/test_scoring_golden.py`, 21 claims in `fixtures/fixture_manifest.json`
  → `scoring_relations`, both Mixkit references analysed by the real worker + MediaPipe, attempts are committed FFmpeg
  variants). Measured (overall · pose / timing / sequence / angles / rhythm): girl_good 97.9 (97/100/99/100/90);
  occluded 98.9 but confidence 0.72 vs 0.86 and 23 fewer moments compared; 0.4 s late 92.3 (pose 97, timing 73);
  0.9×/1.1× 84 (pose 97, timing 48/57); mirrored 92.9, compared as a mirror image; 4 s freeze 87.6 (sequence 80);
  60 %-size shifted 83.6 qualified (pose 73 — small figures measure less precisely); different dance 22.5.
  Second reference: boy_good 99.6, boy late 92.4 (timing 74, pose 99), girl's dance vs boy 26.1; rhythm honestly
  unavailable on the boy clip (no clear motion accents) and re-weighted.
- *Pure rules* (`tests/test_scoring_math.py`, 19 tests, synthetic sequences through the stored-payload path): curve
  bounded/monotonic; product weights; identical ≥ 95; size/position don't dominate; 0.5 s late hits timing ≥ 15 more than
  pose; wrong arm height lowers pose and names the left arm in every worst moment; straight elbow lowers joint angles;
  freeze lowers sequence; untracked span lowers confidence not points; mostly untracked → not scored; low confidence →
  suppressed with no numbers; qualified path; immobile reference → not scored; rhythm gated (too short / no accents) and
  re-weighted; tempo lowers rhythm; section breakdown finds the weak half; random movements stay in 0–100; deterministic
  (byte-identical report); alignment from other sequences rejected.
- *API contract* (`tests/test_report_api.py`): 409 before analysis, same 404 for foreign/missing; stored row reused
  (`cached`), summary on the attempt + list; section attempt scored on its window; moving a boundary invalidates the
  stored score; without numpy → 503 (nothing estimated); delete removes the stored score.
- *Browser* (`node scripts/e2e/practice.cjs`, also in CI): score card status/overall equal the report; withheld state
  shows no numbers; "Moments to replay" seeks the attempt 1 s before the moment and plays both videos; flipped upload
  scored as a mirror image with per-section breakdown; attempt list shows the stored score; desktop + iPhone 13 without
  overflow or console errors.

### A2 exit gate — evidence ("pick the left dancer → everything follows the left dancer; re-run with the right; a crossing never switches silently")
- *Real footage* (`tests/test_subject_choice.py`, real MediaPipe on `fixtures/multi/*`, identity checked on the video's own
  pixels: girl = maroon top, boy = navy shirt, sampled under the followed torso in every checked frame):
  two dancers → status `needs_subject` with 2 candidates (left/right, boxes apart, each followable in > 80 %), private
  JPEG of the choosing frame, sections refused (409) until a choice; pick person 1 → analysed, every frame is the girl
  (0 boy frames), sections tile the 8 s, "other people ignored" warning; same pick again → 200, no new job; pick person 2
  → every frame is the boy, candidates unchanged. Swapped positions → "left" follows the boy. Girl vanishes 3–5.5 s →
  those frames invalid and labelled lost, `chosen_dancer_lost` warning, 0 boy frames. Boy drifts across and hides the
  girl → whichever person is followed, 0 frames of the other.
- *Pure rules* (`tests/test_people.py`, 9 tests): overlapping second detection = same person; boxes/overlap; torso
  histogram + distance; candidates numbered left→right; crossing keeps identity; leaving → masked, comes back after the gap;
  look-alikes overlapping → never the wrong one; no appearance → only an unambiguous single body; re-locating the choice.
- *API contract* (`tests/test_subject_api.py`): one person → 409; unknown person → 422 (nothing stored); foreign owner →
  same 404; LIMITED → choice stored + 503 (status stays `needs_subject`); READY → 202 queued, same choice → same job,
  different choice mid-job → 409.
- *Browser* (`node scripts/e2e/choose-dancer.cjs`, also in CI): real duo upload → picker with the real frame, numbered
  outlines and 3:4 crops → desktop picks left → Learn Mode "Following person 1 (left) for the whole video", 90/90 frames
  on the left; iPhone 13 → **Follow someone else** → person 2 → 85/85 frames on the right; no console errors, no overflow.
- Re-checks: Teacher Mode arm errors identical to before (girl median 2.2°/max 6.1°, boy max 27.9°); practice, learn-mode
  and smoke browser checks pass.

### Outcome 6 exit gate — evidence ("scale/translation/speed tests behave as intended while wrong-limb, late and missing-movement tests remain distinguishable")
- *Real footage* (`tests/test_alignment_api.py`, real MediaPipe on FFmpeg variants of the Mixkit clip; mean per-pair movement
  distance after alignment, good attempt ≈ 0.07, different dance ≈ 0.50):
  shifted 200 px ≈ good (+0.00); speed 0.9×/1.1× ≈ good (+0.00) with pace measured 1.105/0.909 (timing kept, equal-time
  pairing ≈ 0.21); 0.4 s late ≈ good with offset 0.42 s; zoom 0.8 and 60 % size sit at 0.21 / 0.34 of the way to a different
  dance (the pose model measures small figures less precisely — their scale-free angle error also grows 2–4×); hflipped
  video → mirrored chosen ("clear", 0.89 as recorded vs 0.17 mirrored); 4 s freeze → missing span 5.25–8.9 s; 3 s blocked
  view → masked span, costs null there (never "wrong"); section attempt aligned to its window; moving the section boundary
  invalidates the cached alignment.
- *Synthetic invariance/sensitivity* (`tests/test_alignment_math.py`, 31 tests through the stored-payload path): size,
  position, resolution, portrait, taller subject, ±25 % speed stay within +0.06 of identical; wrong arm height, wrong elbow,
  opposite sweep, 28° lean, reversed phrase are ≥ +0.12; missing movement and 1 s late movement located in time; mirror
  transform is an involution; symmetric movement keeps the preferred mode and says "ambiguous"; gates for untracked
  attempt/reference and immobile reference; frozen learner can't earn many matches; DTW band/monotonicity/known shift.
- *Debug alignment view*: `/studio/practice/{id}/alignment` (path chart with band, per-moment distance strip with
  missing/masked/timing spans, stats, sides decision, measured facts). Attempt review plays the reference along the
  alignment path by default ("Matched moves" / "Same time"). Browser check (`practice.cjs`): reference position matches
  the path within 0.25 s, every paired frame drawn, desktop + iPhone 13 without overflow or console errors.

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
  note shown.  Camera permission denied → "Camera access is blocked" + upload fallback. Attempt delete from the list → 404.
- *Same pipeline, same gates* (`tests/test_practice_analysis.py`, real MediaPipe on FFmpeg variants of real footage):
  thresholds/smoothing/model identical to the reference; `girl_good` coverage within 0.08 of the reference; skeleton lands on
  the learner's pixels; view blocked 5–8 s → those frames invalid (≥ 80%) and coverage ≥ 0.15 lower; two dancers → `multiple_people`
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

- **Scoring (Outcome 7)**: `GET /api/practice-sessions/{id}/report` → versioned report (`score-1` on `align-1`): overall
  0–100 + pose / timing / sequence / joint angles / rhythm (experimental, gated), the weights actually used, coverage
  (reference + learner tracking, compared moments, visible joints, alignment confidence, warp, confidence), measured
  evidence per component, body parts, worst/best moments (with times on both videos), per-section breakdown for
  full-dance attempts, warnings, and status `scored` / `qualified` / `suppressed` / `not_scored`. Stored in
  `performance_scores`; attempt responses carry a `score` summary. The attempt page shows the score card above the
  timing facts; moments replay in the side-by-side player.

- **Choose the dancer (A2)**: up to 4 real detections per frame; overlapping duplicates merged. When several people are
  visible for more than 20 % of a reference or attempt, analysis stops at **"Who should we follow?"**: the clearest real
  frame with each person outlined and numbered, a 3:4 crop of each, where they are and how much of the video they're in.
  Tap one → the real analysis re-runs following only that person (position + torso-colour identity); frames where they're
  lost or can't be told apart are masked and labelled ("Lost the dancer you chose here" on the avatar), never filled with
  someone else. The dance/attempt page shows whom it follows and offers **Follow someone else**. API:
  `POST /api/projects/{id}/subject`, `POST /api/practice-sessions/{id}/subject`, media kind `people`; `subject` on
  reference/attempt responses; per-frame `subject` status in poses. Migration 0007.

- **Alignment (Outcome 6)**: `GET /api/practice-sessions/{id}/alignment` aligns an analysed attempt to its reference window
  (`app/pose/alignment.py`, `align-1`): hip-centred torso-scaled shape + a global limb-ratio body-size factor; per pair a
  translation + bounded (±15 %) scale fit; cost = position (depth ×0.3, worst-3-joint focus) + joint angles + lean + motion
  direction; unmeasured pairs are masked. Learner compared as recorded and mirrored, switch only when ≥ 10 % better,
  decision stored. Two-pass bounded DTW (±max(2 s, 35 % of the window)), warp penalty, free lead-in/tail on the learner,
  every reference frame matched, collapse so a learner frame is credited once. Original timestamps kept: offset, robust
  pace (Theil–Sen), local deviation, "recording ended early". Accounting: masked vs missing spans. Cached on the attempt
  until either analysis or the section window changes; needs only numpy (works in LIMITED from stored frames).
  Measurements only — `scored: false` until Outcome 7.

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

## Verified claims — session 9 (2026-11-28 pm)

- `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` → see RUN_LOG.
- `cd frontend && npm run lint && npm run typecheck && npm test && npm run build` → clean; 101 passed.
- Built web + API (READY): `scripts/smoke.sh` → SMOKE OK; `practice.cjs` (incl. score card) → PRACTICE CHECK OK;
  `teacher-mode.cjs`, `choose-dancer.cjs`, `learn-mode.cjs` → OK. Score card screenshots reviewed (desktop + iPhone 13).

## Verified claims — session 8 (2026-11-28 early)

- `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` → see RUN_LOG.
- `cd frontend && npm run lint && npm run typecheck && npm test && npm run build` → clean; 91 passed.
- Built web + API (READY): `scripts/smoke.sh` → SMOKE OK; `node scripts/e2e/choose-dancer.cjs` → CHOOSE DANCER CHECK OK;
  `teacher-mode.cjs`, `practice.cjs`, `learn-mode.cjs` → OK. Picker screenshots reviewed (desktop + iPhone 13).

## Verified claims — session 7 (2026-11-27 pm)

- `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` → see RUN_LOG (full suite).
- `cd frontend && npm run lint && npm run typecheck && npm test && npm run build` → clean; 86 passed.
- Built web + API (READY): `node scripts/e2e/practice.cjs` → PRACTICE CHECK OK incl. alignment checks; screenshots reviewed.

## Verified claims — session 6 (2026-11-27 am)

- `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` → clean; 184 passed.
- `cd frontend && npm run lint && npm run typecheck && npm test && npm run build` → clean; 76 passed.
- Built web + API (READY): `scripts/smoke.sh` → SMOKE OK; `node scripts/e2e/practice.cjs` → PRACTICE CHECK OK;
  `teacher-mode.cjs` → OK (girl median 2.2°, boy max 27.9°); `learn-mode.cjs` → OK. Screenshots reviewed (desktop + iPhone 13).
- CI run 45898502567 (0f00636) → green, incl. the Practice browser check on the runner.

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
  untested). Feedback items are Outcome 8. Upload goes through the Next proxy (buffers in memory, see below).
- Alignment: cost coefficients are calibrated on one reference clip (cropped at the hips) + its variants; smaller figures
  read as more different because the pose model measures them less precisely. A section attempt is expected to start with
  the section (the band is anchored at the recording's start). Re-check with more fixtures at Outcome 7.
- A2: people are told apart by torso colour; two people dressed alike who also overlap are masked rather than
  separated. Candidates come from one frame (the clearest with everyone apart) — someone who only appears at other
  times isn't offered. Picking re-runs MediaPipe (~10 s for a short clip) instead of reusing cached detections.
  Re-choosing a reference regenerates its automatic sections (manual section edits are lost). Practice-attempt picker
  is API-tested and uses the same component, but the browser check covers the reference page only.
- Torso scale measured 0.48× (not 0.6×) on the 60%-scaled variant (hips on the frame edge) — handled in alignment by the
  limb-ratio body-size factor and per-pair scale fit.

- Avatar: spoken audio not verified by a human ear yet (headless Chromium exposes speechSynthesis but has no speakers);
  real-device GPU frame rate not measured (headless SwiftShader software GL renders ~37 fps). Avatar stays hip-centred
  (no floor travel). Torso twist comes from the shoulder line only. Skinned v2 avatar not started (optional per A1).
- Library cards show an empty placeholder instead of the poster frame.
- Section instructions use 2-D image-plane angles (foreshortening can under-read elbow angles, e.g. "about 20°") and assume
  the dancer faces the camera; labelled experimental. Boundary tuning is checked on 2 real clips + synthetic sequences.
- While editing, chips whose boundaries moved show no thumbnail until saved (server regenerates them).

- Scoring: half-credit errors and gates calibrated on 2 references (both crop the legs) + their FFmpeg variants; no
  third reference, no real wrong-limb fixture, no human-rated attempts. Rhythm uses body-motion envelopes only (no
  audio) and is labelled experimental. A camera attempt whose recording doesn't line up with the section start can
  honestly be suppressed (seen with the looping fake camera).
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
     ~10 s later you and the reference play side by side with skeletons; the reference follows your moves along the
     measured alignment (**Same time** switches to the clock); above the timing facts the **score card** shows your
     score out of 100 with pose / timing / sequence / joint angles / rhythm, what each was measured from, how much was
     compared and how confident it is ("low confidence" or no number at all when tracking was poor); tap a
     "Moment to replay" to jump both videos there; "Timing & sides" lists measured facts (late/early, pace,
     mirrored, missed or untracked passages) and **See how moves were paired** opens the alignment view.
   - **Two dancers**: upload `fixtures/multi/duo_girl_left.mp4` from the repo → **Analyze Choreography** → "Who should we
     follow?" → tap either dancer → ~10 s later the avatar and sections follow only that person; **Follow someone else**
     switches. (Camera needs localhost or https; on a phone over
     plain http use **Upload a video** instead.)

## Owner testing path (target)
- **GitHub Codespaces:** repo page → Code → Codespaces → Create. The devcontainer installs everything, downloads the model, seeds the demo, and starts the app on a forwarded HTTPS URL (webcam works).
- **Local alternative:** `docker compose up`, then open http://localhost:3000.

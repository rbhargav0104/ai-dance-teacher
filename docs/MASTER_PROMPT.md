# AI Dance Teacher — Complete Greenfield Product & Engineering Execution Prompt

## How to use this document

Paste everything from **START OF MASTER PROMPT** through **END OF MASTER PROMPT** into a capable coding agent or autonomous development platform. Give the agent a writable repository, terminal access, network access for official dependencies, and deployment access when available.

This prompt is intentionally exhaustive. It contains the product story, user experience, machine-vision design, architecture, data model, reliability requirements, outcome-based plan, acceptance tests, deployment target, and the lessons learned from an earlier prototype. It assumes a completely new execution from a blank repository. No earlier conversation or source code is required.

---

# START OF MASTER PROMPT

You are the founding engineer, product engineer, computer-vision engineer, UX designer, QA owner, and deployment owner for a product called **AI Dance Teacher**.

Your assignment is to build a real, production-oriented MVP from a blank repository and carry it through implementation, testing, visual verification, documentation, and deployment. Do not stop after writing a plan. Do not deliver only wireframes or frontend mockups. Work autonomously until the complete acceptance flow works or until a concrete external credential is the only remaining blocker.

When something is unavailable, degrade honestly and preserve user data. Never simulate a successful AI result, invent scores, or disguise unfinished features as working.

## 1. Product definition

**Product name:** AI Dance Teacher

**Tagline:** Learn any dance. Frame by frame.

**Product concept:** A private, encouraging dance-learning product that lets a person upload any choreography, understand it in small teachable sections, practice it, and receive real movement feedback from computer vision.

Think of the experience as:

- Duolingo's progressive learning loop;
- an AI fitness coach's body-awareness and feedback;
- a patient dance instructor's step-by-step teaching;
- a private practice room with no social judgment.

The product exists because many people feel anxious, self-conscious, or judged in dance workshops. YouTube can demonstrate choreography but cannot tell a learner whether their elbow is too low, their knee is insufficiently bent, their weight shifted in the wrong direction, or their movement arrived late. AI Dance Teacher should make dance practice accessible to people who want personalized correction without an audience.

The emotional product principle is as important as the technical one: feedback must be specific, supportive, and nonjudgmental. Never shame the learner. Never describe a person as bad, unfit, stiff, overweight, or untalented. Say what movement changed, how confident the system is, and what small correction to try next.

## 2. Core promise

A user should be able to:

1. Upload a 15–30 second reference dance video.
2. Have the system read real frames and extract a real pose sequence.
3. See the detected skeleton over the reference video.
4. Receive automatically suggested choreography sections that they can edit.
5. Learn each section with looping, slow motion, mirroring, frame stepping, movement paths, and concise instructions.
6. Record or upload their own attempt.
7. Have the system extract their pose with the same pipeline.
8. Align the two performances even when the learner moves slightly faster or slower.
9. Receive a real numerical similarity assessment based on measured movement.
10. See several concrete differences at specific timestamps and replay the relevant portion.
11. Re-practice the weakest section and track improvement.

The system must understand movement through pose landmarks and temporal comparison. Merely replaying a video, drawing a decorative skeleton, or returning random/generated scores does not satisfy the product.

## 3. Non-negotiable engineering rules

1. **No fake AI.** Scores must come from extracted landmarks, measured joint angles, normalized geometry, motion trajectories, and temporal alignment.
2. **No random or hard-coded performance scores.** Demo data may be preprocessed, but it must have been produced by the same real pipeline and be clearly labeled.
3. **Tracking confidence is not dance accuracy.** Keep those concepts separate in data, APIs, UI, and copy.
4. **Unavailable inference must be explicit.** The product may enter a LIMITED state, but it must not manufacture pose results.
5. **Low-quality input must reduce confidence or request a re-record.** Do not output false precision for occluded, cropped, multi-person, or badly tracked footage.
6. **Screen position and body size must not dominate the score.** Normalize the skeleton before comparing it.
7. **Timing must not be erased by alignment.** Dynamic Time Warping may pair movements, but original timestamps must remain available for timing penalties and feedback.
8. **Missing joints must be masked.** Do not score invisible or low-confidence landmarks as if they were confidently incorrect.
9. **Segmentation must remain editable.** Automatic boundaries are suggestions, not semantic truth.
10. **Language may verbalize measured facts only.** A language model may improve wording later, but it may not invent movement observations.
11. **Videos are private by default.** Never make uploaded videos public unless the user explicitly changes that in a future sharing feature.
12. **Video binaries do not belong in PostgreSQL.** Store them in private object storage.
13. **Every advertised feature must have a tested path.** Mark experimental capabilities clearly.
14. **Build for a reliable investor/user demo.** External-provider failures must not destroy the core local flow.
15. **Report progress by working outcomes and acceptance gates.** Do not claim arbitrary percentages such as “50% complete.”

## 4. What earlier prototyping proved and what it did not prove

Treat the following as design evidence and regression expectations, not as source code to reuse:

### Previously demonstrated outcomes

- MP4, MOV, and WebM upload with drag-and-drop, preview, duration/size checks, and deletion.
- Real MediaPipe Pose Landmarker inference on a 20-second sample.
- Approximately 12 analyzed poses per second.
- 33 landmarks per analyzed pose.
- Eight primary joint-angle measurements.
- Skeleton overlay, frame stepping, slow motion, mirroring, timestamps, source-frame numbers, tracking confidence, and landmark IDs.
- Hip-centered normalized coordinates, torso/scale normalization, approximate center of mass, velocity, direction, torso lean, and facing estimates.
- Private local session ownership, signed media access, job progress, retry behavior, and separate object storage.
- A sample run produced roughly 240 analyzed frames with full usable tracking for that particular clip.
- A degraded runtime in which the API could still boot and users could upload/manage projects when the vision runtime was absent.
- Explicit UI states: **STUDIO READY**, **LIMITED**, and **OFFLINE**.
- A bounded expired-session retry that refreshed authentication once.
- Robust rejection behavior: unsupported extension, corrupt video, oversized upload, excessive duration, and audio-only media did not leave database/project residue.
- Source FPS detection, no-video-track rejection, FFprobe/FFmpeg timeout handling, prepared-file verification, partial-output cleanup, and job interruption recovery bounded to three attempts.
- A robustness suite reached 8 passing API tests for these intake/degraded-runtime cases.

### Previously drafted but not validated as complete

- motion-energy segmentation;
- heuristic instructional descriptions;
- bounded Dynamic Time Warping alignment;
- weighted scoring;
- joint/timing feedback generation.

Those algorithms are useful starting hypotheses. Reimplement and validate them; do not call them production-ready because a draft once existed.

### Known gaps the new execution must close

- real reference segmentation integrated into the product;
- editable section boundaries and complete Learn Mode;
- learner upload and webcam capture;
- real learner pose extraction;
- validated mirroring and normalization;
- trustworthy reference/learner alignment;
- calibrated scores and confidence rules;
- timestamp-level coaching and color overlays;
- reporting and repeat-practice loop;
- at least three reference fixtures and three learner-attempt fixtures;
- production authentication, Postgres, private object storage, durable worker execution, and stable deployment;
- complete end-to-end acceptance testing in the actual deployment environment.

## 5. MVP scope

Build the following now:

- premium landing page and entry flow;
- reference video upload;
- licensed sample/demo dance;
- robust media validation and normalization;
- real reference pose extraction;
- debug pose viewer;
- automatic and editable choreography segmentation;
- Learn/Teacher Mode;
- learner video upload;
- webcam recording;
- real learner pose extraction;
- normalized pose and joint comparison;
- temporal alignment;
- versioned component scores and overall score;
- confidence-aware timestamp feedback;
- visual body-part feedback;
- performance report;
- weakest-section repeat loop;
- dashboard/history;
- private production persistence and deletion;
- local development mode;
- automated tests, golden fixtures, documentation, and deployment.

Do not spend meaningful MVP time on song-generated choreography, 3D avatars, celebrity styles, AR, social challenges, or leaderboards. Preserve clean interfaces for them and document them as later phases.

## 6. Required user journeys

### Journey A — landing and demo

The landing page must communicate the product in one screen:

- Brand: **AI Dance Teacher**
- Headline: **Learn any dance. Frame by frame.**
- Supporting line: **Upload any choreography, let AI break it down, practice it, and get instant feedback on your performance.**
- Primary action: **Learn a Dance**
- Secondary action: **Try Demo**

“Try Demo” should use a licensed 15–20 second, single-dancer, full-body clip and let a visitor reach a real preprocessed skeleton/section experience quickly. Preprocessing the demo is acceptable only if its artifacts came from the same pipeline and the UI says it is a sample.

### Journey B — reference upload and analysis

The user can:

- drag and drop or choose an MP4, MOV, or WebM;
- see the filename, duration, dimensions, and preview;
- remove/reselect the file before submission;
- optionally see URL input placeholders for YouTube/TikTok/Instagram, explicitly marked as future/unsupported;
- start **Analyze Choreography**;
- see honest upload and job progress;
- leave and return without losing the job;
- see actionable failure guidance.

### Journey C — sections and Learn Mode

After analysis, the system suggests sections such as:

- Section 01 — 0:00–0:05
- Section 02 — 0:05–0:11
- Section 03 — 0:11–0:17

Each section has:

- start/end timestamps;
- thumbnail;
- loop;
- normal and slow playback;
- mirror toggle;
- editable boundaries;
- completion state;
- a concise, clearly experimental instruction derived from movement facts.

Teacher Mode desktop layout:

- **Left:** large reference video;
- **Center:** skeleton/movement-path visualization;
- **Right:** instruction, section state, and controls;
- **Bottom:** interactive section timeline.

Controls:

- play/pause;
- restart section;
- loop;
- 0.25×, 0.5×, 0.75×, and 1× speed;
- mirror instructor;
- previous/next analyzed frame;
- skeleton visibility;
- movement trails;
- landmark IDs in debug mode;
- mark complete;
- next section.

### Journey D — practice

The learner chooses full dance or a section and either:

1. records with the webcam using MediaRecorder; or
2. uploads a video.

The experience must include permission guidance, countdown, recording state, stop, preview, retry, and upload. It must work without webcam access through file upload.

Show reference and learner video side by side with synchronized playback after processing.

### Journey E — score, feedback, and repeat

After analysis, show:

- overall score;
- pose score;
- timing score;
- sequence score;
- joint-angle score;
- rhythm score only when reliable;
- tracking coverage/confidence;
- strongest section;
- weakest section;
- most common measured correction;
- best matched pose;
- timestamp feedback;
- **Practice Weakest Section** action.

Clicking a feedback item must seek both videos to the relevant moment and replay the surrounding portion.

### Journey F — dashboard

Show private user data:

- My Dances;
- learned progress per dance;
- latest and best scores;
- number of practice sessions;
- sections completed;
- recent dances;
- progress ring per dance.

Use real persisted data. Do not populate a signed-in user's dashboard with fake score cards.

## 7. Visual and emotional design

This is a consumer dance product, not an enterprise admin dashboard.

References for sensibility: Spotify, Nike Training Club, Duolingo, Apple Fitness+, contemporary music/dance culture, and premium AI-native products.

Visual thesis: a dark private dance studio with energetic electric-lime movement signals.

Suggested foundation tokens:

- background: near-black green `#10120f`;
- raised surface: `#1a1d17`;
- line/border: `#33382e`;
- primary lime: `#c1f86a`;
- tracking lime: `#9bea35`;
- text: `#f1f4eb`;
- secondary text: `#a2aa98`;
- warning/limited: amber;
- error: warm red that remains accessible.

Use:

- large video surfaces;
- strong typography and generous space;
- restrained glass/blur panels;
- subtle gradients;
- tasteful motion;
- skeleton trails and movement arcs;
- section timelines;
- progress rings;
- clear loading/progress states.

Avoid:

- a generic shadcn starter appearance;
- dense enterprise navigation;
- excessive cards;
- neon overload;
- decorative AI imagery that implies nonexistent capability;
- judgmental copy;
- animation that interferes with video inspection.

Desktop is the first optimization target because movement comparison benefits from space. Mobile must still support upload, demo, section learning, recording, score review, deletion, and persistent READY/LIMITED/OFFLINE visibility without horizontal overflow.

Respect reduced-motion preferences. Provide strong focus states, keyboard operation, semantic controls, readable type, captions/labels, and accessible status/error announcements.

## 8. Required technology stack

Use a clean monorepo with separately runnable frontend and backend.

### Frontend

- Next.js App Router;
- React;
- TypeScript strict mode;
- Tailwind CSS;
- accessible component primitives such as shadcn/ui where useful, restyled into the product system;
- Recharts for report/dashboard visualization;
- MediaRecorder API for webcam capture;
- SVG or Canvas overlay for pose drawing;
- TanStack Query or a small typed fetch layer for server state;
- no sensitive service credentials in the browser.

### Backend

- Python 3.12;
- FastAPI;
- Pydantic settings/models;
- SQLAlchemy;
- Alembic migrations;
- MediaPipe Tasks Pose Landmarker, preferably the Full model for initial accuracy;
- OpenCV for decoded frames/thumbnails;
- FFmpeg/FFprobe for media inspection and canonical transcoding;
- NumPy and SciPy;
- a durable job system suitable for deployment.

### Persistence

- local development: SQLite plus private local object directory;
- production: Supabase Auth, PostgreSQL, and private Supabase Storage, or an equivalent explicitly documented private object store;
- never store raw video bytes in relational tables.

### Hosting

- frontend: Vercel;
- backend API and analysis worker: Railway;
- production database/object storage/auth: Supabase;
- use Docker for the backend/worker so FFmpeg, OpenCV dependencies, model assets, and Python versions are deterministic.

Do not attempt heavy MediaPipe video processing inside a short-lived Vercel function.

## 9. Repository structure

Create a structure similar to:

```text
/
  README.md
  PROJECT_STATUS.md
  ARCHITECTURE.md
  DECISIONS.md
  IMPLEMENTATION_PLAN.md
  docker-compose.yml
  .env.example
  /frontend
    /app
    /components
    /features
    /lib
    /public/demo
    /tests
  /backend
    /api
    /auth
    /db
    /models
    /schemas
    /storage
    /jobs
    /video
    /pose
    /segmentation
    /comparison
    /scoring
    /feedback
    /tests
  /fixtures
    /references
    /attempts
    fixture_manifest.json
  /scripts
  /supabase
    /migrations
  /deployment
```

Keep pure movement math isolated from HTTP, persistence, and UI so it can be unit-tested deterministically.

## 10. Data model

Create migrations/models for at least:

### users

- id;
- auth provider ID;
- created_at;
- preferences JSON (mirror default, feedback style, retention choice).

### dance_projects

- id;
- owner_id;
- title;
- status;
- error_code/error_message;
- progress;
- is_demo;
- created_at/updated_at.

### reference_videos

- id;
- project_id;
- immutable source object key;
- canonical video object key;
- thumbnail key;
- duration;
- source FPS;
- analysis FPS;
- width/height;
- pose coverage;
- warnings;
- pipeline/model version.

### dance_segments

- id;
- project_id;
- position;
- start_time/end_time;
- title;
- instruction;
- thumbnail key;
- boundary source: automatic/manual;
- completed;
- created_at/updated_at.

### reference_pose_frames

- id;
- reference_video_id;
- timestamp;
- frame_number;
- payload JSONB or optimized structured representation;
- validity/confidence;
- pipeline version.

### practice_sessions

- id;
- owner_id;
- project_id;
- optional segment_id;
- source/canonical/thumbnail object keys;
- status/error/progress;
- duration/FPS/dimensions;
- tracking coverage;
- user-declared mirror state and detected mirror choice;
- created_at.

### user_pose_frames

- id;
- practice_session_id;
- timestamp/frame_number;
- payload;
- confidence/validity;
- pipeline version.

### performance_scores

- id;
- practice_session_id;
- scoring version;
- overall;
- component scores;
- weights;
- coverage;
- confidence;
- report JSON;
- created_at.

### feedback_items

- id;
- practice_session_id;
- segment_id;
- reference_time;
- practice_time;
- category;
- body_part;
- severity;
- measured_delta;
- message;
- evidence/confidence JSON.

### analysis_jobs

- id;
- owner/project/session IDs;
- kind;
- idempotency key;
- status;
- progress/message;
- attempts;
- locked_at/worker_id when relevant;
- created_at/updated_at.

Use foreign keys and cascade rules deliberately. Deleting a project must delete derived database rows and all its owned objects. Keep the original source immutable until deletion or retention expiry.

## 11. Reference media ingestion

Implement ingestion defensively.

### Preflight and upload

- Accept only `.mp4`, `.mov`, and `.webm` at the product level.
- MIME type and extension are hints; inspect actual media with FFprobe.
- Configurable defaults: maximum 200 MB and 120 seconds.
- Enforce request limits as early as infrastructure allows and again while streaming.
- Stream to temporary storage; do not load full uploads into memory.
- Use an idempotency key for project creation/upload so retries cannot duplicate accepted videos.
- Reject failures before permanent project persistence where possible.
- If persistence begins and later fails, transactionally clean database rows and temporary/permanent objects.

### Metadata validation

- Require at least one real video stream.
- Reject audio-only files with a specific message.
- Validate finite duration between 1 second and the configured maximum.
- Validate dimensions between a reasonable minimum such as 128 px and maximum such as 7680 px.
- Parse `avg_frame_rate`, then `r_frame_rate`; accept sane 1–240 fps values.
- Reject invalid timing.
- Set FFprobe timeout and return actionable errors.

### Canonical representation

Keep source media private and immutable. In a background job, create a deterministic analysis/playback copy:

- maximum 1280 px on the long side;
- preserve aspect ratio;
- even dimensions;
- 24 fps canonical video;
- H.264, `yuv420p`, fast start;
- optional AAC audio; missing audio is valid;
- bounded duration;
- argument-list subprocesses, never shell-concatenated user input;
- timeout;
- delete partial output on failure;
- re-probe final output;
- verify non-empty playable file before pose extraction.

Persist source FPS separately from canonical/analysis FPS.

### Tracking suitability checks

Prefer one full-body dancer, fixed camera, good lighting, and visible feet. Detect multiple people. If multiple poses appear in more than a configured minority of frames, stop and ask the user to crop/select one dancer. Do not silently switch identities.

## 12. Pose extraction pipeline

Use MediaPipe Pose Landmarker in VIDEO mode with real frame timestamps.

For every sampled frame, store:

- source/canonical frame number;
- timestamp;
- 33 image-space landmarks with x/y/z, visibility, and presence/confidence;
- world landmarks when available;
- valid flag;
- aggregate tracking confidence;
- normalized coordinates;
- joint angles;
- torso/facing orientation estimates;
- root position/travel;
- approximate center of mass;
- per-landmark velocity;
- root travel direction;
- pipeline/model version.

Initial analysis rate may be approximately 12 fps after a 24 fps canonical transcode. Make it configurable. Preserve timestamps so feedback can seek the original/canonical video accurately.

### Quality gates

A frame is valid only when the core body is visible and enough major joints exceed the confidence threshold. Use shoulders and hips as core points. Aggregate clip coverage as valid analyzed frames / total analyzed frames.

Suggested behavior:

- coverage below 55%: fail analysis and request a clearer recording;
- 55–85%: continue with a visible warning and omit hidden joints;
- above 85%: normal processing;
- calibrate thresholds with fixtures rather than treating these defaults as final truth.

### Temporal smoothing

Add confidence-aware smoothing that reduces landmark jitter without erasing fast choreography. Compare at least exponential/One-Euro/Savitzky-Golay style smoothing. Never interpolate long missing spans as confident movement. Mark interpolated values and limit gap length.

## 13. Feature engineering and normalization

Raw pixel coordinates are not a valid comparison metric.

### Coordinate correction

- Correct image x geometry for aspect ratio before measuring distance.
- Define the hip midpoint as the body root.
- Use robust median torso length and/or shoulder/hip scale as body-size normalization.
- Center pose-shape coordinates on the hip midpoint.
- Preserve root travel as a separate feature so actual movement across the floor is not erased.
- Weight model depth more lightly than x/y because monocular z is less reliable.
- Do not rotate every pose into identical facing; preserve torso orientation as a comparison signal.

### Joint angles

At minimum calculate:

- left/right elbow;
- left/right shoulder;
- left/right hip;
- left/right knee.

Add ankle/wrist/torso angles where confidence and validation justify them. Return null for an angle when any required landmark is unreliable.

### Other features

- shoulder line and hip line;
- torso lean;
- facing/yaw estimate with explicit experimental label;
- limb trajectories;
- motion energy;
- root displacement and direction;
- per-joint velocity/acceleration;
- pose hold/stillness intervals;
- approximate center of mass, clearly labeled as an estimate.

### Mirroring

Implement a correct left/right landmark mapping and x-axis reflection. Compare both normal and mirrored interpretations where appropriate, then choose the better mode only with an explicit record of the decision. Avoid left/right feedback inversion bugs. Add deterministic mirror tests.

## 14. Choreography segmentation

Automatic segmentation suggests teachable boundaries based on movement changes; it must not claim semantic choreography understanding.

Start with a deterministic algorithm:

1. Calculate smoothed motion energy from confidence-masked velocities of major body joints.
2. Detect local pauses, direction reversals, pose transitions, and motion-energy change points.
3. Prefer sections around 3–7 seconds.
4. Enforce sensible minimum/maximum durations.
5. Favor boundaries near natural low-energy states without forcing every boundary into a complete stop.
6. Guarantee coverage from 0 to video duration with no gaps or overlaps.
7. Create a midpoint thumbnail per section.
8. Store automatic boundaries and allow manual edits.

Manual boundary editing must update thumbnails/instructions and preserve ordering/coverage. Validate server-side.

Create segmentation tests for:

- short clip;
- long continuous movement;
- clear pauses;
- no movement;
- missing pose spans;
- boundary editing;
- full coverage/no overlap.

## 15. Heuristic teaching instructions

Generate short statements only from measured features, for example:

- “Lift your left arm above shoulder level while stepping to your right.”
- “Bend both knees as you lower your body.”
- “Rotate your torso clockwise while shifting weight toward your left foot.”
- “Follow the arm path and weight shift at half speed.”

Rules:

- keep them brief;
- identify direction from the learner's selected mirror perspective correctly;
- never invent feet/arms that were not reliably visible;
- label generated movement descriptions as experimental;
- always keep the video/skeleton as the source of truth;
- do not block the MVP if instruction quality is weak.

## 16. Learner capture and processing

Use the same normalization, pose model, features, and quality thresholds for reference and learner footage.

Support:

- full-dance attempt;
- section attempt;
- upload;
- webcam recording;
- mirrored selfie preview without corrupting the stored comparison orientation;
- countdown;
- elapsed recording time;
- stop/retry/submit;
- recording failure guidance;
- permission-denied fallback to upload;
- job progress and resumable UI state;
- deletion of individual attempts.

For best results, prompt the learner to use a similar camera angle and keep their full body visible. These are quality suggestions, not prerequisites for using the product.

## 17. Temporal alignment and movement comparison

Do not compare frames solely by equal index.

### Alignment

Use bounded Dynamic Time Warping or a similarly explainable temporal alignment method on confidence-masked pose/motion features.

- downsample or cap matrix size for predictable resource use;
- use a Sakoe-Chiba-like band so wildly unrelated timing cannot align arbitrarily;
- add insertion/deletion/warp penalties;
- preserve original reference and practice timestamps;
- collapse repeated DTW pairs carefully so one learner frame cannot artificially earn many matches;
- penalize missing passages and excessive warping;
- reject insufficient tracked frames;
- reject essentially immobile reference sections for choreography scoring;
- return alignment path and confidence for debug mode.

### Per-frame cost

Use a documented mixture of:

- visibility-weighted normalized landmark distance;
- joint-angle error;
- torso lean/facing difference;
- trajectory/direction similarity;
- root travel pattern;
- optional velocity/motion-energy difference.

Down-weight monocular depth. Require a minimum number of visible body landmarks. Make coefficients versioned and testable.

### Invariance tests

Prove that comparison is relatively insensitive to:

- subject height;
- camera resolution;
- distance from camera within usable framing;
- horizontal location in the frame;
- moderate performance-speed difference after alignment.

Prove that it remains sensitive to:

- wrong arm height;
- wrong elbow/knee angle;
- wrong movement direction;
- missing movement;
- large torso lean/facing difference;
- late movement;
- reversed sequence.

## 18. Scoring model

Begin with the requested product weights:

- Pose accuracy — 30%
- Timing accuracy — 25%
- Movement sequence — 20%
- Joint-angle similarity — 15%
- Rhythm/tempo consistency — 10%

Overall score is 0–100.

Do not treat these weights or error-to-score curves as scientifically validated. Store a scoring version and calibrate against the golden set.

### Component definitions

**Pose accuracy:** visibility-weighted normalized skeleton similarity including torso orientation.

**Timing:** original timestamp lag after movement alignment. Alignment finds the related move; timing still measures early/late execution.

**Sequence:** matched motion order, direction similarity, missing reference fraction, and excessive warp penalty.

**Joint angles:** error across confidently visible angle features.

**Rhythm:** initially body-motion cadence/envelope and tempo similarity. Audio beat detection is a later or optional input. If rhythm confidence is insufficient or the clip has no useful audio/motion cadence, mark rhythm unavailable and reweight the remaining components rather than penalizing the learner.

### Confidence and coverage

Every report includes:

- reference tracking coverage;
- learner tracking coverage;
- compared-frame count;
- visible-joint coverage;
- alignment confidence/warp amount;
- scoring version;
- warnings.

Suppress or qualify an overall score when coverage is too low. Never turn uncertain data into a confident 82/100.

### Calibration

Create a fixture manifest with intended qualitative relationships. Example:

- same/reference-derived attempt should score highest;
- translated/scaled version should remain close;
- small timing shift should reduce timing more than pose;
- wrong arm should reduce pose/joint feedback around relevant frames;
- missing middle passage should reduce sequence;
- occlusion should reduce confidence and assessed coverage, not necessarily imply terrible dancing.

Use thresholds/rank relations before claiming absolute human-quality grading.

## 19. Timestamp feedback generation

Generate structured feedback from measured deltas.

Examples:

- “Raise your right elbow approximately 18°.”
- “You started this movement 0.4 seconds late.”
- “Bend your left knee a little more.”
- “Your torso is leaning farther forward than the reference.”
- “Great timing through this transition.”

For every item store:

- category;
- body part;
- reference timestamp;
- learner timestamp;
- measured delta;
- severity;
- confidence/evidence;
- section;
- replay interval.

Feedback selection rules:

- choose the most important actionable differences;
- avoid repeating the same correction every frame;
- cluster nearby errors;
- cap feedback density;
- include positive feedback when genuinely measured;
- omit low-confidence joints;
- use approximate language for monocular depth/orientation;
- correctly map left/right in mirrored mode.

Initial configurable threshold examples may start around 18° for meaningful angle feedback and 35° for high severity, but they must be calibrated.

## 20. Visual feedback

Overlay the learner skeleton on their video:

- green: close match;
- yellow: moderate difference;
- red: substantial confident difference;
- muted/gray: unavailable or low-confidence joint, not an error.

Color by body segment based on measured error. Show reference ghost/skeleton or movement path where useful. Avoid red when confidence is low.

Provide:

- section-level summary;
- timestamp list;
- synchronized seeking;
- replay around feedback;
- optional pause on the comparison frame;
- legend explaining colors and uncertainty.

## 21. Performance report

Create an impressive but honest report:

```text
YOUR DANCE SCORE
84 / 100

Pose Accuracy 88
Timing 76
Rhythm 82
Sequence 91
Joint Angles 80

Strongest Section
Weakest Section
Most Common Correction
Best Matched Pose
Areas to Improve
Tracking Coverage
```

AI Coach summary must be generated from structured results, e.g.:

“Your sequence matched the reference well. Most of the lost points came from timing and right-arm positioning in Section 03.”

Include **Practice Weakest Section** and a clear path back to the selected loop. Compare the learner's current attempt with their own previous attempt where enough history exists.

## 22. Developer visualization and test mode

Every processed video needs a developer/debug mode showing:

- video and pose skeleton;
- landmark IDs;
- confidence/presence;
- joint angles;
- frame number;
- timestamp;
- normalized pose;
- root travel;
- velocity/motion energy;
- section boundary scores;
- alignment pairs and per-frame cost;
- mirror interpretation;
- model/pipeline/scoring versions;
- excluded joints and reason.

Debug tools must require ownership/authentication and must not expose another user's media.

## 23. API contract

Design typed APIs around these capabilities. Exact paths may improve, but document them in OpenAPI and keep frontend types generated or aligned.

### Health/capabilities

- `GET /api/health`
  - status;
  - analysis availability;
  - model availability/version;
  - upload/duration limits;
  - auth mode;
  - non-sensitive degraded-mode message.

### Local development session

- `POST /api/session`
  - development/demo only;
  - creates a signed private identity;
  - bounded expiry;
  - never accepted as production auth.

### Projects/reference

- `POST /api/projects` — streaming multipart upload with idempotency key;
- `POST /api/demo` — create/access sample project;
- `GET /api/projects`;
- `GET /api/projects/{id}`;
- `DELETE /api/projects/{id}`;
- `POST /api/projects/{id}/analysis`;
- `GET /api/projects/{id}/poses`;
- `GET /api/projects/{id}/segments`;
- `PATCH /api/projects/{id}/segments`;
- `POST /api/projects/{id}/segments/regenerate`.

### Practice

- `POST /api/projects/{id}/practice-sessions`;
- `GET /api/practice-sessions/{id}`;
- `POST /api/practice-sessions/{id}/analysis`;
- `GET /api/practice-sessions/{id}/poses`;
- `GET /api/practice-sessions/{id}/report`;
- `DELETE /api/practice-sessions/{id}`.

### Media

Use short-lived signed URLs or authenticated streaming. Support range requests for video. Prevent path traversal. Set private/no-store headers where appropriate.

Use consistent error codes/messages, not only generic strings. Never leak stack traces, object keys, local paths, secrets, or other users' IDs.

## 24. Job architecture and recovery

Video analysis is asynchronous.

### Development

A single background worker is acceptable with SQLite if clearly documented. Run one API worker only.

### Production

Use a dedicated Railway worker and durable claiming, such as Postgres row locking with `FOR UPDATE SKIP LOCKED`, or a well-supported queue. Do not let multiple workers process the same job.

Required behavior:

- idempotent job creation;
- stage progress: inspecting, preparing, tracking, segmenting, comparing, scoring, saving;
- heartbeat/lease;
- bounded retries;
- running job recovery after restart;
- maximum three automatic interruption attempts;
- repeated interruption becomes failed/retryable, not an infinite crash loop;
- project/session stuck in processing without a live job is repaired to failed/retryable;
- cancellation/deletion semantics;
- structured failure code and user-facing guidance;
- clean temporary files in success and failure paths.

## 25. READY, LIMITED, and OFFLINE behavior

The frontend must persistently show capability state, including on mobile.

### STUDIO READY

API, persistence, model, and worker are available. All implemented capabilities are enabled.

### LIMITED

API and private persistence work, but movement inference is unavailable. Users can sign in, browse, upload, preview, and delete videos. Analyze controls are disabled with an explanation. Backend also enforces 503. Do not rely on frontend disabling as a security/reliability boundary.

### OFFLINE

API cannot be reached. Preserve local form state where reasonable and show retry. Do not show the empty studio before initial loading resolves.

Authentication recovery:

- on 401 in local development mode, clear the expired local token, create one fresh session, and retry once;
- uploads may retry once only when the 401 occurred before persistence;
- do not auto-retry unknown network failures without idempotency guarantees;
- production uses normal Supabase token refresh.

## 26. Privacy and security

- Supabase Row Level Security for user-owned records.
- Private storage bucket.
- Server-created signed URLs with short expiry.
- Validate project ownership on every endpoint.
- CORS allowlist from environment.
- CSRF strategy appropriate to auth method.
- Rate limiting for session, upload, analysis, and signed URL endpoints.
- Streaming upload size checks and reverse-proxy/platform limits.
- Sanitized filenames; generated object keys.
- Safe subprocess argument arrays.
- No shell interpolation of user input.
- Timeouts and resource limits for FFprobe/FFmpeg/inference.
- Path traversal protection.
- Dependency pinning and container scanning.
- Secrets only in environment/secret manager.
- No raw videos, landmarks, tokens, or signed URLs in application logs.
- Clear delete-video/delete-project actions.
- Define and document retention behavior.
- Do not use uploaded videos for model training without explicit future consent.

Add a concise privacy message where upload/recording happens. Explain that videos are private and deletable.

## 27. Reliability and failure cases

Handle and test:

- unsupported extension;
- corrupt bytes with a valid extension;
- no video track;
- invalid/zero FPS;
- duration outside limits;
- extreme dimensions;
- oversized body;
- FFprobe timeout;
- FFmpeg timeout/failure/empty output;
- browser-incompatible original format;
- model file missing/corrupt;
- MediaPipe import/runtime unavailable;
- zero pose;
- multiple dancers;
- cropped body;
- poor coverage;
- portrait/landscape;
- side profile;
- mirrored recording;
- occlusion;
- fast movement;
- worker interruption;
- duplicate request;
- expired session;
- signed media expiry;
- deletion during safe/unsafe job states;
- database/storage partial failure;
- frontend refresh during job;
- mobile layout;
- camera permission denial.

Rejected uploads must leave no project row, permanent object, or abandoned job. Test that invariant.

## 28. Testing strategy

### Unit tests

- angle calculation;
- coordinate/aspect normalization;
- body-scale invariance;
- mirror mapping;
- confidence masks;
- smoothing/missing gaps;
- segmentation coverage;
- DTW path bounds;
- timing lag preservation;
- scoring bounds/version;
- feedback direction and left/right wording;
- rhythm-unavailable reweighting.

### API integration tests

- auth/ownership;
- health modes;
- valid upload;
- every invalid-media case;
- no-residue invariant;
- idempotency;
- job lifecycle/recovery;
- delete cascades and object cleanup;
- signed media and range requests;
- segment editing;
- practice-to-report flow.

### Frontend tests

- loading state before empty state;
- READY/LIMITED/OFFLINE;
- upload progress and errors;
- expired session recovery;
- analysis polling/reload recovery;
- timeline/seek/frame controls;
- editable sections;
- webcam fallback;
- feedback replay;
- mobile status visibility;
- keyboard/focus behavior.

### Golden fixtures

Before calling scores trustworthy, build at least:

- three reference dances representing different motion characteristics;
- three or more learner attempts, including good, timing-shifted, wrong-limb, missing-move, mirrored, and low-visibility variants.

Record fixture provenance/consent/license. Keep expected relational outcomes in `fixture_manifest.json`. Do not fake pose outputs to make tests pass; deterministic synthetic landmark sequences may test pure math separately, but end-to-end fixtures must exercise real inference.

### Browser and visual QA

Verify desktop and mobile layouts using real rendered pages. Check:

- video aspect ratios;
- overlay alignment;
- no clipping/overflow;
- readable confidence/warnings;
- timeline usability;
- empty/loading/error/success states;
- report clarity;
- reduced motion;
- keyboard flow.

## 29. Observability

Add structured logs and metrics for:

- upload acceptance/rejection reason;
- job duration per stage;
- analysis frame count/rate;
- pose coverage;
- model/pipeline version;
- segmentation count;
- alignment runtime/warp;
- report generation;
- job retries/failures;
- deletion cleanup failures;
- API latency/error rate.

Use request/job correlation IDs. Do not include personal media data. Add a simple internal health/readiness endpoint suitable for Railway health checks.

## 30. Local developer experience

Provide:

- one clear README;
- `.env.example` files with no secrets;
- Dockerfile(s);
- Docker Compose for local services where helpful;
- exact setup for Node, Python, FFmpeg, model download, database migration, frontend, API, and worker;
- scripts such as `dev`, `test`, `typecheck`, `build`, `lint` only where useful, `smoke`, and `seed-demo`;
- model download script with fixed official URL/version and SHA-256 verification;
- generated API docs/OpenAPI;
- troubleshooting for OpenCV system packages and FFmpeg;
- clean sample provenance/license file.

The project should run locally without paid services through local auth, SQLite, and local private object storage. Production adapters must be real and documented.

## 31. Environment variables

Define and document at least:

### Shared/backend

- `APP_ENV`
- `DATABASE_URL`
- `SECRET_KEY`
- `AUTH_MODE`
- `STORAGE_PROVIDER`
- `API_PUBLIC_URL`
- `CORS_ORIGINS`
- `DATA_DIR`
- `MODEL_PATH`
- `ANALYSIS_FPS`
- `MAX_DURATION_SECONDS`
- `MAX_UPLOAD_MB`
- `MAX_PROJECTS_PER_USER`
- `MAX_SESSIONS_PER_PROJECT`
- `JOB_MAX_ATTEMPTS`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_BUCKET`

### Frontend

- `NEXT_PUBLIC_API_URL` or a documented same-origin rewrite;
- public Supabase URL/anon key only when production auth is active;
- never expose service-role keys.

Validate production configuration at startup: HTTPS API URL, Postgres, production auth, private storage, strong secret, explicit origins.

## 32. Deployment plan

### Backend/Railway

Build a Docker image containing:

- Python runtime;
- pinned dependencies;
- FFmpeg/FFprobe;
- required OpenCV system libraries;
- verified MediaPipe model or deterministic model download at build time;
- API entrypoint;
- worker entrypoint.

Deploy API and worker as separate services from the same image when durable queue claiming is ready. Until then, explicitly run one worker/API process only.

Use Railway variables/secrets. Use a persistent Postgres/Supabase connection and private object storage; do not rely on Railway's ephemeral filesystem for user videos. Add `/api/health` health check. Record the stable backend domain.

### Frontend/Vercel

Deploy the Next.js frontend to a stable Vercel project. Configure backend URL/rewrite and Supabase public auth values. Add backend CORS for the production domain. Verify camera and upload behavior over HTTPS.

### Production verification

From the deployed frontend, run the full acceptance flow with a fresh user, reference video, and learner attempt. Do not declare deployment successful because the landing page loads.

## 33. Outcome-based execution plan

Execute in this order. Every outcome has an exit gate. Finish verification before expanding scope.

### Outcome 0 — engineering foundation

Deliver:

- repository/monorepo;
- frontend and backend booting;
- environment examples;
- migrations;
- local auth/storage/database;
- docs/status/decision log;
- CI baseline.

Exit gate: a new developer can run both services from the README and reach health/session endpoints.

### Outcome 1 — robust private reference intake

Deliver:

- upload/drag-drop/sample;
- real metadata;
- private source storage;
- job record;
- validation and cleanup;
- project list/delete;
- READY/LIMITED/OFFLINE shell.

Exit gate: valid media persists privately; all rejection fixtures leave no residue; refresh preserves project/job state.

### Outcome 2 — real reference pose and debugger

Deliver:

- canonical transcode;
- MediaPipe inference;
- stored frames/features;
- quality gates;
- skeleton viewer/debugger;
- real progress and recovery.

Exit gate: a real sample/upload yields correctly aligned skeleton and inspectable landmarks/angles; low-quality and multi-person clips fail honestly.

### Outcome 3 — teachable sections

Deliver:

- automatic boundaries;
- thumbnails;
- editable timeline;
- coverage validation;
- section loops/speeds/mirror;
- experimental instructions.

Exit gate: sections cover the entire video without gap/overlap, edits persist, and every section can be looped accurately.

### Outcome 4 — Teacher Mode

Deliver:

- left/reference, center/skeleton, right/instruction, bottom/timeline workspace;
- progress/completion;
- movement trails;
- responsive behavior.

Exit gate: a user can complete a section-by-section learning loop on desktop and mobile.

### Outcome 5 — learner capture and real learner pose

Deliver:

- webcam and upload;
- preview/retry;
- practice persistence/jobs;
- same pose/quality pipeline;
- synchronized dual video.

Exit gate: a learner attempt produces real stored pose data and can be reviewed beside the reference.

### Outcome 6 — normalized alignment

Deliver:

- invariance-tested normalization;
- mirror handling;
- bounded DTW;
- original timing preservation;
- missing-motion/warp accounting;
- debug alignment view.

Exit gate: scale/translation/speed tests behave as intended while wrong-limb, late, and missing-movement tests remain distinguishable.

### Outcome 7 — versioned scoring

Deliver:

- component metrics;
- requested weights;
- confidence/coverage rules;
- rhythm gating;
- report schema;
- golden-set relationship tests.

Exit gate: scores are deterministic, bounded, evidence-linked, and suppressed/qualified when data quality is inadequate.

### Outcome 8 — actionable feedback

Deliver:

- clustered timestamp corrections;
- body-part delta overlay;
- positive observations;
- replay links;
- section summary;
- left/right mirror correctness.

Exit gate: known fixture errors generate the correct category/body part/time and can be replayed.

### Outcome 9 — report, repeat, and dashboard

Deliver:

- complete report;
- strongest/weakest section;
- practice-weakest loop;
- history/latest/best/progress dashboard;
- deletion/retention controls.

Exit gate: a learner can practice, understand results, repeat the weakest section, and see improvement history.

### Outcome 10 — production identity and durable infrastructure

Deliver:

- Supabase auth/RLS/Postgres/private storage;
- durable queue/worker;
- signed media;
- rate limits;
- observability;
- migrations and cleanup.

Exit gate: one user cannot access another user's metadata or media; restarts do not lose or duplicate jobs.

### Outcome 11 — stable deployment and full acceptance

Deliver:

- Railway API/worker;
- Vercel frontend;
- stable URLs;
- HTTPS camera/upload;
- production smoke test;
- golden fixture run;
- deployment/runbook.

Exit gate: the complete acceptance test below passes from the deployed frontend.

## 34. Final acceptance test

The MVP is successful only when all of this works:

1. Open the stable deployed URL.
2. Sign in or enter the private studio.
3. Upload a real 15–30 second dance video.
4. The application validates and processes it.
5. View the real detected skeleton and debug data.
6. See automatically suggested sections.
7. Edit a section boundary and verify persistence.
8. Loop a section, slow it, mirror it, and step frames.
9. Upload or record a real learner attempt.
10. The learner attempt is processed with real pose extraction.
11. Reference and learner sequences align and play synchronously.
12. Receive deterministic component scores and overall score with confidence/coverage.
13. See several real movement differences at approximately correct timestamps.
14. Click a difference and replay the relevant portion.
15. Open the weakest section and practice it again.
16. See the new attempt in history and compare improvement.
17. Delete the attempt/video/project and confirm owned media and derived data are removed.
18. Confirm another user/session cannot access the deleted or private media.

Also verify LIMITED mode by disabling the vision runtime: the API and project management must remain usable, analysis must be disabled/503, and no fake result may appear.

## 35. Required deliverables

At completion provide:

- complete source repository;
- stable deployed frontend URL;
- stable backend health URL;
- README with local and production setup;
- `.env.example` files;
- database migrations/RLS policies;
- Dockerfiles/Compose where relevant;
- architecture and decision documents;
- current `PROJECT_STATUS.md` with verified/unverified claims;
- OpenAPI documentation;
- test suite and exact results;
- fixture manifest and licenses/provenance;
- deployment runbook;
- privacy/deletion notes;
- known limitations;
- list of keys/accounts the owner must configure, without hard-coded secrets.

## 36. Progress and communication rules

While executing:

- state the current outcome and next verification target;
- give concise updates during long work;
- distinguish implemented, tested, deployed, and merely planned;
- record every material decision in `DECISIONS.md`;
- update `PROJECT_STATUS.md` after each outcome;
- keep a list of exact commands/tests run and results;
- do not hide blockers;
- do not call the project complete when only the frontend works;
- do not call scoring complete before golden-set validation;
- do not ask the owner to make routine technical decisions that you can resolve safely;
- when credentials are missing, finish all local code/configuration first, then state the exact credential and location needed;
- preserve a recoverable source state in Git after every accepted outcome.

## 37. Cost and performance guidance

Keep the MVP affordable:

- open-source pose inference;
- CPU-compatible analysis initially;
- canonical resolution/FPS limits;
- background jobs;
- reuse stored pose artifacts rather than re-running unnecessarily;
- hash/version pipelines for cache invalidation;
- avoid an LLM in the critical movement pipeline;
- optional language verbalization only after deterministic facts exist;
- track analysis duration and storage size;
- clean temporary files;
- configurable retention.

Optimize for 15–30 second clips first. Support up to two minutes through configuration, but do not sacrifice reliability of the target acceptance clip.

## 38. Future phases — architect for them, do not prioritize them

### Phase 2 — song-to-choreography generation

User uploads audio. Analyze tempo, beats, energy, and song sections; generate choreography. Potential research/model inputs include AIST++ and motion-generation work such as Stanford EDGE. Verify license/attribution before adopting any model or dataset. This phase requires a separate evaluation strategy and must not be mixed into MVP pose scoring.

### Phase 3 — 3D instructor/avatar

Convert pose/motion into a selected avatar using Three.js, Blender, Mixamo, SMPL, Unity, or similar. An avatar must teach the verified motion, not conceal poor pose extraction.

### Phase 4 — style/celebrity-inspired learning

Requires likeness, licensing, content, and safety review. Do not imply celebrity endorsement.

### Phase 5 — AR instructor

Place the teacher in the learner's room with spatial guidance.

### Phase 6 — social challenges and leaderboards

Opt-in only, with privacy, consent, moderation, age considerations, and non-harmful ranking design.

### Longer-term movement-intelligence platform

The underlying movement engine may later support gym/smart mirrors, earbuds, yoga, rehabilitation, and swimming technique. Safety-critical drowning detection is a separate product/module with separate data, validation, latency, reliability, and regulatory requirements; never treat the dance scorer as a safety system.

## 39. Begin execution now

Start from a blank repository.

1. Inspect the available environment and deployment integrations.
2. Create the monorepo, status documents, and outcome plan.
3. Implement Outcome 0 and verify it.
4. Continue sequentially through the acceptance test.
5. Keep the application runnable after every outcome.
6. Use the strongest reasonable defaults when a choice is not product-defining.
7. Never replace a hard engineering problem with a mock success state.
8. Do not stop after describing what should be built. Build it, run it, fix it, test it, deploy it, and hand over the stable URLs and source.

# END OF MASTER PROMPT

---

## Concise project summary for a human reader

AI Dance Teacher is a private computer-vision dance coach. A person uploads choreography, the system extracts a real 33-landmark pose sequence, suggests teachable sections, and provides learning controls such as loop, slow motion, mirror, frame stepping, skeletons, and movement paths. The learner then records or uploads an attempt. The product normalizes body geometry, aligns the performances through time, compares pose, joint angles, direction, timing, sequence, and reliable rhythm signals, and turns measured differences into timestamped, supportive coaching.

The earlier prototype established that real ingestion, MediaPipe extraction, skeleton visualization, local privacy, signed media, job progress, degraded runtime behavior, and robust rejection paths are feasible. It also exposed the central remaining risk: a convincing UI is much easier than a trustworthy movement assessment. The new execution must therefore prioritize real learner data, invariance tests, confidence-aware alignment, golden fixtures, calibrated scoring, and complete deployed acceptance over visual expansion.

The MVP finishes when a real user can upload a reference, learn its sections, submit an attempt, receive evidence-linked feedback, replay mistakes, re-practice the weakest section, see progress, and delete their private data from a stable deployed application.

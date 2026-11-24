# Asset sourcing (owner supplies nothing)

The owner's only role is testing. Every asset must be obtained by the build sessions.
The build sandbox can reach GitHub (incl. `raw.githubusercontent.com`, `media.githubusercontent.com`, `gh api`)
and package registries (PyPI, npm). Google Cloud Storage, Hugging Face, Wikimedia and stock sites are blocked.

## Pose model — verified 2026-11-24
`pose_landmarker_full.task`, 9,398,198 bytes,
SHA-256 `4eaa5eb7a98365221087693fcc286334cf0858e2eb6e15b506aa4a7ecdcec4ad`
(identical in two independent repos; loads and runs with `mediapipe` 1.2.3 Tasks API, VIDEO mode).

`scripts/download_model.sh` must try, in order, and verify the SHA-256 after each:
1. Official: `https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task`
2. Mirror: `https://media.githubusercontent.com/media/torinmb/mediapipe-touchdesigner/HEAD/src/mediapipe/models/pose_landmark_detection/pose_landmarker_full.task`
3. Mirror: `https://media.githubusercontent.com/media/empress-of-development/preciosAI/HEAD/example/assets/models/pose_landmarker_full.task`

Do not commit the model to the repo; download at setup / Docker build time.

## Reference dance videos
Find real, openly licensed clips of one full-body dancer on a fixed camera, committed in public GitHub repos.
Search with `gh api "search/code?q=..."` (e.g. `filename:dance extension:mp4`, `mixkit dance`, `pexels dance`).
Acceptable licenses: Mixkit Free License, Pexels License, Pixabay Content License, CC0, CC-BY (with attribution).
Lead found 2026-11-24: `alexandremendoncaalvaro/CorridorKey-Runtime` → `assets/video_samples/mixkit-girl-dancing-with-her-earphones-on-a-green-background-28306-4k.mp4` (Mixkit).

### Findings 2026-11-24 (build session 1)
- In scheduled runs `gh api repos/<other>/...` is **denied** (scope is this repo only), but `gh api search/code` works and
  direct downloads from `https://media.githubusercontent.com/media/<owner>/<repo>/HEAD/<url-encoded path>` work (LFS),
  falling back to `raw.githubusercontent.com`. Record HEAD as the ref and the download date; the blob commit SHA can't be
  looked up via the API from here, so store the file's own SHA-256 in the manifest instead.
- Verified downloadable Mixkit clips (Mixkit Free License, single dancer, green screen, fixed camera):
  1. `alexandremendoncaalvaro/CorridorKey-Runtime` → `assets/video_samples/mixkit-girl-dancing-with-her-earphones-on-a-green-background-28306-4k.mp4`
     — 3840×2160, 24 fps, 14.0 s, no audio, 66 MB. Framed **thighs-up** (feet not visible): arm/torso-heavy, gentle sway.
  2. `hasanosman2020/20JSProjects_02Mastery` → `video_player/videoclips/mixkit-boy-dancing-funnily-on-a-green-chroma-background-28289-medium.mp4`
     — 1280×720, 59.94 fps, 16.0 s. Framed **knees-up**: playful arm + hip grooves, steps side to side.
  Neither shows feet, so both will carry a "cropped body" warning — honest, and useful as the cropped-body case.
- Rejected: `reallyigor/easy_dwpose assets/dance.mp4` (2 s, licence unknown), `gatewai-dev/framefields-smoke assets/dancer.mp4`
  (6 s, licence unknown), OpenNeuroDatasets Kinetics-derived clips (YouTube-sourced, not openly licensed).
- Still needed: one **full-body** clip (feet visible). Next searches: `filename:mixkit` with `.webm`/`.mov`, Mixkit IDs near
  28289–28306 (same green-screen shoot series, e.g. `mixkit-*-dancing-*-on-a-green-*`), `filename:full-body`, `filename:pexels-`
  with numeric IDs + `dance` in repo README. If none is found by Outcome 2, use the two Mixkit clips plus a distinct
  time-window of each as separate references, and document that limitation in PROJECT_STATUS.

Aim for 3 references with different motion (e.g. arm-heavy, footwork/travel, pauses). Trim/transcode to 15–30 s, ≤720p, before committing to `fixtures/references/`.
Record source repo, path, commit SHA, original source and license in `fixtures/fixture_manifest.json` and `fixtures/LICENSES.md`.
Avoid clips with copyrighted music where possible; strip audio from fixtures if licensing is unclear.

## Learner-attempt fixtures
Real videos, generated from real footage with FFmpeg (never fabricated landmarks):
- `good`: a different take or same clip re-encoded at another resolution.
- `scaled_translated`: same performance, smaller and shifted in frame (pad/scale).
- `late_0_4s`: same performance delayed by ~0.4 s.
- `speed_0_9x` / `speed_1_1x`: tempo variants.
- `mirrored`: horizontal flip.
- `missing_middle`: middle passage cut and replaced with a hold.
- `occluded`: a solid box covering one limb region for part of the clip.
- `wrong_dance`: a different reference clip compared against this reference (stands in for wrong movements).
Each variant's expected relationship goes in `fixture_manifest.json` (spec section 18 calibration).

## Webcam path without a human
Playwright Chromium flags `--use-fake-ui-for-media-stream --use-fake-device-for-media-stream --use-file-for-fake-video-capture=<fixture>.y4m`
let E2E tests exercise the real MediaRecorder flow with a fixture video as the camera.

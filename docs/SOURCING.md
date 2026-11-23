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

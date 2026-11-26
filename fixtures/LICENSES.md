# Fixture video licences and attribution

All fixture videos are real footage, trimmed/transcoded with FFmpeg (audio stripped). Exact commands and
SHA-256 hashes are in `fixture_manifest.json`.

## references/mixkit_girl_earphones_28306.mp4
- Original: Mixkit clip 28306, "Girl dancing with her earphones on a green background" (mixkit.co).
- Licence: Mixkit Free License — https://mixkit.co/license/ (free for commercial and personal use, no attribution
  required; the clip may not be redistributed or sold as a standalone stock item). Credit given anyway: video by Mixkit.
- Obtained from: GitHub `alexandremendoncaalvaro/CorridorKey-Runtime`,
  `assets/video_samples/mixkit-girl-dancing-with-her-earphones-on-a-green-background-28306-4k.mp4` (HEAD, downloaded 2026-11-25).
- Changes: downscaled 3840x2160 -> 1280x720, re-encoded H.264 CRF 26, no audio track.

## references/mixkit_boy_funny_28289.mp4
- Original: Mixkit clip 28289, "Boy dancing funnily on a green chroma background" (mixkit.co).
- Licence: Mixkit Free License — https://mixkit.co/license/. Credit: video by Mixkit.
- Obtained from: GitHub `hasanosman2020/20JSProjects_02Mastery`,
  `video_player/videoclips/mixkit-boy-dancing-funnily-on-a-green-chroma-background-28289-medium.mp4` (HEAD, downloaded 2026-11-25).
- Changes: 59.94 fps -> 30 fps, re-encoded H.264 CRF 26, audio removed.

These clips are bundled only as test fixtures embedded in this application's test suite, not offered for
download as stock footage.

## attempts/*.mp4 (learner-attempt fixtures)
- Derived from the two Mixkit clips above (same Mixkit Free License, credit: video by Mixkit) with FFmpeg by
  `scripts/make_attempt_fixtures.py`: 640x360, 24 fps, H.264 CRF 28, no audio. Variants: re-encode (`girl_good`),
  60% size + shifted, +0.4 s late, 0.9x / 1.1x speed, mirrored, middle replaced by a 4 s hold, view fully blocked 5–8 s,
  and the other dance as a wrong-dance attempt. Exact commands, SHA-256 and the expected relationship of each
  variant are in `fixture_manifest.json` → `attempts`. No landmarks are fabricated: each is a real video.

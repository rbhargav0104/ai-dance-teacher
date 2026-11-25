# Spec amendments (owner decisions that change docs/MASTER_PROMPT.md)

Read this together with the master spec. An amendment here overrides the referenced spec section.
Section 3 (non-negotiable engineering rules) still always wins.

## A1 — 3D AI avatar teacher with voice (owner, 2026-11-25)

**Owner's words:** "after I upload a sample video an ai avatar is supposed to come teach me".
Asked to choose, the owner picked **a full 3D avatar** (over a 2D coach) and **spoken cues**.

**Overrides:** spec §5 ("do not spend meaningful MVP time on … 3D avatars") and moves §36 Phase 3
"3D instructor/avatar" into the MVP, as the centrepiece of **Outcome 4 — Teacher Mode**.

### What the learner experiences
After a reference is analysed, the dance opens in Teacher Mode. A 3D avatar on a studio stage performs the
choreography **section by section**. It does exactly what the dancer in the video did, driven by the tracked motion.
The learner can:
- play / pause / restart the section, loop, and choose 0.25×, 0.5×, 0.75× or 1× speed;
- mirror the instructor (default ON, like a dance-class mirror);
- orbit or switch the camera (front, side, 3/4) to see the move in depth;
- see the original video small beside the avatar (picture-in-picture), in sync;
- hear the coach. The browser's Web Speech API reads short cues and counts ("5, 6, 7, 8"), e.g. "Right arm sweeps up
  over your head" and "Bend both elbows to about 90°". Cues can be muted, captions are always shown, and a reduced-motion
  setting is honoured;
- mark the section complete and go to the next one.

### Honesty rules (spec §3 applied to the avatar)
- The avatar is driven **only** by measured landmarks for this video: MediaPipe world landmarks (metres, hip-centred),
  smoothed with the existing One-Euro filter. It never runs invented, canned or "AI-generated" dance motion.
- **Untracked body parts are never animated as if they were known.** Example: the feet in both current samples.
  Those limbs are held in a neutral rest pose, rendered translucent/ghosted with a "not tracked in this video" label.
  Hips/legs are not inferred from the upper body. Short gaps (≤ 2 analysed frames) may be bridged, and are shown faint.
- If a section's coverage is below the analysis gate, the avatar shows the gap ("tracking lost here") instead of
  freezing or guessing. The reference video stays available.
- Spoken and written cues verbalise measured facts only (angles, directions, travel, holds from features.py). They
  are labelled "experimental" (spec §15). No language-model wording yet.
- Calling it an "AI avatar" is fine. Copy must not claim it understands music, style or emotion.

### Technical direction (sessions may refine; record changes in DECISIONS.md)
- `three` + `@react-three/fiber` + `@react-three/drei` in the frontend (npm: reachable).
- **Avatar v1: an original, procedural stylised mannequin** built from primitives (capsule limbs, rounded torso,
  simple head, lime accent joints). Each bone is aimed along its measured segment direction, and segment lengths are
  fixed from robust per-clip medians so limbs don't stretch. There are no licensing questions and it can't look
  "puppeted" from wrong retargeting.
- **Avatar v2 (optional, only after core outcomes are green):** a skinned glTF humanoid with a CC0 licence
  (e.g. Quaternius-style CC0 characters mirrored on GitHub), retargeted from the same bone directions. Full provenance
  goes in fixtures/LICENSES.md. A Mixamo/Ready Player Me account is not available (owner supplies no accounts).
- The backend exposes the stored `world` landmarks and reliability per frame (already persisted). Retargeting maths
  (segment directions, fixed bone lengths, mirror mapping, ghost-pose for unreliable limbs) is a pure, unit-tested
  module, in TypeScript (`frontend/lib/avatar/`) and/or Python. Tests must cover it.
- Section timing comes from Outcome 3 segments. Count-in uses the section's measured tempo when Outcome 7 rhythm is
  reliable, otherwise an even 8-count over the section.
- Performance budget: 60 fps on a mid-range laptop, ≥ 30 fps on a recent phone. Fall back to the 2D skeleton view if
  WebGL is unavailable (state it, don't fail silently).
- The center "skeleton/movement path" panel of §6 Teacher Mode becomes the avatar stage. The skeleton remains a toggle.

### Exit gate for Outcome 4 (replaces the spec's)
On desktop and mobile, a user can open an analysed sample and learn it section by section from the 3D avatar:
play/loop/slow/mirror, spoken + captioned cues, mark complete, next section. Untracked limbs are visibly marked,
not animated. Verified by:
- unit tests of the retargeting maths;
- a Playwright run on the real fixtures that screenshots the avatar at known timestamps;
- a check that the avatar's arm direction matches the measured landmarks at those timestamps.

### Schedule impact
Outcome 4 grows. Revised pacing is in IMPLEMENTATION_PLAN.md. If time runs short, the order stays: real scoring
(Outcomes 6–7) and honest feedback (Outcome 8) are not skipped. Instead, avatar polish (v2 skinned model, camera
presets) is cut first, and that slip is recorded in PROJECT_STATUS.md.

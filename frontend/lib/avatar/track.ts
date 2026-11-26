/**
 * Avatar motion track: measured world landmarks → smoothed, gap-aware, pre-posed frames the
 * 3D stage samples at the video's current time. Pure and deterministic (no three.js here).
 *
 * Steps, per spec amendment A1:
 *  1. One-Euro smoothing of every world-landmark coordinate (same parameters as the backend
 *     pipeline). Unreliable samples restart the filter; nothing is smoothed through a gap.
 *  2. Gaps of ≤ 2 analysed frames between reliable samples are bridged by linear interpolation
 *     and flagged `bridged` (drawn faint). Longer gaps stay unknown (ghosted rest pose).
 *  3. Bone lengths fixed from per-clip medians (`buildRig`), each frame posed (`poseFrame`).
 *  4. Sampling between analysed frames interpolates bone directions; when the nearest analysed
 *     frame is invalid (or too far away) the stage reports "tracking lost" instead of guessing.
 */

import type { PosesResponse } from "../types";
import {
  type AvatarPose,
  BONES,
  type BoneName,
  type BonePose,
  type BoneState,
  type ClipRig,
  type Vec3,
  type WorldFrame,
  buildRig,
  mirrorFrame,
  poseFrame,
  unit,
} from "./retarget";

export const ONE_EURO = { minCutoff: 1.7, beta: 0.3, dCutoff: 1.0 } as const;
export const MAX_BRIDGE_FRAMES = 2;

function alpha(cutoff: number, dt: number): number {
  const tau = 1 / (2 * Math.PI * cutoff);
  return 1 / (1 + tau / dt);
}

/**
 * One-Euro filter over a 1-D series. `reliable[i] === false` → NaN output and a filter restart.
 * Mirrors backend/app/pose/smoothing.py `one_euro`.
 */
export function oneEuro(
  values: number[],
  times: number[],
  reliable: boolean[],
  { minCutoff = ONE_EURO.minCutoff, beta = ONE_EURO.beta, dCutoff = ONE_EURO.dCutoff } = {},
): number[] {
  const out = new Array<number>(values.length).fill(NaN);
  let prevX: number | null = null;
  let prevDx = 0;
  let prevT = 0;
  for (let i = 0; i < values.length; i++) {
    const x = values[i];
    if (!reliable[i] || !Number.isFinite(x)) {
      prevX = null;
      continue;
    }
    if (prevX === null) {
      prevX = x;
      prevDx = 0;
      prevT = times[i];
      out[i] = x;
      continue;
    }
    const dt = Math.max(1e-6, times[i] - prevT);
    const dx: number = (x - prevX) / dt;
    const aD = alpha(dCutoff, dt);
    const dxHat: number = aD * dx + (1 - aD) * prevDx;
    const cutoff = minCutoff + beta * Math.abs(dxHat);
    const a = alpha(cutoff, dt);
    const xHat: number = a * x + (1 - a) * prevX;
    out[i] = xHat;
    prevX = xHat;
    prevDx = dxHat;
    prevT = times[i];
  }
  return out;
}

/**
 * Fill runs of missing samples no longer than `maxGap` that sit between two known samples.
 * Returns the filled values and which indices were bridged. Edges are never extrapolated.
 */
export function bridgeGaps(values: number[], known: boolean[], maxGap = MAX_BRIDGE_FRAMES): { values: number[]; bridged: boolean[] } {
  const v = [...values];
  const bridged = new Array<boolean>(values.length).fill(false);
  let i = 0;
  while (i < v.length) {
    if (known[i]) {
      i++;
      continue;
    }
    const s = i;
    while (i < v.length && !known[i]) i++;
    const e = i; // first known after the gap, or length
    const len = e - s;
    if (s > 0 && e < v.length && len <= maxGap) {
      const a = v[s - 1];
      const b = v[e];
      for (let k = s; k < e; k++) {
        const u = (k - s + 1) / (len + 1);
        v[k] = a + (b - a) * u;
        bridged[k] = true;
      }
    }
  }
  return { values: v, bridged };
}

/** Convert the poses API payload into world frames, smoothing and bridging each landmark track. */
export function smoothWorldFrames(poses: Pick<PosesResponse, "frames">): WorldFrame[] {
  const frames = poses.frames;
  const n = frames.length;
  const times = frames.map((f) => f.t);
  const J = 33;
  const world: (Vec3 | null)[][] = frames.map(() => new Array<Vec3 | null>(J).fill(null));
  const reliableOut: boolean[][] = frames.map(() => new Array<boolean>(J).fill(false));
  const bridgedOut: boolean[][] = frames.map(() => new Array<boolean>(J).fill(false));

  for (let j = 0; j < J; j++) {
    const rel = frames.map((f) => Boolean(f.valid && f.data.world && f.data.world[j] && f.data.reliable[j]));
    const smoothed: number[][] = [0, 1, 2].map((c) =>
      oneEuro(
        frames.map((f, i) => (rel[i] ? f.data.world![j][c] : NaN)),
        times,
        rel,
      ),
    );
    // Bridge only inside valid frames: an invalid frame (no usable pose) is never filled.
    const filled = smoothed.map((series) => bridgeGaps(series, rel));
    for (let i = 0; i < n; i++) {
      if (rel[i]) {
        world[i][j] = [smoothed[0][i], smoothed[1][i], smoothed[2][i]];
        reliableOut[i][j] = true;
      } else if (frames[i].valid && filled[0].bridged[i]) {
        world[i][j] = [filled[0].values[i], filled[1].values[i], filled[2].values[i]];
        bridgedOut[i][j] = true;
      }
    }
  }

  return frames.map((f, i) => {
    const has = world[i].some((p) => p !== null);
    return {
      t: f.t,
      valid: f.valid && has,
      world: has ? world[i].map((p) => p ?? ([NaN, NaN, NaN] as Vec3)) : null,
      reliable: reliableOut[i],
      bridged: bridgedOut[i],
    };
  });
}

export interface AvatarTrack {
  mirrored: boolean;
  rig: ClipRig;
  poses: AvatarPose[];
  times: number[];
  /** Half the analysed frame step: beyond this from any analysed frame, nothing is known. */
  step: number;
  /** Neutral rest pose (every bone untracked), shown when the moment wasn't measured. */
  rest: AvatarPose;
  /** Lowest point a measured or rest leg reaches below the hips (to stand the avatar on the floor). */
  legLength: number;
}

export function buildTrack(poses: Pick<PosesResponse, "frames" | "analysis_fps">, mirrored: boolean): AvatarTrack {
  const base = smoothWorldFrames(poses);
  const frames = mirrored ? base.map(mirrorFrame) : base;
  const rig = buildRig(frames);
  const fps = poses.analysis_fps ?? 12;
  const legLength = Math.max(rig.lengths.thighL + rig.lengths.shinL, rig.lengths.thighR + rig.lengths.shinR);
  return {
    mirrored,
    rig,
    poses: frames.map((f) => poseFrame(f, rig)),
    times: frames.map((f) => f.t),
    step: 1 / Math.max(1, fps),
    rest: poseFrame({ t: 0, valid: false, world: null, reliable: [] }, rig),
    legLength,
  };
}

export type SampleStatus = "tracked" | "lost" | "outside";

export interface AvatarSample {
  t: number;
  status: SampleStatus;
  pose: AvatarPose | null;
}

function lowerIndex(times: number[], t: number): number {
  let lo = 0;
  let hi = times.length - 1;
  if (hi < 0 || t < times[0]) return -1;
  while (lo < hi) {
    const m = (lo + hi + 1) >> 1;
    if (times[m] <= t) lo = m;
    else hi = m - 1;
  }
  return lo;
}

const lerp3 = (a: Vec3, b: Vec3, u: number): Vec3 => [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u];

function worse(a: BoneState, b: BoneState): BoneState {
  const rank = { measured: 0, bridged: 1, untracked: 2 } as const;
  return rank[a] >= rank[b] ? a : b;
}

/** Blend two posed frames: directions are normalised-lerped; untracked wins over measured. */
export function blendPoses(a: AvatarPose, b: AvatarPose, u: number, rig: ClipRig): AvatarPose {
  if (u <= 0) return a;
  if (u >= 1) return b;
  const bones = {} as Record<BoneName, BonePose>;
  // Re-chain positions from the blended directions so limbs keep their fixed lengths.
  const startOf = (name: BoneName): Vec3 => {
    const sa = a.bones[name].start;
    const sb = b.bones[name].start;
    return lerp3(sa, sb, u);
  };
  for (const def of BONES) {
    const ba = a.bones[def.name];
    const bb = b.bones[def.name];
    const state = worse(ba.state, bb.state);
    // If either side is unknown, hold the rest direction rather than blending toward a guess.
    const dir: Vec3 = state === "untracked" ? def.rest : (unit(lerp3(ba.dir, bb.dir, u)) ?? ba.dir);
    bones[def.name] = { name: def.name, start: [0, 0, 0], end: [0, 0, 0], dir, measured: state !== "untracked", state };
  }
  const chain = (name: BoneName, start: Vec3) => {
    const bone = bones[name];
    bone.start = start;
    bone.end = [start[0] + bone.dir[0] * rig.lengths[name], start[1] + bone.dir[1] * rig.lengths[name], start[2] + bone.dir[2] * rig.lengths[name]];
    return bone.end;
  };
  const chest = chain("spine", [0, 0, 0]);
  chain("neck", chest);
  // Shoulder/hip anchors follow the blended chest/pelvis offsets of the two frames.
  const offset = (name: BoneName, parentA: Vec3, parentB: Vec3, parent: Vec3): Vec3 => {
    const oa: Vec3 = [a.bones[name].start[0] - parentA[0], a.bones[name].start[1] - parentA[1], a.bones[name].start[2] - parentA[2]];
    const ob: Vec3 = [b.bones[name].start[0] - parentB[0], b.bones[name].start[1] - parentB[1], b.bones[name].start[2] - parentB[2]];
    const o = lerp3(oa, ob, u);
    return [parent[0] + o[0], parent[1] + o[1], parent[2] + o[2]];
  };
  const chestA = a.bones.spine.end;
  const chestB = b.bones.spine.end;
  chain("forearmL", chain("upperArmL", offset("upperArmL", chestA, chestB, chest)));
  chain("forearmR", chain("upperArmR", offset("upperArmR", chestA, chestB, chest)));
  chain("shinL", chain("thighL", startOf("thighL")));
  chain("shinR", chain("thighR", startOf("thighR")));
  const axis = a.shoulderAxis && b.shoulderAxis ? unit(lerp3(a.shoulderAxis, b.shoulderAxis, u)) : (a.shoulderAxis ?? b.shoulderAxis);
  return { t: a.t + (b.t - a.t) * u, valid: a.valid && b.valid, bones, shoulderAxis: axis };
}

/**
 * Avatar pose at media time `t`. Between two valid analysed frames → interpolated. Next to an
 * invalid frame (or past a missing stretch) → "lost": the stage shows the gap, never a guess.
 */
export function sampleTrack(track: AvatarTrack, t: number): AvatarSample {
  const { times, poses, step } = track;
  if (times.length === 0) return { t, status: "outside", pose: null };
  if (t < times[0] - step / 2 || t > times[times.length - 1] + step / 2) return { t, status: "outside", pose: null };
  const i = lowerIndex(times, t);
  if (i < 0) return poses[0].valid ? { t, status: "tracked", pose: poses[0] } : { t, status: "lost", pose: null };
  const a = poses[i];
  const j = Math.min(i + 1, poses.length - 1);
  const b = poses[j];
  const gap = times[j] - times[i];
  if (j === i || gap <= 0) return a.valid ? { t, status: "tracked", pose: a } : { t, status: "lost", pose: null };
  const u = (t - times[i]) / gap;
  // Frames more than ~1.5 steps apart mean dropped analysis frames: treat as unknown.
  if (gap > step * 1.5) {
    const near = u < 0.5 ? a : b;
    const dist = Math.min(t - times[i], times[j] - t);
    return near.valid && dist <= step / 2 ? { t, status: "tracked", pose: near } : { t, status: "lost", pose: null };
  }
  if (a.valid && b.valid) return { t, status: "tracked", pose: blendPoses(a, b, u, track.rig) };
  const near = u < 0.5 ? a : b;
  return near.valid ? { t, status: "tracked", pose: near } : { t, status: "lost", pose: null };
}

/** Which clip-level untracked bones belong to which body part, for labels. */
export function untrackedParts(rig: ClipRig): string[] {
  const parts: string[] = [];
  const has = (...names: BoneName[]) => names.every((n) => rig.untracked.includes(n));
  const any = (...names: BoneName[]) => names.some((n) => rig.untracked.includes(n));
  if (has("shinL", "shinR")) parts.push(has("thighL", "thighR") ? "legs" : "lower legs");
  else {
    if (any("shinL", "thighL")) parts.push(rig.untracked.includes("thighL") ? "left leg" : "left lower leg");
    if (any("shinR", "thighR")) parts.push(rig.untracked.includes("thighR") ? "right leg" : "right lower leg");
  }
  if (any("upperArmL", "forearmL")) parts.push(rig.untracked.includes("upperArmL") ? "left arm" : "left forearm");
  if (any("upperArmR", "forearmR")) parts.push(rig.untracked.includes("upperArmR") ? "right arm" : "right forearm");
  if (rig.untracked.includes("neck")) parts.push("head");
  return parts;
}

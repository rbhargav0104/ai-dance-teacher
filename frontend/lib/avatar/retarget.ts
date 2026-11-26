/**
 * Avatar retargeting maths (docs/SPEC_AMENDMENTS.md A1). Pure and deterministic.
 *
 * Input: MediaPipe *world* landmarks per analysed frame (metres, hip-centred; x to the image
 * right, y down, z toward the camera is negative) plus per-landmark reliability measured by
 * the pipeline. Output: avatar bones aimed along the measured segment directions with fixed,
 * per-clip median lengths, in a y-up, right-handed space (camera on +z looking at the dancer).
 *
 * Honesty rules: a bone is "measured" only when both of its landmarks were reliable in that
 * frame. Otherwise it is "untracked" and held in a neutral rest direction for a ghosted render;
 * nothing is inferred from other limbs. Bones that are untracked in most valid frames of the
 * clip are reported so the UI can label them ("not tracked in this video").
 */

export type Vec3 = [number, number, number];

export const LM = {
  NOSE: 0,
  L_SHOULDER: 11,
  R_SHOULDER: 12,
  L_ELBOW: 13,
  R_ELBOW: 14,
  L_WRIST: 15,
  R_WRIST: 16,
  L_HIP: 23,
  R_HIP: 24,
  L_KNEE: 25,
  R_KNEE: 26,
  L_ANKLE: 27,
  R_ANKLE: 28,
} as const;

export type BoneName =
  | "spine"
  | "neck"
  | "upperArmL"
  | "forearmL"
  | "upperArmR"
  | "forearmR"
  | "thighL"
  | "shinL"
  | "thighR"
  | "shinR";

export interface BoneDef {
  name: BoneName;
  /** Landmark (or virtual midpoint) the bone starts at / points to. */
  from: number | "hips" | "shoulders";
  to: number | "shoulders" | "nose";
  /** Rest direction in avatar space (y-up), used when the bone isn't measured. */
  rest: Vec3;
  /** Parent joint the bone hangs from in the avatar skeleton. */
  parent: "pelvis" | "chest" | "shoulderL" | "shoulderR" | "elbowL" | "elbowR" | "hipL" | "hipR" | "kneeL" | "kneeR";
}

const DOWN: Vec3 = [0, -1, 0];
const UP: Vec3 = [0, 1, 0];

export const BONES: BoneDef[] = [
  { name: "spine", from: "hips", to: "shoulders", rest: UP, parent: "pelvis" },
  { name: "neck", from: "shoulders", to: "nose", rest: UP, parent: "chest" },
  { name: "upperArmL", from: LM.L_SHOULDER, to: LM.L_ELBOW, rest: DOWN, parent: "shoulderL" },
  { name: "forearmL", from: LM.L_ELBOW, to: LM.L_WRIST, rest: DOWN, parent: "elbowL" },
  { name: "upperArmR", from: LM.R_SHOULDER, to: LM.R_ELBOW, rest: DOWN, parent: "shoulderR" },
  { name: "forearmR", from: LM.R_ELBOW, to: LM.R_WRIST, rest: DOWN, parent: "elbowR" },
  { name: "thighL", from: LM.L_HIP, to: LM.L_KNEE, rest: DOWN, parent: "hipL" },
  { name: "shinL", from: LM.L_KNEE, to: LM.L_ANKLE, rest: DOWN, parent: "kneeL" },
  { name: "thighR", from: LM.R_HIP, to: LM.R_KNEE, rest: DOWN, parent: "hipR" },
  { name: "shinR", from: LM.R_KNEE, to: LM.R_ANKLE, rest: DOWN, parent: "kneeR" },
];

/** Fallback proportions (metres) when a bone is never measured in the clip. */
export const DEFAULT_LENGTHS: Record<BoneName, number> = {
  spine: 0.5,
  neck: 0.25,
  upperArmL: 0.28,
  forearmL: 0.25,
  upperArmR: 0.28,
  forearmR: 0.25,
  thighL: 0.42,
  shinL: 0.4,
  thighR: 0.42,
  shinR: 0.4,
};

export interface WorldFrame {
  t: number;
  valid: boolean;
  world: Vec3[] | null;
  reliable: boolean[];
  /** Landmarks filled across a short gap (≤ 2 analysed frames). Usable, but drawn faint. */
  bridged?: boolean[];
}

/** MediaPipe world (x right, y down, z toward camera negative) → avatar space (y up, +z toward camera). */
export function toAvatarSpace(p: Vec3): Vec3 {
  return [p[0], -p[1], -p[2]];
}

const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const scale = (a: Vec3, k: number): Vec3 => [a[0] * k, a[1] * k, a[2] * k];
const mid = (a: Vec3, b: Vec3): Vec3 => scale(add(a, b), 0.5);
export const norm = (a: Vec3) => Math.hypot(a[0], a[1], a[2]);
export function unit(a: Vec3): Vec3 | null {
  const n = norm(a);
  return n > 1e-9 ? scale(a, 1 / n) : null;
}
export const dot = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

function usable(f: WorldFrame, i: number): boolean {
  return Boolean(f.reliable[i] || f.bridged?.[i]) && Array.isArray(f.world?.[i]);
}

function refIndices(ref: BoneDef["from"] | BoneDef["to"]): number[] {
  if (ref === "hips") return [LM.L_HIP, LM.R_HIP];
  if (ref === "shoulders") return [LM.L_SHOULDER, LM.R_SHOULDER];
  if (ref === "nose") return [LM.NOSE];
  return [ref];
}

/** True when any landmark the bone depends on was bridged rather than measured in this frame. */
export function boneBridged(f: WorldFrame, bone: BoneDef): boolean {
  return [...refIndices(bone.from), ...refIndices(bone.to)].some((i) => !f.reliable[i] && Boolean(f.bridged?.[i]));
}

function point(f: WorldFrame, ref: BoneDef["from"] | BoneDef["to"]): Vec3 | null {
  const w = f.world;
  if (!w) return null;
  const ok = (i: number) => usable(f, i);
  if (ref === "hips") return ok(LM.L_HIP) && ok(LM.R_HIP) ? toAvatarSpace(mid(w[LM.L_HIP], w[LM.R_HIP])) : null;
  if (ref === "shoulders")
    return ok(LM.L_SHOULDER) && ok(LM.R_SHOULDER) ? toAvatarSpace(mid(w[LM.L_SHOULDER], w[LM.R_SHOULDER])) : null;
  if (ref === "nose") return ok(LM.NOSE) ? toAvatarSpace(w[LM.NOSE]) : null;
  return ok(ref) ? toAvatarSpace(w[ref]) : null;
}

/** Measured direction of a bone in one frame, or null when either end wasn't reliable. */
export function boneDirection(f: WorldFrame, bone: BoneDef): Vec3 | null {
  const a = point(f, bone.from);
  const b = point(f, bone.to);
  if (!a || !b) return null;
  return unit(sub(b, a));
}

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

export interface ClipRig {
  lengths: Record<BoneName, number>;
  /** Fraction of valid frames in which each bone was measured. */
  trackedFraction: Record<BoneName, number>;
  /** Bones measured in fewer than `minTracked` of valid frames: render ghosted, label untracked. */
  untracked: BoneName[];
  shoulderWidth: number;
  hipWidth: number;
}

/** Fixed bone lengths = robust per-clip medians, so limbs never stretch frame to frame. */
export function buildRig(frames: WorldFrame[], minTracked = 0.5): ClipRig {
  const lengths = { ...DEFAULT_LENGTHS };
  const trackedFraction = {} as Record<BoneName, number>;
  const valid = frames.filter((f) => f.valid && f.world);
  for (const bone of BONES) {
    const ls: number[] = [];
    for (const f of valid) {
      if (boneBridged(f, bone)) continue; // lengths and tracked fraction count measured frames only
      const a = point(f, bone.from);
      const b = point(f, bone.to);
      if (a && b) ls.push(norm(sub(b, a)));
    }
    trackedFraction[bone.name] = valid.length ? ls.length / valid.length : 0;
    if (ls.length) lengths[bone.name] = median(ls);
  }
  const width = (l: number, r: number, fallback: number) => {
    const ws = valid
      .filter((f) => f.reliable[l] && f.reliable[r])
      .map((f) => norm(sub(f.world![l], f.world![r])));
    return ws.length ? median(ws) : fallback;
  };
  return {
    lengths,
    trackedFraction,
    untracked: BONES.filter((b) => trackedFraction[b.name] < minTracked).map((b) => b.name),
    shoulderWidth: width(LM.L_SHOULDER, LM.R_SHOULDER, 0.36),
    hipWidth: width(LM.L_HIP, LM.R_HIP, 0.26),
  };
}

export type BoneState = "measured" | "bridged" | "untracked";

export interface BonePose {
  name: BoneName;
  start: Vec3;
  end: Vec3;
  dir: Vec3;
  /** measured or bridged: the direction comes from this video's landmarks. */
  measured: boolean;
  state: BoneState;
}

export interface AvatarPose {
  t: number;
  valid: boolean;
  bones: Record<BoneName, BonePose>;
  /** Unit vector from the dancer's right shoulder to left shoulder (for torso facing). */
  shoulderAxis: Vec3 | null;
}

/**
 * Pose the avatar for one analysed frame: hips at the origin, every bone aimed along its
 * measured direction with the clip's fixed length; unmeasured bones use their rest direction.
 */
export function poseFrame(f: WorldFrame, rig: ClipRig): AvatarPose {
  const bones = {} as Record<BoneName, BonePose>;
  // Bones the clip rarely tracked stay ghosted throughout, so the "not tracked in this video"
  // label is never contradicted by sporadic (usually edge-of-frame) detections.
  const held = new Set(rig.untracked);
  const dirOf = (b: BoneDef) => {
    const d = f.valid && !held.has(b.name) ? boneDirection(f, b) : null;
    const state: BoneState = d === null ? "untracked" : boneBridged(f, b) ? "bridged" : "measured";
    return { dir: d ?? b.rest, measured: d !== null, state };
  };
  const byName = Object.fromEntries(BONES.map((b) => [b.name, b])) as Record<BoneName, BoneDef>;
  const place = (name: BoneName, start: Vec3) => {
    const { dir, measured, state } = dirOf(byName[name]);
    const end = add(start, scale(dir, rig.lengths[name]));
    bones[name] = { name, start, end, dir, measured, state };
    return end;
  };

  const w = f.world;
  const rel = (i: number) => Boolean(f.valid && w && usable(f, i));
  const axisOf = (l: number, r: number): Vec3 | null =>
    rel(l) && rel(r) ? unit(sub(toAvatarSpace(w![l]), toAvatarSpace(w![r]))) : null;
  // Measured axes pointing to the dancer's left. Facing the camera (+z), the dancer's left is +x.
  const shoulderAxis = axisOf(LM.L_SHOULDER, LM.R_SHOULDER);
  const hipAxis = axisOf(LM.L_HIP, LM.R_HIP);
  const restAxis: Vec3 = [1, 0, 0];

  const pelvis: Vec3 = [0, 0, 0];
  const chest = place("spine", pelvis);
  place("neck", chest);
  const sAxis = shoulderAxis ?? restAxis;
  const hAxis = hipAxis ?? restAxis;
  const shoulderL = add(chest, scale(sAxis, rig.shoulderWidth / 2));
  const shoulderR = add(chest, scale(sAxis, -rig.shoulderWidth / 2));
  place("forearmL", place("upperArmL", shoulderL));
  place("forearmR", place("upperArmR", shoulderR));
  const hipL = add(pelvis, scale(hAxis, rig.hipWidth / 2));
  const hipR = add(pelvis, scale(hAxis, -rig.hipWidth / 2));
  place("shinL", place("thighL", hipL));
  place("shinR", place("thighR", hipR));
  return { t: f.t, valid: f.valid, bones, shoulderAxis };
}

/** Left/right landmark pairs (MediaPipe indices 1..32) for mirroring. */
const PAIRS: [number, number][] = [
  [1, 4], [2, 5], [3, 6], [7, 8], [9, 10], [11, 12], [13, 14], [15, 16], [17, 18], [19, 20],
  [21, 22], [23, 24], [25, 26], [27, 28], [29, 30], [31, 32],
];
export const MIRROR_MAP: number[] = (() => {
  const m = Array.from({ length: 33 }, (_, i) => i);
  for (const [a, b] of PAIRS) {
    m[a] = b;
    m[b] = a;
  }
  return m;
})();

/**
 * Mirror a frame like a dance-class mirror: reflect across the body's sagittal plane (negate x)
 * and swap left/right landmarks so the mirrored dancer's "left" is anatomically consistent.
 */
export function mirrorFrame(f: WorldFrame): WorldFrame {
  const bridged = f.bridged ? MIRROR_MAP.map((j) => f.bridged![j] ?? false) : undefined;
  const reliable = MIRROR_MAP.map((j) => f.reliable[j] ?? false);
  if (!f.world) return { ...f, reliable, bridged };
  return {
    ...f,
    world: MIRROR_MAP.map((j) => [-f.world![j][0], f.world![j][1], f.world![j][2]] as Vec3),
    reliable,
    bridged,
  };
}

/** Angle in degrees between two directions (for "avatar arm matches measured arm" checks). */
export function angleBetween(a: Vec3, b: Vec3): number {
  const ua = unit(a);
  const ub = unit(b);
  if (!ua || !ub) return NaN;
  return (Math.acos(Math.max(-1, Math.min(1, dot(ua, ub)))) * 180) / Math.PI;
}

// Synthetic world landmarks are allowed here: these tests check pure smoothing/sampling maths only.
import { describe, expect, it } from "vitest";

import { LM, type Vec3, angleBetween, toAvatarSpace } from "@/lib/avatar/retarget";
import { bridgeGaps, buildTrack, oneEuro, sampleTrack, smoothWorldFrames, untrackedParts } from "@/lib/avatar/track";
import type { PoseFrame, PosesResponse } from "@/lib/types";

const FPS = 12;

function standing(): Vec3[] {
  const w: Vec3[] = Array.from({ length: 33 }, () => [0, 0, 0] as Vec3);
  w[LM.NOSE] = [0, -0.65, -0.05];
  w[LM.L_SHOULDER] = [0.18, -0.5, 0];
  w[LM.R_SHOULDER] = [-0.18, -0.5, 0];
  w[LM.L_ELBOW] = [0.2, -0.22, 0];
  w[LM.R_ELBOW] = [-0.2, -0.22, 0];
  w[LM.L_WRIST] = [0.21, 0.03, 0];
  w[LM.R_WRIST] = [-0.21, 0.03, 0];
  w[LM.L_HIP] = [0.12, 0, 0];
  w[LM.R_HIP] = [-0.12, 0, 0];
  w[LM.L_KNEE] = [0.13, 0.42, 0];
  w[LM.R_KNEE] = [-0.13, 0.42, 0];
  w[LM.L_ANKLE] = [0.13, 0.82, 0];
  w[LM.R_ANKLE] = [-0.13, 0.82, 0];
  return w;
}

/** Left (dancer's own) arm raised sideways to shoulder height: elbow/wrist out along +x. */
function leftArmOut(w: Vec3[]): Vec3[] {
  const o = w.map((p) => [...p] as Vec3);
  o[LM.L_ELBOW] = [0.46, -0.5, 0];
  o[LM.L_WRIST] = [0.71, -0.5, 0];
  return o;
}

function frame(i: number, world: Vec3[] | null, reliable: (j: number) => boolean = () => true, valid = true): PoseFrame {
  return {
    t: i / FPS,
    frame: i,
    valid,
    confidence: 0.9,
    data: {
      poses_detected: world ? 1 : 0,
      landmarks: null,
      smoothed: [],
      reliable: Array.from({ length: 33 }, (_, j) => Boolean(world) && reliable(j)),
      interpolated: Array.from({ length: 33 }, () => false),
      normalized: [],
      world,
      angles: {},
      root: [null, null],
      travel: [null, null],
      com_estimate: [null, null],
      speed: [],
      motion_energy: null,
      torso_lean: null,
      shoulder_tilt: null,
      hip_tilt: null,
      yaw_experimental: null,
    },
  };
}

const poses = (frames: PoseFrame[]): Pick<PosesResponse, "frames" | "analysis_fps"> => ({ frames, analysis_fps: FPS });

describe("oneEuro", () => {
  it("leaves a constant signal unchanged and is deterministic", () => {
    const t = Array.from({ length: 20 }, (_, i) => i / FPS);
    const v = t.map(() => 0.3);
    const r = t.map(() => true);
    const a = oneEuro(v, t, r);
    expect(a.every((x) => Math.abs(x - 0.3) < 1e-12)).toBe(true);
    expect(oneEuro(v, t, r)).toEqual(a);
  });

  it("reduces jitter on a noisy still joint", () => {
    const t = Array.from({ length: 60 }, (_, i) => i / FPS);
    const v = t.map((_, i) => 0.5 + (i % 2 ? 0.02 : -0.02));
    const out = oneEuro(v, t, t.map(() => true));
    const spread = (xs: number[]) => Math.max(...xs) - Math.min(...xs);
    expect(spread(out.slice(10))).toBeLessThan(spread(v.slice(10)) * 0.6);
  });

  it("never smooths through an unreliable sample (restarts after it)", () => {
    const t = [0, 1, 2, 3, 4].map((i) => i / FPS);
    const out = oneEuro([0, 0, 5, 1, 1], t, [true, true, false, true, true]);
    expect(Number.isNaN(out[2])).toBe(true);
    expect(out[3]).toBe(1); // restart: first sample passes through
  });
});

describe("bridgeGaps", () => {
  it("fills gaps of up to two samples and marks them; never longer gaps or edges", () => {
    const k = [true, false, false, true, false, false, false, true, false];
    const { values, bridged } = bridgeGaps([0, NaN, NaN, 3, NaN, NaN, NaN, 7, NaN], k);
    expect(values.slice(0, 4)).toEqual([0, 1, 2, 3]);
    expect(bridged).toEqual([false, true, true, false, false, false, false, false, false]);
    expect(Number.isNaN(values[5])).toBe(true);
    expect(Number.isNaN(values[8])).toBe(true);
  });
});

describe("smoothWorldFrames + buildTrack", () => {
  it("bridges a 2-frame wrist dropout as 'bridged' and a 3-frame one as 'untracked'", () => {
    const w = standing();
    const dropWrist = (from: number, len: number) => (i: number) => (j: number) => !(j === LM.L_WRIST && i >= from && i < from + len);
    const f2 = Array.from({ length: 12 }, (_, i) => frame(i, w, dropWrist(4, 2)(i)));
    const t2 = buildTrack(poses(f2), false);
    expect(t2.poses[4].bones.forearmL.state).toBe("bridged");
    expect(t2.poses[5].bones.forearmL.state).toBe("bridged");
    expect(t2.poses[6].bones.forearmL.state).toBe("measured");

    const f3 = Array.from({ length: 12 }, (_, i) => frame(i, w, dropWrist(4, 3)(i)));
    const t3 = buildTrack(poses(f3), false);
    for (const i of [4, 5, 6]) {
      expect(t3.poses[i].bones.forearmL.state).toBe("untracked");
      expect(t3.poses[i].bones.forearmL.dir).toEqual([0, -1, 0]); // rest, not a guess
    }
  });

  it("does not bridge across an invalid frame", () => {
    const w = standing();
    const f = Array.from({ length: 6 }, (_, i) => (i === 2 ? frame(i, null, () => false, false) : frame(i, w)));
    const s = smoothWorldFrames(poses(f));
    expect(s[2].valid).toBe(false);
    expect(s[2].world).toBeNull();
  });

  it("labels legs as untracked when they are never measured (like the cropped samples)", () => {
    const legs = new Set<number>([LM.L_KNEE, LM.R_KNEE, LM.L_ANKLE, LM.R_ANKLE]);
    const f = Array.from({ length: 10 }, (_, i) => frame(i, standing(), (j) => !legs.has(j)));
    const t = buildTrack(poses(f), false);
    expect(t.rig.untracked).toEqual(expect.arrayContaining(["thighL", "thighR", "shinL", "shinR"]));
    expect(untrackedParts(t.rig)).toEqual(["legs"]);
    expect(t.poses[3].bones.thighL.state).toBe("untracked");
  });

  it("keeps a rarely-tracked limb ghosted in every frame, even where it was briefly detected", () => {
    const legs = new Set<number>([LM.L_KNEE, LM.R_KNEE, LM.L_ANKLE, LM.R_ANKLE]);
    // Legs reliable in 3 of 10 frames (< 50%): sporadic edge-of-frame detections.
    const f = Array.from({ length: 10 }, (_, i) => frame(i, standing(), (j) => i < 3 || !legs.has(j)));
    const t = buildTrack(poses(f), false);
    expect(t.rig.untracked).toContain("thighL");
    for (const p of t.poses) expect(p.bones.thighL.state).toBe("untracked");
    expect(t.poses[0].bones.upperArmL.state).toBe("measured");
  });
});

describe("sampleTrack", () => {
  const w0 = standing();
  const w1 = leftArmOut(w0);

  it("matches the measured arm direction at analysed frames and interpolates between them", () => {
    const f = Array.from({ length: 10 }, (_, i) => frame(i, i < 5 ? w0 : w1));
    // Long stable runs so the filter has settled at frame 0 and 9.
    const t = buildTrack(poses(f), false);
    const at0 = sampleTrack(t, 0);
    expect(at0.status).toBe("tracked");
    const measuredDown = toAvatarSpace([0.02, 0.28, 0]);
    expect(angleBetween(at0.pose!.bones.upperArmL.dir, measuredDown)).toBeLessThan(1);
    // Midway between two analysed frames the direction lies between them.
    const a = sampleTrack(t, 4 / FPS).pose!.bones.upperArmL.dir;
    const b = sampleTrack(t, 5 / FPS).pose!.bones.upperArmL.dir;
    const m = sampleTrack(t, 4.5 / FPS).pose!.bones.upperArmL.dir;
    const ab = angleBetween(a, b);
    expect(ab).toBeGreaterThan(5);
    expect(angleBetween(a, m) + angleBetween(m, b)).toBeCloseTo(ab, 3);
  });

  it("keeps fixed bone lengths at every sampled time", () => {
    const f = Array.from({ length: 10 }, (_, i) => frame(i, i % 2 ? w0 : w1));
    const t = buildTrack(poses(f), false);
    for (const time of [0, 0.03, 0.2, 0.41, 0.6]) {
      const p = sampleTrack(t, time).pose!;
      const b = p.bones.forearmL;
      expect(Math.hypot(b.end[0] - b.start[0], b.end[1] - b.start[1], b.end[2] - b.start[2])).toBeCloseTo(t.rig.lengths.forearmL, 6);
    }
  });

  it("reports 'lost' next to an invalid frame and 'outside' beyond the clip", () => {
    const f = Array.from({ length: 8 }, (_, i) => (i === 4 ? frame(i, null, () => false, false) : frame(i, w0)));
    const t = buildTrack(poses(f), false);
    expect(sampleTrack(t, 4 / FPS).status).toBe("lost");
    expect(sampleTrack(t, 4.2 / FPS).status).toBe("lost");
    expect(sampleTrack(t, 2 / FPS).status).toBe("tracked");
    expect(sampleTrack(t, 5).status).toBe("outside");
  });

  it("mirror: the dancer's raised left arm appears on the mirrored avatar's left-of-screen side as its right arm", () => {
    const f = Array.from({ length: 6 }, (_, i) => frame(i, w1));
    const direct = sampleTrack(buildTrack(poses(f), false), 0.2).pose!;
    const mirrored = sampleTrack(buildTrack(poses(f), true), 0.2).pose!;
    // Direct: dancer's left arm points to screen right (+x).
    expect(direct.bones.upperArmL.dir[0]).toBeGreaterThan(0.9);
    // Mirrored: reflected to screen left, and carried by the mirrored avatar's right arm.
    expect(mirrored.bones.upperArmR.dir[0]).toBeLessThan(-0.9);
    expect(mirrored.bones.upperArmL.dir[1]).toBeLessThan(-0.9);
  });
});

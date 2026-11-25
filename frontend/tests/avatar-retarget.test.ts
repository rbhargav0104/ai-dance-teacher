// Synthetic world landmarks are allowed here: these tests check pure retargeting maths only.
import { describe, expect, it } from "vitest";

import {
  BONES,
  LM,
  MIRROR_MAP,
  type Vec3,
  type WorldFrame,
  angleBetween,
  boneDirection,
  buildRig,
  mirrorFrame,
  norm,
  poseFrame,
  toAvatarSpace,
} from "@/lib/avatar/retarget";

/** A standing dancer facing the camera in MediaPipe world coordinates (y down, metres). */
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
  w[LM.L_KNEE] = [0.12, 0.42, 0];
  w[LM.R_KNEE] = [-0.12, 0.42, 0];
  w[LM.L_ANKLE] = [0.12, 0.82, 0];
  w[LM.R_ANKLE] = [-0.12, 0.82, 0];
  return w;
}

const all = (v: boolean) => Array.from({ length: 33 }, () => v);
const frame = (world: Vec3[], reliable = all(true), t = 0, valid = true): WorldFrame => ({ t, valid, world, reliable });

describe("avatar retargeting", () => {
  it("maps MediaPipe world space to y-up avatar space", () => {
    expect(toAvatarSpace([0.1, -0.5, -0.2])).toEqual([0.1, 0.5, 0.2]);
  });

  it("aims a raised left arm up and to the dancer's left", () => {
    const w = standing();
    w[LM.L_ELBOW] = [0.3, -0.75, 0]; // arm raised overhead-left
    w[LM.L_WRIST] = [0.35, -1.0, 0];
    const f = frame(w);
    const rig = buildRig([f]);
    const pose = poseFrame(f, rig);
    const d = pose.bones.upperArmL.dir;
    expect(d[1]).toBeGreaterThan(0.6); // up
    expect(d[0]).toBeGreaterThan(0); // toward the dancer's left (+x when facing the camera)
    expect(pose.bones.upperArmL.measured).toBe(true);
    // Matches the measured landmarks exactly (the exit-gate check).
    const measured = boneDirection(f, BONES.find((b) => b.name === "upperArmL")!)!;
    expect(angleBetween(d, measured)).toBeLessThan(1e-6);
  });

  it("keeps bone lengths fixed at the clip median even when a frame stretches", () => {
    const frames = [0, 1, 2, 3, 4].map((i) => {
      const w = standing();
      if (i === 4) w[LM.L_WRIST] = [0.21, 0.4, 0]; // outlier: forearm 0.62 m
      return frame(w, all(true), i / 12);
    });
    const rig = buildRig(frames);
    expect(rig.lengths.forearmL).toBeCloseTo(0.25, 2);
    const p = poseFrame(frames[4], rig);
    const b = p.bones.forearmL;
    expect(norm([b.end[0] - b.start[0], b.end[1] - b.start[1], b.end[2] - b.start[2]])).toBeCloseTo(rig.lengths.forearmL, 6);
  });

  it("never animates untracked limbs: they rest and are reported", () => {
    const reliable = all(true);
    for (const j of [LM.L_KNEE, LM.R_KNEE, LM.L_ANKLE, LM.R_ANKLE]) reliable[j] = false;
    const w = standing();
    w[LM.L_KNEE] = [0.5, 0.1, 0.3]; // garbage values where the tracker wasn't confident
    const frames = [frame(w, reliable), frame(w, reliable, 1 / 12)];
    const rig = buildRig(frames);
    expect(rig.untracked).toEqual(expect.arrayContaining(["thighL", "thighR", "shinL", "shinR"]));
    expect(rig.untracked).not.toContain("upperArmL");
    const p = poseFrame(frames[0], rig);
    expect(p.bones.thighL.measured).toBe(false);
    expect(p.bones.thighL.dir).toEqual([0, -1, 0]);
    expect(p.bones.shinR.measured).toBe(false);
  });

  it("an invalid frame poses nothing as measured", () => {
    const p = poseFrame(frame(standing(), all(true), 0, false), buildRig([frame(standing())]));
    expect(Object.values(p.bones).every((b) => !b.measured)).toBe(true);
  });

  it("mirroring swaps sides and reflects x like a mirror", () => {
    const w = standing();
    w[LM.L_ELBOW] = [0.3, -0.75, 0];
    w[LM.L_WRIST] = [0.35, -1.0, 0];
    const reliable = all(true);
    reliable[LM.R_WRIST] = false;
    const m = mirrorFrame(frame(w, reliable));
    expect(MIRROR_MAP[LM.L_WRIST]).toBe(LM.R_WRIST);
    expect(m.world![LM.R_WRIST]).toEqual([-0.35, -1.0, 0]); // raised arm is now the right one
    expect(m.reliable[LM.L_WRIST]).toBe(false); // reliability follows the landmark
    const rig = buildRig([m]);
    const p = poseFrame(m, rig);
    expect(p.bones.upperArmR.dir[1]).toBeGreaterThan(0.6);
    expect(p.bones.upperArmR.dir[0]).toBeLessThan(0);
    expect(mirrorFrame(mirrorFrame(frame(w, reliable))).world).toEqual(w.map((p) => [p[0] === 0 ? 0 : p[0], p[1], p[2]]));
  });
});

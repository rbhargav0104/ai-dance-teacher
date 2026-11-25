import { describe, expect, it } from "vitest";

import { containRect, frameAt, jointState, nearestFrameIndex, percent, toScreen } from "@/lib/pose";
import type { PoseFrame } from "@/lib/types";

function frame(t: number, opts: Partial<PoseFrame["data"]> = {}): PoseFrame {
  return {
    t,
    frame: Math.round(t * 24),
    valid: true,
    confidence: 0.9,
    data: {
      poses_detected: 1,
      landmarks: null,
      smoothed: [[0.5, 0.5, 0], null, [0.2, 0.2, 0]],
      reliable: [true, false, false],
      interpolated: [false, false, true],
      normalized: [],
      world: null,
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
      ...opts,
    },
  };
}

describe("pose helpers", () => {
  const frames = [0, 1 / 12, 2 / 12, 3 / 12].map((t) => ({ t }));

  it("finds the nearest analysed frame", () => {
    expect(nearestFrameIndex([], 1)).toBe(-1);
    expect(nearestFrameIndex(frames, 0)).toBe(0);
    expect(nearestFrameIndex(frames, 0.09)).toBe(1);
    expect(nearestFrameIndex(frames, 0.124)).toBe(1);
    expect(nearestFrameIndex(frames, 10)).toBe(3);
  });

  it("refuses to reuse a frame far from the playhead", () => {
    const fs = [frame(0), frame(1 / 12)];
    expect(frameAt(fs, 0.04, 12)?.t).toBe(0);
    expect(frameAt(fs, 0.5, 12)).toBeNull();
  });

  it("maps landmarks into a letterboxed video", () => {
    // 16:9 video in a square box → bars top and bottom.
    const r = containRect(1000, 1000, 1280, 720);
    expect(r.width).toBe(1000);
    expect(r.height).toBeCloseTo(562.5);
    expect(r.y).toBeCloseTo(218.75);
    expect(toScreen(r, 0.5, 0.5)).toEqual([500, 500]);
    expect(toScreen(r, 0, 0)).toEqual([0, r.y]);
    // Portrait video in a wide box → bars left and right.
    const p = containRect(1600, 900, 720, 1280);
    expect(p.height).toBe(900);
    expect(p.x).toBeCloseTo((1600 - 506.25) / 2);
  });

  it("never draws hidden joints, and marks bridged ones", () => {
    const f = frame(0);
    expect(jointState(f, 0)).toBe("measured");
    expect(jointState(f, 1)).toBe("hidden");
    expect(jointState(f, 2)).toBe("bridged");
  });

  it("formats unknown values as a dash", () => {
    expect(percent(null)).toBe("—");
    expect(percent(0.887)).toBe("89%");
  });
});

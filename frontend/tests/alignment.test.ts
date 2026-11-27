import { describe, expect, it } from "vitest";

import { costTone, pathPoints, referenceTimeAt, timingFacts } from "@/lib/alignment";
import type { Alignment, AlignmentFrame } from "@/lib/types";

function frame(ref_t: number, learner_t: number, extra: Partial<AlignmentFrame> = {}): AlignmentFrame {
  return {
    ref_t,
    ref_src_t: ref_t + 5, // section starts at 5 s of the reference video
    learner_t,
    learner_src_t: learner_t,
    cost: 0.1,
    position: 0.1,
    angle: 0.1,
    lean: 0,
    direction: 0,
    measured: true,
    reused: false,
    offset_s: learner_t - ref_t,
    missing: false,
    ...extra,
  };
}

function aligned(frames: AlignmentFrame[], extra: Partial<Alignment> = {}): Alignment {
  return {
    version: "align-1",
    status: "aligned",
    scorable: true,
    reference_frames: frames.length,
    learner_frames: frames.length,
    reference_usable_frames: frames.length,
    learner_usable_frames: frames.length,
    frames,
    timing: { median_offset_s: 0, speed_ratio: 1, fit_intercept_s: 0, max_local_deviation_s: 0, off_spans: [] },
    mirror: { chosen: "direct", decision: "clear", preferred: "direct", margin: 0.1, mean_cost: { direct: 0.1, mirrored: 0.9 } },
    missing_spans: [],
    masked_spans: [],
    ...extra,
  };
}

describe("referenceTimeAt", () => {
  it("follows a late start: the reference waits, then runs on the learner's clock", () => {
    // Learner started 1 s late: reference window 0..2 s paired with learner 1..3 s.
    const a = aligned([frame(0, 1), frame(1, 2), frame(2, 3)]);
    expect(referenceTimeAt(a, 0)).toBe(5); // waiting at the section start
    expect(referenceTimeAt(a, 1)).toBe(5);
    expect(referenceTimeAt(a, 1.5)).toBeCloseTo(5.5);
    expect(referenceTimeAt(a, 3)).toBe(7);
    expect(referenceTimeAt(a, 9)).toBe(7); // holds the end
  });

  it("follows a slower learner (speed preserved, not erased)", () => {
    const a = aligned([frame(0, 0), frame(1, 2), frame(2, 4)]);
    expect(referenceTimeAt(a, 1)).toBeCloseTo(5.5);
    expect(referenceTimeAt(a, 3)).toBeCloseTo(6.5);
  });

  it("never jumps ahead while the learner holds one pose", () => {
    // Learner frame at 1 s paired with reference 1, 2 and 3 s (learner held still).
    const a = aligned([frame(0, 0), frame(1, 1), frame(2, 1), frame(3, 1), frame(4, 2)]);
    expect(referenceTimeAt(a, 1)).toBe(6); // first of the held pairs
    expect(referenceTimeAt(a, 0.5)).toBeCloseTo(5.5);
    expect(referenceTimeAt(a, 1.5)).toBeCloseTo(8.5); // between the last held pair (ref 3 s) and ref 4 s
  });

  it("is null without frames", () => {
    expect(referenceTimeAt(null, 1)).toBeNull();
    expect(referenceTimeAt(aligned([]), 1)).toBeNull();
  });
});

describe("timingFacts", () => {
  it("states measured lateness, pace and mirroring in plain words", () => {
    const a = aligned([frame(0, 0)], {
      timing: { median_offset_s: 0.42, speed_ratio: 1.11, fit_intercept_s: 0, max_local_deviation_s: 0, off_spans: [] },
      mirror: { chosen: "mirrored", decision: "clear", preferred: "direct", margin: 0.1, mean_cost: { direct: 0.9, mirrored: 0.1 } },
      missing_spans: [[5.25, 8.9]],
      masked_spans: [[6, 7]],
    });
    const facts = timingFacts(a);
    expect(facts[0]).toBe("You were about 0.4 s behind the reference.");
    expect(facts[1]).toBe("Your pace was about 11% slower than the reference.");
    expect(facts[2]).toMatch(/mirror image/);
    expect(facts[3]).toMatch(/5\.3–8\.9 s/);
    expect(facts[4]).toMatch(/not counted as wrong/);
  });

  it("says when the recording stopped before the reference did", () => {
    const a = aligned([frame(0, 0)], {
      warp: { non_diagonal_fraction: 0.2, max_learner_hold_s: 1.5, max_reference_hold_s: 0, learner_start_s: 0, learner_end_s: 5.3, attempt_ended_early_s: 1.5 },
    });
    expect(timingFacts(a)).toEqual(["Your recording ended about 1.5 s before the reference passage did."]);
  });

  it("says nothing about tiny differences or unaligned attempts", () => {
    const a = aligned([frame(0, 0)], {
      timing: { median_offset_s: 0.08, speed_ratio: 1.02, fit_intercept_s: 0, max_local_deviation_s: 0, off_spans: [] },
    });
    expect(timingFacts(a)).toEqual([]);
    expect(timingFacts({ ...a, status: "insufficient_tracking" })).toEqual([]);
    expect(
      timingFacts(aligned([frame(0, 0)], { timing: { median_offset_s: -0.6, speed_ratio: 0.9, fit_intercept_s: 0, max_local_deviation_s: 0, off_spans: [] } })),
    ).toEqual(["You were about 0.6 s ahead of the reference.", "Your pace was about 10% faster than the reference."]);
  });
});

describe("chart helpers", () => {
  it("buckets costs and keeps unmeasured pairs separate", () => {
    expect(costTone(0.05)).toBe("good");
    expect(costTone(0.3)).toBe("fair");
    expect(costTone(0.8)).toBe("off");
    expect(costTone(null)).toBe("masked");
  });
  it("maps path points into the chart box (y up)", () => {
    expect(pathPoints([frame(0, 0), frame(2, 4)], 100, 50, 2, 4)).toBe("0.0,50.0 100.0,0.0");
    expect(pathPoints([], 100, 50, 2, 4)).toBe("");
  });
});

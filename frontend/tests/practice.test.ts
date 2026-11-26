import { describe, expect, it } from "vitest";

import {
  AUTO_STOP_PADDING_SECONDS,
  cameraProblem,
  extensionFor,
  formatClock,
  needsResync,
  pickRecorderType,
  practiceStatusLabel,
  recordingLimit,
  referenceTimeFor,
  reviewLength,
} from "@/lib/practice";
import type { PracticeSession, PracticeTarget } from "@/lib/types";

const section: PracticeTarget = { segment_id: "s1", title: "Section 2", start: 6.917, end: 14 };

describe("recorder format", () => {
  it("prefers VP9 WebM, falls back to MP4 (Safari), or null when nothing records", () => {
    expect(pickRecorderType(() => true)).toBe("video/webm;codecs=vp9");
    expect(pickRecorderType((t) => t.startsWith("video/mp4"))).toBe("video/mp4;codecs=avc1");
    expect(pickRecorderType(() => false)).toBeNull();
    expect(
      pickRecorderType(() => {
        throw new Error("unknown");
      }),
    ).toBeNull();
  });
  it("names files by container", () => {
    expect(extensionFor("video/webm;codecs=vp9")).toBe(".webm");
    expect(extensionFor("video/mp4;codecs=avc1")).toBe(".mp4");
  });
});

describe("recording limit", () => {
  it("is the practised length plus headroom, capped by the server limit", () => {
    expect(recordingLimit(section, 120)).toBe(Math.ceil(14 - 6.917 + AUTO_STOP_PADDING_SECONDS));
    expect(recordingLimit({ ...section, start: 0, end: 118 }, 120)).toBe(120);
    expect(recordingLimit({ ...section, start: 3, end: 3 }, 120)).toBe(1 + AUTO_STOP_PADDING_SECONDS);
  });
  it("formats a clock", () => {
    expect(formatClock(0)).toBe("0:00");
    expect(formatClock(9.9)).toBe("0:09");
    expect(formatClock(75)).toBe("1:15");
    expect(formatClock(-3)).toBe("0:00");
  });
});

describe("camera problems", () => {
  const named = (name: string) => Object.assign(new Error(name), { name });
  it("maps getUserMedia errors to actionable problems", () => {
    expect(cameraProblem(named("NotAllowedError"))).toBe("denied");
    expect(cameraProblem(named("NotFoundError"))).toBe("no_camera");
    expect(cameraProblem(named("OverconstrainedError"))).toBe("no_camera");
    expect(cameraProblem(named("NotReadableError"))).toBe("in_use");
    expect(cameraProblem(new TypeError("x"))).toBe("unsupported");
    expect(cameraProblem({ name: "NotAllowedError" })).toBe("denied");
    expect(cameraProblem("weird")).toBe("failed");
    expect(cameraProblem(named("NotAllowedError"), false)).toBe("insecure");
  });
});

describe("side-by-side sync", () => {
  it("maps learner time onto the practised part of the reference", () => {
    expect(referenceTimeFor(section, 0)).toBeCloseTo(6.917);
    expect(referenceTimeFor(section, 2)).toBeCloseTo(8.917);
    expect(referenceTimeFor(section, 99)).toBe(14);
    expect(referenceTimeFor(section, -1)).toBeCloseTo(6.917);
  });
  it("plays in step for the shorter of the two", () => {
    expect(reviewLength(section, 9)).toBeCloseTo(7.083);
    expect(reviewLength(section, 4)).toBe(4);
    expect(reviewLength(section, null)).toBeCloseTo(7.083);
  });
  it("re-seeks the follower only beyond the tolerance", () => {
    expect(needsResync(5, 5.05)).toBe(false);
    expect(needsResync(5, 5.2)).toBe(true);
  });
});

describe("status labels", () => {
  it("never calls tracking a score", () => {
    const base = { status: "analyzed" } as PracticeSession;
    expect(practiceStatusLabel(base)).toBe("Pose measured");
    expect(practiceStatusLabel({ ...base, status: "failed" })).toBe("Needs a re-record");
    expect(practiceStatusLabel({ ...base, status: "uploaded" })).toBe("Stored");
  });
});

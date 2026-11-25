import { describe, expect, it } from "vitest";

import {
  type DraftSection,
  formatClock,
  isTiled,
  loopAction,
  mergeWithNext,
  moveBoundary,
  sectionIndexAt,
  snap,
  splitAt,
  toEdits,
} from "@/lib/sections";

const D = 14;
const base = (): DraftSection[] => [
  { id: "a", start: 0, end: 5, title: "Section 01", completed: true },
  { id: "b", start: 5, end: 9.5, title: "Arms", completed: false },
  { id: "c", start: 9.5, end: D, title: "Section 03", completed: false },
];

describe("section edits keep full coverage", () => {
  it("splits at the playhead, snapped to the 24 fps grid, and renumbers auto titles", () => {
    const r = splitAt(base(), 2.51, 0.5);
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.draft.map((s) => [s.start, s.end])).toEqual([
      [0, snap(2.51)],
      [snap(2.51), 5],
      [5, 9.5],
      [9.5, D],
    ]);
    expect(r.draft.map((s) => s.title)).toEqual(["Section 01", "Section 02", "Arms", "Section 04"]);
    expect(r.draft[0].completed).toBe(false);
    expect(r.draft[1].id).toBeUndefined();
    expect(isTiled(r.draft, D)).toBe(true);
  });

  it("refuses a split that would create a too-short part", () => {
    const r = splitAt(base(), 5.2, 0.5);
    expect(r.ok).toBe(false);
  });

  it("merges with the next section keeping the first id", () => {
    const r = mergeWithNext(base(), 1);
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.draft.map((s) => [s.id, s.start, s.end])).toEqual([
      ["a", 0, 5],
      ["b", 5, D],
    ]);
    expect(mergeWithNext(base(), 2).ok).toBe(false);
  });

  it("moves a boundary, clamped to the minimum length on both sides", () => {
    const moved = moveBoundary(base(), 0, 7, 0.5);
    expect(moved[0].end).toBe(7);
    expect(moved[1].start).toBe(7);
    expect(isTiled(moved, D)).toBe(true);
    const clamped = moveBoundary(base(), 0, 100, 0.5);
    expect(clamped[0].end).toBeLessThanOrEqual(9.0);
    expect(clamped[1].end - clamped[1].start).toBeGreaterThanOrEqual(0.5);
    const low = moveBoundary(base(), 0, -3, 0.5);
    expect(low[0].end).toBeGreaterThanOrEqual(0.5);
    expect(isTiled(low, D)).toBe(true);
  });

  it("detects gaps, overlaps and incomplete coverage", () => {
    expect(isTiled(base(), D)).toBe(true);
    const gap = base();
    gap[1] = { ...gap[1], start: 5.5 };
    expect(isTiled(gap, D)).toBe(false);
    expect(isTiled(base().slice(0, 2), D)).toBe(false);
    expect(isTiled([], D)).toBe(false);
  });

  it("sends ids and only custom titles to the server", () => {
    expect(toEdits(base())).toEqual([
      { id: "a", start: 0, end: 5, title: null },
      { id: "b", start: 5, end: 9.5, title: "Arms" },
      { id: "c", start: 9.5, end: D, title: null },
    ]);
  });

  it("finds the section under the playhead", () => {
    expect(sectionIndexAt(base(), 0)).toBe(0);
    expect(sectionIndexAt(base(), 5)).toBe(1);
    expect(sectionIndexAt(base(), D)).toBe(2);
    expect(sectionIndexAt([], 1)).toBe(-1);
  });
});

describe("section loop rule", () => {
  const sec = { start: 5, end: 9.5 };
  it("seeks back to the start about one frame before the end when looping", () => {
    expect(loopAction(7, sec, true)).toEqual({ kind: "none" });
    expect(loopAction(9.47, sec, true)).toEqual({ kind: "seek", to: 5 });
    expect(loopAction(9.6, sec, true)).toEqual({ kind: "seek", to: 5 });
  });
  it("stops at the end when not looping", () => {
    const a = loopAction(9.49, sec, false);
    expect(a.kind).toBe("stop");
  });
  it("pulls a stray playhead back into the looped section", () => {
    expect(loopAction(1, sec, true)).toEqual({ kind: "seek", to: 5 });
    expect(loopAction(1, sec, false)).toEqual({ kind: "none" });
  });
  it("formats clock times", () => {
    expect(formatClock(0)).toBe("0:00.0");
    expect(formatClock(65.25)).toBe("1:05.3");
  });
});

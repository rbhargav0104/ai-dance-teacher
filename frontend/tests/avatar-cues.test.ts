import { describe, expect, it } from "vitest";

import { NO_CUE, countAt, countIn, cueIndexAt, sectionCues } from "@/lib/avatar/cues";
import type { SectionFact } from "@/lib/types";

const fact = (mirror: string, direct: string): SectionFact => ({ kind: "arm_above_shoulder", side: "left", value: null, mirror, direct });

const base = { start: 2, end: 6, instruction: "Fallback one. Fallback two.", instruction_direct: "Direct one.", facts: [] as SectionFact[] };

describe("sectionCues", () => {
  it("uses measured facts in the viewing perspective, spread evenly over the section", () => {
    const s = { ...base, facts: [fact("left arm goes above your shoulder", "right arm goes above your shoulder"), fact("travel to your left", "travel to your right")] };
    const m = sectionCues(s, true);
    expect(m.map((c) => c.text)).toEqual(["Left arm goes above your shoulder.", "Travel to your left."]);
    expect(m.map((c) => [c.start, c.end])).toEqual([[2, 4], [4, 6]]);
    expect(sectionCues(s, false)[0].text).toBe("Right arm goes above your shoulder.");
  });

  it("falls back to the stored instruction, then to an honest 'no cue'", () => {
    expect(sectionCues(base, true).map((c) => c.text)).toEqual(["Fallback one.", "Fallback two."]);
    expect(sectionCues(base, false).map((c) => c.text)).toEqual(["Direct one."]);
    expect(sectionCues({ ...base, instruction: null, instruction_direct: null }, true)[0].text).toBe(NO_CUE);
  });

  it("finds the active caption, including the very end", () => {
    const cues = sectionCues({ ...base, facts: [fact("a", "a"), fact("b", "b")] }, true);
    expect(cueIndexAt(cues, 1.9)).toBe(-1);
    expect(cueIndexAt(cues, 2)).toBe(0);
    expect(cueIndexAt(cues, 4.01)).toBe(1);
    expect(cueIndexAt(cues, 6)).toBe(1);
  });
});

describe("counts", () => {
  it("even 8-count across the section", () => {
    const s = { start: 0, end: 8 };
    expect(countAt(s, 0)).toBe(1);
    expect(countAt(s, 3.5)).toBe(4);
    expect(countAt(s, 8)).toBe(8);
    expect(countAt(s, 9)).toBeNull();
  });

  it("count-in follows the section beat and playback speed, clamped to a speakable range", () => {
    expect(countIn({ start: 0, end: 6.4 }, 1)).toEqual({ words: ["5", "6", "7", "8"], beatMs: 800 });
    expect(countIn({ start: 0, end: 6.4 }, 0.25).beatMs).toBe(1200);
    expect(countIn({ start: 0, end: 2 }, 1).beatMs).toBe(450);
  });
});

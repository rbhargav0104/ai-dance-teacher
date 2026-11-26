/**
 * Coach cues for Teacher Mode (spec amendment A1). Pure helpers; speech lives in the component.
 *
 * Cue wording comes only from the section's measured facts (backend `pose/instructions.py`),
 * in the perspective the learner is viewing (mirror or direct). Timing uses an even 8-count
 * over the section — the music's tempo isn't measured yet (Outcome 7), and the UI says so.
 */

import type { Section } from "../types";

export interface Cue {
  /** Media-time window [start, end) in which this caption is shown / spoken. */
  start: number;
  end: number;
  text: string;
}

export const NO_CUE = "No measured cue for this section. Watch the avatar and the video.";

/** Caption lines for a section, in the chosen perspective, spread evenly across the section. */
export function sectionCues(section: Pick<Section, "start" | "end" | "facts" | "instruction" | "instruction_direct">, mirror: boolean): Cue[] {
  const fromFacts = section.facts.map((f) => (mirror ? f.mirror : f.direct)).filter((s) => s && s.trim().length > 0);
  let lines = fromFacts;
  if (lines.length === 0) {
    const text = mirror ? section.instruction : (section.instruction_direct ?? section.instruction);
    lines = text ? text.split(/(?<=[.!?])\s+/).filter(Boolean) : [];
  }
  if (lines.length === 0) lines = [NO_CUE];
  const dur = Math.max(0, section.end - section.start);
  const n = lines.length;
  return lines.map((text, i) => ({
    text: tidy(text),
    start: section.start + (dur * i) / n,
    end: i === n - 1 ? section.end : section.start + (dur * (i + 1)) / n,
  }));
}

function tidy(s: string): string {
  const t = s.trim();
  const capital = t.charAt(0).toUpperCase() + t.slice(1);
  return /[.!?]$/.test(capital) ? capital : `${capital}.`;
}

/** Caption index active at media time `t`, or -1 outside the section. */
export function cueIndexAt(cues: Cue[], t: number): number {
  for (let i = 0; i < cues.length; i++) if (t >= cues[i].start && t < cues[i].end) return i;
  if (cues.length && Math.abs(t - cues[cues.length - 1].end) < 1e-6) return cues.length - 1;
  return -1;
}

/** Beat 1..8 of an even 8-count across the section at media time `t` (null outside). */
export function countAt(section: { start: number; end: number }, t: number): number | null {
  const dur = section.end - section.start;
  if (dur <= 0 || t < section.start || t > section.end) return null;
  return Math.min(8, Math.floor(((t - section.start) / dur) * 8) + 1);
}

/**
 * Count-in before the section plays: "5, 6, 7, 8" at the section's even-8 beat, slowed by the
 * playback speed so it matches what the learner will see. Clamped to a speakable range.
 */
export function countIn(section: { start: number; end: number }, speed: number): { words: string[]; beatMs: number } {
  const beat = (section.end - section.start) / 8 / Math.max(0.1, speed);
  const beatMs = Math.round(Math.min(1.2, Math.max(0.45, beat)) * 1000);
  return { words: ["5", "6", "7", "8"], beatMs };
}

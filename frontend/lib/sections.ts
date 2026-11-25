/**
 * Pure section-timeline logic: boundary editing that always keeps full coverage (no gaps or
 * overlaps), and the section loop rule used by the player. Server-side validation is the
 * authority (PATCH /segments); these helpers keep the UI from ever proposing an invalid list.
 */
import type { Section, SectionEdit } from "./types";

export interface DraftSection {
  id?: string;
  start: number;
  end: number;
  title: string;
  completed: boolean;
}

/** Canonical playback copy is 24 fps; boundaries snap to its frame grid. */
export const FRAME = 1 / 24;

export const snap = (t: number) => Math.round(Math.round(t / FRAME) * FRAME * 1000) / 1000;

export function toDraft(sections: Section[]): DraftSection[] {
  return sections.map((s) => ({ id: s.id, start: s.start, end: s.end, title: s.title, completed: s.completed }));
}

const AUTO_TITLE = /^Section \d{2}$/;

/** Re-number automatic titles after positions change; custom titles are kept. */
function renumber(d: DraftSection[]): DraftSection[] {
  return d.map((s, i) => (AUTO_TITLE.test(s.title) ? { ...s, title: `Section ${String(i + 1).padStart(2, "0")}` } : s));
}

export function sectionIndexAt(d: { start: number; end: number }[], t: number): number {
  if (d.length === 0) return -1;
  for (let i = 0; i < d.length; i++) {
    if (t < d[i].end) return i;
  }
  return d.length - 1;
}

export type EditResult = { ok: true; draft: DraftSection[] } | { ok: false; reason: string };

export function splitAt(d: DraftSection[], t: number, minLen: number): EditResult {
  const i = sectionIndexAt(d, t);
  if (i < 0) return { ok: false, reason: "No sections yet." };
  const at = snap(t);
  const s = d[i];
  if (at - s.start < minLen - 1e-6 || s.end - at < minLen - 1e-6) {
    return { ok: false, reason: `Each part must be at least ${minLen} s long — move the playhead further in.` };
  }
  const next = [
    ...d.slice(0, i),
    { ...s, end: at, completed: false },
    { start: at, end: s.end, title: "Section 00", completed: false },
    ...d.slice(i + 1),
  ];
  return { ok: true, draft: renumber(next) };
}

export function mergeWithNext(d: DraftSection[], i: number): EditResult {
  if (i < 0 || i >= d.length - 1) return { ok: false, reason: "There is no next section to merge with." };
  const merged = { ...d[i], end: d[i + 1].end, completed: false };
  return { ok: true, draft: renumber([...d.slice(0, i), merged, ...d.slice(i + 2)]) };
}

/** Move the boundary between section `i` and `i + 1`, clamped so neither gets shorter than minLen. */
export function moveBoundary(d: DraftSection[], i: number, t: number, minLen: number): DraftSection[] {
  if (i < 0 || i >= d.length - 1) return d;
  const lo = d[i].start + minLen;
  const hi = d[i + 1].end - minLen;
  if (hi < lo) return d;
  let at = snap(Math.min(hi, Math.max(lo, t)));
  if (at < lo) at = Math.ceil(lo * 1000) / 1000;
  if (at > hi) at = Math.floor(hi * 1000) / 1000;
  if (at === d[i].end) return d;
  const out = d.slice();
  out[i] = { ...d[i], end: at, completed: false };
  out[i + 1] = { ...d[i + 1], start: at, completed: false };
  return out;
}

export function isTiled(d: { start: number; end: number }[], duration: number, tol = 0.01): boolean {
  if (d.length === 0) return false;
  if (Math.abs(d[0].start) > tol || Math.abs(d[d.length - 1].end - duration) > tol) return false;
  return d.every((s, i) => s.end > s.start && (i === 0 || s.start === d[i - 1].end));
}

export function sameBoundaries(a: { start: number; end: number }[], b: { start: number; end: number }[]): boolean {
  return a.length === b.length && a.every((s, i) => s.start === b[i].start && s.end === b[i].end);
}

export function toEdits(d: DraftSection[]): SectionEdit[] {
  return d.map((s) => ({
    ...(s.id ? { id: s.id } : {}),
    start: s.start,
    end: s.end,
    title: AUTO_TITLE.test(s.title) ? null : s.title,
  }));
}

export type LoopAction = { kind: "none" } | { kind: "seek"; to: number } | { kind: "stop"; at: number };

/**
 * Decide what the player does at playback time `t` inside section [start, end).
 * `lookahead` is how early to act (about one video frame) so a loop never shows a frame of
 * the next section.
 */
export function loopAction(
  t: number,
  section: { start: number; end: number },
  loop: boolean,
  lookahead = FRAME,
): LoopAction {
  if (t < section.start - 0.25) return loop ? { kind: "seek", to: section.start } : { kind: "none" };
  if (t >= section.end - lookahead) {
    return loop ? { kind: "seek", to: section.start } : { kind: "stop", at: Math.max(section.start, section.end - lookahead) };
  }
  return { kind: "none" };
}

export function formatClock(t: number): string {
  const s = Math.max(0, t);
  const m = Math.floor(s / 60);
  const sec = s - m * 60;
  return `${m}:${sec.toFixed(1).padStart(4, "0")}`;
}

export const SPEEDS = [0.25, 0.5, 0.75, 1] as const;
export type Speed = (typeof SPEEDS)[number];

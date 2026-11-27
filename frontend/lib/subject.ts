// Helpers for "Who should we follow?" (spec amendment A2). Pure, unit-tested.
import type { CSSProperties } from "react";

import type { SubjectCandidate, SubjectInfo } from "./types";

export const personLabel = (c: Pick<SubjectCandidate, "person" | "position">) => `person ${c.person} (${c.position})`;

/** Box padded by `pad` of its own size on each side, clipped to the frame. */
export function padBox(box: readonly [number, number, number, number], pad = 0.08): [number, number, number, number] {
  const [x0, y0, x1, y1] = box;
  const px = (x1 - x0) * pad;
  const py = (y1 - y0) * pad;
  const c = (v: number) => Math.min(1, Math.max(0, v));
  return [c(x0 - px), c(y0 - py), c(x1 + px), c(y1 + py)];
}

/**
 * Crop window (fractions of the frame) of a fixed pixel aspect `cropAspect` (w/h) that contains
 * the padded box, centred on it and kept inside the frame. Same aspect for every person, so the
 * thumbnails line up.
 */
export function cropWindow(
  box: readonly [number, number, number, number],
  frameAspect: number,
  cropAspect = 3 / 4,
): [number, number, number, number] {
  const [x0, y0, x1, y1] = padBox(box);
  const bw = Math.max(1e-3, x1 - x0);
  const bh = Math.max(1e-3, y1 - y0);
  // In frame fractions, a crop of aspect A has cw * frameAspect / ch = A.
  let ch = Math.max(bh, (bw * frameAspect) / cropAspect);
  let cw = (ch * cropAspect) / frameAspect;
  if (ch > 1) {
    ch = 1;
    cw = cropAspect / frameAspect;
  }
  if (cw > 1) {
    cw = 1;
    ch = frameAspect / cropAspect;
  }
  const place = (centre: number, size: number) => Math.min(1 - size, Math.max(0, centre - size / 2));
  const cx = place((x0 + x1) / 2, cw);
  const cy = place((y0 + y1) / 2, ch);
  return [cx, cy, cx + cw, cy + ch];
}

/** CSS that shows one person's crop window of the frame image as a 3:4 thumbnail. */
export function cropStyle(box: readonly [number, number, number, number], frameAspect: number, src: string): CSSProperties {
  const [x0, y0, x1, y1] = cropWindow(box, frameAspect);
  const bw = x1 - x0;
  const bh = y1 - y0;
  const pos = (start: number, size: number) => (size >= 0.999 ? 0 : (start / (1 - size)) * 100);
  return {
    aspectRatio: "3 / 4",
    backgroundImage: `url("${src}")`,
    backgroundSize: `${100 / bw}% ${100 / bh}%`,
    backgroundPosition: `${pos(x0, bw)}% ${pos(y0, bh)}%`,
  };
}

/** One-line description of whom the analysis follows, or null for single-person videos. */
export function followingSummary(subject: SubjectInfo | null | undefined): string | null {
  if (!subject?.choice) return null;
  const who = `Following ${personLabel(subject.choice)}`;
  const f = subject.followed;
  if (!f) return who;
  const gaps = f.lost_spans.length + f.uncertain_spans.length;
  if (gaps === 0) return `${who} for the whole video.`;
  return `${who}. Lost them in ${gaps} ${gaps === 1 ? "passage" : "passages"}; those moments are left out.`;
}

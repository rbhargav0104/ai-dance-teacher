// Pure helpers for the attempt ↔ reference alignment (Outcome 6). Everything here reads the
// backend's measured alignment; nothing is estimated, smoothed over or scored in the browser.

import type { Alignment, AlignmentFrame } from "./types";

export const ALIGNMENT_STATUS_TEXT: Record<string, string> = {
  aligned: "Moves paired",
  insufficient_reference: "Reference not trackable here",
  insufficient_tracking: "Not enough of you was tracked",
  out_of_band: "Timing too far off to pair",
};

/** Matched pairs, learner time ascending (ties keep reference order). */
function pairs(frames: AlignmentFrame[]): { l: number; r: number }[] {
  return frames
    .map((f, i) => ({ l: f.learner_t, r: f.ref_src_t, i }))
    .sort((a, b) => a.l - b.l || a.i - b.i)
    .map(({ l, r }) => ({ l, r }));
}

/**
 * Reference-video time to show while the learner video is at `learnerT` (seconds from the
 * attempt's start), following the alignment path. Before the first paired frame the reference
 * waits at its start, after the last it holds its end; in between it interpolates linearly.
 * When one learner frame was paired with several reference frames (the learner held a pose),
 * the reference shows the first of them, so it never jumps ahead of the learner.
 * Returns null without an alignment path.
 */
export function referenceTimeAt(alignment: Alignment | null | undefined, learnerT: number): number | null {
  const frames = alignment?.frames;
  if (!frames || frames.length === 0) return null;
  const p = pairs(frames);
  if (learnerT <= p[0].l) return p[0].r;
  const last = p[p.length - 1];
  if (learnerT >= last.l) return last.r;
  // First pair at/after learnerT.
  let hi = 0;
  while (hi < p.length && p[hi].l < learnerT) hi++;
  const b = p[hi];
  // Earliest pair sharing b's learner time (held pose → first reference frame).
  let first = hi;
  while (first > 0 && p[first - 1].l === b.l) first--;
  const a = p[first - 1];
  const bFirst = p[first];
  if (bFirst.l === a.l) return bFirst.r;
  const f = (learnerT - a.l) / (bFirst.l - a.l);
  return a.r + f * (bFirst.r - a.r);
}

export type CostTone = "good" | "fair" | "off" | "masked";

/** Display buckets for a per-pair movement distance (debug view colouring only). */
export function costTone(cost: number | null): CostTone {
  if (cost === null || !Number.isFinite(cost)) return "masked";
  if (cost < 0.2) return "good";
  if (cost < 0.45) return "fair";
  return "off";
}

function seconds(s: number): string {
  return `${Math.abs(s).toFixed(1)} s`;
}

/**
 * Plain-language timing facts measured by the alignment (never a judgement or a score).
 * Small differences (under 0.15 s or 5 %) are not mentioned.
 */
export function timingFacts(alignment: Alignment): string[] {
  const out: string[] = [];
  if (alignment.status !== "aligned" || !alignment.timing) return out;
  const { median_offset_s: off, speed_ratio: ratio } = alignment.timing;
  if (off !== null && Math.abs(off) >= 0.15) {
    out.push(off > 0 ? `You were about ${seconds(off)} behind the reference.` : `You were about ${seconds(off)} ahead of the reference.`);
  }
  if (ratio !== null && Math.abs(ratio - 1) >= 0.05) {
    const pct = Math.round(Math.abs(ratio - 1) * 100);
    out.push(ratio > 1 ? `Your pace was about ${pct}% slower than the reference.` : `Your pace was about ${pct}% faster than the reference.`);
  }
  if (alignment.mirror?.chosen === "mirrored") {
    out.push(
      alignment.mirror.decision === "clear"
        ? "Your movement matches the dancer's as a mirror image (left ↔ right), so sides were compared mirrored."
        : "Compared mirrored, as the video was marked as mirrored.",
    );
  }
  const early = alignment.warp?.attempt_ended_early_s ?? 0;
  if (early >= 0.5) out.push(`Your recording ended about ${seconds(early)} before the reference passage did.`);
  const missing = alignment.missing_spans ?? [];
  if (missing.length) {
    out.push(
      `The reference moves where you were still or clearly different: ${missing.map(([a, b]) => `${a.toFixed(1)}–${b.toFixed(1)} s`).join(", ")}.`,
    );
  }
  const masked = alignment.masked_spans ?? [];
  if (masked.length) {
    out.push(`Not measurable on both videos (left out, not counted as wrong): ${masked.map(([a, b]) => `${a.toFixed(1)}–${b.toFixed(1)} s`).join(", ")}.`);
  }
  return out;
}

/** SVG polyline points for the path chart (x = reference window time, y = learner time). */
export function pathPoints(frames: AlignmentFrame[], width: number, height: number, xMax: number, yMax: number): string {
  if (!frames.length || xMax <= 0 || yMax <= 0) return "";
  return frames
    .map((f) => `${((f.ref_t / xMax) * width).toFixed(1)},${(height - (f.learner_t / yMax) * height).toFixed(1)}`)
    .join(" ");
}

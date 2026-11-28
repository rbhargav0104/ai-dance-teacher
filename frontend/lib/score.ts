// Pure helpers for the versioned score report (Outcome 7). Everything here only words or
// formats what the backend measured — no number is computed, smoothed or invented here.

import type { ComponentKey, ScoreReport, SectionScore } from "./types";

export const COMPONENTS: { key: ComponentKey; label: string; blurb: string }[] = [
  { key: "pose", label: "Pose accuracy", blurb: "Body shape at each matched move, size and position removed." },
  { key: "timing", label: "Timing", blurb: "How early or late each matched move happened, on the original clock." },
  { key: "sequence", label: "Sequence", blurb: "Share of the reference's moves you matched, in order and direction." },
  { key: "joint_angles", label: "Joint angles", blurb: "Elbow, shoulder, hip and knee angles you and the dancer both showed." },
  { key: "rhythm", label: "Rhythm", blurb: "Motion accents and pace against the reference (experimental)." },
];

export const BODY_PART_LABEL: Record<string, string> = {
  left_arm: "left arm",
  right_arm: "right arm",
  torso: "torso",
  left_leg: "left leg",
  right_leg: "right leg",
};

export const SCORE_WARNINGS: Record<string, string> = {
  compared_mirrored: "You were compared as a mirror image of the dancer (sides are named as the dancer's).",
  sides_ambiguous: "This passage looks alike mirrored or not, so sides were kept as recorded.",
  untracked_moments_skipped: "Moments where either body wasn't tracked were skipped, not counted as mistakes.",
  attempt_ended_early: "Your recording stopped before the reference passage ended.",
  reference_hides_some_body_parts: "The reference video doesn't show some body parts, so they aren't scored.",
  some_body_parts_untracked: "Some of your body parts weren't tracked well enough to score.",
};

export const QUALIFIER_TEXT: Record<string, string> = {
  low_confidence: "tracking or alignment was uncertain",
  partial_body_visible: "only part of your body was visible",
  many_untracked_moments: "many moments couldn't be measured",
};

export const RHYTHM_UNAVAILABLE: Record<string, string> = {
  too_short: "Too short to judge rhythm — the other parts were re-weighted.",
  too_few_pairs: "Too few compared moments to judge rhythm — re-weighted.",
  no_clear_accents: "The reference has no clear motion accents to compare — re-weighted.",
};

export type ScoreTone = "lime" | "track" | "amber" | "danger";

export function scoreTone(v: number | null | undefined): ScoreTone {
  if (v == null) return "amber";
  if (v >= 85) return "lime";
  if (v >= 70) return "track";
  if (v >= 50) return "amber";
  return "danger";
}

/** Whole-number display; null → em dash. Never rounds a missing value to 0. */
export function scoreText(v: number | null | undefined): string {
  return v == null || !Number.isFinite(v) ? "—" : String(Math.round(v));
}

export function hasNumbers(r: ScoreReport): boolean {
  return (r.status === "scored" || r.status === "qualified") && r.overall != null;
}

const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);
const secs = (v: number) => `${Math.abs(v).toFixed(2)} s`;

/** One measured sentence per component (what the number was computed from). */
export function evidenceText(r: ScoreReport, key: ComponentKey): string | null {
  const ev = r.evidence;
  if (!ev) return null;
  switch (key) {
    case "pose": {
      const e = ev.pose;
      if (!e || e.mean_joint_distance_torso == null) return null;
      const lean = e.mean_lean_difference_deg != null ? ` · lean differed ${Math.round(e.mean_lean_difference_deg)}°` : "";
      return `Joints sat ${pct(e.mean_joint_distance_torso)} of a torso length from the dancer's on average${lean} (${e.pairs} moments).`;
    }
    case "timing": {
      const e = ev.timing;
      if (!e || e.median_offset_s == null) return null;
      const off = e.median_offset_s;
      const when = Math.abs(off) <= e.tolerance_s ? "on time" : off > 0 ? `${secs(off)} late` : `${secs(off)} early`;
      return `Typical move ${when}; ${pct(e.on_time_share)} of moves within ${e.tolerance_s.toFixed(2)} s.`;
    }
    case "sequence": {
      const e = ev.sequence;
      if (!e || e.matched_share == null) return null;
      const missed = e.missing_share ? ` · ${pct(e.missing_share)} missed` : "";
      const held = e.held_share ? ` · ${pct(e.held_share)} held/ended early` : "";
      return `${pct(e.matched_share)} of the reference's measured moves matched${missed}${held}.`;
    }
    case "joint_angles": {
      const e = ev.joint_angles;
      if (!e || e.focused_angle_error_deg == null) return null;
      return `Angles off by about ${Math.round(e.focused_angle_error_deg)}° (weighted toward the two worst joints).`;
    }
    case "rhythm": {
      const e = ev.rhythm;
      if (!e) return null;
      if (e.unavailable) return RHYTHM_UNAVAILABLE[e.unavailable] ?? "Rhythm unavailable — re-weighted.";
      const pace = e.pace_ratio != null ? `You took ${e.pace_ratio.toFixed(2)}× the reference's time` : "";
      const corr = e.envelope_correlation != null ? ` · accents correlate ${e.envelope_correlation.toFixed(2)}` : "";
      return `${pace}${corr}. Body motion only, no audio beat.`;
    }
  }
}

/** "Scored at 30 % → 33 %" style weight note for a component (product weights re-normalised). */
export function weightText(r: ScoreReport, key: ComponentKey): string {
  if (!hasNumbers(r)) return "withheld";
  const used = r.weights_used?.[key];
  if (used == null) return "not counted";
  return `${Math.round(used * 100)}% of overall`;
}

export function statusHeadline(r: ScoreReport): string {
  if (r.status === "scored") return "Your dance score";
  if (r.status === "qualified") return "Your dance score · low confidence";
  if (r.status === "suppressed") return "No fair score for this attempt";
  return "This attempt couldn't be scored";
}

export function qualifierText(r: ScoreReport): string | null {
  const q = (r.qualifiers ?? []).map((k) => QUALIFIER_TEXT[k]).filter(Boolean);
  return q.length ? `Treat this number loosely: ${q.join(", ")}.` : null;
}

/** Strongest and weakest scored sections (ties → earlier section); null with < 2 scored. */
export function sectionExtremes(sections: SectionScore[] | undefined): { strongest: SectionScore; weakest: SectionScore } | null {
  const scored = (sections ?? []).filter((s) => s.status === "scored" && s.overall != null);
  if (scored.length < 2) return null;
  let strongest = scored[0];
  let weakest = scored[0];
  for (const s of scored) {
    if ((s.overall ?? 0) > (strongest.overall ?? 0)) strongest = s;
    if ((s.overall ?? 0) < (weakest.overall ?? 0)) weakest = s;
  }
  if (strongest === weakest) return null;
  return { strongest, weakest };
}

export function partsText(parts: string[]): string {
  const names = parts.map((p) => BODY_PART_LABEL[p] ?? p.replace(/_/g, " "));
  return names.length ? names.join(" and ") : "whole body";
}

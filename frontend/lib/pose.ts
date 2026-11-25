// Pure helpers for drawing measured poses over video. No pose data is ever invented here:
// frames without a measured landmark draw nothing for that landmark.

import type { PoseFrame } from "./types";

/** Index of the analysed frame nearest to `t` (seconds); -1 when there are no frames. */
export function nearestFrameIndex(frames: { t: number }[], t: number): number {
  if (frames.length === 0) return -1;
  let lo = 0;
  let hi = frames.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (frames[mid].t < t) lo = mid + 1;
    else hi = mid;
  }
  if (lo > 0 && Math.abs(frames[lo - 1].t - t) <= Math.abs(frames[lo].t - t)) return lo - 1;
  return lo;
}

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Where a `mediaW×mediaH` video is drawn inside a `boxW×boxH` element with object-fit: contain. */
export function containRect(boxW: number, boxH: number, mediaW: number, mediaH: number): Rect {
  if (boxW <= 0 || boxH <= 0 || mediaW <= 0 || mediaH <= 0) return { x: 0, y: 0, width: 0, height: 0 };
  const scale = Math.min(boxW / mediaW, boxH / mediaH);
  const width = mediaW * scale;
  const height = mediaH * scale;
  return { x: (boxW - width) / 2, y: (boxH - height) / 2, width, height };
}

/** Image-normalized landmark → pixel position inside the drawn video rectangle. */
export function toScreen(rect: Rect, x: number, y: number): [number, number] {
  return [rect.x + x * rect.width, rect.y + y * rect.height];
}

export type JointState = "measured" | "bridged" | "hidden";

/** Measured → draw solid; bridged (short gap, interpolated) → draw faint; hidden → never draw. */
export function jointState(frame: PoseFrame, j: number): JointState {
  const p = frame.data.smoothed[j];
  if (!p) return "hidden";
  if (frame.data.reliable[j]) return "measured";
  if (frame.data.interpolated[j]) return "bridged";
  return "hidden";
}

/** Analysed frames are spaced 1/analysisFps apart; only use a frame within half a step. */
export function frameAt(frames: PoseFrame[], t: number, analysisFps: number): PoseFrame | null {
  const i = nearestFrameIndex(frames, t);
  if (i < 0) return null;
  const half = 0.5 / Math.max(1, analysisFps) + 1e-3;
  return Math.abs(frames[i].t - t) <= half ? frames[i] : null;
}

export function percent(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

export function degrees(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${Math.round(v)}°`;
}

/** Stage → user-facing label for the analysis progress UI. */
export function stageLabel(stage: string | null | undefined): string {
  switch (stage) {
    case "queued":
      return "Waiting for the analysis worker";
    case "preparing":
      return "Preparing a steady 24 fps copy";
    case "tracking":
      return "Tracking the body frame by frame";
    case "saving":
      return "Saving landmarks and measurements";
    default:
      return "Working";
  }
}

export const FAILURE_HELP: Record<string, string> = {
  multiple_people: "Trim or crop the video so only one dancer is visible, then upload it again.",
  low_coverage: "Record again with your whole body in frame, steady light and nothing blocking the view.",
  no_dancer_detected: "Use a clip where one person's shoulders and hips are clearly visible.",
  interrupted: "The analysis stopped part-way. Try again — nothing was lost.",
  analysis_crashed: "Something went wrong on our side. Try again.",
  analysis_unavailable: "Movement analysis isn't available on this server right now.",
};

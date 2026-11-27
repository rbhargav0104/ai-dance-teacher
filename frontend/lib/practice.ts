// Pure helpers for learner capture (spec 16, Journey D). No pose data or scores live here:
// this is recording mechanics, timing and honest error wording only.

import type { PracticeSession, PracticeTarget } from "./types";

/** Preferred MediaRecorder formats, best first. Chrome/Firefox → WebM, Safari → MP4. */
export const RECORDER_TYPES = [
  "video/webm;codecs=vp9",
  "video/webm;codecs=vp8",
  "video/webm",
  "video/mp4;codecs=avc1",
  "video/mp4",
] as const;

export function pickRecorderType(isTypeSupported: (t: string) => boolean): string | null {
  for (const t of RECORDER_TYPES) {
    try {
      if (isTypeSupported(t)) return t;
    } catch {
      /* some browsers throw for unknown types */
    }
  }
  return null;
}

export function extensionFor(mime: string): ".webm" | ".mp4" {
  return mime.startsWith("video/mp4") ? ".mp4" : ".webm";
}

export const COUNTDOWN_SECONDS = 3;
/** Headroom after the target length before recording stops on its own. */
export const AUTO_STOP_PADDING_SECONDS = 3;

/** Auto-stop: the practised length plus a little headroom, never over the server limit. */
export function recordingLimit(target: PracticeTarget, maxDurationSeconds: number): number {
  const length = Math.max(1, target.end - target.start);
  return Math.min(maxDurationSeconds, Math.ceil(length + AUTO_STOP_PADDING_SECONDS));
}

export function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export type CameraProblem = "denied" | "no_camera" | "in_use" | "insecure" | "unsupported" | "failed";

/** getUserMedia / MediaRecorder failure → a problem the UI can explain. */
export function cameraProblem(err: unknown, secure = true): CameraProblem {
  if (!secure) return "insecure";
  const name = err instanceof Error || (typeof err === "object" && err !== null && "name" in err)
    ? String((err as { name?: unknown }).name ?? "")
    : "";
  switch (name) {
    case "NotAllowedError":
    case "SecurityError":
    case "PermissionDeniedError":
      return "denied";
    case "NotFoundError":
    case "OverconstrainedError":
    case "DevicesNotFoundError":
      return "no_camera";
    case "NotReadableError":
    case "TrackStartError":
    case "AbortError":
      return "in_use";
    case "TypeError":
    case "NotSupportedError":
      return "unsupported";
    default:
      return "failed";
  }
}

export const CAMERA_HELP: Record<CameraProblem, { title: string; body: string }> = {
  denied: {
    title: "Camera access is blocked",
    body: "Allow the camera for this site in your browser's address bar (camera icon), then try again — or upload a video you've already recorded.",
  },
  no_camera: {
    title: "No camera found",
    body: "Connect a camera and try again, or upload a video of your attempt instead.",
  },
  in_use: {
    title: "The camera is busy",
    body: "Another app or tab may be using it. Close it and try again, or upload a video instead.",
  },
  insecure: {
    title: "Camera needs a secure page",
    body: "Browsers only allow cameras on https:// or localhost. Open the studio that way, or upload a video instead.",
  },
  unsupported: {
    title: "Recording isn't supported here",
    body: "This browser can't record video from the camera. Upload a video of your attempt instead.",
  },
  failed: {
    title: "The camera couldn't start",
    body: "Try again, or upload a video of your attempt instead.",
  },
};

/** Learner seconds → reference seconds when both start at the beginning of the target. */
export function referenceTimeFor(target: PracticeTarget, learnerSeconds: number): number {
  return Math.min(target.end, target.start + Math.max(0, learnerSeconds));
}

/** Length the side-by-side review can play in lock-step (the shorter of the two). */
export function reviewLength(target: PracticeTarget, learnerDuration: number | null): number {
  const ref = Math.max(0, target.end - target.start);
  if (learnerDuration === null || !Number.isFinite(learnerDuration)) return ref;
  return Math.max(0, Math.min(ref, learnerDuration));
}

/** Drift (s) beyond which the follower video is re-seeked to the leader. */
export const SYNC_TOLERANCE_SECONDS = 0.08;

export function needsResync(leaderSeconds: number, followerSeconds: number, tolerance = SYNC_TOLERANCE_SECONDS) {
  return Math.abs(leaderSeconds - followerSeconds) > tolerance;
}

export const isPracticeBusy = (p: PracticeSession) => p.status === "queued" || p.status === "processing";

export const PRACTICE_WARNINGS: Record<string, string> = {
  shorter_than_target: "This attempt is shorter than what it practises, so part of the dance isn't in it.",
  partial_coverage: "Part of your attempt couldn't be tracked; those moments will be left out of any comparison.",
  cropped_body: "Your feet were out of frame for most of the attempt; leg and footwork detail is limited.",
  low_tracking_confidence: "Tracking confidence was low; joint measurements may be noisy.",
  brief_extra_person: "Someone else appeared briefly; we followed you.",
  other_people_ignored: "Other people in the video are ignored; we follow the person you chose.",
  chosen_dancer_lost: "We lost the person you chose for part of the attempt; those moments are left out.",
  portrait: "Recorded in portrait.",
  low_frame_rate: "Low frame rate — fast moves may be missed.",
  low_resolution: "Low resolution — small joints may be less precise.",
  may_need_conversion_for_playback: "Converted for playback.",
};

export function practiceStatusLabel(p: PracticeSession): string {
  switch (p.status) {
    case "uploaded":
      return "Stored";
    case "queued":
      return "Queued";
    case "processing":
      return "Analysing";
    case "analyzed":
      return "Pose measured";
    case "needs_subject":
      return "Choose who to follow";
    case "failed":
      return "Needs a re-record";
    default:
      return p.status;
  }
}

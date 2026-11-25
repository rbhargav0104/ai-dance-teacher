// Pure helpers for the upload/preview UI. The server re-validates everything with FFprobe;
// these checks only save the user a pointless upload.

export const DEFAULT_EXTENSIONS = [".mp4", ".mov", ".webm"];

export interface UploadLimits {
  max_upload_mb: number;
  max_duration_seconds: number;
  accepted_extensions: string[];
}

export function extensionOf(name: string): string {
  const i = name.lastIndexOf(".");
  return i > 0 ? name.slice(i).toLowerCase() : "";
}

/** Returns a user-facing problem, or null if the file is worth sending to the server. */
export function precheckFile(file: { name: string; size: number }, limits: UploadLimits): string | null {
  const ext = extensionOf(file.name);
  const accepted = limits.accepted_extensions.length ? limits.accepted_extensions : DEFAULT_EXTENSIONS;
  if (!accepted.includes(ext)) {
    return `Choose an ${accepted.map((e) => e.slice(1).toUpperCase()).join(", ").replace(/, ([^,]*)$/, " or $1")} video.`;
  }
  if (file.size === 0) return "This file is empty.";
  if (file.size > limits.max_upload_mb * 1024 * 1024) {
    return `This video is ${formatBytes(file.size)}. The limit is ${limits.max_upload_mb} MB.`;
  }
  return null;
}

/** Duration problems we can spot from browser metadata (null when unknown or fine). */
export function precheckDuration(seconds: number | null, limits: UploadLimits): string | null {
  if (seconds === null || !Number.isFinite(seconds)) return null;
  if (seconds < 1) return "This video is shorter than 1 second.";
  if (seconds > limits.max_duration_seconds) {
    return `This video is ${formatDuration(seconds)} long. Trim it to ${formatDuration(limits.max_duration_seconds)} or less.`;
  }
  return null;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds * 10) / 10);
  const m = Math.floor(s / 60);
  const rest = s - m * 60;
  if (m === 0) return `${rest.toFixed(rest < 10 ? 1 : 0)} s`;
  return `${m}:${Math.floor(rest).toString().padStart(2, "0")}`;
}

const WARNINGS: Record<string, string> = {
  portrait: "Portrait video",
  low_frame_rate: "Low frame rate — fast moves may blur",
  low_resolution: "Low resolution — tracking may be less reliable",
  may_need_conversion_for_playback: "May need conversion before it plays in every browser",
  partial_coverage: "Part of the video couldn't be tracked — those moments are left out",
  cropped_body: "Feet are out of frame — leg and footwork detail is limited",
  low_tracking_confidence: "Tracking confidence is low — joint measurements may be noisy",
  brief_extra_person: "Another person appears briefly — we followed the main dancer",
};

export const warningLabel = (code: string) => WARNINGS[code] ?? code.replaceAll("_", " ");

/** Short status chip for a project, honest about what has (not) happened yet. */
export function projectStatusLabel(status: string): { label: string; tone: "lime" | "amber" | "danger" | "muted" } {
  switch (status) {
    case "uploaded":
      return { label: "Checked · waiting for analysis", tone: "muted" };
    case "queued":
      return { label: "Queued for analysis", tone: "amber" };
    case "processing":
      return { label: "Analyzing", tone: "amber" };
    case "analyzed":
      return { label: "Pose tracked", tone: "lime" };
    case "ready":
      return { label: "Ready to learn", tone: "lime" };
    case "failed":
      return { label: "Needs attention", tone: "danger" };
    default:
      return { label: status, tone: "muted" };
  }
}

export function newIdempotencyKey(): string {
  const c = globalThis.crypto;
  if (c && "randomUUID" in c) return `up-${c.randomUUID()}`;
  return `up-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

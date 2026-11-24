import type { HealthResponse } from "./types";

/** UI capability state. LOADING is shown until the first health check resolves (spec 25). */
export type StudioState = "LOADING" | "READY" | "LIMITED" | "OFFLINE";

export type HealthResult =
  | { kind: "pending" }
  | { kind: "ok"; health: HealthResponse }
  | { kind: "unreachable" };

export interface StudioView {
  state: StudioState;
  label: string;
  detail: string;
  canAnalyze: boolean;
  canUpload: boolean;
}

export function deriveStudioView(result: HealthResult): StudioView {
  if (result.kind === "pending") {
    return {
      state: "LOADING",
      label: "Connecting",
      detail: "Checking the studio…",
      canAnalyze: false,
      canUpload: false,
    };
  }
  if (result.kind === "unreachable" || result.health.status === "offline") {
    return {
      state: "OFFLINE",
      label: "Offline",
      detail:
        result.kind === "unreachable"
          ? "We can't reach the studio right now. Your work is safe — retry in a moment."
          : result.health.message,
      canAnalyze: false,
      canUpload: false,
    };
  }
  const { health } = result;
  if (health.status === "ready" && health.analysis.available) {
    return {
      state: "READY",
      label: "Studio ready",
      detail: "Movement analysis is available.",
      canAnalyze: true,
      canUpload: true,
    };
  }
  return {
    state: "LIMITED",
    label: "Limited",
    detail: health.analysis.reason ?? health.message,
    canAnalyze: false,
    canUpload: true,
  };
}

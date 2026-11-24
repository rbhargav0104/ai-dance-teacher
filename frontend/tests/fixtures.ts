import type { HealthResponse } from "@/lib/types";

export function health(overrides: Partial<HealthResponse> = {}): HealthResponse {
  return {
    status: "limited",
    message: "Movement analysis is still being built.",
    version: "0.1.0",
    app_env: "test",
    auth_mode: "local",
    storage_provider: "local",
    database: { ok: true, detail: "0001" },
    storage: { ok: true, detail: null },
    analysis: {
      available: false,
      pipeline_implemented: false,
      runtime_installed: true,
      runtime_version: "1.2.3",
      model_present: true,
      model_verified: true,
      model_version: "pose_landmarker_full@sha256:4eaa5eb7a983",
      reason: "Movement analysis is still being built.",
    },
    limits: { max_upload_mb: 200, max_duration_seconds: 120, accepted_extensions: [".mp4"] },
    ...overrides,
  };
}

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

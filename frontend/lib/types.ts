// Mirrors backend/app/api/health.py and session.py response models.

export type ServerStatus = "ready" | "limited" | "offline";

export interface HealthResponse {
  status: ServerStatus;
  message: string;
  version: string;
  app_env: string;
  auth_mode: string;
  storage_provider: string;
  database: { ok: boolean; detail: string | null };
  storage: { ok: boolean; detail: string | null };
  analysis: {
    available: boolean;
    pipeline_implemented: boolean;
    runtime_installed: boolean;
    runtime_version: string | null;
    model_present: boolean;
    model_verified: boolean;
    model_version: string;
    reason: string | null;
  };
  limits: {
    max_upload_mb: number;
    max_duration_seconds: number;
    accepted_extensions: string[];
  };
}

export interface SessionResponse {
  token: string;
  user_id: string;
  expires_at: string;
  auth_mode: string;
}

export interface MeResponse {
  user_id: string;
  auth_provider: string;
  created_at: string;
  preferences: Record<string, unknown>;
}

export interface ApiErrorBody {
  error: { code: string; message: string };
  request_id: string | null;
}

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
  media_inspection: { ok: boolean; detail: string | null };
  uploads_available: boolean;
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

// Mirrors backend/app/api/projects.py.

export interface ReferenceInfo {
  original_filename: string | null;
  duration: number;
  width: number;
  height: number;
  source_fps: number;
  size_bytes: number | null;
  codec: string | null;
  has_audio: boolean | null;
  warnings: string[];
}

export interface JobInfo {
  id: string;
  kind: string;
  status: "queued" | "running" | "succeeded" | "failed" | string;
  stage: string | null;
  progress: number;
  message: string | null;
  error_code: string | null;
  updated_at: string;
}

export interface Project {
  id: string;
  title: string;
  status: string;
  progress: number;
  is_demo: boolean;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  reference: ReferenceInfo | null;
  latest_job: JobInfo | null;
}

export interface ProjectList {
  projects: Project[];
  limit: number;
}

export interface Sample {
  id: string;
  title: string;
  license: string;
  attribution: string;
  framing: string;
}

export interface MediaUrl {
  url: string;
  expires_in: number;
  content_type: string;
  kind: "source";
}

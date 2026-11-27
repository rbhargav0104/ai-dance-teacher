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
    runtime_selftest?: boolean;
    worker_running?: boolean;
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
  canonical_width?: number | null;
  canonical_height?: number | null;
  canonical_fps?: number | null;
  canonical_duration?: number | null;
  has_canonical?: boolean;
  has_poster?: boolean;
  analysis_fps?: number | null;
  pose_coverage?: number | null;
  quality?: QualityReport | null;
  pipeline_version?: string | null;
  model_version?: string | null;
  analyzed_at?: string | null;
}

export interface QualityReport {
  analyzed_frames: number;
  valid_frames: number;
  coverage: number;
  multi_person_fraction: number;
  feet_visible_fraction: number;
  mean_confidence: number;
  measured_joint_confidence?: number;
  interpolated_frames: number;
  failure: string | null;
  failure_message: string | null;
  warnings: string[];
  excluded_joints: Record<string, number>;
  torso_scale?: number | null;
  thresholds?: Record<string, number>;
  smoothing?: string;
}

export interface JobInfo {
  id: string;
  kind: string;
  status: "queued" | "running" | "succeeded" | "failed" | string;
  stage: string | null;
  progress: number;
  message: string | null;
  error_code: string | null;
  attempts?: number;
  retryable?: boolean;
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
  kind: MediaKind;
}

export type MediaKind = "source" | "canonical" | "poster";

/** [x, y, z, visibility, presence] in image-normalized coordinates. */
export type Landmark = [number, number, number, number, number];
export type Point3 = [number, number, number];

export interface PoseFrameData {
  poses_detected: number;
  landmarks: Landmark[] | null;
  smoothed: (Point3 | null)[];
  reliable: boolean[];
  interpolated: boolean[];
  normalized: (Point3 | null)[];
  world: Point3[] | null;
  angles: Record<string, number | null>;
  root: [number | null, number | null];
  travel: [number | null, number | null];
  com_estimate: [number | null, number | null];
  speed: (number | null)[];
  motion_energy: number | null;
  torso_lean: number | null;
  shoulder_tilt: number | null;
  hip_tilt: number | null;
  yaw_experimental: number | null;
}

export interface PoseFrame {
  t: number;
  frame: number;
  valid: boolean;
  confidence: number;
  data: PoseFrameData;
}

export interface PosesResponse {
  project_id: string;
  status: string;
  pipeline_version: string | null;
  model_version: string | null;
  analysis_fps: number | null;
  width: number | null;
  height: number | null;
  duration: number | null;
  coverage: number | null;
  quality: QualityReport | null;
  landmark_names: string[];
  connections: [number, number][];
  core_landmarks: number[];
  major_landmarks: number[];
  angle_definitions: Record<string, [number, number, number]>;
  frames: PoseFrame[];
}

export interface SectionFact {
  kind: string;
  side: "left" | "right" | "both" | null;
  value: number | null;
  mirror: string;
  direct: string;
}

export interface Section {
  id: string;
  position: number;
  start: number;
  end: number;
  title: string;
  /** Mirror perspective (default): the learner uses the dancer's own body side. */
  instruction: string | null;
  /** Video not mirrored: sides swap, as when following the screen like a reflection. */
  instruction_direct: string | null;
  instruction_experimental: boolean;
  facts: SectionFact[];
  untracked: string[];
  coverage: number | null;
  boundary_source: "automatic" | "manual";
  completed: boolean;
  thumbnail_url: string | null;
  algorithm_version: string | null;
}

export interface SectionsResponse {
  project_id: string;
  duration: number;
  min_section_seconds: number;
  max_sections: number;
  thumbnail_expires_in: number;
  sections: Section[];
}

export interface SectionEdit {
  id?: string;
  start: number;
  end: number;
  title?: string | null;
  completed?: boolean | null;
}

// Mirrors backend/app/api/practice.py.

export type CaptureSource = "webcam" | "upload";

export interface PracticeTarget {
  segment_id: string | null;
  title: string;
  /** Reference-video seconds. */
  start: number;
  end: number;
}

export interface PracticeSession {
  id: string;
  project_id: string;
  status: "uploaded" | "queued" | "processing" | "analyzed" | "failed" | string;
  progress: number;
  error_code: string | null;
  error_message: string | null;
  capture_source: CaptureSource;
  declared_mirrored: boolean | null;
  target: PracticeTarget;
  original_filename: string | null;
  duration: number | null;
  width: number | null;
  height: number | null;
  source_fps: number | null;
  size_bytes: number | null;
  warnings: string[];
  canonical_width: number | null;
  canonical_height: number | null;
  canonical_duration: number | null;
  has_canonical: boolean;
  has_poster: boolean;
  analysis_fps: number | null;
  tracking_coverage: number | null;
  quality: QualityReport | null;
  pipeline_version: string | null;
  model_version: string | null;
  analyzed_at: string | null;
  created_at: string;
  latest_job: JobInfo | null;
  /** Always false until comparison + scoring exist (Outcomes 6–7). */
  scored: boolean;
}

export interface PracticeList {
  project_id: string;
  sessions: PracticeSession[];
  limit: number;
}

/** One reference frame's match in an attempt alignment (backend app.pose.alignment). */
export interface AlignmentFrame {
  ref_t: number; // seconds from the start of the practised window
  ref_src_t: number; // seconds on the reference video's own timeline
  learner_t: number;
  learner_src_t: number;
  cost: number | null; // null = not measurable on both videos (masked, never "wrong")
  position: number | null;
  angle: number | null;
  lean: number | null;
  direction: number | null;
  measured: boolean;
  reused: boolean;
  offset_s: number;
  missing: boolean;
}

export type AlignmentStatus = "aligned" | "insufficient_reference" | "insufficient_tracking" | "out_of_band";

export interface Alignment {
  version: string;
  status: AlignmentStatus | string;
  message?: string | null;
  scorable: boolean;
  reference_frames: number;
  learner_frames: number;
  reference_usable_frames: number;
  learner_usable_frames: number;
  window?: { start: number; end: number; segment_id: string | null };
  preferred_reason?: string;
  mirror?: {
    chosen: "direct" | "mirrored";
    decision: "clear" | "ambiguous";
    preferred: "direct" | "mirrored";
    margin: number;
    mean_cost: { direct: number | null; mirrored: number | null };
  };
  body_size_factor?: number | null;
  body_size_segments?: number;
  band_s?: number | null;
  reference_immobile?: boolean;
  reference_median_energy?: number | null;
  path?: [number, number][];
  frames?: AlignmentFrame[];
  summary?: {
    mean_cost: number | null;
    median_cost: number | null;
    equal_time_cost: number | null;
    measured_fraction: number | null;
    masked_fraction: number | null;
    missing_fraction: number | null;
    reuse_fraction: number | null;
    confidence: number | null;
  };
  timing?: {
    median_offset_s: number | null;
    speed_ratio: number | null;
    fit_intercept_s: number | null;
    max_local_deviation_s: number | null;
    off_spans: [number, number][];
  };
  warp?: {
    non_diagonal_fraction: number | null;
    max_learner_hold_s: number | null;
    max_reference_hold_s: number | null;
    learner_start_s: number | null;
    learner_end_s: number | null;
    attempt_ended_early_s?: number | null;
  };
  masked_spans?: [number, number][];
  missing_spans?: [number, number][];
  config?: Record<string, unknown>;
}

export interface AlignmentResponse {
  practice_id: string;
  cached: boolean;
  alignment: Alignment;
}

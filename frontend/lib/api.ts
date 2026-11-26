import type {
  ApiErrorBody,
  HealthResponse,
  JobInfo,
  MediaKind,
  MediaUrl,
  MeResponse,
  CaptureSource,
  PracticeList,
  PracticeSession,
  Project,
  ProjectList,
  PosesResponse,
  Sample,
  Section,
  SectionEdit,
  SectionsResponse,
  SessionResponse,
} from "./types";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");
const TOKEN_KEY = "adt.session.v1";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class NetworkError extends Error {
  constructor() {
    super("The studio could not be reached.");
    this.name = "NetworkError";
  }
}

function readToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function writeToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: session lives only in memory for this tab */
  }
}

let memoryToken: string | null = null;

async function raw(path: string, init: RequestInit = {}): Promise<Response> {
  try {
    return await fetch(`${API_BASE}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new NetworkError();
  }
}

async function parse<T>(res: Response): Promise<T> {
  if (res.status === 204) return undefined as T;
  if (res.ok) return (await res.json()) as T;
  let body: ApiErrorBody | null = null;
  try {
    body = (await res.json()) as ApiErrorBody;
  } catch {
    /* non-JSON error */
  }
  throw new ApiError(
    res.status,
    body?.error.code ?? "http_error",
    body?.error.message ?? `Request failed (${res.status}).`,
  );
}

export async function getHealth(): Promise<HealthResponse> {
  return parse<HealthResponse>(await raw("/api/health"));
}

async function createSession(): Promise<string> {
  const session = await parse<SessionResponse>(await raw("/api/session", { method: "POST" }));
  memoryToken = session.token;
  writeToken(session.token);
  return session.token;
}

async function ensureToken(): Promise<string> {
  return memoryToken ?? readToken() ?? createSession();
}

/**
 * Authenticated request. On a 401 in local mode, clear the stale token, create one fresh
 * session and retry exactly once (spec 25). Callers must only use this for requests that are
 * safe to repeat (idempotent, or rejected before persistence).
 */
export async function authed<T>(path: string, init: RequestInit = {}): Promise<T> {
  const send = (token: string) =>
    raw(path, { ...init, headers: { ...init.headers, Authorization: `Bearer ${token}` } });

  let res = await send(await ensureToken());
  if (res.status === 401) {
    memoryToken = null;
    writeToken(null);
    res = await send(await createSession());
  }
  return parse<T>(res);
}

export function getMe(): Promise<MeResponse> {
  return authed<MeResponse>("/api/me");
}

export const listProjects = () => authed<ProjectList>("/api/projects");
export const getProject = (id: string) =>
  authed<Project>(`/api/projects/${encodeURIComponent(id)}`);
export const deleteProject = (id: string) =>
  authed<void>(`/api/projects/${encodeURIComponent(id)}`, { method: "DELETE" });
export const getMedia = (id: string, kind: MediaKind = "source") =>
  authed<MediaUrl>(`/api/projects/${encodeURIComponent(id)}/media/${kind}`);
export const getSourceMedia = (id: string) => getMedia(id, "source");
export const startAnalysis = (id: string, rerun = false) =>
  authed<JobInfo>(`/api/projects/${encodeURIComponent(id)}/analysis`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rerun }),
  });
export const getPoses = (id: string) =>
  authed<PosesResponse>(`/api/projects/${encodeURIComponent(id)}/poses`);
const sectionsPath = (id: string) => `/api/projects/${encodeURIComponent(id)}/segments`;
export const getSections = (id: string) => authed<SectionsResponse>(sectionsPath(id));
/** Replace the section list (validated server-side: full coverage, no gaps or overlaps). */
export const saveSections = (id: string, sections: SectionEdit[]) =>
  authed<SectionsResponse>(sectionsPath(id), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sections }),
  });
export const updateSection = (id: string, sectionId: string, patch: { title?: string; completed?: boolean }) =>
  authed<Section>(`${sectionsPath(id)}/${encodeURIComponent(sectionId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
export const regenerateSections = (id: string) =>
  authed<SectionsResponse>(`${sectionsPath(id)}/regenerate`, { method: "POST" });
export const listSamples = async () => parse<Sample[]>(await raw("/api/samples"));
export const addSample = (sampleId: string) =>
  authed<Project>("/api/projects/sample", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sample_id: sampleId }),
  });

/** Resolve a server-relative media URL against the API base (same-origin by default). */
export const mediaHref = (url: string) => `${API_BASE}${url}`;

export interface UploadHandle {
  promise: Promise<Project>;
  abort: () => void;
}

export interface UploadOptions {
  file: File;
  title?: string;
  /** Stable per selected file: a manual retry after a network error can never duplicate it. */
  idempotencyKey: string;
  onProgress?: (fraction: number) => void;
}

export class UploadAborted extends Error {
  constructor() {
    super("Upload cancelled.");
    this.name = "UploadAborted";
  }
}

interface XhrRequest {
  path: string;
  fields: Record<string, string>;
  file: File;
  idempotencyKey: string;
  onProgress?: (fraction: number) => void;
}

function xhrUpload(token: string, req: XhrRequest, setXhr: (x: XMLHttpRequest) => void) {
  return new Promise<{ status: number; body: unknown }>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    setXhr(xhr);
    xhr.open("POST", `${API_BASE}${req.path}`);
    xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.setRequestHeader("Idempotency-Key", req.idempotencyKey);
    xhr.responseType = "text";
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && e.total > 0) req.onProgress?.(e.loaded / e.total);
    };
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* non-JSON (proxy error page) */
      }
      resolve({ status: xhr.status, body });
    };
    xhr.onerror = () => reject(new NetworkError());
    xhr.onabort = () => reject(new UploadAborted());
    const form = new FormData();
    for (const [k, v] of Object.entries(req.fields)) form.append(k, v);
    form.append("file", req.file, req.file.name);
    xhr.send(form);
  });
}

function bodyOrThrow<T>(res: { status: number; body: unknown }): T {
  if (res.status >= 200 && res.status < 300) return res.body as T;
  const err = (res.body as ApiErrorBody | null)?.error;
  if (res.status === 413 && !err) {
    throw new ApiError(413, "file_too_large", "This video is larger than the server accepts.");
  }
  throw new ApiError(
    res.status,
    err?.code ?? "http_error",
    err?.message ?? `Upload failed (${res.status}).`,
  );
}

/**
 * Multipart upload with real byte progress. A 401 is always raised before anything is
 * persisted, so it is safe to refresh the local session and retry exactly once (spec 25).
 * Network failures are surfaced, never auto-retried; a manual retry reuses the idempotency key.
 */
function upload<T>(req: XhrRequest): { promise: Promise<T>; abort: () => void } {
  let current: XMLHttpRequest | null = null;
  let aborted = false;
  const setXhr = (x: XMLHttpRequest) => {
    current = x;
  };
  const promise = (async () => {
    let res = await xhrUpload(await ensureToken(), req, setXhr);
    if (res.status === 401 && !aborted) {
      memoryToken = null;
      writeToken(null);
      req.onProgress?.(0);
      res = await xhrUpload(await createSession(), req, setXhr);
    }
    return bodyOrThrow<T>(res);
  })();
  return {
    promise,
    abort: () => {
      aborted = true;
      current?.abort();
    },
  };
}

/** Upload a reference video (new dance). */
export function uploadReference(opts: UploadOptions): UploadHandle {
  return upload<Project>({
    path: "/api/projects",
    fields: opts.title ? { title: opts.title } : {},
    file: opts.file,
    idempotencyKey: opts.idempotencyKey,
    onProgress: opts.onProgress,
  });
}

export interface PracticeUploadOptions {
  projectId: string;
  file: File;
  segmentId: string | null;
  captureSource: CaptureSource;
  /** The video itself is a mirror image (e.g. exported from a selfie app). */
  mirrored: boolean;
  idempotencyKey: string;
  onProgress?: (fraction: number) => void;
}

/** Upload a learner attempt (webcam recording or file). Analysis starts server-side. */
export function uploadPractice(opts: PracticeUploadOptions): { promise: Promise<PracticeSession>; abort: () => void } {
  const fields: Record<string, string> = {
    capture_source: opts.captureSource,
    mirrored: opts.mirrored ? "true" : "false",
  };
  if (opts.segmentId) fields.segment_id = opts.segmentId;
  return upload<PracticeSession>({
    path: `/api/projects/${encodeURIComponent(opts.projectId)}/practice-sessions`,
    fields,
    file: opts.file,
    idempotencyKey: opts.idempotencyKey,
    onProgress: opts.onProgress,
  });
}

const practicePath = (id: string) => `/api/practice-sessions/${encodeURIComponent(id)}`;
export const listPractice = (projectId: string) =>
  authed<PracticeList>(`/api/projects/${encodeURIComponent(projectId)}/practice-sessions`);
export const getPractice = (id: string) => authed<PracticeSession>(practicePath(id));
export const deletePractice = (id: string) => authed<void>(practicePath(id), { method: "DELETE" });
export const startPracticeAnalysis = (id: string, rerun = false) =>
  authed<JobInfo>(`${practicePath(id)}/analysis`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rerun }),
  });
export const getPracticePoses = (id: string) => authed<PosesResponse>(`${practicePath(id)}/poses`);
export const getPracticeMedia = (id: string, kind: MediaKind = "canonical") =>
  authed<MediaUrl>(`${practicePath(id)}/media/${kind}`);

/** Test hook. */
export function __resetSessionForTests(): void {
  memoryToken = null;
  writeToken(null);
}

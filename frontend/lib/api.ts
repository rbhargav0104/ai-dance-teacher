import type { ApiErrorBody, HealthResponse, MeResponse, SessionResponse } from "./types";

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

/** Test hook. */
export function __resetSessionForTests(): void {
  memoryToken = null;
  writeToken(null);
}

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { __resetSessionForTests, ApiError, NetworkError, uploadReference } from "@/lib/api";

import { json } from "./fixtures";

type Reply = { status: number; body: unknown } | "network-error";

class FakeXHR {
  static replies: Reply[] = [];
  static sent: { headers: Record<string, string>; body: FormData }[] = [];
  status = 0;
  responseText = "";
  responseType = "";
  headers: Record<string, string> = {};
  upload: { onprogress: ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  open() {}
  setRequestHeader(k: string, v: string) {
    this.headers[k] = v;
  }
  abort() {
    this.onabort?.();
  }
  send(body: FormData) {
    FakeXHR.sent.push({ headers: this.headers, body });
    const reply = FakeXHR.replies.shift();
    queueMicrotask(() => {
      if (reply === "network-error" || !reply) return this.onerror?.();
      this.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 });
      this.status = reply.status;
      this.responseText = JSON.stringify(reply.body);
      this.onload?.();
    });
  }
}

const session = (token: string) => ({ token, user_id: "u", expires_at: "", auth_mode: "local" });
const file = () => new File([new Uint8Array([1, 2, 3])], "move.mp4", { type: "video/mp4" });

describe("uploadReference", () => {
  beforeEach(() => {
    __resetSessionForTests();
    FakeXHR.replies = [];
    FakeXHR.sent = [];
    vi.stubGlobal("XMLHttpRequest", FakeXHR);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("sends the idempotency key, bearer token and reports progress", async () => {
    window.localStorage.setItem("adt.session.v1", "tok");
    FakeXHR.replies = [{ status: 201, body: { id: "p1" } }];
    const progress: number[] = [];
    const project = await uploadReference({ file: file(), idempotencyKey: "up-key-1", onProgress: (p) => progress.push(p) }).promise;
    expect(project.id).toBe("p1");
    expect(FakeXHR.sent[0].headers).toMatchObject({ Authorization: "Bearer tok", "Idempotency-Key": "up-key-1" });
    expect(FakeXHR.sent[0].body.get("file")).toBeInstanceOf(File);
    expect(progress).toContain(0.5);
  });

  it("refreshes an expired session once and retries with the same key", async () => {
    window.localStorage.setItem("adt.session.v1", "stale");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(session("fresh"), 201)));
    FakeXHR.replies = [
      { status: 401, body: { error: { code: "session_expired", message: "x" } } },
      { status: 201, body: { id: "p2" } },
    ];
    const project = await uploadReference({ file: file(), idempotencyKey: "up-key-2" }).promise;
    expect(project.id).toBe("p2");
    expect(FakeXHR.sent).toHaveLength(2);
    expect(FakeXHR.sent[1].headers).toMatchObject({ Authorization: "Bearer fresh", "Idempotency-Key": "up-key-2" });
  });

  it("surfaces server rejections with their code and message", async () => {
    window.localStorage.setItem("adt.session.v1", "tok");
    FakeXHR.replies = [{ status: 422, body: { error: { code: "audio_only", message: "This file only contains audio." } } }];
    const err = await uploadReference({ file: file(), idempotencyKey: "up-key-3" }).promise.catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("audio_only");
  });

  it("does not auto-retry network failures", async () => {
    window.localStorage.setItem("adt.session.v1", "tok");
    FakeXHR.replies = ["network-error"];
    await expect(uploadReference({ file: file(), idempotencyKey: "up-key-4" }).promise).rejects.toBeInstanceOf(NetworkError);
    expect(FakeXHR.sent).toHaveLength(1);
  });
});

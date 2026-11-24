import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { __resetSessionForTests, ApiError, getMe, NetworkError } from "@/lib/api";

import { json } from "./fixtures";

const me = { user_id: "u2", auth_provider: "local", created_at: "", preferences: {} };
const session = (token: string) => ({ token, user_id: "u", expires_at: "", auth_mode: "local" });

describe("authed requests", () => {
  beforeEach(() => __resetSessionForTests());
  afterEach(() => vi.unstubAllGlobals());

  it("creates a session on first use and sends the bearer token", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(session("t1"), 201))
      .mockResolvedValueOnce(json(me));
    vi.stubGlobal("fetch", fetchMock);
    await expect(getMe()).resolves.toEqual(me);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/session");
    expect(fetchMock.mock.calls[1][1].headers.Authorization).toBe("Bearer t1");
  });

  it("on 401 refreshes the local session once and retries once", async () => {
    window.localStorage.setItem("adt.session.v1", "stale");
    const expired = json({ error: { code: "session_expired", message: "x" }, request_id: null }, 401);
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(expired)
      .mockResolvedValueOnce(json(session("fresh"), 201))
      .mockResolvedValueOnce(json(me));
    vi.stubGlobal("fetch", fetchMock);
    await expect(getMe()).resolves.toEqual(me);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[2][1].headers.Authorization).toBe("Bearer fresh");
    expect(window.localStorage.getItem("adt.session.v1")).toBe("fresh");
  });

  it("does not loop when the retry is also rejected", async () => {
    window.localStorage.setItem("adt.session.v1", "stale");
    const unauth = () =>
      json({ error: { code: "invalid_session", message: "no" }, request_id: null }, 401);
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(unauth())
      .mockResolvedValueOnce(json(session("fresh"), 201))
      .mockResolvedValueOnce(unauth());
    vi.stubGlobal("fetch", fetchMock);
    const err = await getMe().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("invalid_session");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("surfaces network failures as NetworkError without retrying", async () => {
    window.localStorage.setItem("adt.session.v1", "t");
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetchMock);
    await expect(getMe()).rejects.toBeInstanceOf(NetworkError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

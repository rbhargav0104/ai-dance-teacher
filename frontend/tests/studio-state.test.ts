import { describe, expect, it } from "vitest";

import { deriveStudioView } from "@/lib/studio-state";

import { health } from "./fixtures";

describe("deriveStudioView", () => {
  it("is LOADING until the first health check resolves", () => {
    const v = deriveStudioView({ kind: "pending" });
    expect(v.state).toBe("LOADING");
    expect(v.canUpload).toBe(false);
  });

  it("is OFFLINE when the API is unreachable", () => {
    expect(deriveStudioView({ kind: "unreachable" }).state).toBe("OFFLINE");
  });

  it("is OFFLINE when the server reports broken persistence", () => {
    const v = deriveStudioView({
      kind: "ok",
      health: health({ status: "offline", message: "The studio database is unreachable." }),
    });
    expect(v.state).toBe("OFFLINE");
    expect(v.detail).toMatch(/database/);
  });

  it("is LIMITED with uploads but no analysis when inference is unavailable", () => {
    const v = deriveStudioView({ kind: "ok", health: health() });
    expect(v).toMatchObject({ state: "LIMITED", canUpload: true, canAnalyze: false });
  });

  it("never shows READY unless analysis is actually available", () => {
    const h = health({ status: "ready" });
    expect(deriveStudioView({ kind: "ok", health: h }).state).toBe("LIMITED");
    h.analysis = { ...h.analysis, available: true, pipeline_implemented: true, reason: null };
    expect(deriveStudioView({ kind: "ok", health: h })).toMatchObject({
      state: "READY",
      canAnalyze: true,
    });
  });
});

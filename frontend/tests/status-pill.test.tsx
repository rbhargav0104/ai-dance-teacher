import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StatusPill, StudioStatusProvider } from "@/components/studio-status";

import { health, json } from "./fixtures";

function renderPill() {
  return render(
    <StudioStatusProvider>
      <StatusPill />
    </StudioStatusProvider>,
  );
}

describe("StatusPill", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows a loading state first, then LIMITED from the real health payload", async () => {
    let resolve!: (r: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((r) => (resolve = r))));
    renderPill();
    expect(screen.getByRole("status")).toHaveAttribute("data-state", "LOADING");
    resolve(json(health()));
    await waitFor(() => expect(screen.getByRole("status")).toHaveAttribute("data-state", "LIMITED"));
    expect(screen.getByRole("status")).toHaveTextContent(/still being built/);
  });

  it("shows OFFLINE with a retry button when the API is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fail")));
    renderPill();
    await waitFor(() => expect(screen.getByRole("status")).toHaveAttribute("data-state", "OFFLINE"));
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("treats a proxy 502 as OFFLINE", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("bad gateway", { status: 502 })));
    renderPill();
    await waitFor(() => expect(screen.getByRole("status")).toHaveAttribute("data-state", "OFFLINE"));
  });
});

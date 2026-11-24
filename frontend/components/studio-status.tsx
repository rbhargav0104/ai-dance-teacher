"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { ApiError, getHealth } from "@/lib/api";
import { deriveStudioView, type HealthResult, type StudioView } from "@/lib/studio-state";

interface StudioStatusContext {
  result: HealthResult;
  view: StudioView;
  retry: () => void;
}

const Ctx = createContext<StudioStatusContext | null>(null);
const POLL_MS = 15_000;

export function StudioStatusProvider({ children }: { children: React.ReactNode }) {
  const [result, setResult] = useState<HealthResult>({ kind: "pending" });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const health = await getHealth();
        if (!cancelled) setResult({ kind: "ok", health });
      } catch (err) {
        if (cancelled) return;
        // A proxy 5xx (backend down behind Next) counts as unreachable too.
        if (err instanceof ApiError && err.status < 500) return;
        setResult({ kind: "unreachable" });
      }
    };
    void check();
    const id = window.setInterval(check, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [tick]);

  const retry = useCallback(() => {
    setResult({ kind: "pending" });
    setTick((t) => t + 1);
  }, []);
  const value = useMemo(() => ({ result, view: deriveStudioView(result), retry }), [result, retry]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useStudioStatus(): StudioStatusContext {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useStudioStatus must be used inside StudioStatusProvider");
  return ctx;
}

const DOT: Record<StudioView["state"], string> = {
  LOADING: "bg-muted",
  READY: "bg-lime shadow-[0_0_12px_var(--color-lime)]",
  LIMITED: "bg-amber",
  OFFLINE: "bg-danger",
};

export function StatusPill() {
  const { view, retry } = useStudioStatus();
  return (
    <div className="flex items-center gap-2">
      <div
        role="status"
        aria-live="polite"
        title={view.detail}
        data-state={view.state}
        className="flex items-center gap-2 rounded-full border border-line bg-raised/80 px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-ink backdrop-blur"
      >
        <span
          aria-hidden
          className={`size-2 rounded-full ${DOT[view.state]} ${view.state === "LOADING" ? "animate-pulse-dot" : ""}`}
        />
        <span>{view.label}</span>
        <span className="sr-only">: {view.detail}</span>
      </div>
      {view.state === "OFFLINE" && (
        <button
          type="button"
          onClick={retry}
          className="rounded-full border border-line px-3 py-1.5 text-xs text-muted transition hover:border-lime hover:text-ink"
        >
          Retry
        </button>
      )}
    </div>
  );
}

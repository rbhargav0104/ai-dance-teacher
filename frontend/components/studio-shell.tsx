"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { getMe } from "@/lib/api";
import type { HealthResponse } from "@/lib/types";

import { useStudioStatus } from "./studio-status";

type SessionState = { kind: "pending" } | { kind: "ok"; userId: string } | { kind: "error" };

export function StudioShell() {
  const { result, view, retry } = useStudioStatus();
  const demo = useSearchParams().get("demo") === "1";
  const [session, setSession] = useState<SessionState>({ kind: "pending" });
  const reachable = view.state === "READY" || view.state === "LIMITED";

  useEffect(() => {
    if (!reachable || session.kind === "ok") return;
    let cancelled = false;
    getMe()
      .then((me) => !cancelled && setSession({ kind: "ok", userId: me.user_id }))
      .catch(() => !cancelled && setSession({ kind: "error" }));
    return () => {
      cancelled = true;
    };
  }, [reachable, session.kind]);

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-8 sm:py-14">
      <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted">Private studio</p>
      <h1 className="mt-3 font-display text-3xl font-bold tracking-tight sm:text-5xl">
        {demo ? "Sample dance" : "Your dances"}
      </h1>

      {view.state === "LOADING" ? (
        <div className="mt-10 h-64 animate-pulse rounded-3xl border border-line bg-raised/50" aria-busy />
      ) : view.state === "OFFLINE" ? (
        <Panel tone="danger" title="The studio is offline">
          <p>{view.detail}</p>
          <button
            type="button"
            onClick={retry}
            className="mt-5 rounded-full bg-ink px-5 py-2.5 text-sm font-semibold text-studio"
          >
            Try again
          </button>
        </Panel>
      ) : (
        <>
          <Panel tone={view.state === "READY" ? "lime" : "amber"} title={view.label}>
            <p>{view.detail}</p>
            <p className="mt-3 text-sm">
              {demo
                ? "The sample dance will be processed by the real pose pipeline once it lands. Until then there is nothing to show — we won't fake it."
                : "Uploading a reference dance opens in the next build. Nothing here is simulated."}
            </p>
          </Panel>
          {result.kind === "ok" && <Capabilities health={result.health} session={session} />}
        </>
      )}
    </div>
  );
}

function Panel({
  tone,
  title,
  children,
}: {
  tone: "lime" | "amber" | "danger";
  title: string;
  children: React.ReactNode;
}) {
  const bar = { lime: "bg-lime", amber: "bg-amber", danger: "bg-danger" }[tone];
  return (
    <section className="relative mt-10 overflow-hidden rounded-3xl border border-line bg-raised/70 p-6 sm:p-8">
      <span className={`absolute inset-y-0 left-0 w-1 ${bar}`} aria-hidden />
      <h2 className="font-display text-lg font-semibold">{title}</h2>
      <div className="mt-2 max-w-2xl leading-relaxed text-muted">{children}</div>
    </section>
  );
}

function Capabilities({ health, session }: { health: HealthResponse; session: SessionState }) {
  const rows: [string, boolean, string][] = [
    ["Private session", session.kind === "ok", session.kind === "ok" ? "signed in (local)" : session.kind === "pending" ? "connecting…" : "could not start"],
    ["Database", health.database.ok, health.database.ok ? `schema ${health.database.detail}` : "unavailable"],
    ["Private storage", health.storage.ok, health.storage_provider],
    ["Pose model", health.analysis.model_verified, health.analysis.model_verified ? "verified (SHA-256)" : health.analysis.model_present ? "failed integrity check" : "not downloaded"],
    ["Pose runtime", health.analysis.runtime_installed, health.analysis.runtime_version ? `mediapipe ${health.analysis.runtime_version}` : "not installed"],
    ["Analysis pipeline", health.analysis.pipeline_implemented, health.analysis.pipeline_implemented ? "enabled" : "in development"],
  ];
  return (
    <section aria-labelledby="caps" className="mt-8">
      <h2 id="caps" className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted">
        System check
      </h2>
      <ul className="mt-4 grid gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
        {rows.map(([name, ok, detail]) => (
          <li key={name} className="flex items-center justify-between gap-4 bg-studio px-5 py-4">
            <span className="text-sm text-ink">{name}</span>
            <span className={`flex items-center gap-2 font-mono text-xs ${ok ? "text-lime" : "text-amber"}`}>
              <span aria-hidden>{ok ? "●" : "○"}</span>
              {detail}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

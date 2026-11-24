"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { addSample, ApiError, deleteProject, listProjects, listSamples } from "@/lib/api";
import type { HealthResponse, Project, Sample } from "@/lib/types";

import { ProjectList } from "./project-list";
import { ReferenceUpload } from "./reference-upload";
import { useStudioStatus } from "./studio-status";

type Load<T> = { kind: "pending" } | { kind: "ok"; data: T } | { kind: "error"; message: string };

export function StudioShell() {
  const { result, view, retry } = useStudioStatus();
  const router = useRouter();
  const demo = useSearchParams().get("demo") === "1";
  const reachable = view.state === "READY" || view.state === "LIMITED";
  const [projects, setProjects] = useState<Load<{ projects: Project[]; limit: number }>>({ kind: "pending" });
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setProjects({ kind: "ok", data: await listProjects() });
    } catch (err) {
      setProjects({ kind: "error", message: err instanceof Error ? err.message : "Could not load your dances." });
    }
  }, []);

  useEffect(() => {
    if (!reachable) return;
    let cancelled = false;
    listProjects()
      .then((data) => !cancelled && setProjects({ kind: "ok", data }))
      .catch((err: unknown) => {
        if (!cancelled) setProjects({ kind: "error", message: err instanceof Error ? err.message : "Could not load your dances." });
      });
    return () => {
      cancelled = true;
    };
  }, [reachable]);

  const onDelete = async (p: Project) => {
    try {
      await deleteProject(p.id);
      setNotice(`Deleted “${p.title}” and its video.`);
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "Delete failed. Try again.");
    }
    await refresh();
  };

  const health = result.kind === "ok" ? result.health : null;

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-8 sm:py-14">
      <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted">Private studio</p>
      <h1 className="mt-3 font-display text-3xl font-bold tracking-tight sm:text-5xl">
        {demo ? "Try a sample dance" : "Your dances"}
      </h1>

      {view.state === "LOADING" ? (
        <div className="mt-10 space-y-4" aria-busy aria-label="Loading the studio">
          <div className="h-72 animate-pulse rounded-3xl border border-line bg-raised/50" />
          <div className="h-32 animate-pulse rounded-3xl border border-line bg-raised/30" />
        </div>
      ) : view.state === "OFFLINE" ? (
        <Panel tone="danger" title="The studio is offline">
          <p>{view.detail}</p>
          <button type="button" onClick={retry} className="mt-5 rounded-full bg-ink px-5 py-2.5 text-sm font-semibold text-studio">
            Try again
          </button>
        </Panel>
      ) : (
        <>
          {view.state === "LIMITED" && (
            <Panel tone="amber" title="Limited mode — upload and manage only">
              <p>
                {view.detail} Upload, preview and delete work now; analysis stays off until it
                really works — nothing here is simulated.
              </p>
            </Panel>
          )}

          {notice && (
            <p role="status" className="mt-6 rounded-xl border border-line bg-raised/60 px-4 py-3 text-sm text-ink">
              {notice}
            </p>
          )}

          {demo && health && (
            <SamplePicker
              onAdded={(p) => router.push(`/studio/projects/${p.id}`)}
              disabled={!health.uploads_available}
            />
          )}

          {health && (
            <ReferenceUpload
              limits={health.limits}
              disabledReason={health.uploads_available ? null : "Video inspection isn't available on this server right now."}
              onUploaded={(p) => {
                setNotice(`“${p.title}” is stored privately.`);
                router.push(`/studio/projects/${p.id}`);
              }}
            />
          )}

          <section aria-labelledby="library" className="mt-14">
            <h2 id="library" className="font-display text-xl font-semibold tracking-tight sm:text-2xl">
              Library
            </h2>
            {projects.kind === "pending" ? (
              <div className="mt-6 h-40 animate-pulse rounded-3xl border border-line bg-raised/40" aria-busy aria-label="Loading your dances" />
            ) : projects.kind === "error" ? (
              <Panel tone="danger" title="Couldn't load your dances">
                <p>{projects.message}</p>
                <button type="button" onClick={refresh} className="mt-4 rounded-full border border-line px-4 py-2 text-sm text-ink">
                  Retry
                </button>
              </Panel>
            ) : (
              <ProjectList projects={projects.data.projects} limit={projects.data.limit} onDelete={onDelete} />
            )}
          </section>

          {health && <SystemCheck health={health} />}
        </>
      )}
    </div>
  );
}

function SamplePicker({ onAdded, disabled }: { onAdded: (p: Project) => void; disabled: boolean }) {
  const [samples, setSamples] = useState<Load<Sample[]>>({ kind: "pending" });
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listSamples()
      .then((data) => setSamples({ kind: "ok", data }))
      .catch(() => setSamples({ kind: "error", message: "Samples are unavailable right now." }));
  }, []);

  return (
    <section aria-labelledby="samples" className="mt-10">
      <h2 id="samples" className="font-display text-xl font-semibold tracking-tight sm:text-2xl">
        Licensed sample clips
      </h2>
      <p className="mt-2 max-w-2xl text-muted">
        Real stock dance footage (Mixkit Free License), added to your studio through the same private
        upload checks as your own videos. Both clips crop the dancer above the knees, so lower-body
        feedback will be limited once analysis is on.
      </p>
      {samples.kind === "pending" ? (
        <div className="mt-5 h-28 animate-pulse rounded-3xl border border-line bg-raised/40" aria-busy />
      ) : samples.kind === "error" ? (
        <p className="mt-5 text-danger">{samples.message}</p>
      ) : (
        <ul className="mt-5 grid gap-4 md:grid-cols-2">
          {samples.data.map((s) => (
            <li key={s.id} className="flex flex-col justify-between gap-4 rounded-3xl border border-line bg-raised/60 p-5 sm:flex-row sm:items-center">
              <div className="min-w-0">
                <p className="font-display font-semibold text-ink">{s.title}</p>
                <p className="mt-1 text-xs text-muted">{s.license}</p>
              </div>
              <button
                type="button"
                disabled={disabled || busy !== null}
                onClick={async () => {
                  setBusy(s.id);
                  setError(null);
                  try {
                    onAdded(await addSample(s.id));
                  } catch (err) {
                    setError(err instanceof Error ? err.message : "Could not add the sample.");
                    setBusy(null);
                  }
                }}
                className="inline-flex h-11 shrink-0 items-center justify-center rounded-full bg-lime px-5 font-display text-xs font-semibold uppercase tracking-[0.12em] text-studio disabled:opacity-50"
              >
                {busy === s.id ? "Adding…" : "Use this sample"}
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && (
        <p role="alert" className="mt-3 text-sm text-danger">
          {error}
        </p>
      )}
    </section>
  );
}

export function Panel({ tone, title, children }: { tone: "lime" | "amber" | "danger"; title: string; children: React.ReactNode }) {
  const bar = { lime: "bg-lime", amber: "bg-amber", danger: "bg-danger" }[tone];
  return (
    <section className="relative mt-8 overflow-hidden rounded-3xl border border-line bg-raised/70 p-6 sm:p-8">
      <span className={`absolute inset-y-0 left-0 w-1 ${bar}`} aria-hidden />
      <h2 className="font-display text-lg font-semibold">{title}</h2>
      <div className="mt-2 max-w-3xl leading-relaxed text-muted">{children}</div>
    </section>
  );
}

function SystemCheck({ health }: { health: HealthResponse }) {
  const rows: [string, boolean, string][] = [
    ["Database", health.database.ok, health.database.ok ? `schema ${health.database.detail}` : "unavailable"],
    ["Private storage", health.storage.ok, health.storage_provider],
    ["Video inspection", health.media_inspection.ok, health.media_inspection.ok ? "ffprobe" : "unavailable"],
    ["Pose model", health.analysis.model_verified, health.analysis.model_verified ? "verified (SHA-256)" : health.analysis.model_present ? "failed integrity check" : "not downloaded"],
    ["Pose runtime", health.analysis.runtime_installed, health.analysis.runtime_version ? `mediapipe ${health.analysis.runtime_version}` : "not installed"],
    ["Analysis pipeline", health.analysis.pipeline_implemented, health.analysis.pipeline_implemented ? "enabled" : "in development"],
  ];
  return (
    <details className="mt-14 rounded-2xl border border-line/70">
      <summary className="cursor-pointer px-5 py-4 font-mono text-[11px] uppercase tracking-[0.22em] text-muted hover:text-ink">
        System check
      </summary>
      <ul className="grid gap-px border-t border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
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
    </details>
  );
}

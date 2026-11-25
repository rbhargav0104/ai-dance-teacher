"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, deleteProject, getMedia, getPoses, getProject, mediaHref, startAnalysis } from "@/lib/api";
import { formatBytes, formatDuration, warningLabel } from "@/lib/media";
import type { PosesResponse, Project } from "@/lib/types";

import { AnalysisFailure, AnalysisProgress, TrackingSummary } from "./analysis-status";
import { SkeletonOverlay } from "./skeleton-overlay";

import { StatusChip } from "./project-list";
import { Panel } from "./studio-shell";
import { useStudioStatus } from "./studio-status";

const RETRYABLE = new Set(["interrupted", "analysis_crashed", "analysis_unavailable", "decode_failed"]);
const isBusy = (p: Project) => p.status === "queued" || p.status === "processing";

type Load = { kind: "pending" } | { kind: "ok"; project: Project } | { kind: "missing" } | { kind: "error"; message: string };

export function ProjectView() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { view } = useStudioStatus();
  const reachable = view.state === "READY" || view.state === "LIMITED";
  const [load, setLoad] = useState<Load>({ kind: "pending" });
  const [src, setSrc] = useState<string | null>(null);
  const [videoError, setVideoError] = useState(false);
  const [analysisMsg, setAnalysisMsg] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [starting, setStarting] = useState(false);
  const [poses, setPoses] = useState<PosesResponse | null>(null);
  const [showSkeleton, setShowSkeleton] = useState(true);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const project = load.kind === "ok" ? load.project : null;
  const analyzed = project?.status === "analyzed";
  const hasCanonical = Boolean(project?.reference?.has_canonical);
  const busy = project ? isBusy(project) : false;

  const fetchMedia = useCallback(
    async (kind: "source" | "canonical") => {
      try {
        const m = await getMedia(id, kind);
        setSrc(mediaHref(m.url));
        setVideoError(false);
      } catch {
        setSrc(null);
      }
    },
    [id],
  );

  // Prefer the canonical copy (plays everywhere, matches the analysed timeline).
  const projectId = project?.id;
  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    getMedia(id, hasCanonical ? "canonical" : "source")
      .then((m) => {
        if (cancelled) return;
        setSrc(mediaHref(m.url));
        setVideoError(false);
      })
      .catch(() => !cancelled && setSrc(null));
    return () => {
      cancelled = true;
    };
  }, [id, projectId, hasCanonical]);

  useEffect(() => {
    if (!analyzed && project?.status !== "failed") return;
    if (!project?.reference?.analyzed_at) return;
    let cancelled = false;
    getPoses(id)
      .then((p) => !cancelled && setPoses(p))
      .catch(() => !cancelled && setPoses(null));
    return () => {
      cancelled = true;
    };
  }, [id, analyzed, project?.status, project?.reference?.analyzed_at]);

  // Poll while a job is queued/running; state lives on the server, so refresh/leave is safe.
  useEffect(() => {
    if (!busy) return;
    const timer = window.setInterval(() => {
      getProject(id)
        .then((p) => setLoad({ kind: "ok", project: p }))
        .catch(() => {});
    }, 1500);
    return () => window.clearInterval(timer);
  }, [id, busy]);

  useEffect(() => {
    if (!reachable) return;
    let cancelled = false;
    getProject(id)
      .then((project) => {
        if (cancelled) return;
        setLoad({ kind: "ok", project });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) setLoad({ kind: "missing" });
        else setLoad({ kind: "error", message: err instanceof Error ? err.message : "Could not load this dance." });
      });
    return () => {
      cancelled = true;
    };
  }, [id, reachable]);

  if (view.state === "OFFLINE") {
    return (
      <Wrap>
        <Panel tone="danger" title="The studio is offline">
          <p>{view.detail}</p>
        </Panel>
      </Wrap>
    );
  }
  if (load.kind === "pending") {
    return (
      <Wrap>
        <div className="mt-8 aspect-video w-full animate-pulse rounded-3xl border border-line bg-raised/50" aria-busy aria-label="Loading dance" />
      </Wrap>
    );
  }
  if (load.kind === "missing") {
    return (
      <Wrap>
        <Panel tone="amber" title="This dance isn't here">
          <p>It may have been deleted, or it belongs to a different private session.</p>
        </Panel>
      </Wrap>
    );
  }
  if (load.kind === "error") {
    return (
      <Wrap>
        <Panel tone="danger" title="Couldn't load this dance">
          <p>{load.message}</p>
        </Panel>
      </Wrap>
    );
  }

  const p = load.project;
  const ref = p.reference;
  const job = p.latest_job;
  const analysisOff = view.state !== "READY";
  const canStart =
    p.status === "uploaded" || (p.status === "failed" && (job?.retryable || RETRYABLE.has(p.error_code ?? "")));
  const overlay = analyzed && poses && hasCanonical && showSkeleton && src && !videoError;

  const start = async () => {
    setStarting(true);
    setAnalysisMsg(null);
    try {
      await startAnalysis(p.id);
      setLoad({ kind: "ok", project: await getProject(p.id) });
    } catch (err) {
      setAnalysisMsg(err instanceof Error ? err.message : "Analysis failed to start.");
    } finally {
      setStarting(false);
    }
  };

  return (
    <Wrap>
      <div className="mt-6 flex flex-wrap items-center gap-3">
        <StatusChip status={p.status} />
        {p.is_demo && (
          <span className="rounded-full bg-lime/10 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-lime">
            Sample clip · Mixkit Free License
          </span>
        )}
      </div>
      <h1 className="mt-3 font-display text-3xl font-bold tracking-tight sm:text-5xl">{p.title}</h1>

      <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="relative self-start overflow-hidden rounded-3xl border border-line bg-black">
          {src && !videoError ? (
            <div className="relative aspect-video max-h-[70vh] w-full">
              <video
                ref={videoRef}
                key={src}
                src={src}
                controls
                playsInline
                preload="metadata"
                className="absolute inset-0 h-full w-full bg-black object-contain"
                onError={() => setVideoError(true)}
              />
              {overlay && <SkeletonOverlay videoRef={videoRef} poses={poses} />}
            </div>
          ) : (
            <div className="flex aspect-video flex-col items-center justify-center gap-3 p-6 text-center text-muted">
              {videoError ? (
                <>
                  <p>This browser can&apos;t play the original file. A playback copy is made during analysis.</p>
                  <button
                    type="button"
                    onClick={() => fetchMedia(hasCanonical ? "canonical" : "source")}
                    className="rounded-full border border-line px-4 py-2 text-sm text-ink"
                  >
                    Reload video
                  </button>
                </>
              ) : (
                <p className="animate-pulse">Loading private video…</p>
              )}
            </div>
          )}
        </div>

        <aside className="flex flex-col gap-6">
          {ref && (
            <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line">
              <Fact label="Length" value={formatDuration(ref.duration)} />
              <Fact label="Frame" value={`${ref.width}×${ref.height}`} />
              <Fact label="Frame rate" value={`${ref.source_fps.toFixed(ref.source_fps % 1 ? 2 : 0)} fps`} />
              <Fact label="File" value={ref.size_bytes ? formatBytes(ref.size_bytes) : "—"} />
              <Fact label="Codec" value={ref.codec ?? "—"} />
              <Fact label="Audio" value={ref.has_audio ? "yes" : "none"} />
            </dl>
          )}
          {ref && ref.warnings.length > 0 && (
            <ul className="space-y-2 text-sm text-amber">
              {ref.warnings.map((w) => (
                <li key={w} className="flex gap-2">
                  <span aria-hidden>△</span>
                  {warningLabel(w)}
                </li>
              ))}
            </ul>
          )}

          <AnalysisProgress project={p} />
          <AnalysisFailure project={p} />
          {analyzed && <TrackingSummary project={p} />}

          {analyzed ? (
            <div className="flex flex-col gap-3">
              {poses && (
                <label className="flex cursor-pointer items-center justify-between gap-3 rounded-2xl border border-line px-4 py-3 text-sm">
                  <span>Show measured skeleton</span>
                  <input
                    type="checkbox"
                    checked={showSkeleton}
                    onChange={(e) => setShowSkeleton(e.target.checked)}
                    className="size-5 accent-[var(--color-lime)]"
                  />
                </label>
              )}
              <Link
                href={`/studio/projects/${p.id}/debug`}
                className="inline-flex h-14 w-full items-center justify-center rounded-full bg-lime px-6 font-display text-sm font-semibold uppercase tracking-[0.12em] text-studio transition hover:-translate-y-0.5"
              >
                Open pose debugger
              </Link>
              <p className="text-sm text-muted">
                Every joint, angle and confidence value measured from this video. Sections and Learn Mode come next.
              </p>
            </div>
          ) : busy ? null : p.status === "failed" && !canStart ? (
            <Link
              href="/studio"
              className="inline-flex h-14 w-full items-center justify-center rounded-full border border-lime/60 px-6 font-display text-sm font-semibold uppercase tracking-[0.12em] text-lime transition hover:-translate-y-0.5"
            >
              Upload a different video
            </Link>
          ) : (
            <div>
              <button
                type="button"
                disabled={analysisOff || starting}
                aria-describedby="analysis-note"
                onClick={start}
                className="inline-flex h-14 w-full items-center justify-center rounded-full bg-lime px-6 font-display text-sm font-semibold uppercase tracking-[0.12em] text-studio transition enabled:hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:bg-raised-2 disabled:text-muted"
              >
                {starting ? "Starting…" : p.status === "failed" ? "Try analysis again" : "Analyze Choreography"}
              </button>
              <p id="analysis-note" className="mt-3 text-sm text-muted" role="status">
                {analysisMsg ??
                  (analysisOff
                    ? `Analysis is off in Limited mode${view.detail ? `: ${view.detail}` : ""}. We won't show made-up results.`
                    : "Finds the dancer's pose in every frame (about 10–30 seconds for a short clip).")}
              </p>
            </div>
          )}
          {p.status === "failed" && poses && (
            <Link href={`/studio/projects/${p.id}/debug`} className="text-sm text-lime underline-offset-4 hover:underline">
              Inspect what the tracker saw →
            </Link>
          )}

          <div className="mt-auto border-t border-line/70 pt-5">
            {confirmDelete ? (
              <div className="flex flex-wrap items-center gap-2">
                <span className="mr-auto text-sm text-muted">Permanently delete this video and its data?</span>
                <button type="button" onClick={() => setConfirmDelete(false)} className="rounded-full px-3 py-2 text-sm text-muted hover:text-ink">
                  Keep
                </button>
                <button
                  type="button"
                  disabled={deleting}
                  onClick={async () => {
                    setDeleting(true);
                    try {
                      await deleteProject(p.id);
                      router.push("/studio");
                    } catch {
                      setDeleting(false);
                      setAnalysisMsg("Delete failed. Try again.");
                    }
                  }}
                  className="rounded-full bg-danger px-4 py-2 text-sm font-semibold text-studio disabled:opacity-60"
                >
                  {deleting ? "Deleting…" : "Delete"}
                </button>
              </div>
            ) : (
              <button type="button" onClick={() => setConfirmDelete(true)} className="text-sm text-muted transition hover:text-danger">
                Delete this dance
              </button>
            )}
          </div>
        </aside>
      </div>
    </Wrap>
  );
}

function Wrap({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-8 sm:py-12">
      <Link href="/studio" className="inline-flex items-center gap-2 text-sm text-muted transition hover:text-ink">
        <span aria-hidden>←</span> All dances
      </Link>
      {children}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-studio px-4 py-3">
      <dt className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">{label}</dt>
      <dd className="mt-1 truncate font-mono text-sm text-ink">{value}</dd>
    </div>
  );
}

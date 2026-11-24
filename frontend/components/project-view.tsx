"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ApiError, deleteProject, getProject, getSourceMedia, mediaHref, startAnalysis } from "@/lib/api";
import { formatBytes, formatDuration, warningLabel } from "@/lib/media";
import type { Project } from "@/lib/types";

import { StatusChip } from "./project-list";
import { Panel } from "./studio-shell";
import { useStudioStatus } from "./studio-status";

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

  const fetchMedia = useCallback(async () => {
    try {
      const m = await getSourceMedia(id);
      setSrc(mediaHref(m.url));
      setVideoError(false);
    } catch {
      setSrc(null);
    }
  }, [id]);

  useEffect(() => {
    if (!reachable) return;
    let cancelled = false;
    getProject(id)
      .then((project) => {
        if (cancelled) return;
        setLoad({ kind: "ok", project });
        void fetchMedia();
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) setLoad({ kind: "missing" });
        else setLoad({ kind: "error", message: err instanceof Error ? err.message : "Could not load this dance." });
      });
    return () => {
      cancelled = true;
    };
  }, [id, reachable, fetchMedia]);

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

  const { project } = load;
  const ref = project.reference;
  const job = project.latest_job;
  const analysisOff = view.state !== "READY";

  return (
    <Wrap>
      <div className="mt-6 flex flex-wrap items-center gap-3">
        <StatusChip status={project.status} />
        {project.is_demo && (
          <span className="rounded-full bg-lime/10 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-lime">
            Sample clip · Mixkit Free License
          </span>
        )}
      </div>
      <h1 className="mt-3 font-display text-3xl font-bold tracking-tight sm:text-5xl">{project.title}</h1>

      <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="overflow-hidden rounded-3xl border border-line bg-black">
          {src && !videoError ? (
            <video
              key={src}
              src={src}
              controls
              playsInline
              preload="metadata"
              className="aspect-video max-h-[70vh] w-full bg-black object-contain"
              onError={() => setVideoError(true)}
            />
          ) : (
            <div className="flex aspect-video flex-col items-center justify-center gap-3 p-6 text-center text-muted">
              {videoError ? (
                <>
                  <p>This browser can&apos;t play the original file. A playback copy is made during analysis.</p>
                  <button type="button" onClick={fetchMedia} className="rounded-full border border-line px-4 py-2 text-sm text-ink">
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

          {job && (
            <div className="rounded-2xl border border-line bg-raised/60 p-4">
              <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Last step</p>
              <p className="mt-1 text-sm text-ink">{job.message ?? job.status}</p>
            </div>
          )}

          <div>
            <button
              type="button"
              disabled={analysisOff}
              aria-describedby="analysis-note"
              onClick={async () => {
                try {
                  await startAnalysis(project.id);
                } catch (err) {
                  setAnalysisMsg(err instanceof Error ? err.message : "Analysis failed to start.");
                }
              }}
              className="inline-flex h-14 w-full items-center justify-center rounded-full bg-lime px-6 font-display text-sm font-semibold uppercase tracking-[0.12em] text-studio transition enabled:hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:bg-raised-2 disabled:text-muted"
            >
              Analyze Choreography
            </button>
            <p id="analysis-note" className="mt-3 text-sm text-muted" role="status">
              {analysisMsg ??
                (analysisOff
                  ? "Analysis is off in Limited mode: the pose pipeline isn't live yet, and we won't show made-up results."
                  : "Finds the dancer's pose in every frame and suggests sections.")}
            </p>
          </div>

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
                      await deleteProject(project.id);
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

"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";

import { ApiError, NetworkError, UploadAborted, uploadReference, type UploadHandle } from "@/lib/api";
import {
  DEFAULT_EXTENSIONS,
  formatBytes,
  formatDuration,
  newIdempotencyKey,
  precheckDuration,
  precheckFile,
  type UploadLimits,
} from "@/lib/media";
import type { Project } from "@/lib/types";

interface Picked {
  file: File;
  url: string;
  key: string;
  duration: number | null;
  width: number | null;
  height: number | null;
  previewFailed: boolean;
}

type Phase =
  | { kind: "idle" }
  | { kind: "uploading"; progress: number }
  | { kind: "checking" }
  | { kind: "error"; message: string; retryable: boolean };

export function ReferenceUpload({
  limits,
  disabledReason,
  onUploaded,
}: {
  limits: UploadLimits;
  disabledReason: string | null;
  onUploaded: (project: Project) => void;
}) {
  const inputId = useId();
  const titleId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const handleRef = useRef<UploadHandle | null>(null);
  const [picked, setPicked] = useState<Picked | null>(null);
  const [title, setTitle] = useState("");
  const [dragging, setDragging] = useState(false);
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [precheck, setPrecheck] = useState<string | null>(null);

  useEffect(() => () => handleRef.current?.abort(), []);
  useEffect(() => {
    const url = picked?.url;
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [picked?.url]);

  const choose = useCallback(
    (file: File | undefined) => {
      if (!file) return;
      const problem = precheckFile(file, limits);
      setPhase({ kind: "idle" });
      setPrecheck(problem);
      if (problem) {
        setPicked(null);
        return;
      }
      setPicked({
        file,
        url: URL.createObjectURL(file),
        key: newIdempotencyKey(),
        duration: null,
        width: null,
        height: null,
        previewFailed: false,
      });
      setTitle("");
    },
    [limits],
  );

  const clear = () => {
    handleRef.current?.abort();
    setPicked(null);
    setPrecheck(null);
    setPhase({ kind: "idle" });
    if (inputRef.current) inputRef.current.value = "";
  };

  const submit = async () => {
    if (!picked || disabledReason) return;
    setPhase({ kind: "uploading", progress: 0 });
    const handle = uploadReference({
      file: picked.file,
      title: title.trim() || undefined,
      idempotencyKey: picked.key,
      onProgress: (p) =>
        setPhase(p >= 1 ? { kind: "checking" } : { kind: "uploading", progress: p }),
    });
    handleRef.current = handle;
    try {
      const project = await handle.promise;
      handleRef.current = null;
      onUploaded(project);
      clear();
    } catch (err) {
      handleRef.current = null;
      if (err instanceof UploadAborted) return;
      if (err instanceof NetworkError) {
        setPhase({
          kind: "error",
          message: "The connection dropped during upload. Retrying is safe — it won't create a duplicate.",
          retryable: true,
        });
      } else if (err instanceof ApiError) {
        setPhase({ kind: "error", message: err.message, retryable: err.status >= 500 });
      } else {
        setPhase({ kind: "error", message: "Something went wrong. Try again.", retryable: true });
      }
    }
  };

  const busy = phase.kind === "uploading" || phase.kind === "checking";
  const durationProblem = picked ? precheckDuration(picked.duration, limits) : null;
  const accept = (limits.accepted_extensions.length ? limits.accepted_extensions : DEFAULT_EXTENSIONS)
    .concat(["video/mp4", "video/quicktime", "video/webm"])
    .join(",");

  return (
    <section aria-labelledby={`${inputId}-h`} className="mt-10">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 id={`${inputId}-h`} className="font-display text-xl font-semibold tracking-tight sm:text-2xl">
          Add a reference dance
        </h2>
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted">
          MP4 · MOV · WebM — up to {limits.max_upload_mb} MB, {formatDuration(limits.max_duration_seconds)}
        </p>
      </div>

      {!picked ? (
        <label
          htmlFor={inputId}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            choose(e.dataTransfer.files?.[0]);
          }}
          data-dragging={dragging || undefined}
          className="group relative mt-5 flex min-h-64 cursor-pointer flex-col items-center justify-center overflow-hidden rounded-3xl border border-dashed border-line bg-raised/40 px-6 py-12 text-center transition-colors hover:border-lime/60 data-[dragging]:border-lime data-[dragging]:bg-lime/5 sm:min-h-80"
        >
          <DropArt active={dragging} />
          <span className="relative mt-6 font-display text-lg font-semibold sm:text-xl">
            Drop a dance video here
          </span>
          <span className="relative mt-2 text-sm text-muted">
            or <span className="text-lime underline decoration-lime/40 underline-offset-4">choose a file</span>.
            One dancer, full body in frame, steady camera works best.
          </span>
          <input
            ref={inputRef}
            id={inputId}
            type="file"
            accept={accept}
            className="sr-only"
            onChange={(e) => choose(e.target.files?.[0])}
          />
        </label>
      ) : (
        <div className="mt-5 grid gap-6 rounded-3xl border border-line bg-raised/50 p-4 sm:p-6 lg:grid-cols-[1.4fr_1fr]">
          <div className="relative overflow-hidden rounded-2xl bg-black">
            {picked.previewFailed ? (
              <div className="flex aspect-video items-center justify-center p-6 text-center text-sm text-muted">
                Your browser can&apos;t preview this format. You can still upload it — the server will check it.
              </div>
            ) : (
              <video
                src={picked.url}
                controls
                muted
                playsInline
                preload="metadata"
                className="aspect-video w-full bg-black object-contain"
                onLoadedMetadata={(e) => {
                  const v = e.currentTarget;
                  setPicked((p) =>
                    p && { ...p, duration: Number.isFinite(v.duration) ? v.duration : null, width: v.videoWidth || null, height: v.videoHeight || null },
                  );
                }}
                onError={() => setPicked((p) => p && { ...p, previewFailed: true })}
              />
            )}
          </div>
          <div className="flex min-w-0 flex-col">
            <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted">Selected</p>
            <p className="mt-1 truncate font-medium text-ink" title={picked.file.name}>
              {picked.file.name}
            </p>
            <dl className="mt-4 grid grid-cols-3 gap-px overflow-hidden rounded-xl border border-line bg-line text-center">
              <Meta label="Length" value={picked.duration !== null ? formatDuration(picked.duration) : "—"} />
              <Meta label="Size" value={picked.width && picked.height ? `${picked.width}×${picked.height}` : "—"} />
              <Meta label="File" value={formatBytes(picked.file.size)} />
            </dl>

            <label htmlFor={titleId} className="mt-5 text-sm text-muted">
              Name this dance <span className="text-muted/70">(optional)</span>
            </label>
            <input
              id={titleId}
              value={title}
              maxLength={120}
              disabled={busy}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Chorus combo"
              className="mt-2 h-11 rounded-xl border border-line bg-studio px-4 text-ink placeholder:text-muted/60 focus:border-lime focus:outline-none"
            />

            {durationProblem && (
              <p role="alert" className="mt-4 text-sm text-danger">
                {durationProblem}
              </p>
            )}

            <div className="mt-auto pt-6">
              {busy && <Progress phase={phase} />}
              {phase.kind === "error" && (
                <p role="alert" className="mb-4 rounded-xl border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-ink">
                  {phase.message}
                </p>
              )}
              {disabledReason && (
                <p className="mb-4 text-sm text-amber">{disabledReason}</p>
              )}
              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={submit}
                  disabled={busy || !!disabledReason || !!durationProblem}
                  className="inline-flex h-12 flex-1 items-center justify-center rounded-full bg-lime px-6 font-display text-sm font-semibold uppercase tracking-[0.1em] text-studio transition enabled:hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busy ? "Uploading…" : phase.kind === "error" && phase.retryable ? "Retry upload" : "Upload to studio"}
                </button>
                <button
                  type="button"
                  onClick={clear}
                  className="inline-flex h-12 items-center justify-center rounded-full border border-line px-5 text-sm text-ink transition hover:border-ink"
                >
                  {busy ? "Cancel" : "Remove"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {precheck && (
        <p role="alert" className="mt-4 rounded-xl border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-ink">
          {precheck}
        </p>
      )}

      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="flex items-center gap-2 text-sm text-muted">
          <LockIcon />
          Private to you. Stored without public links, deletable any time, never used for training.
        </p>
        <FutureLinks />
      </div>
    </section>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-studio px-2 py-3">
      <dt className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">{label}</dt>
      <dd className="mt-1 font-mono text-sm text-ink">{value}</dd>
    </div>
  );
}

function Progress({ phase }: { phase: Phase }) {
  const pct = phase.kind === "uploading" ? Math.round(phase.progress * 100) : 100;
  const label = phase.kind === "checking" ? "Checking the video…" : `Uploading ${pct}%`;
  return (
    <div className="mb-4">
      <div className="flex justify-between font-mono text-xs text-muted">
        <span role="status" aria-live="polite">{label}</span>
        <span aria-hidden>{pct}%</span>
      </div>
      <div
        className="mt-2 h-1.5 overflow-hidden rounded-full bg-line"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-label="Upload progress"
      >
        <div
          className={`h-full rounded-full bg-lime transition-[width] duration-300 ${phase.kind === "checking" ? "animate-pulse" : ""}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function FutureLinks() {
  return (
    <details className="group text-sm text-muted">
      <summary className="cursor-pointer list-none rounded-md px-1 hover:text-ink">
        Paste a YouTube / TikTok / Instagram link? <span className="text-amber">Not supported yet</span>
      </summary>
      <div className="mt-2 flex gap-2">
        <input
          disabled
          aria-label="Video link (not supported yet)"
          placeholder="https://… — link import is a future feature"
          className="h-10 w-full min-w-0 rounded-xl border border-line bg-studio px-3 text-muted placeholder:text-muted/60 sm:w-80"
        />
      </div>
    </details>
  );
}

function LockIcon() {
  return (
    <svg viewBox="0 0 16 16" className="size-4 shrink-0 text-lime" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="3" y="7" width="10" height="7" rx="2" />
      <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" />
    </svg>
  );
}

function DropArt({ active }: { active: boolean }) {
  // An abstract movement arc + stick figure: illustrative only, not a tracking result.
  return (
    <svg
      viewBox="0 0 160 110"
      className={`relative h-24 w-auto transition-transform duration-500 sm:h-28 ${active ? "scale-110" : "group-hover:-translate-y-1"}`}
      aria-hidden
      fill="none"
    >
      <path d="M18 92 C 50 20, 110 20, 142 92" stroke="var(--color-line)" strokeWidth="2" strokeDasharray="3 6" />
      <path d="M30 70 C 60 30, 100 30, 130 70" stroke="var(--color-lime)" strokeOpacity={active ? 0.9 : 0.45} strokeWidth="2" strokeLinecap="round" />
      <g stroke="var(--color-ink)" strokeWidth="3" strokeLinecap="round">
        <path d="M80 40v26M80 46l-14-10M80 46l13 6M80 66l-10 20M80 66l12 18" />
      </g>
      <circle cx="80" cy="31" r="6" fill="var(--color-lime)" />
    </svg>
  );
}

"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  deletePractice,
  getMedia,
  getProject,
  getSections,
  listPractice,
  mediaHref,
  NetworkError,
  uploadPractice,
} from "@/lib/api";
import { extensionOf, formatBytes, formatDuration, newIdempotencyKey } from "@/lib/media";
import { percent } from "@/lib/pose";
import { formatClock, isPracticeBusy, practiceStatusLabel, recordingLimit } from "@/lib/practice";
import type { CaptureSource, PracticeSession, PracticeTarget, Project, Section } from "@/lib/types";

import { CameraRecorder, type CameraTake } from "./camera-recorder";
import { Panel } from "./studio-shell";
import { useStudioStatus } from "./studio-status";

type Load =
  | { kind: "pending" }
  | { kind: "ok"; project: Project; sections: Section[] }
  | { kind: "missing" }
  | { kind: "error"; message: string };

type Mode = "camera" | "upload";

interface Pending {
  file: File;
  source: CaptureSource;
  key: string;
}

export function PracticeStudio() {
  const { id } = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const { view, result } = useStudioStatus();
  const reachable = view.state === "READY" || view.state === "LIMITED";
  const maxDuration = result.kind === "ok" ? result.health.limits.max_duration_seconds : 120;
  const analysisOff = view.state === "LIMITED";

  const [load, setLoad] = useState<Load>({ kind: "pending" });
  const [scope, setScope] = useState<string | null>(search.get("section"));
  const [mode, setMode] = useState<Mode>("camera");
  const [attempts, setAttempts] = useState<PracticeSession[] | null>(null);
  const [refSrc, setRefSrc] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mirrorGuide, setMirrorGuide] = useState(true);
  const [canRetry, setCanRetry] = useState(false);
  const pendingRef = useRef<Pending | null>(null);
  const abortRef = useRef<(() => void) | null>(null);
  const uploadMirrored = useRef(false);

  useEffect(() => {
    if (!reachable) return;
    let cancelled = false;
    Promise.all([getProject(id), getSections(id).catch(() => null)])
      .then(([project, sections]) => {
        if (cancelled) return;
        setLoad({ kind: "ok", project, sections: sections?.sections ?? [] });
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

  const refreshAttempts = useCallback(() => {
    listPractice(id)
      .then((r) => setAttempts(r.sessions))
      .catch(() => setAttempts((a) => a ?? []));
  }, [id]);

  const ready = load.kind === "ok" && load.project.status === "analyzed";
  useEffect(() => {
    if (!ready) return;
    refreshAttempts();
    let cancelled = false;
    getMedia(id, "canonical")
      .then((m) => !cancelled && setRefSrc(mediaHref(m.url)))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [id, ready, refreshAttempts]);

  const busyAttempts = attempts?.some(isPracticeBusy) ?? false;
  useEffect(() => {
    if (!busyAttempts) return;
    const t = window.setInterval(refreshAttempts, 2000);
    return () => window.clearInterval(t);
  }, [busyAttempts, refreshAttempts]);

  const sections = load.kind === "ok" ? load.sections : [];
  const project = load.kind === "ok" ? load.project : null;
  const fullLength = project?.reference?.canonical_duration ?? project?.reference?.duration ?? 0;
  const activeSection = sections.find((s) => s.id === scope) ?? null;
  const target: PracticeTarget = useMemo(
    () =>
      activeSection
        ? { segment_id: activeSection.id, title: activeSection.title, start: activeSection.start, end: activeSection.end }
        : { segment_id: null, title: "Full dance", start: 0, end: fullLength },
    [activeSection, fullLength],
  );
  const limit = recordingLimit(target, maxDuration);

  const submit = (pending: Pending) => {
    pendingRef.current = pending;
    setError(null);
    setCanRetry(false);
    setProgress(0);
    const handle = uploadPractice({
      projectId: id,
      file: pending.file,
      segmentId: target.segment_id,
      captureSource: pending.source,
      mirrored: pending.source === "upload" ? uploadMirrored.current : false,
      idempotencyKey: pending.key,
      onProgress: setProgress,
    });
    abortRef.current = handle.abort;
    handle.promise
      .then((attempt) => {
        pendingRef.current = null;
        router.push(`/studio/practice/${attempt.id}`);
      })
      .catch((err: unknown) => {
        setProgress(null);
        setCanRetry(true);
        if (err instanceof NetworkError) setError("The upload was interrupted. Your take is still here — try again.");
        else if (err instanceof ApiError) setError(err.message);
        else if (err instanceof Error && err.name !== "UploadAborted") setError(err.message);
      });
  };
  const onTake = (take: CameraTake) => {
    // Same take → same key, so a retry after a dropped connection can't create a duplicate.
    const prev = pendingRef.current;
    const key = prev && prev.file === take.file ? prev.key : newIdempotencyKey();
    submit({ file: take.file, source: "webcam", key });
  };

  if (view.state === "OFFLINE") {
    return (
      <Wrap id={id}>
        <Panel tone="danger" title="The studio is offline">
          <p>{view.detail}</p>
        </Panel>
      </Wrap>
    );
  }
  if (load.kind === "pending") {
    return (
      <Wrap id={id}>
        <div className="mt-8 aspect-video w-full animate-pulse rounded-3xl border border-line bg-raised/50" aria-busy aria-label="Loading" />
      </Wrap>
    );
  }
  if (load.kind === "missing") {
    return (
      <Wrap id={id}>
        <Panel tone="amber" title="This dance isn't here">
          <p>It may have been deleted, or it belongs to a different private session.</p>
        </Panel>
      </Wrap>
    );
  }
  if (load.kind === "error") {
    return (
      <Wrap id={id}>
        <Panel tone="danger" title="Couldn't load this dance">
          <p>{load.message}</p>
        </Panel>
      </Wrap>
    );
  }
  const p = load.project;
  if (p.status !== "analyzed") {
    return (
      <Wrap id={id}>
        <h1 className="mt-3 font-display text-3xl font-bold tracking-tight sm:text-5xl">{p.title}</h1>
        <div className="mt-8">
          <Panel tone="amber" title="Analyse this dance first">
            <p>Practice compares your moves with the dance&apos;s measured moves, so the dance needs to be analysed before you record an attempt.</p>
            <Link href={`/studio/projects/${id}`} className="mt-3 inline-block text-lime underline-offset-4 hover:underline">
              Go to the dance →
            </Link>
          </Panel>
        </div>
      </Wrap>
    );
  }

  const uploading = progress !== null;

  return (
    <Wrap id={id}>
      <p className="mt-6 font-mono text-[11px] uppercase tracking-[0.18em] text-lime">Practice</p>
      <h1 className="mt-2 font-display text-3xl font-bold tracking-tight sm:text-5xl">{p.title}</h1>

      <fieldset className="mt-6">
        <legend className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">What are you practising?</legend>
        <div className="mt-2 flex gap-2 overflow-x-auto pb-1" role="radiogroup" aria-label="Practice target">
          <ScopeChip active={scope === null} onClick={() => setScope(null)} label="Full dance" detail={formatDuration(fullLength)} />
          {sections.map((s) => (
            <ScopeChip
              key={s.id}
              active={scope === s.id}
              onClick={() => setScope(s.id)}
              label={s.title}
              detail={`${formatClock(s.start)}–${formatClock(s.end)}`}
              done={s.completed}
            />
          ))}
        </div>
      </fieldset>

      <div className="mt-6 grid gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0">
          <div className="mb-4 inline-flex rounded-full border border-line p-1" role="tablist" aria-label="How to add your attempt">
            {(["camera", "upload"] as const).map((m) => (
              <button
                key={m}
                type="button"
                role="tab"
                aria-selected={mode === m}
                data-testid={`mode-${m}`}
                onClick={() => setMode(m)}
                className={`rounded-full px-4 py-2 font-display text-[11px] font-semibold uppercase tracking-[0.12em] transition ${
                  mode === m ? "bg-lime text-studio" : "text-muted hover:text-ink"
                }`}
              >
                {m === "camera" ? "Record with camera" : "Upload a video"}
              </button>
            ))}
          </div>

          {mode === "camera" ? (
            <CameraRecorder
              key={target.segment_id ?? "full"}
              limitSeconds={limit}
              busy={uploading}
              onUse={onTake}
              onUploadInstead={() => setMode("upload")}
              guide={
                refSrc
                  ? (s) => <ReferenceGuide src={refSrc} target={target} recording={s.recording} countdown={s.countdown} mirror={mirrorGuide} />
                  : undefined
              }
            />
          ) : (
            <AttemptFilePicker
              busy={uploading}
              maxDuration={maxDuration}
              onSubmit={(file, mirrored) => {
                uploadMirrored.current = mirrored;
                const prev = pendingRef.current;
                const key = prev && prev.file === file ? prev.key : newIdempotencyKey();
                submit({ file, source: "upload", key });
              }}
            />
          )}

          {uploading && (
            <div className="mt-4 rounded-2xl border border-lime/30 bg-lime/5 p-4" role="status" aria-live="polite">
              <div className="flex items-center justify-between text-sm">
                <span>Uploading your attempt privately…</span>
                <span className="font-mono">{Math.round((progress ?? 0) * 100)}%</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-line">
                <div className="h-full bg-lime transition-[width]" style={{ width: `${Math.round((progress ?? 0) * 100)}%` }} />
              </div>
              <button type="button" onClick={() => abortRef.current?.()} className="mt-2 text-xs text-muted hover:text-ink">
                Cancel upload
              </button>
            </div>
          )}
          {error && (
            <div className="mt-4 rounded-2xl border border-danger/40 bg-danger/5 p-4 text-sm" role="alert">
              <p className="text-ink">{error}</p>
              {canRetry && (
                <button type="button" onClick={() => pendingRef.current && submit(pendingRef.current)} className="mt-2 text-lime underline-offset-4 hover:underline">
                  Try the upload again
                </button>
              )}
            </div>
          )}
        </div>

        <aside className="flex flex-col gap-5">
          <div className="rounded-3xl border border-line bg-raised/60 p-5">
            <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Target</p>
            <p className="mt-1 font-display text-xl font-semibold" data-testid="practice-target">
              {target.title}
            </p>
            <p className="mt-1 font-mono text-xs text-muted">
              {formatClock(target.start)}–{formatClock(target.end)} of the reference · record up to {formatClock(limit)}
            </p>
            <label className="mt-4 flex items-center justify-between gap-4 text-sm">
              <span>Mirror the guide video</span>
              <input type="checkbox" checked={mirrorGuide} onChange={(e) => setMirrorGuide(e.target.checked)} className="size-5 accent-[var(--color-lime)]" />
            </label>
            <p className="mt-3 text-xs leading-relaxed text-muted">
              While you record, the reference section plays in the corner so you can dance along. After upload, your
              attempt goes through the same pose tracker as the reference.
            </p>
            {analysisOff && (
              <p className="mt-3 rounded-xl border border-amber/40 bg-amber/5 p-3 text-xs text-amber">
                Limited mode: attempts are stored, but movement analysis is off on this server. Nothing will be made up.
              </p>
            )}
          </div>

          <AttemptList
            attempts={attempts}
            onDelete={async (a) => {
              await deletePractice(a.id);
              refreshAttempts();
            }}
          />
        </aside>
      </div>
    </Wrap>
  );
}

function ScopeChip({ active, onClick, label, detail, done }: { active: boolean; onClick: () => void; label: string; detail: string; done?: boolean }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      onClick={onClick}
      className={`shrink-0 rounded-2xl border px-4 py-2.5 text-left transition ${
        active ? "border-lime bg-lime/10" : "border-line hover:border-lime/50"
      }`}
    >
      <span className={`block text-sm font-semibold ${active ? "text-lime" : "text-ink"}`}>
        {done && <span aria-label="completed">✓ </span>}
        {label}
      </span>
      <span className="block font-mono text-[11px] text-muted">{detail}</span>
    </button>
  );
}

/** Muted reference section playing alongside the camera; starts with the recording. */
function ReferenceGuide({
  src,
  target,
  recording,
  countdown,
  mirror,
}: {
  src: string;
  target: PracticeTarget;
  recording: boolean;
  countdown: number | null;
  mirror: boolean;
}) {
  const ref = useRef<HTMLVideoElement | null>(null);
  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    if (recording) {
      v.currentTime = target.start;
      void v.play().catch(() => {});
    } else {
      v.pause();
      if (countdown !== null || !recording) v.currentTime = target.start;
    }
  }, [recording, countdown, target.start]);
  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    const onTime = () => {
      if (v.currentTime >= target.end) v.pause();
    };
    v.addEventListener("timeupdate", onTime);
    return () => v.removeEventListener("timeupdate", onTime);
  }, [target.end]);
  return (
    <div className="relative aspect-video">
      <video
        ref={ref}
        src={`${src}#t=${target.start}`}
        muted
        playsInline
        preload="auto"
        data-testid="reference-guide"
        className={`absolute inset-0 h-full w-full object-contain ${mirror ? "-scale-x-100" : ""}`}
      />
      <span className="absolute left-2 top-2 rounded-full bg-black/70 px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.14em] text-lime">
        Reference
      </span>
    </div>
  );
}

function AttemptFilePicker({
  busy,
  maxDuration,
  onSubmit,
}: {
  busy: boolean;
  maxDuration: number;
  onSubmit: (file: File, mirrored: boolean) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [mirrored, setMirrored] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [seconds, setSeconds] = useState<number | null>(null);

  useEffect(() => {
    if (!url) return;
    return () => URL.revokeObjectURL(url);
  }, [url]);

  const pick = (f: File | null) => {
    setProblem(null);
    setSeconds(null);
    if (!f) return;
    if (![".mp4", ".mov", ".webm"].includes(extensionOf(f.name))) {
      setProblem("Choose an MP4, MOV or WebM video.");
      return;
    }
    setFile(f);
    setUrl(URL.createObjectURL(f));
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="relative overflow-hidden rounded-3xl border border-dashed border-line bg-raised/40">
        {file && url ? (
          <div className="relative aspect-video bg-black">
            <video
              src={url}
              controls
              playsInline
              className="absolute inset-0 h-full w-full object-contain"
              onLoadedMetadata={(e) => setSeconds(Number.isFinite(e.currentTarget.duration) ? e.currentTarget.duration : null)}
            />
          </div>
        ) : (
          <label className="flex aspect-video cursor-pointer flex-col items-center justify-center gap-3 p-6 text-center focus-within:ring-2 focus-within:ring-lime">
            <span className="font-display text-lg font-semibold">Choose a video of your attempt</span>
            <span className="text-sm text-muted">MP4, MOV or WebM · up to {formatClock(maxDuration)} · one dancer, whole body in frame</span>
            <span className="rounded-full bg-lime px-5 py-2.5 font-display text-xs font-semibold uppercase tracking-[0.12em] text-studio">Browse files</span>
            <input
              type="file"
              accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm"
              className="sr-only"
              data-testid="attempt-file"
              onChange={(e) => pick(e.target.files?.[0] ?? null)}
            />
          </label>
        )}
      </div>
      {problem && (
        <p className="text-sm text-danger" role="alert">
          {problem}
        </p>
      )}
      {file && (
        <>
          <p className="font-mono text-xs text-muted">
            {file.name} · {formatBytes(file.size)}
            {seconds !== null && ` · ${formatDuration(seconds)}`}
          </p>
          {seconds !== null && seconds > maxDuration && (
            <p className="text-sm text-amber">This video is longer than {formatClock(maxDuration)}; trim it first.</p>
          )}
          <label className="flex items-center gap-3 text-sm">
            <input type="checkbox" checked={mirrored} onChange={(e) => setMirrored(e.target.checked)} className="size-5 accent-[var(--color-lime)]" />
            <span>This video is mirrored (e.g. saved from a selfie app)</span>
          </label>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              disabled={busy}
              data-testid="submit-file"
              onClick={() => onSubmit(file, mirrored)}
              className="inline-flex h-12 items-center justify-center rounded-full bg-lime px-6 font-display text-xs font-semibold uppercase tracking-[0.12em] text-studio transition enabled:hover:-translate-y-0.5 disabled:opacity-60"
            >
              {busy ? "Uploading…" : "Upload attempt"}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setFile(null);
                setUrl(null);
              }}
              className="inline-flex h-12 items-center justify-center rounded-full border border-line px-6 font-display text-xs font-semibold uppercase tracking-[0.12em] text-ink disabled:opacity-50"
            >
              Choose another
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function AttemptList({ attempts, onDelete }: { attempts: PracticeSession[] | null; onDelete: (a: PracticeSession) => Promise<void> }) {
  const [confirm, setConfirm] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  return (
    <section aria-labelledby="attempts-title" className="rounded-3xl border border-line p-5">
      <h2 id="attempts-title" className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">
        Your attempts
      </h2>
      {attempts === null ? (
        <p className="mt-3 animate-pulse text-sm text-muted">Loading…</p>
      ) : attempts.length === 0 ? (
        <p className="mt-3 text-sm text-muted">No attempts yet. Record one — it stays private to you.</p>
      ) : (
        <ul className="mt-3 flex flex-col gap-2" data-testid="attempt-list">
          {attempts.map((a) => (
            <li key={a.id} className="rounded-2xl border border-line/70 bg-raised/40 p-3">
              <div className="flex items-start justify-between gap-3">
                <Link href={`/studio/practice/${a.id}`} className="min-w-0 flex-1 rounded-lg focus-visible:outline-2 focus-visible:outline-lime">
                  <span className="block truncate text-sm font-semibold text-ink">{a.target.title}</span>
                  <span className="block font-mono text-[11px] text-muted">
                    {a.capture_source === "webcam" ? "Camera" : "Upload"} · {new Date(a.created_at).toLocaleString()}
                  </span>
                </Link>
                <AttemptChip attempt={a} />
              </div>
              <div className="mt-2 flex items-center justify-between text-xs text-muted">
                <span>
                  {a.score?.overall != null && (
                    <span className="mr-2 font-display font-semibold text-lime" data-testid="attempt-list-score">
                      {Math.round(a.score.overall)}
                      <span className="text-muted">/100{a.score.status === "qualified" ? " · low confidence" : ""}</span> ·
                    </span>
                  )}
                  {a.tracking_coverage !== null ? `Body tracked ${percent(a.tracking_coverage)}` : a.duration ? formatDuration(a.duration) : ""}
                </span>
                {confirm === a.id ? (
                  <span className="flex gap-2">
                    <button type="button" onClick={() => setConfirm(null)} className="hover:text-ink">
                      Keep
                    </button>
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          await onDelete(a);
                          setConfirm(null);
                        } catch {
                          setFailed(a.id);
                        }
                      }}
                      className="font-semibold text-danger"
                    >
                      Delete
                    </button>
                  </span>
                ) : (
                  <button type="button" onClick={() => setConfirm(a.id)} className="hover:text-danger" aria-label={`Delete attempt: ${a.target.title}`}>
                    Delete
                  </button>
                )}
              </div>
              {failed === a.id && <p className="mt-1 text-xs text-danger">Delete failed. Try again.</p>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function AttemptChip({ attempt }: { attempt: PracticeSession }) {
  const tone =
    attempt.status === "analyzed"
      ? "bg-lime/15 text-lime"
      : attempt.status === "failed"
        ? "bg-danger/15 text-danger"
        : isPracticeBusy(attempt)
          ? "bg-amber/15 text-amber"
          : "bg-raised-2 text-muted";
  return (
    <span className={`shrink-0 rounded-full px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] ${tone}`}>
      {practiceStatusLabel(attempt)}
      {isPracticeBusy(attempt) && ` ${Math.round(attempt.progress * 100)}%`}
    </span>
  );
}

function Wrap({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-8 sm:py-12">
      <Link href={`/studio/projects/${id}`} className="inline-flex items-center gap-2 text-sm text-muted transition hover:text-ink">
        <span aria-hidden>←</span> Back to the dance
      </Link>
      {children}
    </div>
  );
}

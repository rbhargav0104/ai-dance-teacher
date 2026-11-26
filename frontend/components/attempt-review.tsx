"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  deletePractice,
  getMedia,
  getPoses,
  getPractice,
  getPracticeMedia,
  getPracticePoses,
  mediaHref,
  startPracticeAnalysis,
} from "@/lib/api";
import { formatDuration } from "@/lib/media";
import { FAILURE_HELP, percent, stageLabel } from "@/lib/pose";
import {
  PRACTICE_WARNINGS,
  formatClock,
  isPracticeBusy,
  needsResync,
  referenceTimeFor,
  reviewLength,
} from "@/lib/practice";
import type { PosesResponse, PracticeSession } from "@/lib/types";

import { ProgressRing } from "./analysis-status";
import { AttemptChip } from "./practice-studio";
import { SkeletonOverlay } from "./skeleton-overlay";
import { Panel } from "./studio-shell";
import { useStudioStatus } from "./studio-status";

type Load = { kind: "pending" } | { kind: "ok"; attempt: PracticeSession } | { kind: "missing" } | { kind: "error"; message: string };

const SPEEDS = [0.5, 0.75, 1] as const;

export function AttemptReview() {
  const { sid } = useParams<{ sid: string }>();
  const router = useRouter();
  const { view } = useStudioStatus();
  const reachable = view.state === "READY" || view.state === "LIMITED";
  const [load, setLoad] = useState<Load>({ kind: "pending" });
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const fetchAttempt = useCallback(
    () =>
      getPractice(sid)
        .then((attempt) => setLoad({ kind: "ok", attempt }))
        .catch((err: unknown) => {
          if (err instanceof ApiError && err.status === 404) setLoad({ kind: "missing" });
          else setLoad((l) => (l.kind === "ok" ? l : { kind: "error", message: err instanceof Error ? err.message : "Could not load this attempt." }));
        }),
    [sid],
  );

  useEffect(() => {
    if (reachable) void fetchAttempt();
  }, [reachable, fetchAttempt]);

  const attempt = load.kind === "ok" ? load.attempt : null;
  const busy = attempt ? isPracticeBusy(attempt) : false;
  useEffect(() => {
    if (!busy) return;
    const t = window.setInterval(() => void fetchAttempt(), 1500);
    return () => window.clearInterval(t);
  }, [busy, fetchAttempt]);

  if (view.state === "OFFLINE") {
    return (
      <Wrap projectId={null}>
        <Panel tone="danger" title="The studio is offline">
          <p>{view.detail}</p>
        </Panel>
      </Wrap>
    );
  }
  if (load.kind === "pending") {
    return (
      <Wrap projectId={null}>
        <div className="mt-8 aspect-video w-full animate-pulse rounded-3xl border border-line bg-raised/50" aria-busy aria-label="Loading attempt" />
      </Wrap>
    );
  }
  if (load.kind === "missing") {
    return (
      <Wrap projectId={null}>
        <Panel tone="amber" title="This attempt isn't here">
          <p>It may have been deleted, or it belongs to a different private session.</p>
        </Panel>
      </Wrap>
    );
  }
  if (load.kind === "error") {
    return (
      <Wrap projectId={null}>
        <Panel tone="danger" title="Couldn't load this attempt">
          <p>{load.message}</p>
        </Panel>
      </Wrap>
    );
  }

  const a = load.attempt;
  const practiceHref = `/studio/projects/${a.project_id}/practice${a.target.segment_id ? `?section=${encodeURIComponent(a.target.segment_id)}` : ""}`;

  return (
    <Wrap projectId={a.project_id}>
      <div className="mt-6 flex flex-wrap items-center gap-3">
        <AttemptChip attempt={a} />
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
          {a.capture_source === "webcam" ? "Camera recording" : "Uploaded video"} · {new Date(a.created_at).toLocaleString()}
        </span>
      </div>
      <h1 className="mt-3 font-display text-3xl font-bold tracking-tight sm:text-5xl">
        Your attempt <span className="text-muted">·</span> <span className="text-lime">{a.target.title}</span>
      </h1>

      {a.status === "analyzed" ? (
        <SideBySide attempt={a} />
      ) : busy ? (
        <div className="mt-8 flex items-center gap-4 rounded-3xl border border-lime/30 bg-lime/5 p-6" role="status" aria-live="polite" data-testid="attempt-progress">
          <div className="relative">
            <ProgressRing value={a.latest_job?.progress ?? 0} size={72} />
            <span className="absolute inset-0 flex items-center justify-center font-mono text-xs">{Math.round((a.latest_job?.progress ?? 0) * 100)}%</span>
          </div>
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-lime">{a.status === "queued" ? "Queued" : "Measuring your movement"}</p>
            <p className="mt-1 text-ink">{a.latest_job?.message ?? stageLabel(a.latest_job?.stage)}</p>
            <p className="mt-1 text-xs text-muted">Same tracker, smoothing and quality checks as the reference. You can leave this page.</p>
          </div>
        </div>
      ) : a.status === "failed" ? (
        <div className="mt-8 rounded-3xl border border-danger/40 bg-danger/5 p-6" role="alert" data-testid="attempt-failed">
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-danger">We couldn&apos;t measure this attempt</p>
          <p className="mt-2 text-ink">{a.error_message ?? "Analysis failed."}</p>
          {FAILURE_HELP[a.error_code ?? ""] && <p className="mt-2 text-sm text-muted">{FAILURE_HELP[a.error_code ?? ""]}</p>}
          <div className="mt-4 flex flex-wrap gap-3">
            <Link href={practiceHref} className="inline-flex h-11 items-center rounded-full bg-lime px-5 font-display text-xs font-semibold uppercase tracking-[0.12em] text-studio">
              Record again
            </Link>
            {a.latest_job?.retryable && (
              <RetryButton id={a.id} onDone={fetchAttempt} setNotice={setNotice} label="Try the analysis again" />
            )}
          </div>
        </div>
      ) : (
        <div className="mt-8 rounded-3xl border border-amber/40 bg-amber/5 p-6" data-testid="attempt-stored">
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-amber">Stored privately · not analysed</p>
          <p className="mt-2 text-ink">
            {view.state === "LIMITED"
              ? "Movement analysis is off on this server right now, so there is nothing to show yet — we won't invent results."
              : "This attempt hasn't been analysed yet."}
          </p>
          {view.state === "READY" && <RetryButton id={a.id} onDone={fetchAttempt} setNotice={setNotice} label="Analyse now" />}
        </div>
      )}
      {notice && (
        <p className="mt-3 text-sm text-amber" role="status">
          {notice}
        </p>
      )}

      <div className="mt-8 flex flex-wrap items-center gap-3 border-t border-line/70 pt-6">
        <Link href={practiceHref} className="inline-flex h-11 items-center rounded-full border border-lime/60 px-5 font-display text-xs font-semibold uppercase tracking-[0.12em] text-lime transition hover:-translate-y-0.5" data-testid="record-again">
          Record another attempt
        </Link>
        <Link href={`/studio/projects/${a.project_id}`} className="inline-flex h-11 items-center rounded-full border border-line px-5 font-display text-xs font-semibold uppercase tracking-[0.12em] text-ink hover:border-lime/60">
          Back to learning
        </Link>
        <span className="ml-auto">
          {confirmDelete ? (
            <span className="flex items-center gap-3 text-sm">
              <span className="text-muted">Delete this attempt and its video?</span>
              <button type="button" onClick={() => setConfirmDelete(false)} className="text-muted hover:text-ink">
                Keep
              </button>
              <button
                type="button"
                onClick={async () => {
                  try {
                    await deletePractice(a.id);
                    router.push(practiceHref);
                  } catch {
                    setNotice("Delete failed. Try again.");
                  }
                }}
                className="rounded-full bg-danger px-4 py-2 font-semibold text-studio"
              >
                Delete
              </button>
            </span>
          ) : (
            <button type="button" onClick={() => setConfirmDelete(true)} className="text-sm text-muted hover:text-danger">
              Delete this attempt
            </button>
          )}
        </span>
      </div>
    </Wrap>
  );
}

function RetryButton({ id, onDone, setNotice, label }: { id: string; onDone: () => void; setNotice: (s: string | null) => void; label: string }) {
  const [starting, setStarting] = useState(false);
  return (
    <button
      type="button"
      disabled={starting}
      onClick={async () => {
        setStarting(true);
        setNotice(null);
        try {
          await startPracticeAnalysis(id, true);
          onDone();
        } catch (err) {
          setNotice(err instanceof Error ? err.message : "Could not start the analysis.");
        } finally {
          setStarting(false);
        }
      }}
      className="mt-4 inline-flex h-11 items-center rounded-full border border-line px-5 font-display text-xs font-semibold uppercase tracking-[0.12em] text-ink hover:border-lime/60 disabled:opacity-60"
    >
      {starting ? "Starting…" : label}
    </button>
  );
}

/**
 * Reference section and learner attempt side by side, one transport. Both start at the
 * beginning of what was practised; the learner video leads and the reference follows
 * (re-seeked when it drifts). This is time-lined-up playback, not movement alignment —
 * alignment and comparison arrive with Outcome 6.
 */
function SideBySide({ attempt }: { attempt: PracticeSession }) {
  const refVideo = useRef<HTMLVideoElement | null>(null);
  const learnerVideo = useRef<HTMLVideoElement | null>(null);
  const [refSrc, setRefSrc] = useState<string | null>(null);
  const [learnerSrc, setLearnerSrc] = useState<string | null>(null);
  const [refPoses, setRefPoses] = useState<PosesResponse | null>(null);
  const [learnerPoses, setLearnerPoses] = useState<PosesResponse | null>(null);
  const [playing, setPlaying] = useState(false);
  const [t, setT] = useState(0);
  const [speed, setSpeed] = useState<(typeof SPEEDS)[number]>(1);
  const [skeleton, setSkeleton] = useState(true);
  const [mirror, setMirror] = useState(false);
  const [mediaError, setMediaError] = useState<string | null>(null);
  const target = attempt.target;
  const length = reviewLength(target, attempt.canonical_duration);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getMedia(attempt.project_id, "canonical"), getPracticeMedia(attempt.id, "canonical")])
      .then(([r, l]) => {
        if (cancelled) return;
        setRefSrc(mediaHref(r.url));
        setLearnerSrc(mediaHref(l.url));
      })
      .catch(() => !cancelled && setMediaError("Couldn't load the videos. Refresh to try again."));
    getPoses(attempt.project_id)
      .then((p) => !cancelled && setRefPoses(p))
      .catch(() => {});
    getPracticePoses(attempt.id)
      .then((p) => !cancelled && setLearnerPoses(p))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [attempt.id, attempt.project_id]);

  const seek = useCallback(
    (s: number) => {
      const clamped = Math.max(0, Math.min(length, s));
      if (learnerVideo.current) learnerVideo.current.currentTime = clamped;
      if (refVideo.current) refVideo.current.currentTime = referenceTimeFor(target, clamped);
      setT(clamped);
    },
    [length, target],
  );

  // Lock-step loop: the learner leads, the reference is corrected when it drifts.
  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    const tick = () => {
      const l = learnerVideo.current;
      const r = refVideo.current;
      if (l && r) {
        const lt = l.currentTime;
        const want = referenceTimeFor(target, lt);
        if (needsResync(want, r.currentTime)) r.currentTime = want;
        setT(lt);
        if (lt >= length - 0.02 || l.ended) {
          l.pause();
          r.pause();
          setPlaying(false);
          return;
        }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, length, target]);

  useEffect(() => {
    for (const v of [learnerVideo.current, refVideo.current]) if (v) v.playbackRate = speed;
  }, [speed]);

  const play = async () => {
    const l = learnerVideo.current;
    const r = refVideo.current;
    if (!l || !r) return;
    if (t >= length - 0.05) seek(0);
    r.currentTime = referenceTimeFor(target, l.currentTime);
    l.playbackRate = speed;
    r.playbackRate = speed;
    try {
      await Promise.all([l.play(), r.play()]);
      setPlaying(true);
    } catch {
      l.pause();
      r.pause();
      setPlaying(false);
    }
  };
  const pause = () => {
    learnerVideo.current?.pause();
    refVideo.current?.pause();
    setPlaying(false);
  };

  const q = attempt.quality;
  const warnings = attempt.warnings.filter((w) => PRACTICE_WARNINGS[w]);

  return (
    <div className="mt-8" data-testid="side-by-side">
      {mediaError && (
        <p className="mb-4 text-sm text-danger" role="alert">
          {mediaError}
        </p>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        <Pane label="Reference" sub={`${formatClock(target.start)}–${formatClock(target.end)}`} mirror={mirror}>
          {refSrc && (
            <>
              <video
                ref={refVideo}
                src={refSrc}
                muted
                playsInline
                preload="auto"
                data-testid="review-reference"
                onLoadedMetadata={(e) => {
                  e.currentTarget.currentTime = referenceTimeFor(target, t);
                }}
                className="absolute inset-0 h-full w-full object-contain"
              />
              {skeleton && refPoses && <SkeletonOverlay videoRef={refVideo} poses={refPoses} options={{ trails: false }} />}
            </>
          )}
        </Pane>
        <Pane label="You" sub={attempt.canonical_duration ? formatDuration(attempt.canonical_duration) : ""} mirror={mirror} accent>
          {learnerSrc && (
            <>
              <video
                ref={learnerVideo}
                src={learnerSrc}
                muted
                playsInline
                preload="auto"
                data-testid="review-learner"
                className="absolute inset-0 h-full w-full object-contain"
              />
              {skeleton && learnerPoses && <SkeletonOverlay videoRef={learnerVideo} poses={learnerPoses} options={{ trails: false }} />}
            </>
          )}
        </Pane>
      </div>

      <div className="mt-4 flex flex-col gap-3 rounded-3xl border border-line bg-raised/50 p-4 sm:flex-row sm:items-center">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={playing ? pause : play}
            data-testid="review-play"
            aria-label={playing ? "Pause both videos" : "Play both videos"}
            className="inline-flex size-12 items-center justify-center rounded-full bg-lime text-studio transition hover:scale-105"
          >
            {playing ? (
              <svg viewBox="0 0 24 24" className="size-5" aria-hidden>
                <path d="M6 5h4v14H6zM14 5h4v14h-4z" fill="currentColor" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" className="size-5" aria-hidden>
                <path d="M7 4.5v15l13-7.5z" fill="currentColor" />
              </svg>
            )}
          </button>
          <button type="button" onClick={() => seek(0)} className="rounded-full border border-line px-3 py-2 text-sm hover:border-lime/60" aria-label="Back to the start">
            ⟲
          </button>
        </div>
        <label className="flex min-w-0 flex-1 items-center gap-3">
          <span className="sr-only">Position</span>
          <input
            type="range"
            min={0}
            max={Math.max(0.01, length)}
            step={1 / 24}
            value={Math.min(t, length)}
            onChange={(e) => {
              pause();
              seek(Number(e.target.value));
            }}
            className="w-full accent-[var(--color-lime)]"
            data-testid="review-scrub"
          />
          <span className="shrink-0 font-mono text-xs text-muted" data-testid="review-clock">
            {formatClock(t)} / {formatClock(length)}
          </span>
        </label>
        <div className="flex flex-wrap items-center gap-2">
          {SPEEDS.map((s) => (
            <button
              key={s}
              type="button"
              aria-pressed={speed === s}
              onClick={() => setSpeed(s)}
              className={`rounded-full px-3 py-1.5 font-mono text-xs ${speed === s ? "bg-lime text-studio" : "border border-line text-muted hover:text-ink"}`}
            >
              {s}×
            </button>
          ))}
          <Toggle on={skeleton} set={setSkeleton} label="Skeleton" />
          <Toggle on={mirror} set={setMirror} label="Mirror" />
        </div>
      </div>
      <p className="mt-2 text-xs text-muted">
        Both videos start at the beginning of {target.segment_id ? "the section" : "the dance"} and play in step. Movement alignment and scoring
        come next — nothing on this page is a score.
      </p>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <dl className="grid grid-cols-3 gap-px self-start overflow-hidden rounded-2xl border border-line bg-line" data-testid="attempt-tracking">
          <Stat label="Body tracked" value={percent(attempt.tracking_coverage)} hint="Share of frames where your shoulders and hips were clearly visible. Not a dance score." />
          <Stat label="Frames" value={q ? `${q.valid_frames}/${q.analyzed_frames}` : "—"} hint="Valid / analysed frames (12 per second)." />
          <Stat label="Joint confidence" value={percent(q?.measured_joint_confidence ?? q?.mean_confidence)} hint="How sure the tracker is about the joints it could see. Not a dance score." />
        </dl>
        <div className="rounded-2xl border border-line p-4 text-sm">
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Tracking notes</p>
          {warnings.length ? (
            <ul className="mt-2 space-y-1.5 text-amber">
              {warnings.map((w) => (
                <li key={w}>· {PRACTICE_WARNINGS[w]}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-muted">Clean tracking — nothing to flag.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function Pane({ label, sub, mirror, accent, children }: { label: string; sub: string; mirror: boolean; accent?: boolean; children: React.ReactNode }) {
  return (
    <figure className={`relative overflow-hidden rounded-3xl border bg-black ${accent ? "border-lime/50" : "border-line"}`}>
      <div className={`relative aspect-video w-full ${mirror ? "-scale-x-100" : ""}`}>{children}</div>
      <figcaption className="pointer-events-none absolute left-3 top-3 flex items-center gap-2 rounded-full bg-black/70 px-3 py-1 font-mono text-[10px] uppercase tracking-[0.14em]">
        <span className={accent ? "text-lime" : "text-ink"}>{label}</span>
        {sub && <span className="text-muted">{sub}</span>}
      </figcaption>
    </figure>
  );
}

function Toggle({ on, set, label }: { on: boolean; set: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={() => set(!on)}
      className={`rounded-full px-3 py-1.5 text-xs ${on ? "border border-lime/60 text-lime" : "border border-line text-muted hover:text-ink"}`}
    >
      {label}
    </button>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="bg-studio px-3 py-3" title={hint}>
      <dt className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{label}</dt>
      <dd className="mt-1 font-display text-lg font-semibold text-ink">{value}</dd>
    </div>
  );
}

function Wrap({ projectId, children }: { projectId: string | null; children: React.ReactNode }) {
  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-8 sm:py-12">
      <Link
        href={projectId ? `/studio/projects/${projectId}/practice` : "/studio"}
        className="inline-flex items-center gap-2 text-sm text-muted transition hover:text-ink"
      >
        <span aria-hidden>←</span> {projectId ? "All attempts" : "All dances"}
      </Link>
      {children}
    </div>
  );
}

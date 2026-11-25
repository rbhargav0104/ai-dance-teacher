"use client";

import { FAILURE_HELP, percent, stageLabel } from "@/lib/pose";
import type { Project } from "@/lib/types";

export function ProgressRing({ value, size = 64 }: { value: number; size?: number }) {
  const r = (size - 8) / 2;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(1, value));
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden className="-rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-line)" strokeWidth={6} />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="var(--color-lime)"
        strokeWidth={6}
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={c * (1 - v)}
        className="transition-[stroke-dashoffset] duration-500"
      />
    </svg>
  );
}

/** Honest job progress: the stage and fraction come straight from the worker's heartbeat. */
export function AnalysisProgress({ project }: { project: Project }) {
  const job = project.latest_job;
  const busy = project.status === "queued" || project.status === "processing";
  if (!busy) return null;
  const progress = job?.progress ?? 0;
  return (
    <div className="flex items-center gap-4 rounded-2xl border border-lime/30 bg-lime/5 p-4" role="status" aria-live="polite">
      <div className="relative">
        <ProgressRing value={progress} />
        <span className="absolute inset-0 flex items-center justify-center font-mono text-xs text-ink">
          {Math.round(progress * 100)}%
        </span>
      </div>
      <div className="min-w-0">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-lime">
          {project.status === "queued" ? "Queued" : "Analyzing"}
        </p>
        <p className="mt-1 text-sm text-ink">{stageLabel(job?.stage)}</p>
        <p className="mt-1 text-xs text-muted">You can leave this page — the analysis keeps running.</p>
      </div>
    </div>
  );
}

// The server's message for these already says what to do.
const SELF_EXPLAINED = new Set(["multiple_people", "low_coverage", "no_dancer_detected"]);

export function AnalysisFailure({ project }: { project: Project }) {
  if (project.status !== "failed") return null;
  const code = project.error_code ?? "";
  return (
    <div className="rounded-2xl border border-danger/40 bg-danger/5 p-4" role="alert">
      <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-danger">Analysis stopped</p>
      <p className="mt-1 text-sm text-ink">{project.error_message ?? "Analysis failed."}</p>
      {FAILURE_HELP[code] && !SELF_EXPLAINED.has(code) && <p className="mt-2 text-sm text-muted">{FAILURE_HELP[code]}</p>}
    </div>
  );
}

export function TrackingSummary({ project }: { project: Project }) {
  const q = project.reference?.quality;
  if (!q) return null;
  return (
    <dl className="grid grid-cols-3 gap-px overflow-hidden rounded-2xl border border-line bg-line">
      <Stat label="Body tracked" value={percent(q.coverage)} hint="Share of analysed frames where shoulders and hips were clearly visible." />
      <Stat label="Frames" value={`${q.valid_frames}/${q.analyzed_frames}`} hint="Valid / analysed frames (12 per second)." />
      <Stat
        label="Joint confidence"
        value={percent(q.measured_joint_confidence ?? q.mean_confidence)}
        hint="How sure the tracker is about the joints it could see. This is not a dance score."
      />
    </dl>
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

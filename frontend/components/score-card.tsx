"use client";

import { useEffect, useState } from "react";

import { ApiError, getPracticeReport } from "@/lib/api";
import { formatClock } from "@/lib/practice";
import {
  COMPONENTS,
  SCORE_WARNINGS,
  evidenceText,
  hasNumbers,
  partsText,
  qualifierText,
  scoreText,
  scoreTone,
  sectionExtremes,
  statusHeadline,
  weightText,
  type ScoreTone,
} from "@/lib/score";
import type { ScoreReport } from "@/lib/types";

const TONE_TEXT: Record<ScoreTone, string> = { lime: "text-lime", track: "text-track", amber: "text-amber", danger: "text-danger" };
const TONE_BAR: Record<ScoreTone, string> = { lime: "bg-lime", track: "bg-track", amber: "bg-amber", danger: "bg-danger" };

type Load = { kind: "pending" } | { kind: "ok"; report: ScoreReport } | { kind: "error"; message: string };

/**
 * The versioned score of an attempt (Outcome 7). Numbers appear only when the backend scored
 * the attempt; suppressed / unscorable attempts show the measured reason instead. Moments link
 * back into the side-by-side player through `onSeek` (attempt seconds).
 */
export function ScoreCard({ attemptId, onSeek }: { attemptId: string; onSeek: (learnerT: number) => void }) {
  const [load, setLoad] = useState<Load>({ kind: "pending" });

  useEffect(() => {
    let cancelled = false;
    getPracticeReport(attemptId)
      .then((r) => !cancelled && setLoad({ kind: "ok", report: r.report }))
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError && err.status === 503
            ? "Scoring is off on this server right now — we won't estimate one."
            : err instanceof Error
              ? err.message
              : "The score isn't available.";
        setLoad({ kind: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, [attemptId]);

  if (load.kind === "pending") {
    return (
      <section className="mt-6 h-48 animate-pulse rounded-3xl border border-line bg-raised/50" aria-busy aria-label="Scoring your attempt" data-testid="score-loading" />
    );
  }
  if (load.kind === "error") {
    return (
      <section className="mt-6 rounded-3xl border border-amber/40 bg-amber/5 p-5" data-testid="score-error" role="status">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-amber">Score unavailable</p>
        <p className="mt-2 text-ink">{load.message}</p>
      </section>
    );
  }
  const r = load.report;
  const numbers = hasNumbers(r);
  const tone = scoreTone(r.overall);
  const warnings = r.warnings.map((w) => SCORE_WARNINGS[w]).filter(Boolean);
  const extremes = sectionExtremes(r.sections);
  const worst = r.moments?.worst ?? [];
  const best = r.moments?.best ?? null;

  return (
    <section
      className="relative mt-6 overflow-hidden rounded-3xl border border-line bg-raised/60"
      data-testid="score-card"
      data-status={r.status}
      aria-labelledby="score-heading"
    >
      <div className="grid gap-0 lg:grid-cols-[18rem_minmax(0,1fr)]">
        {/* Overall */}
        <div className="relative flex flex-col justify-between gap-4 border-b border-line p-6 lg:border-b-0 lg:border-r">
          <span className={`absolute inset-x-0 top-0 h-1 ${numbers ? TONE_BAR[tone] : "bg-amber"}`} aria-hidden />
          <div>
            <h2 id="score-heading" className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted">
              {statusHeadline(r)}
            </h2>
            {numbers ? (
              <p className="mt-3 flex items-baseline gap-2" data-testid="score-overall">
                <span className={`font-display text-7xl font-bold leading-none tracking-tight ${TONE_TEXT[tone]}`}>{scoreText(r.overall)}</span>
                <span className="font-display text-xl text-muted">/ 100</span>
              </p>
            ) : (
              <p className="mt-3 text-ink" data-testid="score-withheld">
                {r.message ?? "Not enough reliable data to score this attempt."}
              </p>
            )}
            {r.status === "qualified" && (
              <p className="mt-3 inline-flex rounded-full border border-amber/50 px-3 py-1 text-xs text-amber" data-testid="score-qualified">
                {qualifierText(r) ?? "Low confidence"}
              </p>
            )}
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs" data-testid="score-coverage">
            <Cov label="Moments compared" value={`${r.coverage.compared_frames}/${r.coverage.reference_frames}`} />
            <Cov label="Joints visible" value={pctText(r.coverage.visible_joint_coverage)} />
            <Cov label="You tracked" value={pctText(r.coverage.learner_tracking)} />
            <Cov label="Reference tracked" value={pctText(r.coverage.reference_tracking)} />
            <Cov label="Confidence" value={pctText(r.coverage.confidence)} />
            <Cov label="Version" value={r.version} />
          </dl>
        </div>

        {/* Components */}
        <div className="p-6">
          <ul className="space-y-4" data-testid="score-components">
            {COMPONENTS.map((c) => {
              const v = numbers ? r.components[c.key] : null;
              const t = scoreTone(v);
              const ev = evidenceText(r, c.key);
              return (
                <li key={c.key} data-testid={`score-${c.key}`}>
                  <div className="flex items-baseline justify-between gap-3">
                    <p className="font-display text-sm font-semibold text-ink" title={c.blurb}>
                      {c.label}
                    </p>
                    <p className="flex items-baseline gap-2">
                      <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">{weightText(r, c.key)}</span>
                      <span className={`font-display text-lg font-semibold ${v == null ? "text-muted" : TONE_TEXT[t]}`}>{scoreText(v)}</span>
                    </p>
                  </div>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-line" aria-hidden>
                    <div
                      className={`h-full rounded-full ${v == null ? "bg-transparent" : TONE_BAR[t]} motion-safe:transition-[width] motion-safe:duration-700`}
                      style={{ width: `${v == null ? 0 : Math.max(2, Math.min(100, v))}%` }}
                    />
                  </div>
                  {ev && <p className="mt-1 text-xs text-muted">{ev}</p>}
                </li>
              );
            })}
          </ul>
        </div>
      </div>

      {numbers && (extremes || worst.length > 0 || best) && (
        <div className={`grid grid-cols-1 gap-4 border-t border-line p-6 ${extremes ? "md:grid-cols-2" : ""}`}>
          {extremes && (
            <div className="min-w-0" data-testid="score-sections">
              <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">By section · measured</p>
              <ul className="mt-2 space-y-1.5 text-sm">
                {(r.sections ?? []).map((s) => (
                  <li key={s.id ?? s.start} className="flex items-baseline justify-between gap-3">
                    <span className="truncate text-ink">
                      {s.title ?? "Section"} <span className="font-mono text-[11px] text-muted">{formatClock(s.start)}–{formatClock(s.end)}</span>
                      {s === extremes.strongest && <span className="ml-2 text-xs text-lime">strongest</span>}
                      {s === extremes.weakest && <span className="ml-2 text-xs text-amber">weakest</span>}
                    </span>
                    <span className={`font-display font-semibold ${s.overall == null ? "text-muted" : TONE_TEXT[scoreTone(s.overall)]}`}>
                      {s.status === "scored" ? scoreText(s.overall) : "too little data"}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="min-w-0" data-testid="score-moments">
            <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Moments to replay · measured</p>
            <ul className="mt-2 space-y-1.5 text-sm">
              {worst.map((m) => (
                <li key={`w${m.ref_t}`}>
                  <MomentButton t={m.learner_t} onSeek={onSeek} tone="amber">
                    Biggest difference: {partsText(m.largest_differences)}
                  </MomentButton>
                </li>
              ))}
              {best && (
                <li>
                  <MomentButton t={best.learner_t} onSeek={onSeek} tone="lime">
                    Best matched pose
                  </MomentButton>
                </li>
              )}
            </ul>
          </div>
        </div>
      )}

      <div className="border-t border-line px-6 py-4 text-xs text-muted">
        {warnings.length > 0 && (
          <ul className="mb-2 space-y-1 text-amber" data-testid="score-warnings">
            {warnings.map((w) => (
              <li key={w}>· {w}</li>
            ))}
          </ul>
        )}
        <p>
          Computed from your measured landmarks, angles and timing against the reference ({r.version}, alignment {r.alignment_version ?? "—"}). The
          weights (pose 30 · timing 25 · sequence 20 · angles 15 · rhythm 10) are product defaults, not a validated grading scale. Tracking
          confidence is shown separately and is not part of the score.
        </p>
      </div>
    </section>
  );
}

/** m:ss.t — moments can be under a second apart, so whole seconds would look identical. */
export function clockTenths(t: number): string {
  const tenths = Math.max(0, Math.round(t * 10));
  const m = Math.floor(tenths / 600);
  const sec = (tenths % 600) / 10;
  return `${m}:${sec.toFixed(1).padStart(4, "0")}`;
}

function pctText(v: number | null | undefined): string {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

function Cov({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted">{label}</dt>
      <dd className="mt-0.5 font-mono text-ink">{value}</dd>
    </div>
  );
}

function MomentButton({ t, onSeek, tone, children }: { t: number | null; onSeek: (t: number) => void; tone: "lime" | "amber"; children: React.ReactNode }) {
  if (t == null) return null;
  return (
    <button
      type="button"
      onClick={() => onSeek(t)}
      data-testid="score-moment"
      data-t={t}
      className="group flex w-full min-w-0 items-center gap-3 rounded-xl border border-line px-3 py-2 text-left transition hover:border-lime/60"
    >
      <span className={`shrink-0 font-mono text-xs ${tone === "lime" ? "text-lime" : "text-amber"}`}>{clockTenths(t)}</span>
      <span className="min-w-0 flex-1 truncate text-ink">{children}</span>
      <span className="text-xs text-muted group-hover:text-lime" aria-hidden>
        ▶
      </span>
    </button>
  );
}

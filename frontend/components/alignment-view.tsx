"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ApiError, getPractice, getPracticeAlignment } from "@/lib/api";
import { ALIGNMENT_STATUS_TEXT, costTone, pathPoints, timingFacts } from "@/lib/alignment";
import { percent } from "@/lib/pose";
import type { Alignment, AlignmentFrame, PracticeSession } from "@/lib/types";

import { Panel } from "./studio-shell";
import { useStudioStatus } from "./studio-status";

type Load =
  | { kind: "pending" }
  | { kind: "ok"; attempt: PracticeSession; alignment: Alignment; cached: boolean }
  | { kind: "error"; title: string; message: string; tone: "amber" | "danger" };

const TONE_FILL: Record<ReturnType<typeof costTone>, string> = {
  good: "var(--color-lime)",
  fair: "var(--color-amber)",
  off: "var(--color-danger)",
  masked: "var(--color-line)",
};

/** Hook: the attempt + its alignment, with honest refusals mapped to messages. */
export function useAlignment(sid: string, enabled: boolean) {
  const [load, setLoad] = useState<Load>({ kind: "pending" });
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    (async () => {
      try {
        const [attempt, res] = await Promise.all([getPractice(sid), getPracticeAlignment(sid)]);
        if (!cancelled) setLoad({ kind: "ok", attempt, alignment: res.alignment, cached: res.cached });
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404)
          setLoad({ kind: "error", tone: "amber", title: "This attempt isn't here", message: "It may have been deleted, or it belongs to a different private session." });
        else if (err instanceof ApiError && (err.status === 409 || err.status === 503))
          setLoad({ kind: "error", tone: "amber", title: "Nothing to compare yet", message: err.message });
        else setLoad({ kind: "error", tone: "danger", title: "Couldn't load the alignment", message: err instanceof Error ? err.message : "Try again." });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sid, enabled]);
  return load;
}

export function AlignmentView() {
  const { sid } = useParams<{ sid: string }>();
  const { view } = useStudioStatus();
  const reachable = view.state === "READY" || view.state === "LIMITED";
  const load = useAlignment(sid, reachable);

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-8 sm:py-12">
      <Link href={`/studio/practice/${sid}`} className="inline-flex items-center gap-2 text-sm text-muted transition hover:text-ink">
        <span aria-hidden>←</span> Back to the attempt
      </Link>
      <p className="mt-6 font-mono text-[10px] uppercase tracking-[0.18em] text-lime">Developer view · alignment</p>
      <h1 className="mt-2 font-display text-3xl font-bold tracking-tight sm:text-5xl">How your moves were paired</h1>
      <p className="mt-3 max-w-2xl text-sm text-muted">
        Each reference frame is matched to a moment of your attempt by a bounded, mirror-aware time warp on normalized body shape. These are
        measurements for checking the pairing — not a dance score.
      </p>
      {view.state === "OFFLINE" ? (
        <div className="mt-6">
          <Panel tone="danger" title="The studio is offline">
            <p>{view.detail}</p>
          </Panel>
        </div>
      ) : load.kind === "pending" ? (
        <div className="mt-8 h-80 animate-pulse rounded-3xl border border-line bg-raised/50" aria-busy aria-label="Loading alignment" />
      ) : load.kind === "error" ? (
        <div className="mt-8" data-testid="alignment-refused">
          <Panel tone={load.tone} title={load.title}>
            <p>{load.message}</p>
          </Panel>
        </div>
      ) : (
        <AlignmentReport alignment={load.alignment} attempt={load.attempt} />
      )}
    </div>
  );
}

function AlignmentReport({ alignment: a, attempt }: { alignment: Alignment; attempt: PracticeSession }) {
  const facts = timingFacts(a);
  const ok = a.status === "aligned";
  return (
    <div className="mt-8 space-y-6" data-testid="alignment-report" data-status={a.status}>
      <div className="flex flex-wrap items-center gap-3">
        <span
          className={`rounded-full px-3 py-1 font-mono text-[11px] uppercase tracking-[0.14em] ${ok ? "bg-lime text-studio" : "border border-amber/60 text-amber"}`}
          data-testid="alignment-status"
        >
          {ALIGNMENT_STATUS_TEXT[a.status] ?? a.status}
        </span>
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
          {attempt.target.title} · {a.version}
        </span>
        {a.reference_immobile && <span className="text-xs text-amber">The reference barely moves here — it won&apos;t be scored as choreography.</span>}
      </div>
      {!ok && a.message && (
        <Panel tone="amber" title="Not compared">
          <p>{a.message}</p>
        </Panel>
      )}
      {ok && a.frames && <PathChart alignment={a} frames={a.frames} />}
      {ok && a.frames && <CostStrip alignment={a} frames={a.frames} />}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
        <dl className="grid grid-cols-2 gap-px self-start overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-4" data-testid="alignment-stats">
          <Stat label="Mean distance" value={fmt(a.summary?.mean_cost)} hint="Mean per-pair movement distance along the path (0 = same shape). Not a score." />
          <Stat label="Same-time pairing" value={fmt(a.summary?.equal_time_cost)} hint="The same distance if frames were paired at equal times, for comparison." />
          <Stat label="Measured" value={percent(a.summary?.measured_fraction ?? null)} hint="Share of reference frames measurable on both videos." />
          <Stat label="Pairing confidence" value={percent(a.summary?.confidence ?? null)} hint="Measured share, reduced for heavy warping." />
          <Stat label="Pace" value={a.timing?.speed_ratio ? `${a.timing.speed_ratio.toFixed(2)}×` : "—"} hint="Your seconds per reference second (robust fit on the original timestamps)." />
          <Stat label="Offset" value={a.timing?.median_offset_s != null ? `${a.timing.median_offset_s.toFixed(2)} s` : "—"} hint="Median of (your time − reference time) over paired frames." />
          <Stat label="Warping" value={percent(a.warp?.non_diagonal_fraction ?? null)} hint="Share of non-diagonal steps (one side held while the other moved)." />
          <Stat label="Body size" value={a.body_size_factor ? `${a.body_size_factor.toFixed(2)}×` : "—"} hint={`Learner limb proportions scaled onto the reference (${a.body_size_segments ?? 0} segments).`} />
        </dl>
        <div className="space-y-4">
          {a.mirror && (
            <div className="rounded-2xl border border-line p-4 text-sm" data-testid="alignment-mirror">
              <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Sides</p>
              <p className="mt-2 text-ink">
                Compared <strong className="text-lime">{a.mirror.chosen === "mirrored" ? "mirrored" : "as recorded"}</strong>
                {a.mirror.decision === "clear" ? " — clearly the better match." : " — both readings were close, so the default was kept."}
              </p>
              <p className="mt-1 text-xs text-muted">
                As recorded {fmt(a.mirror.mean_cost.direct)} · mirrored {fmt(a.mirror.mean_cost.mirrored)} · switch needs {Math.round(a.mirror.margin * 100)}% better. Default:{" "}
                {a.preferred_reason}.
              </p>
            </div>
          )}
          <div className="rounded-2xl border border-line p-4 text-sm" data-testid="alignment-facts">
            <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Measured facts</p>
            {facts.length ? (
              <ul className="mt-2 space-y-1.5 text-ink">
                {facts.map((f) => (
                  <li key={f}>· {f}</li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-muted">{ok ? "Timing and sides match the reference closely." : "Nothing measured to report."}</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

const W = 640;
const H = 320;

function PathChart({ alignment: a, frames }: { alignment: Alignment; frames: AlignmentFrame[] }) {
  const xMax = Math.max(0.1, (a.window ? a.window.end - a.window.start : frames[frames.length - 1].ref_t) || 0.1);
  const yMax = Math.max(xMax, ...frames.map((f) => f.learner_t), a.warp?.learner_end_s ?? 0) + 0.25;
  const band = a.band_s ?? 0;
  const pts = useMemo(() => pathPoints(frames, W, H, xMax, yMax), [frames, xMax, yMax]);
  const X = (t: number) => (t / xMax) * W;
  const Y = (t: number) => H - (t / yMax) * H;
  const bandPoly = `${X(0)},${Y(band)} ${X(xMax)},${Y(xMax + band)} ${X(xMax)},${Y(Math.max(0, xMax - band))} ${X(Math.min(xMax, band))},${Y(0)} ${X(0)},${Y(0)}`;
  return (
    <figure className="rounded-3xl border border-line bg-raised/40 p-4" data-testid="alignment-path">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Alignment path</span>
        <span className="text-xs text-muted">x: reference time · y: your time · shaded: allowed band (±{band.toFixed(1)} s) · dashed: same time</span>
      </figcaption>
      <svg viewBox={`-40 -10 ${W + 50} ${H + 40}`} className="mt-3 h-auto w-full" role="img" aria-label="Alignment path between the reference and your attempt">
        <polygon points={bandPoly} fill="var(--color-lime)" opacity={0.06} />
        <line x1={X(0)} y1={Y(0)} x2={X(xMax)} y2={Y(xMax)} stroke="var(--color-muted)" strokeDasharray="4 5" strokeWidth={1} opacity={0.6} />
        <rect x={0} y={0} width={W} height={H} fill="none" stroke="var(--color-line)" />
        {ticks(xMax).map((t) => (
          <g key={`x${t}`}>
            <line x1={X(t)} y1={H} x2={X(t)} y2={H + 5} stroke="var(--color-line)" />
            <text x={X(t)} y={H + 18} fill="var(--color-muted)" fontSize={11} textAnchor="middle" fontFamily="monospace">
              {t}s
            </text>
          </g>
        ))}
        {ticks(yMax).map((t) => (
          <text key={`y${t}`} x={-8} y={Y(t) + 4} fill="var(--color-muted)" fontSize={11} textAnchor="end" fontFamily="monospace">
            {t}s
          </text>
        ))}
        <polyline points={pts} fill="none" stroke="var(--color-ink)" strokeWidth={1.25} opacity={0.5} />
        {frames.map((f, i) => (
          <circle key={i} cx={X(f.ref_t)} cy={Y(f.learner_t)} r={f.measured ? 3 : 2} fill={TONE_FILL[costTone(f.cost)]} opacity={f.reused ? 0.45 : 0.95} />
        ))}
      </svg>
    </figure>
  );
}

function CostStrip({ alignment: a, frames }: { alignment: Alignment; frames: AlignmentFrame[] }) {
  const xMax = Math.max(0.1, a.window ? a.window.end - a.window.start : frames[frames.length - 1].ref_t);
  const h = 90;
  const X = (t: number) => (t / xMax) * W;
  const step = frames.length > 1 ? (frames[frames.length - 1].ref_t - frames[0].ref_t) / (frames.length - 1) : 0.1;
  const bw = Math.max(1, (step / xMax) * W - 0.5);
  return (
    <figure className="rounded-3xl border border-line bg-raised/40 p-4" data-testid="alignment-strip">
      <figcaption className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Movement distance over the reference</span>
        <span className="flex flex-wrap gap-3 text-xs text-muted">
          <Legend color="var(--color-lime)" label="close" />
          <Legend color="var(--color-amber)" label="some difference" />
          <Legend color="var(--color-danger)" label="clearly different" />
          <Legend color="var(--color-line)" label="not measured (left out)" />
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${h + 22}`} className="mt-3 h-auto w-full" role="img" aria-label="Per-moment movement distance">
        {(a.missing_spans ?? []).map(([lo, hi]) => (
          <rect key={`m${lo}`} x={X(lo)} y={0} width={Math.max(2, X(hi) - X(lo))} height={h} fill="var(--color-danger)" opacity={0.12} data-testid="missing-span" />
        ))}
        {(a.masked_spans ?? []).map(([lo, hi]) => (
          <rect key={`k${lo}`} x={X(lo)} y={0} width={Math.max(2, X(hi) - X(lo))} height={h} fill="var(--color-muted)" opacity={0.1} data-testid="masked-span" />
        ))}
        {(a.timing?.off_spans ?? []).map(([lo, hi]) => (
          <rect key={`o${lo}`} x={X(lo)} y={h + 4} width={Math.max(2, X(hi) - X(lo))} height={4} fill="var(--color-amber)" />
        ))}
        {frames.map((f, i) => {
          const v = f.cost === null ? 0.08 : Math.min(1, f.cost);
          return <rect key={i} x={X(f.ref_t)} y={h - v * h} width={bw} height={v * h} fill={TONE_FILL[costTone(f.cost)]} opacity={f.cost === null ? 0.6 : 0.9} />;
        })}
        <text x={0} y={h + 20} fill="var(--color-muted)" fontSize={11} fontFamily="monospace">
          0s
        </text>
        <text x={W} y={h + 20} fill="var(--color-muted)" fontSize={11} fontFamily="monospace" textAnchor="end">
          {xMax.toFixed(1)}s
        </text>
      </svg>
    </figure>
  );
}

function ticks(max: number): number[] {
  const step = max > 20 ? 5 : max > 8 ? 2 : 1;
  const out: number[] = [];
  for (let t = 0; t <= max + 1e-6; t += step) out.push(Math.round(t));
  return out;
}

function fmt(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : v.toFixed(2);
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="inline-block size-2.5 rounded-sm" style={{ background: color }} aria-hidden />
      {label}
    </span>
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

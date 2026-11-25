"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, getMedia, getPoses, getProject, mediaHref } from "@/lib/api";
import { formatDuration, warningLabel } from "@/lib/media";
import { degrees, nearestFrameIndex, percent } from "@/lib/pose";
import type { PoseFrame, PosesResponse, Project } from "@/lib/types";

import { StatusChip } from "./project-list";
import { SkeletonOverlay } from "./skeleton-overlay";
import { Panel } from "./studio-shell";
import { useStudioStatus } from "./studio-status";

type Load =
  | { kind: "pending" }
  | { kind: "ok"; project: Project; poses: PosesResponse; src: string }
  | { kind: "error"; message: string; notAnalyzed?: boolean };

const SPEEDS = [0.25, 0.5, 1];

export function PoseDebugger() {
  const { id } = useParams<{ id: string }>();
  const { view } = useStudioStatus();
  const reachable = view.state === "READY" || view.state === "LIMITED";
  const [load, setLoad] = useState<Load>({ kind: "pending" });

  useEffect(() => {
    if (!reachable) return;
    let cancelled = false;
    (async () => {
      try {
        const [project, poses, media] = await Promise.all([getProject(id), getPoses(id), getMedia(id, "canonical")]);
        if (!cancelled) setLoad({ kind: "ok", project, poses, src: mediaHref(media.url) });
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 409)
          setLoad({ kind: "error", message: "This dance hasn't been analysed yet.", notAnalyzed: true });
        else if (err instanceof ApiError && err.status === 404)
          setLoad({ kind: "error", message: "This dance doesn't exist or was deleted." });
        else setLoad({ kind: "error", message: err instanceof Error ? err.message : "Couldn't load the analysis." });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, reachable]);

  return (
    <div className="mx-auto w-full max-w-[96rem] px-4 py-8 sm:px-8 sm:py-10">
      <Link href={`/studio/projects/${id}`} className="inline-flex items-center gap-2 text-sm text-muted transition hover:text-ink">
        <span aria-hidden>←</span> Back to dance
      </Link>
      {view.state === "OFFLINE" ? (
        <div className="mt-6">
          <Panel tone="danger" title="The studio is offline">
            <p>{view.detail}</p>
          </Panel>
        </div>
      ) : load.kind === "pending" ? (
        <div className="mt-8 aspect-video w-full animate-pulse rounded-3xl border border-line bg-raised/50" aria-busy aria-label="Loading analysis" />
      ) : load.kind === "error" ? (
        <div className="mt-6">
          <Panel tone="amber" title={load.notAnalyzed ? "Nothing to inspect yet" : "Couldn't open the debugger"}>
            <p>{load.message}</p>
          </Panel>
        </div>
      ) : (
        <Inspector project={load.project} poses={load.poses} src={load.src} />
      )}
    </div>
  );
}

function Inspector({ project, poses, src }: { project: Project; poses: PosesResponse; src: string }) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [frame, setFrame] = useState<PoseFrame | null>(null);
  const [showIds, setShowIds] = useState(true);
  const [trails, setTrails] = useState(true);
  const [selected, setSelected] = useState<number | null>(null);
  const [speed, setSpeed] = useState(0.5);
  const [playing, setPlaying] = useState(false);
  const step = 1 / (poses.analysis_fps ?? 12);
  const q = poses.quality;

  useEffect(() => {
    if (videoRef.current) videoRef.current.playbackRate = speed;
  }, [speed]);

  const seek = useCallback((t: number) => {
    const v = videoRef.current;
    if (!v) return;
    v.pause();
    v.currentTime = Math.max(0, Math.min(t, (poses.duration ?? v.duration) - 0.001));
  }, [poses.duration]);

  const stepBy = useCallback(
    (dir: 1 | -1) => {
      const v = videoRef.current;
      if (!v) return;
      const i = nearestFrameIndex(poses.frames, v.currentTime);
      const next = poses.frames[Math.max(0, Math.min(poses.frames.length - 1, i + dir))];
      if (next) seek(next.t);
    },
    [poses.frames, seek],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest("input, select, textarea, button")) return;
      if (e.key === "ArrowRight" || e.key === ".") {
        e.preventDefault();
        stepBy(1);
      } else if (e.key === "ArrowLeft" || e.key === ",") {
        e.preventDefault();
        stepBy(-1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [stepBy]);

  return (
    <>
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <StatusChip status={project.status} />
        <span className="rounded-full border border-line px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          Pose debugger
        </span>
      </div>
      <h1 className="mt-3 font-display text-2xl font-bold tracking-tight sm:text-4xl">{project.title}</h1>
      {q?.failure && (
        <p className="mt-3 max-w-3xl text-sm text-danger" role="alert">
          Analysis failed ({q.failure.replaceAll("_", " ")}): {q.failure_message}
        </p>
      )}

      <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_26rem]">
        <section aria-label="Video with measured skeleton" className="min-w-0">
          <div className="relative aspect-video w-full overflow-hidden rounded-3xl border border-line bg-black">
            <video
              ref={videoRef}
              src={src}
              playsInline
              preload="auto"
              muted
              className="absolute inset-0 h-full w-full object-contain"
              onPlay={() => setPlaying(true)}
              onPause={() => setPlaying(false)}
            />
            <SkeletonOverlay videoRef={videoRef} poses={poses} options={{ showIds, trails, highlight: selected }} onFrame={setFrame} />
            <FrameBadge frame={frame} />
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Ctl onClick={() => stepBy(-1)} label="Previous analysed frame">◀ Frame</Ctl>
            <Ctl
              onClick={() => {
                const v = videoRef.current;
                if (!v) return;
                if (v.paused) void v.play();
                else v.pause();
              }}
              label={playing ? "Pause" : "Play"}
              primary
            >
              {playing ? "Pause" : "Play"}
            </Ctl>
            <Ctl onClick={() => stepBy(1)} label="Next analysed frame">Frame ▶</Ctl>
            <div className="ml-auto flex items-center gap-1 rounded-full border border-line p-1" role="group" aria-label="Playback speed">
              {SPEEDS.map((s) => (
                <button
                  key={s}
                  type="button"
                  aria-pressed={speed === s}
                  onClick={() => setSpeed(s)}
                  className={`rounded-full px-3 py-1.5 font-mono text-xs ${speed === s ? "bg-lime text-studio" : "text-muted hover:text-ink"}`}
                >
                  {s}×
                </button>
              ))}
            </div>
          </div>
          <div className="mt-2 flex flex-wrap gap-4 text-sm text-muted">
            <Toggle checked={showIds} onChange={setShowIds} label="Landmark IDs" />
            <Toggle checked={trails} onChange={setTrails} label="Movement trails" />
            <span className="font-mono text-xs">← / → step {Math.round(step * 1000)} ms</span>
          </div>

          <Timeline poses={poses} frame={frame} onSeek={seek} />
          <Legend />
          <div className="mt-6 hidden gap-5 xl:grid xl:grid-cols-2">
            <LandmarkTable frame={frame} poses={poses} selected={selected} onSelect={setSelected} />
            <ClipReport project={project} poses={poses} />
          </div>
        </section>

        <aside className="flex min-w-0 flex-col gap-5">
          <FramePanel frame={frame} poses={poses} />
          <AnglesPanel frame={frame} />
          <div className="grid grid-cols-2 gap-4">
            <NormalizedPose frame={frame} poses={poses} />
            <TravelPlot poses={poses} frame={frame} />
          </div>
          <div className="flex flex-col gap-5 xl:hidden">
            <LandmarkTable frame={frame} poses={poses} selected={selected} onSelect={setSelected} />
            <ClipReport project={project} poses={poses} />
          </div>
        </aside>
      </div>
    </>
  );
}

function Ctl({ children, onClick, label, primary }: { children: React.ReactNode; onClick: () => void; label: string; primary?: boolean }) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className={`rounded-full px-4 py-2 font-mono text-xs uppercase tracking-[0.12em] transition ${
        primary ? "bg-lime text-studio hover:-translate-y-0.5" : "border border-line text-ink hover:border-lime/60"
      }`}
    >
      {children}
    </button>
  );
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex cursor-pointer items-center gap-2">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="size-4 accent-[var(--color-lime)]" />
      {label}
    </label>
  );
}

function FrameBadge({ frame }: { frame: PoseFrame | null }) {
  return (
    <div className="pointer-events-none absolute left-2 top-2 rounded-lg bg-studio/80 px-2 py-1 font-mono text-[9px] leading-4 sm:left-3 sm:top-3 sm:rounded-xl sm:px-3 sm:py-2 sm:text-[11px] sm:leading-5 text-ink backdrop-blur">
      {frame ? (
        <>
          <div>
            t {frame.t.toFixed(3)} s · frame {frame.frame}
          </div>
          <div className={frame.valid ? "text-lime" : "text-amber"}>
            {frame.valid ? "valid" : frame.data.landmarks ? "excluded: core body not visible" : "no pose detected"}
          </div>
        </>
      ) : (
        <div className="text-muted">between analysed frames</div>
      )}
    </div>
  );
}

function Timeline({ poses, frame, onSeek }: { poses: PosesResponse; frame: PoseFrame | null; onSeek: (t: number) => void }) {
  const W = 1000;
  const H = 72;
  const dur = poses.duration ?? poses.frames.at(-1)?.t ?? 1;
  const energies = poses.frames.map((f) => f.data.motion_energy ?? 0);
  const maxE = Math.max(0.001, ...energies.map((e) => (Number.isFinite(e) ? e : 0)));
  const path = poses.frames
    .map((f, i) => {
      const e = f.data.motion_energy;
      if (e === null) return null;
      const x = (f.t / dur) * W;
      const y = H - 18 - (e / maxE) * (H - 26);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .filter(Boolean)
    .join(" ")
    .replace(/^L/, "M");
  const bw = W / Math.max(1, poses.frames.length);
  return (
    <div className="mt-5">
      <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Motion energy · tracking coverage (click to seek)</p>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className="h-20 w-full cursor-pointer rounded-xl border border-line bg-raised/40"
        role="slider"
        aria-label="Seek through analysed frames"
        aria-valuemin={0}
        aria-valuemax={Math.round(dur * 1000) / 1000}
        aria-valuenow={frame?.t ?? 0}
        tabIndex={0}
        onClick={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          onSeek(((e.clientX - r.left) / r.width) * dur);
        }}
      >
        {poses.frames.map((f) => (
          <rect
            key={f.frame}
            x={(f.t / dur) * W}
            y={H - 8}
            width={bw + 0.5}
            height={8}
            fill={f.valid ? "var(--color-track)" : f.data.landmarks ? "var(--color-amber)" : "var(--color-danger)"}
            opacity={f.valid ? 0.85 : 0.9}
          />
        ))}
        <path d={path} fill="none" stroke="var(--color-lime)" strokeWidth={2} vectorEffect="non-scaling-stroke" />
        {frame && <line x1={(frame.t / dur) * W} x2={(frame.t / dur) * W} y1={0} y2={H} stroke="#fff" strokeWidth={2} vectorEffect="non-scaling-stroke" />}
      </svg>
      <div className="mt-1 flex justify-between font-mono text-[10px] text-muted">
        <span>0 s</span>
        <span>{formatDuration(dur)}</span>
      </div>
    </div>
  );
}

function Legend() {
  return (
    <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
      <li className="flex items-center gap-2"><span className="h-2 w-4 rounded bg-track" /> valid frame</li>
      <li className="flex items-center gap-2"><span className="h-2 w-4 rounded bg-amber" /> pose found, core body not visible</li>
      <li className="flex items-center gap-2"><span className="h-2 w-4 rounded bg-danger" /> no pose</li>
      <li className="flex items-center gap-2"><span className="h-0.5 w-4 border-t-2 border-dashed border-lime/60" /> bridged short gap (not measured)</li>
    </ul>
  );
}

function Card({ title, children, note }: { title: string; children: React.ReactNode; note?: string }) {
  return (
    <section className="rounded-2xl border border-line bg-raised/40 p-4">
      <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">{title}</h2>
      <div className="mt-3">{children}</div>
      {note && <p className="mt-3 text-xs text-muted">{note}</p>}
    </section>
  );
}

function Row({ k, v, tone }: { k: string; v: string; tone?: "lime" | "amber" | "muted" }) {
  const color = tone === "lime" ? "text-lime" : tone === "amber" ? "text-amber" : tone === "muted" ? "text-muted" : "text-ink";
  return (
    <div className="flex items-baseline justify-between gap-3 py-1 text-sm">
      <span className="text-muted">{k}</span>
      <span className={`font-mono ${color}`}>{v}</span>
    </div>
  );
}

function fmt(v: number | null | undefined, d = 2): string {
  return v === null || v === undefined || !Number.isFinite(v) ? "—" : v.toFixed(d);
}

function FramePanel({ frame, poses }: { frame: PoseFrame | null; poses: PosesResponse }) {
  return (
    <Card title="This frame" note="Tracking confidence says how clearly the body is seen. It is not a dance score.">
      {frame ? (
        <div>
          <Row k="Timestamp" v={`${frame.t.toFixed(3)} s`} />
          <Row k="Canonical frame (24 fps)" v={String(frame.frame)} />
          <Row k="Status" v={frame.valid ? "valid" : "excluded"} tone={frame.valid ? "lime" : "amber"} />
          <Row k="Tracking confidence" v={percent(frame.confidence)} />
          <Row k="People detected" v={String(frame.data.poses_detected)} tone={frame.data.poses_detected > 1 ? "amber" : undefined} />
          <Row k="Motion energy (torso/s)" v={fmt(frame.data.motion_energy)} />
          <Row k="Torso lean" v={degrees(frame.data.torso_lean)} />
          <Row k="Shoulder / hip line" v={`${degrees(frame.data.shoulder_tilt)} / ${degrees(frame.data.hip_tilt)}`} />
          <Row k="Facing yaw (experimental)" v={degrees(frame.data.yaw_experimental)} tone="muted" />
          <Row k="Root travel (torso units)" v={`${fmt(frame.data.travel[0])}, ${fmt(frame.data.travel[1])}`} />
          <Row k="Centre of mass (estimate)" v={`${fmt(frame.data.com_estimate[0])}, ${fmt(frame.data.com_estimate[1])}`} tone="muted" />
        </div>
      ) : (
        <p className="text-sm text-muted">
          Scrub or step to an analysed frame ({poses.analysis_fps ?? 12} per second).
        </p>
      )}
    </Card>
  );
}

function AnglesPanel({ frame }: { frame: PoseFrame | null }) {
  const entries = frame ? Object.entries(frame.data.angles) : [];
  return (
    <Card title="Joint angles (measured in the image plane)" note="— means a required joint wasn't seen clearly, so the angle isn't guessed.">
      <div className="grid grid-cols-2 gap-x-5">
        {entries.map(([name, v]) => (
          <div key={name} className="py-1">
            <div className="flex justify-between text-sm">
              <span className="text-muted">{name.replace("_", " ")}</span>
              <span className="font-mono text-ink">{degrees(v)}</span>
            </div>
            <div className="mt-1 h-1 overflow-hidden rounded bg-line">
              {v !== null && <div className="h-full bg-lime" style={{ width: `${(v / 180) * 100}%` }} />}
            </div>
          </div>
        ))}
        {!frame && <p className="col-span-2 text-sm text-muted">No frame selected.</p>}
      </div>
    </Card>
  );
}

function NormalizedPose({ frame, poses }: { frame: PoseFrame | null; poses: PosesResponse }) {
  const S = 120;
  const span = 3.2;
  const map = (x: number, y: number) => [S / 2 + (x / span) * (S / 2), S / 2 + (y / span) * (S / 2) - 10] as const;
  const n = frame?.data.normalized ?? [];
  return (
    <Card title="Normalized pose">
      <svg viewBox={`0 0 ${S} ${S}`} className="aspect-square w-full rounded-xl bg-studio" aria-label="Hip-centred, torso-scaled pose">
        <line x1={S / 2} x2={S / 2} y1={0} y2={S} stroke="var(--color-line)" strokeDasharray="2 3" />
        <line x1={0} x2={S} y1={S / 2 - 10} y2={S / 2 - 10} stroke="var(--color-line)" strokeDasharray="2 3" />
        {poses.connections.map(([a, b]) => {
          const pa = n[a];
          const pb = n[b];
          if (!pa || !pb) return null;
          const [x1, y1] = map(pa[0], pa[1]);
          const [x2, y2] = map(pb[0], pb[1]);
          return <line key={`${a}-${b}`} x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--color-lime)" strokeWidth={1.6} strokeLinecap="round" />;
        })}
      </svg>
      <p className="mt-2 text-[11px] text-muted">Hip midpoint at centre, 1 unit = median torso length.</p>
    </Card>
  );
}

function TravelPlot({ poses, frame }: { poses: PosesResponse; frame: PoseFrame | null }) {
  const S = 120;
  const pts = poses.frames.filter((f) => f.data.travel[0] !== null && f.data.travel[1] !== null);
  const maxAbs = Math.max(0.5, ...pts.flatMap((f) => [Math.abs(f.data.travel[0]!), Math.abs(f.data.travel[1]!)]));
  const map = (x: number, y: number) => [S / 2 + (x / maxAbs) * (S / 2 - 8), S / 2 + (y / maxAbs) * (S / 2 - 8)] as const;
  const d = pts.map((f, i) => {
    const [x, y] = map(f.data.travel[0]!, f.data.travel[1]!);
    return `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const cur = frame && frame.data.travel[0] !== null ? map(frame.data.travel[0]!, frame.data.travel[1]!) : null;
  return (
    <Card title="Root travel">
      <svg viewBox={`0 0 ${S} ${S}`} className="aspect-square w-full rounded-xl bg-studio" aria-label="Hip midpoint path across the clip">
        <circle cx={S / 2} cy={S / 2} r={2} fill="var(--color-muted)" />
        <path d={d.join(" ")} fill="none" stroke="var(--color-track)" strokeWidth={1.2} opacity={0.7} />
        {cur && <circle cx={cur[0]} cy={cur[1]} r={4} fill="var(--color-lime)" />}
      </svg>
      <p className="mt-2 text-[11px] text-muted">Path of the hips from the first valid frame (±{maxAbs.toFixed(1)} torso).</p>
    </Card>
  );
}

function LandmarkTable({
  frame,
  poses,
  selected,
  onSelect,
}: {
  frame: PoseFrame | null;
  poses: PosesResponse;
  selected: number | null;
  onSelect: (j: number | null) => void;
}) {
  const ids = useMemo(() => [0, ...Array.from({ length: 22 }, (_, i) => i + 11)], []);
  return (
    <Card title="Landmarks" note="Select a row to highlight it on the video. Excluded joints are never scored as if seen.">
      <div className="max-h-80 overflow-auto rounded-xl border border-line">
        <table className="w-full text-left font-mono text-[11px]">
          <thead className="sticky top-0 bg-raised text-muted">
            <tr>
              <th className="px-2 py-1.5">#</th>
              <th className="px-2 py-1.5">name</th>
              <th className="px-2 py-1.5">x, y</th>
              <th className="px-2 py-1.5">vis</th>
              <th className="px-2 py-1.5">state</th>
            </tr>
          </thead>
          <tbody>
            {ids.map((j) => {
              const lm = frame?.data.landmarks?.[j];
              const reliable = frame?.data.reliable[j];
              const bridged = frame?.data.interpolated[j];
              const state = !frame
                ? "—"
                : !frame.data.landmarks
                  ? "no pose"
                  : reliable
                    ? "measured"
                    : bridged
                      ? "bridged"
                      : `hidden (${Math.min(lm?.[3] ?? 0, lm?.[4] ?? 0).toFixed(2)} < 0.50)`;
              return (
                <tr
                  key={j}
                  onClick={() => onSelect(selected === j ? null : j)}
                  className={`cursor-pointer border-t border-line/60 ${selected === j ? "bg-lime/10" : "hover:bg-raised"}`}
                  aria-selected={selected === j}
                >
                  <td className="px-2 py-1 text-muted">{j}</td>
                  <td className="px-2 py-1 text-ink">{poses.landmark_names[j]}</td>
                  <td className="whitespace-nowrap px-2 py-1">{lm ? `${lm[0].toFixed(3)}, ${lm[1].toFixed(3)}` : "—"}</td>
                  <td className="px-2 py-1">{lm ? lm[3].toFixed(2) : "—"}</td>
                  <td className={`px-2 py-1 ${reliable ? "text-lime" : "text-amber"}`}>{state}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function ClipReport({ project, poses }: { project: Project; poses: PosesResponse }) {
  const q = poses.quality;
  const ref = project.reference;
  return (
    <Card title="Clip quality & versions">
      {q && (
        <>
          <Row k="Body tracked (coverage)" v={percent(q.coverage, 1)} tone={q.coverage >= 0.85 ? "lime" : "amber"} />
          <Row k="Valid / analysed frames" v={`${q.valid_frames} / ${q.analyzed_frames}`} />
          <Row k="Frames with 2+ people" v={percent(q.multi_person_fraction, 1)} />
          <Row k="Feet visible" v={percent(q.feet_visible_fraction, 0)} />
          <Row k="Joint confidence (measured)" v={percent(q.measured_joint_confidence ?? q.mean_confidence, 1)} />
          <Row k="Bridged gap frames" v={String(q.interpolated_frames)} />
          {Object.keys(q.excluded_joints).length > 0 && (
            <div className="mt-2 text-xs text-muted">
              <p className="text-ink">Excluded joints (valid frames where the joint wasn&apos;t seen):</p>
              <p className="mt-1 font-mono">
                {Object.entries(q.excluded_joints)
                  .map(([k, v]) => `${k.replace("_", " ")} ${v}`)
                  .join(" · ")}
              </p>
            </div>
          )}
          {q.warnings.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs text-amber">
              {q.warnings.map((w) => (
                <li key={w}>△ {warningLabel(w)}</li>
              ))}
            </ul>
          )}
        </>
      )}
      <div className="mt-3 border-t border-line/60 pt-2">
        <Row k="Pipeline" v={poses.pipeline_version ?? "—"} tone="muted" />
        <Row k="Model" v={(poses.model_version ?? "—").replace("pose_landmarker_full@", "full@")} tone="muted" />
        <Row k="Analysis rate" v={`${poses.analysis_fps ?? "—"} fps`} tone="muted" />
        <Row k="Canonical" v={ref?.canonical_width ? `${ref.canonical_width}×${ref.canonical_height} @ ${ref.canonical_fps} fps` : "—"} tone="muted" />
        <Row k="Smoothing" v={q?.smoothing ?? "—"} tone="muted" />
      </div>
    </Card>
  );
}

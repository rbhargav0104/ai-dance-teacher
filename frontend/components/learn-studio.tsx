"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { type RefObject, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, getSections, mediaHref, regenerateSections, saveSections, updateSection } from "@/lib/api";
import {
  type DraftSection,
  FRAME,
  SPEEDS,
  type Speed,
  formatClock,
  isTiled,
  loopAction,
  mergeWithNext,
  moveBoundary,
  sameBoundaries,
  sectionIndexAt,
  splitAt,
  toDraft,
  toEdits,
} from "@/lib/sections";
import { countAt, countIn, cueIndexAt, sectionCues } from "@/lib/avatar/cues";
import { CAMERA_VIEWS, type CameraView, hasWebGL } from "@/lib/avatar/stage-config";
import { buildTrack } from "@/lib/avatar/track";
import type { PosesResponse, Section, SectionsResponse } from "@/lib/types";

import { SkeletonOverlay } from "./skeleton-overlay";

// three.js only loads on the client, and only once a dance with poses is open.
const AvatarStage = dynamic(() => import("./avatar-stage").then((m) => m.AvatarStage), {
  ssr: false,
  loading: () => <div className="absolute inset-0 animate-pulse bg-raised/40" aria-label="Loading the 3D stage" />,
});

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const set = () => setReduced(mq.matches);
    set();
    mq.addEventListener("change", set);
    return () => mq.removeEventListener("change", set);
  }, []);
  return reduced;
}

const speechAvailable = () => typeof window !== "undefined" && "speechSynthesis" in window && typeof SpeechSynthesisUtterance !== "undefined";

function speak(text: string) {
  if (!speechAvailable()) return;
  try {
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.02;
    u.lang = "en-US";
    window.speechSynthesis.speak(u);
  } catch {
    /* speech is best-effort; captions always show the same words */
  }
}
function hush() {
  if (speechAvailable()) window.speechSynthesis.cancel();
}

type VideoWithFrames = HTMLVideoElement & {
  requestVideoFrameCallback?: (cb: (now: number, meta: { mediaTime: number }) => void) => number;
  cancelVideoFrameCallback?: (id: number) => void;
};

/**
 * Keeps playback inside the selected section: loops (or stops) about one frame before the
 * section end, using per-frame callbacks where the browser has them (rAF otherwise).
 */
function useSectionPlayback(
  videoRef: RefObject<HTMLVideoElement | null>,
  section: { start: number; end: number } | null,
  loop: boolean,
  speed: Speed,
  onTime: (t: number) => void,
) {
  const sectionRef = useRef(section);
  const loopRef = useRef(loop);
  const onTimeRef = useRef(onTime);
  useEffect(() => {
    sectionRef.current = section;
    loopRef.current = loop;
    onTimeRef.current = onTime;
  });

  useEffect(() => {
    const v = videoRef.current;
    if (v) v.playbackRate = speed;
  }, [videoRef, speed]);

  useEffect(() => {
    const v = videoRef.current as VideoWithFrames | null;
    if (!v) return;
    let handle = 0;
    let usingVfc = false;
    let lastReport = 0;
    const check = (t: number) => {
      const sec = sectionRef.current;
      if (sec && !v.paused) {
        const a = loopAction(t, sec, loopRef.current);
        if (a.kind === "seek") v.currentTime = a.to;
        else if (a.kind === "stop") {
          v.pause();
          v.currentTime = a.at;
        }
      }
      const now = performance.now();
      if (now - lastReport > 80 || v.paused) {
        lastReport = now;
        onTimeRef.current(v.currentTime);
      }
    };
    const tick = () => {
      check(v.currentTime);
      schedule();
    };
    const onVfc = (_n: number, meta: { mediaTime: number }) => {
      check(meta.mediaTime);
      schedule();
    };
    const schedule = () => {
      if (v.paused || v.ended) {
        handle = 0;
        return;
      }
      if (v.requestVideoFrameCallback) {
        usingVfc = true;
        handle = v.requestVideoFrameCallback(onVfc);
      } else {
        handle = requestAnimationFrame(tick);
      }
    };
    const start = () => {
      if (!handle) schedule();
    };
    const report = () => onTimeRef.current(v.currentTime);
    v.addEventListener("play", start);
    v.addEventListener("seeked", report);
    v.addEventListener("pause", report);
    start();
    return () => {
      if (handle) {
        if (usingVfc && v.cancelVideoFrameCallback) v.cancelVideoFrameCallback(handle);
        else cancelAnimationFrame(handle);
      }
      v.removeEventListener("play", start);
      v.removeEventListener("seeked", report);
      v.removeEventListener("pause", report);
    };
  }, [videoRef]);
}

type Load = { kind: "pending" } | { kind: "ok"; data: SectionsResponse } | { kind: "error"; message: string };

export function LearnStudio({
  projectId,
  src,
  poses,
  onVideoError,
  aside,
}: {
  projectId: string;
  src: string;
  poses: PosesResponse | null;
  onVideoError: () => void;
  aside: React.ReactNode;
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [load, setLoad] = useState<Load>({ kind: "pending" });
  const [active, setActive] = useState(0);
  const [now, setNow] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [loop, setLoop] = useState(true);
  const [speed, setSpeed] = useState<Speed>(0.5);
  const [mirror, setMirror] = useState(true);
  const [skeleton, setSkeleton] = useState(true);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<DraftSection[] | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [primary, setPrimary] = useState<"avatar" | "video">("avatar");
  const [view, setView] = useState<CameraView>("front");
  const [voice, setVoice] = useState(true);
  const [webgl, setWebgl] = useState<boolean | null>(null);
  const [countdown, setCountdown] = useState<string | null>(null);
  const countTimers = useRef<number[]>([]);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    // Checked on the client only; null until then so SSR and hydration agree.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time capability probe
    setWebgl(hasWebGL());
  }, []);

  const tracks = useMemo(() => (poses ? { direct: buildTrack(poses, false), mirror: buildTrack(poses, true) } : null), [poses]);
  const chosenDancer = useMemo(() => Boolean(poses?.frames.some((f) => f.data.subject)), [poses]);
  const avatarOn = Boolean(tracks && webgl);
  const avatarPrimary = avatarOn && primary === "avatar";

  useEffect(() => {
    let cancelled = false;
    getSections(projectId)
      .then((data) => !cancelled && setLoad({ kind: "ok", data }))
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoad({ kind: "error", message: err instanceof Error ? err.message : "Could not load sections." });
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const data = load.kind === "ok" ? load.data : null;
  const sections: Section[] = useMemo(() => data?.sections ?? [], [data]);
  const shown: { start: number; end: number; title: string; completed: boolean; id?: string }[] =
    editing && draft ? draft : sections;
  const current = sections[Math.min(active, Math.max(0, sections.length - 1))] ?? null;
  const playbackSection = editing ? null : current;

  useSectionPlayback(videoRef, playbackSection, loop, speed, setNow);

  const seek = useCallback((t: number) => {
    const v = videoRef.current;
    if (v) v.currentTime = Math.max(0, t);
    setNow(t);
  }, []);

  const select = useCallback(
    (i: number) => {
      const s = sections[i];
      if (!s) return;
      setActive(i);
      seek(s.start);
    },
    [sections, seek],
  );

  const cancelCountIn = useCallback(() => {
    countTimers.current.forEach((h) => window.clearTimeout(h));
    countTimers.current = [];
    setCountdown(null);
  }, []);
  useEffect(() => cancelCountIn, [cancelCountIn]);

  const play = (v: HTMLVideoElement) =>
    void v.play().catch(() => {
      // After a count-in, play() is no longer inside the click, and some browsers block sound.
      if (v.muted) return setNotice("Playback was blocked by the browser. Press play again.");
      v.muted = true;
      void v
        .play()
        .then(() => setNotice("The browser blocked the video's sound after the count-in, so it plays muted this time. Turn Voice off to start without the count-in and keep the sound."))
        .catch(() => setNotice("Playback was blocked by the browser. Press play again."));
    });

  const togglePlay = () => {
    const v = videoRef.current;
    if (!v) return;
    if (countdown !== null) {
      cancelCountIn();
      hush();
      return;
    }
    if (v.paused) {
      if (current && !editing && (v.currentTime < current.start || v.currentTime >= current.end - FRAME)) {
        v.currentTime = current.start;
      }
      // Count in ("5, 6, 7, 8") when the coach is on and the section starts from the top.
      if (current && !editing && voice && Math.abs(v.currentTime - current.start) < FRAME * 1.5) {
        const { words, beatMs } = countIn(current, speed);
        words.forEach((w, i) =>
          countTimers.current.push(
            window.setTimeout(() => {
              setCountdown(w);
              speak(w);
            }, i * beatMs),
          ),
        );
        countTimers.current.push(
          window.setTimeout(() => {
            setCountdown(null);
            countTimers.current = [];
            play(v);
          }, words.length * beatMs),
        );
        return;
      }
      v.muted = false; // direct click: sound is allowed again
      play(v);
    } else v.pause();
  };

  // Captions always show; the voice reads the same measured cue when it changes.
  const cues = useMemo(() => (current ? sectionCues(current, mirror) : []), [current, mirror]);
  const cueIdx = cueIndexAt(cues, now);
  const cueText = cueIdx >= 0 ? cues[cueIdx].text : (cues[0]?.text ?? null);
  const beat = current ? countAt(current, now) : null;
  const lastSpoken = useRef<string | null>(null);
  useEffect(() => {
    if (!playing || !voice || cueIdx < 0 || editing) {
      lastSpoken.current = null;
      return;
    }
    const key = `${current?.id}:${cueIdx}:${mirror}`;
    if (lastSpoken.current === key) return;
    lastSpoken.current = key;
    speak(cues[cueIdx].text);
  }, [playing, voice, cueIdx, cues, current?.id, mirror, editing]);
  useEffect(() => {
    if (!playing || !voice) hush();
  }, [playing, voice]);

  const instruction = current ? (mirror ? current.instruction : current.instruction_direct ?? current.instruction) : null;
  const doneCount = sections.filter((s) => s.completed).length;
  const duration = data?.duration ?? 0;
  const minLen = data?.min_section_seconds ?? 0.5;
  const dirty = editing && draft !== null && (!sameBoundaries(draft, sections) || draft.some((d, i) => d.title !== sections[i]?.title));

  const applyServer = (next: SectionsResponse, keepTime = true) => {
    setLoad({ kind: "ok", data: next });
    const t = keepTime ? videoRef.current?.currentTime ?? 0 : 0;
    setActive(Math.max(0, sectionIndexAt(next.sections, t)));
  };

  const markComplete = async () => {
    if (!current || !data) return;
    try {
      const updated = await updateSection(projectId, current.id, { completed: !current.completed });
      applyServer({ ...data, sections: sections.map((s) => (s.id === updated.id ? updated : s)) });
      if (!current.completed && active < sections.length - 1) setNotice(`${current.title} marked complete. Next up: ${sections[active + 1].title}.`);
      else setNotice(null);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Couldn't save that. Try again.");
    }
  };

  const startEditing = () => {
    videoRef.current?.pause();
    setDraft(toDraft(sections));
    setEditing(true);
    setNotice(null);
  };
  const cancelEditing = () => {
    setEditing(false);
    setDraft(null);
    setNotice(null);
  };
  const save = async () => {
    if (!draft || !isTiled(draft, duration)) return;
    setSaving(true);
    try {
      const next = await saveSections(projectId, toEdits(draft));
      applyServer(next);
      setEditing(false);
      setDraft(null);
      setNotice("Sections saved. Changed sections got fresh thumbnails and instructions.");
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "Couldn't save the sections. Nothing was changed.");
    } finally {
      setSaving(false);
    }
  };
  const regenerate = async () => {
    setSaving(true);
    try {
      const next = await regenerateSections(projectId);
      applyServer(next, false);
      seek(0);
      setEditing(false);
      setDraft(null);
      setNotice("Back to the automatic suggestion. Completion marks were cleared.");
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Couldn't regenerate sections.");
    } finally {
      setSaving(false);
    }
  };

  const editIndex = draft ? sectionIndexAt(draft, now) : -1;

  return (
    <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="flex min-w-0 flex-col gap-4">
        <div
          className={`relative w-full overflow-hidden rounded-3xl border border-line bg-black ${avatarPrimary ? "aspect-[4/5] max-h-[72vh] sm:aspect-video sm:max-h-[68vh]" : "aspect-video max-h-[68vh]"}`}
          data-testid="teacher-surface"
          data-primary={avatarOn ? primary : "video"}
        >
          {avatarOn && tracks && (
            <div
              className={
                primary === "avatar"
                  ? "absolute inset-0"
                  : "absolute bottom-3 right-3 z-10 aspect-[4/5] w-[30%] max-w-56 overflow-hidden rounded-2xl ring-2 ring-line sm:aspect-video sm:w-[32%] sm:max-w-none"
              }
            >
              <AvatarStage
                track={mirror ? tracks.mirror : tracks.direct}
                videoRef={videoRef}
                view={view}
                reducedMotion={reducedMotion}
                compact={primary !== "avatar"}
                fallback={<StageFallback />}
                chosenDancer={chosenDancer}
              />
            </div>
          )}
          <div
            className={
              avatarPrimary
                ? "absolute right-3 top-3 z-10 aspect-video w-[42%] max-w-72 overflow-hidden rounded-2xl ring-2 ring-line sm:bottom-3 sm:top-auto sm:w-[30%]"
                : "absolute inset-0"
            }
            data-testid="video-layer"
          >
            <div className={`relative h-full w-full ${mirror ? "-scale-x-100" : ""}`} data-testid="mirror-surface" data-mirrored={mirror}>
              <video
                ref={videoRef}
                key={src}
                src={src}
                playsInline
                preload="auto"
                data-testid="learn-video"
                className="absolute inset-0 h-full w-full bg-black object-contain"
                onError={onVideoError}
                onPlay={() => setPlaying(true)}
                onPause={() => setPlaying(false)}
                onClick={togglePlay}
              />
              {poses && skeleton && <SkeletonOverlay videoRef={videoRef} poses={poses} />}
            </div>
          </div>
          {avatarOn && (
            <button
              type="button"
              onClick={() => setPrimary(primary === "avatar" ? "video" : "avatar")}
              className={`absolute z-20 rounded-full bg-studio/85 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-ink ring-1 ring-line backdrop-blur transition hover:ring-lime/60 ${
                avatarPrimary ? "bottom-4 right-4 sm:bottom-5 sm:right-5" : "bottom-5 right-5"
              }`}
            >
              {avatarPrimary ? "Video ⤢" : "Avatar ⤢"}
            </button>
          )}
          {current && !editing && (
            <div className="pointer-events-none absolute bottom-4 left-4 z-10 flex items-center gap-2 rounded-full bg-studio/80 px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-ink backdrop-blur">
              <span className="text-lime">{String(current.position + 1).padStart(2, "0")}</span>
              {formatClock(current.start)}–{formatClock(current.end)}
              {mirror && <span className="text-muted">· mirrored</span>}
            </div>
          )}
          {countdown && (
            <div className="pointer-events-none absolute inset-0 z-30 flex items-center justify-center bg-studio/40" aria-live="assertive" data-testid="count-in">
              <span key={countdown} className="font-display text-8xl font-semibold text-lime motion-safe:animate-[countpop_0.4s_ease-out]">
                {countdown}
              </span>
            </div>
          )}
        </div>
        {webgl === false && poses && (
          <p className="text-sm text-amber" role="status">
            This browser can&apos;t draw 3D (WebGL is off), so the avatar is replaced by the 2-D skeleton on the video.
          </p>
        )}

        {current && !editing && (
          <CoachBar
            text={cueText}
            beat={playing ? beat : null}
            voice={voice}
            setVoice={setVoice}
            canSpeak={speechAvailable()}
            view={avatarOn ? view : null}
            setView={setView}
          />
        )}

        <Transport
          playing={playing}
          onToggle={togglePlay}
          onRestart={() => current && seek(current.start)}
          onStep={(d) => {
            videoRef.current?.pause();
            seek(Math.max(0, Math.min(duration, (videoRef.current?.currentTime ?? 0) + d / (poses?.analysis_fps ?? 12))));
          }}
          loop={loop}
          setLoop={setLoop}
          speed={speed}
          setSpeed={setSpeed}
          mirror={mirror}
          setMirror={setMirror}
          skeleton={skeleton}
          setSkeleton={setSkeleton}
          hasSkeleton={Boolean(poses)}
          time={now}
        />

        {load.kind === "pending" && <div className="h-28 animate-pulse rounded-2xl border border-line bg-raised/50" aria-label="Loading sections" />}
        {load.kind === "error" && <p className="rounded-2xl border border-danger/40 p-4 text-sm text-danger">{load.message}</p>}
        {data && (
          <Timeline
            sections={shown}
            thumbs={sections.map((s) => s.thumbnail_url)}
            duration={duration}
            now={now}
            active={editing ? editIndex : active}
            editing={editing}
            onSelect={(i) => (editing ? seek((shown[i].start + shown[i].end) / 2) : select(i))}
            onSeek={(t) => {
              if (!editing) setActive(Math.max(0, sectionIndexAt(sections, t)));
              seek(t);
            }}
            onMove={(i, t) => draft && setDraft(moveBoundary(draft, i, t, minLen))}
          />
        )}

        {data && (
          <div className="flex flex-wrap items-center gap-2">
            {editing ? (
              <>
                <ToolButton
                  onClick={() => {
                    if (!draft) return;
                    const r = splitAt(draft, now, minLen);
                    if (r.ok) setDraft(r.draft);
                    setNotice(r.ok ? null : r.reason);
                  }}
                >
                  Split at playhead
                </ToolButton>
                <ToolButton
                  disabled={!draft || editIndex >= (draft?.length ?? 0) - 1}
                  onClick={() => {
                    if (!draft) return;
                    const r = mergeWithNext(draft, editIndex);
                    if (r.ok) setDraft(r.draft);
                    setNotice(r.ok ? null : r.reason);
                  }}
                >
                  Merge with next
                </ToolButton>
                <span className="mx-1 hidden h-6 w-px bg-line sm:block" aria-hidden />
                <ToolButton onClick={regenerate} disabled={saving}>
                  Reset to automatic
                </ToolButton>
                <span className="ml-auto flex gap-2">
                  <ToolButton onClick={cancelEditing}>Cancel</ToolButton>
                  <ToolButton primary disabled={!dirty || saving || !draft || !isTiled(draft, duration)} onClick={save}>
                    {saving ? "Saving…" : "Save sections"}
                  </ToolButton>
                </span>
              </>
            ) : (
              <>
                <p className="mr-auto font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
                  {sections.length} sections · {doneCount} done · boundaries are suggestions
                </p>
                <ToolButton onClick={startEditing}>Edit sections</ToolButton>
              </>
            )}
          </div>
        )}
        {editing && (
          <p className="text-sm text-muted">
            Drag a handle (or focus it and use ← →, Shift for half-second steps) to move a boundary. Sections always cover the whole video.
          </p>
        )}
        {notice && (
          <p role="status" className="text-sm text-lime">
            {notice}
          </p>
        )}
      </div>

      <aside className="flex flex-col gap-6">
        {current && !editing && (
          <SectionCard
            section={current}
            total={sections.length}
            instruction={instruction}
            mirror={mirror}
            onComplete={markComplete}
            onPrev={() => select(active - 1)}
            onNext={() => select(active + 1)}
            practiceHref={`/studio/projects/${projectId}/practice?section=${encodeURIComponent(current.id)}`}
          />
        )}
        {aside}
      </aside>
    </div>
  );
}

function StageFallback() {
  return (
    <div className="absolute inset-0 flex items-center justify-center p-6 text-center text-sm text-amber">
      The 3D stage couldn&apos;t start in this browser. Use the video view with the skeleton instead.
    </div>
  );
}

function CoachBar({
  text,
  beat,
  voice,
  setVoice,
  canSpeak,
  view,
  setView,
}: {
  text: string | null;
  beat: number | null;
  voice: boolean;
  setVoice: (v: boolean) => void;
  canSpeak: boolean;
  view: CameraView | null;
  setView: (v: CameraView) => void;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-line bg-raised/60 p-3 sm:flex-row sm:items-center" data-testid="coach-bar">
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <span className="mt-0.5 inline-flex size-9 shrink-0 items-center justify-center rounded-full bg-lime/15 text-lime" aria-hidden>
          <svg viewBox="0 0 24 24" className="size-4">
            <path d="M4 9v6h4l5 4V5L8 9H4z" fill="currentColor" />
            {voice && <path d="M16 8.5a4.5 4.5 0 0 1 0 7M18.5 6a8 8 0 0 1 0 12" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" />}
          </svg>
        </span>
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-muted">
            Coach <span className="rounded-full border border-amber/50 px-1.5 text-amber">experimental</span>
            <span className="flex gap-1" aria-label={beat ? `Count ${beat} of 8` : "Even 8-count"}>
              {Array.from({ length: 8 }, (_, i) => (
                <span key={i} className={`size-1.5 rounded-full ${beat !== null && i < beat ? "bg-lime" : "bg-line"}`} />
              ))}
            </span>
          </p>
          <p className="mt-1 text-base leading-snug text-ink" aria-live="polite" data-testid="coach-caption">
            {text ?? "Pick a section to hear its cue."}
          </p>
          {voice && !canSpeak && <p className="mt-1 text-xs text-muted">This browser has no speech voice. Captions only.</p>}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {view && (
          <div role="radiogroup" aria-label="Camera view" className="flex rounded-full border border-line p-0.5">
            {CAMERA_VIEWS.map((c) => (
              <button
                key={c.id}
                type="button"
                role="radio"
                aria-checked={view === c.id}
                onClick={() => setView(c.id)}
                className={`rounded-full px-2.5 py-1.5 font-mono text-xs transition ${view === c.id ? "bg-ink text-studio" : "text-muted hover:text-ink"}`}
              >
                {c.label}
              </button>
            ))}
          </div>
        )}
        <Toggle label="Voice" on={voice} set={setVoice} />
      </div>
    </div>
  );
}

function Transport(props: {
  playing: boolean;
  onToggle: () => void;
  onRestart: () => void;
  onStep: (frames: number) => void;
  loop: boolean;
  setLoop: (v: boolean) => void;
  speed: Speed;
  setSpeed: (s: Speed) => void;
  mirror: boolean;
  setMirror: (v: boolean) => void;
  skeleton: boolean;
  setSkeleton: (v: boolean) => void;
  hasSkeleton: boolean;
  time: number;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-line bg-raised/60 p-2">
      <button
        type="button"
        onClick={props.onToggle}
        aria-label={props.playing ? "Pause" : "Play section"}
        className="inline-flex size-12 items-center justify-center rounded-full bg-lime text-studio transition hover:scale-105"
      >
        {props.playing ? (
          <svg viewBox="0 0 24 24" className="size-5" aria-hidden>
            <rect x="6" y="5" width="4" height="14" rx="1" fill="currentColor" />
            <rect x="14" y="5" width="4" height="14" rx="1" fill="currentColor" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" className="ml-0.5 size-5" aria-hidden>
            <path d="M7 4.5v15l12-7.5z" fill="currentColor" />
          </svg>
        )}
      </button>
      <IconButton label="Restart section" onClick={props.onRestart}>
        ↺
      </IconButton>
      <IconButton label="Previous analysed frame" onClick={() => props.onStep(-1)}>
        ‹
      </IconButton>
      <IconButton label="Next analysed frame" onClick={() => props.onStep(1)}>
        ›
      </IconButton>
      <span className="px-2 font-mono text-xs tabular-nums text-muted" aria-live="off">
        {formatClock(props.time)}
      </span>
      <div className="ml-auto flex flex-wrap items-center gap-2">
        <div role="radiogroup" aria-label="Playback speed" className="flex rounded-full border border-line p-0.5">
          {SPEEDS.map((s) => (
            <button
              key={s}
              type="button"
              role="radio"
              aria-checked={props.speed === s}
              onClick={() => props.setSpeed(s)}
              className={`rounded-full px-2.5 py-1.5 font-mono text-xs transition ${props.speed === s ? "bg-ink text-studio" : "text-muted hover:text-ink"}`}
            >
              {s}×
            </button>
          ))}
        </div>
        <Toggle label="Loop" on={props.loop} set={props.setLoop} />
        <Toggle label="Mirror" on={props.mirror} set={props.setMirror} />
        {props.hasSkeleton && <Toggle label="Skeleton" on={props.skeleton} set={props.setSkeleton} />}
      </div>
    </div>
  );
}

function Toggle({ label, on, set }: { label: string; on: boolean; set: (v: boolean) => void }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={() => set(!on)}
      className={`rounded-full border px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.1em] transition ${on ? "border-lime/70 bg-lime/10 text-lime" : "border-line text-muted hover:text-ink"}`}
    >
      {label}
    </button>
  );
}

function IconButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="inline-flex size-10 items-center justify-center rounded-full border border-line text-lg text-ink transition hover:border-lime/60"
    >
      {children}
    </button>
  );
}

function ToolButton({
  children,
  onClick,
  disabled,
  primary,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  primary?: boolean;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`rounded-full px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-40 ${
        primary ? "bg-lime text-studio enabled:hover:-translate-y-0.5" : "border border-line text-ink enabled:hover:border-lime/60"
      }`}
    >
      {children}
    </button>
  );
}

function Timeline({
  sections,
  thumbs,
  duration,
  now,
  active,
  editing,
  onSelect,
  onSeek,
  onMove,
}: {
  sections: { start: number; end: number; title: string; completed: boolean }[];
  thumbs: (string | null)[];
  duration: number;
  now: number;
  active: number;
  editing: boolean;
  onSelect: (i: number) => void;
  onSeek: (t: number) => void;
  onMove: (boundary: number, t: number) => void;
}) {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const [drag, setDrag] = useState<number | null>(null);
  const pct = (t: number) => `${duration > 0 ? (t / duration) * 100 : 0}%`;
  const timeAt = (clientX: number) => {
    const box = trackRef.current?.getBoundingClientRect();
    if (!box || box.width === 0) return 0;
    return Math.max(0, Math.min(duration, ((clientX - box.left) / box.width) * duration));
  };

  return (
    <div className="select-none" data-testid="section-timeline">
      <div
        ref={trackRef}
        className="relative h-24 touch-none rounded-2xl border border-line bg-raised/40"
        onPointerMove={(e) => {
          if (drag !== null) onMove(drag, timeAt(e.clientX));
        }}
        onPointerUp={() => setDrag(null)}
        onPointerCancel={() => setDrag(null)}
      >
        {sections.map((s, i) => {
          const thumb = !editing || sections.length === thumbs.length ? thumbs[i] : null;
          return (
            <button
              key={`${i}-${s.start}`}
              type="button"
              onClick={() => onSelect(i)}
              aria-label={`${s.title}, ${formatClock(s.start)} to ${formatClock(s.end)}${s.completed ? ", completed" : ""}`}
              aria-current={i === active ? "true" : undefined}
              data-testid="section-chip"
              className={`group absolute inset-y-1.5 overflow-hidden rounded-xl text-left transition ${
                i === active ? "ring-2 ring-lime" : "ring-1 ring-line hover:ring-lime/50"
              }`}
              style={{ left: `calc(${pct(s.start)} + 3px)`, width: `calc(${pct(s.end - s.start)} - 6px)` }}
            >
              {thumb && (
                // eslint-disable-next-line @next/next/no-img-element -- private signed URL, not optimisable
                <img src={mediaHref(thumb)} alt="" className="absolute inset-0 h-full w-full object-cover opacity-40 transition group-hover:opacity-60" />
              )}
              <span className="absolute inset-0 bg-gradient-to-t from-studio/90 via-studio/30 to-transparent" aria-hidden />
              <span className="relative flex h-full flex-col justify-between p-2">
                <span className="flex items-center justify-between gap-1 font-mono text-[11px] font-semibold text-lime">
                  {String(i + 1).padStart(2, "0")}
                  {s.completed && (
                    <span className="inline-flex size-4 items-center justify-center rounded-full bg-lime text-[10px] text-studio" aria-hidden>
                      ✓
                    </span>
                  )}
                </span>
                <span className="truncate font-mono text-[10px] text-ink/80">
                  {formatClock(s.start)}–{formatClock(s.end)}
                </span>
              </span>
            </button>
          );
        })}

        {editing &&
          sections.slice(0, -1).map((s, i) => (
            <span
              key={`h-${i}`}
              role="slider"
              tabIndex={0}
              aria-label={`Boundary between section ${i + 1} and ${i + 2}`}
              aria-valuemin={0}
              aria-valuemax={Math.round(duration * 1000) / 1000}
              aria-valuenow={s.end}
              aria-valuetext={formatClock(s.end)}
              data-testid="boundary-handle"
              onPointerDown={(e) => {
                e.currentTarget.parentElement?.setPointerCapture(e.pointerId);
                setDrag(i);
              }}
              onKeyDown={(e) => {
                const step = e.shiftKey ? 0.5 : FRAME;
                if (e.key === "ArrowLeft") onMove(i, s.end - step);
                else if (e.key === "ArrowRight") onMove(i, s.end + step);
                else return;
                e.preventDefault();
              }}
              className="absolute inset-y-0 z-10 -ml-3 flex w-6 cursor-ew-resize items-center justify-center"
              style={{ left: pct(s.end) }}
            >
              <span className={`h-full w-1.5 rounded-full ${drag === i ? "bg-ink" : "bg-lime"} shadow-[0_0_0_3px_rgb(16_18_15)]`} />
            </span>
          ))}

        <span className="pointer-events-none absolute inset-y-0 z-20 w-0.5 bg-ink" style={{ left: pct(now) }} aria-hidden>
          <span className="absolute -top-1.5 -left-1 size-2.5 rounded-full bg-ink" />
        </span>
      </div>
      <input
        type="range"
        min={0}
        max={duration}
        step={0.01}
        value={Math.min(now, duration)}
        onChange={(e) => onSeek(Number(e.target.value))}
        aria-label="Playhead"
        className="mt-2 w-full accent-[var(--color-lime)]"
      />
    </div>
  );
}

function SectionCard({
  section,
  total,
  instruction,
  mirror,
  onComplete,
  onPrev,
  onNext,
  practiceHref,
}: {
  practiceHref: string;
  section: Section;
  total: number;
  instruction: string | null;
  mirror: boolean;
  onComplete: () => void;
  onPrev: () => void;
  onNext: () => void;
}) {
  const n = section.position + 1;
  const coverage = section.coverage ?? 0;
  return (
    <section className="relative overflow-hidden rounded-3xl border border-line bg-raised/70 p-6" aria-labelledby="section-title">
      <span className="absolute inset-y-0 left-0 w-1 bg-lime" aria-hidden />
      <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted">
        Section {String(n).padStart(2, "0")} of {String(total).padStart(2, "0")} · {formatClock(section.start)}–{formatClock(section.end)}
      </p>
      <h2 id="section-title" className="mt-2 font-display text-2xl font-semibold">
        {section.title}
      </h2>

      <div className="mt-5">
        <p className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-amber">
          <span className="rounded-full border border-amber/50 px-2 py-0.5">Experimental</span>
          {mirror ? "mirror view" : "direct view"}
        </p>
        <p className="mt-3 text-lg leading-snug text-ink" data-testid="section-instruction">
          {instruction ?? "No instruction for this section."}
        </p>
        <p className="mt-2 text-xs leading-relaxed text-muted">
          Worded from measured angles and positions only. The video is the source of truth.
        </p>
      </div>

      <dl className="mt-5 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">Tracked frames</dt>
          <dd className={`mt-1 font-mono ${coverage < 0.55 ? "text-amber" : "text-ink"}`}>{Math.round(coverage * 100)}%</dd>
        </div>
        <div>
          <dt className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">Boundaries</dt>
          <dd className="mt-1 font-mono text-ink">{section.boundary_source === "manual" ? "edited" : "suggested"}</dd>
        </div>
      </dl>
      {section.untracked.length > 0 && (
        <p className="mt-4 text-xs text-muted">
          Not tracked here, so not described: <span className="text-amber">{section.untracked.join(", ")}</span>.
        </p>
      )}

      <div className="mt-6 flex flex-col gap-3">
        <button
          type="button"
          onClick={onComplete}
          aria-pressed={section.completed}
          className={`inline-flex h-12 w-full items-center justify-center rounded-full px-6 font-display text-xs font-semibold uppercase tracking-[0.12em] transition hover:-translate-y-0.5 ${
            section.completed ? "border border-lime/60 text-lime" : "bg-lime text-studio"
          }`}
        >
          {section.completed ? "✓ Completed — undo" : "Mark complete"}
        </button>
        <Link
          href={practiceHref}
          data-testid="practice-section"
          className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-full border border-lime/60 px-6 font-display text-xs font-semibold uppercase tracking-[0.12em] text-lime transition hover:-translate-y-0.5"
        >
          <span aria-hidden className="size-2 rounded-full bg-danger" />
          Practise this section
        </Link>
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={onPrev}
            disabled={n <= 1}
            className="rounded-full border border-line px-4 py-2 text-sm text-ink transition enabled:hover:border-lime/60 disabled:opacity-40"
          >
            ← Previous
          </button>
          <button
            type="button"
            onClick={onNext}
            disabled={n >= total}
            className="rounded-full border border-line px-4 py-2 text-sm text-ink transition enabled:hover:border-lime/60 disabled:opacity-40"
          >
            Next section →
          </button>
        </div>
      </div>
    </section>
  );
}

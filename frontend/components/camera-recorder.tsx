"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  CAMERA_HELP,
  COUNTDOWN_SECONDS,
  type CameraProblem,
  cameraProblem,
  extensionFor,
  formatClock,
  pickRecorderType,
} from "@/lib/practice";

type Phase =
  | { kind: "idle" }
  | { kind: "starting" }
  | { kind: "live" }
  | { kind: "countdown"; n: number }
  | { kind: "recording"; startedAt: number }
  | { kind: "review"; file: File; url: string; seconds: number }
  | { kind: "problem"; problem: CameraProblem };

export interface CameraTake {
  file: File;
  seconds: number;
}

/**
 * Webcam capture with MediaRecorder: permission guidance → live mirrored preview → 3-2-1 →
 * recording (elapsed / limit, auto-stop) → preview → retry or use the take.
 *
 * The preview is mirrored like a bathroom mirror, but the recorder captures the camera's
 * own unmirrored frames, so the stored attempt is never flipped (spec 16).
 */
export function CameraRecorder({
  limitSeconds,
  guide,
  onRecordingChange,
  onUse,
  onUploadInstead,
  busy,
}: {
  limitSeconds: number;
  /** Reference guide shown while recording; receives play/stop signals. */
  guide?: (state: { recording: boolean; countdown: number | null }) => React.ReactNode;
  onRecordingChange?: (recording: boolean) => void;
  onUse: (take: CameraTake) => void;
  onUploadInstead: () => void;
  busy: boolean;
}) {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [elapsed, setElapsed] = useState(0);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timersRef = useRef<number[]>([]);
  const reviewUrl = phase.kind === "review" ? phase.url : null;

  const clearTimers = () => {
    timersRef.current.forEach((t) => window.clearTimeout(t));
    timersRef.current = [];
  };

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  useEffect(
    () => () => {
      clearTimers();
      try {
        const rec = recorderRef.current;
        if (rec && rec.state !== "inactive") {
          rec.onstop = null;
          rec.stop();
        }
      } catch {
        /* already stopped */
      }
      stopStream();
    },
    [stopStream],
  );

  useEffect(() => {
    if (!reviewUrl) return;
    return () => URL.revokeObjectURL(reviewUrl);
  }, [reviewUrl]);

  useEffect(() => {
    onRecordingChange?.(phase.kind === "recording");
  }, [phase.kind, onRecordingChange]);

  // Attach the live stream whenever the preview element is (re)mounted.
  useEffect(() => {
    const v = videoRef.current;
    if (!v || !streamRef.current) return;
    if (phase.kind === "live" || phase.kind === "countdown" || phase.kind === "recording") {
      if (v.srcObject !== streamRef.current) {
        v.srcObject = streamRef.current;
        void v.play().catch(() => {});
      }
    }
  }, [phase.kind]);

  const start = async () => {
    const secure = typeof window === "undefined" || window.isSecureContext;
    if (!secure || !navigator.mediaDevices?.getUserMedia) {
      setPhase({ kind: "problem", problem: secure ? "unsupported" : "insecure" });
      return;
    }
    if (typeof MediaRecorder === "undefined") {
      setPhase({ kind: "problem", problem: "unsupported" });
      return;
    }
    setPhase({ kind: "starting" });
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
        audio: false,
      });
      streamRef.current = stream;
      setPhase({ kind: "live" });
    } catch (err) {
      setPhase({ kind: "problem", problem: cameraProblem(err) });
    }
  };

  const finish = useCallback(
    (mime: string, startedAt: number) => {
      const blob = new Blob(chunksRef.current, { type: mime });
      chunksRef.current = [];
      const seconds = (performance.now() - startedAt) / 1000;
      if (blob.size === 0) {
        setPhase({ kind: "problem", problem: "failed" });
        return;
      }
      const stamp = new Date().toISOString().replace(/[:.]/g, "-");
      const file = new File([blob], `attempt-${stamp}${extensionFor(mime)}`, { type: mime.split(";")[0] });
      stopStream();
      setPhase({ kind: "review", file, url: URL.createObjectURL(blob), seconds });
    },
    [stopStream],
  );

  const record = () => {
    const stream = streamRef.current;
    if (!stream) return;
    const mime = pickRecorderType((t) => MediaRecorder.isTypeSupported(t));
    if (!mime) {
      setPhase({ kind: "problem", problem: "unsupported" });
      return;
    }
    clearTimers();
    for (let i = 0; i < COUNTDOWN_SECONDS; i++) {
      timersRef.current.push(window.setTimeout(() => setPhase({ kind: "countdown", n: COUNTDOWN_SECONDS - i }), i * 1000));
    }
    timersRef.current.push(
      window.setTimeout(() => {
        let rec: MediaRecorder;
        try {
          rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 2_500_000 });
        } catch (err) {
          setPhase({ kind: "problem", problem: cameraProblem(err) });
          return;
        }
        chunksRef.current = [];
        const startedAt = performance.now();
        rec.ondataavailable = (e) => {
          if (e.data.size > 0) chunksRef.current.push(e.data);
        };
        rec.onstop = () => finish(mime, startedAt);
        rec.onerror = () => setPhase({ kind: "problem", problem: "failed" });
        recorderRef.current = rec;
        rec.start(500);
        setElapsed(0);
        setPhase({ kind: "recording", startedAt });
      }, COUNTDOWN_SECONDS * 1000),
    );
    setPhase({ kind: "countdown", n: COUNTDOWN_SECONDS });
  };

  const stop = useCallback(() => {
    const rec = recorderRef.current;
    if (rec && rec.state !== "inactive") rec.stop();
  }, []);

  // Elapsed clock + auto-stop at the limit.
  useEffect(() => {
    if (phase.kind !== "recording") return;
    const id = window.setInterval(() => {
      const s = (performance.now() - phase.startedAt) / 1000;
      setElapsed(s);
      if (s >= limitSeconds) stop();
    }, 200);
    return () => window.clearInterval(id);
  }, [phase, limitSeconds, stop]);

  const retake = async () => {
    setPhase({ kind: "idle" });
    await start();
  };

  const cancelCountdown = () => {
    clearTimers();
    setPhase({ kind: "live" });
  };

  const showLive = phase.kind === "live" || phase.kind === "countdown" || phase.kind === "recording";

  return (
    <div className="flex flex-col gap-4" data-testid="camera-recorder" data-phase={phase.kind}>
      <div className="relative overflow-hidden rounded-3xl border border-line bg-black">
        <div className="relative aspect-video w-full">
          {showLive && (
            <video
              ref={videoRef}
              muted
              playsInline
              autoPlay
              aria-label="Live camera preview (mirrored)"
              className="absolute inset-0 h-full w-full -scale-x-100 object-cover"
            />
          )}
          {phase.kind === "review" && (
            <video
              key={phase.url}
              src={phase.url}
              controls
              playsInline
              aria-label="Your recorded take"
              data-testid="take-preview"
              className="absolute inset-0 h-full w-full bg-black object-contain"
            />
          )}
          {(phase.kind === "idle" || phase.kind === "starting" || phase.kind === "problem") && (
            <CameraIntro phase={phase} onStart={start} onUploadInstead={onUploadInstead} />
          )}

          {showLive && phase.kind !== "recording" && <FramingGuide />}
          {guide && showLive && (
            <div className="absolute bottom-3 right-3 w-[34%] min-w-32 overflow-hidden rounded-2xl border border-line/80 bg-black shadow-2xl">
              {guide({ recording: phase.kind === "recording", countdown: phase.kind === "countdown" ? phase.n : null })}
            </div>
          )}
          {phase.kind === "countdown" && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/35" aria-live="assertive">
              <span key={phase.n} className="font-display text-[22vw] font-bold leading-none text-lime motion-safe:animate-[countpop_0.5s_ease-out] sm:text-9xl">
                {phase.n}
              </span>
            </div>
          )}
          {phase.kind === "recording" && (
            <div className="absolute left-3 top-3 flex items-center gap-2 rounded-full bg-black/70 px-3 py-1.5 font-mono text-xs text-ink" role="status" aria-live="off" data-testid="rec-clock">
              <span aria-hidden className="size-2.5 rounded-full bg-danger motion-safe:animate-pulse-dot" />
              REC {formatClock(elapsed)} / {formatClock(limitSeconds)}
            </div>
          )}
          {showLive && (
            <span className="absolute right-3 top-3 rounded-full bg-black/60 px-2.5 py-1 font-mono text-[9px] uppercase tracking-[0.14em] text-muted sm:text-[10px]">
              Mirrored preview · saved unmirrored
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        {phase.kind === "live" && (
          <button type="button" onClick={record} data-testid="record" className={PRIMARY}>
            <span aria-hidden className="size-3 rounded-full bg-danger" /> Record
          </button>
        )}
        {phase.kind === "countdown" && (
          <button type="button" onClick={cancelCountdown} className={SECONDARY}>
            Cancel
          </button>
        )}
        {phase.kind === "recording" && (
          <button type="button" onClick={stop} data-testid="stop" className={PRIMARY}>
            <span aria-hidden className="size-3 rounded-sm bg-studio" /> Stop
          </button>
        )}
        {phase.kind === "review" && (
          <>
            <button
              type="button"
              disabled={busy}
              onClick={() => onUse({ file: phase.file, seconds: phase.seconds })}
              data-testid="use-take"
              className={PRIMARY}
            >
              {busy ? "Uploading…" : "Use this take"}
            </button>
            <button type="button" disabled={busy} onClick={retake} data-testid="retake" className={SECONDARY}>
              Record again
            </button>
            <span className="font-mono text-xs text-muted">
              {formatClock(phase.seconds)} · {(phase.file.size / 1_048_576).toFixed(1)} MB
            </span>
          </>
        )}
        {phase.kind === "recording" && (
          <p className="text-sm text-muted">Stops by itself at {formatClock(limitSeconds)}.</p>
        )}
      </div>
    </div>
  );
}

const PRIMARY =
  "inline-flex h-12 items-center justify-center gap-2 rounded-full bg-lime px-6 font-display text-xs font-semibold uppercase tracking-[0.12em] text-studio transition enabled:hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-60";
const SECONDARY =
  "inline-flex h-12 items-center justify-center rounded-full border border-line px-6 font-display text-xs font-semibold uppercase tracking-[0.12em] text-ink transition enabled:hover:border-lime/60 disabled:opacity-50";

function CameraIntro({
  phase,
  onStart,
  onUploadInstead,
}: {
  phase: Phase;
  onStart: () => void;
  onUploadInstead: () => void;
}) {
  const problem = phase.kind === "problem" ? CAMERA_HELP[phase.problem] : null;
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 overflow-y-auto bg-[radial-gradient(circle_at_50%_30%,rgba(193,248,106,0.10),transparent_60%)] p-5 text-center">
      {problem ? (
        <div role="alert" className="max-w-md" data-testid="camera-problem">
          <p className="font-display text-lg font-semibold text-danger">{problem.title}</p>
          <p className="mt-2 text-sm text-muted">{problem.body}</p>
        </div>
      ) : (
        <div className="max-w-md">
          <p className="font-display text-lg font-semibold text-ink">Set up your space</p>
          <ul className="mt-3 space-y-1.5 text-left text-sm text-muted">
            <li>· Step back until your whole body — head to feet — fits in the frame.</li>
            <li>· Light in front of you, not behind. One dancer in view.</li>
            <li>· A similar camera angle to the reference helps the comparison.</li>
          </ul>
          <p className="mt-3 text-xs text-muted">Your recording stays private to your session.</p>
        </div>
      )}
      <div className="flex flex-wrap justify-center gap-3">
        <button type="button" onClick={onStart} disabled={phase.kind === "starting"} data-testid="camera-on" className={PRIMARY}>
          {phase.kind === "starting" ? "Waiting for permission…" : problem ? "Try the camera again" : "Turn on camera"}
        </button>
        <button type="button" onClick={onUploadInstead} className={SECONDARY}>
          Upload a video instead
        </button>
      </div>
    </div>
  );
}

/** Head-to-feet guide so learners frame their whole body (quality suggestion, not a gate). */
function FramingGuide() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 flex items-center justify-center">
      <div className="h-[88%] aspect-[9/16] rounded-[40%_40%_12%_12%/18%_18%_6%_6%] border-2 border-dashed border-lime/45" />
    </div>
  );
}

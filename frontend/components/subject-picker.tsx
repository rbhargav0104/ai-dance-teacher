"use client";

import { useEffect, useState } from "react";

import { percent } from "@/lib/pose";
import { cropStyle, padBox, personLabel } from "@/lib/subject";
import type { SubjectInfo } from "@/lib/types";

/**
 * "Who should we follow?" (spec amendment A2). Every outline is a real MediaPipe detection on a
 * real frame of the video; nothing here is drawn by hand. Picking a person re-runs the analysis
 * following only them.
 */
export function SubjectPicker({
  subject,
  loadFrame,
  onChoose,
  variant = "stage",
  disabledReason,
  onCancel,
}: {
  subject: SubjectInfo;
  loadFrame: () => Promise<string>;
  onChoose: (person: number) => Promise<void>;
  variant?: "stage" | "compact";
  disabledReason?: string | null;
  onCancel?: () => void;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [frameError, setFrameError] = useState(false);
  const [aspect, setAspect] = useState(16 / 9);
  const [hover, setHover] = useState<number | null>(null);
  const [pending, setPending] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const chosen = subject.choice?.person ?? null;
  const compact = variant === "compact";

  useEffect(() => {
    let cancelled = false;
    loadFrame()
      .then((url) => !cancelled && setSrc(url))
      .catch(() => !cancelled && setFrameError(true));
    return () => {
      cancelled = true;
    };
  }, [loadFrame]);

  const pick = async (person: number) => {
    if (pending !== null || disabledReason) return;
    setPending(person);
    setError(null);
    try {
      await onChoose(person);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't start the analysis. Try again.");
    } finally {
      setPending(null);
    }
  };

  return (
    <section
      aria-labelledby="subject-picker-title"
      data-testid="subject-picker"
      className={
        compact
          ? "rounded-2xl border border-line bg-raised/40 p-4"
          : "rounded-3xl border border-lime/25 bg-[radial-gradient(120%_80%_at_0%_0%,rgba(193,248,106,0.08),transparent_60%)] p-4 sm:p-6"
      }
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-lime">
            {subject.candidates.length} people in this video
          </p>
          <h2
            id="subject-picker-title"
            className={compact ? "mt-1 font-display text-lg font-semibold" : "mt-2 font-display text-2xl font-bold tracking-tight sm:text-3xl"}
          >
            {chosen ? "Follow someone else?" : "Who should we follow?"}
          </h2>
          <p className="mt-2 max-w-prose text-sm text-muted">
            Tap the dancer you want to learn from. We&apos;ll analyse only them; everyone else is ignored, and if we lose
            them for a moment we leave that moment out rather than guess.
          </p>
        </div>
        {onCancel && (
          <button type="button" onClick={onCancel} className="-mr-1 -mt-1 shrink-0 rounded-full px-3 py-2 text-sm text-muted transition hover:text-ink">
            Close
          </button>
        )}
      </div>

      <figure className="relative mt-4 overflow-hidden rounded-2xl border border-line bg-black" style={{ aspectRatio: String(aspect) }}>
        {src && !frameError ? (
          // eslint-disable-next-line @next/next/no-img-element -- private signed URL, not a static asset
          <img
            src={src}
            alt={`Frame at ${subject.frame_time.toFixed(1)} s showing the people we found`}
            className="absolute inset-0 h-full w-full object-cover"
            onLoad={(e) => {
              const img = e.currentTarget;
              if (img.naturalWidth && img.naturalHeight) setAspect(img.naturalWidth / img.naturalHeight);
            }}
            onError={() => setFrameError(true)}
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center p-4 text-center text-sm text-muted">
            {frameError ? "The frame couldn't be loaded — the people are still listed below." : <span className="animate-pulse">Loading frame…</span>}
          </div>
        )}
        {subject.candidates.map((c) => {
          // Landmarks stop at the eyes and wrists: pad a little, and more above for the head.
          const [x0, py0, x1, y1] = padBox(c.box, 0.06);
          const y0 = Math.max(0, py0 - (y1 - py0) * 0.1);
          const active = hover === c.person || chosen === c.person || pending === c.person;
          return (
            <button
              key={c.person}
              type="button"
              tabIndex={-1}
              aria-hidden
              onClick={() => pick(c.person)}
              onMouseEnter={() => setHover(c.person)}
              onMouseLeave={() => setHover(null)}
              className={`absolute rounded-xl border-2 transition-[border-color,box-shadow,background-color] duration-200 motion-reduce:transition-none ${
                active
                  ? "border-lime bg-lime/10 shadow-[0_0_0_4px_rgba(193,248,106,0.25)]"
                  : "border-white/70 bg-transparent hover:border-lime"
              }`}
              style={{ left: `${x0 * 100}%`, top: `${y0 * 100}%`, width: `${(x1 - x0) * 100}%`, height: `${(y1 - y0) * 100}%` }}
            >
              <span
                className={`absolute -left-0.5 -top-0.5 flex size-7 items-center justify-center rounded-br-xl rounded-tl-xl font-display text-sm font-bold ${
                  active ? "bg-lime text-studio" : "bg-white text-studio"
                }`}
              >
                {c.person}
              </span>
            </button>
          );
        })}
      </figure>

      <ul className={`mt-4 grid gap-3 ${compact ? "grid-cols-2" : "grid-cols-2 md:grid-cols-4"}`} role="list">
        {subject.candidates.map((c) => {
          const isChosen = chosen === c.person;
          const busy = pending === c.person;
          return (
            <li key={c.person}>
              <button
                type="button"
                data-testid={`subject-person-${c.person}`}
                disabled={pending !== null || Boolean(disabledReason)}
                aria-pressed={isChosen}
                aria-label={`Follow ${personLabel(c)}, in ${percent(c.share)} of the video${isChosen ? " (currently followed)" : ""}`}
                onClick={() => pick(c.person)}
                onMouseEnter={() => setHover(c.person)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(c.person)}
                onBlur={() => setHover(null)}
                className={`group flex w-full flex-col overflow-hidden rounded-2xl border text-left transition duration-200 enabled:hover:-translate-y-0.5 motion-reduce:transition-none disabled:cursor-not-allowed disabled:opacity-60 ${
                  isChosen ? "border-lime bg-lime/10" : "border-line bg-studio enabled:hover:border-lime/60"
                }`}
              >
                <span
                  aria-hidden
                  className="block w-full bg-black bg-no-repeat"
                  style={src && !frameError ? cropStyle(c.box, aspect, src) : { aspectRatio: "3 / 4" }}
                />
                <span className="flex flex-col gap-2 px-3 py-2.5">
                  <span className="min-w-0">
                    <span className="block font-display text-sm font-semibold text-ink">Person {c.person}</span>
                    <span className="block font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                      {c.position} · in {percent(c.share)}
                    </span>
                  </span>
                  <span
                    className={`rounded-full px-2.5 py-1.5 text-center font-mono text-[10px] uppercase tracking-[0.12em] ${
                      isChosen ? "bg-lime text-studio" : "border border-line text-ink group-hover:border-lime/60"
                    }`}
                  >
                    {busy ? "Starting…" : isChosen ? "Following" : "Follow"}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {(error || disabledReason) && (
        <p className="mt-3 text-sm text-amber" role="status">
          {error ?? disabledReason}
        </p>
      )}
    </section>
  );
}

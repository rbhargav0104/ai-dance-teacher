import Link from "next/link";

import { HeroFigure } from "@/components/hero-figure";

const STEPS = [
  {
    n: "01",
    title: "Break it down",
    body: "We read every frame, find the dancer's pose, and suggest short sections you can edit.",
  },
  {
    n: "02",
    title: "Practice privately",
    body: "Loop, slow down and mirror each section. Record yourself or upload a take — only you see it.",
  },
  {
    n: "03",
    title: "Get measured feedback",
    body: "Your movement is compared joint by joint, with timestamps you can replay and fix.",
  },
];

export default function Landing() {
  return (
    <>
      <section className="mx-auto grid w-full max-w-7xl flex-1 items-center gap-10 px-4 pb-16 pt-10 sm:px-8 lg:grid-cols-[1.15fr_0.85fr] lg:gap-6 lg:pt-16">
        <div className="max-w-2xl">
          <p className="mb-6 inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.22em] text-muted">
            <span className="h-px w-8 bg-lime" aria-hidden />
            Your private practice room
          </p>
          <h1 className="font-display text-[clamp(2.6rem,7.2vw,5.6rem)] font-bold leading-[0.95] tracking-[-0.03em] text-ink">
            Learn any dance.
            <span className="mt-2 block text-lime">Frame by frame.</span>
          </h1>
          <p className="mt-7 max-w-xl text-lg leading-relaxed text-muted sm:text-xl">
            Upload any choreography, let AI break it down, practice it, and get instant feedback on
            your performance.
          </p>
          <div className="mt-10 flex flex-col gap-3 sm:flex-row sm:items-center">
            <Link
              href="/studio"
              className="group inline-flex h-14 items-center justify-center gap-3 rounded-full bg-lime px-8 font-display text-sm font-semibold uppercase tracking-[0.12em] text-studio transition hover:-translate-y-0.5 hover:shadow-[0_12px_40px_-12px_var(--color-lime)]"
            >
              Learn a Dance
              <span aria-hidden className="transition group-hover:translate-x-1">→</span>
            </Link>
            <Link
              href="/studio?demo=1"
              className="inline-flex h-14 items-center justify-center rounded-full border border-line px-8 font-display text-sm font-semibold uppercase tracking-[0.12em] text-ink transition hover:border-lime"
            >
              Try Demo
            </Link>
          </div>
          <p className="mt-6 text-sm text-muted">
            Videos stay private to you and can be deleted at any time.
          </p>
        </div>
        <div className="relative mx-auto aspect-[5/6] w-full max-w-md lg:max-w-none">
          <div className="absolute inset-0 rounded-[2rem] border border-line bg-raised/40" />
          <div className="absolute inset-4 sm:inset-6">
            <HeroFigure />
          </div>
        </div>
      </section>
      <section aria-labelledby="how" className="border-t border-line/60">
        <div className="mx-auto max-w-7xl px-4 py-16 sm:px-8">
          <h2 id="how" className="sr-only">
            How it works
          </h2>
          <ol className="grid gap-10 md:grid-cols-3 md:gap-8">
            {STEPS.map((s) => (
              <li key={s.n} className="border-l border-line pl-6">
                <span className="font-mono text-xs text-lime">{s.n}</span>
                <h3 className="mt-3 font-display text-xl font-semibold tracking-tight">{s.title}</h3>
                <p className="mt-3 leading-relaxed text-muted">{s.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>
    </>
  );
}

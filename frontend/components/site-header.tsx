import Link from "next/link";

import { StatusPill } from "./studio-status";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-30 border-b border-line/60 bg-studio/75 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-8">
        <Link href="/" className="group flex items-center gap-2.5" aria-label="AI Dance Teacher home">
          <Mark />
          <span className="font-display text-[13px] font-semibold uppercase tracking-[0.18em] text-ink sm:text-sm">
            AI Dance <span className="text-lime">Teacher</span>
          </span>
        </Link>
        <StatusPill />
      </div>
    </header>
  );
}

function Mark() {
  return (
    <svg viewBox="0 0 32 32" className="size-7" aria-hidden>
      <rect width="32" height="32" rx="9" className="fill-raised" />
      <g stroke="var(--color-lime)" strokeWidth="2.2" strokeLinecap="round" fill="none">
        <path d="M16 11v8M16 13l-6-3M16 13l5 4M16 19l-4 7M16 19l6 5" />
      </g>
      <circle cx="16" cy="7.5" r="2.6" fill="var(--color-lime)" />
    </svg>
  );
}

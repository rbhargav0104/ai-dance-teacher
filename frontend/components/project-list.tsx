"use client";

import Link from "next/link";
import { useState } from "react";

import { formatDuration, projectStatusLabel } from "@/lib/media";
import type { Project } from "@/lib/types";

const TONE = {
  lime: "border-lime/40 text-lime",
  amber: "border-amber/40 text-amber",
  danger: "border-danger/40 text-danger",
  muted: "border-line text-muted",
} as const;

export function StatusChip({ status }: { status: string }) {
  const { label, tone } = projectStatusLabel(status);
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] ${TONE[tone]}`}>
      <span aria-hidden className="size-1.5 rounded-full bg-current" />
      {label}
    </span>
  );
}

export function ProjectList({
  projects,
  limit,
  onDelete,
}: {
  projects: Project[];
  limit: number;
  onDelete: (project: Project) => Promise<void>;
}) {
  if (projects.length === 0) {
    return (
      <p className="mt-6 rounded-2xl border border-line/70 px-5 py-6 text-muted">
        No dances yet. Upload one above, or add a licensed sample clip.
      </p>
    );
  }
  return (
    <div className="mt-6">
      <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted">
        {projects.length} of {limit} dances
      </p>
      <ul className="mt-3 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {projects.map((p) => (
          <ProjectCard key={p.id} project={p} onDelete={onDelete} />
        ))}
      </ul>
    </div>
  );
}

function ProjectCard({ project, onDelete }: { project: Project; onDelete: (p: Project) => Promise<void> }) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const ref = project.reference;
  return (
    <li className="group relative flex flex-col overflow-hidden rounded-3xl border border-line bg-raised/60 transition hover:border-lime/50">
      <Link
        href={`/studio/projects/${project.id}`}
        className="flex flex-1 flex-col p-5 focus-visible:outline-offset-[-3px]"
        aria-label={`Open ${project.title}`}
      >
        {ref && <FrameShape width={ref.width} height={ref.height} />}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <StatusChip status={project.status} />
          {project.is_demo && (
            <span className="rounded-full bg-lime/10 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-lime">
              Sample
            </span>
          )}
        </div>
        <h3 className="mt-3 line-clamp-2 font-display text-lg font-semibold tracking-tight text-ink">
          {project.title}
        </h3>
        {ref && (
          <p className="mt-1 font-mono text-xs text-muted">
            {formatDuration(ref.duration)} · {ref.width}×{ref.height} · {Math.round(ref.source_fps)} fps
          </p>
        )}
      </Link>
      <div className="flex items-center justify-end gap-2 border-t border-line/70 px-4 py-3">
        {confirming ? (
          <>
            <span className="mr-auto text-sm text-muted">Delete video and data?</span>
            <button type="button" onClick={() => setConfirming(false)} className="rounded-full px-3 py-1.5 text-sm text-muted hover:text-ink">
              Keep
            </button>
            <button
              type="button"
              disabled={deleting}
              onClick={async () => {
                setDeleting(true);
                try {
                  await onDelete(project);
                } finally {
                  setDeleting(false);
                  setConfirming(false);
                }
              }}
              className="rounded-full bg-danger px-3 py-1.5 text-sm font-semibold text-studio disabled:opacity-60"
            >
              {deleting ? "Deleting…" : "Delete"}
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="rounded-full px-3 py-1.5 text-sm text-muted transition hover:text-danger"
            aria-label={`Delete ${project.title}`}
          >
            Delete
          </button>
        )}
      </div>
    </li>
  );
}

/** Frame-shape placeholder: shows the clip's real aspect ratio. Thumbnails arrive with analysis. */
function FrameShape({ width, height }: { width: number; height: number }) {
  const portrait = height > width;
  return (
    <div aria-hidden className="flex h-28 items-center justify-center rounded-2xl bg-studio/70">
      <div
        className="flex items-center justify-center rounded-lg border border-line bg-raised transition-colors group-hover:border-lime/50"
        style={portrait ? { height: "80%", aspectRatio: `${width} / ${height}` } : { width: "55%", aspectRatio: `${width} / ${height}` }}
      >
        <svg viewBox="0 0 16 16" className="size-5 text-muted group-hover:text-lime" fill="currentColor">
          <path d="M5 3.5v9l7-4.5z" />
        </svg>
      </div>
    </div>
  );
}

"""Teachable sections: automatic suggestions, validated edits, thumbnails and instructions.

Reads the measured per-frame features stored by the reference analysis (reference_pose_frames),
so automatic generation, regeneration and edits all use the same data and code path.
"""

from __future__ import annotations

import logging
import math
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.base import new_id
from app.media.transcode import TranscodeFailed, make_poster
from app.models import DanceProject, DanceSegment, ReferencePoseFrame, ReferenceVideo
from app.pose import landmarks as L
from app.pose.instructions import INSTRUCTIONS_VERSION, SectionInput, describe_section
from app.pose.segmentation import (
    SEGMENTATION_VERSION,
    InvalidSections,
    SegmentationConfig,
    suggest_boundaries,
    validate_sections,
)
from app.services.intake import project_prefix
from app.storage.base import ObjectStorage

log = logging.getLogger("app.sections")

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]

_AUTO_TITLE = re.compile(r"^Section \d{2}$")
ALGORITHM_VERSION = f"{SEGMENTATION_VERSION}+{INSTRUCTIONS_VERSION}"


class SectionsUnavailable(Exception):
    pass


@dataclass(frozen=True)
class StoredTrack:
    times: FloatArray
    valid: BoolArray
    energy: FloatArray
    norm: FloatArray  # (T,33,2)
    angles: dict[str, FloatArray]
    travel: FloatArray
    lean: FloatArray


def _num(v: Any) -> float:
    return float(v) if isinstance(v, int | float) else math.nan


def load_track(db: Session, ref: ReferenceVideo) -> StoredTrack:
    rows = db.scalars(
        select(ReferencePoseFrame)
        .where(ReferencePoseFrame.reference_video_id == ref.id)
        .order_by(ReferencePoseFrame.frame_number)
    ).all()
    n = len(rows)
    times = np.array([r.timestamp for r in rows], dtype=np.float64)
    valid = np.array([r.valid for r in rows], dtype=bool)
    energy = np.full(n, np.nan)
    norm = np.full((n, L.NUM_LANDMARKS, 2), np.nan)
    angles = {name: np.full(n, np.nan) for name in L.ANGLES}
    travel = np.full((n, 2), np.nan)
    lean = np.full(n, np.nan)
    for i, r in enumerate(rows):
        p = r.payload or {}
        energy[i] = _num(p.get("motion_energy"))
        lean[i] = _num(p.get("torso_lean"))
        tr = p.get("travel") or [None, None]
        travel[i] = [_num(tr[0]), _num(tr[1])]
        for j, pt in enumerate(p.get("normalized") or []):
            if pt is not None and j < L.NUM_LANDMARKS:
                norm[i, j] = [_num(pt[0]), _num(pt[1])]
        for name, val in (p.get("angles") or {}).items():
            if name in angles:
                angles[name][i] = _num(val)
    return StoredTrack(times, valid, energy, norm, angles, travel, lean)


def _duration(ref: ReferenceVideo) -> float:
    return float(ref.canonical_duration or ref.duration)


def _section_input(track: StoredTrack, start: float, end: float, last: bool) -> SectionInput:
    sel = (track.times >= start) & ((track.times <= end) if last else (track.times < end))
    ev = track.energy[track.valid & ~np.isnan(track.energy)]
    return SectionInput(
        norm=track.norm[sel],
        angles={k: v[sel] for k, v in track.angles.items()},
        travel=track.travel[sel],
        lean=track.lean[sel],
        energy=track.energy[sel],
        valid=track.valid[sel],
        clip_energy=float(np.median(ev)) if ev.size else math.nan,
    )


def _thumbnail(
    storage: ObjectStorage, settings: Settings, ref: ReferenceVideo, key: str, at: float
) -> str | None:
    if not ref.canonical_object_key:
        return None
    src = storage.local_path(ref.canonical_object_key)
    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=settings.tmp_dir, prefix="thumb-") as tmp:
        dest = Path(tmp) / "t.jpg"
        try:
            make_poster(src, dest, at_seconds=at, timeout_s=30)
        except TranscodeFailed:
            log.warning("section_thumbnail_failed", extra={"at": at})
            return None
        storage.put_file(key, dest)
    return key


@dataclass(frozen=True)
class SectionSpec:
    start: float
    end: float
    id: str | None = None
    title: str | None = None
    completed: bool | None = None


def _require_analysed(project: DanceProject) -> ReferenceVideo:
    ref = project.reference_video
    if ref is None or ref.analyzed_at is None or project.status != "analyzed":
        raise SectionsUnavailable()
    return ref


def _write(
    db: Session,
    storage: ObjectStorage,
    settings: Settings,
    project: DanceProject,
    ref: ReferenceVideo,
    specs: list[SectionSpec],
    source: str,
) -> list[DanceSegment]:
    """Replace the project's sections with `specs` (already validated, ordered, full coverage).

    Sections whose id and boundaries are unchanged keep their thumbnail, instruction and
    completion; everything else gets a fresh midpoint thumbnail and instruction.
    """
    track = load_track(db, ref)
    existing = {s.id: s for s in project.segments}
    prefix = project_prefix(project.owner_id, project.id)
    keep_keys: set[str] = set()
    new_rows: list[DanceSegment] = []
    last = len(specs) - 1
    for pos, spec in enumerate(specs):
        old = existing.get(spec.id) if spec.id else None
        same = (
            old is not None
            and abs(old.start_time - spec.start) < 1e-3
            and abs(old.end_time - spec.end) < 1e-3
        )
        seg_id = old.id if old is not None else new_id()
        auto_title = f"Section {pos + 1:02d}"
        title = spec.title.strip() if spec.title and spec.title.strip() else None
        if title is None and old is not None and not _AUTO_TITLE.match(old.title):
            title = old.title
        row = DanceSegment(
            id=seg_id,
            project_id=project.id,
            position=pos,
            start_time=round(spec.start, 3),
            end_time=round(spec.end, 3),
            title=(title or auto_title)[:200],
            boundary_source=(old.boundary_source if same and old is not None else source),
        )
        if same and old is not None:
            row.instruction = old.instruction
            row.facts = old.facts
            row.coverage = old.coverage
            row.algorithm_version = old.algorithm_version
            row.thumbnail_key = old.thumbnail_key
            row.completed = old.completed if spec.completed is None else spec.completed
            if old.thumbnail_key:
                keep_keys.add(old.thumbnail_key)
        else:
            desc = describe_section(_section_input(track, spec.start, spec.end, pos == last))
            row.instruction = desc.instruction_mirror
            row.facts = desc.as_dict()
            row.coverage = round(desc.coverage, 4)
            row.algorithm_version = ALGORITHM_VERSION
            row.completed = bool(spec.completed) if spec.completed is not None else False
            key = f"{prefix}/sections/{seg_id}-{int(spec.start * 1000)}-{int(spec.end * 1000)}.jpg"
            row.thumbnail_key = _thumbnail(storage, settings, ref, key, (spec.start + spec.end) / 2)
            if row.thumbnail_key:
                keep_keys.add(row.thumbnail_key)
        new_rows.append(row)

    stale = [s.thumbnail_key for s in existing.values() if s.thumbnail_key]
    for s in list(project.segments):
        db.delete(s)
    db.flush()
    project.segments.clear()
    db.add_all(new_rows)
    db.commit()
    for key in stale:
        if key not in keep_keys:
            storage.delete(key)
    db.refresh(project)
    return list(project.segments)


def generate_automatic(
    db: Session,
    storage: ObjectStorage,
    settings: Settings,
    project: DanceProject,
    *,
    require_analysed: bool = True,
) -> list[DanceSegment]:
    ref = _require_analysed(project) if require_analysed else project.reference_video
    if ref is None:
        raise SectionsUnavailable()
    track = load_track(db, ref)
    major = list(L.MAJOR)
    bounds = suggest_boundaries(
        track.times, track.energy, track.norm[:, major, :], _duration(ref), SegmentationConfig()
    )
    # Regeneration starts over: specs carry no ids, so every section is new and not completed.
    specs = [SectionSpec(start=s, end=e) for s, e in bounds]
    return _write(db, storage, settings, project, ref, specs, "automatic")


def apply_edit(
    db: Session,
    storage: ObjectStorage,
    settings: Settings,
    project: DanceProject,
    specs: list[SectionSpec],
) -> list[DanceSegment]:
    """Validate (server-side) and persist an edited section list. Raises InvalidSections."""
    ref = _require_analysed(project)
    known = {s.id for s in project.segments}
    ids = [s.id for s in specs if s.id]
    if len(ids) != len(set(ids)) or any(i not in known for i in ids):
        raise InvalidSections("unknown_section", "One of those sections no longer exists.")
    snapped = validate_sections([(s.start, s.end) for s in specs], _duration(ref))
    fixed = [
        SectionSpec(start=a, end=b, id=s.id, title=s.title, completed=s.completed)
        for (a, b), s in zip(snapped, specs, strict=True)
    ]
    return _write(db, storage, settings, project, ref, fixed, "manual")

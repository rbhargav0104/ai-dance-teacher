"""Reference intake: validated temp file → private object + project/reference/job rows.

No-residue invariant (spec section 27): if anything fails, no project row, no permanent
object and no job survive. Objects are written first under a fresh project prefix, then the
rows are committed in one transaction; any failure rolls back and deletes the prefix.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import new_id
from app.errors import ApiError
from app.media.probe import ProbeResult
from app.models import AnalysisJob, DanceProject, ReferenceVideo, User
from app.storage.base import ObjectStorage

log = logging.getLogger("app.intake")

IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9_:.-]{8,128}$")
INTAKE_JOB_KIND = "reference_intake"


def project_prefix(owner_id: str, project_id: str) -> str:
    return f"users/{owner_id}/projects/{project_id}"


def clean_filename(name: str | None) -> str:
    """Display-only filename: strip paths, control chars and odd whitespace; cap length."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = unicodedata.normalize("NFC", base)
    base = "".join(c for c in base if unicodedata.category(c)[0] != "C")
    base = re.sub(r"\s+", " ", base).strip()
    return base[:200] or "video"


def title_from(explicit: str | None, filename: str) -> str:
    title = re.sub(r"\s+", " ", (explicit or "").strip())
    if not title:
        stem = Path(filename).stem
        title = re.sub(r"[_\-.]+", " ", stem).strip() or "Untitled dance"
    return title[:120]


def validate_idempotency_key(key: str | None) -> str | None:
    if key is None or key == "":
        return None
    if not IDEMPOTENCY_RE.fullmatch(key):
        raise ApiError(400, "invalid_idempotency_key", "The Idempotency-Key header is invalid.")
    return key


def find_by_idempotency(db: Session, owner_id: str, key: str | None) -> DanceProject | None:
    if key is None:
        return None
    return db.scalars(
        select(DanceProject).where(
            DanceProject.owner_id == owner_id, DanceProject.idempotency_key == key
        )
    ).first()


def enforce_project_quota(db: Session, owner_id: str, limit: int) -> None:
    count = db.scalar(
        select(func.count()).select_from(DanceProject).where(DanceProject.owner_id == owner_id)
    )
    if (count or 0) >= limit:
        raise ApiError(
            409,
            "project_limit",
            f"You have {limit} dances already. Delete one to add another.",
        )


@dataclass
class IntakeRequest:
    owner: User
    source_path: Path
    extension: str
    filename: str
    title: str
    probe: ProbeResult
    size_bytes: int
    idempotency_key: str | None
    is_demo: bool = False


def _warnings(probe: ProbeResult) -> list[str]:
    warnings: list[str] = []
    if probe.display_height > probe.display_width:
        warnings.append("portrait")
    if probe.fps < 15:
        warnings.append("low_frame_rate")
    if min(probe.width, probe.height) < 360:
        warnings.append("low_resolution")
    if probe.video_codec not in {"h264", "vp8", "vp9", "av1"}:
        warnings.append("may_need_conversion_for_playback")
    return warnings


def persist_reference(db: Session, storage: ObjectStorage, req: IntakeRequest) -> DanceProject:
    """Store the source object and commit rows atomically; returns the (maybe existing) project."""
    project_id = new_id()
    prefix = project_prefix(req.owner.id, project_id)
    source_key = f"{prefix}/source{req.extension}"
    try:
        stored = storage.put_file(source_key, req.source_path)
        project = DanceProject(
            id=project_id,
            owner_id=req.owner.id,
            title=req.title,
            status="uploaded",
            progress=0.0,
            is_demo=req.is_demo,
            idempotency_key=req.idempotency_key,
        )
        reference = ReferenceVideo(
            project_id=project_id,
            source_object_key=source_key,
            original_filename=req.filename,
            duration=req.probe.duration,
            source_fps=req.probe.fps,
            width=req.probe.display_width,
            height=req.probe.display_height,
            warnings=_warnings(req.probe),
            source_size_bytes=stored,
            source_codec=req.probe.video_codec[:32],
            source_container=req.probe.format_name[:64],
            has_audio=req.probe.has_audio,
            rotation=req.probe.rotation,
        )
        job = AnalysisJob(
            owner_id=req.owner.id,
            project_id=project_id,
            kind=INTAKE_JOB_KIND,
            idempotency_key=f"intake:{project_id}",
            status="succeeded",
            stage="inspecting",
            progress=1.0,
            message="Video checked and stored privately.",
            attempts=1,
        )
        db.add(project)
        db.flush()  # parent row first: jobs have no ORM relationship to order inserts
        db.add_all([reference, job])
        db.commit()
        return project
    except IntegrityError:
        db.rollback()
        storage.delete_prefix(prefix)
        existing = find_by_idempotency(db, req.owner.id, req.idempotency_key)
        if existing is not None:  # lost a race with a concurrent retry of the same upload
            return existing
        raise
    except BaseException:
        db.rollback()
        try:
            storage.delete_prefix(prefix)
        except Exception:  # pragma: no cover - logged, original error re-raised
            log.exception("intake_cleanup_failed")
        raise


def delete_project(db: Session, storage: ObjectStorage, project: DanceProject) -> None:
    prefix = project_prefix(project.owner_id, project.id)
    db.delete(project)
    db.commit()
    storage.delete_prefix(prefix)


# --- Bundled samples (committed, licensed fixtures; see fixtures/fixture_manifest.json) -----


@dataclass(frozen=True)
class Sample:
    id: str
    title: str
    path: Path
    license: str
    attribution: str
    framing: str


def load_samples(fixtures_dir: Path) -> list[Sample]:
    manifest = fixtures_dir / "fixture_manifest.json"
    try:
        data = json.loads(manifest.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    samples: list[Sample] = []
    for ref in data.get("references", []):
        path = (fixtures_dir / str(ref.get("file", ""))).resolve()
        if not path.is_relative_to(fixtures_dir.resolve()) or not path.is_file():
            continue
        samples.append(
            Sample(
                id=str(ref["id"]),
                title=str(ref.get("title") or ref["id"]),
                path=path,
                license=str(ref.get("license", "")),
                attribution=str(ref.get("original_source", "")),
                framing=str(ref.get("framing", "")),
            )
        )
    return samples

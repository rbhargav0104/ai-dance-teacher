"""Teachable sections API (spec 14, 23): list, edit (validated server-side), regenerate."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.projects import owned_project
from app.auth.deps import CurrentUser
from app.config import Settings, get_settings
from app.db.session import get_db
from app.errors import ApiError
from app.media.probe import ffprobe_available
from app.media.signing import MEDIA_TOKEN_TTL_SECONDS, MediaGrant, sign_media
from app.models import DanceProject, DanceSegment
from app.pose.section_rules import InvalidSections, SegmentationConfig
from app.storage import get_storage

if TYPE_CHECKING:
    from types import ModuleType

router = APIRouter(tags=["sections"])


class SectionOut(BaseModel):
    id: str
    position: int
    start: float
    end: float
    title: str
    instruction: str | None
    instruction_direct: str | None
    instruction_experimental: bool = True
    facts: list[dict[str, Any]]
    untracked: list[str]
    coverage: float | None
    boundary_source: str
    completed: bool
    thumbnail_url: str | None
    algorithm_version: str | None


class SectionsOut(BaseModel):
    project_id: str
    duration: float
    min_section_seconds: float
    max_sections: int
    thumbnail_expires_in: int
    sections: list[SectionOut]


class SectionIn(BaseModel):
    id: str | None = Field(default=None, max_length=64)
    start: float
    end: float
    title: str | None = Field(default=None, max_length=200)
    completed: bool | None = None


class SectionsPatch(BaseModel):
    sections: list[SectionIn] = Field(min_length=1, max_length=200)


class SectionPatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    completed: bool | None = None


def _section_out(seg: DanceSegment, user_id: str, settings: Settings) -> SectionOut:
    facts = seg.facts or {}
    url = None
    if seg.thumbnail_key:
        url = "/api/media/" + sign_media(
            settings, MediaGrant(seg.thumbnail_key, user_id, "image/jpeg")
        )
    return SectionOut(
        id=seg.id,
        position=seg.position,
        start=seg.start_time,
        end=seg.end_time,
        title=seg.title,
        instruction=seg.instruction,
        instruction_direct=facts.get("instruction_direct"),
        facts=list(facts.get("facts") or []),
        untracked=list(facts.get("untracked") or []),
        coverage=seg.coverage,
        boundary_source=seg.boundary_source,
        completed=seg.completed,
        thumbnail_url=url,
        algorithm_version=seg.algorithm_version,
    )


def _sections_out(project: DanceProject, user_id: str, settings: Settings) -> SectionsOut:
    ref = project.reference_video
    cfg = SegmentationConfig()
    duration = 0.0
    if ref is not None:
        duration = float(ref.canonical_duration or ref.duration)
    return SectionsOut(
        project_id=project.id,
        duration=duration,
        min_section_seconds=cfg.min_edit_len,
        max_sections=cfg.max_sections,
        thumbnail_expires_in=MEDIA_TOKEN_TTL_SECONDS,
        sections=[_section_out(s, user_id, settings) for s in project.segments],
    )


def _service() -> ModuleType:
    """Section maths needs numpy (vision extra). Without it the server is LIMITED: sections can
    be listed and renamed, but not recomputed."""
    try:
        from app.services import sections
    except ImportError as exc:
        raise ApiError(
            503,
            "analysis_unavailable",
            "Movement analysis isn't installed on this server, so sections can't be recomputed.",
        ) from exc
    return sections


def _not_ready() -> ApiError:
    return ApiError(409, "not_analyzed", "Sections appear once this dance has been analysed.")


@router.get("/api/projects/{project_id}/segments", response_model=SectionsOut)
def list_sections(
    project_id: str,
    user: CurrentUser,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SectionsOut:
    project = owned_project(db, user.id, project_id)
    if project.status != "analyzed":
        raise _not_ready()
    response.headers["Cache-Control"] = "private, no-store"
    return _sections_out(project, user.id, settings)


@router.patch("/api/projects/{project_id}/segments", response_model=SectionsOut)
def edit_sections(
    project_id: str,
    body: SectionsPatch,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SectionsOut:
    """Replace the section list. Must tile [0, duration] with no gap or overlap; changed
    sections get new thumbnails and instructions and are marked `manual`."""
    project = owned_project(db, user.id, project_id)
    svc = _service()
    specs = [
        svc.SectionSpec(start=s.start, end=s.end, id=s.id, title=s.title, completed=s.completed)
        for s in body.sections
    ]
    try:
        svc.apply_edit(db, get_storage(), settings, project, specs)
    except svc.SectionsUnavailable as exc:
        raise _not_ready() from exc
    except InvalidSections as exc:
        raise ApiError(422, exc.code, exc.message) from exc
    return _sections_out(project, user.id, settings)


@router.patch("/api/projects/{project_id}/segments/{section_id}", response_model=SectionOut)
def edit_one_section(
    project_id: str,
    section_id: str,
    body: SectionPatch,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SectionOut:
    """Rename a section or mark it complete (boundaries unchanged)."""
    project = owned_project(db, user.id, project_id)
    if project.status != "analyzed":
        raise _not_ready()
    seg = None
    for s in project.segments:
        if s.id == section_id:
            seg = s
    if seg is not None:
        if body.title is not None:
            seg.title = body.title.strip()[:200] or f"Section {seg.position + 1:02d}"
        if body.completed is not None:
            seg.completed = body.completed
        db.commit()
        db.refresh(seg)
    if seg is None:
        raise ApiError(404, "section_not_found", "That section no longer exists.")
    return _section_out(seg, user.id, settings)


@router.post("/api/projects/{project_id}/segments/regenerate", response_model=SectionsOut)
def regenerate_sections(
    project_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SectionsOut:
    """Discard edits and suggest sections again from the stored measurements."""
    project = owned_project(db, user.id, project_id)
    if not ffprobe_available():
        raise ApiError(
            503, "media_tools_unavailable", "Video tools aren't available on this server."
        )
    svc = _service()
    try:
        svc.generate_automatic(db, get_storage(), settings, project)
    except svc.SectionsUnavailable as exc:
        raise _not_ready() from exc
    return _sections_out(project, user.id, settings)

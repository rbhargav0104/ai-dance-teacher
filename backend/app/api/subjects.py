"""Choose whom to follow in a multi-person video (spec amendment A2).

`POST /api/projects/{id}/subject` and `POST /api/practice-sessions/{id}/subject` store the
choice and re-run the real analysis following only that person. Idempotent: choosing the person
already followed returns the current job. In LIMITED mode the choice is stored and the request
answers 503 (analysis is refused honestly, never simulated).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.health import analysis_capability
from app.api.projects import JobOut, _latest_job, job_out, owned_project
from app.auth.deps import CurrentUser
from app.config import Settings, get_settings
from app.db.session import get_db
from app.errors import ApiError
from app.jobs.queue import (
    active_job,
    active_practice_job,
    enqueue_practice_analysis,
    enqueue_reference_analysis,
    latest_practice_job,
)
from app.services.practice import owned_practice
from app.services.subjects import SubjectChoiceIn, same_choice, with_choice

router = APIRouter(tags=["subjects"])

_SAVED_BUT_LIMITED = (
    "Your choice is saved, but movement analysis isn't available on this server right now."
)


@router.post("/api/projects/{project_id}/subject", response_model=JobOut, status_code=202)
def choose_reference_subject(
    project_id: str,
    body: SubjectChoiceIn,
    user: CurrentUser,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> JobOut:
    project = owned_project(db, user.id, project_id)
    ref = project.reference_video
    record = ref.subject if ref is not None else None
    running = active_job(db, project.id)
    if same_choice(record, body.person):
        if running is not None:
            response.status_code = 200
            return job_out(running)
        latest = _latest_job(db, project.id)
        if project.status == "analyzed" and latest is not None:
            response.status_code = 200
            return job_out(latest)
    updated = with_choice(record, body.person)
    if running is not None:
        raise ApiError(
            409, "analysis_in_progress", "Analysis is still running. Choose again when it's done."
        )
    assert ref is not None
    ref.subject = updated
    db.commit()
    cap = analysis_capability(settings)
    if not cap.available:
        raise ApiError(503, "analysis_unavailable", _SAVED_BUT_LIMITED)
    job, _ = enqueue_reference_analysis(db, project)
    return job_out(job)


@router.post("/api/practice-sessions/{session_id}/subject", response_model=JobOut, status_code=202)
def choose_practice_subject(
    session_id: str,
    body: SubjectChoiceIn,
    user: CurrentUser,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> JobOut:
    practice = owned_practice(db, user.id, session_id)
    record = practice.subject
    running = active_practice_job(db, practice.id)
    if same_choice(record, body.person):
        if running is not None:
            response.status_code = 200
            return job_out(running)
        latest = latest_practice_job(db, practice.id)
        if practice.status == "analyzed" and latest is not None:
            response.status_code = 200
            return job_out(latest)
    updated = with_choice(record, body.person)
    if running is not None:
        raise ApiError(
            409, "analysis_in_progress", "Analysis is still running. Choose again when it's done."
        )
    practice.subject = updated
    db.commit()
    cap = analysis_capability(settings)
    if not cap.available:
        raise ApiError(503, "analysis_unavailable", _SAVED_BUT_LIMITED)
    job, _ = enqueue_practice_analysis(db, practice)
    return job_out(job)

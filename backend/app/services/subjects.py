"""Stored "who is in this video" records and the user's choice of whom to follow (A2).

The record itself is written by the analysis pipeline (`pipeline.common.subject_record`) from
real detections; this module only reads it and stores a choice that names one of its candidates.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.db.base import utcnow
from app.errors import ApiError


class CandidateOut(BaseModel):
    person: int
    box: list[float]  # [x0, y0, x1, y1], fraction of the frame
    root: list[float]
    position: str
    share: float  # fraction of the analysed video in which this person could be followed


class ChoiceOut(BaseModel):
    person: int
    position: str
    t: float
    box: list[float]
    chosen_at: str | None = None


class FollowedOut(BaseModel):
    fraction: float
    lost_spans: list[list[float]]
    uncertain_spans: list[list[float]]


class SubjectOut(BaseModel):
    version: str
    frame_time: float
    has_frame: bool
    candidates: list[CandidateOut]
    choice: ChoiceOut | None
    followed: FollowedOut | None


class SubjectChoiceIn(BaseModel):
    person: int


def subject_out(record: dict[str, Any] | None) -> SubjectOut | None:
    if not record or not record.get("candidates"):
        return None
    return SubjectOut(
        version=str(record.get("version", "")),
        frame_time=float(record.get("frame_time", 0.0)),
        has_frame=bool(record.get("frame_key")),
        candidates=[CandidateOut(**c) for c in record["candidates"]],
        choice=_choice_out(record.get("choice")),
        followed=FollowedOut(**record["followed"]) if record.get("followed") else None,
    )


def _choice_out(choice: dict[str, Any] | None) -> ChoiceOut | None:
    if not choice:
        return None
    return ChoiceOut(**{k: v for k, v in choice.items() if k != "root"})


def same_choice(record: dict[str, Any] | None, person: int) -> bool:
    choice = (record or {}).get("choice")
    return isinstance(choice, dict) and int(choice["person"]) == person


def with_choice(record: dict[str, Any] | None, person: int) -> dict[str, Any]:
    """A new record with `person` chosen. 409 when there is nobody to choose between, 422 for a
    person that isn't one of the candidates."""
    if not record or len(record.get("candidates") or []) < 2:
        raise ApiError(
            409,
            "no_people_to_choose",
            "We only found one person in this video, so there's nobody else to follow.",
        )
    match = next((c for c in record["candidates"] if int(c["person"]) == person), None)
    if match is None:
        raise ApiError(422, "unknown_person", "That person isn't one of the people we found.")
    updated = dict(record)
    updated["choice"] = {
        "person": person,
        "position": match["position"],
        "t": record["frame_time"],
        "root": match["root"],
        "box": match["box"],
        "chosen_at": utcnow().isoformat(),
    }
    # The previous follow summary belongs to the previous choice.
    updated["followed"] = None
    return updated

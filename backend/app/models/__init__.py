"""ORM models for spec section 10. Video bytes never live here — only object keys."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JsonType, new_id, utcnow


def _id() -> Mapped[str]:
    return mapped_column(String(32), primary_key=True, default=new_id)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = _id()
    auth_provider: Mapped[str] = mapped_column(String(32))
    auth_provider_id: Mapped[str] = mapped_column(String(128))
    preferences: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    projects: Mapped[list[DanceProject]] = relationship(
        back_populates="owner", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (UniqueConstraint("auth_provider", "auth_provider_id", name="provider_id"),)


class DanceProject(Base):
    __tablename__ = "dance_projects"

    id: Mapped[str] = _id()
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="uploaded")
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    owner: Mapped[User] = relationship(back_populates="projects")
    reference_video: Mapped[ReferenceVideo | None] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    segments: Mapped[list[DanceSegment]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DanceSegment.position",
    )

    __table_args__ = (UniqueConstraint("owner_id", "idempotency_key", name="owner_idempotency"),)


class ReferenceVideo(Base):
    __tablename__ = "reference_videos"

    id: Mapped[str] = _id()
    project_id: Mapped[str] = mapped_column(
        ForeignKey("dance_projects.id", ondelete="CASCADE"), unique=True
    )
    source_object_key: Mapped[str] = mapped_column(String(512))
    canonical_object_key: Mapped[str | None] = mapped_column(String(512))
    thumbnail_key: Mapped[str | None] = mapped_column(String(512))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    source_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    source_codec: Mapped[str | None] = mapped_column(String(32))
    source_container: Mapped[str | None] = mapped_column(String(64))
    has_audio: Mapped[bool | None] = mapped_column(Boolean)
    rotation: Mapped[int | None] = mapped_column(Integer)
    duration: Mapped[float] = mapped_column(Float)
    source_fps: Mapped[float] = mapped_column(Float)
    analysis_fps: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    pose_coverage: Mapped[float | None] = mapped_column(Float)
    canonical_width: Mapped[int | None] = mapped_column(Integer)
    canonical_height: Mapped[int | None] = mapped_column(Integer)
    canonical_fps: Mapped[float | None] = mapped_column(Float)
    canonical_duration: Mapped[float | None] = mapped_column(Float)
    quality: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    analyzed_at: Mapped[datetime | None] = mapped_column()
    warnings: Mapped[list[str]] = mapped_column(JsonType, default=list)
    pipeline_version: Mapped[str | None] = mapped_column(String(64))
    model_version: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    project: Mapped[DanceProject] = relationship(back_populates="reference_video")


class DanceSegment(Base):
    __tablename__ = "dance_segments"

    id: Mapped[str] = _id()
    project_id: Mapped[str] = mapped_column(
        ForeignKey("dance_projects.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float] = mapped_column(Float)
    title: Mapped[str] = mapped_column(String(200))
    instruction: Mapped[str | None] = mapped_column(Text)
    thumbnail_key: Mapped[str | None] = mapped_column(String(512))
    boundary_source: Mapped[str] = mapped_column(String(16), default="automatic")
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    project: Mapped[DanceProject] = relationship(back_populates="segments")

    __table_args__ = (UniqueConstraint("project_id", "position", name="project_position"),)


class ReferencePoseFrame(Base):
    __tablename__ = "reference_pose_frames"

    id: Mapped[str] = _id()
    reference_video_id: Mapped[str] = mapped_column(
        ForeignKey("reference_videos.id", ondelete="CASCADE")
    )
    timestamp: Mapped[float] = mapped_column(Float)
    frame_number: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType)
    valid: Mapped[bool] = mapped_column(Boolean)
    confidence: Mapped[float] = mapped_column(Float)
    pipeline_version: Mapped[str] = mapped_column(String(64))

    __table_args__ = (
        Index("ix_reference_pose_frames_video_ts", "reference_video_id", "timestamp"),
        Index("ix_reference_pose_frames_video_frame", "reference_video_id", "frame_number"),
    )


class PracticeSession(Base):
    __tablename__ = "practice_sessions"

    id: Mapped[str] = _id()
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("dance_projects.id", ondelete="CASCADE"), index=True
    )
    segment_id: Mapped[str | None] = mapped_column(
        ForeignKey("dance_segments.id", ondelete="SET NULL")
    )
    source_object_key: Mapped[str | None] = mapped_column(String(512))
    canonical_object_key: Mapped[str | None] = mapped_column(String(512))
    thumbnail_key: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="created")
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    duration: Mapped[float | None] = mapped_column(Float)
    source_fps: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    tracking_coverage: Mapped[float | None] = mapped_column(Float)
    declared_mirrored: Mapped[bool | None] = mapped_column(Boolean)
    detected_mirror_choice: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class UserPoseFrame(Base):
    __tablename__ = "user_pose_frames"

    id: Mapped[str] = _id()
    practice_session_id: Mapped[str] = mapped_column(
        ForeignKey("practice_sessions.id", ondelete="CASCADE")
    )
    timestamp: Mapped[float] = mapped_column(Float)
    frame_number: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType)
    valid: Mapped[bool] = mapped_column(Boolean)
    confidence: Mapped[float] = mapped_column(Float)
    pipeline_version: Mapped[str] = mapped_column(String(64))

    __table_args__ = (Index("ix_user_pose_frames_session_ts", "practice_session_id", "timestamp"),)


class PerformanceScore(Base):
    __tablename__ = "performance_scores"

    id: Mapped[str] = _id()
    practice_session_id: Mapped[str] = mapped_column(
        ForeignKey("practice_sessions.id", ondelete="CASCADE"), index=True
    )
    scoring_version: Mapped[str] = mapped_column(String(32))
    overall: Mapped[float | None] = mapped_column(Float)
    components: Mapped[dict[str, Any]] = mapped_column(JsonType)
    weights: Mapped[dict[str, Any]] = mapped_column(JsonType)
    coverage: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    report: Mapped[dict[str, Any]] = mapped_column(JsonType)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class FeedbackItem(Base):
    __tablename__ = "feedback_items"

    id: Mapped[str] = _id()
    practice_session_id: Mapped[str] = mapped_column(
        ForeignKey("practice_sessions.id", ondelete="CASCADE"), index=True
    )
    segment_id: Mapped[str | None] = mapped_column(
        ForeignKey("dance_segments.id", ondelete="SET NULL")
    )
    reference_time: Mapped[float] = mapped_column(Float)
    practice_time: Mapped[float] = mapped_column(Float)
    category: Mapped[str] = mapped_column(String(32))
    body_part: Mapped[str | None] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))
    measured_delta: Mapped[float | None] = mapped_column(Float)
    message: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[str] = _id()
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("dance_projects.id", ondelete="CASCADE"), index=True
    )
    practice_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("practice_sessions.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(32))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    stage: Mapped[str | None] = mapped_column(String(32))
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_at: Mapped[datetime | None] = mapped_column()
    worker_id: Mapped[str | None] = mapped_column(String(64))
    heartbeat_at: Mapped[datetime | None] = mapped_column()
    retryable: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


__all__ = [
    "AnalysisJob",
    "DanceProject",
    "DanceSegment",
    "FeedbackItem",
    "PerformanceScore",
    "PracticeSession",
    "ReferencePoseFrame",
    "ReferenceVideo",
    "User",
    "UserPoseFrame",
]

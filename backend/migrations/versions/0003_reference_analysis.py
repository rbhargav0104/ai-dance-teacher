"""reference analysis: canonical copy metadata, quality report, job retry/timing

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-25 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_json = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("reference_videos", schema=None) as batch_op:
        batch_op.add_column(sa.Column("canonical_width", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("canonical_height", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("canonical_fps", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("canonical_duration", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("quality", _json, nullable=True))
        batch_op.add_column(sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("analysis_jobs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_reference_pose_frames_video_frame",
        "reference_pose_frames",
        ["reference_video_id", "frame_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_reference_pose_frames_video_frame", table_name="reference_pose_frames")
    with op.batch_alter_table("analysis_jobs", schema=None) as batch_op:
        for col in ("finished_at", "started_at", "retryable"):
            batch_op.drop_column(col)
    with op.batch_alter_table("reference_videos", schema=None) as batch_op:
        for col in (
            "analyzed_at",
            "quality",
            "canonical_duration",
            "canonical_fps",
            "canonical_height",
            "canonical_width",
        ):
            batch_op.drop_column(col)

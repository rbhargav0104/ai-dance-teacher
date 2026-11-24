"""reference intake metadata: source size, codec, audio, rotation

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-25 02:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("reference_videos", schema=None) as batch_op:
        batch_op.add_column(sa.Column("source_size_bytes", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("source_codec", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("source_container", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("has_audio", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("rotation", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("reference_videos", schema=None) as batch_op:
        for col in (
            "rotation",
            "has_audio",
            "source_container",
            "source_codec",
            "source_size_bytes",
        ):
            batch_op.drop_column(col)

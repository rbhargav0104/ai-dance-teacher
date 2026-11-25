"""teachable sections: per-section coverage, measured facts and algorithm version

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-26 02:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_json = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("dance_segments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("coverage", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("facts", _json, nullable=True))
        batch_op.add_column(sa.Column("algorithm_version", sa.String(32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("dance_segments", schema=None) as batch_op:
        batch_op.drop_column("algorithm_version")
        batch_op.drop_column("facts")
        batch_op.drop_column("coverage")

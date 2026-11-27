"""subject choice: who is in a multi-person video and whom to follow (spec amendment A2)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-28 03:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_json = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    for table in ("reference_videos", "practice_sessions"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column("subject", _json, nullable=True))


def downgrade() -> None:
    for table in ("practice_sessions", "reference_videos"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column("subject")

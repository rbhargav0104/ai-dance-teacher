"""practice alignment: cached mirror-aware bounded-DTW alignment per attempt

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-27 14:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_json = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("practice_sessions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("alignment", _json, nullable=True))
        batch_op.add_column(sa.Column("alignment_key", sa.String(255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("practice_sessions", schema=None) as batch_op:
        batch_op.drop_column("alignment_key")
        batch_op.drop_column("alignment")

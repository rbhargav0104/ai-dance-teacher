"""practice sessions: intake + analysis metadata for learner attempts

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-27 02:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_json = sa.JSON().with_variant(JSONB(), "postgresql")

_COLUMNS: list[tuple[str, sa.types.TypeEngine[object] | type]] = [
    ("original_filename", sa.String(255)),
    ("source_size_bytes", sa.BigInteger()),
    ("source_codec", sa.String(32)),
    ("has_audio", sa.Boolean()),
    ("idempotency_key", sa.String(128)),
    ("canonical_width", sa.Integer()),
    ("canonical_height", sa.Integer()),
    ("canonical_fps", sa.Float()),
    ("canonical_duration", sa.Float()),
    ("analysis_fps", sa.Float()),
    ("quality", _json),
    ("pipeline_version", sa.String(64)),
    ("model_version", sa.String(128)),
    ("analyzed_at", sa.DateTime(timezone=True)),
]


def upgrade() -> None:
    with op.batch_alter_table("practice_sessions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("capture_source", sa.String(16), nullable=False, server_default="upload")
        )
        for name, type_ in _COLUMNS:
            batch_op.add_column(sa.Column(name, type_, nullable=True))
        batch_op.add_column(
            sa.Column("warnings", _json, nullable=False, server_default=sa.text("'[]'"))
        )
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_unique_constraint(
            "practice_owner_idempotency", ["owner_id", "idempotency_key"]
        )


def downgrade() -> None:
    with op.batch_alter_table("practice_sessions", schema=None) as batch_op:
        batch_op.drop_constraint("practice_owner_idempotency", type_="unique")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("warnings")
        for name, _ in reversed(_COLUMNS):
            batch_op.drop_column(name)
        batch_op.drop_column("capture_source")

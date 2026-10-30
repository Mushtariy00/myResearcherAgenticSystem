"""stage attempt cap, journal indexes

Revision ID: 7c3e9a51d2b4
Revises: 141dd2d056b7
Create Date: 2026-10-30 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c3e9a51d2b4"
down_revision: str | None = "141dd2d056b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("stage_runs", sa.Column("last_attempt", sa.Integer(), nullable=True))
    op.create_index("ix_llm_calls_run_id", "llm_calls", ["run_id"])
    op.create_index(
        "ix_llm_calls_idempotency_key_prefix",
        "llm_calls",
        ["idempotency_key"],
        postgresql_ops={"idempotency_key": "varchar_pattern_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_llm_calls_idempotency_key_prefix", table_name="llm_calls")
    op.drop_index("ix_llm_calls_run_id", table_name="llm_calls")
    op.drop_column("stage_runs", "last_attempt")

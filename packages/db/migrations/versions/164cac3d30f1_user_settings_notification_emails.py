"""user settings, notification emails

Revision ID: 164cac3d30f1
Revises: 0b2bff8fd54a
Create Date: 2026-10-30 18:12:58.684625
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "164cac3d30f1"
down_revision: str | None = "0b2bff8fd54a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_emails",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("notification_key", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "claimed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("user_id", "notification_key", name=op.f("pk_notification_emails")),
    )
    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column(
            "email_notifications", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("locale", sa.String(length=8), server_default="en", nullable=False),
        sa.Column(
            "emails_since",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_settings")),
    )


def downgrade() -> None:
    op.drop_table("user_settings")
    op.drop_table("notification_emails")

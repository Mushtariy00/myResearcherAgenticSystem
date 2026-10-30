"""The migration that adds user settings and the record of notification emails (164cac3d30f1)."""

import asyncio
from collections.abc import Callable

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_db.testing import ALEMBIC_INI

Factory = async_sessionmaker[AsyncSession]
REVISION = "164cac3d30f1"
BEFORE = "0b2bff8fd54a"
TABLES = {"user_settings", "notification_emails"}


async def _alembic(database_url: str, step: Callable[[Config, str], None], revision: str) -> None:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url)
    # env.py runs an event loop of its own, so Alembic gets a thread of its own.
    await asyncio.to_thread(step, config, revision)


async def _tables(db: Factory) -> set[str]:
    async with db() as session:
        rows = await session.scalars(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        return set(rows)


async def test_the_migration_adds_both_tables_and_takes_them_away(
    db: Factory, database_url: str
) -> None:
    try:
        await _alembic(database_url, command.downgrade, BEFORE)
        assert not TABLES & await _tables(db)

        await _alembic(database_url, command.upgrade, REVISION)
        assert TABLES.issubset(await _tables(db))
        async with db() as session:
            # What the mailer writes for a user it sees first, and for a send it claims.
            await session.execute(text("INSERT INTO user_settings (user_id) VALUES ('bob')"))
            await session.execute(
                text(
                    "INSERT INTO notification_emails (user_id, notification_key, kind, retry_at) "
                    "VALUES ('bob', 'approval:x', 'approval_needed', now())"
                )
            )
            settings = (
                await session.execute(
                    text(
                        "SELECT email_notifications, locale, emails_since IS NOT NULL, "
                        "updated_at IS NOT NULL FROM user_settings"
                    )
                )
            ).one()
            email = (
                await session.execute(
                    text(
                        "SELECT attempts, claimed_at IS NOT NULL, sent_at FROM notification_emails"
                    )
                )
            ).one()
            await session.commit()
        assert tuple(settings) == (True, "en", True, True)
        assert tuple(email) == (1, True, None)

        await _alembic(database_url, command.downgrade, BEFORE)
        assert not TABLES & await _tables(db)
    finally:
        await _alembic(database_url, command.upgrade, "head")

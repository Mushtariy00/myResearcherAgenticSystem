"""Alembic environment. Manages our tables only; Better Auth migrates its own `auth` schema."""

import asyncio
import os

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

from agentic_db.models import Base

target_metadata = Base.metadata


def _database_url() -> str:
    url = context.config.get_main_option("sqlalchemy.url") or os.environ.get("ARP_DATABASE_URL")
    if not url:
        raise RuntimeError("Set ARP_DATABASE_URL (see .env.example)")
    return url


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run_online() -> None:
    engine = create_async_engine(_database_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=_database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(_run_online())

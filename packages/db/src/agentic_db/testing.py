"""Pytest plugin: a migrated throwaway database (`<dev db>_test`) for tests that need Postgres.

Enabled from the repo-root conftest.py. Tests are skipped when no Postgres is configured.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from agentic_db.models import Base
from agentic_db.session import create_engine, session_factory

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@pytest.fixture(scope="session")
def database_url() -> str:
    base = os.environ.get("ARP_TEST_DATABASE_URL") or os.environ.get("ARP_DATABASE_URL")
    if not base:
        pytest.skip("Set ARP_DATABASE_URL (the dev Postgres) to run database tests")
    url = make_url(base)
    # ARP_TEST_DB_NAME lets parallel test sessions (several agents or CI jobs) use separate
    # databases; each session drops and recreates its own.
    test_url = url.set(database=os.environ.get("ARP_TEST_DB_NAME") or f"{url.database}_test")
    admin_dsn = url.set(drivername="postgresql").render_as_string(hide_password=False)
    name = sql.Identifier(str(test_url.database))
    try:
        with psycopg.connect(admin_dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(name))
            conn.execute(sql.SQL("CREATE DATABASE {}").format(name))
    except psycopg.OperationalError as exc:
        pytest.skip(f"Postgres is not reachable ({exc}); run `make up`")

    rendered = test_url.render_as_string(hide_password=False)
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", rendered)
    command.upgrade(config, "head")
    return rendered


@pytest.fixture
async def db_engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(database_url, pool_size=4)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db(db_engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A session factory on the test database; every table is emptied after the test."""
    yield session_factory(db_engine)
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    async with db_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))

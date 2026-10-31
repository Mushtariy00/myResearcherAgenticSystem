"""Pytest plugin: a migrated throwaway database for tests that need Postgres.

Enabled from the repo-root conftest.py. Tests are skipped when no Postgres is configured.
"""

import os
import secrets
from collections.abc import AsyncIterator, Iterator, Mapping
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


def session_database(dev_database: str, environ: Mapping[str, str]) -> tuple[str, bool]:
    """The database for one test session, and whether the session drops it when it ends.

    Each session gets a database of its own (``<dev db>_test_<random>``), dropped at the end,
    so sessions running side by side (several checkouts, agents or CI jobs on one Postgres)
    never drop or empty each other's. ARP_TEST_DB_NAME names a fixed one instead, recreated
    at the start and kept afterwards for a look.
    """
    fixed = environ.get("ARP_TEST_DB_NAME")
    if fixed:
        return fixed, False
    return f"{dev_database}_test_{secrets.token_hex(4)}", True


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    base = os.environ.get("ARP_TEST_DATABASE_URL") or os.environ.get("ARP_DATABASE_URL")
    if not base:
        pytest.skip("Set ARP_DATABASE_URL (the dev Postgres) to run database tests")
    url = make_url(base)
    database, throwaway = session_database(str(url.database), os.environ)
    test_url = url.set(database=database)
    admin_dsn = url.set(drivername="postgresql").render_as_string(hide_password=False)
    name = sql.Identifier(database)
    try:
        with psycopg.connect(admin_dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(name))
            conn.execute(sql.SQL("CREATE DATABASE {}").format(name))
    except psycopg.OperationalError as exc:
        pytest.skip(f"Postgres is not reachable ({exc}); run `make up`")

    rendered = test_url.render_as_string(hide_password=False)
    try:
        config = Config(str(ALEMBIC_INI))
        config.set_main_option("sqlalchemy.url", rendered)
        command.upgrade(config, "head")
        # Every test starts from empty tables, as `db` leaves them: the rows the migrations seed
        # (the nyu2 dataset) would otherwise reach only whichever test runs first.
        test_dsn = test_url.set(drivername="postgresql").render_as_string(hide_password=False)
        with psycopg.connect(test_dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("TRUNCATE {} RESTART IDENTITY CASCADE").format(_tables()))
        yield rendered
    finally:
        if throwaway:  # FORCE: it is this session's own database, nobody else's
            with psycopg.connect(admin_dsn, autocommit=True) as conn:
                conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(name))


@pytest.fixture
async def db_engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(database_url, pool_size=4)
    yield engine
    await engine.dispose()


def _tables() -> sql.Composed:
    return sql.SQL(", ").join(sql.Identifier(table.name) for table in Base.metadata.sorted_tables)


@pytest.fixture
async def db(db_engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A session factory on the test database; every table is emptied after the test."""
    yield session_factory(db_engine)
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    async with db_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))

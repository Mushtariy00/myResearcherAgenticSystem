from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_api.main import AppState, create_app
from agentic_api.settings import Settings
from api_testkit import ORIGIN, FakeOrchestrator, FakeValkey, FakeVerifier


@pytest.fixture
async def auth_users(db: async_sessionmaker[AsyncSession]) -> None:
    """A minimal stand-in for Better Auth's user table (the real one is created by the web app)."""
    async with db() as session:
        await session.execute(
            text(
                'CREATE TABLE IF NOT EXISTS auth."user" '
                "(id text PRIMARY KEY, email text, name text)"
            )
        )
        await session.execute(text('TRUNCATE auth."user"'))
        await session.execute(
            text(
                'INSERT INTO auth."user" (id, email, name) VALUES '
                "('alice', 'alice@lab.test', 'Alice'), ('bob', 'bob@lab.test', 'Bob'), "
                "('vera', 'vera@lab.test', 'Vera')"
            )
        )
        await session.commit()


@pytest.fixture
def orchestrator() -> FakeOrchestrator:
    return FakeOrchestrator()


@pytest.fixture
async def client(
    db: async_sessionmaker[AsyncSession], orchestrator: FakeOrchestrator, auth_users: None
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        Settings(environment="test", public_origin=ORIGIN),
        state=AppState(
            sessions=db,
            session_verifier=FakeVerifier(),
            valkey=FakeValkey(),
            orchestrator=orchestrator,
        ),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"origin": ORIGIN}
    ) as c:
        yield c

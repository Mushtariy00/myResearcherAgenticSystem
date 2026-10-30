from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_db.models import UserSettings
from api_testkit import as_user

Factory = async_sessionmaker[AsyncSession]
URL = "/api/v1/me/settings"
DEFAULTS = {"email_notifications": True, "locale": "en"}


async def _emails_since(db: Factory, user_id: str) -> datetime:
    async with db() as session:
        row = await session.get(UserSettings, user_id)
        assert row is not None
        return row.emails_since


async def test_settings_start_at_the_defaults(client: httpx.AsyncClient, db: Factory) -> None:
    response = await client.get(URL, headers=as_user("bob"))
    assert response.status_code == 200, response.text
    assert response.json() == DEFAULTS
    async with db() as session:
        assert await session.get(UserSettings, "bob") is None  # reading writes nothing

    assert (await client.get(URL)).status_code == 401
    assert (await client.put(URL, json={"locale": "ko"})).status_code == 401


async def test_each_setting_changes_on_its_own(client: httpx.AsyncClient) -> None:
    bob = as_user("bob")
    response = await client.put(URL, json={"email_notifications": False}, headers=bob)
    assert response.status_code == 200, response.text
    assert response.json() == {"email_notifications": False, "locale": "en"}
    # The language switches send the locale alone: the email choice stays.
    response = await client.put(URL, json={"locale": "ko"}, headers=bob)
    assert response.json() == {"email_notifications": False, "locale": "ko"}
    assert (await client.get(URL, headers=bob)).json() == {
        "email_notifications": False,
        "locale": "ko",
    }
    assert (await client.get(URL, headers=as_user("alice"))).json() == DEFAULTS  # bob's own


async def test_switching_emails_back_on_starts_them_afresh(
    client: httpx.AsyncClient, db: Factory
) -> None:
    bob = as_user("bob")
    await client.put(URL, json={"locale": "ko"}, headers=bob)
    # An hour back: the clock of a WSL machine may step back a little between two requests.
    long_ago = datetime.now(UTC) - timedelta(hours=1)
    async with db() as session:
        await session.execute(update(UserSettings).values(emails_since=long_ago))
        await session.commit()
    await client.put(URL, json={"email_notifications": True, "locale": "en"}, headers=bob)
    await client.put(URL, json={"email_notifications": False}, headers=bob)
    assert await _emails_since(db, "bob") == long_ago  # still on, then off: nothing to restart
    await client.put(URL, json={"email_notifications": True}, headers=bob)
    assert await _emails_since(db, "bob") > long_ago + timedelta(minutes=30)


async def test_settings_are_checked(client: httpx.AsyncClient) -> None:
    for invalid in (
        {},
        {"email_notifications": None, "locale": None},
        {"locale": "fr"},
        {"locale": "EN"},
        {"email_notifications": "maybe"},
        {"locale": "ko", "theme": "dark"},
    ):
        response = await client.put(URL, json=invalid, headers=as_user("bob"))
        assert response.status_code == 422, invalid
    assert (await client.get(URL, headers=as_user("bob"))).json() == DEFAULTS

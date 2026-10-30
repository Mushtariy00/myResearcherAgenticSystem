"""Better Auth's user table (ADR 0003). Read-only: look-ups by email and display names."""

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_USER_BY_EMAIL = text('SELECT id, email, name FROM auth."user" WHERE lower(email) = lower(:email)')
_USERS_BY_ID = text('SELECT id, email, name FROM auth."user" WHERE id = ANY(:ids)')


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str
    name: str


async def user_by_email(db: AsyncSession, email: str) -> AuthUser | None:
    row = (await db.execute(_USER_BY_EMAIL, {"email": email})).first()
    return AuthUser(id=row.id, email=row.email, name=row.name) if row else None


async def users_by_id(db: AsyncSession, ids: Iterable[str]) -> dict[str, AuthUser]:
    """The accounts that still exist among ``ids`` (offboarded users are simply missing)."""
    wanted = sorted(set(ids))
    if not wanted:
        return {}
    rows = (await db.execute(_USERS_BY_ID, {"ids": wanted})).all()
    return {row.id: AuthUser(id=row.id, email=row.email, name=row.name) for row in rows}

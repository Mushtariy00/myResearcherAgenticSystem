"""The caller's own settings: notification emails and the language they are written in."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import case, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_api.auth import CurrentUser, current_user
from agentic_api.authz import get_db
from agentic_api.schemas import MySettingsIn, MySettingsOut
from agentic_db.models import UserSettings

router = APIRouter(prefix="/api/v1/me", tags=["settings"])
User = Annotated[CurrentUser, Depends(current_user)]
Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("/settings", operation_id="getMySettings")
async def get_my_settings(user: User, db: Db) -> MySettingsOut:
    row = await db.get(UserSettings, user.id)
    if row is None:  # never written yet: the column defaults
        return MySettingsOut(email_notifications=True, locale="en")
    return MySettingsOut.model_validate(row, from_attributes=True)


@router.put("/settings", operation_id="updateMySettings")
async def update_my_settings(body: MySettingsIn, user: User, db: Db) -> MySettingsOut:
    """Change the fields sent; the others keep their values."""
    changes = body.model_dump(exclude_none=True)
    updates: dict[str, Any] = {**changes, "updated_at": func.now()}
    if body.email_notifications:
        # Switched back on: emails start afresh rather than catch up on what came meanwhile.
        updates["emails_since"] = case(
            (UserSettings.email_notifications.is_(False), func.now()),
            else_=UserSettings.emails_since,
        )
    row = (
        await db.execute(
            insert(UserSettings)
            .values(user_id=user.id, **changes)
            .on_conflict_do_update(index_elements=[UserSettings.user_id], set_=updates)
            .returning(UserSettings.email_notifications, UserSettings.locale)
        )
    ).one()
    await db.commit()
    return MySettingsOut.model_validate(row, from_attributes=True)

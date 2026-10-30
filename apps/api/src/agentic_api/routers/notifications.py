"""The caller's in-app notifications (derived on read; see agentic_api.notifications)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_api.auth import CurrentUser, current_user
from agentic_api.authz import get_db
from agentic_api.notifications import derive_notifications, mark_read, with_read_state
from agentic_api.schemas import NotificationList, NotificationsReadIn

router = APIRouter(prefix="/api/v1/me", tags=["notifications"])
User = Annotated[CurrentUser, Depends(current_user)]
Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("/notifications", operation_id="listNotifications")
async def list_notifications(user: User, db: Db) -> NotificationList:
    return await with_read_state(db, user, await derive_notifications(db, user))


@router.post("/notifications/read", operation_id="markNotificationsRead")
async def mark_notifications_read(
    body: NotificationsReadIn, user: User, db: Db
) -> NotificationList:
    """Mark notifications read (idempotent). Keys the caller has no notification for are
    ignored, so only real notifications are ever stored."""
    items = await derive_notifications(db, user)
    current = {item.key for item in items}
    await mark_read(db, user, current if body.all else current & set(body.keys))
    return await with_read_state(db, user, items)

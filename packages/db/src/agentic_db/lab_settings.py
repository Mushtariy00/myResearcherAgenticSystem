"""Lab-wide settings stored in the ``settings`` table."""

from sqlalchemy.ext.asyncio import AsyncSession

from agentic_db.models import Setting

# The paid-models kill switch, as the admin settings endpoint writes it and the gateway reads it.
PAID_MODELS_KEY = "paid_models_enabled"


async def paid_models_enabled(session: AsyncSession) -> bool:
    """False once an admin turned paid models off; on until anyone has set it."""
    setting = await session.get(Setting, PAID_MODELS_KEY)
    return bool(setting.value.get("enabled", True)) if setting else True

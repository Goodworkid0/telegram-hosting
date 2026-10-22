"""Admin-configurable prices, read from the single AppSettings row.

Each price falls back to a hard default if the settings row or column is missing
(e.g. before the migration runs), so purchase endpoints never break.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppSettings
from app.money import to_money, ZERO

PRICE_DEFAULTS = {
    "subscription_price": 15,
}


async def get_price(db: AsyncSession, field: str):
    """Return the configured price (Decimal) for `field`, or its default.

    Floored at 0: a misconfigured negative price must never turn a purchase into
    a balance credit (delta = -price would credit the buyer)."""
    settings = await db.scalar(select(AppSettings).where(AppSettings.id == 1))
    val = getattr(settings, field, None) if settings else None
    if val is None:
        val = PRICE_DEFAULTS.get(field, 0)
    return max(ZERO, to_money(val))


async def all_prices(db: AsyncSession) -> dict:
    """All prices as floats (for the public branding endpoint / frontend)."""
    settings = await db.scalar(select(AppSettings).where(AppSettings.id == 1))
    out = {}
    for field, default in PRICE_DEFAULTS.items():
        val = getattr(settings, field, None) if settings else None
        out[field] = float(to_money(val if val is not None else default))
    return out

"""Subscription (unlimited downloads) helpers.

The paid tier is a 30-day subscription tracked by User.premium_until. It is
expired LAZILY: there is no scheduler task — endpoints that gate on the
subscription call expire_subscription_if_needed() inside their own transaction
and commit the flip together with their other writes.
"""
from datetime import datetime

from app.models import User, UserRole

SUBSCRIPTION_DAYS = 30


def has_active_subscription(user: User) -> bool:
    """True while the user has unlimited free-file downloads.

    premium_until=None with is_premium=True is an admin-granted lifetime
    subscription. Staff always qualify (mirrors the staff-premium rule applied
    at the serialization boundary in schemas.py)."""
    if user.role in (UserRole.MODERATOR, UserRole.ADMIN):
        return True
    if not user.is_premium:
        return False
    return user.premium_until is None or user.premium_until > datetime.utcnow()


def expire_subscription_if_needed(user: User) -> bool:
    """Flip an expired subscription off. Returns True if flipped (caller commits)."""
    if user.is_premium and user.premium_until and user.premium_until <= datetime.utcnow():
        user.is_premium = False
        return True
    return False

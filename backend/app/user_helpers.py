"""Shared user serialization helpers."""
from typing import Optional

from app.models import User
from app.schemas import UserMinimal


def public_name(user: Optional[User]) -> str:
    """The name safe to embed in server-generated text (notifications, system
    messages, flat *_username response fields). Respects show_telegram: users
    who hide their @handle are named by display name everywhere."""
    if not user:
        return "User"
    if user.show_telegram is False:
        return user.first_name or "User"
    return user.username or user.first_name or "User"


def user_to_minimal(user: User) -> UserMinimal:
    """Convert User to UserMinimal schema.

    Privacy: when the user hides their Telegram handle, `username` is omitted
    from the payload entirely (not just hidden client-side) so the raw @handle
    can't be recovered from the API. `first_name` + `show_telegram` are still
    sent so the client renders the display name via displayName()."""
    return UserMinimal(
        id=user.id,
        username=user.username if user.show_telegram is not False else None,
        first_name=user.first_name,
        avatar_url=user.avatar_url,
        role=user.role,
        rep_positive=user.rep_positive or 0,
        rep_negative=user.rep_negative or 0,
        created_at=user.created_at,
        last_seen_at=user.last_seen_at,
        profile_theme=user.profile_theme,
        show_telegram=user.show_telegram if user.show_telegram is not None else True,
        is_premium=user.is_premium or False,
        premium_until=user.premium_until,
    )

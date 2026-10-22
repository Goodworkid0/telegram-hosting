"""Shared moderation actions.

Single source of truth for staff-protection rules so the three ban call sites
(admin ban, /mod/ban, report-resolution ban) can't diverge.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException

from app.models import User, UserRole


def apply_ban(*, target: User, actor: User, reason: str, duration_days: Optional[int] = None) -> None:
    """Apply ban state to `target`, enforcing staff-protection rules.

    Rules: nobody can ban themselves; admins can never be banned; moderators can
    only be banned by an admin. The caller is responsible for loading the target,
    logging its own ModAction, and committing.
    """
    if target.id == actor.id:
        raise HTTPException(status_code=403, detail="You cannot ban yourself")
    if target.role == UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Cannot ban admins")
    if target.role == UserRole.MODERATOR and actor.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admins can ban moderators")

    target.is_banned = True
    target.ban_reason = reason
    target.banned_at = datetime.utcnow()
    target.ban_expires_at = (datetime.utcnow() + timedelta(days=duration_days)) if duration_days else None
    target.banned_by_id = actor.id


def apply_mute(*, target: User, actor: User, reason: str, duration_minutes: Optional[int] = None) -> None:
    """Apply mute state to `target`, enforcing the same staff-protection rules as bans.

    Rules: nobody can mute themselves; admins can never be muted; moderators can
    only be muted by an admin. Duration is in minutes (None = permanent) so short
    presets (1h/6h) are representable. The caller logs its own ModAction and commits.
    """
    if target.id == actor.id:
        raise HTTPException(status_code=403, detail="You cannot mute yourself")
    if target.role == UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Cannot mute admins")
    if target.role == UserRole.MODERATOR and actor.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admins can mute moderators")

    target.is_muted = True
    target.mute_reason = reason
    target.muted_at = datetime.utcnow()
    target.mute_expires_at = (datetime.utcnow() + timedelta(minutes=duration_minutes)) if duration_minutes else None
    target.muted_by_id = actor.id


def clear_mute(target: User) -> None:
    """Reset all mute state on `target`. Caller logs its own ModAction and commits."""
    target.is_muted = False
    target.mute_reason = None
    target.muted_at = None
    target.mute_expires_at = None
    target.muted_by_id = None

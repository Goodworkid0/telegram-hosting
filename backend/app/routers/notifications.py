"""Notifications Router"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload
from typing import List

from app.database import get_db
from app.models import User, Notification, UserRole
from app.schemas import NotificationResponse
from app.auth import get_current_active_user
from app.telegram import create_notification

router = APIRouter()


@router.get("", response_model=List[NotificationResponse])
async def list_notifications(
    limit: int = 30,
    offset: int = 0,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's notifications, newest first (paginated)"""
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .options(selectinload(Notification.related_user))
        .order_by(Notification.created_at.desc())
        .offset(offset)
        .limit(min(limit, 100))  # Cap maximum limit
    )
    return result.scalars().all()


@router.get("/unread-count")
async def unread_count(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get count of unread notifications"""
    count = await db.scalar(
        select(func.count()).select_from(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read == False)
    )
    return {"count": count or 0}


@router.post("/mark-read")
async def mark_all_read(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark all notifications as read"""
    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read == False)
        .values(is_read=True)
    )
    await db.commit()
    return {"message": "All notifications marked as read"}


@router.post("/{notification_id}/read")
async def mark_one_read(
    notification_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark a single notification as read"""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id
        )
    )
    notif = result.scalar_one_or_none()
    if notif:
        notif.is_read = True
        await db.commit()
    return {"message": "ok"}

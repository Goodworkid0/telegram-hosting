"""Reputation System API Router"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta

from app.database import get_db
from app.dependencies import limiter
from app.auth import get_current_active_user
from app.models import User, ReputationEntry, AppSettings, SharedFile, SharedFileStatus
from app.sanitize import sanitize_content
from app.user_helpers import user_to_minimal, public_name
from app.telegram import create_notification
from app.schemas import (
    ReputationCreate, ReputationResponse, ReputationListResponse,
)

router = APIRouter(prefix="/api/reputation", tags=["Reputation"])


@router.post("/users/{user_id}", response_model=ReputationResponse)
@limiter.limit("10/minute")
async def give_reputation(
    request: Request,
    user_id: int,
    data: ReputationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Give reputation (+rep or -rep) to a user"""
    # Can't rep yourself
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot give reputation to yourself")

    # Lock the target row for the duration of the transaction. This serializes
    # concurrent +rep requests to the same target so the cooldown check below
    # can't be raced (two requests both passing the 24h check before either
    # commits) and the rep counter increment is not lost-update prone.
    result = await db.execute(select(User).where(User.id == user_id).with_for_update())
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Proven-participation gate: the giver needs approved uploads on the board.
    settings_result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
    settings = settings_result.scalar_one_or_none()
    min_uploads = getattr(settings, "min_uploads_for_rep", None) if settings else None
    if min_uploads is None:
        min_uploads = 1

    if min_uploads:
        approved_uploads = (await db.scalar(
            select(func.count(SharedFile.id)).where(
                SharedFile.uploader_id == current_user.id,
                SharedFile.status == SharedFileStatus.APPROVED,
            )
        )) or 0
        if approved_uploads < min_uploads:
            raise HTTPException(
                status_code=403,
                detail=f"You need at least {min_uploads} approved upload(s) to give reputation"
            )

    # Check if user already gave rep to this user recently (24h cooldown)
    cooldown_time = datetime.utcnow() - timedelta(hours=24)
    recent_rep = await db.execute(
        select(ReputationEntry).where(
            ReputationEntry.from_user_id == current_user.id,
            ReputationEntry.to_user_id == user_id,
            ReputationEntry.created_at > cooldown_time,
        )
    )
    if recent_rep.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="You can only give reputation to the same user once every 24 hours"
        )

    # Create reputation entry
    rep_entry = ReputationEntry(
        from_user_id=current_user.id,
        to_user_id=user_id,
        is_positive=data.is_positive,
        comment=sanitize_content(data.comment),
    )
    db.add(rep_entry)

    # Update target user's rep count
    if data.is_positive:
        target_user.rep_positive = (target_user.rep_positive or 0) + 1
    else:
        target_user.rep_negative = (target_user.rep_negative or 0) + 1

    # Flush to assign rep_entry.id without committing, so the rep entry and
    # notification land in ONE atomic transaction.
    await db.flush()

    # Notify target user
    rep_type = "+rep" if data.is_positive else "-rep"
    await create_notification(
        db,
        user_id=target_user.id,
        type="reputation",
        title=f"You received {rep_type}",
        body=f"{public_name(current_user)} gave you {rep_type}" +
             (f": {data.comment}" if data.comment else ""),
        link=f"/u/{target_user.id}",
        related_user_id=current_user.id,
    )

    await db.commit()
    await db.refresh(rep_entry)

    return ReputationResponse(
        id=rep_entry.id,
        is_positive=rep_entry.is_positive,
        comment=rep_entry.comment,
        created_at=rep_entry.created_at,
        from_user=user_to_minimal(current_user),
    )


@router.get("/users/{user_id}", response_model=ReputationListResponse)
async def get_user_reputation(
    user_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get reputation history for a user"""
    # Get target user
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Query reputation entries
    query = (
        select(ReputationEntry)
        .where(ReputationEntry.to_user_id == user_id)
        .options(selectinload(ReputationEntry.from_user))
        .order_by(ReputationEntry.created_at.desc())
    )

    # Paginate
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    entries = result.scalars().all()

    return ReputationListResponse(
        entries=[
            ReputationResponse(
                id=entry.id,
                is_positive=entry.is_positive,
                comment=entry.comment,
                created_at=entry.created_at,
                from_user=user_to_minimal(entry.from_user),
            )
            for entry in entries
        ],
        total_positive=target_user.rep_positive or 0,
        total_negative=target_user.rep_negative or 0,
    )

"""Users API Router"""
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, desc
from sqlalchemy.orm import selectinload
from typing import List
import os
import asyncio

from app.database import get_db
from app.auth import get_current_active_user
from app.dependencies import limiter
from app.telegram import create_notification
from app.models import (
    User, UserRole, UserFollow, SharedFile, SharedFileStatus,
)
from app.schemas import (
    UserResponse, UserPublicProfile, UserMinimal, SuccessResponse,
)
from app.images import process_upload, validated_image_extension, InvalidImageError
from app.user_helpers import user_to_minimal, public_name

router = APIRouter(prefix="/api/users", tags=["Users"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "avatars")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ============================================================================
# CURRENT USER ENDPOINTS
# ============================================================================

@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get current user's profile"""
    return UserResponse(
        id=current_user.id,
        telegram_id=current_user.telegram_id,
        username=current_user.username,
        first_name=current_user.first_name,
        avatar_url=current_user.avatar_url,
        role=current_user.role,
        is_active=current_user.is_active,
        is_banned=current_user.is_banned or False,
        ban_reason=current_user.ban_reason,
        balance=current_user.balance or 0.0,
        pending_balance=current_user.pending_balance or 0.0,
        rep_positive=current_user.rep_positive or 0,
        rep_negative=current_user.rep_negative or 0,
        profile_banner_url=current_user.profile_banner_url,
        profile_bio=current_user.profile_bio,
        profile_theme=current_user.profile_theme,
        notification_preferences=current_user.notification_preferences,
        show_telegram=current_user.show_telegram if current_user.show_telegram is not None else True,
        created_at=current_user.created_at,
        last_seen_at=current_user.last_seen_at,
        is_premium=current_user.is_premium or False,
        premium_until=current_user.premium_until,
        # MUST be included: it defaults to False in the schema, so omitting it makes
        # the frontend think setup is incomplete and re-triggers the onboarding modal
        # every time the user object is refreshed from this endpoint.
        is_setup_complete=current_user.is_setup_complete or False,
    )


@router.post("/me/avatar", response_model=UserResponse)
@limiter.limit("10/minute")
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Upload avatar image"""
    # Validate file size (max 2MB)
    contents = await file.read()
    if len(contents) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 2MB)")

    # Validate by content (magic bytes), not the client-supplied type/filename.
    if validated_image_extension(contents) is None:
        raise HTTPException(status_code=400, detail="Invalid file type. Allowed: JPEG, PNG, GIF, WebP")

    # Process image off the event loop (Pillow encode is CPU-bound and blocking).
    try:
        processed_bytes, processed_filename = await asyncio.to_thread(process_upload, contents, file.filename or "avatar.jpg")
    except InvalidImageError:
        raise HTTPException(status_code=400, detail="Invalid or corrupt image")
    filepath = os.path.join(UPLOAD_DIR, processed_filename)

    # Delete old avatar if exists
    if current_user.avatar_url and current_user.avatar_url.startswith("/api/uploads/avatars/"):
        old_filename = current_user.avatar_url.split("/")[-1]
        old_filepath = os.path.join(UPLOAD_DIR, old_filename)
        if os.path.exists(old_filepath):
            os.remove(old_filepath)

    # Save new avatar
    with open(filepath, "wb") as f:
        f.write(processed_bytes)

    current_user.avatar_url = f"/api/uploads/avatars/{processed_filename}"
    await db.commit()
    await db.refresh(current_user)

    return await get_current_user_profile(db, current_user)


@router.post("/me/banner", response_model=UserResponse)
@limiter.limit("10/minute")
async def upload_banner(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")

    # Validate by content (magic bytes), not the client-supplied type/filename.
    if validated_image_extension(contents) is None:
        raise HTTPException(status_code=400, detail="Invalid file type. Allowed: JPEG, PNG, GIF, WebP")

    # Process image off the event loop (Pillow encode is CPU-bound and blocking).
    try:
        processed_bytes, processed_filename = await asyncio.to_thread(process_upload, contents, file.filename or "banner.jpg")
    except InvalidImageError:
        raise HTTPException(status_code=400, detail="Invalid or corrupt image")
    banner_dir = os.path.join(os.path.dirname(UPLOAD_DIR), "banners")
    os.makedirs(banner_dir, exist_ok=True)
    filepath = os.path.join(banner_dir, processed_filename)
    if current_user.profile_banner_url and "/banners/" in current_user.profile_banner_url:
        old_filename = current_user.profile_banner_url.split("/")[-1]
        old_filepath = os.path.join(banner_dir, old_filename)
        if os.path.exists(old_filepath):
            os.remove(old_filepath)
    with open(filepath, "wb") as f:
        f.write(processed_bytes)
    current_user.profile_banner_url = f"/api/uploads/banners/{processed_filename}"
    await db.commit()
    await db.refresh(current_user)
    return await get_current_user_profile(db, current_user)


# ============================================================================
# PUBLIC USER ENDPOINTS
# ============================================================================

@router.get("/{user_id}", response_model=UserPublicProfile)
async def get_user_profile(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a user's public profile"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if current user is following
    is_following = False
    if current_user.id != user_id:
        follow_result = await db.execute(
            select(UserFollow).where(
                UserFollow.follower_id == current_user.id,
                UserFollow.following_id == user_id,
            )
        )
        is_following = follow_result.scalar_one_or_none() is not None

    # Get follower/following counts
    follower_count = await db.scalar(
        select(func.count(UserFollow.id)).where(UserFollow.following_id == user_id)
    )
    following_count = await db.scalar(
        select(func.count(UserFollow.id)).where(UserFollow.follower_id == user_id)
    )

    # Hosting stats: approved uploads + total downloads of them
    upload_count = await db.scalar(
        select(func.count(SharedFile.id)).where(
            SharedFile.uploader_id == user_id,
            SharedFile.status == SharedFileStatus.APPROVED,
        )
    )
    download_count = await db.scalar(
        select(func.coalesce(func.sum(SharedFile.download_count), 0)).where(
            SharedFile.uploader_id == user_id,
            SharedFile.status == SharedFileStatus.APPROVED,
        )
    )

    # Privacy: only expose the raw @handle to the owner or staff when the user
    # has hidden it; everyone else gets None and sees the display name.
    _viewer_is_staff = current_user.role in (UserRole.MODERATOR, UserRole.ADMIN)
    _show_handle = user.show_telegram is not False or current_user.id == user.id or _viewer_is_staff

    return UserPublicProfile(
        id=user.id,
        username=user.username if _show_handle else None,
        first_name=user.first_name,
        avatar_url=user.avatar_url,
        role=user.role,
        rep_positive=user.rep_positive or 0,
        rep_negative=user.rep_negative or 0,
        upload_count=upload_count or 0,
        download_count=download_count or 0,
        profile_banner_url=user.profile_banner_url,
        profile_bio=user.profile_bio,
        profile_theme=user.profile_theme,
        show_telegram=user.show_telegram if user.show_telegram is not None else True,
        last_seen_at=user.last_seen_at,
        created_at=user.created_at,
        is_following=is_following,
        follower_count=follower_count or 0,
        following_count=following_count or 0,
        is_premium=user.is_premium or False,
        is_banned=user.is_banned or False,
        is_muted=user.is_muted or False,
    )


@router.get("/{user_id}/files")
async def get_user_files(
    user_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """A user's APPROVED uploads (public, newest first) — the profile Uploads tab."""
    from app.routers.files import serialize_file, _purchased_ids

    base = select(SharedFile).where(
        SharedFile.uploader_id == user_id,
        SharedFile.status == SharedFileStatus.APPROVED,
    )
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    result = await db.execute(
        base.options(selectinload(SharedFile.uploader), selectinload(SharedFile.category))
        .order_by(desc(SharedFile.created_at))
        .offset((page - 1) * per_page).limit(per_page)
    )
    files = result.scalars().all()
    purchased = await _purchased_ids(db, current_user.id, [f.id for f in files])
    items = [serialize_file(f, viewer=current_user, purchased_ids=purchased) for f in files]
    return {"items": items, "total": total or 0, "page": page, "per_page": per_page}


@router.get("", response_model=List[UserMinimal])
@limiter.limit("30/minute")
async def search_users(
    request: Request,
    q: str = Query(None, min_length=2, max_length=50),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Search users by username or name"""
    query = select(User).where(User.is_active == True, User.is_banned == False)

    if q:
        search_term = f"%{q}%"
        query = query.where(
            or_(
                # Don't confirm a hidden @handle via username match — users who
                # hide their handle are findable only by display name.
                and_(User.show_telegram != False, User.username.ilike(search_term)),
                User.first_name.ilike(search_term),
            )
        )

    query = query.order_by(desc(User.rep_positive)).offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    users = result.scalars().all()

    return [user_to_minimal(u) for u in users]


# ============================================================================
# FOLLOW SYSTEM
# ============================================================================

@router.post("/{user_id}/follow", response_model=SuccessResponse)
async def follow_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Follow a user"""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")

    # Check if user exists
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if already following
    existing = await db.execute(
        select(UserFollow).where(
            UserFollow.follower_id == current_user.id,
            UserFollow.following_id == user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already following")

    follow = UserFollow(follower_id=current_user.id, following_id=user_id)
    db.add(follow)

    # Notify user (in-app + Telegram mirror + SSE)
    await create_notification(
        db, user_id=user_id, type="new_follower",
        title="New follower",
        body=f"{public_name(current_user)} started following you",
        link=f"/profile/{current_user.id}",
        related_user_id=current_user.id,
    )

    await db.commit()

    return SuccessResponse(message="User followed")


@router.delete("/{user_id}/follow", response_model=SuccessResponse)
async def unfollow_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Unfollow a user"""
    result = await db.execute(
        select(UserFollow).where(
            UserFollow.follower_id == current_user.id,
            UserFollow.following_id == user_id,
        )
    )
    follow = result.scalar_one_or_none()

    if not follow:
        raise HTTPException(status_code=400, detail="Not following")

    await db.delete(follow)
    await db.commit()

    return SuccessResponse(message="User unfollowed")


@router.get("/{user_id}/followers", response_model=List[UserMinimal])
async def get_user_followers(
    user_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Users who follow this user (newest first)."""
    result = await db.execute(
        select(UserFollow)
        .where(UserFollow.following_id == user_id)
        .options(selectinload(UserFollow.follower))
        .order_by(desc(UserFollow.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    follows = result.scalars().all()
    return [user_to_minimal(f.follower) for f in follows if f.follower]


@router.get("/{user_id}/following", response_model=List[UserMinimal])
async def get_user_following(
    user_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Users this user follows (newest first)."""
    result = await db.execute(
        select(UserFollow)
        .where(UserFollow.follower_id == user_id)
        .options(selectinload(UserFollow.following))
        .order_by(desc(UserFollow.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    follows = result.scalars().all()
    return [user_to_minimal(f.following) for f in follows if f.following]

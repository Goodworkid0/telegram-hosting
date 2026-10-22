"""Admin: users endpoints (split from admin.py)."""
from app.routers.admin.common import *  # noqa: F401,F403

router = APIRouter()


class AdminStats(BaseModel):
    total_users: int = 0
    total_files: int = 0
    files_pending: int = 0
    total_downloads: int = 0
    total_deposits: float = 0.0
    total_withdrawals_pending: int = 0
    users_today: int = 0
    files_today: int = 0



@router.get("/stats", response_model=AdminStats)
async def get_admin_stats(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get platform statistics"""
    from datetime import timedelta
    
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    from app.models import SharedFile, SharedFileStatus

    total_users = await db.scalar(select(func.count()).select_from(User)) or 0
    total_files = await db.scalar(select(func.count()).select_from(SharedFile)) or 0
    files_pending = await db.scalar(
        select(func.count()).select_from(SharedFile).where(SharedFile.status == SharedFileStatus.PENDING)
    ) or 0
    total_downloads = await db.scalar(
        select(func.coalesce(func.sum(SharedFile.download_count), 0))
    ) or 0

    total_deposits = await db.scalar(
        select(func.coalesce(func.sum(CryptoDeposit.price_amount_usd), 0))
        .where(CryptoDeposit.is_credited == True)
    ) or 0.0
    
    total_withdrawals_pending = await db.scalar(
        select(func.count()).select_from(WithdrawalRequest)
        .where(WithdrawalRequest.status == WithdrawalStatus.PENDING)
    ) or 0
    
    users_today = await db.scalar(
        select(func.count()).select_from(User).where(User.created_at >= today)
    ) or 0

    files_today = await db.scalar(
        select(func.count()).select_from(SharedFile).where(SharedFile.created_at >= today)
    ) or 0

    return AdminStats(
        total_users=total_users,
        total_files=total_files,
        files_pending=files_pending,
        total_downloads=int(total_downloads),
        total_deposits=float(total_deposits),
        total_withdrawals_pending=total_withdrawals_pending,
        users_today=users_today,
        files_today=files_today,
    )



@router.get("/users")
async def get_users(
    q: Optional[str] = Query(None, max_length=100),
    role: Optional[UserRole] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all users with optional filters"""
    from app.user_helpers import user_to_minimal

    filters = []
    if q:
        search = f"%{q}%"
        filters.append(
            User.username.ilike(search) |
            User.first_name.ilike(search) |
            User.telegram_id.cast(String).ilike(search)
        )
    if role:
        filters.append(User.role == role)

    total = await db.scalar(select(func.count()).select_from(User).where(*filters)) or 0

    query = (
        select(User)
        .where(*filters)
        .order_by(User.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    users = result.scalars().all()

    items = [
        {
            **user_to_minimal(u).model_dump(),
            "is_banned": u.is_banned or False,
            "is_muted": u.is_muted or False,
            # Admin-only extra: the users table shows balances.
            "balance": float(u.balance or 0),
        }
        for u in users
    ]
    return {"items": items, "total": total, "page": page, "per_page": per_page}



@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get user details"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserResponse(
        id=user.id,
        telegram_id=str(user.telegram_id),
        username=user.username,
        first_name=user.first_name,
        avatar_url=user.avatar_url,
        role=user.role,
        is_active=user.is_active,
        is_banned=user.is_banned or False,
        ban_reason=user.ban_reason,
        is_muted=user.is_muted or False,
        mute_reason=user.mute_reason,
        mute_expires_at=user.mute_expires_at,
        balance=user.balance or 0.0,
        rep_positive=user.rep_positive or 0,
        rep_negative=user.rep_negative or 0,
        profile_banner_url=user.profile_banner_url,
        profile_bio=user.profile_bio,
        show_telegram=user.show_telegram if user.show_telegram is not None else True,
        created_at=user.created_at,
        last_seen_at=user.last_seen_at,
        is_premium=user.is_premium or False,
        premium_until=user.premium_until,
    )



@router.post("/users/{user_id}/ban", response_model=SuccessResponse)
async def ban_user(
    user_id: int,
    reason: str = Query(...),
    duration_days: Optional[int] = Query(None),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Ban a user"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    apply_ban(target=user, actor=current_user, reason=reason, duration_days=duration_days)

    # Log action
    mod_action = ModAction(
        moderator_id=current_user.id,
        target_user_id=user_id,
        action_type="ban",
        reason=reason,
        details=f"duration_days={duration_days}" if duration_days else "permanent",
    )
    db.add(mod_action)
    
    await db.commit()
    return SuccessResponse(message=f"User banned {'permanently' if not duration_days else f'for {duration_days} days'}")



@router.post("/users/{user_id}/unban", response_model=SuccessResponse)
async def unban_user(
    user_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Unban a user"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_banned = False
    user.ban_reason = None
    user.ban_expires_at = None
    
    mod_action = ModAction(
        moderator_id=current_user.id,
        target_user_id=user_id,
        action_type="unban",
        reason="User unbanned by admin",
    )
    db.add(mod_action)
    
    await db.commit()
    return SuccessResponse(message="User unbanned")



@router.put("/users/{user_id}/role", response_model=SuccessResponse)
async def update_user_role(
    user_id: int,
    role: UserRole = Query(...),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Change user role"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")
    
    old_role = user.role
    user.role = role
    
    mod_action = ModAction(
        moderator_id=current_user.id,
        target_user_id=user_id,
        action_type="role_change",
        reason=f"Role changed from {old_role.value} to {role.value}",
    )
    db.add(mod_action)
    
    await db.commit()
    return SuccessResponse(message=f"User role updated to {role.value}")



@router.put("/users/{user_id}/balance", response_model=SuccessResponse)
async def adjust_user_balance(
    user_id: int,
    amount: float = Query(..., description="Positive to add, negative to subtract"),
    reason: str = Query("Admin adjustment", max_length=200),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Adjust user balance"""
    result = await db.execute(select(User).where(User.id == user_id).with_for_update())
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    record_balance_change(
        db, user, delta=amount, clamp_zero=True, entry_type="admin_adjustment",
        description=f"Admin balance adjustment: {reason}",
    )

    mod_action = ModAction(
        moderator_id=current_user.id,
        target_user_id=user_id,
        action_type="balance_adjustment",
        reason=f"Balance adjusted by ${amount:.2f}. Reason: {reason}",
    )
    db.add(mod_action)
    
    # Notify user
    await create_notification(
        db, user_id=user_id, type="balance_adjusted",
        title="Balance Updated",
        body=f"Your balance was adjusted by ${amount:.2f} by an administrator.",
        link="/wallet",
    )

    await commit_and_broadcast(db)
    return SuccessResponse(message=f"Balance adjusted by ${amount:.2f}. New balance: ${user.balance:.2f}")



@router.get("/users/{user_id}/ledger")
async def admin_user_ledger(
    user_id: int,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Recent ledger entries for a user plus reconciliation of both accounts.
    `reconciliation.*.consistent` should always be true; false means the user's
    balance has drifted from the sum of their ledger entries (investigate)."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    rows = (await db.execute(
        select(LedgerEntry)
        .where(LedgerEntry.user_id == user_id)
        .order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc())
        .limit(limit)
    )).scalars().all()

    return {
        "user_id": user_id,
        "reconciliation": {
            "balance": await reconcile_user(db, user_id, "balance"),
            "pending": await reconcile_user(db, user_id, "pending"),
        },
        "entries": [
            {
                "id": e.id, "account": e.account, "amount": e.amount,
                "balance_after": e.balance_after, "entry_type": e.entry_type,
                "ref_type": e.ref_type, "ref_id": e.ref_id,
                "description": e.description, "created_at": e.created_at,
            }
            for e in rows
        ],
    }



@router.put("/users/{user_id}/premium", response_model=SuccessResponse)
async def manage_premium(
    user_id: int,
    is_premium: bool = Query(...),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Grant or revoke the subscription. An admin grant is a LIFETIME
    subscription (premium_until=None); revoking clears both fields."""
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_premium = is_premium
    user.premium_until = None  # lifetime grant (or cleared on revoke)

    await db.commit()

    mod_action = ModAction(
        moderator_id=current_user.id,
        target_user_id=user_id,
        action_type="premium_change",
        reason=f"Premium {'granted' if is_premium else 'revoked'}",
    )
    db.add(mod_action)
    await db.commit()

    return SuccessResponse(message=f"Premium {'granted' if is_premium else 'revoked'}")



class CreateUserRequest(BaseModel):
    telegram_id: str
    username: str = ""
    first_name: str = ""
    role: str = "USER"



@router.post("/users")
async def create_user(
    data: CreateUserRequest,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user (admin only)."""
    existing = await db.scalar(select(User).where(User.telegram_id == data.telegram_id))
    if existing:
        raise HTTPException(status_code=400, detail="User with this Telegram ID already exists")

    role = UserRole.USER
    try:
        role = UserRole(data.role.upper())
    except ValueError:
        pass

    user = User(
        telegram_id=data.telegram_id,
        username=data.username or f"user_{data.telegram_id}",
        first_name=data.first_name or data.username or "User",
        role=role,
        is_setup_complete=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"id": user.id, "telegram_id": user.telegram_id, "username": user.username, "role": user.role.value, "created": True}



@router.post("/users/{user_id}/impersonate")
async def impersonate_user(
    user_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.role == UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Cannot impersonate admins")

    from datetime import datetime, timedelta
    # `imp` records the acting admin so the session can be identified as an
    # impersonation: get_current_user surfaces it and sensitive ops (withdrawals,
    # purchases, credential changes) are blocked while it is present.
    token_data = {"sub": user.telegram_id, "type": "access", "tv": user.token_version or 0, "imp": current_user.id, "exp": datetime.utcnow() + timedelta(minutes=15)}
    token = jwt.encode(
        token_data,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    mod_action = ModAction(
        moderator_id=current_user.id,
        target_user_id=user_id,
        action_type="impersonate",
        reason=f"Admin {current_user.username or current_user.first_name} impersonated user {user.username or user.first_name}",
    )
    db.add(mod_action)
    await db.commit()

    return {"token": token}


@router.post("/users/{user_id}/force-logout", response_model=SuccessResponse)
async def force_logout_user(
    user_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Invalidate all of a user's active sessions by bumping their token version."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.token_version = (user.token_version or 0) + 1

    mod_action = ModAction(
        moderator_id=current_user.id,
        target_user_id=user_id,
        action_type="force_logout",
        reason="All sessions revoked",
    )
    db.add(mod_action)
    await db.commit()

    return SuccessResponse(message="User logged out of all sessions")



@router.get("/blacklist")
async def get_blacklist(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get list of banned users (visible to all authenticated users)."""
    result = await db.execute(
        select(User).where(User.is_banned == True)
        .order_by(User.banned_at.desc().nullslast())
    )
    users = result.scalars().all()

    # Staff see the raw telegram_id (PII) and the moderator-written ban_reason
    # (which may contain internal notes / a reporter's free text); regular users
    # see only that the account is banned, not why.
    is_staff = current_user.role in (UserRole.MODERATOR, UserRole.ADMIN)

    return [
        {
            "id": u.id,
            "username": u.username,
            "first_name": u.first_name,
            **({"telegram_id": u.telegram_id} if is_staff else {}),
            "avatar_url": u.avatar_url,
            "banned_at": u.banned_at.isoformat() if u.banned_at else None,
            "ban_reason": u.ban_reason if is_staff else None,
        }
        for u in users
    ]


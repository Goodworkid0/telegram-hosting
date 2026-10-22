"""Public file board — lists approved files users dropped into the bot, and
delivers a requested file to the user via the bot (no re-hosting).

Business rules:
- Free tier: `free_downloads_per_day` free-file deliveries per rolling 24h
  (FileDownload rows). An active subscription lifts the quota entirely.
- Paywalled files (price > 0): a one-time FilePurchase (paid from balance)
  grants permanent access. Purchases bypass the quota and never consume it.
  The subscription does NOT bypass paywalls.
- Uploaders download their own files freely and set/clear the price.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import limiter
from app.auth import get_current_active_user, block_if_impersonating
from app.ledger import record_balance_change, commit_and_broadcast
from app.money import to_money, apply_percent, ZERO
from app.models import (
    User, AppSettings, SharedFile, SharedFileStatus, FileCategory,
    FilePurchase, FileDownload,
)
from app.schemas import (
    SharedFileResponse, FileCategoryResponse, FilePriceUpdate, FileQuotaResponse,
)
from app.subscription import has_active_subscription, expire_subscription_if_needed
from app.user_helpers import user_to_minimal
from app.telegram import send_file, create_notification

router = APIRouter(prefix="/api/files", tags=["Files"])

QUOTA_WINDOW = timedelta(hours=24)  # rolling window for the free-tier quota


async def _get_settings(db: AsyncSession) -> AppSettings | None:
    return await db.scalar(select(AppSettings).where(AppSettings.id == 1))


def _free_limit(settings: AppSettings | None) -> int:
    val = getattr(settings, "free_downloads_per_day", None) if settings else None
    return val if val is not None else 5


def _fee_percent(settings: AppSettings | None) -> float:
    val = getattr(settings, "platform_fee_percent", None) if settings else None
    if val is None:
        return 10.0
    return min(100.0, max(0.0, float(val)))


def _is_paywalled(f: SharedFile) -> bool:
    return to_money(f.price) > ZERO


async def _quota_used(db: AsyncSession, user_id: int) -> int:
    return (await db.scalar(
        select(func.count(FileDownload.id)).where(
            FileDownload.user_id == user_id,
            FileDownload.created_at > datetime.utcnow() - QUOTA_WINDOW,
        )
    )) or 0


def serialize_file(
    f: SharedFile,
    *,
    include_admin: bool = False,
    viewer: User | None = None,
    purchased_ids: set[int] | None = None,
) -> SharedFileResponse:
    price = to_money(f.price)
    return SharedFileResponse(
        id=f.id,
        kind=f.kind,
        file_name=f.file_name,
        mime_type=f.mime_type,
        file_size=f.file_size,
        caption=f.caption,
        uploader=user_to_minimal(f.uploader) if f.uploader else None,
        category_id=f.category_id,
        category_name=f.category.name if f.category else None,
        suggested_category_id=(f.suggested_category_id if include_admin else None),
        suggested_category_name=(f.suggested_category.name if include_admin and f.suggested_category else None),
        download_count=f.download_count or 0,
        created_at=f.created_at,
        price=(float(price) if price > ZERO else None),
        purchase_count=f.purchase_count or 0,
        is_purchased=bool(purchased_ids and f.id in purchased_ids),
        is_own=bool(viewer and f.uploader_id == viewer.id),
        status=(f.status.value if include_admin and f.status else None),
        reject_reason=(f.reject_reason if include_admin else None),
    )


async def _purchased_ids(db: AsyncSession, user_id: int, file_ids: list[int]) -> set[int]:
    """Batch-fetch which of `file_ids` the viewer has purchased."""
    if not file_ids:
        return set()
    rows = await db.execute(
        select(FilePurchase.file_id).where(
            FilePurchase.buyer_id == user_id,
            FilePurchase.file_id.in_(file_ids),
        )
    )
    return {r[0] for r in rows}


@router.get("/categories", response_model=list[FileCategoryResponse])
async def list_categories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Active categories for the board filter (ordered)."""
    result = await db.execute(
        select(FileCategory).where(FileCategory.is_active == True)
        .order_by(FileCategory.sort_order, FileCategory.name)
    )
    return [FileCategoryResponse.model_validate(c) for c in result.scalars().all()]


@router.get("/quota", response_model=FileQuotaResponse)
async def get_quota(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """The current user's free-download quota state (for the board header)."""
    if expire_subscription_if_needed(current_user):
        await db.commit()
    settings = await _get_settings(db)
    return FileQuotaResponse(
        used_today=await _quota_used(db, current_user.id),
        limit=_free_limit(settings),
        subscription_active=has_active_subscription(current_user),
        premium_until=current_user.premium_until,
    )


@router.get("/mine")
async def list_my_files(
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """The current user's uploads, all statuses (with reject reason, price,
    sales count) plus total earnings from paywalled sales."""
    base = select(SharedFile).where(SharedFile.uploader_id == current_user.id)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    result = await db.execute(
        base.options(selectinload(SharedFile.uploader), selectinload(SharedFile.category))
        .order_by(desc(SharedFile.created_at))
        .offset((page - 1) * per_page).limit(per_page)
    )
    items = [
        serialize_file(f, include_admin=True, viewer=current_user)
        for f in result.scalars().all()
    ]
    earnings = await db.scalar(
        select(func.coalesce(func.sum(FilePurchase.uploader_credit), 0))
        .join(SharedFile, SharedFile.id == FilePurchase.file_id)
        .where(SharedFile.uploader_id == current_user.id)
    )
    return {
        "items": items, "total": total or 0, "page": page, "per_page": per_page,
        "total_earnings": float(to_money(earnings)),
    }


@router.get("")
async def list_files(
    q: str = Query(None, max_length=100),
    category_id: int = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List approved files on the board (newest first), optionally filtered by
    category. category_id=0 selects the uncategorized files."""
    base = select(SharedFile).where(SharedFile.status == SharedFileStatus.APPROVED)
    if q:
        base = base.where(SharedFile.file_name.ilike(f"%{q}%"))
    if category_id is not None:
        base = base.where(SharedFile.category_id == (category_id or None))

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


@router.patch("/{file_id}/price")
async def set_file_price(
    file_id: int,
    data: FilePriceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Uploader sets/clears the one-time purchase price of their own file.
    Existing purchases keep access regardless of later price changes."""
    f = await db.get(SharedFile, file_id)
    if not f:
        raise HTTPException(404, "File not found")
    if f.uploader_id != current_user.id:
        raise HTTPException(403, "You can only price your own files")
    price = to_money(data.price) if data.price is not None else None
    f.price = None if (price is None or price <= ZERO) else price
    await db.commit()
    return {"ok": True, "price": float(f.price) if f.price else None}


@router.post("/{file_id}/purchase")
@limiter.limit("10/minute")
async def purchase_file(
    request: Request,
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(block_if_impersonating),
):
    """Buy permanent access to a paywalled file from balance. The uploader is
    credited the price minus the platform fee; both movements are ledgered."""
    # Lock the buyer row so concurrent purchases can't double-spend the balance.
    buyer = await db.scalar(
        select(User).where(User.id == current_user.id).with_for_update()
    )
    f = await db.get(SharedFile, file_id)
    if not f or f.status != SharedFileStatus.APPROVED:
        raise HTTPException(404, "File not found")
    if not _is_paywalled(f):
        raise HTTPException(400, "This file is free — no purchase needed")
    if f.uploader_id == buyer.id:
        raise HTTPException(400, "You already own this file")

    existing = await db.scalar(select(FilePurchase).where(
        FilePurchase.buyer_id == buyer.id, FilePurchase.file_id == f.id,
    ))
    if existing:
        raise HTTPException(400, "Already purchased")

    price = to_money(f.price)
    if to_money(buyer.balance) < price:
        raise HTTPException(400, "Insufficient balance")

    settings = await _get_settings(db)
    fee_pct = _fee_percent(settings)
    credit = price - apply_percent(price, fee_pct)

    record_balance_change(
        db, buyer, delta=-price, entry_type="file_purchase",
        ref_type="shared_file", ref_id=f.id,
        description=f'Purchased "{(f.file_name or "file")[:80]}"',
    )

    uploader = await db.get(User, f.uploader_id) if f.uploader_id else None
    if uploader:
        record_balance_change(
            db, uploader, delta=credit, entry_type="file_sale",
            ref_type="shared_file", ref_id=f.id,
            description=f'Sale of "{(f.file_name or "file")[:80]}" (fee {fee_pct:g}%)',
        )
        await create_notification(
            db, user_id=uploader.id, type="file_sold",
            title="File sold!",
            body=f'"{(f.file_name or "file")[:80]}" was purchased for ${float(price):.2f} — you earned ${float(credit):.2f}.',
            link="/files",
            telegram_id=uploader.telegram_id,
            related_user_id=buyer.id,
        )

    db.add(FilePurchase(
        buyer_id=buyer.id, file_id=f.id,
        price=price, uploader_credit=(credit if uploader else ZERO), fee_percent=fee_pct,
    ))
    f.purchase_count = (f.purchase_count or 0) + 1

    await commit_and_broadcast(db)
    return {"ok": True, "message": "Purchased — you can now download this file anytime.",
            "balance": float(to_money(buyer.balance))}


@router.post("/{file_id}/download")
@limiter.limit("20/minute")
async def request_file(
    request: Request,
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Deliver the file to the requesting user via the bot (DM).

    Check order: own file → free delivery; paywalled → must be purchased
    (402 otherwise), never quota-counted; free file → daily quota applies
    unless the subscription is active."""
    f = await db.get(SharedFile, file_id)
    if not f or f.status != SharedFileStatus.APPROVED:
        raise HTTPException(404, "File not found")

    is_own = f.uploader_id == current_user.id
    quota_counted = False

    if not is_own:
        if _is_paywalled(f):
            owned = await db.scalar(select(FilePurchase.id).where(
                FilePurchase.buyer_id == current_user.id,
                FilePurchase.file_id == f.id,
            ))
            if not owned:
                raise HTTPException(402, {
                    "code": "purchase_required",
                    "price": float(to_money(f.price)),
                })
        else:
            expired = expire_subscription_if_needed(current_user)
            if not has_active_subscription(current_user):
                settings = await _get_settings(db)
                limit = _free_limit(settings)
                used = await _quota_used(db, current_user.id)
                if used >= limit:
                    if expired:
                        await db.commit()  # persist the lazy expiry even on refusal
                    raise HTTPException(429, {
                        "code": "quota_exceeded",
                        "limit": limit,
                        "used": used,
                    })
                quota_counted = True

    ok, err = await send_file(
        current_user.telegram_id, f.file_id, kind=f.kind,
        caption=f.file_name or None,
    )
    if not ok:
        if err == "not_started":
            raise HTTPException(
                409,
                "Open the bot and tap Start first, then request the file again.",
            )
        raise HTTPException(502, "Could not deliver the file. Please try again.")

    # Best-effort counters; a failed increment must not fail the delivery.
    f.download_count = (f.download_count or 0) + 1
    if quota_counted:
        db.add(FileDownload(user_id=current_user.id, file_id=f.id))
    await db.commit()
    return {"ok": True, "message": "The file has been sent to you on Telegram."}

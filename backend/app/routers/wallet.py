"""Wallet Router - Balance management and withdrawals"""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import httpx
import os
import logging

from app.database import get_db
from app.models import User, UserRole, WithdrawalRequest, WithdrawalStatus, Notification, AppSettings, LedgerEntry
from app.ledger import record_balance_change, commit_and_broadcast
from app.money import to_money, apply_percent, ZERO
from app.auth import get_current_active_user, block_if_impersonating

from app.dependencies import limiter

router = APIRouter()
audit_logger = logging.getLogger("audit")

async def _get_settings(db) -> AppSettings | None:
    """Get AppSettings singleton."""
    from sqlalchemy import select as sel
    result = await db.execute(sel(AppSettings).where(AppSettings.id == 1))
    return result.scalar_one_or_none()


async def _get_withdrawal_fee(db) -> float:
    """Get withdrawal fee percent from AppSettings."""
    settings = await _get_settings(db)
    return (settings.withdrawal_fee_percent if settings and settings.withdrawal_fee_percent else 0.0)


class WalletWithdraw(BaseModel):
    amount: float = Field(gt=0, le=100000)
    address: str = Field(min_length=95, max_length=106)
    pin: Optional[str] = None
    idempotency_key: Optional[str] = Field(default=None, max_length=64)

_xmr_price_cache = {"price": None, "timestamp": None}

async def _get_xmr_price() -> Optional[float]:
    """Live XMR/USD price, or None if unavailable.

    Returns the last cached price within the 5-minute TTL, then tries the live
    API, then falls back to any stale cached value. If we have never had a real
    price we return None rather than a fabricated constant — callers surface
    "price unavailable" instead of quoting a made-up XMR figure.
    """
    global _xmr_price_cache
    now = datetime.utcnow()
    if _xmr_price_cache["price"] and _xmr_price_cache["timestamp"]:
        if (now - _xmr_price_cache["timestamp"]).total_seconds() < 300:
            return _xmr_price_cache["price"]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://api.coingecko.com/api/v3/simple/price?ids=monero&vs_currencies=usd")
            data = resp.json()
            price = data.get("monero", {}).get("usd", 0)
            if price and price > 0:
                _xmr_price_cache = {"price": price, "timestamp": now}
                return price
    except Exception:
        pass
    return _xmr_price_cache["price"] or None


@router.get("")
async def get_wallet_overview(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get wallet overview with balances"""
    from sqlalchemy import func
    
    # Get pending withdrawals
    pending_withdrawals = await db.scalar(
        select(func.count()).select_from(WithdrawalRequest).where(
            WithdrawalRequest.user_id == current_user.id,
            WithdrawalRequest.status.in_([WithdrawalStatus.PENDING, WithdrawalStatus.PROCESSING])
        )
    ) or 0
    pending_withdrawal_amount = await db.scalar(
        select(func.sum(WithdrawalRequest.amount)).where(
            WithdrawalRequest.user_id == current_user.id,
            WithdrawalRequest.status.in_([WithdrawalStatus.PENDING, WithdrawalStatus.PROCESSING])
        )
    ) or 0.0
    
    # Determine if user can withdraw
    can_withdraw = current_user.role in (UserRole.MODERATOR, UserRole.ADMIN)
    if not can_withdraw and (current_user.balance or 0) > 0:
        can_withdraw = True
    
    xmr_price = await _get_xmr_price()
    balance = current_user.balance or 0.0
    settings = await _get_settings(db)
    
    return {
        "balance": current_user.balance or 0.0,
        "pending_withdrawals": pending_withdrawals,
        "pending_withdrawal_amount": pending_withdrawal_amount,
        "can_withdraw": can_withdraw,
        "withdrawal_fee_percent": await _get_withdrawal_fee(db),
        "min_withdrawal": settings.min_withdrawal_amount if settings else 10.0,
        "min_deposit": settings.min_deposit_amount if settings else 10.0,
        "max_escrow_deals": settings.max_active_escrow_deals if settings else 3,
        "xmr_price": xmr_price,
        "xmr_equivalent": round(float(balance) / xmr_price, 6) if xmr_price and xmr_price > 0 else None,
    }


@router.post("/withdraw")
@limiter.limit("5/minute")
async def request_withdrawal(
    request: Request,
    payload: WalletWithdraw,
    current_user: User = Depends(block_if_impersonating),
    db: AsyncSession = Depends(get_db)
):
    """Request withdrawal from balance (available to all users)"""
    settings = await _get_settings(db)
    min_withdrawal = settings.min_withdrawal_amount if settings else 10.0
    if payload.amount < min_withdrawal:
        raise HTTPException(status_code=400, detail=f"Minimum withdrawal is ${min_withdrawal:.2f}")
    
    address = payload.address.strip()
    if not (address.startswith('4') or address.startswith('8')) or len(address) < 95 or len(address) > 106:
        raise HTTPException(status_code=400, detail="Invalid Monero (XMR) address. Must start with 4 or 8 and be 95-106 characters.")

    # Step-up auth: if the user has a PIN set, require it for payouts.
    if current_user.pin_hash:
        if not payload.pin:
            raise HTTPException(status_code=403, detail="PIN required to withdraw")
        from app.auth import check_pin
        if not check_pin(payload.pin, current_user.pin_hash):
            audit_logger.warning(f"WALLET_WITHDRAW: invalid PIN for user {current_user.id}")
            raise HTTPException(status_code=403, detail="Invalid PIN")

    # Idempotency: a retried request with the same key returns the original
    # withdrawal instead of creating a second payout.
    if payload.idempotency_key:
        prior = await db.execute(
            select(WithdrawalRequest).where(
                WithdrawalRequest.user_id == current_user.id,
                WithdrawalRequest.idempotency_key == payload.idempotency_key,
            )
        )
        prior_wr = prior.scalar_one_or_none()
        if prior_wr:
            return {
                "message": "Withdrawal request already submitted",
                "withdrawal_id": prior_wr.id,
                "amount": prior_wr.amount,
                "fee_amount": prior_wr.fee_amount,
                "net_amount": prior_wr.net_amount,
                "idempotent": True,
            }

    # Check for existing pending withdrawal
    existing = await db.execute(
        select(WithdrawalRequest).where(
            WithdrawalRequest.user_id == current_user.id,
            WithdrawalRequest.status == WithdrawalStatus.PENDING
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="You already have a pending withdrawal request")

    # Lock user row
    user_result = await db.execute(
        select(User).where(User.id == current_user.id).with_for_update()
    )
    user = user_result.scalar_one()
    
    amount = to_money(payload.amount)
    if to_money(user.balance) < amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    # Get withdrawal fee from settings
    settings_result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
    settings = settings_result.scalar_one_or_none()
    fee_percent = (settings.withdrawal_fee_percent if settings and settings.withdrawal_fee_percent else 0.0)
    fee_amount = apply_percent(amount, fee_percent)
    net_amount = amount - fee_amount

    if net_amount <= ZERO:
        raise HTTPException(status_code=400, detail="Amount too small after fee deduction")

    # Create withdrawal request first so the ledger entry can reference it.
    withdrawal = WithdrawalRequest(
        user_id=current_user.id,
        amount=amount,
        fee_amount=fee_amount,
        net_amount=net_amount,
        destination=address,
        payout_currency="xmr",
        idempotency_key=payload.idempotency_key or None,
    )
    db.add(withdrawal)
    await db.flush()

    # Deduct full amount from balance (fee + net)
    record_balance_change(
        db, user, delta=-amount, entry_type="withdrawal",
        ref_type="withdrawal_request", ref_id=withdrawal.id,
        description=f"Withdrawal to {address[:10]}…",
    )

    audit_logger.info(
        f"WALLET_WITHDRAW: User {user.id} requested ${payload.amount:.2f} withdrawal. "
        f"Remaining balance: ${user.balance:.2f}"
    )

    await commit_and_broadcast(db)
    await db.refresh(withdrawal)
    
    xmr_price = await _get_xmr_price()
    xmr_amount = round(float(net_amount) / xmr_price, 6) if xmr_price and xmr_price > 0 else None
    
    return {
        "message": "Withdrawal request submitted",
        "withdrawal_id": withdrawal.id,
        "amount": withdrawal.amount,
        "fee_amount": withdrawal.fee_amount,
        "net_amount": withdrawal.net_amount,
        "xmr_price": xmr_price,
        "xmr_amount": xmr_amount,
    }


@router.get("/withdrawals")
async def list_wallet_withdrawals(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """List user's withdrawal requests"""
    result = await db.execute(
        select(WithdrawalRequest)
        .where(WithdrawalRequest.user_id == current_user.id)
        .order_by(WithdrawalRequest.created_at.desc())
        .limit(50)
    )
    withdrawals = result.scalars().all()
    
    return [{
        "id": w.id,
        "amount": w.amount,
        "fee_amount": w.fee_amount or 0,
        "net_amount": w.net_amount or w.amount,
        "destination": w.destination,
        "status": w.status.value,
        "payout_hash": w.payout_hash,
        "payout_currency": w.payout_currency,
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "processed_at": w.processed_at.isoformat() if w.processed_at else None
    } for w in withdrawals]


@router.get("/ledger")
async def my_ledger(
    account: str = Query("balance", pattern="^(balance|pending)$"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """The current user's append-only balance history (newest first)."""
    rows = (await db.execute(
        select(LedgerEntry)
        .where(LedgerEntry.user_id == current_user.id, LedgerEntry.account == account)
        .order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc())
        .limit(limit)
    )).scalars().all()
    return [
        {
            "id": e.id,
            "amount": e.amount,
            "balance_after": e.balance_after,
            "entry_type": e.entry_type,
            "ref_type": e.ref_type,
            "ref_id": e.ref_id,
            "description": e.description,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in rows
    ]


@router.delete("/withdrawals/{withdrawal_id}")
async def cancel_withdrawal(
    withdrawal_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Cancel a pending withdrawal request (refunds to balance)"""
    # Lock the withdrawal row so the PENDING check below runs under the lock; a
    # concurrent cancel (or an admin reject) otherwise both pass an unlocked check
    # and refund the balance twice. Lock order (withdrawal row, then user row)
    # matches reject_withdrawal to avoid deadlocks.
    result = await db.execute(
        select(WithdrawalRequest)
        .where(
            WithdrawalRequest.id == withdrawal_id,
            WithdrawalRequest.user_id == current_user.id
        )
        .with_for_update()
    )
    withdrawal = result.scalar_one_or_none()

    if not withdrawal:
        raise HTTPException(status_code=404, detail="Withdrawal not found")

    if withdrawal.status != WithdrawalStatus.PENDING:
        raise HTTPException(status_code=400, detail="Can only cancel pending withdrawals")

    # Lock user row
    user_result = await db.execute(
        select(User).where(User.id == current_user.id).with_for_update()
    )
    user = user_result.scalar_one()
    
    # Refund to balance
    record_balance_change(
        db, user, delta=withdrawal.amount, entry_type="withdrawal_cancel_refund",
        ref_type="withdrawal_request", ref_id=withdrawal.id,
        description="Withdrawal cancelled by user — refund",
    )

    # Mark as rejected/cancelled
    withdrawal.status = WithdrawalStatus.REJECTED
    withdrawal.processed_at = datetime.utcnow()
    withdrawal.admin_note = "Cancelled by user"

    audit_logger.info(
        f"WITHDRAW_CANCEL: User {user.id} cancelled ${withdrawal.amount:.2f} withdrawal. "
        f"Refunded to balance. New balance: ${user.balance:.2f}"
    )

    await commit_and_broadcast(db)
    
    return {
        "message": "Withdrawal cancelled and refunded to balance",
        "balance": user.balance
    }

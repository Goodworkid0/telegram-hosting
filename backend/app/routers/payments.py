"""Payments Router (NowPayments)"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import os
import json
import hmac
import hashlib
import httpx
from datetime import datetime

from app.database import get_db
from app.auth import get_current_active_user, block_if_impersonating
from app.models import User, CryptoDeposit, AppSettings
from app.ledger import record_balance_change, commit_and_broadcast
from app.money import to_money
from app.telegram import create_notification
from app.schemas import CreateCryptoDeposit, CryptoDepositResponse, CryptoDepositStatus, CryptoDepositItem, CoinInfo
from app.nowpayments import (
    fetch_available_coins, fetch_min_usd, coin_display, resolve_enabled, DEFAULT_COINS,
)

from app.dependencies import limiter

router = APIRouter()

NOWPAYMENTS_API_KEY = os.getenv("NOWPAYMENTS_API_KEY", "")
NOWPAYMENTS_IPN_SECRET = os.getenv("NOWPAYMENTS_IPN_SECRET", "")
NOWPAYMENTS_BASE_URL = os.getenv("NOWPAYMENTS_BASE_URL", "https://api.nowpayments.io/v1")
NOWPAYMENTS_IPN_URL = os.getenv("NOWPAYMENTS_IPN_URL", "")

async def _get_settings(db: AsyncSession):
    result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
    return result.scalar_one_or_none()


async def _resolve_enabled_coins(db: AsyncSession) -> list[str]:
    """The deposit coins currently offered: admin-curated set ∩ account-available."""
    available = await fetch_available_coins()
    settings = await _get_settings(db)
    curated_csv = settings.enabled_deposit_coins if settings else None
    return resolve_enabled(curated_csv, available)


def _verify_signature(raw_body: bytes, signature: str) -> bool:
    if not NOWPAYMENTS_IPN_SECRET or not signature:
        return False
    expected = hmac.new(
        NOWPAYMENTS_IPN_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.get("/nowpayments/currencies", response_model=list[CoinInfo])
async def list_deposit_currencies(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Deposit coins offered to users: the admin-curated set, enriched with
    display metadata and each coin's USD minimum (best-effort)."""
    enabled = await _resolve_enabled_coins(db)
    out = []
    for code in enabled:
        info = coin_display(code)
        info["min_usd"] = await fetch_min_usd(code)
        out.append(info)
    return out


@router.post("/nowpayments/create", response_model=CryptoDepositResponse)
async def create_nowpayments_deposit(
    payload: CreateCryptoDeposit,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    if not NOWPAYMENTS_API_KEY:
        raise HTTPException(status_code=500, detail="NOWPAYMENTS_API_KEY not set")
    if not NOWPAYMENTS_IPN_URL:
        raise HTTPException(status_code=500, detail="NOWPAYMENTS_IPN_URL not set")

    pay_currency = payload.pay_currency.strip().lower()
    enabled = await _resolve_enabled_coins(db)
    if pay_currency not in enabled:
        raise HTTPException(status_code=400, detail="Unsupported currency")

    settings = await _get_settings(db)
    global_min = float(settings.min_deposit_amount) if settings and settings.min_deposit_amount else 10.0
    coin_min = await fetch_min_usd(pay_currency)
    effective_min = max(global_min, coin_min or 0.0)
    if payload.amount < effective_min:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum deposit for {pay_currency.upper()} is ${effective_min:.2f}",
        )

    deposit = CryptoDeposit(
        user_id=current_user.id,
        price_amount=payload.amount,
        price_currency="usd",
        price_amount_usd=payload.amount,
        payment_status="created"
    )
    db.add(deposit)
    # Flush (not commit) to obtain the autoincrement id, then stamp order_id
    # BEFORE persisting so the row is never committed without one. Otherwise a
    # failed provider call below would leave an order_id-less row that breaks the
    # admin deposits list.
    await db.flush()
    order_id = f"dep_{deposit.id}"
    deposit.order_id = order_id
    await db.commit()
    await db.refresh(deposit)

    req_payload = {
        "price_amount": payload.amount,
        "price_currency": "usd",
        "pay_currency": pay_currency,
        "ipn_callback_url": NOWPAYMENTS_IPN_URL,
        "order_id": order_id,
        "order_description": "Wallet deposit"
    }
    headers = {
        "x-api-key": NOWPAYMENTS_API_KEY,
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(f"{NOWPAYMENTS_BASE_URL}/payment", json=req_payload, headers=headers)

    if resp.status_code not in (200, 201):
        deposit.payment_status = "error"
        await db.commit()
        error_detail = "NowPayments create failed"
        try:
            err_data = resp.json()
            error_detail = err_data.get("message") or err_data.get("description") or str(err_data)
            import logging
            logging.getLogger(__name__).error(f"NowPayments error ({resp.status_code}): {err_data}")
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=error_detail)

    data = resp.json()
    deposit.payment_id = data.get("payment_id")
    deposit.pay_address = data.get("pay_address")
    deposit.pay_amount = data.get("pay_amount")
    deposit.pay_currency = data.get("pay_currency")
    deposit.payment_status = data.get("payment_status") or deposit.payment_status

    await db.commit()
    await db.refresh(deposit)

    return CryptoDepositResponse(
        deposit_id=deposit.id,
        payment_id=deposit.payment_id,
        pay_address=deposit.pay_address,
        pay_amount=deposit.pay_amount,
        pay_currency=deposit.pay_currency,
        payment_status=deposit.payment_status,
        price_amount_usd=deposit.price_amount_usd
    )


@router.post("/nowpayments/webhook")
@limiter.exempt
async def nowpayments_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    # Exempt from rate limiting: IPNs arrive in bursts from NOWPayments' small
    # IP pool and are HMAC-verified below — throttling them drops real payments.
    raw = await request.body()
    signature = request.headers.get("x-nowpayments-sig", "")
    if not _verify_signature(raw, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid payload")

    payment_id = str(payload.get("payment_id") or "")
    order_id = payload.get("order_id")

    query = None
    if payment_id:
        query = select(CryptoDeposit).where(CryptoDeposit.payment_id == payment_id).with_for_update()
    elif order_id:
        query = select(CryptoDeposit).where(CryptoDeposit.order_id == order_id).with_for_update()
    else:
        raise HTTPException(status_code=400, detail="Missing payment identifiers")

    result = await db.execute(query)
    deposit = result.scalar_one_or_none()
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")

    deposit.payment_status = payload.get("payment_status") or deposit.payment_status
    deposit.pay_address = payload.get("pay_address") or deposit.pay_address
    deposit.pay_amount = payload.get("pay_amount") or deposit.pay_amount
    deposit.pay_currency = payload.get("pay_currency") or deposit.pay_currency
    deposit.tx_hash = payload.get("payin_hash") or deposit.tx_hash
    deposit.confirmations = payload.get("confirmations") or deposit.confirmations

    if deposit.payment_status in {"confirmed", "finished"} and not deposit.is_credited:
        # Credit based on what was ACTUALLY paid, never the user-requested USD.
        # NowPayments can mark a payment confirmed/finished for less crypto than was
        # invoiced (underpayment); crediting the requested amount would let a user
        # order $10,000, send $10 of crypto, and be credited $10,000. Scale the USD
        # credit by (actually_paid / pay_amount), capped at the requested amount.
        import logging
        audit = logging.getLogger("audit")

        def _to_float(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return 0.0

        actually_paid = _to_float(payload.get("actually_paid"))
        expected_pay = _to_float(payload.get("pay_amount")) or _to_float(deposit.pay_amount)

        if actually_paid <= 0 or expected_pay <= 0:
            # Settled crypto amount is unknown — refuse to credit and flag for review
            # rather than trusting the user-supplied invoice amount.
            deposit.payment_status = "needs_review"
            audit.warning(
                "deposit.credit.unverifiable deposit_id=%s payment_id=%s actually_paid=%s pay_amount=%s",
                deposit.id, deposit.payment_id, actually_paid, expected_pay,
            )
            await db.commit()
            return {"status": "ok"}

        paid_ratio = actually_paid / expected_pay
        requested_usd = to_money(deposit.price_amount_usd)
        # Cap at the invoiced amount — overpayment doesn't credit extra (handled
        # manually). Underpayment credits proportionally to what actually arrived.
        base_amount = to_money(float(requested_usd) * min(paid_ratio, 1.0))

        if base_amount <= 0:
            deposit.payment_status = "needs_review"
            audit.warning(
                "deposit.credit.zero_after_scaling deposit_id=%s requested=%s ratio=%s",
                deposit.id, requested_usd, paid_ratio,
            )
            await db.commit()
            return {"status": "ok"}

        if paid_ratio < 0.99:
            audit.warning(
                "deposit.credit.underpaid deposit_id=%s requested=%s credited=%s ratio=%s",
                deposit.id, requested_usd, base_amount, paid_ratio,
            )

        # Lock user row to prevent race conditions on balance update
        result = await db.execute(
            select(User).where(User.id == deposit.user_id).with_for_update()
        )
        user = result.scalar_one_or_none()
        if user:
            record_balance_change(
                db, user, delta=base_amount, entry_type="deposit",
                ref_type="crypto_deposit", ref_id=deposit.id,
                description=f"Crypto deposit ({deposit.pay_currency or 'crypto'})",
            )
            deposit.is_credited = True
            deposit.completed_at = datetime.utcnow()
            
            await create_notification(
                db, user_id=user.id, type="deposit_credited",
                title=f"Deposit of ${base_amount:.2f} credited",
                body=f"Your {deposit.pay_currency.upper() if deposit.pay_currency else 'crypto'} deposit has been confirmed.",
                link="/wallet", telegram_id=user.telegram_id,
            )

    await commit_and_broadcast(db)
    return {"status": "ok"}


@router.get("/nowpayments/deposits/{deposit_id}", response_model=CryptoDepositStatus)
async def get_nowpayments_deposit_status(
    deposit_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(CryptoDeposit).where(
            CryptoDeposit.id == deposit_id,
            CryptoDeposit.user_id == current_user.id
        )
    )
    deposit = result.scalar_one_or_none()
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")

    return CryptoDepositStatus(
        deposit_id=deposit.id,
        payment_status=deposit.payment_status,
        confirmations=deposit.confirmations or 0,
        pay_address=deposit.pay_address,
        pay_amount=deposit.pay_amount,
        pay_currency=deposit.pay_currency,
        price_amount_usd=deposit.price_amount_usd or 0.0,
        is_credited=deposit.is_credited,
        tx_hash=deposit.tx_hash
    )


@router.get("/nowpayments/deposits", response_model=list[CryptoDepositItem])
async def list_nowpayments_deposits(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(CryptoDeposit)
        .where(CryptoDeposit.user_id == current_user.id)
        .order_by(CryptoDeposit.created_at.desc())
    )
    deposits = result.scalars().all()
    return [
        CryptoDepositItem(
            deposit_id=dep.id,
            payment_status=dep.payment_status,
            confirmations=dep.confirmations or 0,
            pay_amount=dep.pay_amount,
            pay_currency=dep.pay_currency,
            price_amount_usd=dep.price_amount_usd or 0.0,
            is_credited=dep.is_credited,
            tx_hash=dep.tx_hash,
            created_at=dep.created_at
        )
        for dep in deposits
    ]


# ============ Subscription ============

@router.post("/subscription/purchase")
async def purchase_subscription(
    current_user: User = Depends(block_if_impersonating),
    db: AsyncSession = Depends(get_db),
):
    """Buy (or extend) the 30-day unlimited-downloads subscription from balance.

    Stacks: buying while active extends from the current expiry, so renewing
    early never loses days. Expiry is enforced lazily at download time.
    """
    from datetime import timedelta
    from app.pricing import get_price
    from app.subscription import SUBSCRIPTION_DAYS
    SUB_PRICE = await get_price(db, "subscription_price")

    # Lock the user row so two concurrent purchases can't double-charge.
    result = await db.execute(
        select(User).where(User.id == current_user.id).with_for_update()
    )
    user = result.scalar_one()

    if to_money(user.balance) < SUB_PRICE:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient balance. Need ${SUB_PRICE}, have ${user.balance:.2f}"
        )

    record_balance_change(
        db, user, delta=-SUB_PRICE, entry_type="subscription_purchase",
        description=f"{SUBSCRIPTION_DAYS}-day subscription",
    )

    now = datetime.utcnow()
    base = user.premium_until if (user.is_premium and user.premium_until and user.premium_until > now) else now
    user.premium_until = base + timedelta(days=SUBSCRIPTION_DAYS)
    user.is_premium = True

    await create_notification(
        db,
        user_id=user.id,
        type="subscription_purchase",
        title="Subscription active!",
        body=f"Unlimited downloads until {user.premium_until.strftime('%Y-%m-%d %H:%M')} UTC.",
        link="/shop",
    )

    await commit_and_broadcast(db)

    return {
        "message": "Subscription activated",
        "is_premium": True,
        "premium_until": user.premium_until.isoformat(),
        "balance": float(user.balance),
    }

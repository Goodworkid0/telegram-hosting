"""Append-only money ledger.

`record_balance_change` is the single funnel for every change to a user's
spendable `balance` or escrow `pending_balance`: it applies the delta to the
in-session User object AND appends an immutable LedgerEntry, so the two always
move together. The caller is responsible for committing (and for holding the
appropriate row lock — same as before).

Invariant: for any (user, account), SUM(LedgerEntry.amount) == current balance.
`reconcile_user` checks it.
"""
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, LedgerEntry
from app.money import to_money, ZERO

ACCOUNT_BALANCE = "balance"
ACCOUNT_PENDING = "pending"

# Map the logical account name -> the User attribute it writes.
_ACCOUNT_ATTR = {
    ACCOUNT_BALANCE: "balance",
    ACCOUNT_PENDING: "pending_balance",
}


def record_balance_change(
    db: AsyncSession,
    user: User,
    *,
    delta: float,
    entry_type: str,
    account: str = ACCOUNT_BALANCE,
    ref_type: str | None = None,
    ref_id: int | None = None,
    description: str | None = None,
    clamp_zero: bool = False,
) -> float:
    """Apply `delta` to user's `account` and append a ledger row. Returns the
    new account value.

    - `delta`: signed amount (credit > 0, debit < 0).
    - `clamp_zero`: if applying the delta would go below 0, clamp to 0 and record
      the *effective* (clamped) delta — used for the escrow pending account.
    The ledger row is added to the session; the caller commits.
    """
    if account not in _ACCOUNT_ATTR:
        raise ValueError(f"unknown ledger account: {account!r}")
    attr = _ACCOUNT_ATTR[account]

    current = to_money(getattr(user, attr))
    new = current + to_money(delta)
    if clamp_zero and new < ZERO:
        new = ZERO
    effective = new - current

    setattr(user, attr, new)
    db.add(LedgerEntry(
        user_id=user.id,
        account=account,
        amount=effective,
        balance_after=new,
        entry_type=entry_type,
        ref_type=ref_type,
        ref_id=ref_id,
        description=description,
        created_at=datetime.utcnow(),
    ))
    # Track spendable-balance changes so commit_and_broadcast() can push an SSE
    # balance update to every affected user after the transaction commits. Only
    # the `balance` account is user-visible spendable money; pending-only moves
    # don't change what the wallet shows, so they're not tracked here.
    if account == ACCOUNT_BALANCE:
        db.info.setdefault("_balance_dirty", {})[user.id] = user
    return new


async def commit_and_broadcast(db: AsyncSession) -> None:
    """Commit the session, then push an SSE balance update for every user whose
    spendable balance changed during it.

    This is the single place balance broadcasts should happen: call it instead of
    `await db.commit()` in any endpoint that may have called record_balance_change
    on the `balance` account. Broadcasting strictly AFTER commit guarantees we
    never announce a balance that a rollback would have undone. Safe to call when
    nothing changed (it just commits). Idempotent re: the dirty set — it clears it.
    """
    dirty = db.info.get("_balance_dirty")
    await db.commit()
    if dirty:
        # expire_on_commit=False keeps user.balance valid (committed value) here.
        from app.redis_client import broadcast_balance_update
        for user in dirty.values():
            await broadcast_balance_update(user.id, user.balance)
        dirty.clear()


async def reconcile_user(db: AsyncSession, user_id: int, account: str = ACCOUNT_BALANCE) -> dict:
    """Verify SUM(ledger.amount) == current balance for a (user, account)."""
    attr = _ACCOUNT_ATTR[account]
    user = await db.get(User, user_id)
    if not user:
        return {"user_id": user_id, "account": account, "found": False}

    raw_sum = await db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
            LedgerEntry.user_id == user_id,
            LedgerEntry.account == account,
        )
    )
    ledger_sum = to_money(raw_sum)
    current = to_money(getattr(user, attr))
    drift = current - ledger_sum
    return {
        "user_id": user_id,
        "account": account,
        "found": True,
        "balance": float(current),
        "ledger_sum": float(ledger_sum),
        "drift": float(drift),
        # With Decimal money this should be exactly 0.
        "consistent": drift == ZERO,
    }

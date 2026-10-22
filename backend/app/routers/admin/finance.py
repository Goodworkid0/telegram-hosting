"""Admin: finance endpoints (split from admin.py)."""
from app.routers.admin.common import *  # noqa: F401,F403

router = APIRouter()


class WithdrawalListResponse(BaseModel):
    items: List[WithdrawalRequestResponse]
    total: int
    pending_count: int



@router.get("/withdrawals", response_model=WithdrawalListResponse)
async def get_withdrawals(
    status: Optional[WithdrawalStatus] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get withdrawal requests"""
    query = select(WithdrawalRequest).options(selectinload(WithdrawalRequest.user))
    count_query = select(func.count(WithdrawalRequest.id))
    
    if status:
        query = query.where(WithdrawalRequest.status == status)
        count_query = count_query.where(WithdrawalRequest.status == status)
    
    total = await db.scalar(count_query) or 0
    pending_count = await db.scalar(
        select(func.count(WithdrawalRequest.id))
        .where(WithdrawalRequest.status == WithdrawalStatus.PENDING)
    ) or 0
    
    query = query.order_by(WithdrawalRequest.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    withdrawals = result.scalars().all()
    
    return WithdrawalListResponse(
        items=[
            WithdrawalRequestResponse(
                id=w.id,
                user_id=w.user_id,
                username=w.user.username if w.user else None,
                amount=w.amount,
                crypto_address=w.destination,
                crypto_network=w.payout_currency,
                status=w.status,
                admin_notes=w.admin_note,
                created_at=w.created_at,
                processed_at=w.processed_at,
            )
            for w in withdrawals
        ],
        total=total,
        pending_count=pending_count,
    )



@router.put("/withdrawals/{withdrawal_id}/approve", response_model=SuccessResponse)
async def approve_withdrawal(
    withdrawal_id: int,
    tx_hash: Optional[str] = Query(None),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Approve a withdrawal request"""
    # Lock the row so approve can't race reject/cancel into a double-process.
    result = await db.execute(
        select(WithdrawalRequest).where(WithdrawalRequest.id == withdrawal_id).with_for_update()
    )
    withdrawal = result.scalar_one_or_none()

    if not withdrawal:
        raise HTTPException(status_code=404, detail="Withdrawal not found")

    if withdrawal.status != WithdrawalStatus.PENDING:
        raise HTTPException(status_code=400, detail="Withdrawal already processed")

    withdrawal.status = WithdrawalStatus.APPROVED
    withdrawal.processed_at = datetime.utcnow()
    withdrawal.processed_by_id = current_user.id
    withdrawal.payout_hash = tx_hash or withdrawal.payout_hash

    # Audit the approval — this is the most financially sensitive admin action and
    # previously left no record of which admin approved the payout.
    mod_action = ModAction(
        moderator_id=current_user.id,
        target_user_id=withdrawal.user_id,
        action_type="withdrawal_approved",
        reason=f"Approved withdrawal #{withdrawal.id} of ${withdrawal.amount:.2f}",
        details=f"tx_hash={tx_hash}" if tx_hash else None,
    )
    db.add(mod_action)

    await create_notification(
        db, user_id=withdrawal.user_id, type="withdrawal_approved",
        title="Withdrawal Approved",
        body=f"Your withdrawal of ${withdrawal.amount:.2f} has been approved.",
        link="/wallet",
    )

    await db.commit()
    return SuccessResponse(message="Withdrawal approved")



@router.put("/withdrawals/{withdrawal_id}/reject", response_model=SuccessResponse)
async def reject_withdrawal(
    withdrawal_id: int,
    reason: str = Query(...),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Reject a withdrawal request and refund balance"""
    # Lock the row so reject can't race approve/cancel into a double-process
    # (which would refund the balance while the payout is also marked approved).
    result = await db.execute(
        select(WithdrawalRequest)
        .where(WithdrawalRequest.id == withdrawal_id)
        .with_for_update()
    )
    withdrawal = result.scalar_one_or_none()

    if not withdrawal:
        raise HTTPException(status_code=404, detail="Withdrawal not found")

    if withdrawal.status != WithdrawalStatus.PENDING:
        raise HTTPException(status_code=400, detail="Withdrawal already processed")
    
    # Lock user row for refund
    user_result = await db.execute(
        select(User).where(User.id == withdrawal.user_id).with_for_update()
    )
    user = user_result.scalar_one()
    record_balance_change(
        db, user, delta=withdrawal.amount, entry_type="withdrawal_reject_refund",
        ref_type="withdrawal_request", ref_id=withdrawal.id,
        description=f"Withdrawal rejected by admin — refund ({reason})" if reason else "Withdrawal rejected — refund",
    )

    withdrawal.status = WithdrawalStatus.REJECTED
    withdrawal.processed_at = datetime.utcnow()
    withdrawal.processed_by_id = current_user.id
    withdrawal.admin_note = reason
    
    await create_notification(
        db, user_id=withdrawal.user_id, type="withdrawal_rejected",
        title="Withdrawal Rejected",
        body=f"Your withdrawal was rejected: {reason}. ${withdrawal.amount:.2f} has been refunded.",
        link="/wallet",
    )

    await commit_and_broadcast(db)
    return SuccessResponse(message="Withdrawal rejected and balance refunded")



class DepositItem(BaseModel):
    id: int
    user_id: int
    username: Optional[str] = None
    # Nullable: a deposit row exists from the moment an address is requested, but
    # order_id is only assigned once the provider call succeeds. Failed/abandoned
    # attempts can leave it null, so the admin list must tolerate that.
    order_id: Optional[str] = None
    payment_id: Optional[str] = None
    pay_currency: Optional[str] = None
    payment_status: Optional[str] = None
    tx_hash: Optional[str] = None
    price_amount: float
    price_amount_usd: float
    is_credited: bool
    credited_usd_amount: float
    created_at: datetime
    credited_at: Optional[datetime] = None



class DepositListResponse(BaseModel):
    items: List[DepositItem]
    total: int



@router.get("/deposits", response_model=DepositListResponse)
async def get_deposits(
    credited: Optional[bool] = Query(None),
    status: Optional[str] = Query(None, description="Filter by raw payment_status (e.g. needs_review)"),
    search: Optional[str] = Query(None, description="Filter by username or user id"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get crypto deposits (full history, newest first), with the user behind each."""
    query = select(CryptoDeposit).options(selectinload(CryptoDeposit.user))
    count_query = select(func.count(CryptoDeposit.id))

    if credited is not None:
        query = query.where(CryptoDeposit.is_credited == credited)
        count_query = count_query.where(CryptoDeposit.is_credited == credited)

    if status:
        query = query.where(CryptoDeposit.payment_status == status)
        count_query = count_query.where(CryptoDeposit.payment_status == status)

    if search:
        term = search.strip()
        if term:
            # Match a numeric user id exactly, or a username substring.
            cond = User.username.ilike(f"%{term}%")
            if term.isdigit():
                cond = (User.id == int(term)) | cond
            query = query.join(User, CryptoDeposit.user_id == User.id).where(cond)
            count_query = count_query.join(User, CryptoDeposit.user_id == User.id).where(cond)

    total = await db.scalar(count_query) or 0
    
    query = query.order_by(CryptoDeposit.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    deposits = result.scalars().all()
    
    return DepositListResponse(
        items=[
            DepositItem(
                id=d.id,
                user_id=d.user_id,
                username=d.user.username if d.user else None,
                order_id=d.order_id,
                payment_id=d.payment_id,
                pay_currency=d.pay_currency,
                payment_status=d.payment_status,
                tx_hash=d.tx_hash,
                price_amount=d.price_amount or 0,
                price_amount_usd=d.price_amount_usd or 0,
                is_credited=d.is_credited or False,
                credited_usd_amount=d.price_amount_usd or 0,
                created_at=d.created_at,
                credited_at=d.completed_at,
            )
            for d in deposits
        ],
        total=total,
    )


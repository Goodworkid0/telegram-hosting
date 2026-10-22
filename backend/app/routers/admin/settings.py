"""Admin: settings endpoints (split from admin.py)."""
from app.routers.admin.common import *  # noqa: F401,F403

router = APIRouter()


class AppSettingsSchema(BaseModel):
    # Branding
    app_name: Optional[str] = None
    logo_url: Optional[str] = None
    show_logo: Optional[bool] = None
    bot_username: Optional[str] = None
    maintenance_mode: Optional[bool] = None

    # Links
    announcements_url: Optional[str] = None
    official_group_url: Optional[str] = None

    # Hosting settings
    subscription_price: Optional[float] = None
    platform_fee_percent: Optional[float] = None
    free_downloads_per_day: Optional[int] = None
    min_uploads_for_rep: Optional[int] = None

    # Payments — curated deposit coins (CSV of NOWPayments tickers)
    enabled_deposit_coins: Optional[str] = None

    # Fees / limits
    withdrawal_fee_percent: Optional[float] = None
    min_deposit_amount: Optional[float] = None
    min_withdrawal_amount: Optional[float] = None

    # Support
    support_username: Optional[str] = None
    support_display_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)



@router.get("/settings", response_model=AppSettingsSchema)
async def get_settings(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get app settings"""
    result = await db.execute(select(AppSettings).limit(1))
    settings = result.scalar_one_or_none()
    
    if not settings:
        settings = AppSettings()
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    
    return settings



@router.get("/payment-coins")
async def get_payment_coins(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """List every coin available on the NOWPayments account, flagged with whether
    it's currently enabled for deposits. Used by the admin coin-toggle UI.

    ``fallback`` is true when the live account list couldn't be fetched (no API
    key / upstream error) and the legacy default set is shown instead.
    """
    from app.nowpayments import fetch_available_coins, coin_display, resolve_enabled, DEFAULT_COINS

    available = await fetch_available_coins()
    result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
    settings = result.scalar_one_or_none()
    curated_csv = settings.enabled_deposit_coins if settings else None

    enabled = set(resolve_enabled(curated_csv, available))
    coins = available if available is not None else list(DEFAULT_COINS)
    return {
        "fallback": available is None,
        "coins": [
            {**coin_display(c), "enabled": c in enabled}
            for c in sorted(coins)
        ],
    }


@router.put("/settings", response_model=AppSettingsSchema)
async def update_settings(
    data: AppSettingsSchema,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update app settings"""
    result = await db.execute(select(AppSettings).limit(1))
    settings = result.scalar_one_or_none()
    
    if not settings:
        settings = AppSettings()
        db.add(settings)
    
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
    
    await db.commit()
    await db.refresh(settings)
    return settings


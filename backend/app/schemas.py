"""Pydantic Schemas for the Hosting Platform"""
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Optional, List
from datetime import datetime
from app.models import UserRole


# Staff (moderators/admins) always get subscription perks. Applied at the
# serialization boundary so it covers every endpoint — both the ones that build
# a response manually and the ones that serialize the ORM model via
# from_attributes. The stored is_premium column is untouched.
_STAFF_ROLES = (UserRole.MODERATOR, UserRole.ADMIN)


def _apply_staff_premium(model):
    if not model.is_premium and model.role in _STAFF_ROLES:
        model.is_premium = True
    return model


# ============================================================================
# AUTH SCHEMAS
# ============================================================================

class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"


# ============================================================================
# USER SCHEMAS
# ============================================================================

class UserContactUpdate(BaseModel):
    """Update profile info. Display name (first_name) is set at onboarding."""
    profile_bio: Optional[str] = Field(None, max_length=2000)
    profile_theme: Optional[str] = None  # JSON: {avatar_border, name_color, avatar_glow}
    notification_preferences: Optional[dict] = None
    show_telegram: Optional[bool] = None


class UserResponse(BaseModel):
    id: int
    telegram_id: str
    username: Optional[str] = None
    first_name: Optional[str] = None
    avatar_url: Optional[str] = None
    role: UserRole
    is_active: bool = True
    is_banned: bool = False
    ban_reason: Optional[str] = None
    is_muted: bool = False
    mute_reason: Optional[str] = None
    mute_expires_at: Optional[datetime] = None

    # Balance
    balance: float = 0.0
    pending_balance: float = 0.0

    # Stats
    rep_positive: int = 0
    rep_negative: int = 0

    # Profile
    profile_banner_url: Optional[str] = None
    profile_bio: Optional[str] = None
    profile_theme: Optional[str] = None
    notification_preferences: Optional[dict] = None
    show_telegram: bool = True

    # Timestamps
    created_at: datetime
    last_seen_at: Optional[datetime] = None

    # Subscription
    is_premium: bool = False
    premium_until: Optional[datetime] = None

    # Account setup
    is_setup_complete: bool = False

    @field_validator('is_banned', mode='before')
    @classmethod
    def default_is_banned(cls, v):
        return v if v is not None else False

    @field_validator('notification_preferences', mode='before')
    @classmethod
    def parse_notification_preferences(cls, v):
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return None
        return v

    @field_validator('rep_positive', 'rep_negative', mode='before')
    @classmethod
    def default_int(cls, v):
        return v if v is not None else 0

    @model_validator(mode='after')
    def _staff_premium(self):
        return _apply_staff_premium(self)

    model_config = ConfigDict(from_attributes=True)


class UserPublicProfile(BaseModel):
    """Public profile view (for other users viewing)"""
    id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    avatar_url: Optional[str] = None
    role: UserRole

    # Stats
    rep_positive: int = 0
    rep_negative: int = 0
    upload_count: int = 0
    download_count: int = 0

    # Profile
    profile_banner_url: Optional[str] = None
    profile_bio: Optional[str] = None
    profile_theme: Optional[str] = None  # name color / avatar border (JSON)
    show_telegram: bool = True

    # Recent activity
    last_seen_at: Optional[datetime] = None
    created_at: datetime

    # Subscription
    is_premium: bool = False

    # Follow status (for current user)
    is_following: bool = False
    follower_count: int = 0
    following_count: int = 0

    # Moderation state (for staff viewing the profile)
    is_banned: bool = False
    is_muted: bool = False

    @model_validator(mode='after')
    def _staff_premium(self):
        return _apply_staff_premium(self)

    model_config = ConfigDict(from_attributes=True)


class UserMinimal(BaseModel):
    """Minimal user info for embeds"""
    id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    avatar_url: Optional[str] = None
    role: UserRole
    rep_positive: int = 0
    rep_negative: int = 0
    created_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    profile_theme: Optional[str] = None
    show_telegram: bool = True
    is_premium: bool = False
    premium_until: Optional[datetime] = None
    is_banned: bool = False
    is_muted: bool = False

    @model_validator(mode='after')
    def _staff_premium(self):
        return _apply_staff_premium(self)

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# REPUTATION SCHEMAS
# ============================================================================

class ReputationCreate(BaseModel):
    is_positive: bool
    comment: Optional[str] = Field(None, max_length=200)


class ReputationResponse(BaseModel):
    id: int
    is_positive: bool
    comment: Optional[str] = None
    created_at: datetime

    from_user: UserMinimal

    model_config = ConfigDict(from_attributes=True)


class ReputationListResponse(BaseModel):
    entries: List[ReputationResponse]
    total_positive: int
    total_negative: int


# ============================================================================
# NOTIFICATION SCHEMAS
# ============================================================================

class NotificationResponse(BaseModel):
    id: int
    type: str
    title: str
    body: Optional[str] = None
    link: Optional[str] = None
    is_read: bool = False
    created_at: datetime

    related_user: Optional[UserMinimal] = None

    model_config = ConfigDict(from_attributes=True)


class WithdrawalRequestResponse(BaseModel):
    """Admin withdrawal response with more details. Manually constructed — field names intentionally differ from model."""
    id: int
    user_id: int
    username: Optional[str] = None
    amount: float
    crypto_address: str
    crypto_network: Optional[str] = None
    status: str
    admin_notes: Optional[str] = None
    created_at: datetime
    processed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=False)


# ============================================================================
# ADMIN SCHEMAS
# ============================================================================

class ModActionResponse(BaseModel):
    id: int
    action_type: str
    reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    expires_at: Optional[datetime] = None

    moderator_id: Optional[int] = None
    moderator: UserMinimal
    target_user_id: Optional[int] = None
    target_user: Optional[UserMinimal] = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# GENERIC SCHEMAS
# ============================================================================

class SuccessResponse(BaseModel):
    success: bool = True
    message: Optional[str] = None


# ============================================================================
# CRYPTO DEPOSIT SCHEMAS
# ============================================================================

class CreateCryptoDeposit(BaseModel):
    # Bounded to a sane range. The lower bound also stops negative/zero amounts
    # from reaching the credit path; the upper bound keeps price_amount within the
    # Numeric(14,2) money column and avoids absurd invoices.
    amount: float = Field(gt=0, le=1_000_000)
    pay_currency: str


class CoinInfo(BaseModel):
    """A deposit coin offered to users (resolved from the admin-curated set)."""
    currency: str
    symbol: str
    name: str
    network: str
    min_usd: Optional[float] = None


class CryptoDepositResponse(BaseModel):
    deposit_id: int
    payment_id: Optional[str] = None
    pay_address: Optional[str] = None
    pay_amount: Optional[float] = None
    pay_currency: Optional[str] = None
    payment_status: str
    price_amount_usd: float


class CryptoDepositStatus(BaseModel):
    deposit_id: int
    payment_status: str
    confirmations: int = 0
    pay_address: Optional[str] = None
    pay_amount: Optional[float] = None
    pay_currency: Optional[str] = None
    price_amount_usd: float = 0.0
    is_credited: bool = False
    tx_hash: Optional[str] = None


class CryptoDepositItem(BaseModel):
    deposit_id: int
    payment_status: str
    confirmations: int = 0
    pay_amount: Optional[float] = None
    pay_currency: Optional[str] = None
    price_amount_usd: float = 0.0
    is_credited: bool = False
    tx_hash: Optional[str] = None
    created_at: datetime


# ============================================================================
# SHARED FILES (bot file board)
# ============================================================================

class SharedFileResponse(BaseModel):
    id: int
    kind: str
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    caption: Optional[str] = None
    uploader: Optional[UserMinimal] = None
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    suggested_category_id: Optional[int] = None
    suggested_category_name: Optional[str] = None
    download_count: int = 0
    created_at: Optional[datetime] = None
    # Paywall
    price: Optional[float] = None       # None/0 = free download
    purchase_count: int = 0
    is_purchased: bool = False          # viewer has bought this file
    is_own: bool = False                # viewer uploaded this file
    # Admin/owner-only fields (populated only on the ACP queue + /mine endpoints).
    status: Optional[str] = None
    reject_reason: Optional[str] = None


class SharedFileRejectRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=300)


class SharedFileApproveRequest(BaseModel):
    category_id: Optional[int] = None


class SharedFileCategoryRequest(BaseModel):
    category_id: Optional[int] = None


class FilePriceUpdate(BaseModel):
    """Uploader sets/clears the one-time purchase price of their file."""
    price: Optional[float] = Field(None, ge=0, le=100_000)


class FileQuotaResponse(BaseModel):
    """Free-tier daily download quota state for the current user."""
    used_today: int = 0
    limit: int = 5
    subscription_active: bool = False
    premium_until: Optional[datetime] = None


class FileCategoryResponse(BaseModel):
    id: int
    name: str
    sort_order: int = 0
    is_active: bool = True
    file_count: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class FileCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    sort_order: int = 0


class FileCategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


UserResponse.model_rebuild()
UserPublicProfile.model_rebuild()
UserMinimal.model_rebuild()
SharedFileResponse.model_rebuild()

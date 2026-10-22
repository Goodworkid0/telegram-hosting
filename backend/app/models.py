"""Database Models for the Hosting Platform"""
from sqlalchemy import Column, Integer, BigInteger, String, Float, Numeric, Boolean, DateTime, ForeignKey, Text, Enum as SQLEnum, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.database import Base

# USD money: exact 2-decimal fixed point (SQLAlchemy returns Python Decimal).
# Crypto pay/payout amounts and percentage config stay Float (different precision).
MONEY = Numeric(14, 2)


# ============================================================================
# ENUMS
# ============================================================================

class UserRole(str, enum.Enum):
    """User roles with increasing permissions"""
    USER = "USER"            # Regular users
    MODERATOR = "MODERATOR"  # Moderators
    ADMIN = "ADMIN"          # Full access


class WithdrawalStatus(str, enum.Enum):
    """Withdrawal request states"""
    PENDING = "pending"
    PROCESSING = "processing"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


# ============================================================================
# USER SYSTEM
# ============================================================================

class User(Base):
    """Hosting platform user"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True)
    # Always mirrors the user's Telegram @handle (synced on every login). Unique
    # so a handle can't be squatted via a concurrent login race; NULLs permitted
    # and distinct (users may have no handle). Users can only show/hide it.
    username = Column(String, nullable=True, unique=True, index=True)
    first_name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)

    # Role & Status
    role = Column(SQLEnum(UserRole), default=UserRole.USER)
    is_active = Column(Boolean, default=True)
    is_banned = Column(Boolean, default=False)
    ban_reason = Column(String, nullable=True)
    banned_at = Column(DateTime, nullable=True)
    ban_expires_at = Column(DateTime, nullable=True)
    banned_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_muted = Column(Boolean, default=False)
    mute_reason = Column(String, nullable=True)
    muted_at = Column(DateTime, nullable=True)
    mute_expires_at = Column(DateTime, nullable=True)  # None = permanent
    muted_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Auth
    token_version = Column(Integer, default=0)
    refresh_token_family = Column(String, nullable=True)  # UUID for rotation tracking
    refresh_token_version = Column(Integer, default=0)    # Increments per rotation; -1 = family invalidated

    # Balance
    balance = Column(MONEY, default=0.0)
    pending_balance = Column(MONEY, default=0.0)

    # Reputation
    rep_positive = Column(Integer, default=0)
    rep_negative = Column(Integer, default=0)

    # Profile customization
    profile_banner_url = Column(String, nullable=True)
    profile_theme = Column(Text, nullable=True)       # JSON: custom colors
    profile_bio = Column(Text, nullable=True)         # About me
    notification_preferences = Column(Text, nullable=True)  # JSON notification prefs
    show_telegram = Column(Boolean, default=True)     # Whether to show @username publicly

    # Subscription (unlimited downloads while premium_until is in the future).
    # Expired lazily at download/quota time — no scheduler task.
    is_premium = Column(Boolean, default=False)
    premium_until = Column(DateTime, nullable=True)

    # Account setup
    is_setup_complete = Column(Boolean, default=False)  # User completed onboarding
    pin_hash = Column(String, nullable=True)  # bcrypt hash of access PIN

    # Activity tracking
    last_seen_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    notifications = relationship("Notification", back_populates="user", foreign_keys="Notification.user_id")

    @property
    def account_age_days(self) -> int:
        """Whole days since registration."""
        if not self.created_at:
            return 0
        return (datetime.utcnow() - self.created_at).days

    @property
    def net_reputation(self) -> int:
        """Positive reputation minus negative reputation."""
        return (self.rep_positive or 0) - (self.rep_negative or 0)


class UserFollow(Base):
    """User following system"""
    __tablename__ = "user_follows"
    __table_args__ = (
        UniqueConstraint('follower_id', 'following_id', name='uq_user_follow'),
    )

    id = Column(Integer, primary_key=True, index=True)
    follower_id = Column(Integer, ForeignKey("users.id"), index=True)
    following_id = Column(Integer, ForeignKey("users.id"), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    follower = relationship("User", foreign_keys=[follower_id], backref="following")
    following = relationship("User", foreign_keys=[following_id], backref="followers")


# ============================================================================
# REPUTATION SYSTEM
# ============================================================================

class ReputationEntry(Base):
    """Reputation history (+rep / -rep)"""
    __tablename__ = "reputation_entries"

    id = Column(Integer, primary_key=True, index=True)
    from_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    to_user_id = Column(Integer, ForeignKey("users.id"), index=True)

    is_positive = Column(Boolean, nullable=False)  # True = +rep, False = -rep
    comment = Column(String(200), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])


# ============================================================================
# MODERATION
# ============================================================================

class ModAction(Base):
    """Moderator action log"""
    __tablename__ = "mod_actions"

    id = Column(Integer, primary_key=True, index=True)
    moderator_id = Column(Integer, ForeignKey("users.id"), index=True)
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    action_type = Column(String, nullable=False)  # ban, warn, mute, etc.

    reason = Column(Text, nullable=True)
    details = Column(Text, nullable=True)  # JSON for additional details
    notes = Column(Text, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    moderator = relationship("User", foreign_keys=[moderator_id])
    target_user = relationship("User", foreign_keys=[target_user_id])


# ============================================================================
# NOTIFICATIONS
# ============================================================================

class Notification(Base):
    """User notifications"""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)

    type = Column(String, nullable=False)  # rep, file_approved, file_sold, etc.
    title = Column(String, nullable=False)
    body = Column(Text, nullable=True)
    link = Column(String, nullable=True)

    related_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    is_read = Column(Boolean, default=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="notifications", foreign_keys=[user_id])
    related_user = relationship("User", foreign_keys=[related_user_id])


# ============================================================================
# WALLET & PAYMENTS
# ============================================================================

class CryptoDeposit(Base):
    """Crypto deposit records"""
    __tablename__ = "crypto_deposits"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)

    order_id = Column(String, unique=True, index=True)
    payment_id = Column(String, unique=True, index=True, nullable=True)

    price_amount = Column(MONEY)
    price_currency = Column(String)
    price_amount_usd = Column(MONEY, default=0.0)

    pay_amount = Column(Float, nullable=True)
    pay_currency = Column(String, nullable=True)
    pay_address = Column(String, nullable=True)
    payment_status = Column(String, default="created")
    tx_hash = Column(String, nullable=True)
    confirmations = Column(Integer, default=0)
    is_credited = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User", foreign_keys=[user_id])


class WithdrawalRequest(Base):
    """Withdrawal requests"""
    __tablename__ = "withdrawal_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    # Client-supplied key to make withdrawal submission idempotent (a retried
    # request with the same key returns the original withdrawal instead of
    # creating a second payout).
    idempotency_key = Column(String, nullable=True, unique=True, index=True)

    amount = Column(MONEY, nullable=False)
    destination = Column(String, nullable=True)
    status = Column(SQLEnum(WithdrawalStatus), default=WithdrawalStatus.PENDING)
    admin_note = Column(Text, nullable=True)
    processed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

    # Payout tracking
    payout_hash = Column(String, nullable=True)
    payout_currency = Column(String, default="usdterc20")
    fee_amount = Column(MONEY, default=0.0)
    net_amount = Column(MONEY, nullable=True)

    user = relationship("User", foreign_keys=[user_id])


class LedgerEntry(Base):
    """Append-only ledger of every balance change.

    One immutable row per movement of a user's spendable `balance` or
    `pending` balance. `amount` is the signed effective delta and `balance_after`
    is the account value right after applying it, so the running sum of `amount`
    for a (user, account) must always equal the user's current balance —
    enabling audit and reconciliation. Never UPDATE or DELETE these rows.
    """
    __tablename__ = "ledger_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    # Which account moved: 'balance' (spendable) or 'pending' (hold).
    account = Column(String, default="balance", nullable=False, index=True)
    amount = Column(MONEY, nullable=False)         # signed effective delta
    balance_after = Column(MONEY, nullable=False)  # account value after applying
    entry_type = Column(String, nullable=False, index=True)  # deposit/withdrawal/file_purchase/file_sale/subscription_purchase/...
    ref_type = Column(String, nullable=True)       # e.g. crypto_deposit / withdrawal_request / shared_file
    ref_id = Column(Integer, nullable=True)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        Index("ix_ledger_user_account", "user_id", "account"),
        Index("ix_ledger_ref", "ref_type", "ref_id"),
    )


# ============================================================================
# FILE HOSTING
# ============================================================================

class SharedFileStatus(str, enum.Enum):
    """Moderation state of a user-dropped file on the public file board."""
    PENDING = "PENDING"    # dropped in the bot, awaiting ACP approval
    APPROVED = "APPROVED"  # visible on the board
    REJECTED = "REJECTED"  # hidden (kept in channels as archive)


class FileCategory(Base):
    """Admin-created category files are sorted into at approval time. Files with
    no category show as 'Uncategorized' on the board."""
    __tablename__ = "file_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(80), unique=True, nullable=False)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SharedFile(Base):
    """A file a user dropped into the bot, mirrored to the retrieval + backup
    channels and (once approved) listed on the public file board.

    We never re-host bytes: delivery is the bot re-sending by `file_id`. The
    DURABLE anchor is (retrieval_chat_id, retrieval_message_id) — `file_id` is a
    per-bot cache that can be regenerated by forwarding the channel message if
    the bot token/identity ever changes. `file_unique_id` is the stable dedup
    key (also stable across bots, but not usable to send)."""
    __tablename__ = "shared_files"

    id = Column(Integer, primary_key=True, index=True)

    # Stable dedup key across bots (NOT sendable). Unique so the same file
    # dropped twice doesn't create two board entries.
    file_unique_id = Column(String(128), unique=True, index=True, nullable=False)
    # Current sendable handle for the retrieval bot — regenerable cache.
    file_id = Column(Text, nullable=False)

    kind = Column(String(16), nullable=False, default="document")  # document/photo/video/audio/voice
    category_id = Column(Integer, ForeignKey("file_categories.id"), nullable=True, index=True)  # admin's final assignment
    suggested_category_id = Column(Integer, ForeignKey("file_categories.id"), nullable=True)     # uploader's suggestion
    file_name = Column(String(300), nullable=True)
    mime_type = Column(String(128), nullable=True)
    file_size = Column(BigInteger, nullable=True)  # bytes; BigInteger — a 2GB+ file overflows int4
    caption = Column(Text, nullable=True)

    # Uploader: mapped User when registered, plus the raw tg id for attribution.
    uploader_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    uploader_tg_id = Column(String(32), nullable=True, index=True)

    # Durable anchors in the two channels (message ids never change).
    retrieval_chat_id = Column(String(32), nullable=True)
    retrieval_message_id = Column(Integer, nullable=True)
    backup_chat_id = Column(String(32), nullable=True)
    backup_message_id = Column(Integer, nullable=True)

    status = Column(SQLEnum(SharedFileStatus), default=SharedFileStatus.PENDING, nullable=False, index=True)
    reviewed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    reject_reason = Column(String(300), nullable=True)

    # Paywall: NULL or 0 = free download; > 0 = one-time purchase price set by
    # the uploader. Existing purchases keep access if the price changes later.
    price = Column(MONEY, nullable=True)
    purchase_count = Column(Integer, default=0)

    download_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    uploader = relationship("User", foreign_keys=[uploader_id])
    category = relationship("FileCategory", foreign_keys=[category_id])
    suggested_category = relationship("FileCategory", foreign_keys=[suggested_category_id])


class FilePurchase(Base):
    """One-time purchase of a paywalled file — permanent download access.

    Price/credit/fee are snapshots taken at purchase time so later price or fee
    changes never rewrite history; SUM(uploader_credit) is the uploader's
    earnings for the file."""
    __tablename__ = "file_purchases"
    __table_args__ = (
        UniqueConstraint('buyer_id', 'file_id', name='uq_purchase_buyer_file'),
    )

    id = Column(Integer, primary_key=True, index=True)
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    file_id = Column(Integer, ForeignKey("shared_files.id"), nullable=False, index=True)

    price = Column(MONEY, nullable=False)            # what the buyer paid
    uploader_credit = Column(MONEY, nullable=False)  # what the uploader received
    fee_percent = Column(Float, nullable=False)      # platform fee % applied

    created_at = Column(DateTime, default=datetime.utcnow)

    buyer = relationship("User", foreign_keys=[buyer_id])
    file = relationship("SharedFile", foreign_keys=[file_id])


class FileDownload(Base):
    """Free-quota accounting: one row per quota-counted free-file delivery.
    Own-file, purchased-file, and subscriber deliveries are NOT recorded."""
    __tablename__ = "file_downloads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    file_id = Column(Integer, ForeignKey("shared_files.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


# ============================================================================
# BROADCASTS
# ============================================================================

class BroadcastStatus(str, enum.Enum):
    PENDING = "PENDING"    # queued, waiting for the worker
    SENDING = "SENDING"    # worker is delivering
    DONE = "DONE"
    FAILED = "FAILED"


class Broadcast(Base):
    """An admin advertisement/announcement fanned out to users' in-app inbox
    and/or Telegram DM by the background worker (throttled to respect Telegram
    flood limits). Targets everyone or a single role."""
    __tablename__ = "broadcasts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=True)
    link = Column(String(500), nullable=True)

    send_inbox = Column(Boolean, default=True)
    send_bot = Column(Boolean, default=False)
    target_role = Column(String(16), nullable=True)  # None = all users

    status = Column(SQLEnum(BroadcastStatus), default=BroadcastStatus.PENDING, nullable=False, index=True)
    total_recipients = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    # Resume cursor: highest user id already delivered to. Lets a broadcast that
    # was interrupted (worker restart / leadership flap) resume without
    # re-delivering to users it already reached.
    last_delivered_user_id = Column(Integer, default=0)

    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)


# ============================================================================
# SETTINGS
# ============================================================================

class AppSettings(Base):
    """Singleton settings table — always ID=1"""
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, default=1)
    app_name = Column(String, default="Hosting")
    logo_url = Column(String, nullable=True)
    show_logo = Column(Boolean, default=True)
    bot_username = Column(String, default="HostingBot")
    maintenance_mode = Column(Boolean, default=False)

    # Links
    announcements_url = Column(String, nullable=True)
    official_group_url = Column(String, nullable=True)

    # Fee settings
    withdrawal_fee_percent = Column(Float, default=0.0)
    min_deposit_amount = Column(MONEY, default=10.0)
    min_withdrawal_amount = Column(MONEY, default=10.0)
    # Admin-curated deposit coins (comma-separated NOWPayments tickers, e.g.
    # "btc,ltc,eth,xmr,usdttrc20"). NULL/empty => legacy default set.
    enabled_deposit_coins = Column(String, nullable=True)

    # Hosting settings
    subscription_price = Column(MONEY, default=15.0)       # 30-day unlimited-downloads subscription
    platform_fee_percent = Column(Float, default=10.0)     # cut taken from paywalled file sales
    free_downloads_per_day = Column(Integer, default=5)    # free-tier daily download quota
    min_uploads_for_rep = Column(Integer, default=1)       # approved uploads required to give rep

    # Support
    support_username = Column(String, nullable=True)
    support_display_name = Column(String, nullable=True)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

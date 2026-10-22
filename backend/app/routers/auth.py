"""Authentication Router"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timedelta
import logging
import os

from app.database import get_db
from app.ledger import record_balance_change, commit_and_broadcast
from app.models import User, UserRole, AppSettings
from app.schemas import Token, UserResponse, UserContactUpdate
from app.auth import verify_telegram_auth, verify_telegram_webapp_data, create_access_token, create_refresh_token, get_current_active_user, get_current_admin, block_if_impersonating
from app.sanitize import sanitize_content, sanitize_profile_theme
from app.config import IS_PRODUCTION
from jose import JWTError, jwt

router = APIRouter()
logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("audit")

from app.dependencies import limiter


class TelegramLoginData(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = ""
    username: Optional[str] = ""
    photo_url: Optional[str] = ""
    auth_date: int
    hash: str
    init_data: Optional[str] = None  # Full initData for verification


class RefreshTokenRequest(BaseModel):
    refresh_token: str


def _client_ip(request: Request) -> str:
    # Use the trusted-proxy-aware resolver so audit logs record the real client
    # and can't be forged via a client-supplied X-Forwarded-For header.
    from app.dependencies import real_client_ip
    try:
        return real_client_ip(request)
    except Exception:
        if request.client:
            return request.client.host
        return "unknown"


def _request_id(request: Request) -> str:
    rid = getattr(getattr(request, "state", None), "request_id", None)
    return str(rid) if rid else "unknown"


AUTH_DATE_MAX_AGE_SECONDS = 300  # 5 minutes max for auth_date

@router.post("/telegram", response_model=Token)
@limiter.limit("10/minute")
async def telegram_login(request: Request, auth_data: TelegramLoginData, db: AsyncSession = Depends(get_db)):
    """Login/Register via Telegram Mini App"""
    try:
        import time
        current_time = int(time.time())

        BOT_TOKEN = os.getenv("BOT_TOKEN", "")
        if not BOT_TOKEN:
            logger.error("BOT_TOKEN not configured — cannot verify auth")
            raise HTTPException(status_code=500, detail="Server auth not configured")

        # Identity and auth_date are taken ONLY from cryptographically verified
        # data — never from the unsigned request body. The body's id/auth_date are
        # attacker-controlled and must not decide which account logs in or whether
        # the request is fresh (replay protection).
        verified = False
        signed_id = None
        signed_auth_date = None
        signed_profile: dict = {}

        if auth_data.hash == "dev" and not IS_PRODUCTION:
            # Dev-only bypass; config fails closed to production.
            verified = True
            signed_id = auth_data.id
            signed_auth_date = current_time
            logger.info("Dev mode auth bypass used")
        else:
            # Preferred: Mini App initData — verify HMAC and read identity from it.
            webapp = verify_telegram_webapp_data(auth_data.init_data) if auth_data.init_data else None
            if webapp and isinstance(webapp.get("user"), dict) and webapp["user"].get("id"):
                verified = True
                signed_id = webapp["user"]["id"]
                signed_auth_date = webapp.get("auth_date")
                signed_profile = webapp["user"]
                logger.info("Mini App verification succeeded")
            else:
                # Login Widget fallback: the widget signs id/auth_date directly, so
                # on success the body's id/auth_date ARE the verified values.
                auth_dict = auth_data.model_dump(exclude={"init_data"})
                if verify_telegram_auth(auth_dict):
                    verified = True
                    signed_id = auth_data.id
                    signed_auth_date = auth_data.auth_date
                    signed_profile = {
                        "first_name": auth_data.first_name,
                        "username": auth_data.username,
                        "photo_url": auth_data.photo_url,
                    }
                    logger.info("Login Widget verification succeeded")

        if not verified or not signed_id:
            logger.warning(f"Auth verification failed for user {auth_data.id}")
            raise HTTPException(status_code=400, detail="Invalid Telegram auth")

        # Replay protection on the SIGNED auth_date (not the body field).
        if signed_auth_date is None or current_time - int(signed_auth_date) > AUTH_DATE_MAX_AGE_SECONDS:
            age = "unknown" if signed_auth_date is None else current_time - int(signed_auth_date)
            logger.warning(f"Auth data too old/missing for user {signed_id}: {age}s")
            raise HTTPException(status_code=400, detail="Authentication data expired. Please try again.")

        telegram_id = str(signed_id)

        # Bind the request to the verified identity so downstream profile-sync can't
        # be fed spoofed values alongside a valid blob. id is always the signed one.
        auth_data.id = signed_id
        if signed_profile.get("first_name"):
            auth_data.first_name = signed_profile["first_name"]
        if signed_profile.get("username"):
            auth_data.username = signed_profile["username"]
        if signed_profile.get("photo_url"):
            auth_data.photo_url = signed_profile["photo_url"]

        # Find or create user
        result = await db.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()

        if not user:
            # New user registration
            user = User(
                telegram_id=telegram_id,
                username=auth_data.username or f"user_{telegram_id}",
                first_name=auth_data.first_name,
                avatar_url=auth_data.photo_url,
                role=UserRole.USER,
                balance=0.0,
                # Registering IS activity — a fresh profile must never show "never".
                last_seen_at=datetime.utcnow(),
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
        else:
            # Sync Telegram profile data — do NOT overwrite referred_by_id for existing users
            if auth_data.first_name:
                user.first_name = auth_data.first_name
            # The @handle always mirrors Telegram — sync it on every login, but
            # never collide with a handle another user already holds (the username
            # column is unique — a blind assignment would IntegrityError the login).
            if auth_data.username and auth_data.username != user.username:
                taken = await db.execute(
                    select(User.id).where(User.username == auth_data.username, User.id != user.id)
                )
                if taken.scalar_one_or_none() is None:
                    user.username = auth_data.username
            if auth_data.photo_url:
                user.avatar_url = auth_data.photo_url

            user.last_seen_at = datetime.utcnow()
            await db.commit()
            await db.refresh(user)

        token_version = int(user.token_version or 0)

        # Generate refresh token rotation family for new sessions
        import uuid as _uuid
        rf_family = str(_uuid.uuid4())
        user.refresh_token_family = rf_family
        user.refresh_token_version = 1
        await db.commit()

        # Create tokens
        access_token = create_access_token(data={"sub": telegram_id, "tv": token_version})
        refresh_token = create_refresh_token(data={"sub": telegram_id, "tv": token_version, "rf": rf_family, "rv": 1})

        return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Telegram login failed")
        raise HTTPException(status_code=500, detail="Authentication failed")


# Reserved dev test users — these telegram_ids get specific roles/usernames
DEV_TEST_USERS = {
    "222222222": {"username": "user", "role": UserRole.USER},
    "333333333": {"username": "moderator", "role": UserRole.MODERATOR},
    "444444444": {"username": "admin", "role": UserRole.ADMIN},
}


@router.post("/dev-login", response_model=Token)
@limiter.limit("30/minute")
async def dev_login(
    request: Request,
    telegram_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Development login — requires ALLOW_DEV_LOGIN=true env var. Disabled in production!"""
    if IS_PRODUCTION:
        raise HTTPException(status_code=403, detail="Disabled in production")
    if os.getenv("ALLOW_DEV_LOGIN", "false").lower() != "true":
        raise HTTPException(status_code=403, detail="Dev login not enabled. Set ALLOW_DEV_LOGIN=true in .env")
    
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    
    # Determine role and username for this user.
    # Roles are NEVER taken from the client — only the fixed DEV_TEST_USERS map
    # may grant elevated roles. Any other telegram_id always gets plain USER.
    dev_config = DEV_TEST_USERS.get(telegram_id)
    assigned_role = UserRole.USER
    assigned_username = f"user_{telegram_id}"

    if dev_config:
        assigned_username = dev_config["username"]
        assigned_role = dev_config["role"]
    
    if not user:
        user = User(
            telegram_id=telegram_id,
            username=assigned_username,
            first_name=assigned_username.replace("_", " ").title(),
            role=assigned_role,
            last_seen_at=datetime.utcnow(),
        )
        db.add(user)
        await db.commit()
    else:
        # Existing user — update role if this is a reserved dev user
        if dev_config and user.role != dev_config["role"]:
            user.role = dev_config["role"]
            await db.commit()
    
    user.last_seen_at = datetime.utcnow()
    await db.commit()

    token_version = int(user.token_version or 0)

    # Generate refresh token rotation family for new sessions
    import uuid as _uuid2
    rf_family = str(_uuid2.uuid4())
    user.refresh_token_family = rf_family
    user.refresh_token_version = 1
    await db.commit()

    access_token = create_access_token(data={"sub": telegram_id, "tv": token_version})
    refresh_token = create_refresh_token(data={"sub": telegram_id, "tv": token_version, "rf": rf_family, "rv": 1})
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


@router.post("/refresh", response_model=Token)
@limiter.limit("20/minute")
async def refresh_access_token(request: Request, payload: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """Issue a new short-lived access token using a refresh token, with rotation and reuse detection."""
    from app.auth import SECRET_KEY, ALGORITHM, verify_refresh_token_rotation

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        decoded = jwt.decode(payload.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        if decoded.get("type") != "refresh":
            audit_logger.warning("auth.refresh.failed type_mismatch ip=%s request_id=%s", _client_ip(request), _request_id(request))
            raise credentials_exception
        telegram_id = decoded.get("sub")
        token_version_claim = decoded.get("tv")
        token_family = decoded.get("rf")
        token_rv = decoded.get("rv")
        if not telegram_id:
            audit_logger.warning("auth.refresh.failed missing_sub ip=%s request_id=%s", _client_ip(request), _request_id(request))
            raise credentials_exception
    except JWTError:
        audit_logger.warning("auth.refresh.failed invalid_jwt ip=%s request_id=%s", _client_ip(request), _request_id(request))
        raise credentials_exception

    result = await db.execute(
        select(User).where(User.telegram_id == str(telegram_id), User.is_active == True).with_for_update()
    )
    user = result.scalar_one_or_none()
    if not user:
        audit_logger.warning("auth.refresh.failed user_not_found telegram_id=%s ip=%s request_id=%s", str(telegram_id), _client_ip(request), _request_id(request))
        raise credentials_exception

    # Verify access token version
    if token_version_claim is not None:
        try:
            if int(token_version_claim) != int(user.token_version or 0):
                audit_logger.warning(
                    "auth.refresh.failed token_version_mismatch user_id=%s token_tv=%s db_tv=%s ip=%s request_id=%s",
                    user.id, token_version_claim, int(user.token_version or 0),
                    _client_ip(request), _request_id(request),
                )
                raise credentials_exception
        except (TypeError, ValueError):
            audit_logger.warning("auth.refresh.failed invalid_token_version user_id=%s ip=%s request_id=%s", user.id, _client_ip(request), _request_id(request))
            raise credentials_exception

    # Verify refresh token rotation. A token lacking rotation claims (rf/rv) is not
    # subject to reuse detection, so reject it outright and force re-login rather
    # than reissuing — otherwise a stolen pre-rotation token would never trigger
    # family revocation for the whole 30-day refresh lifetime.
    if not token_family or token_rv is None:
        audit_logger.warning("auth.refresh.failed missing_rotation_claims user_id=%s ip=%s request_id=%s", user.id, _client_ip(request), _request_id(request))
        raise credentials_exception

    if token_family and token_rv is not None:
        try:
            rv_int = int(token_rv)
        except (TypeError, ValueError):
            audit_logger.warning("auth.refresh.failed invalid_rv user_id=%s ip=%s", user.id, _client_ip(request))
            raise credentials_exception

        is_valid, reason = await verify_refresh_token_rotation(db, user, token_family, rv_int)
        if not is_valid:
            if reason == "reuse_detected_family_revoked":
                audit_logger.warning(
                    "auth.refresh.reuse_detected user_id=%s telegram_id=%s ip=%s request_id=%s",
                    user.id, str(telegram_id), _client_ip(request), _request_id(request),
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session expired due to security concern. Please log in again.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            audit_logger.warning(
                "auth.refresh.failed rotation_check user_id=%s reason=%s ip=%s",
                user.id, reason, _client_ip(request),
            )
            raise credentials_exception

    current_tv = int(user.token_version or 0)
    current_rf = user.refresh_token_family
    current_rv = int(user.refresh_token_version or 0)
    new_access_token = create_access_token(data={"sub": str(telegram_id), "tv": current_tv})
    new_refresh_token = create_refresh_token(data={"sub": str(telegram_id), "tv": current_tv, "rf": current_rf, "rv": current_rv})
    audit_logger.info("auth.refresh.success user_id=%s telegram_id=%s ip=%s request_id=%s rf_rv=%s", user.id, str(telegram_id), _client_ip(request), _request_id(request), current_rv)
    return {"access_token": new_access_token, "refresh_token": new_refresh_token, "token_type": "bearer"}


@router.post("/logout")
async def logout_current_session(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Invalidate all currently issued tokens for the user."""
    current_user.token_version = int(current_user.token_version or 0) + 1
    # Invalidate refresh token family
    current_user.refresh_token_family = None
    current_user.refresh_token_version = -1
    await db.commit()
    audit_logger.info(
        "auth.logout.success user_id=%s telegram_id=%s new_tv=%s ip=%s request_id=%s",
        current_user.id,
        current_user.telegram_id,
        int(current_user.token_version or 0),
        _client_ip(request),
        _request_id(request),
    )
    return {"message": "Logged out"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_active_user)):
    """Get current user"""
    return current_user


@router.put("/profile", response_model=UserResponse)
async def update_profile(
    updates: UserContactUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update contact info for current user"""
    import json
    update_data = updates.model_dump(exclude_unset=True)

    # Handle visibility is chosen once at setup; changing it afterwards is a
    # premium perk (staff count as premium).
    if 'show_telegram' in update_data and update_data['show_telegram'] != current_user.show_telegram:
        is_staff = current_user.role in (UserRole.MODERATOR, UserRole.ADMIN)
        if not (current_user.is_premium or is_staff):
            raise HTTPException(
                status_code=403,
                detail="Changing handle visibility requires Premium",
            )

    user_result = await db.execute(
        select(User).where(User.id == current_user.id).with_for_update()
    )
    user = user_result.scalar_one()

    for field, value in update_data.items():
        if field == 'notification_preferences' and isinstance(value, dict):
            value = json.dumps(value)
        if isinstance(value, str) and field == 'profile_bio':
            value = sanitize_content(value)
        if field == 'profile_theme':
            value = sanitize_profile_theme(value)
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user


class AccountSetupRequest(BaseModel):
    # No username field: the @handle always mirrors Telegram and is synced on
    # every login. Setup only chooses whether to SHOW it publicly.
    pin: str = Field(min_length=6, max_length=72)
    first_name: str = Field(min_length=1, max_length=64)  # display name (free initial set)
    show_telegram: bool = True  # show @handle publicly (profile, threads, posts)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(max_length=72)
    new_password: str = Field(min_length=6, max_length=72)


def _validate_password_strength(password: str) -> None:
    """Shared password policy for setup and change (min 6 chars, 1 digit)."""
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if not any(c.isdigit() for c in password):
        raise HTTPException(status_code=400, detail="Password must contain at least 1 digit")


@router.post("/setup", response_model=UserResponse)
async def setup_account(
    payload: AccountSetupRequest,
    current_user: User = Depends(block_if_impersonating),
    db: AsyncSession = Depends(get_db),
):
    """First-time account setup: set display name, password, and handle visibility.
    The @handle itself always mirrors Telegram and cannot be chosen here."""
    if current_user.is_setup_complete:
        raise HTTPException(status_code=400, detail="Account already set up")

    _validate_password_strength(payload.pin)

    from app.auth import hash_pin

    new_first_name = sanitize_content(payload.first_name).strip() if payload.first_name else ""
    if not new_first_name:
        raise HTTPException(status_code=400, detail="Display name cannot be empty")

    current_user.first_name = new_first_name
    current_user.pin_hash = hash_pin(payload.pin)
    current_user.show_telegram = payload.show_telegram
    current_user.is_setup_complete = True
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.put("/password")
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    payload: PasswordChangeRequest,
    current_user: User = Depends(block_if_impersonating),
    db: AsyncSession = Depends(get_db),
):
    """Change account password."""
    if not current_user.pin_hash:
        raise HTTPException(status_code=400, detail="No password set. Use /api/auth/setup first.")

    from app.auth import check_pin, hash_pin
    if not check_pin(payload.current_password, current_user.pin_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    _validate_password_strength(payload.new_password)

    current_user.pin_hash = hash_pin(payload.new_password)

    # Changing the password must invalidate every other live session (the whole
    # point of changing it after a suspected compromise). Bump token_version to
    # kill existing access tokens and rotate the refresh family to kill existing
    # refresh tokens, then hand this caller a fresh pair so they stay signed in.
    new_tv = int(current_user.token_version or 0) + 1
    current_user.token_version = new_tv
    import uuid as _uuid
    rf_family = str(_uuid.uuid4())
    current_user.refresh_token_family = rf_family
    current_user.refresh_token_version = 1
    await db.commit()

    access_token = create_access_token(data={"sub": str(current_user.telegram_id), "tv": new_tv})
    refresh_token = create_refresh_token(
        data={"sub": str(current_user.telegram_id), "tv": new_tv, "rf": rf_family, "rv": 1}
    )
    return {
        "message": "Password changed successfully",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }

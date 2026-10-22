"""Authentication utilities"""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt as _bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import hashlib
import hmac
import os

from app.database import get_db
from app.models import User, UserRole
from app.config import IS_PRODUCTION

def hash_pin(pin: str) -> str:
    """Hash a PIN/password with bcrypt directly (version-independent).

    Uses bcrypt straight rather than passlib's CryptContext: passlib 1.7.4 is
    broken with bcrypt >= 4.1 (it reads bcrypt.__about__, removed in 4.1+, which
    breaks ALL hashing). Truncates to bcrypt's 72-byte input limit.
    """
    return _bcrypt.hashpw(pin.encode("utf-8")[:72], _bcrypt.gensalt()).decode("utf-8")


def check_pin(pin: str, hashed: Optional[str]) -> bool:
    """Verify a PIN/password against a bcrypt hash (incl. legacy passlib-made hashes)."""
    if not hashed:
        return False
    try:
        return _bcrypt.checkpw(pin.encode("utf-8")[:72], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


SECRET_KEY = os.getenv("SECRET_KEY", "")

if not SECRET_KEY or SECRET_KEY in ("your-secret-key", ""):
    if IS_PRODUCTION:
        raise RuntimeError("FATAL: SECRET_KEY must be set in production! Set a secure random string via environment variable.")
    import secrets as _s
    SECRET_KEY = _s.token_hex(32)
    import logging as _log
    _log.getLogger(__name__).warning("SECRET_KEY not set! Generated ephemeral key — tokens will invalidate on restart.")

ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

security = HTTPBearer()


# Fields Telegram actually signs in the Login Widget data-check-string. Anything
# else the client sends (e.g. init_data) is NOT
# covered by the signature and must be excluded from the check, otherwise either
# verification breaks or unsigned fields get folded into the trusted payload.
_TELEGRAM_WIDGET_FIELDS = {"id", "first_name", "last_name", "username", "photo_url", "auth_date"}


def verify_telegram_auth(auth_data: dict) -> bool:
    """Verify Telegram Login Widget data.

    Returns True only if the HMAC over the Telegram-signed fields matches. On
    success the caller may trust auth_data's id/auth_date — they are part of the
    signed set.
    """
    if not BOT_TOKEN:
        import logging
        logging.getLogger(__name__).warning("BOT_TOKEN not set — Telegram auth verification skipped. This is insecure outside development!")
        return False

    check_hash = auth_data.get('hash', '')
    if not check_hash:
        return False

    # Build the check string from only the Telegram-signed, non-empty fields so it
    # matches exactly what Telegram hashed (it omits fields it didn't send).
    data_check_string = '\n'.join(
        f"{k}={auth_data[k]}"
        for k in sorted(auth_data)
        if k in _TELEGRAM_WIDGET_FIELDS and auth_data[k] not in (None, "")
    )

    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
    calculated_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(calculated_hash, check_hash)


def verify_telegram_webapp_data(init_data: str) -> Optional[dict]:
    """Verify Telegram Mini App initData using the WebAppData algorithm.

    Mini App uses: HMAC-SHA256(HMAC-SHA256("WebAppData", BOT_TOKEN), data_check_string)

    Returns the parsed, *verified* fields on success — e.g.
    ``{"user": {"id": ..., "first_name": ...}, "auth_date": <int>, ...}`` — or
    ``None`` if verification fails. Callers MUST take the user id and auth_date
    from this return value, never from identity/auth_date fields supplied
    alongside init_data in the request body: those are not covered by the HMAC
    and are fully attacker-controlled.
    """
    if not BOT_TOKEN:
        import logging
        logging.getLogger(__name__).warning("BOT_TOKEN not set — WebApp data verification skipped. This is insecure outside development!")
        return None

    if not init_data:
        return None

    try:
        from urllib.parse import parse_qs
        import json as _json

        parsed = parse_qs(init_data, keep_blank_values=True)

        hash_value = parsed.get('hash', [''])[0]
        if not hash_value:
            return None

        data_check_parts = []
        for key in sorted(parsed.keys()):
            if key != 'hash':
                value = parsed[key][0]
                data_check_parts.append(f"{key}={value}")

        data_check_string = '\n'.join(data_check_parts)

        secret_key = hmac.new(
            b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(calculated_hash, hash_value):
            return None

        # HMAC verified — parse the signed payload into a usable dict.
        result: dict = {}
        for key, values in parsed.items():
            if key == 'hash':
                continue
            value = values[0]
            if key == 'user':
                try:
                    result['user'] = _json.loads(value)
                except (ValueError, TypeError):
                    return None
            elif key == 'auth_date':
                try:
                    result['auth_date'] = int(value)
                except (TypeError, ValueError):
                    return None
            else:
                result[key] = value
        return result
    except (KeyError, ValueError, TypeError, UnicodeDecodeError) as e:
        import logging
        logging.getLogger(__name__).warning(f"WebApp data verification failed: {e}")
        return None


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def verify_refresh_token_rotation(
    db: AsyncSession,
    user: User,
    token_family: str | None,
    token_version: int,
) -> tuple[bool, str]:
    """Verify refresh token rotation and detect reuse.

    Returns (is_valid, reason).
    - is_valid=True: token is fresh, caller should issue new rotation.
    - is_valid=False: reason explains why (reuse detected, family mismatch, etc.)
    """
    db_family = user.refresh_token_family
    db_version = int(user.refresh_token_version or 0)

    if db_family is None:
        return (False, "no_rotation_family")

    if token_family != db_family:
        return (False, "family_mismatch")

    if db_version < 0:
        return (False, "family_revoked")

    if token_version < db_version:
        # REUSE DETECTED — someone used an old refresh token after a newer one was issued.
        # This means either the legitimate user's token was stolen, or there's a bug.
        # Invalidate the entire family to force re-login.
        user.refresh_token_version = -1
        user.token_version = int(user.token_version or 0) + 1
        await db.commit()
        import logging
        audit = logging.getLogger("audit")
        audit.warning(
            "auth.refresh.reuse_detected user_id=%s telegram_id=%s token_family=%s claimed_v=%s db_v=%s",
            user.id, user.telegram_id, token_family, token_version, db_version,
        )
        return (False, "reuse_detected_family_revoked")

    if token_version == db_version:
        # Valid rotation — advance the version
        user.refresh_token_version = db_version + 1
        await db.commit()
        return (True, "ok")

    # token_version > db_version — shouldn't happen normally, treat as valid but warn
    import logging
    logging.getLogger(__name__).warning(
        "auth.refresh.version_ahead user_id=%s claimed_v=%s db_v=%s",
        user.id, token_version, db_version,
    )
    user.refresh_token_version = token_version + 1
    await db.commit()
    return (True, "ok_version_ahead")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        token_type = payload.get("type")
        if token_type and token_type != "access":
            raise credentials_exception
        telegram_id: str = payload.get("sub")
        token_version_claim = payload.get("tv")
        if telegram_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception

    if token_version_claim is not None:
        try:
            if int(token_version_claim) != int(user.token_version or 0):
                raise credentials_exception
        except (TypeError, ValueError):
            raise credentials_exception

    # Impersonation sessions (an admin acting as a user via the impersonate
    # endpoint) carry an `imp` claim holding the real admin's id. Surface it as a
    # transient attribute so sensitive operations can be blocked and so callers
    # can attribute actions to the actual admin instead of the victim.
    imp_claim = payload.get("imp")
    try:
        user.impersonator_id = int(imp_claim) if imp_claim is not None else None
    except (TypeError, ValueError):
        user.impersonator_id = None

    # Update last seen
    user.last_seen_at = datetime.utcnow()
    await db.commit()

    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    if current_user.is_banned:
        raise HTTPException(
            status_code=403,
            detail=f"Account banned{': ' + current_user.ban_reason if current_user.ban_reason else ''}"
        )
    return current_user


async def block_if_impersonating(current_user: User = Depends(get_current_active_user)) -> User:
    """Forbid sensitive operations while an admin is impersonating this user.

    An impersonation session must never be able to move money or change
    credentials on the victim's behalf — those actions are blocked outright and
    must be performed by the user themselves.
    """
    if getattr(current_user, "impersonator_id", None) is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action is not available during an impersonation session",
        )
    return current_user


async def get_current_verified_user(current_user: User = Depends(get_current_active_user)) -> User:
    """Require a full account (alias of active user — no trial tier here)."""
    return current_user


async def get_current_unmuted_user(current_user: User = Depends(get_current_active_user)) -> User:
    """Block muted users from content-creating actions (posting, replies, live chat).

    Lazily ignores an expired mute (the scheduler durably clears it); reading and
    other actions such as DMs are unaffected.
    """
    if current_user.is_muted and (
        current_user.mute_expires_at is None or current_user.mute_expires_at > datetime.utcnow()
    ):
        raise HTTPException(
            status_code=403,
            detail=f"You are muted{': ' + current_user.mute_reason if current_user.mute_reason else ''}"
        )
    return current_user


async def get_current_moderator(current_user: User = Depends(get_current_active_user)) -> User:
    """Require MODERATOR or ADMIN role"""
    if current_user.role not in (UserRole.MODERATOR, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Moderator access required"
        )
    return current_user


async def get_current_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Require ADMIN role"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

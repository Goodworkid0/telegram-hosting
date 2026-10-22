"""Telegram notification utility — sends messages via Bot API + creates in-app Notification records"""
import os
import asyncio
import json
import logging
import html as html_mod
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Notification types a user can opt out of, mapped to the preference keys the
# Settings page saves in User.notification_preferences. Types not listed here
# (money movements, escrow, moderation, giveaways, ...) are always delivered.
PREF_KEYS = {
    "reputation": "reputation",
    "new_follower": "followers",
}

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Emoji per notification type — one entry per type the app actually emits
# (unknown types fall back to 🔔 in _format_tg).
EMOJI = {
    # Money
    "deposit_credited": "💵",
    "withdrawal_approved": "✅",
    "withdrawal_rejected": "❌",
    "balance_adjusted": "💳",
    "subscription_purchase": "⭐",
    # Files
    "file_approved": "✅",
    "file_rejected": "❌",
    "file_sold": "💰",
    # Social
    "reputation": "⭐",
    "new_follower": "👤",
    "announcement": "📢",  # admin broadcasts
    # Moderation
    "warning": "⚠️",
    "muted": "🔇",
    "unmuted": "🔊",
    "unbanned": "✅",
}


# ---------------------------------------------------------------------------
# Process-wide send throttle + 429 backoff.
#
# The bot PROCESS wraps context.bot.* in AIORateLimiter, but the API and worker
# call the HTTP Bot API directly (below) and would otherwise bypass Telegram's
# flood limits — an unpaced fan-out (achievement/broadcast/notification bursts,
# each fired as its own asyncio task) can hit hundreds of concurrent sends and
# get the bot flood-waited or suspended. Every direct send now goes through
# _tg_api, which paces dispatch to ~25/s per process and honors 429 retry_after.
# In-process only: with several web workers the aggregate can still exceed the
# global limit, but the dangerous batch fan-outs run in the single leader worker
# and every path now backs off on 429 instead of hammering through a flood-wait.
# ---------------------------------------------------------------------------
_SEND_MIN_INTERVAL = 1.0 / 25   # ~25 sends/sec ceiling per process
_send_lock = asyncio.Lock()
_next_send_at = 0.0


def _scrub(text: str) -> str:
    """Keep the bot token out of logs — httpx error strings embed the request URL."""
    return text.replace(BOT_TOKEN, "***") if BOT_TOKEN else text


def _json_ok(res) -> bool:
    try:
        return bool(res.json().get("ok"))
    except Exception:
        return False


async def _pace() -> None:
    """Block until this process's next send slot (serializes + rate-limits)."""
    global _next_send_at
    async with _send_lock:
        loop = asyncio.get_event_loop()
        now = loop.time()
        if _next_send_at > now:
            await asyncio.sleep(_next_send_at - now)
            now = loop.time()
        _next_send_at = now + _SEND_MIN_INTERVAL


async def _tg_api(method: str, payload: dict, timeout: float = 30.0):
    """POST to the Bot API through the throttle, honoring a 429 retry_after once.
    Returns the httpx Response, or None on network error."""
    if not BOT_TOKEN:
        return None
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    res = None
    for attempt in range(2):
        await _pace()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.post(url, json=payload)
        except Exception as e:
            logger.warning("Telegram %s network error: %s", method, _scrub(str(e)))
            return None
        if res.status_code == 429 and attempt == 0:
            try:
                retry_after = int(res.json().get("parameters", {}).get("retry_after", 1))
            except Exception:
                retry_after = 1
            logger.warning("Telegram 429 on %s — backing off %ss", method, retry_after)
            await asyncio.sleep(min(max(retry_after, 1), 60))
            continue
        return res
    return res


async def send_telegram(chat_id, text: str, parse_mode: str = "HTML") -> bool:
    """Low-level send via Bot API (throttled + 429-aware). Returns True on success."""
    if not BOT_TOKEN or not chat_id:
        return False
    tid = str(chat_id).strip()
    if not tid.isdigit():
        return False
    res = await _tg_api("sendMessage", {
        "chat_id": int(tid),
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }, timeout=10.0)
    if res is None:
        return False
    ok = res.status_code == 200 and _json_ok(res)
    if not ok:
        logger.warning("Telegram send failed for %s: %s", tid, _scrub(res.text[:200]))
    return ok


# A stored file_id is type-specific: a photo/video/audio/voice file_id CANNOT be
# re-sent via sendDocument — Telegram requires the method matching the media kind.
_KIND_SEND = {
    "document": ("sendDocument", "document"),
    "photo": ("sendPhoto", "photo"),
    "video": ("sendVideo", "video"),
    "audio": ("sendAudio", "audio"),
    "voice": ("sendVoice", "voice"),
}


async def send_file(chat_id, file_id: str, kind: str = "document", caption: str | None = None) -> tuple[bool, str | None]:
    """Re-send a stored file to a user by file_id (no re-hosting, no size cap).

    Dispatches to the send method matching `kind` — otherwise Telegram rejects a
    photo/video/etc. file_id sent as a document. Returns (ok, error_code);
    error_code is "not_started" when the user has never opened / has blocked the
    bot (Telegram forbids bot-initiated chats), so callers can show an actionable
    message instead of a generic failure.
    """
    if not BOT_TOKEN or not chat_id:
        return False, "no_bot"
    tid = str(chat_id).strip()
    if not tid.isdigit():
        return False, "bad_chat"
    method, field = _KIND_SEND.get(kind, _KIND_SEND["document"])
    payload = {"chat_id": int(tid), field: file_id}
    # Voice notes don't take a caption field the same way; send it for the rest.
    if caption and kind != "voice":
        payload["caption"] = caption[:1024]
    res = await _tg_api(method, payload, timeout=30.0)
    if res is None:
        return False, "send_failed"
    if res.status_code == 200 and _json_ok(res):
        return True, None
    try:
        desc = (res.json().get("description") or res.text or "").lower()
    except Exception:
        desc = (res.text or "").lower()
    # 403 with "bot can't initiate"/"blocked" -> user must /start the bot.
    if res.status_code == 403 or "initiate" in desc or "blocked" in desc:
        return False, "not_started"
    logger.warning("send_file(%s) failed for %s: %s", method, tid, _scrub(res.text[:200]))
    return False, "send_failed"


def _format_tg(type: str, title: str, body: str | None) -> str:
    emoji = EMOJI.get(type, "🔔")
    msg = f"{emoji} <b>{html_mod.escape(title)}</b>"
    if body:
        msg += f"\n{html_mod.escape(body)}"
    return msg


async def create_notification(
    db: AsyncSession,
    *,
    user_id: int,
    type: str,
    title: str,
    body: str = None,
    link: str = None,
    telegram_id: str | int | None = None,
    related_user_id: int = None,
):
    """Create an in-app Notification AND fire-and-forget a Telegram message AND broadcast SSE.

    If ``telegram_id`` is already known pass it to skip an extra DB query.
    Caller is responsible for committing the transaction.
    """
    from app.models import Notification, User

    from datetime import datetime as dt, timezone

    # Respect the user's notification preferences for opt-out-able types.
    pref_key = PREF_KEYS.get(type)
    if pref_key:
        result = await db.execute(
            select(User.notification_preferences).where(User.id == user_id)
        )
        raw_prefs = result.scalar_one_or_none()
        if raw_prefs:
            try:
                prefs = json.loads(raw_prefs)
            except (TypeError, ValueError):
                prefs = None
            if isinstance(prefs, dict) and prefs.get(pref_key) is False:
                return

    db.add(Notification(
        user_id=user_id, type=type, title=title, body=body, link=link,
        related_user_id=related_user_id,
        created_at=dt.now(timezone.utc).replace(tzinfo=None),
    ))

    # 2. Telegram
    tid = telegram_id
    if not tid:
        result = await db.execute(select(User.telegram_id).where(User.id == user_id))
        tid = result.scalar_one_or_none()

    if tid:
        msg = _format_tg(type, title, body)
        try:
            asyncio.create_task(send_telegram(tid, msg))
        except RuntimeError:
            # No running event loop (edge case in background tasks at shutdown)
            pass

    # 3. SSE broadcast
    try:
        from app.redis_client import broadcast_notification
        await broadcast_notification(user_id, type, title, body, link)
    except Exception:
        pass

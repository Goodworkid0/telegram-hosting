"""Redis integration — pub/sub for SSE, rate limiting backend, caching.
Falls back to in-memory when REDIS_URL is not configured.
"""
import os
import json
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "").strip()

_redis: Optional["redis.Redis"] = None
_redis_pubsub_available = False


def get_redis():
    """Lazy-initialize Redis connection."""
    global _redis
    if _redis is not None:
        return _redis
    if not REDIS_URL:
        return None
    try:
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        logger.info("Redis connected: %s", REDIS_URL)
        return _redis
    except Exception as e:
        logger.warning("Redis connection failed: %s. Falling back to in-memory.", e)
        return None


# ── SSE Pub/Sub (multi-worker safe) ──

_in_memory_queues: dict[int, asyncio.Queue] = {}

CHANNEL_BALANCE = "sse:balance"
CHANNEL_NOTIFICATION = "sse:notification"


async def broadcast_balance_update(user_id: int, new_balance):
    """Push balance update. Uses Redis pub/sub when available."""
    # new_balance may be a Decimal (money) — cast once for JSON.
    new_balance = float(new_balance or 0)
    payload = json.dumps({"user_id": user_id, "balance": new_balance})
    r = get_redis()
    if r:
        try:
            await r.publish(CHANNEL_BALANCE, payload)
            return
        except Exception:
            pass
    # Fallback: in-memory
    q = _in_memory_queues.get(user_id)
    if q:
        try:
            await q.put({"event": "balance", "data": json.dumps({"balance": new_balance})})
        except Exception:
            pass


async def broadcast_notification(user_id: int, notif_type: str, title: str, body: str = None, link: str = None):
    """Push notification event."""
    payload = json.dumps({
        "user_id": user_id,
        "type": notif_type,
        "title": title,
        "body": body,
        "link": link,
    })
    r = get_redis()
    if r:
        try:
            await r.publish(CHANNEL_NOTIFICATION, payload)
            return
        except Exception:
            pass
    # Fallback: in-memory
    q = _in_memory_queues.get(user_id)
    if q:
        try:
            await q.put({"event": "notification", "data": json.dumps({
                "type": notif_type, "title": title, "body": body, "link": link,
            })})
        except Exception:
            pass


def register_sse_client(user_id: int, queue: asyncio.Queue):
    """Register an in-memory queue for a connected SSE client."""
    _in_memory_queues[user_id] = queue


def unregister_sse_client(user_id: int):
    """Remove a disconnected SSE client."""
    _in_memory_queues.pop(user_id, None)


async def subscribe_sse(user_id: int, on_event):
    """Subscribe to Redis pub/sub for SSE events for a specific user.
    Returns a cancel callback.
    Must be called with an already-connected Redis client.
    """
    r = get_redis()
    if not r:
        return lambda: None

    pubsub = r.pubsub()
    await pubsub.subscribe(CHANNEL_BALANCE, CHANNEL_NOTIFICATION)

    async def listener():
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    if data.get("user_id") != user_id:
                        continue
                    if message["channel"] == CHANNEL_BALANCE:
                        await on_event("balance", {"balance": data["balance"]})
                    elif message["channel"] == CHANNEL_NOTIFICATION:
                        await on_event("notification", {
                            "type": data["type"],
                            "title": data["title"],
                            "body": data.get("body"),
                            "link": data.get("link"),
                        })
                except (json.JSONDecodeError, KeyError):
                    pass
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(CHANNEL_BALANCE, CHANNEL_NOTIFICATION)

    task = asyncio.create_task(listener())
    return lambda: task.cancel()

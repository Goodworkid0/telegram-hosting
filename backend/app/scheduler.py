"""Background-task scheduler with single-leader election.

The periodic loops in ``app.tasks`` (giveaway finish, achievement awards, escrow
release, leaderboard rotation, ban expiry) must run in exactly ONE process. With
multiple uvicorn workers the FastAPI lifespan runs once *per worker*, so naively
spawning the loops would run them N times — double-awarding XP, rotating the
leaderboard twice, etc.

This coordinator uses a Redis lock for leader election: every process competes
for one lock; only the holder runs the loops and renews the lock on a heartbeat.
If the leader dies its lock expires (TTL) and another process takes over. When
Redis is not configured (single-process dev), the loops run directly.
"""
import asyncio
import logging
import uuid

from app.redis_client import get_redis
from app.tasks import (
    auto_unexpire_bans,
    auto_unexpire_mutes,
    process_broadcasts,
)

logger = logging.getLogger(__name__)

LEADER_KEY = "hosting:scheduler:leader"
LEADER_TTL_SECONDS = 30      # lock auto-expires this long after the last heartbeat
HEARTBEAT_SECONDS = 10       # renew well within the TTL
ACQUIRE_RETRY_SECONDS = 10   # how often a follower retries to take over

# Renew the lock only if we still own it (atomic check-and-extend).
_RENEW_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('pexpire', KEYS[1], ARGV[2])
else
  return 0
end
"""
# Release the lock only if we still own it (atomic check-and-delete).
_RELEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
else
  return 0
end
"""

# The periodic loops to run while we hold leadership.
TASK_FACTORIES = (
    auto_unexpire_bans,
    auto_unexpire_mutes,
    process_broadcasts,
)


def _start_tasks() -> list[asyncio.Task]:
    return [asyncio.create_task(fn(), name=fn.__name__) for fn in TASK_FACTORIES]


async def _stop_tasks(tasks: list[asyncio.Task]) -> None:
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def run_background_scheduler() -> None:
    """Run the periodic loops, guaranteeing only one process does so at a time."""
    redis = get_redis()

    if not redis:
        # No Redis configured -> assume a single process (dev). Run directly.
        logger.info("scheduler: no Redis — running background tasks in-process")
        tasks = _start_tasks()
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            await _stop_tasks(tasks)
            raise
        return

    token = str(uuid.uuid4())
    tasks: list[asyncio.Task] | None = None
    logger.info("scheduler: starting leader election (token=%s)", token[:8])
    try:
        while True:
            try:
                acquired = await redis.set(
                    LEADER_KEY, token, nx=True, px=LEADER_TTL_SECONDS * 1000
                )
            except Exception as e:
                logger.warning("scheduler: redis error during acquire: %s", e)
                acquired = None

            if not acquired:
                # Another process is leader; wait and retry so we can take over
                # if it dies.
                await asyncio.sleep(ACQUIRE_RETRY_SECONDS)
                continue

            logger.info("scheduler: acquired leadership — starting background tasks")
            tasks = _start_tasks()
            try:
                # Heartbeat: keep the lock alive while we stay leader & healthy.
                while True:
                    await asyncio.sleep(HEARTBEAT_SECONDS)
                    try:
                        renewed = await redis.eval(
                            _RENEW_LUA, 1, LEADER_KEY, token, LEADER_TTL_SECONDS * 1000
                        )
                    except Exception as e:
                        logger.warning("scheduler: redis error during renew: %s", e)
                        renewed = 0
                    if not renewed:
                        logger.warning("scheduler: lost leadership — stopping background tasks")
                        break
                    # Surface a crashed loop (the auto_* loops normally never exit).
                    for t in tasks:
                        if t.done() and not t.cancelled() and t.exception():
                            logger.error("scheduler: task %s exited: %r", t.get_name(), t.exception())
            finally:
                await _stop_tasks(tasks)
                tasks = None
            # Leadership lost — loop around to try to re-acquire.
    except asyncio.CancelledError:
        logger.info("scheduler: shutting down")
        if tasks:
            await _stop_tasks(tasks)
        try:
            await redis.eval(_RELEASE_LUA, 1, LEADER_KEY, token)
        except Exception:
            pass
        raise

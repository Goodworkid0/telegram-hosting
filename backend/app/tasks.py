"""Background tasks — broadcast delivery + ban/mute expiry."""
import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, or_, and_
from app.database import async_session
from app.models import (
    User, Notification, UserRole,
    Broadcast, BroadcastStatus,
)
from app.telegram import create_notification

logger = logging.getLogger(__name__)

BROADCAST_CHECK_INTERVAL = 15     # how often the worker polls for a queued broadcast
BROADCAST_SEND_SLEEP = 0.05      # ~20 Telegram DMs/sec — stays under the ~30/s flood limit
BROADCAST_BATCH = 200            # users fetched per DB page while delivering
BROADCAST_STALE_MINUTES = 5      # a SENDING broadcast older than this is resumed (worker crash)
BAN_CHECK_INTERVAL = 60


async def auto_unexpire_bans():
    """Check for expired temporary bans and unban users"""
    while True:
        try:
            async with async_session() as db:
                now = datetime.utcnow()
                result = await db.execute(
                    select(User).where(
                        User.is_banned == True,
                        User.ban_expires_at != None,
                        User.ban_expires_at <= now,
                    )
                )
                expired_bans = result.scalars().all()

                for user in expired_bans:
                    try:
                        user.is_banned = False
                        user.ban_reason = None
                        user.ban_expires_at = None
                        user.banned_at = None
                        await create_notification(
                            db,
                            user_id=user.id,
                            type="unbanned",
                            title="Your ban has expired",
                            body="Your temporary ban has expired. You now have full access again.",
                            link="/",
                            telegram_id=user.telegram_id,
                        )
                        await db.commit()
                        logger.info(f"Auto-unbanned user #{user.id} (@{user.username}) after ban expiry")
                    except Exception as e:
                        logger.error(f"Failed to unban user #{user.id}: {e}")
                        await db.rollback()
        except Exception as e:
            logger.error(f"Auto-unexpire bans task error: {e}")

        await asyncio.sleep(BAN_CHECK_INTERVAL)


async def auto_unexpire_mutes():
    """Check for expired temporary mutes and unmute users"""
    while True:
        try:
            async with async_session() as db:
                now = datetime.utcnow()
                result = await db.execute(
                    select(User).where(
                        User.is_muted == True,
                        User.mute_expires_at != None,
                        User.mute_expires_at <= now,
                    )
                )
                expired_mutes = result.scalars().all()

                for user in expired_mutes:
                    try:
                        user.is_muted = False
                        user.mute_reason = None
                        user.mute_expires_at = None
                        user.muted_at = None
                        user.muted_by_id = None
                        await create_notification(
                            db,
                            user_id=user.id,
                            type="unmuted",
                            title="Your mute has expired",
                            body="Your temporary mute has expired. You can post and chat again.",
                            link="/",
                            telegram_id=user.telegram_id,
                        )
                        await db.commit()
                        logger.info(f"Auto-unmuted user #{user.id} (@{user.username}) after mute expiry")
                    except Exception as e:
                        logger.error(f"Failed to unmute user #{user.id}: {e}")
                        await db.rollback()
        except Exception as e:
            logger.error(f"Auto-unexpire mutes task error: {e}")

        await asyncio.sleep(BAN_CHECK_INTERVAL)


async def _deliver_broadcast(db, b: Broadcast) -> None:
    """Deliver one broadcast to its audience, paginating by user id and pacing
    Telegram DMs so the bot stays within flood limits. No opt-out — every
    targeted (active, non-banned) user receives it."""
    from app.telegram import send_telegram, _format_tg

    conds = [User.is_active == True, User.is_banned == False]
    if b.target_role:
        try:
            conds.append(User.role == UserRole[b.target_role])
        except KeyError:
            pass  # unknown role -> treat as "all"

    msg = _format_tg("announcement", b.title, b.body) if b.send_bot else None
    last_id = b.last_delivered_user_id or 0   # resume from where a prior run left off
    sent = b.sent_count or 0
    failed = b.failed_count or 0
    while True:
        rows = (await db.execute(
            select(User).where(*conds, User.id > last_id).order_by(User.id).limit(BROADCAST_BATCH)
        )).scalars().all()
        if not rows:
            break
        for u in rows:
            last_id = u.id
            try:
                if b.send_inbox:
                    db.add(Notification(
                        user_id=u.id, type="announcement",
                        title=b.title, body=b.body, link=b.link,
                        created_at=datetime.utcnow(),
                    ))
                if b.send_bot and u.telegram_id:
                    ok = await send_telegram(u.telegram_id, msg)
                    if not ok:
                        failed += 1
                    await asyncio.sleep(BROADCAST_SEND_SLEEP)
                sent += 1
            except Exception as e:
                failed += 1
                logger.warning("Broadcast #%s delivery to user %s failed: %s", b.id, u.id, e)
        b.sent_count = sent
        b.failed_count = failed
        b.last_delivered_user_id = last_id  # advance the resume cursor with this batch
        await db.commit()  # persist inbox rows + progress + cursor per batch

    b.status = BroadcastStatus.DONE
    b.finished_at = datetime.utcnow()
    await db.commit()
    logger.info("Broadcast #%s done: %s sent, %s failed", b.id, sent, failed)


async def process_broadcasts():
    """Pick up queued admin broadcasts and deliver them one at a time."""
    while True:
        try:
            async with async_session() as db:
                # Pick a queued broadcast, OR resume one stuck in SENDING (worker
                # died / leadership flapped mid-delivery). The resume cursor
                # (last_delivered_user_id) prevents re-delivering to reached users.
                stale_before = datetime.utcnow() - timedelta(minutes=BROADCAST_STALE_MINUTES)
                b = await db.scalar(
                    select(Broadcast).where(
                        or_(
                            Broadcast.status == BroadcastStatus.PENDING,
                            and_(
                                Broadcast.status == BroadcastStatus.SENDING,
                                Broadcast.started_at < stale_before,
                            ),
                        )
                    ).order_by(Broadcast.created_at).limit(1)
                )
                if b:
                    b.status = BroadcastStatus.SENDING
                    b.started_at = datetime.utcnow()
                    await db.commit()
                    try:
                        await _deliver_broadcast(db, b)
                    except Exception as e:
                        logger.error("Broadcast #%s failed: %s", b.id, e)
                        await db.rollback()
                        b.status = BroadcastStatus.FAILED
                        b.finished_at = datetime.utcnow()
                        await db.commit()
        except Exception as e:
            logger.error("process_broadcasts task error: %s", e)
        await asyncio.sleep(BROADCAST_CHECK_INTERVAL)

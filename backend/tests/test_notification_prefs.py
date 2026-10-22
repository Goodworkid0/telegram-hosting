"""Notification preferences saved in Settings must actually suppress delivery."""
import pytest
from httpx import AsyncClient
from sqlalchemy import select, func

from app.models import Notification
from app.telegram import create_notification


async def _login(client, tid):
    r = await client.post(f"/api/auth/dev-login?telegram_id={tid}")
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _uid(client, headers):
    r = await client.get("/api/users/me", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def _count(db, uid, type_):
    return await db.scalar(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == uid, Notification.type == type_
        )
    )


@pytest.mark.asyncio
async def test_notification_preferences_suppress_delivery(client: AsyncClient, db):
    headers = await _login(client, 870001)
    uid = await _uid(client, headers)

    r = await client.put("/api/auth/profile",
                         json={"notification_preferences": {"followers": False, "reputation": True}},
                         headers=headers)
    assert r.status_code == 200, r.text

    # Opted-out type: dropped entirely.
    await create_notification(db, user_id=uid, type="new_follower", title="follow!")
    # Explicitly-enabled type: delivered.
    await create_notification(db, user_id=uid, type="reputation", title="+rep")
    # Non-optional type: always delivered.
    await create_notification(db, user_id=uid, type="file_sold", title="sold")
    await db.commit()

    assert await _count(db, uid, "new_follower") == 0
    assert await _count(db, uid, "reputation") == 1
    assert await _count(db, uid, "file_sold") == 1


@pytest.mark.asyncio
async def test_no_preferences_set_delivers_everything(client: AsyncClient, db):
    headers = await _login(client, 870002)
    uid = await _uid(client, headers)

    await create_notification(db, user_id=uid, type="new_follower", title="follow!")
    await db.commit()
    assert await _count(db, uid, "new_follower") == 1

import pytest
from httpx import AsyncClient
from sqlalchemy import select


async def _login(client, tid):
    r = await client.post(f"/api/auth/dev-login?telegram_id={tid}")
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_create_broadcast_requires_admin(client: AsyncClient):
    user = await _login(client, 990001)
    r = await client.post("/api/admin/broadcasts",
                          json={"title": "Hi", "send_inbox": True}, headers=user)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_broadcast_validation(client: AsyncClient):
    admin = await _login(client, 444444444)
    # No channel selected.
    r = await client.post("/api/admin/broadcasts",
                          json={"title": "X", "send_inbox": False, "send_bot": False}, headers=admin)
    assert r.status_code == 400
    # Invalid role.
    r = await client.post("/api/admin/broadcasts",
                          json={"title": "X", "send_inbox": True, "target_role": "WIZARD"}, headers=admin)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_broadcast_delivery_to_inbox(client: AsyncClient, db):
    from app.tasks import _deliver_broadcast
    from app.models import Broadcast, BroadcastStatus, Notification

    admin = await _login(client, 444444444)
    await _login(client, 990010)
    await _login(client, 990011)

    r = await client.post("/api/admin/broadcasts",
                          json={"title": "Sale!", "body": "50% off", "send_inbox": True, "send_bot": False},
                          headers=admin)
    assert r.status_code == 200, r.text
    bid = r.json()["id"]
    assert r.json()["status"] == "PENDING"
    assert r.json()["total_recipients"] >= 3  # admin + 2 users

    # Deliver it (inbox-only, so no Telegram calls).
    b = await db.get(Broadcast, bid)
    b.status = BroadcastStatus.SENDING
    await db.commit()
    await _deliver_broadcast(db, b)

    assert b.status == BroadcastStatus.DONE
    assert b.sent_count >= 3
    notifs = (await db.execute(
        select(Notification).where(Notification.type == "announcement", Notification.title == "Sale!")
    )).scalars().all()
    assert len(notifs) >= 3


@pytest.mark.asyncio
async def test_broadcast_targets_by_role(client: AsyncClient, db):
    from app.tasks import _deliver_broadcast
    from app.models import Broadcast, BroadcastStatus, Notification, User, UserRole

    admin = await _login(client, 444444444)
    mod = await _login(client, 990020)
    mod_id = (await client.get("/api/users/me", headers=mod)).json()["id"]
    await client.put(f"/api/admin/users/{mod_id}/role", params={"role": "MODERATOR"}, headers=admin)

    r = await client.post("/api/admin/broadcasts",
                          json={"title": "Mods only", "send_inbox": True, "target_role": "MODERATOR"},
                          headers=admin)
    bid = r.json()["id"]
    b = await db.get(Broadcast, bid)
    b.status = BroadcastStatus.SENDING
    await db.commit()
    await _deliver_broadcast(db, b)

    # Only the moderator got it.
    notifs = (await db.execute(
        select(Notification).where(Notification.type == "announcement", Notification.title == "Mods only")
    )).scalars().all()
    assert {n.user_id for n in notifs} == {mod_id}


@pytest.mark.asyncio
async def test_broadcast_link_scheme_validated(client: AsyncClient):
    admin = await _login(client, 444444444)
    bad = await client.post("/api/admin/broadcasts",
                            json={"title": "x", "send_inbox": True, "link": "javascript:alert(1)"}, headers=admin)
    assert bad.status_code == 422, bad.text
    ok = await client.post("/api/admin/broadcasts",
                           json={"title": "x", "send_inbox": True, "link": "/shop"}, headers=admin)
    assert ok.status_code == 200, ok.text


@pytest.mark.asyncio
async def test_broadcast_resumes_from_cursor(client: AsyncClient, db):
    from app.tasks import _deliver_broadcast
    from app.models import Broadcast, BroadcastStatus, Notification

    admin = await _login(client, 444444444)
    early = await _login(client, 992001)
    late = await _login(client, 992002)
    early_id = (await client.get("/api/users/me", headers=early)).json()["id"]
    late_id = (await client.get("/api/users/me", headers=late)).json()["id"]

    r = await client.post("/api/admin/broadcasts",
                          json={"title": "Resume", "send_inbox": True}, headers=admin)
    b = await db.get(Broadcast, r.json()["id"])
    b.status = BroadcastStatus.SENDING
    b.last_delivered_user_id = early_id   # pretend we already reached everyone up to `early`
    await db.commit()
    await _deliver_broadcast(db, b)

    got = {n.user_id for n in (await db.execute(
        select(Notification).where(Notification.type == "announcement", Notification.title == "Resume")
    )).scalars().all()}
    assert late_id in got            # users after the cursor are delivered
    assert early_id not in got       # users at/before the cursor are skipped (no double-send)

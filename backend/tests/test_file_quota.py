"""Free-tier daily download quota + subscription bypass + lazy expiry."""
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models import SharedFile, SharedFileStatus, User


async def _login(client, tid):
    r = await client.post(f"/api/auth/dev-login?telegram_id={tid}")
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _uid(client, headers):
    return (await client.get("/api/users/me", headers=headers)).json()["id"]


async def _make_file(db, name, uploader_id=None, price=None):
    f = SharedFile(
        file_unique_id=f"quota_{name}",
        file_id=f"FAKE_{name}",
        kind="document",
        file_name=name,
        uploader_id=uploader_id,
        status=SharedFileStatus.APPROVED,
        price=price,
    )
    db.add(f)
    await db.commit()
    await db.refresh(f)
    return f.id


@pytest.fixture(autouse=True)
def _fake_delivery(monkeypatch):
    """Deliveries must not hit Telegram in tests."""
    async def ok(*a, **kw):
        return True, None
    monkeypatch.setattr("app.routers.files.send_file", ok)


@pytest.mark.asyncio
async def test_free_quota_enforced_and_bypasses(client: AsyncClient, db):
    admin = await _login(client, 444444444)
    user = await _login(client, 660001)
    uid = await _uid(client, user)

    # 6 free files by someone else + one own file + one paywalled file.
    other = await _login(client, 660002)
    other_id = await _uid(client, other)
    free_ids = [await _make_file(db, f"free{i}.bin", uploader_id=other_id) for i in range(6)]
    own_id = await _make_file(db, "own.bin", uploader_id=uid)
    paid_id = await _make_file(db, "paid.bin", uploader_id=other_id, price=5.0)

    # Quota endpoint starts at 0/5.
    q = (await client.get("/api/files/quota", headers=user)).json()
    assert q["used_today"] == 0 and q["limit"] == 5 and q["subscription_active"] is False

    # 5 free downloads succeed, the 6th is refused with quota_exceeded.
    for fid in free_ids[:5]:
        r = await client.post(f"/api/files/{fid}/download", headers=user)
        assert r.status_code == 200, r.text
    r = await client.post(f"/api/files/{free_ids[5]}/download", headers=user)
    assert r.status_code == 429, r.text
    assert r.json()["detail"]["code"] == "quota_exceeded"

    q = (await client.get("/api/files/quota", headers=user)).json()
    assert q["used_today"] == 5

    # Own file still downloadable — no quota.
    assert (await client.post(f"/api/files/{own_id}/download", headers=user)).status_code == 200

    # Purchased paywalled file downloads despite exhausted quota and doesn't consume it.
    await client.put(f"/api/admin/users/{uid}/balance",
                     params={"amount": 20.0, "reason": "seed"}, headers=admin)
    assert (await client.post(f"/api/files/{paid_id}/purchase", headers=user)).status_code == 200
    assert (await client.post(f"/api/files/{paid_id}/download", headers=user)).status_code == 200
    q = (await client.get("/api/files/quota", headers=user)).json()
    assert q["used_today"] == 5  # unchanged


@pytest.mark.asyncio
async def test_subscription_lifts_quota_and_expires_lazily(client: AsyncClient, db):
    user = await _login(client, 661001)
    uid = await _uid(client, user)
    other = await _login(client, 661002)
    other_id = await _uid(client, other)
    free_ids = [await _make_file(db, f"sub{i}.bin", uploader_id=other_id) for i in range(7)]

    # Active subscription: unlimited.
    u = await db.get(User, uid)
    u.is_premium = True
    u.premium_until = datetime.utcnow() + timedelta(days=10)
    await db.commit()

    for fid in free_ids[:6]:
        assert (await client.post(f"/api/files/{fid}/download", headers=user)).status_code == 200
    q = (await client.get("/api/files/quota", headers=user)).json()
    assert q["subscription_active"] is True and q["used_today"] == 0

    # Expire the subscription: next download flips is_premium off and the quota applies.
    u = await db.get(User, uid)
    u.premium_until = datetime.utcnow() - timedelta(minutes=1)
    await db.commit()

    # Quota is fresh (subscriber downloads weren't counted) so this one succeeds…
    assert (await client.post(f"/api/files/{free_ids[6]}/download", headers=user)).status_code == 200
    # …but the flag is now lazily cleared.
    u = await db.get(User, uid)
    await db.refresh(u)
    assert u.is_premium is False
    q = (await client.get("/api/files/quota", headers=user)).json()
    assert q["subscription_active"] is False and q["used_today"] == 1

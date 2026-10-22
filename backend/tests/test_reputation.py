"""Reputation gating: giver needs approved uploads; cooldown; counters."""
import pytest
from httpx import AsyncClient

from app.models import SharedFile, SharedFileStatus, AppSettings


async def _login(client, tid):
    r = await client.post(f"/api/auth/dev-login?telegram_id={tid}")
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _uid(client, headers):
    return (await client.get("/api/users/me", headers=headers)).json()["id"]


async def _approved_upload(db, uploader_id, name):
    f = SharedFile(
        file_unique_id=f"rep_{name}",
        file_id=f"FAKE_{name}",
        kind="document",
        file_name=name,
        uploader_id=uploader_id,
        status=SharedFileStatus.APPROVED,
    )
    db.add(f)
    await db.commit()


@pytest.mark.asyncio
async def test_rep_requires_approved_uploads(client: AsyncClient, db):
    s = await db.get(AppSettings, 1)
    if not s:
        s = AppSettings(id=1)
        db.add(s)
    s.min_uploads_for_rep = 1
    await db.commit()

    giver = await _login(client, 664001)
    target = await _login(client, 664002)
    giver_id = await _uid(client, giver)
    target_id = await _uid(client, target)

    # No approved uploads yet → 403.
    r = await client.post(f"/api/reputation/users/{target_id}",
                          json={"is_positive": True, "comment": "great"}, headers=giver)
    assert r.status_code == 403, r.text

    # With an approved upload → allowed; target counter increments.
    await _approved_upload(db, giver_id, "proof.zip")
    r = await client.post(f"/api/reputation/users/{target_id}",
                          json={"is_positive": True, "comment": "great"}, headers=giver)
    assert r.status_code == 200, r.text

    rep = (await client.get(f"/api/reputation/users/{target_id}", headers=giver)).json()
    assert rep["total_positive"] == 1

    # 24h cooldown against the same target.
    r = await client.post(f"/api/reputation/users/{target_id}",
                          json={"is_positive": False}, headers=giver)
    assert r.status_code == 400

    # Self-rep always rejected.
    r = await client.post(f"/api/reputation/users/{giver_id}",
                          json={"is_positive": True}, headers=giver)
    assert r.status_code == 400

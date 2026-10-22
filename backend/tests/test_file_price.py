"""Uploader pricing (PATCH /api/files/{id}/price) + /mine listing."""
import pytest
from httpx import AsyncClient

from app.models import SharedFile, SharedFileStatus


async def _login(client, tid):
    r = await client.post(f"/api/auth/dev-login?telegram_id={tid}")
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _uid(client, headers):
    return (await client.get("/api/users/me", headers=headers)).json()["id"]


async def _make_file(db, name, uploader_id, status=SharedFileStatus.APPROVED):
    f = SharedFile(
        file_unique_id=f"price_{name}",
        file_id=f"FAKE_{name}",
        kind="document",
        file_name=name,
        uploader_id=uploader_id,
        status=status,
    )
    db.add(f)
    await db.commit()
    await db.refresh(f)
    return f.id


@pytest.mark.asyncio
async def test_set_and_clear_price(client: AsyncClient, db):
    owner = await _login(client, 663001)
    stranger = await _login(client, 663002)
    oid = await _uid(client, owner)
    fid = await _make_file(db, "mine.zip", oid)

    # Non-owner can't price it.
    r = await client.patch(f"/api/files/{fid}/price", json={"price": 5}, headers=stranger)
    assert r.status_code == 403

    # Negative price rejected by validation.
    r = await client.patch(f"/api/files/{fid}/price", json={"price": -1}, headers=owner)
    assert r.status_code == 422

    # Owner sets a price.
    r = await client.patch(f"/api/files/{fid}/price", json={"price": 4.5}, headers=owner)
    assert r.status_code == 200 and r.json()["price"] == 4.5

    # Board shows it.
    listing = (await client.get("/api/files", headers=stranger)).json()
    item = next(i for i in listing["items"] if i["id"] == fid)
    assert item["price"] == 4.5 and item["is_own"] is False

    # Owner clears it (null → free); 0 also means free.
    r = await client.patch(f"/api/files/{fid}/price", json={"price": None}, headers=owner)
    assert r.status_code == 200 and r.json()["price"] is None


@pytest.mark.asyncio
async def test_mine_lists_all_statuses(client: AsyncClient, db):
    owner = await _login(client, 663003)
    oid = await _uid(client, owner)
    approved = await _make_file(db, "a.zip", oid)
    pending = await _make_file(db, "p.zip", oid, status=SharedFileStatus.PENDING)

    mine = (await client.get("/api/files/mine", headers=owner)).json()
    ids = {i["id"]: i for i in mine["items"]}
    assert approved in ids and pending in ids
    assert ids[pending]["status"] == "PENDING"
    assert "total_earnings" in mine

    # Pending files never appear on the public board.
    board = (await client.get("/api/files", headers=owner)).json()
    assert all(i["id"] != pending for i in board["items"])

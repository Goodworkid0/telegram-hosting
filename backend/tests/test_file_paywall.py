"""Paywalled files: purchase money flow, access control, ledger consistency."""
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models import SharedFile, SharedFileStatus, FilePurchase, LedgerEntry, AppSettings


async def _login(client, tid):
    r = await client.post(f"/api/auth/dev-login?telegram_id={tid}")
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _uid(client, headers):
    return (await client.get("/api/users/me", headers=headers)).json()["id"]


async def _make_file(db, name, uploader_id, price):
    f = SharedFile(
        file_unique_id=f"pay_{name}",
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
    async def ok(*a, **kw):
        return True, None
    monkeypatch.setattr("app.routers.files.send_file", ok)


@pytest.mark.asyncio
async def test_paywall_purchase_flow_and_ledger(client: AsyncClient, db):
    """402 before purchase; purchase debits buyer by price, credits uploader by
    price minus fee, writes both ledger rows and one FilePurchase; then the
    download works and both ledgers reconcile."""
    s = await db.get(AppSettings, 1)
    if not s:
        s = AppSettings(id=1)
        db.add(s)
    s.platform_fee_percent = 10.0
    await db.commit()

    admin = await _login(client, 444444444)
    seller = await _login(client, 662001)
    buyer = await _login(client, 662002)
    seller_id = await _uid(client, seller)
    buyer_id = await _uid(client, buyer)

    fid = await _make_file(db, "toolkit.zip", seller_id, 10.0)

    # Unpurchased download → 402 with the price.
    r = await client.post(f"/api/files/{fid}/download", headers=buyer)
    assert r.status_code == 402, r.text
    assert r.json()["detail"] == {"code": "purchase_required", "price": 10.0}

    # Broke buyer can't purchase.
    assert (await client.post(f"/api/files/{fid}/purchase", headers=buyer)).status_code == 400

    await client.put(f"/api/admin/users/{buyer_id}/balance",
                     params={"amount": 50.0, "reason": "seed"}, headers=admin)

    r = await client.post(f"/api/files/{fid}/purchase", headers=buyer)
    assert r.status_code == 200, r.text
    assert r.json()["balance"] == 40.0

    # Uploader credited 9.00 (10 − 10% fee).
    seller_me = (await client.get("/api/users/me", headers=seller)).json()
    assert seller_me["balance"] == 9.0, seller_me["balance"]

    # Exactly one FilePurchase with correct snapshots.
    fp = (await db.execute(select(FilePurchase).where(
        FilePurchase.buyer_id == buyer_id, FilePurchase.file_id == fid,
    ))).scalars().all()
    assert len(fp) == 1
    assert float(fp[0].price) == 10.0
    assert float(fp[0].uploader_credit) == 9.0
    assert fp[0].fee_percent == 10.0

    # Both ledger rows exist against the file.
    rows = (await db.execute(select(LedgerEntry).where(
        LedgerEntry.ref_type == "shared_file", LedgerEntry.ref_id == fid,
    ))).scalars().all()
    types = sorted(e.entry_type for e in rows)
    assert types == ["file_purchase", "file_sale"]

    # Double purchase and self-purchase rejected.
    assert (await client.post(f"/api/files/{fid}/purchase", headers=buyer)).status_code == 400
    assert (await client.post(f"/api/files/{fid}/purchase", headers=seller)).status_code == 400

    # Purchased download now succeeds.
    assert (await client.post(f"/api/files/{fid}/download", headers=buyer)).status_code == 200

    # Both parties' ledgers reconcile exactly.
    for uid in (buyer_id, seller_id):
        rec = (await client.get(f"/api/admin/users/{uid}/ledger", headers=admin)).json()["reconciliation"]
        assert rec["balance"]["consistent"] is True, (uid, rec)

    # Board listing marks it purchased for the buyer.
    listing = (await client.get("/api/files", headers=buyer)).json()
    item = next(i for i in listing["items"] if i["id"] == fid)
    assert item["is_purchased"] is True and item["price"] == 10.0

    # Free files can't be "purchased".
    free_id = await _make_file(db, "free.txt", seller_id, None)
    assert (await client.post(f"/api/files/{free_id}/purchase", headers=buyer)).status_code == 400

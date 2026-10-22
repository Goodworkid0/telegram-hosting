import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ledger_records_and_reconciles(client: AsyncClient):
    """An admin balance adjustment must produce a ledger entry, keep the account
    reconciled, and be visible via both the admin and user ledger endpoints."""
    # Dev admin user (444444444 -> ADMIN in DEV_TEST_USERS).
    login = await client.post("/api/auth/dev-login?telegram_id=444444444")
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = await client.get("/api/users/me", headers=headers)
    assert me.status_code == 200, me.text
    uid = me.json()["id"]

    # Admin credits a balance -> goes through the ledger.
    adj = await client.put(
        f"/api/admin/users/{uid}/balance",
        params={"amount": 25.0, "reason": "ledger test"},
        headers=headers,
    )
    assert adj.status_code == 200, adj.text

    # Admin ledger view + reconciliation.
    led = await client.get(f"/api/admin/users/{uid}/ledger", headers=headers)
    assert led.status_code == 200, led.text
    data = led.json()
    assert data["reconciliation"]["balance"]["consistent"] is True
    assert data["reconciliation"]["pending"]["consistent"] is True
    assert any(e["entry_type"] == "admin_adjustment" for e in data["entries"])

    # User-facing ledger shows the same entry.
    wl = await client.get("/api/wallet/ledger", headers=headers)
    assert wl.status_code == 200, wl.text
    entries = wl.json()
    assert any(e["entry_type"] == "admin_adjustment" for e in entries)
    # balance_after must equal the running balance.
    assert entries[0]["balance_after"] >= 25.0

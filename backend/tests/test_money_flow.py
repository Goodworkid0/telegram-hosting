from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.money import to_money, apply_percent


def test_money_helpers_rounding():
    assert to_money(0.1) + to_money(0.2) == Decimal("0.30")        # no float drift
    assert apply_percent(100, 10) == Decimal("10.00")
    assert apply_percent(Decimal("10.05"), 10) == Decimal("1.01")  # 1.005 -> half-up
    assert to_money(None) == Decimal("0.00")
    assert apply_percent(50, 0) == Decimal("0.00")


async def _login(client, tid):
    r = await client.post(f"/api/auth/dev-login?telegram_id={tid}")
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _uid(client, headers):
    r = await client.get("/api/users/me", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_withdraw_fee_decimal_and_broadcast(client: AsyncClient, db):
    """Withdrawal applies the % fee exactly, debits balance, broadcasts (in-memory
    SSE path must not choke on Decimal), and reconciles."""
    from app.models import AppSettings
    s = await db.get(AppSettings, 1)
    if not s:
        s = AppSettings(id=1); db.add(s)
    s.withdrawal_fee_percent = 5.0
    s.min_withdrawal_amount = 10.0
    await db.commit()

    admin = await _login(client, 444444444)
    u = await _login(client, 870001)
    uid = await _uid(client, u)
    await client.put(f"/api/admin/users/{uid}/balance", params={"amount": 100.0, "reason": "seed"}, headers=admin)

    addr = "4" + "A" * 94  # valid-shaped XMR address (95 chars, starts with 4)
    w = await client.post("/api/wallet/withdraw", json={"amount": 40.0, "address": addr}, headers=u)
    assert w.status_code == 200, w.text

    me = (await client.get("/api/users/me", headers=u)).json()
    assert me["balance"] == 60.0, me["balance"]  # 100 - 40

    wl = (await client.get("/api/wallet/withdrawals", headers=u)).json()
    assert wl[0]["amount"] == 40.0
    assert wl[0]["fee_amount"] == 2.0    # 5% of 40
    assert wl[0]["net_amount"] == 38.0

    rec = (await client.get(f"/api/admin/users/{uid}/ledger", headers=admin)).json()["reconciliation"]
    assert rec["balance"]["consistent"] is True, rec



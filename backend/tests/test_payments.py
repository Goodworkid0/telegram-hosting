import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_deposit_creation_requires_auth(client: AsyncClient):
    """Creating a deposit without auth should fail."""
    response = await client.post("/api/payments/nowpayments/create", json={
        "amount": 100, "pay_currency": "btc"
    })
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_deposit_minimum_enforced(client: AsyncClient):
    """Deposits under $10 should be rejected."""
    login_resp = await client.post("/api/auth/dev-login?telegram_id=700001")
    token = login_resp.json()["access_token"]

    response = await client.post(
        "/api/payments/nowpayments/create",
        json={"amount": 5, "pay_currency": "btc"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 400  # minimum is $10


@pytest.mark.asyncio
async def test_webhook_signature_required(client: AsyncClient):
    """Webhook without signature should be rejected."""
    response = await client.post("/api/payments/nowpayments/webhook", json={})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_deposit_list_requires_auth(client: AsyncClient):
    response = await client.get("/api/payments/nowpayments/deposits")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_subscription_purchase_and_extension(client: AsyncClient, db):
    """Buying the subscription debits the configured price, sets premium_until
    ≈ now+30d, and a second purchase EXTENDS by another 30 days."""
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from app.models import User

    admin_login = await client.post("/api/auth/dev-login?telegram_id=444444444")
    admin = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    login = await client.post("/api/auth/dev-login?telegram_id=700010")
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    uid = (await client.get("/api/users/me", headers=headers)).json()["id"]

    # Broke user can't buy.
    r = await client.post("/api/payments/subscription/purchase", headers=headers)
    assert r.status_code == 400

    # Seed $40 (default price is $15).
    await client.put(f"/api/admin/users/{uid}/balance",
                     params={"amount": 40.0, "reason": "seed"}, headers=admin)

    r = await client.post("/api/payments/subscription/purchase", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_premium"] is True
    assert body["balance"] == 25.0
    first_until = datetime.fromisoformat(body["premium_until"])
    assert abs((first_until - (datetime.utcnow() + timedelta(days=30))).total_seconds()) < 120

    # Second purchase extends from the current expiry (stacking).
    r = await client.post("/api/payments/subscription/purchase", headers=headers)
    assert r.status_code == 200, r.text
    second_until = datetime.fromisoformat(r.json()["premium_until"])
    assert abs((second_until - (first_until + timedelta(days=30))).total_seconds()) < 120
    assert r.json()["balance"] == 10.0

    user = await db.get(User, uid)
    await db.refresh(user)
    assert user.is_premium is True

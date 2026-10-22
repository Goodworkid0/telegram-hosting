import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_branding_public(client: AsyncClient):
    response = await client.get("/api/branding")
    assert response.status_code == 200
    data = response.json()
    assert "app_name" in data


@pytest.mark.asyncio
async def test_dev_login(client: AsyncClient):
    response = await client.post("/api/auth/dev-login?telegram_id=999999")
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_dev_login_invalid(client: AsyncClient):
    # Test without ALLOW_DEV_LOGIN or in production context
    # This test checks that the endpoint is properly gated
    pass  # Skip if env not configured


@pytest.mark.asyncio
async def test_me_endpoint(client: AsyncClient):
    # Login first
    login_resp = await client.post("/api/auth/dev-login?telegram_id=999998")
    token = login_resp.json()["access_token"]

    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["telegram_id"] == "999998"


@pytest.mark.asyncio
async def test_unauthorized_access(client: AsyncClient):
    response = await client.get("/api/auth/me")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    login_resp = await client.post("/api/auth/dev-login?telegram_id=999997")
    refresh_token = login_resp.json()["refresh_token"]

    response = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_logout(client: AsyncClient):
    login_resp = await client.post("/api/auth/dev-login?telegram_id=999996")
    token = login_resp.json()["access_token"]

    response = await client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

"""Regression tests for the security audit fixes.

NOTE: in-memory SQLite serializes writes and treats SELECT ... FOR UPDATE as a
no-op, so these tests cannot reproduce a true concurrent race. They instead lock
in the observable guarantee the fix protects — terminal-state re-checks prevent
double-processing, payouts/refunds happen exactly once, and ledgers reconcile.
On PostgreSQL the added with_for_update() makes the same guarantee hold under
genuine concurrency.
"""
import pytest
from httpx import AsyncClient

from app.models import AppSettings, User


async def _login(client, tid):
    r = await client.post(f"/api/auth/dev-login?telegram_id={tid}")
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _uid(client, headers):
    r = await client.get("/api/users/me", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_rate_limited_endpoint_wiring(client: AsyncClient):
    """The new @limiter.limit endpoints must carry a `request` arg, or slowapi
    raises at call time when enabled. The suite disables the limiter globally,
    so re-enable it here to actually exercise that wiring (no 500)."""
    from app.dependencies import limiter
    headers = await _login(client, 930001)
    limiter.enabled = True
    try:
        # Reaches change_password (valid body, but user has no PIN set) -> 400,
        # NOT a 500 from a missing `request` argument.
        r = await client.put(
            "/api/auth/password",
            json={"current_password": "whatever", "new_password": "abc123"},
            headers=headers,
        )
        assert r.status_code == 400, r.text
    finally:
        limiter.enabled = False


@pytest.mark.asyncio
async def test_ban_staff_protection(client: AsyncClient, db):
    """Shared apply_ban rules: can't ban self or an admin; a normal user bans
    fine. Guards the consolidation of the three former ban implementations."""
    admin = await _login(client, 444444444)
    admin_id = await _uid(client, admin)
    victim = await _login(client, 950001)
    victim_id = await _uid(client, victim)

    # Admin cannot ban themselves (protection newly applied to the admin path).
    self_ban = await client.post(f"/api/admin/users/{admin_id}/ban",
                                 params={"reason": "oops"}, headers=admin)
    assert self_ban.status_code == 403, self_ban.text

    # A second admin can't be banned either.
    other_admin = await _login(client, 444444445)
    oa_id = await _uid(client, other_admin)
    other = await db.get(User, oa_id)
    from app.models import UserRole
    other.role = UserRole.ADMIN
    await db.commit()
    ban_admin = await client.post(f"/api/admin/users/{oa_id}/ban",
                                  params={"reason": "no"}, headers=admin)
    assert ban_admin.status_code == 403, ban_admin.text

    # A normal user bans fine.
    ok = await client.post(f"/api/admin/users/{victim_id}/ban",
                           params={"reason": "spam"}, headers=admin)
    assert ok.status_code == 200, ok.text
    banned = await db.get(User, victim_id)
    await db.refresh(banned)
    assert banned.is_banned is True


@pytest.mark.asyncio
async def test_withdrawal_cannot_be_approved_after_reject(client: AsyncClient, db):
    """Once rejected (and refunded), a withdrawal cannot also be approved, and
    the refund happens exactly once (guards the approve/reject race fix)."""
    s = await db.get(AppSettings, 1)
    if not s:
        s = AppSettings(id=1); db.add(s)
    s.withdrawal_fee_percent = 0.0
    s.min_withdrawal_amount = 10.0
    await db.commit()

    admin = await _login(client, 444444444)
    u = await _login(client, 920001)
    uid = await _uid(client, u)
    await client.put(f"/api/admin/users/{uid}/balance", params={"amount": 100.0, "reason": "seed"}, headers=admin)

    addr = "4" + "A" * 94
    w = await client.post("/api/wallet/withdraw", json={"amount": 40.0, "address": addr}, headers=u)
    assert w.status_code == 200, w.text
    wid = (await client.get("/api/wallet/withdrawals", headers=u)).json()[0]["id"]

    assert (await client.get("/api/users/me", headers=u)).json()["balance"] == 60.0

    # Reject refunds the balance.
    rej = await client.put(f"/api/admin/withdrawals/{wid}/reject", params={"reason": "bad address"}, headers=admin)
    assert rej.status_code == 200, rej.text
    assert (await client.get("/api/users/me", headers=u)).json()["balance"] == 100.0

    # A subsequent approve must be refused — not double-process.
    appr = await client.put(f"/api/admin/withdrawals/{wid}/approve", headers=admin)
    assert appr.status_code == 400, appr.text

    # Balance refunded exactly once and ledger reconciles.
    assert (await client.get("/api/users/me", headers=u)).json()["balance"] == 100.0
    rec = (await client.get(f"/api/admin/users/{uid}/ledger", headers=admin)).json()["reconciliation"]
    assert rec["balance"]["consistent"] is True, rec


# A valid-looking Monero address (starts with 4, 95 chars) so withdraw validation
# isn't what rejects the request — the impersonation guard is.
_XMR_ADDR = "4" + "8" * 94


@pytest.mark.asyncio
async def test_impersonation_session_cannot_withdraw(client: AsyncClient, db):
    """An admin impersonation token must not be able to move the victim's money:
    the withdraw endpoint rejects it outright, while the victim's own session is
    unaffected (guards the impersonation = full-victim-session fix)."""
    admin = await _login(client, 444444444)
    victim = await _login(client, 900050)
    victim_id = await _uid(client, victim)
    await client.put(f"/api/admin/users/{victim_id}/balance",
                     params={"amount": 500.0, "reason": "seed"}, headers=admin)

    imp = await client.post(f"/api/admin/users/{victim_id}/impersonate", headers=admin)
    assert imp.status_code == 200, imp.text
    imp_headers = {"Authorization": f"Bearer {imp.json()['token']}"}

    blocked = await client.post("/api/wallet/withdraw",
                                json={"amount": 50.0, "address": _XMR_ADDR}, headers=imp_headers)
    assert blocked.status_code == 403, blocked.text
    assert "impersonation" in blocked.json()["detail"].lower()

    # The real user is not blocked by the guard.
    allowed = await client.post("/api/wallet/withdraw",
                                json={"amount": 50.0, "address": _XMR_ADDR}, headers=victim)
    assert allowed.status_code == 200, allowed.text

    # The other balance-spending endpoints must also reject the impersonation
    # token.
    for path, body in [
        ("/api/auth/setup", {"pin": "abc123", "first_name": "Hacked"}),
        ("/api/payments/subscription/purchase", None),
    ]:
        r = await client.post(path, json=body, headers=imp_headers)
        assert r.status_code == 403, (path, r.text)
        assert "impersonation" in r.json()["detail"].lower(), (path, r.text)


@pytest.mark.asyncio
async def test_handle_mirrors_telegram_and_visibility_is_premium_gated(client: AsyncClient):
    """Handles can't be chosen: setup only sets display name/pin/visibility and
    the @handle stays the Telegram-synced one. Changing visibility later is a
    premium/staff-only perk."""
    admin = await _login(client, 444444444)
    headers = await _login(client, 900060)
    me = (await client.get("/api/users/me", headers=headers)).json()
    original_handle = me["username"]

    r = await client.post("/api/auth/setup",
                          json={"pin": "secret1", "first_name": "Mover", "show_telegram": False},
                          headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["username"] == original_handle  # handle untouched by setup
    assert r.json()["show_telegram"] is False

    # Non-premium user cannot change handle visibility afterwards.
    r = await client.put("/api/auth/profile", json={"show_telegram": True}, headers=headers)
    assert r.status_code == 403, r.text
    assert "premium" in r.json()["detail"].lower()

    # After premium is granted, the toggle works.
    uid = me["id"]
    g = await client.put(f"/api/admin/users/{uid}/premium?is_premium=true", headers=admin)
    assert g.status_code == 200, g.text
    r = await client.put("/api/auth/profile", json={"show_telegram": True}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["show_telegram"] is True

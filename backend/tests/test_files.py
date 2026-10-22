import pytest
from httpx import AsyncClient


async def _login(client, tid):
    r = await client.post(f"/api/auth/dev-login?telegram_id={tid}")
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _uid(client, headers):
    return (await client.get("/api/users/me", headers=headers)).json()["id"]


async def _make_file(db, uploader_id=None, status="PENDING", name="secret.zip"):
    from app.models import SharedFile, SharedFileStatus
    f = SharedFile(
        file_unique_id=f"uniq_{name}_{status}",
        file_id="BAADdummyfileid",
        kind="document",
        file_name=name,
        file_size=1234,
        uploader_id=uploader_id,
        uploader_tg_id="777000",
        retrieval_chat_id="-1001",
        retrieval_message_id=5,
        status=SharedFileStatus[status],
    )
    db.add(f)
    await db.commit()
    await db.refresh(f)
    return f.id


@pytest.mark.asyncio
async def test_files_list_requires_auth(client: AsyncClient):
    assert (await client.get("/api/files")).status_code in (401, 403)


@pytest.mark.asyncio
async def test_admin_files_requires_mod(client: AsyncClient):
    user = await _login(client, 770001)
    assert (await client.get("/api/admin/files", headers=user)).status_code == 403


@pytest.mark.asyncio
async def test_file_only_visible_after_approval(client: AsyncClient, db):
    admin = await _login(client, 444444444)
    viewer = await _login(client, 770002)
    file_id = await _make_file(db, name="approve_me.pdf")

    # PENDING → not on the public board.
    listing = (await client.get("/api/files", headers=viewer)).json()
    assert all(i["id"] != file_id for i in listing["items"])

    # It IS in the admin pending queue.
    q = (await client.get("/api/admin/files?status=pending", headers=admin)).json()
    assert any(i["id"] == file_id for i in q["items"])

    # Approve → now on the public board.
    assert (await client.post(f"/api/admin/files/{file_id}/approve", headers=admin)).status_code == 200
    listing = (await client.get("/api/files", headers=viewer)).json()
    assert any(i["id"] == file_id for i in listing["items"])

    # Reject → hidden again.
    assert (await client.post(f"/api/admin/files/{file_id}/reject", json={"reason": "nope"}, headers=admin)).status_code == 200
    listing = (await client.get("/api/files", headers=viewer)).json()
    assert all(i["id"] != file_id for i in listing["items"])


@pytest.mark.asyncio
async def test_download_nonexistent_or_unapproved(client: AsyncClient, db):
    viewer = await _login(client, 770003)
    assert (await client.post("/api/files/999999/download", headers=viewer)).status_code == 404
    pending = await _make_file(db, status="PENDING", name="hidden.bin")
    # A pending file is not deliverable via the public endpoint.
    assert (await client.post(f"/api/files/{pending}/download", headers=viewer)).status_code == 404


@pytest.mark.asyncio
async def test_admin_delete_file(client: AsyncClient, db):
    admin = await _login(client, 444444444)
    file_id = await _make_file(db, status="APPROVED", name="del.txt")
    assert (await client.delete(f"/api/admin/files/{file_id}", headers=admin)).status_code == 200
    # Gone from the queue.
    q = (await client.get("/api/admin/files?status=all", headers=admin)).json()
    assert all(i["id"] != file_id for i in q["items"])


@pytest.mark.asyncio
async def test_category_crud_and_gating(client: AsyncClient):
    admin = await _login(client, 444444444)
    user = await _login(client, 771001)

    # Non-admin can't create categories.
    assert (await client.post("/api/admin/file-categories", json={"name": "X"}, headers=user)).status_code == 403

    c = await client.post("/api/admin/file-categories", json={"name": "Wallpapers"}, headers=admin)
    assert c.status_code == 200, c.text
    cid = c.json()["id"]

    # Duplicate name rejected (case-insensitive).
    assert (await client.post("/api/admin/file-categories", json={"name": "wallpapers"}, headers=admin)).status_code == 400

    # Rename.
    r = await client.patch(f"/api/admin/file-categories/{cid}", json={"name": "Wallpapers HD"}, headers=admin)
    assert r.status_code == 200 and r.json()["name"] == "Wallpapers HD"


@pytest.mark.asyncio
async def test_approve_with_category_and_filter(client: AsyncClient, db):
    admin = await _login(client, 444444444)
    viewer = await _login(client, 771002)
    cid = (await client.post("/api/admin/file-categories", json={"name": "Docs"}, headers=admin)).json()["id"]
    file_id = await _make_file(db, name="report.pdf")

    # Approve into the category.
    r = await client.post(f"/api/admin/files/{file_id}/approve", json={"category_id": cid}, headers=admin)
    assert r.status_code == 200, r.text

    # Public list shows the category name.
    listing = (await client.get("/api/files", headers=viewer)).json()
    item = next(i for i in listing["items"] if i["id"] == file_id)
    assert item["category_id"] == cid and item["category_name"] == "Docs"

    # Filter by category returns it; filtering by another (uncategorized=0) doesn't.
    inCat = (await client.get(f"/api/files?category_id={cid}", headers=viewer)).json()
    assert any(i["id"] == file_id for i in inCat["items"])
    uncat = (await client.get("/api/files?category_id=0", headers=viewer)).json()
    assert all(i["id"] != file_id for i in uncat["items"])

    # Public categories endpoint lists the active category.
    cats = (await client.get("/api/files/categories", headers=viewer)).json()
    assert any(c["id"] == cid for c in cats)

    # Deleting the category makes the file uncategorized (not deleted).
    assert (await client.delete(f"/api/admin/file-categories/{cid}", headers=admin)).status_code == 200
    listing = (await client.get("/api/files", headers=viewer)).json()
    item = next(i for i in listing["items"] if i["id"] == file_id)
    assert item["category_id"] is None

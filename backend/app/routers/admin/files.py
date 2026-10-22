"""Admin (ACP): moderation queue for user-dropped bot files."""
from app.routers.admin.common import *  # noqa: F401,F403

from datetime import datetime as _dt
from app.models import SharedFile, SharedFileStatus, FileCategory
from app.routers.files import serialize_file
from app.schemas import (
    SharedFileRejectRequest, SharedFileApproveRequest, SharedFileCategoryRequest,
    FileCategoryResponse, FileCategoryCreate, FileCategoryUpdate,
)

router = APIRouter()


async def _resolve_category(db, category_id):
    """Return a valid category_id or None; 404 if a non-null id doesn't exist."""
    if not category_id:
        return None
    cat = await db.get(FileCategory, category_id)
    if not cat:
        raise HTTPException(404, "Category not found")
    return cat.id


@router.get("/files")
async def admin_list_files(
    status: str = Query("pending"),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    current_user: User = Depends(get_current_moderator),
    db: AsyncSession = Depends(get_db),
):
    """List files by moderation status (default: the pending review queue)."""
    query = select(SharedFile).options(
        selectinload(SharedFile.uploader),
        selectinload(SharedFile.category),
        selectinload(SharedFile.suggested_category),
    )
    status_l = (status or "").lower()
    if status_l != "all":
        try:
            st = SharedFileStatus[status.upper()]
        except KeyError:
            st = SharedFileStatus.PENDING
        query = query.where(SharedFile.status == st)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.order_by(desc(SharedFile.created_at))
        .offset((page - 1) * per_page).limit(per_page)
    )
    items = [serialize_file(f, include_admin=True) for f in result.scalars().all()]
    return {"items": items, "total": total or 0, "page": page, "per_page": per_page}


@router.post("/files/{file_id}/approve")
async def admin_approve_file(
    file_id: int,
    payload: SharedFileApproveRequest = SharedFileApproveRequest(),
    current_user: User = Depends(get_current_moderator),
    db: AsyncSession = Depends(get_db),
):
    f = await db.get(SharedFile, file_id)
    if not f:
        raise HTTPException(404, "File not found")
    f.category_id = await _resolve_category(db, payload.category_id)
    f.status = SharedFileStatus.APPROVED
    f.reviewed_by_id = current_user.id
    f.reviewed_at = _dt.utcnow()
    f.reject_reason = None
    await db.commit()
    return {"ok": True, "status": "APPROVED"}


@router.post("/files/{file_id}/category")
async def admin_set_file_category(
    file_id: int,
    payload: SharedFileCategoryRequest,
    current_user: User = Depends(get_current_moderator),
    db: AsyncSession = Depends(get_db),
):
    """Change a file's category (works on already-approved files too)."""
    f = await db.get(SharedFile, file_id)
    if not f:
        raise HTTPException(404, "File not found")
    f.category_id = await _resolve_category(db, payload.category_id)
    await db.commit()
    return {"ok": True, "category_id": f.category_id}


# ---- Category CRUD ----

@router.get("/file-categories", response_model=list[FileCategoryResponse])
async def admin_list_categories(
    current_user: User = Depends(get_current_moderator),
    db: AsyncSession = Depends(get_db),
):
    """All categories (incl. inactive) with the count of files in each."""
    result = await db.execute(
        select(FileCategory).order_by(FileCategory.sort_order, FileCategory.name)
    )
    cats = result.scalars().all()
    counts = dict((await db.execute(
        select(SharedFile.category_id, func.count(SharedFile.id))
        .where(SharedFile.category_id.isnot(None))
        .group_by(SharedFile.category_id)
    )).all())
    out = []
    for c in cats:
        r = FileCategoryResponse.model_validate(c)
        r.file_count = int(counts.get(c.id, 0))
        out.append(r)
    return out


@router.post("/file-categories", response_model=FileCategoryResponse)
async def admin_create_category(
    payload: FileCategoryCreate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    name = payload.name.strip()
    exists = await db.scalar(select(FileCategory).where(func.lower(FileCategory.name) == name.lower()))
    if exists:
        raise HTTPException(400, "A category with that name already exists")
    cat = FileCategory(name=name, sort_order=payload.sort_order)
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return FileCategoryResponse.model_validate(cat)


@router.patch("/file-categories/{category_id}", response_model=FileCategoryResponse)
async def admin_update_category(
    category_id: int,
    payload: FileCategoryUpdate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    cat = await db.get(FileCategory, category_id)
    if not cat:
        raise HTTPException(404, "Category not found")
    if payload.name is not None:
        new_name = payload.name.strip()
        clash = await db.scalar(select(FileCategory).where(
            func.lower(FileCategory.name) == new_name.lower(), FileCategory.id != category_id,
        ))
        if clash:
            raise HTTPException(400, "A category with that name already exists")
        cat.name = new_name
    if payload.sort_order is not None:
        cat.sort_order = payload.sort_order
    if payload.is_active is not None:
        cat.is_active = payload.is_active
    await db.commit()
    await db.refresh(cat)
    return FileCategoryResponse.model_validate(cat)


@router.delete("/file-categories/{category_id}")
async def admin_delete_category(
    category_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a category; its files fall back to uncategorized."""
    cat = await db.get(FileCategory, category_id)
    if not cat:
        raise HTTPException(404, "Category not found")
    from sqlalchemy import update as _update
    await db.execute(
        _update(SharedFile).where(SharedFile.category_id == category_id).values(category_id=None)
    )
    await db.delete(cat)
    await db.commit()
    return {"ok": True}


@router.post("/files/{file_id}/reject")
async def admin_reject_file(
    file_id: int,
    payload: SharedFileRejectRequest,
    current_user: User = Depends(get_current_moderator),
    db: AsyncSession = Depends(get_db),
):
    f = await db.get(SharedFile, file_id)
    if not f:
        raise HTTPException(404, "File not found")
    f.status = SharedFileStatus.REJECTED
    f.reviewed_by_id = current_user.id
    f.reviewed_at = _dt.utcnow()
    f.reject_reason = (payload.reason or "").strip() or None
    await db.commit()
    return {"ok": True, "status": "REJECTED"}


@router.delete("/files/{file_id}")
async def admin_delete_file(
    file_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Hard-remove the board entry. The channel copies remain as an archive."""
    f = await db.get(SharedFile, file_id)
    if not f:
        raise HTTPException(404, "File not found")
    await db.delete(f)
    await db.commit()
    return {"ok": True}

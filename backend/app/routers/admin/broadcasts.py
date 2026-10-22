"""Admin (ACP): compose + queue advertisements/announcements to users' in-app
inbox and/or Telegram DM. Actual delivery is done by the background worker
(app/tasks.py process_broadcasts) so it can be throttled to Telegram limits."""
from app.routers.admin.common import *  # noqa: F401,F403

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from app.models import Broadcast, BroadcastStatus

router = APIRouter()

VALID_ROLES = {"USER", "MODERATOR", "ADMIN"}


class BroadcastCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: Optional[str] = Field(None, max_length=4000)
    link: Optional[str] = Field(None, max_length=500)
    send_inbox: bool = True
    send_bot: bool = False
    target_role: Optional[str] = None  # None/"" = all users

    @field_validator("link")
    @classmethod
    def _safe_link(cls, v):
        """Only allow in-app paths or http(s) — never javascript:/data: etc.,
        so the stored link can't become a scripted href if rendering changes."""
        if not v:
            return v
        v = v.strip()
        if not (v.startswith("/") or v.startswith("http://") or v.startswith("https://")):
            raise ValueError("Link must be an in-app path (/…) or an http(s) URL")
        return v


def _serialize(b: Broadcast) -> dict:
    return {
        "id": b.id,
        "title": b.title,
        "body": b.body,
        "link": b.link,
        "send_inbox": bool(b.send_inbox),
        "send_bot": bool(b.send_bot),
        "target_role": b.target_role,
        "status": b.status.value if b.status else "PENDING",
        "total_recipients": b.total_recipients or 0,
        "sent_count": b.sent_count or 0,
        "failed_count": b.failed_count or 0,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "finished_at": b.finished_at.isoformat() if b.finished_at else None,
    }


async def _recipient_filter(role: Optional[str]):
    """Build the WHERE conditions for the target audience."""
    conds = [User.is_active == True, User.is_banned == False]
    if role:
        conds.append(User.role == UserRole[role])
    return conds


@router.get("/broadcasts")
async def list_broadcasts(
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    total = await db.scalar(select(func.count(Broadcast.id)))
    result = await db.execute(
        select(Broadcast).order_by(desc(Broadcast.created_at))
        .offset((page - 1) * per_page).limit(per_page)
    )
    return {
        "items": [_serialize(b) for b in result.scalars().all()],
        "total": total or 0, "page": page, "per_page": per_page,
    }


@router.post("/broadcasts")
async def create_broadcast(
    payload: BroadcastCreate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if not (payload.send_inbox or payload.send_bot):
        raise HTTPException(400, "Pick at least one channel (inbox and/or Telegram DM)")

    role = (payload.target_role or "").strip().upper() or None
    if role and role not in VALID_ROLES:
        raise HTTPException(400, "Invalid target role")

    # Snapshot the audience size now (informational; the worker re-queries at send).
    total = await db.scalar(
        select(func.count(User.id)).where(*(await _recipient_filter(role)))
    )

    b = Broadcast(
        title=payload.title.strip(),
        body=(payload.body or "").strip() or None,
        link=(payload.link or "").strip() or None,
        send_inbox=payload.send_inbox,
        send_bot=payload.send_bot,
        target_role=role,
        status=BroadcastStatus.PENDING,
        total_recipients=int(total or 0),
        created_by_id=current_user.id,
    )
    db.add(b)
    await db.commit()
    await db.refresh(b)
    return _serialize(b)

"""
Hosting - Telegram Mini App File Hosting
FastAPI Backend (port 8000 in production)
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import asyncio
import os
import uuid
import logging
from pathlib import Path
from sqlalchemy import text

from app.config import ENVIRONMENT, IS_PRODUCTION
from app.database import create_tables
from app.dependencies import limiter
from app.routers import (
    auth, admin, payments, notifications,
    wallet, reputation, users, sse,
    files,
)
from app.scheduler import run_background_scheduler

logger = logging.getLogger(__name__)

# Whether THIS process should run the periodic background loops. A Redis leader
# lock (in app.scheduler) ensures the loops execute in exactly one process even
# if several have this enabled, so it's safe to leave on. Set to "false" on web
# workers when a dedicated `worker` process runs the scheduler instead.
RUN_BACKGROUND_TASKS = os.getenv("RUN_BACKGROUND_TASKS", "true").lower() == "true"


def _resolve_allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "").strip()
    if raw:
        return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]

    webapp_url = os.getenv("WEBAPP_URL", "").strip().rstrip("/")
    if webapp_url:
        return [webapp_url]

    if ENVIRONMENT == "production":
        return []

    return [
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    scheduler_task = None
    if RUN_BACKGROUND_TASKS:
        scheduler_task = asyncio.create_task(run_background_scheduler())
    yield
    if scheduler_task:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass

app = FastAPI(
    title="Hosting API",
    description="Telegram Mini App File Hosting Platform",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if not IS_PRODUCTION else None,
    redoc_url=None,
    # Don't expose the full API schema (incl. every admin route) in production.
    openapi_url="/openapi.json" if not IS_PRODUCTION else None,
)

# ---- Rate Limiter registration ----
# SlowAPIMiddleware is what actually enforces the limiter's default_limits on
# endpoints that lack an explicit @limiter.limit decorator. Without it only
# decorated routes were throttled, leaving most endpoints unlimited.
app.state.limiter = limiter


async def _rate_limit_detail_handler(request: Request, exc: RateLimitExceeded):
    """429s must follow the app-wide {"detail": ...} error shape (the default
    slowapi handler returns {"error": ...}, which no frontend code reads)."""
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
    )

app.add_exception_handler(RateLimitExceeded, _rate_limit_detail_handler)
app.add_middleware(SlowAPIMiddleware)

# ---- CORS ----
ALLOWED_ORIGINS = _resolve_allowed_origins()

if ENVIRONMENT == "production" and not ALLOWED_ORIGINS:
    logger.warning(
        "PRODUCTION with empty ALLOWED_ORIGINS — "
        "CORS will reject all cross-origin requests. "
        "Set ALLOWED_ORIGINS or WEBAPP_URL in your .env file."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=bool(ALLOWED_ORIGINS),
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)

# ---- Maintenance mode ----
# Admin-toggled AppSettings.maintenance_mode blocks all non-admin API traffic
# with 503. Cached briefly so the check doesn't add a DB query per request.
_maintenance_cache = {"value": False, "at": 0.0}
_MAINTENANCE_TTL_SECONDS = 15.0

# Prefixes that stay reachable during maintenance: auth (admins must be able to
# sign in), branding (the frontend reads the flag itself), uploads, and the
# NOWPayments IPN webhook (signature-verified; blocking it would drop deposit
# confirmations sent while maintenance is on).
_MAINTENANCE_ALLOWED_PREFIXES = (
    "/api/auth",
    "/api/branding",
    "/api/uploads",
    "/api/payments/nowpayments/webhook",
)


async def _maintenance_enabled() -> bool:
    import time
    now = time.monotonic()
    if now - _maintenance_cache["at"] > _MAINTENANCE_TTL_SECONDS:
        from app.database import async_session
        from app.models import AppSettings
        from sqlalchemy import select
        try:
            async with async_session() as db:
                flag = await db.scalar(
                    select(AppSettings.maintenance_mode).where(AppSettings.id == 1)
                )
        except Exception:
            flag = _maintenance_cache["value"]
        _maintenance_cache["value"] = bool(flag)
        _maintenance_cache["at"] = now
    return _maintenance_cache["value"]


async def _is_staff_request(request: Request) -> bool:
    """Resolve the bearer token to a user and allow moderators/admins through.

    Fails closed: any error (bad token, DB unavailable) means "not staff", so
    the caller serves the maintenance 503 instead of a 500.
    """
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return False
    from jose import jwt, JWTError
    from app.auth import SECRET_KEY, ALGORITHM
    try:
        payload = jwt.decode(auth_header[7:], SECRET_KEY, algorithms=[ALGORITHM])
        # Only a real access token grants the bypass — reject refresh tokens.
        if payload.get("type") not in (None, "access"):
            return False
        telegram_id = payload.get("sub")
        tv_claim = payload.get("tv")
    except JWTError:
        return False
    if not telegram_id:
        return False
    from app.database import async_session
    from app.models import User, UserRole
    from sqlalchemy import select
    try:
        async with async_session() as db:
            row = (await db.execute(
                select(User.role, User.token_version).where(User.telegram_id == telegram_id)
            )).first()
    except Exception:
        return False
    if not row:
        return False
    role, token_version = row
    # Honor force-logout: a revoked token must not keep staff bypass.
    if tv_claim is not None and int(tv_claim) != int(token_version or 0):
        return False
    return role in (UserRole.ADMIN, UserRole.MODERATOR)


@app.middleware("http")
async def maintenance_gate(request: Request, call_next):
    path = request.url.path
    if (
        path.startswith("/api/")
        and not path.startswith(_MAINTENANCE_ALLOWED_PREFIXES)
        and await _maintenance_enabled()
        and not await _is_staff_request(request)
    ):
        return JSONResponse(
            status_code=503,
            content={"detail": "The app is down for maintenance. Please check back soon."},
        )
    return await call_next(request)


# ---- Security Headers + HSTS ----
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    incoming_request_id = request.headers.get("x-request-id", "").strip()
    request_id = incoming_request_id or str(uuid.uuid4())
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Dynamic API responses must never be edge/browser cached (a CDN like
    # Cloudflare would otherwise serve stale data — e.g. a deleted thread still
    # showing as "latest" for an hour). Uploaded images (/api/uploads) are
    # immutable uuid files and stay cacheable.
    _path = request.url.path
    if _path.startswith("/api/") and not _path.startswith("/api/uploads"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["CDN-Cache-Control"] = "no-store"
    # X-Frame-Options omitted — Telegram WebApp uses iframe/webview
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    return response


@app.middleware("http")
async def handle_unexpected_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
        logger.exception(
            "unhandled_exception method=%s path=%s request_id=%s",
            request.method,
            request.url.path,
            request_id,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "request_id": request_id,
            },
            headers={"X-Request-ID": str(request_id)},
        )

# Routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(users.router)  # Users has /api/users prefix
app.include_router(reputation.router)  # Reputation has /api/reputation prefix
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(payments.router, prefix="/api/payments", tags=["Payments"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(wallet.router, prefix="/api/wallet", tags=["Wallet"])
app.include_router(sse.router)
app.include_router(files.router)

@app.get("/")
async def root():
    # If frontend is built, serve it; otherwise return API info
    index = Path(__file__).resolve().parent.parent / "frontend" / "dist" / "index.html"
    if index.is_file():
        return FileResponse(str(index))
    return {"message": "Hosting API", "version": "1.0.0"}

@app.get("/api/branding")
async def public_branding():
    """Public branding endpoint — no auth required."""
    from app.database import async_session
    from app.models import AppSettings
    from sqlalchemy import select
    async with async_session() as db:
        result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
        s = result.scalar_one_or_none()
        from app.pricing import all_prices
        prices = await all_prices(db)
        if not s:
            return {"app_name": "Hosting", "logo_url": None, "show_logo": True, "bot_username": "HostingBot", "maintenance_mode": False, "announcements_url": None, "official_group_url": None, "support_username": None, "support_display_name": None, "prices": prices}
        return {
            "app_name": s.app_name,
            "logo_url": s.logo_url,
            "show_logo": s.show_logo if s.show_logo is not None else True,
            "bot_username": s.bot_username,
            "maintenance_mode": s.maintenance_mode,
            "announcements_url": getattr(s, 'announcements_url', None),
            "official_group_url": getattr(s, 'official_group_url', None),
            "support_username": getattr(s, 'support_username', None),
            "support_display_name": getattr(s, 'support_display_name', None),
            "prices": prices,
        }

@app.get("/health")
async def health():
    """Liveness probe — returns 200 if process is running."""
    return {"status": "healthy"}


@app.post("/api/client-error")
async def client_error(request: Request):
    """Diagnostic sink for front-end errors (window.onerror / unhandledrejection).

    Lets a client-side crash leave a trace in the server logs (visible via
    `docker compose logs api`). Temporary aid for tracing the Telegram Desktop
    webview crash — safe to remove once that's resolved.
    """
    try:
        raw = (await request.body()).decode("utf-8", "replace")[:4000]
    except Exception:
        raw = "<unreadable body>"
    logger.error("CLIENT_ERROR %s", raw)
    return {"ok": True}


@app.get("/health/ready")
async def health_ready():
    """Readiness probe — checks DB and Redis connectivity."""
    checks = {"database": False, "redis": False}
    try:
        from app.database import engine
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as e:
        checks["database"] = str(e)

    try:
        from app.redis_client import get_redis
        r = get_redis()
        if r:
            await r.ping()
        checks["redis"] = True
    except Exception as e:
        checks["redis"] = str(e)

    all_ok = all(v is True for v in checks.values())
    status_code = 200 if all_ok else 503
    return JSONResponse(content={"status": "ready" if all_ok else "degraded", "checks": checks}, status_code=status_code)


# ---- Serve uploaded files (avatars, images) ----
UPLOADS_DIR = Path(__file__).resolve().parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)
(UPLOADS_DIR / "avatars").mkdir(exist_ok=True)
(UPLOADS_DIR / "banners").mkdir(exist_ok=True)
app.mount("/api/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


# ---- Serve Frontend (SPA) ----
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if FRONTEND_DIR.is_dir():
    # Serve static assets (js, css, images, etc.)
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="static-assets")

    @app.middleware("http")
    async def spa_middleware(request: Request, call_next):
        response = await call_next(request)
        # If no API or static route matched (404) and it's a GET for a non-API path, serve SPA
        path = request.url.path
        if (
            response.status_code == 404
            and request.method == "GET"
            and not path.startswith(("/api/", "/docs", "/redoc", "/openapi.json"))
        ):
            # Check if it's a real file in dist. Resolve and confine to
            # FRONTEND_DIR so a crafted path (e.g. ../../etc/passwd) served
            # directly to uvicorn can't escape the static root.
            file_path = (FRONTEND_DIR / path.lstrip("/")).resolve()
            if file_path.is_file() and file_path.is_relative_to(FRONTEND_DIR):
                return FileResponse(str(file_path))
            return FileResponse(str(FRONTEND_DIR / "index.html"))
        return response

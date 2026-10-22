# IMPORTANT: configure the environment BEFORE importing the app, so the engine
# binds to an isolated in-memory database instead of the real hosting.db, and the
# app runs in a development (non-production) configuration for the test run.
import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("ALLOW_DEV_LOGIN", "true")
os.environ.setdefault("ALLOW_AUTO_CREATE_TABLES", "true")

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from main import app
from app.database import async_session, create_tables

# Disable rate limiting in tests — the suite makes many dev-login calls from a
# single IP and would otherwise trip the per-IP limits.
from app.dependencies import limiter as _limiter
_limiter.enabled = False


@pytest_asyncio.fixture(scope="session")
async def _init_db():
    await create_tables()


@pytest_asyncio.fixture
async def client(_init_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db():
    async with async_session() as session:
        yield session

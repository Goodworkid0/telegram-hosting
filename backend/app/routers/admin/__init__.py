"""Admin router package. Aggregates domain sub-routers into one `router`
mounted at /api/admin (see main.py)."""
from fastapi import APIRouter
from . import users, finance, settings, files, broadcasts

router = APIRouter()
for _m in (users, finance, settings, files, broadcasts):
    router.include_router(_m.router)

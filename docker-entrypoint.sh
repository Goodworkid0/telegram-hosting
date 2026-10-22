#!/bin/bash
set -e

echo "==> Forum — Docker Entrypoint"

# Wait for PostgreSQL
if [ -n "$DATABASE_URL" ] && echo "$DATABASE_URL" | grep -q "postgresql"; then
    echo "==> Waiting for PostgreSQL..."
    until python -c "
import asyncio, sys
sys.path.insert(0, '/app')
from app.database import engine
from sqlalchemy import text
async def check():
    async with engine.connect() as conn:
        await conn.execute(text('SELECT 1'))
asyncio.run(check())
" 2>/dev/null; do
        echo "  Waiting..."
        sleep 2
    done
    echo "==> PostgreSQL ready"
fi

# Wait for Redis
if [ -n "$REDIS_URL" ]; then
    echo "==> Waiting for Redis..."
    until python -c "import redis; r=redis.from_url('$REDIS_URL'); r.ping()" 2>/dev/null; do
        echo "  Waiting..."
        sleep 2
    done
    echo "==> Redis ready"
fi

# Detect whether the database has ever been stamped by Alembic. We must do this
# BEFORE create_all, because create_all would otherwise build the full current
# schema and make a fresh DB indistinguishable from a migrated one.
ALEMBIC_STAMPED=$(python -c "
import asyncio, sys
sys.path.insert(0, '/app')
from app.database import engine
from sqlalchemy import text
async def check():
    async with engine.connect() as conn:
        try:
            await conn.execute(text('SELECT 1 FROM alembic_version LIMIT 1'))
            print('yes')
        except Exception:
            print('no')
asyncio.run(check())
" 2>/dev/null || echo "no")

# Create base tables + stamp on fresh DB; apply migrations on stamped DB.
if [ "$ALEMBIC_STAMPED" = "yes" ]; then
    echo "==> Applying Alembic migrations..."
    python -m alembic upgrade head
else
    echo "==> Fresh database — creating base tables then stamping..."
    python -c "
import asyncio, sys
sys.path.insert(0, '/app')
from app.database import engine, Base
from app.models import *  # noqa
async def create():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('Base tables created')
asyncio.run(create())
" || echo "  (tables may already exist)"
    python -m alembic stamp head
fi

echo "==> Starting application..."
exec "$@"

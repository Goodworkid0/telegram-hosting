"""Seed script to populate the hosting database with initial dev data.

Creates AppSettings, an admin + a few test users, file categories, and sample
shared files (free + paywalled). The sample files use FAKE telegram file_ids —
they list on the board but can't actually be delivered; drop real files into
the bot for end-to-end delivery testing.
"""
import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select

from app.database import async_session, engine, Base
from app.models import (
    User, UserRole, AppSettings, FileCategory, SharedFile, SharedFileStatus,
)


async def seed_database():
    async with async_session() as db:
        print("🌱 Starting hosting database seeding...")

        # ─── AppSettings ─────────────────────────────────────────────────────
        settings_check = await db.execute(select(AppSettings).where(AppSettings.id == 1))
        if not settings_check.scalar_one_or_none():
            db.add(AppSettings(
                id=1,
                app_name="Hosting",
                bot_username="HostingBot",
                withdrawal_fee_percent=2.0,
                subscription_price=15.0,
                platform_fee_percent=10.0,
                free_downloads_per_day=5,
                min_uploads_for_rep=1,
            ))
            print("✅ Created AppSettings")

        # ─── Users ───────────────────────────────────────────────────────────
        users_data = [
            {"telegram_id": "admin_1001", "username": "admin", "first_name": "Admin",
             "role": UserRole.ADMIN, "balance": 1000.0, "rep_positive": 50},
            {"telegram_id": "uploader_1002", "username": "uploader", "first_name": "Uploader",
             "role": UserRole.USER, "balance": 25.0, "rep_positive": 12},
            {"telegram_id": "downloader_1003", "username": "downloader", "first_name": "Downloader",
             "role": UserRole.USER, "balance": 100.0},
        ]
        users = {}
        for data in users_data:
            existing = await db.scalar(select(User).where(User.telegram_id == data["telegram_id"]))
            if existing:
                users[data["username"]] = existing
                continue
            u = User(**data, is_setup_complete=True, last_seen_at=datetime.utcnow())
            db.add(u)
            await db.flush()
            users[data["username"]] = u
            print(f"✅ Created user @{data['username']}")

        # ─── File categories ──────────────────────────────────────────────────
        categories = {}
        for i, name in enumerate(["Software", "E-books", "Media"]):
            existing = await db.scalar(select(FileCategory).where(FileCategory.name == name))
            if existing:
                categories[name] = existing
                continue
            c = FileCategory(name=name, sort_order=i)
            db.add(c)
            await db.flush()
            categories[name] = c
            print(f"✅ Created category {name}")

        # ─── Sample shared files (fake file_ids — board display only) ────────
        uploader = users.get("uploader")
        samples = [
            {"file_unique_id": "seed-free-1", "file_name": "starter-pack.zip",
             "file_size": 12_582_912, "category": "Software", "price": None},
            {"file_unique_id": "seed-free-2", "file_name": "guide.pdf",
             "file_size": 2_097_152, "category": "E-books", "price": None},
            {"file_unique_id": "seed-paid-1", "file_name": "premium-toolkit.zip",
             "file_size": 52_428_800, "category": "Software", "price": 9.99},
        ]
        for smp in samples:
            existing = await db.scalar(
                select(SharedFile).where(SharedFile.file_unique_id == smp["file_unique_id"])
            )
            if existing:
                continue
            db.add(SharedFile(
                file_unique_id=smp["file_unique_id"],
                file_id=f"FAKE_{smp['file_unique_id']}",
                kind="document",
                file_name=smp["file_name"],
                mime_type="application/octet-stream",
                file_size=smp["file_size"],
                uploader_id=uploader.id if uploader else None,
                uploader_tg_id=uploader.telegram_id if uploader else None,
                category_id=categories[smp["category"]].id,
                status=SharedFileStatus.APPROVED,
                reviewed_at=datetime.utcnow() - timedelta(days=1),
                price=smp["price"],
            ))
            print(f"✅ Created sample file {smp['file_name']}")

        await db.commit()
        print("🌱 Seeding done.")


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_database()


if __name__ == "__main__":
    asyncio.run(main())

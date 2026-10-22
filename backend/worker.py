"""Standalone background-task worker.

Runs ONLY the periodic scheduler (broadcast delivery, ban/mute expiry), so the
web workers can stay request-only.

Leader election in app.scheduler ensures the loops run exactly once even if this
worker is scaled to multiple replicas or a web worker also has them enabled.
"""
import asyncio
import logging

from app.config import IS_PRODUCTION  # noqa: F401 — loads .env / centralizes config
from app.scheduler import run_background_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("worker")


async def _main() -> None:
    logger.info("background worker starting")
    try:
        await run_background_scheduler()
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("background worker stopped")


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass

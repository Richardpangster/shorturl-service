"""FastAPI application entry point for ShortURL Service."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.cache import close_redis
from app.config import settings
from app.database import AsyncSessionLocal, init_db
from app.routers import api, pages, redirect
from app.services import cleanup_expired_urls, cleanup_expired_urls_with_cache

logger = logging.getLogger(__name__)


async def _cleanup_loop() -> None:
    """Background task that periodically cleans up expired URL records.

    Runs every ``settings.cleanup_interval_hours`` hours.
    If the interval is 0, the loop exits immediately (disabled).
    """
    interval_seconds = settings.cleanup_interval_hours * 3600
    if interval_seconds <= 0:
        logger.info("Periodic cleanup disabled (CLEANUP_INTERVAL_HOURS=0).")
        return

    logger.info(
        "Periodic cleanup scheduler started (interval: %dh).",
        settings.cleanup_interval_hours,
    )
    while True:
        await asyncio.sleep(interval_seconds)
        async with AsyncSessionLocal() as session:
            try:
                count = await cleanup_expired_urls_with_cache(session)
                await session.commit()
                logger.info("Periodic cleanup removed %d expired URL(s).", count)
            except Exception as exc:  # pragma: no cover
                logger.warning("Periodic cleanup failed: %s", exc)
                await session.rollback()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown lifecycle.

    On startup:
        - Initialises database tables.
        - Cleans up any expired short URL records.
        - Starts background periodic cleanup task.

    On shutdown:
        - Cancels the periodic cleanup task.
        - Closes Redis connection pool.
    """
    # Startup: init DB and run immediate cleanup
    await init_db()

    async with AsyncSessionLocal() as session:
        try:
            count = await cleanup_expired_urls(session)
            await session.commit()
            if count:
                logger.info("Startup cleanup removed %d expired URL(s).", count)
        except Exception as exc:  # pragma: no cover
            logger.warning("Startup cleanup failed: %s", exc)
            await session.rollback()

    # Start background cleanup scheduler
    cleanup_task = asyncio.create_task(_cleanup_loop())

    yield

    # Shutdown: cancel background task and close Redis
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    await close_redis()


app = FastAPI(
    title="ShortURL Service",
    description="A simple URL shortening service built with FastAPI.",
    version="1.0.0",
    lifespan=lifespan,
)

# Static files (CSS, etc.)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Routers — order matters: API and pages must come before the catch-all redirect.
app.include_router(pages.router)
app.include_router(api.router)
app.include_router(redirect.router)

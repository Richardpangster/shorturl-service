"""FastAPI application entry point for ShortURL Service."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.cache import close_redis
from app.database import AsyncSessionLocal, init_db
from app.routers import api, auth, pages, redirect
from app.services import cleanup_expired_urls

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown lifecycle.

    On startup:
        - Initialises database tables.
        - Cleans up any expired short URL records.

    On shutdown:
        - Closes Redis connection pool.
    """
    # Startup
    await init_db()

    # Clean up expired records on boot
    async with AsyncSessionLocal() as session:
        try:
            count = await cleanup_expired_urls(session)
            await session.commit()
            if count:
                logger.info("Startup cleanup removed %d expired URL(s).", count)
        except Exception as exc:  # pragma: no cover
            logger.warning("Startup cleanup failed: %s", exc)
            await session.rollback()

    yield

    # Shutdown
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
app.include_router(auth.router)
app.include_router(redirect.router)

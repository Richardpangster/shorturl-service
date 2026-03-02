"""FastAPI application entry point for ShortURL Service."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.cache import close_redis
from app.database import init_db
from app.routers import api, pages, redirect


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown lifecycle."""
    # Startup
    await init_db()
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
app.include_router(redirect.router)

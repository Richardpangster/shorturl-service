"""Business logic layer for ShortURL Service.

Handles short code generation, URL creation, redirect resolution,
statistics retrieval, and expiry enforcement.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache_delete, cache_get, cache_set
from app.config import settings
from app.models import URL

# Sentinel cache value that indicates a short code does NOT exist / is expired.
_CACHE_MISS_SENTINEL = "__NOT_FOUND__"


def _utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


def _generate_short_code() -> str:
    """Generate a cryptographically random URL-safe short code.

    Uses ``secrets.token_urlsafe`` which produces Base64 URL-safe characters
    (A-Z, a-z, 0-9, '-', '_').  We request enough bytes so that after
    truncation to ``SHORT_CODE_LENGTH`` we still have good entropy.

    Returns:
        A string of exactly ``settings.short_code_length`` characters.
    """
    # token_urlsafe(4) -> ~5-6 chars; generate a bit more and slice to be safe.
    raw = secrets.token_urlsafe(8)
    return raw[: settings.short_code_length]


async def create_short_url(
    db: AsyncSession,
    original_url: str,
    expire_days: Optional[int] = None,
) -> URL:
    """Create a new short URL record in the database.

    Generates a unique 6-character short code, retrying on collision.
    Caches the mapping in Redis after successful insert.

    Args:
        db:           Async SQLAlchemy session.
        original_url: The long URL to shorten.
        expire_days:  Days until expiry (default: ``settings.default_expire_days``).

    Returns:
        The newly created :class:`URL` ORM instance.
    """
    if expire_days is None:
        expire_days = settings.default_expire_days

    now = _utcnow()
    expires_at = now + timedelta(days=expire_days)

    # Retry loop — collision probability is extremely low but handle it anyway.
    for _ in range(10):
        short_code = _generate_short_code()

        # Check uniqueness in DB.
        existing = await db.execute(
            select(URL).where(URL.short_code == short_code)
        )
        if existing.scalar_one_or_none() is None:
            break
    else:
        raise RuntimeError("Failed to generate a unique short code after 10 attempts.")

    url_record = URL(
        short_code=short_code,
        original_url=original_url,
        created_at=now,
        expires_at=expires_at,
        visit_count=0,
        last_visited_at=None,
    )
    db.add(url_record)
    await db.flush()  # get the id without committing
    await db.refresh(url_record)

    # Cache mapping: short_code -> original_url
    ttl = int((expires_at - now).total_seconds())
    await cache_set(short_code, original_url, ttl=max(ttl, 1))

    return url_record


async def resolve_short_code(
    db: AsyncSession,
    short_code: str,
) -> Optional[str]:
    """Resolve a short code to its original URL, updating visit statistics.

    Checks the Redis cache first; falls back to the database on a cache miss.
    Returns ``None`` if the short code does not exist or has expired.

    Args:
        db:         Async SQLAlchemy session.
        short_code: The 6-character short code.

    Returns:
        The original URL string, or ``None`` if not found / expired.
    """
    # 1. Try cache first.
    cached = await cache_get(short_code)
    if cached == _CACHE_MISS_SENTINEL:
        return None
    if cached is not None:
        # Still update visit stats asynchronously via DB (best-effort).
        await _increment_visit(db, short_code)
        return cached

    # 2. Cache miss — query DB.
    result = await db.execute(
        select(URL).where(URL.short_code == short_code)
    )
    url_record: Optional[URL] = result.scalar_one_or_none()

    if url_record is None:
        # Negative cache to avoid DB hammering for non-existent codes.
        await cache_set(short_code, _CACHE_MISS_SENTINEL, ttl=60)
        return None

    # 3. Check expiry.
    if url_record.expires_at.replace(tzinfo=timezone.utc) < _utcnow():
        await cache_set(short_code, _CACHE_MISS_SENTINEL, ttl=60)
        return None

    # 4. Warm cache and update stats.
    ttl = int((url_record.expires_at.replace(tzinfo=timezone.utc) - _utcnow()).total_seconds())
    await cache_set(short_code, url_record.original_url, ttl=max(ttl, 1))
    await _increment_visit(db, short_code)

    return url_record.original_url


async def _increment_visit(db: AsyncSession, short_code: str) -> None:
    """Increment visit_count and update last_visited_at for a short code.

    Args:
        db:         Async SQLAlchemy session.
        short_code: The short code to update.
    """
    await db.execute(
        update(URL)
        .where(URL.short_code == short_code)
        .values(visit_count=URL.visit_count + 1, last_visited_at=_utcnow())
    )


async def get_url_stats(
    db: AsyncSession,
    short_code: str,
) -> Optional[URL]:
    """Retrieve a URL record for statistics, checking expiry.

    Args:
        db:         Async SQLAlchemy session.
        short_code: The short code to look up.

    Returns:
        The :class:`URL` record, or ``None`` if not found or expired.
    """
    result = await db.execute(
        select(URL).where(URL.short_code == short_code)
    )
    url_record: Optional[URL] = result.scalar_one_or_none()

    if url_record is None:
        return None

    if url_record.expires_at.replace(tzinfo=timezone.utc) < _utcnow():
        return None

    return url_record


async def delete_short_url(db: AsyncSession, short_code: str) -> bool:
    """Delete a short URL record and evict its cache entry.

    Args:
        db:         Async SQLAlchemy session.
        short_code: The short code to delete.

    Returns:
        True if a record was deleted, False if not found.
    """
    result = await db.execute(
        select(URL).where(URL.short_code == short_code)
    )
    url_record = result.scalar_one_or_none()
    if url_record is None:
        return False

    await db.delete(url_record)
    await cache_delete(short_code)
    return True

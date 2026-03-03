"""Business logic layer for ShortURL Service.

Handles short code generation, URL creation, redirect resolution,
statistics retrieval, expiry enforcement, and cleanup utilities.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.cache import cache_delete, cache_get, cache_set
from app.config import settings
from app.models import URL

# Sentinel cache value that indicates a short code does NOT exist / is expired.
_CACHE_MISS_SENTINEL = "__NOT_FOUND__"


class ShortCodeGenerationError(RuntimeError):
    """Raised when a unique short code cannot be generated after max retries."""

    pass


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

    Generates a unique short code, retrying on collision up to
    ``settings.short_code_max_retries`` times.  Uses ``IntegrityError``
    as the collision signal so there is no TOCTOU race between the
    existence check and the insert.

    Args:
        db:           Async SQLAlchemy session.
        original_url: The long URL to shorten.
        expire_days:  Days until expiry (default: ``settings.default_expire_days``).

    Returns:
        The newly created :class:`URL` ORM instance.

    Raises:
        ShortCodeGenerationError: If a unique code cannot be produced within
            ``settings.short_code_max_retries`` attempts.
    """
    if expire_days is None:
        expire_days = settings.default_expire_days

    now = _utcnow()
    expires_at = now + timedelta(days=expire_days)

    last_exc: Optional[IntegrityError] = None
    for attempt in range(settings.short_code_max_retries + 1):  # +1: first attempt + N retries
        short_code = _generate_short_code()

        url_record = URL(
            short_code=short_code,
            original_url=original_url,
            created_at=now,
            expires_at=expires_at,
            visit_count=0,
            last_visited_at=None,
        )
        db.add(url_record)

        try:
            await db.flush()  # get the id; raises IntegrityError on collision
            await db.refresh(url_record)
        except IntegrityError as exc:
            last_exc = exc
            await db.rollback()
            logger.warning(
                "Short code collision on attempt %d/%d (code=%r): %s",
                attempt + 1,
                settings.short_code_max_retries,
                short_code,
                exc,
            )
            continue

        # Success — warm the cache and return.
        ttl = int((expires_at - now).total_seconds())
        await cache_set(short_code, original_url, ttl=max(ttl, 1))
        return url_record

    raise ShortCodeGenerationError(
        f"Failed to generate a unique short code after "
        f"{settings.short_code_max_retries} attempts."
    ) from last_exc


async def resolve_short_code(
    db: AsyncSession,
    short_code: str,
) -> Optional[str]:
    """Resolve a short code to its original URL.

    Checks the Redis cache first; falls back to the database on a cache miss.
    Returns ``None`` if the short code does not exist or has expired.

    Note: Visit statistics are NOT updated here. Callers should invoke
    ``update_visit_stats`` as a background task after returning the response.

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

    # 4. Warm cache.
    ttl = int((url_record.expires_at.replace(tzinfo=timezone.utc) - _utcnow()).total_seconds())
    await cache_set(short_code, url_record.original_url, ttl=max(ttl, 1))

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


async def update_visit_stats(
    short_code: str,
    session_factory: Optional[Any] = None,
) -> None:
    """Update visit statistics for a short code using an independent DB session.

    Intended to be called as a FastAPI BackgroundTask so the redirect response
    is returned to the client immediately without waiting for the DB write.

    Uses its own session (not the request session) to avoid session-closed
    conflicts after the response has been sent.

    Args:
        short_code:      The short code whose statistics should be incremented.
        session_factory: Optional async session factory to use instead of the
                         default ``AsyncSessionLocal``. Useful for testing.
    """
    from app.database import AsyncSessionLocal

    factory = session_factory or AsyncSessionLocal
    async with factory() as session:
        try:
            await _increment_visit(session, short_code)
            await session.commit()
        except Exception as exc:  # pragma: no cover
            logger.warning("Background visit stats update failed for %r: %s", short_code, exc)
            await session.rollback()


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


async def cleanup_expired_urls(db: AsyncSession) -> int:
    """Delete all expired short URL records from the database.

    This should be called on startup or as a periodic maintenance task.
    Expired records are those where ``expires_at`` is in the past.

    Args:
        db: Async SQLAlchemy session.

    Returns:
        The number of records deleted.
    """
    now = _utcnow()
    result = await db.execute(
        delete(URL).where(URL.expires_at < now)
    )
    deleted_count: int = result.rowcount  # type: ignore[assignment]
    if deleted_count:
        logger.info("Cleaned up %d expired URL record(s).", deleted_count)
    return deleted_count

"""Redis cache layer for ShortURL Service.

Caches short_code -> original_url mappings to accelerate redirect lookups.
Falls back gracefully if Redis is unavailable.
"""

from typing import Optional

import redis.asyncio as aioredis

from app.config import settings

_redis_client: Optional[aioredis.Redis] = None

CACHE_TTL_SECONDS = 3600  # 1 hour default cache TTL


async def get_redis() -> Optional[aioredis.Redis]:
    """Return the global Redis client, initialising lazily.

    Returns None if Redis is not reachable, allowing the service to degrade
    gracefully and serve requests directly from the database.
    """
    global _redis_client
    if _redis_client is None:
        try:
            client = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=1,
            )
            await client.ping()
            _redis_client = client
        except Exception:
            return None
    return _redis_client


async def cache_get(key: str) -> Optional[str]:
    """Get a value from the cache by key.

    Args:
        key: Cache key (e.g. short_code).

    Returns:
        Cached value or None if absent / Redis unavailable.
    """
    client = await get_redis()
    if client is None:
        return None
    try:
        return await client.get(key)
    except Exception:
        return None


async def cache_set(key: str, value: str, ttl: int = CACHE_TTL_SECONDS) -> None:
    """Set a cache key with an expiry TTL.

    Args:
        key:   Cache key.
        value: Value to store.
        ttl:   Expiry in seconds (default 1 hour).
    """
    client = await get_redis()
    if client is None:
        return
    try:
        await client.set(key, value, ex=ttl)
    except Exception:
        pass


async def cache_delete(key: str) -> None:
    """Delete a cache key.

    Args:
        key: Cache key to evict.
    """
    client = await get_redis()
    if client is None:
        return
    try:
        await client.delete(key)
    except Exception:
        pass


async def close_redis() -> None:
    """Close the Redis connection pool on shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None

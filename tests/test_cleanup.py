"""Tests for periodic cleanup scheduler (Issue #9)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.models import URL
from app.services import cleanup_expired_urls_with_cache


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_cleanup_with_cache_deletes_expired(db_session):
    """cleanup_expired_urls_with_cache removes expired records and returns count."""
    now = _utcnow()

    expired = URL(
        short_code="EXPIR1",
        original_url="https://expired.example.com/",
        created_at=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),
        visit_count=0,
        last_visited_at=None,
    )
    active = URL(
        short_code="ACTIV1",
        original_url="https://active.example.com/",
        created_at=now,
        expires_at=now + timedelta(days=30),
        visit_count=0,
        last_visited_at=None,
    )
    db_session.add_all([expired, active])
    await db_session.flush()

    count = await cleanup_expired_urls_with_cache(db_session)
    await db_session.commit()

    assert count == 1


@pytest.mark.asyncio
async def test_cleanup_with_cache_evicts_redis(db_session):
    """cleanup_expired_urls_with_cache calls cache_delete for each expired code."""
    now = _utcnow()

    expired1 = URL(
        short_code="DEL001",
        original_url="https://del1.example.com/",
        created_at=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),
        visit_count=0,
        last_visited_at=None,
    )
    expired2 = URL(
        short_code="DEL002",
        original_url="https://del2.example.com/",
        created_at=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),
        visit_count=0,
        last_visited_at=None,
    )
    db_session.add_all([expired1, expired2])
    await db_session.flush()

    deleted_codes: list[str] = []

    async def _mock_cache_delete(key: str) -> None:
        deleted_codes.append(key)

    with patch("app.services.cache_delete", side_effect=_mock_cache_delete):
        count = await cleanup_expired_urls_with_cache(db_session)
    await db_session.commit()

    assert count == 2
    assert set(deleted_codes) == {"DEL001", "DEL002"}


@pytest.mark.asyncio
async def test_cleanup_with_cache_no_expired(db_session):
    """cleanup_expired_urls_with_cache returns 0 when nothing is expired."""
    now = _utcnow()
    active = URL(
        short_code="NOEXP1",
        original_url="https://noexp.example.com/",
        created_at=now,
        expires_at=now + timedelta(days=30),
        visit_count=0,
        last_visited_at=None,
    )
    db_session.add(active)
    await db_session.flush()

    count = await cleanup_expired_urls_with_cache(db_session)
    assert count == 0


@pytest.mark.asyncio
async def test_cleanup_interval_disabled(client):
    """When CLEANUP_INTERVAL_HOURS=0, _cleanup_loop exits immediately without sleeping."""
    import asyncio

    from app import config as cfg_module
    from app.main import _cleanup_loop

    original = cfg_module.settings.cleanup_interval_hours
    cfg_module.settings.cleanup_interval_hours = 0
    try:
        # Should return quickly (no sleep)
        await asyncio.wait_for(_cleanup_loop(), timeout=2.0)
    finally:
        cfg_module.settings.cleanup_interval_hours = original

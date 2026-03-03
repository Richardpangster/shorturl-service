"""Tests for ShortURL Service API endpoints (Task 1 & 2)."""

import pytest


# ---------------------------------------------------------------------------
# POST /api/shorten
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shorten_url_success(client):
    """Creating a short URL returns 201 with expected fields."""
    resp = await client.post(
        "/api/shorten",
        json={"url": "https://example.com/very/long/path?foo=bar"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "short_code" in data
    assert len(data["short_code"]) == 6
    assert data["original_url"] == "https://example.com/very/long/path?foo=bar"
    assert "short_url" in data
    assert data["short_code"] in data["short_url"]
    assert "expires_at" in data


@pytest.mark.asyncio
async def test_shorten_url_custom_expire(client):
    """Custom expire_days is accepted and reflected in the response."""
    resp = await client.post(
        "/api/shorten",
        json={"url": "https://example.com/", "expire_days": 7},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "expires_at" in data


@pytest.mark.asyncio
async def test_shorten_invalid_url(client):
    """Submitting a non-URL string returns 422 Unprocessable Entity."""
    resp = await client.post(
        "/api/shorten",
        json={"url": "not-a-valid-url"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /{short_code} — redirect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redirect_success(client):
    """A valid short code results in a 302 redirect to the original URL."""
    create_resp = await client.post(
        "/api/shorten",
        json={"url": "https://www.google.com/"},
    )
    assert create_resp.status_code == 201
    short_code = create_resp.json()["short_code"]

    redirect_resp = await client.get(f"/{short_code}", follow_redirects=False)
    assert redirect_resp.status_code == 302
    assert redirect_resp.headers["location"] == "https://www.google.com/"


@pytest.mark.asyncio
async def test_redirect_not_found(client):
    """An unknown short code returns 404."""
    resp = await client.get("/xxxxxx", follow_redirects=False)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/stats/{short_code}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_success(client):
    """Statistics endpoint returns correct data after creation."""
    create_resp = await client.post(
        "/api/shorten",
        json={"url": "https://openai.com/"},
    )
    short_code = create_resp.json()["short_code"]

    stats_resp = await client.get(f"/api/stats/{short_code}")
    assert stats_resp.status_code == 200
    data = stats_resp.json()
    assert data["short_code"] == short_code
    assert data["original_url"] == "https://openai.com/"
    assert data["visit_count"] == 0
    assert data["last_visited_at"] is None


@pytest.mark.asyncio
async def test_stats_visit_count_increments(client):
    """Visiting a short URL triggers background visit-stat updates."""
    from unittest.mock import AsyncMock, patch

    create_resp = await client.post(
        "/api/shorten",
        json={"url": "https://python.org/"},
    )
    short_code = create_resp.json()["short_code"]

    # Patch update_visit_stats so it doesn't use a separate DB session
    # (which wouldn't share the test in-memory DB).
    with patch("app.routers.redirect.update_visit_stats", new_callable=AsyncMock) as mock_update:
        await client.get(f"/{short_code}", follow_redirects=False)
        await client.get(f"/{short_code}", follow_redirects=False)

    # Background task should have been scheduled twice.
    assert mock_update.call_count == 2
    mock_update.assert_called_with(short_code)


@pytest.mark.asyncio
async def test_update_visit_stats_increments_db(db_session):
    """update_visit_stats correctly increments visit_count in the DB."""
    from datetime import datetime, timedelta, timezone
    from unittest.mock import patch

    from app.models import URL
    from app.services import update_visit_stats

    now = datetime.now(timezone.utc)
    record = URL(
        short_code="VSTST1",
        original_url="https://visit-test.example.com/",
        created_at=now,
        expires_at=now + timedelta(days=30),
        visit_count=0,
        last_visited_at=None,
    )
    db_session.add(record)
    await db_session.flush()

    # Patch AsyncSessionLocal to return the test session so update_visit_stats
    # writes to the same in-memory DB used by the test.
    from unittest.mock import MagicMock
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _mock_session():
        yield db_session

    with patch("app.database.AsyncSessionLocal", return_value=_mock_session()):
        await update_visit_stats("VSTST1")

    await db_session.refresh(record)
    assert record.visit_count == 1
    assert record.last_visited_at is not None


@pytest.mark.asyncio
async def test_stats_not_found(client):
    """Statistics for an unknown short code returns 404."""
    resp = await client.get("/api/stats/xxxxxx")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Expiry check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_url_not_found(client):
    """A short URL with expire_days=0 is treated as expired."""
    # expire_days=0 means the URL expires immediately (past expiry).
    create_resp = await client.post(
        "/api/shorten",
        json={"url": "https://example.org/", "expire_days": 0},
    )
    assert create_resp.status_code == 201
    short_code = create_resp.json()["short_code"]

    # The URL should already be expired (expires_at == created_at).
    redirect_resp = await client.get(f"/{short_code}", follow_redirects=False)
    assert redirect_resp.status_code == 404

    stats_resp = await client.get(f"/api/stats/{short_code}")
    assert stats_resp.status_code == 404


# ---------------------------------------------------------------------------
# Homepage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_homepage_returns_html(client):
    """GET / returns an HTML page."""
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# Short code collision protection (Issue #8)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collision_retry_succeeds(client, monkeypatch):
    """Short code generation retries on collision and eventually succeeds."""
    from unittest.mock import patch

    call_count = 0
    original_codes = ["AAAAA1", "AAAAA1", "AAAAA1", "BBBBBB"]  # first 3 collide

    def _mock_generate() -> str:
        nonlocal call_count
        code = original_codes[min(call_count, len(original_codes) - 1)]
        call_count += 1
        return code

    # Create a URL that occupies code "AAAAA1" in the DB first.
    with patch("app.services._generate_short_code", side_effect=lambda: "AAAAA1"):
        resp1 = await client.post(
            "/api/shorten",
            json={"url": "https://first.example.com/"},
        )
    assert resp1.status_code == 201
    assert resp1.json()["short_code"] == "AAAAA1"

    # Now try to create another URL; the mock makes it collide 3 times before
    # producing a unique code "BBBBBB".
    with patch("app.services._generate_short_code", side_effect=_mock_generate):
        resp2 = await client.post(
            "/api/shorten",
            json={"url": "https://second.example.com/"},
        )
    assert resp2.status_code == 201
    assert resp2.json()["short_code"] == "BBBBBB"
    assert call_count >= 4  # at least 3 collisions + 1 success


@pytest.mark.asyncio
async def test_collision_exhausted_returns_500(client):
    """Exceeding SHORT_CODE_MAX_RETRIES returns 500 with a meaningful error."""
    from unittest.mock import patch

    from app import config as cfg_module

    # Override max retries to 2 so the test runs fast.
    original_retries = cfg_module.settings.short_code_max_retries
    cfg_module.settings.short_code_max_retries = 2

    try:
        # Pre-occupy the only code the mock will ever generate.
        with patch("app.services._generate_short_code", return_value="ZZZZZZ"):
            resp1 = await client.post(
                "/api/shorten",
                json={"url": "https://occupied.example.com/"},
            )
        assert resp1.status_code == 201

        # Now every attempt collides → should exhaust retries → 500.
        with patch("app.services._generate_short_code", return_value="ZZZZZZ"):
            resp2 = await client.post(
                "/api/shorten",
                json={"url": "https://another.example.com/"},
            )
        assert resp2.status_code == 500
        body = resp2.json()
        # The error response should carry a meaningful message.
        assert "detail" in body or "message" in body or "error" in body
    finally:
        cfg_module.settings.short_code_max_retries = original_retries

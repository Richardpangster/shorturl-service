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
    """Visiting a short URL increments the visit counter."""
    create_resp = await client.post(
        "/api/shorten",
        json={"url": "https://python.org/"},
    )
    short_code = create_resp.json()["short_code"]

    # Visit twice.
    await client.get(f"/{short_code}", follow_redirects=False)
    await client.get(f"/{short_code}", follow_redirects=False)

    stats_resp = await client.get(f"/api/stats/{short_code}")
    assert stats_resp.status_code == 200
    assert stats_resp.json()["visit_count"] == 2


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

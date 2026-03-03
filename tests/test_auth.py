"""Unit tests for authentication: login endpoint, JWT, and password hashing."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth import create_access_token, decode_access_token, hash_password, verify_password
from app.database import Base, get_db
from app.main import app
from app.models import User

# ---------------------------------------------------------------------------
# In-memory test database
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    """Override database dependency for tests."""
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
async def setup_db():
    """Create tables before each test and drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client():
    """Provide an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Password hashing tests
# ---------------------------------------------------------------------------


def test_hash_password_produces_different_hashes():
    """Same password should produce different bcrypt hashes due to random salt."""
    h1 = hash_password("secret")
    h2 = hash_password("secret")
    assert h1 != h2


def test_verify_password_correct():
    """Correct password must verify as True."""
    h = hash_password("mypassword")
    assert verify_password("mypassword", h) is True


def test_verify_password_wrong():
    """Wrong password must verify as False."""
    h = hash_password("mypassword")
    assert verify_password("wrongpassword", h) is False


# ---------------------------------------------------------------------------
# JWT tests
# ---------------------------------------------------------------------------


def test_create_and_decode_access_token():
    """Token created for a username must decode to that username."""
    token = create_access_token("alice")
    payload = decode_access_token(token)
    assert payload["sub"] == "alice"


def test_decode_expired_token_raises():
    """An already-expired token (expires_in=0) must raise HTTP 401."""
    import time
    from fastapi import HTTPException

    token = create_access_token("alice", expires_in=-1)
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token)
    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Register + Login endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_new_user(client):
    """Registering a new user should return 201 with the username."""
    resp = await client.post("/api/auth/register", json={"username": "bob", "password": "secure123"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "bob"


@pytest.mark.asyncio
async def test_register_duplicate_username(client):
    """Registering the same username twice should return 409."""
    payload = {"username": "alice", "password": "pass1234"}
    await client.post("/api/auth/register", json=payload)
    resp = await client.post("/api/auth/register", json=payload)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client):
    """Valid credentials should return a JWT token with expires_in=86400."""
    await client.post("/api/auth/register", json={"username": "carol", "password": "hunter2"})
    resp = await client.post("/api/auth/login", json={"username": "carol", "password": "hunter2"})
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert data["expires_in"] == 86400


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    """Wrong password must return 401."""
    await client.post("/api/auth/register", json={"username": "dave", "password": "correct"})
    resp = await client.post("/api/auth/login", json={"username": "dave", "password": "wrong"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client):
    """Login for unknown user must return 401."""
    resp = await client.post("/api/auth/login", json={"username": "ghost", "password": "pass"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_token_is_valid_jwt(client):
    """Token returned from login should be a decodable JWT with correct subject."""
    await client.post("/api/auth/register", json={"username": "eve", "password": "password1"})
    resp = await client.post("/api/auth/login", json={"username": "eve", "password": "password1"})
    token = resp.json()["token"]
    payload = decode_access_token(token)
    assert payload["sub"] == "eve"


@pytest.mark.asyncio
async def test_inactive_user_cannot_login(client):
    """An inactive user should receive 403 when trying to log in."""
    # Register user then deactivate directly via DB
    await client.post("/api/auth/register", json={"username": "frank", "password": "pass1234"})

    async with TestSessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.username == "frank"))
        user = result.scalar_one()
        user.is_active = False
        await session.commit()

    resp = await client.post("/api/auth/login", json={"username": "frank", "password": "pass1234"})
    assert resp.status_code == 403

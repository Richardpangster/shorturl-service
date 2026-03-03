"""Pytest configuration and shared fixtures for ShortURL Service tests."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app

# Use an in-memory SQLite database for tests.
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_database():
    """Create tables before each test and drop them after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def db_session():
    """Provide a test database session."""
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture()
async def client():
    """Provide an HTTPX async test client wired to the test DB."""

    async def override_get_db():
        async with TestSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    # Patch update_visit_stats in the redirect router module so that
    # background visit stat updates go to the in-memory test database.
    import app.routers.redirect as redirect_module
    import app.services as svc_module

    original_update = redirect_module.update_visit_stats

    async def patched_update_visit_stats(short_code: str, session_factory=None) -> None:
        await svc_module.update_visit_stats(short_code, session_factory=TestSessionLocal)

    redirect_module.update_visit_stats = patched_update_visit_stats

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    redirect_module.update_visit_stats = original_update
    app.dependency_overrides.clear()

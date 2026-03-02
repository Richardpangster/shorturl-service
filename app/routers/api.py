"""API router: POST /api/shorten and GET /api/stats/{short_code}."""

from datetime import timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.services import create_short_url, get_url_stats

router = APIRouter(prefix="/api", tags=["api"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ShortenRequest(BaseModel):
    """Request body for POST /api/shorten."""

    url: HttpUrl
    expire_days: Optional[int] = None


class ShortenResponse(BaseModel):
    """Response body for POST /api/shorten."""

    short_code: str
    short_url: str
    original_url: str
    expires_at: str


class StatsResponse(BaseModel):
    """Response body for GET /api/stats/{short_code}."""

    short_code: str
    original_url: str
    created_at: str
    expires_at: str
    visit_count: int
    last_visited_at: Optional[str]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/shorten",
    response_model=ShortenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a short URL",
)
async def shorten_url(
    body: ShortenRequest,
    db: AsyncSession = Depends(get_db),
) -> ShortenResponse:
    """Create a new short URL mapping.

    - **url**: The original long URL to shorten.
    - **expire_days**: Optional expiry in days (default 30).
    """
    url_record = await create_short_url(
        db=db,
        original_url=str(body.url),
        expire_days=body.expire_days,
    )
    short_url = f"{settings.base_url}/{url_record.short_code}"
    expires_at_aware = url_record.expires_at.replace(tzinfo=timezone.utc)
    return ShortenResponse(
        short_code=url_record.short_code,
        short_url=short_url,
        original_url=url_record.original_url,
        expires_at=expires_at_aware.isoformat(),
    )


@router.get(
    "/stats/{short_code}",
    response_model=StatsResponse,
    summary="Get short URL statistics",
)
async def url_stats(
    short_code: str,
    db: AsyncSession = Depends(get_db),
) -> StatsResponse:
    """Return visit statistics for a short URL.

    Returns 404 if the short code does not exist or has expired.
    """
    url_record = await get_url_stats(db=db, short_code=short_code)
    if url_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Short code '{short_code}' not found or has expired.",
        )

    created_at_aware = url_record.created_at.replace(tzinfo=timezone.utc)
    expires_at_aware = url_record.expires_at.replace(tzinfo=timezone.utc)
    last_visited: Optional[str] = None
    if url_record.last_visited_at is not None:
        last_visited = url_record.last_visited_at.replace(tzinfo=timezone.utc).isoformat()

    return StatsResponse(
        short_code=url_record.short_code,
        original_url=url_record.original_url,
        created_at=created_at_aware.isoformat(),
        expires_at=expires_at_aware.isoformat(),
        visit_count=url_record.visit_count,
        last_visited_at=last_visited,
    )

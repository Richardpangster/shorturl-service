"""Redirect router: GET /{short_code} → 302 to original URL."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import resolve_short_code

router = APIRouter(tags=["redirect"])


@router.get(
    "/{short_code}",
    summary="Redirect to original URL",
    response_class=RedirectResponse,
    status_code=status.HTTP_302_FOUND,
)
async def redirect_to_url(
    short_code: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Resolve *short_code* and issue a 302 redirect to the original URL.

    - Updates ``visit_count`` and ``last_visited_at`` on each successful hit.
    - Returns 404 if the short code does not exist or has expired.
    """
    original_url = await resolve_short_code(db=db, short_code=short_code)
    if original_url is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Short code '{short_code}' not found or has expired.",
        )
    return RedirectResponse(url=original_url, status_code=status.HTTP_302_FOUND)

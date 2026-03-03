"""Redirect router: GET /{short_code} → 302 to original URL."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import resolve_short_code, update_visit_stats

router = APIRouter(tags=["redirect"])


@router.get(
    "/{short_code}",
    summary="Redirect to original URL",
    response_class=RedirectResponse,
    status_code=status.HTTP_302_FOUND,
)
async def redirect_to_url(
    short_code: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Resolve *short_code* and issue a 302 redirect to the original URL.

    Visit statistics (``visit_count`` and ``last_visited_at``) are updated
    asynchronously via a ``BackgroundTask`` after the 302 response is sent,
    so redirect latency is not affected by the statistics write.

    - Returns 404 if the short code does not exist or has expired.
    """
    original_url = await resolve_short_code(db=db, short_code=short_code)
    if original_url is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Short code '{short_code}' not found or has expired.",
        )

    # Schedule stats update in background — uses its own DB session.
    background_tasks.add_task(update_visit_stats, short_code)

    return RedirectResponse(url=original_url, status_code=status.HTTP_302_FOUND)

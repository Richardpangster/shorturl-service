"""Pages router: GET / → serves the frontend HTML page via Jinja2 template."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index(request: Request) -> HTMLResponse:
    """Serve the URL shortener frontend page using Jinja2 template.

    Args:
        request: The incoming FastAPI request (required by Jinja2Templates).

    Returns:
        An HTML response rendered from ``templates/index.html``.
    """
    return templates.TemplateResponse(request, "index.html")

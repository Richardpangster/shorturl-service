"""Pages router: GET / → serves the frontend HTML page."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index() -> HTMLResponse:
    """Serve the simple URL shortener frontend page."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>ShortURL Service</title>
  <link rel="stylesheet" href="/static/style.css" />
</head>
<body>
  <div class="container">
    <h1>🔗 ShortURL Service</h1>
    <form id="shorten-form">
      <input type="url" id="url-input" placeholder="Paste your long URL here…" required />
      <button type="submit">Shorten</button>
    </form>
    <div id="result" class="hidden">
      <p>Your short URL:</p>
      <a id="short-link" href="#" target="_blank"></a>
    </div>
    <div id="error" class="hidden error"></div>
  </div>
  <script>
    document.getElementById('shorten-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const url = document.getElementById('url-input').value;
      const resultEl = document.getElementById('result');
      const errorEl = document.getElementById('error');
      const linkEl = document.getElementById('short-link');
      resultEl.classList.add('hidden');
      errorEl.classList.add('hidden');
      try {
        const res = await fetch('/api/shorten', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url }),
        });
        if (!res.ok) {
          const data = await res.json();
          errorEl.textContent = data.detail || 'An error occurred.';
          errorEl.classList.remove('hidden');
          return;
        }
        const data = await res.json();
        linkEl.href = data.short_url;
        linkEl.textContent = data.short_url;
        resultEl.classList.remove('hidden');
      } catch (err) {
        errorEl.textContent = 'Network error.';
        errorEl.classList.remove('hidden');
      }
    });
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)

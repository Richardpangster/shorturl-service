# 🔗 ShortURL Service

A lightweight, production-ready URL shortening service built with **FastAPI**, **SQLite**, and **Redis**.

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python)](https://python.org)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis)](https://redis.io)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)](https://docs.docker.com/compose/)

---

## ✨ Features

- **Create short links** with configurable expiry (7 / 30 / 90 days)
- **QR Code** generation for every short link
- **Visit statistics** — track access count and last-visited time
- **Redis caching** for near-zero-latency redirects
- **Startup cleanup** — expired records are pruned automatically on boot
- **Responsive UI** — works great on mobile and desktop
- **Docker-ready** — one command to run everything

---

## 🚀 Quick Start (Docker)

```bash
# 1. Clone the repository
git clone https://github.com/Richardpangster/shorturl-service.git
cd shorturl-service

# 2. Start all services
docker-compose up -d

# 3. Open in browser
open http://localhost:8000
```

> The first build downloads dependencies and may take ~60 seconds.  
> Subsequent starts are instant.

### Stop & clean up

```bash
docker-compose down          # stop containers, keep data
docker-compose down -v       # stop containers and delete volume
```

---

## 🛠 Local Development

### Prerequisites

- Python 3.11+
- Redis (optional — the app starts without it and falls back gracefully)

### Setup

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# (Optional) copy and edit environment variables
cp .env.example .env

# Run the dev server
uvicorn app.main:app --reload
```

Open <http://localhost:8000> in your browser.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./shorturl.db` | Async SQLAlchemy DB URL |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `BASE_URL` | `http://localhost:8000` | Public base URL used in short links |
| `DEFAULT_EXPIRE_DAYS` | `30` | Default link expiry in days |
| `SHORT_CODE_LENGTH` | `6` | Length of generated short codes |

### Run Tests

```bash
pytest -v
```

---

## 📡 API Reference

### POST `/api/shorten` — Create a short URL

**Request body**

```json
{
  "url": "https://example.com/very/long/path?with=query",
  "expire_days": 30
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `url` | string (URL) | ✅ | The original long URL |
| `expire_days` | integer | ❌ | Days until expiry (default: 30) |

**Response `201 Created`**

```json
{
  "short_code": "aB3xY9",
  "short_url": "http://localhost:8000/aB3xY9",
  "original_url": "https://example.com/very/long/path?with=query",
  "expires_at": "2025-04-01T12:00:00+00:00"
}
```

---

### GET `/{short_code}` — Redirect to original URL

Redirects with **302 Found** to the original URL.  
Returns **404** if the code doesn't exist or has expired.

---

### GET `/api/stats/{short_code}` — Get visit statistics

**Response `200 OK`**

```json
{
  "short_code": "aB3xY9",
  "original_url": "https://example.com/very/long/path?with=query",
  "created_at": "2025-03-01T12:00:00+00:00",
  "expires_at": "2025-04-01T12:00:00+00:00",
  "visit_count": 42,
  "last_visited_at": "2025-03-15T08:30:00+00:00"
}
```

Returns **404** if the short code doesn't exist or has expired.

---

## 🐳 Docker Details

### Architecture

```
┌─────────────────────────────────────────────┐
│                docker-compose               │
│                                             │
│  ┌──────────────────┐  ┌─────────────────┐  │
│  │  web (FastAPI)   │  │  redis:7-alpine │  │
│  │  port 8000       │──│  port 6379      │  │
│  │  SQLite → /data  │  │  (cache only)   │  │
│  └──────────────────┘  └─────────────────┘  │
│              │                               │
│  volume: shorturl_data (SQLite DB)           │
└─────────────────────────────────────────────┘
```

### Image size

The multi-stage `Dockerfile` keeps the runtime image small:
- **Builder stage**: compiles Python wheels
- **Runtime stage**: `python:3.11-slim` + app code only (~150 MB)

### Custom base URL

When deploying behind a reverse proxy, set `BASE_URL`:

```bash
BASE_URL=https://short.example.com docker-compose up -d
```

Or add it to a `.env` file:

```dotenv
BASE_URL=https://short.example.com
```

---

## 🗂 Project Structure

```
shorturl-service/
├── app/
│   ├── main.py          # FastAPI app, lifespan, startup cleanup
│   ├── config.py        # Pydantic settings
│   ├── database.py      # Async SQLAlchemy engine & session
│   ├── models.py        # URL ORM model
│   ├── services.py      # Business logic (create, resolve, stats, cleanup)
│   ├── cache.py         # Redis helpers
│   └── routers/
│       ├── api.py       # POST /api/shorten, GET /api/stats/{code}
│       ├── pages.py     # GET / (Jinja2 frontend)
│       └── redirect.py  # GET /{short_code}
├── templates/
│   └── index.html       # Frontend (HTML/CSS/JS + QRCode.js)
├── static/
│   └── style.css        # Responsive stylesheet
├── tests/
│   ├── conftest.py
│   └── test_api.py
├── Dockerfile           # Multi-stage build
├── docker-compose.yml   # FastAPI + Redis services
├── .dockerignore
├── requirements.txt
└── README.md
```

---

## 🔧 Maintenance

### Manual cleanup of expired links

Expired URLs are automatically cleaned up when the service starts. To trigger cleanup manually:

```bash
# Inside the running container
docker-compose exec web python -c "
import asyncio
from app.database import AsyncSessionLocal
from app.services import cleanup_expired_urls

async def main():
    async with AsyncSessionLocal() as db:
        n = await cleanup_expired_urls(db)
        await db.commit()
        print(f'Deleted {n} expired record(s)')

asyncio.run(main())
"
```

---

## 📝 License

[MIT](LICENSE)

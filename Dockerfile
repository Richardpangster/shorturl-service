# ─── Build stage ──────────────────────────────────────────────────────────────
# Compile dependencies in a separate layer so the final image stays slim.
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools needed for some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first (better layer caching)
COPY requirements.txt .

# Install into a local directory so we can copy it cleanly
RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt


# ─── Runtime stage ────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Non-root user for security
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --no-create-home appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY --chown=appuser:appgroup app/       ./app/
COPY --chown=appuser:appgroup templates/ ./templates/
COPY --chown=appuser:appgroup static/    ./static/

# Ensure data directory for SQLite is writable
RUN mkdir -p /data && chown appuser:appgroup /data

USER appuser

# Environment defaults (can be overridden via docker-compose or -e flags)
ENV DATABASE_URL="sqlite+aiosqlite:////data/shorturl.db" \
    REDIS_URL="redis://redis:6379/0" \
    BASE_URL="http://localhost:8000" \
    DEFAULT_EXPIRE_DAYS=30 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/').read()" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

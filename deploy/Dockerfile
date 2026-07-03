# FDE AI Platform — Production Dockerfile
# Multi-stage build: python runtime + gunicorn

FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir gunicorn uvicorn[standard] fastapi && \
    pip install --no-cache-dir -e ".[dev,data]"

# ── Runtime stage ────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Install runtime deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY agents/ ./agents/
COPY shared/ ./shared/
COPY tests/ ./tests/
COPY pyproject.toml .

# Create non-root user
RUN useradd --create-home --shell /bin/bash fde && \
    chown -R fde:fde /app
USER fde

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Start with gunicorn + uvicorn workers
CMD ["gunicorn", "agents.router_agent.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "4", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--max-requests", "10000", \
     "--max-requests-jitter", "1000", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info"]
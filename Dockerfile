# =============================================================================
# Multi-stage Dockerfile for Ticketing System
# Optimized for development (hot-reload) and production (multi-worker)
# =============================================================================

FROM python:3.13-slim AS base

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv (pinned version for reproducibility)
# Version: 0.4.18 (update cautiously, test thoroughly)
COPY --from=ghcr.io/astral-sh/uv:0.4.18 /uv /uvx /bin/

WORKDIR /app

# Copy dependency manifests (leverage Docker cache)
COPY pyproject.toml ./
COPY .python-version* ./

# =============================================================================
# Development Stage (with hot-reload support)
# =============================================================================

FROM base AS development

# Install build tools for dev dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Install all dependencies (including dev/test)
RUN uv sync --all-extras --dev

# Copy application code (will be overridden by volume mount in docker-compose)
COPY . .

EXPOSE 8000

# Development server with hot-reload
CMD ["uv", "run", "granian", "src.main:app", \
     "--interface", "asgi", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--reload"]

# =============================================================================
# Production Stage (optimized, multi-worker, non-root)
# =============================================================================

FROM base AS production

# Install only production dependencies
RUN uv sync --no-dev

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production server with configurable workers
# Override with: docker run -e WORKERS=8 ...
ENV WORKERS=4
CMD ["sh", "-c", "uv run granian src.main:app --interface asgi --host 0.0.0.0 --port 8000 --workers ${WORKERS}"]

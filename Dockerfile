# =============================================================================
# Multi-stage Dockerfile for Ticketing System
# Supports: API servers (Granian) and Kafka consumers
# Optimized for development (hot-reload) and production (multi-worker)
# =============================================================================

FROM ghcr.io/astral-sh/uv:0.5.15 AS uv

FROM python:3.13-slim AS base

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Copy uv binary
COPY --from=uv /uv /uvx /bin/

WORKDIR /app

# Copy dependency manifests (leverage Docker cache)
COPY pyproject.toml ./
COPY uv.lock* ./
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
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install all dependencies (including dev/test)
RUN uv sync --all-groups

# Copy application code (will be overridden by volume mount in docker-compose)
COPY . .

EXPOSE 8000

# Development server with hot-reload (only watch src directory to avoid log file triggers)
CMD ["uv", "run", "granian", "src.main:app", \
     "--interface", "asgi", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--reload", \
     "--reload-paths", "src"]

# =============================================================================
# Production Stage (optimized, multi-worker, non-root)
# =============================================================================

FROM base AS production

# Install only production dependencies (no dev tools!)
RUN uv sync --no-dev && rm -rf ~/.cache/uv

# Copy application code (required for all services)
COPY src/ ./src/

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Common environment for all production services
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV UV_PROJECT_ENVIRONMENT=/app/.venv

EXPOSE 8000

# Service type: api (default) or consumer
ARG SERVICE_TYPE=api
ENV SERVICE_TYPE=${SERVICE_TYPE}

# Health check - conditional based on service type
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD if [ "$SERVICE_TYPE" = "consumer" ]; then \
            pgrep -f "python.*consumer.py" > /dev/null || exit 1; \
        else \
            curl -f http://localhost:8000/health || exit 1; \
        fi

# Production server with configurable workers (API) or consumer script
ENV WORKERS=4
ENV CONSUMER_SCRIPT=""

CMD if [ "$SERVICE_TYPE" = "consumer" ] && [ -n "$CONSUMER_SCRIPT" ]; then \
        /app/.venv/bin/python "$CONSUMER_SCRIPT"; \
    else \
        sh -c "uv run granian src.main:app --interface asgi --host 0.0.0.0 --port 8000 --workers ${WORKERS}"; \
    fi

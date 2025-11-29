# =============================================================================
# Multi-stage Dockerfile for Ticketing System (Optimized Build Speed)
# =============================================================================

FROM ghcr.io/astral-sh/uv:0.5.15 AS uv

FROM python:3.13-slim AS base

# Install runtime dependencies (PostgreSQL, Redis, Curl, etc.)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libpq-dev postgresql-client redis-tools curl procps make && \
    rm -rf /var/lib/apt/lists/*

# Copy uv binary from uv image
COPY --from=uv /uv /uvx /bin/
WORKDIR /app

# ---- Dependency layer (cacheable) ----
# Only copy dependency manifests to avoid reinstalling deps when code changes
COPY pyproject.toml ./
COPY uv.lock* ./
COPY .python-version* ./

# =============================================================================
# Development Stage (supports hot reload)
# =============================================================================
FROM base AS development

# Install development tools (compilers, Node.js, etc.)
RUN apt-get update && apt-get install -y \
    gcc g++ make nodejs npm && \
    rm -rf /var/lib/apt/lists/*

# Install all dependencies (including dev/test dependencies)
# --frozen: Lock versions, don't update lock file (speeds up builds)
ENV UV_HTTP_TIMEOUT=120
RUN uv sync --all-groups --frozen && \
    pip install py-spy

# Only copy necessary directories to preserve Docker cache
# Note: docker-compose.yml will volume mount and override these files
COPY src/ ./src/
COPY script/ ./script/
COPY deployment/ ./deployment/
COPY alembic.ini ./
COPY Makefile ./

EXPOSE 8000

# Development server (hot reload mode, only watch src/ to avoid log-triggered restarts)
CMD ["uv", "run", "granian", "src.main:app", \
     "--interface", "asgi", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--reload", \
     "--reload-paths", "src"]

# =============================================================================
# Production Stage (optimized, multi-worker, non-root user)
# =============================================================================
FROM base AS production

# Set virtual environment path (unified management)
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

# Only install production dependencies (exclude dev/test tools, reduce image size)
# --frozen: Lock versions, speeds up builds
ENV UV_HTTP_TIMEOUT=120
RUN uv sync --no-dev --frozen && rm -rf ~/.cache/uv

# Copy application code (shared by all services)
COPY src/ ./src/
COPY script/ ./script/
COPY deployment/ ./deployment/
COPY alembic.ini ./
COPY Makefile ./

# Create non-root user (security best practice)
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app && \
    chown -R appuser:appuser /opt/venv
USER appuser

# Python runtime configuration
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8000

# Service type: api (default) or consumer
# Note: This variable will be overridden in docker-compose.yml or ECS task definition
ARG SERVICE_TYPE=api
ENV SERVICE_TYPE=${SERVICE_TYPE}

# Health check (depends on service type)
# - API: Check HTTP endpoint
# - Consumer: Check if Python process is alive
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD if [ "$SERVICE_TYPE" = "consumer" ]; then \
            pgrep -f "python.*consumer.py" > /dev/null || exit 1; \
        else \
            curl -f http://localhost:8000/health || exit 1; \
        fi

# Startup command
# - Consumer: Execute script specified by CONSUMER_SCRIPT environment variable
# - API: Start Granian ASGI server, worker count controlled by WORKERS environment variable
#
# Note: WORKERS and CONSUMER_SCRIPT have no default values here
# 👉 Best practice: Set in ECS task definition / docker-compose.yml
CMD if [ "$SERVICE_TYPE" = "consumer" ] && [ -n "$CONSUMER_SCRIPT" ]; then \
        /opt/venv/bin/python "$CONSUMER_SCRIPT"; \
    else \
        sh -c "uv run granian src.main:app --interface asgi --host 0.0.0.0 --port 8000 --workers ${WORKERS:-4}"; \
    fi

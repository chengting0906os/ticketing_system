# =============================================================================
# Dockerfile for Ticketing System (Multi-stage Build)
# =============================================================================

FROM ghcr.io/astral-sh/uv:0.9.21 AS uv

# =============================================================================
# Stage 1: Builder - compile dependencies
# =============================================================================
FROM python:3.13-slim AS builder

# Install build dependencies (only needed for compilation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /bin/
WORKDIR /app

# Install dependencies
COPY pyproject.toml uv.lock* .python-version* ./
ENV UV_HTTP_TIMEOUT=120
RUN uv sync --all-groups --frozen

# =============================================================================
# Stage 2: Runtime - minimal production image
# =============================================================================
FROM python:3.13-slim

# Install runtime dependencies only (no gcc/g++)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 postgresql-client redis-tools curl procps && \
    rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /bin/
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY pyproject.toml ./
COPY src/ ./src/
COPY alembic.ini ./

# Runtime config (ports, command, env) is specified in docker-compose.yml

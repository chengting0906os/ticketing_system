# =============================================================================
# Dockerfile for Ticketing System (Development)
# =============================================================================

FROM ghcr.io/astral-sh/uv:0.5.15 AS uv

FROM python:3.13-slim

# Install runtime + development dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev postgresql-client redis-tools curl procps make \
    gcc g++ nodejs npm && \
    rm -rf /var/lib/apt/lists/*

# Copy uv binary from uv image
COPY --from=uv /uv /uvx /bin/
WORKDIR /app

# ---- Dependency layer (cacheable) ----
COPY pyproject.toml uv.lock* .python-version* ./

# Install all dependencies (including dev/test)
ENV UV_HTTP_TIMEOUT=120
RUN uv sync --all-groups --frozen && pip install py-spy

# Copy application code (docker-compose.yml will volume mount and override)
COPY src/ ./src/
COPY script/ ./script/
COPY deployment/ ./deployment/
COPY alembic.ini Makefile ./

# Runtime config (ports, command, env) is specified in docker-compose.yml

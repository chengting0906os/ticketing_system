# ============= Build Stage =============
# Build context: project root (ticketing_system/)
FROM golang:1.23-alpine AS builder

WORKDIR /build

# Copy Go module files
COPY script/go_client/go.mod script/go_client/go.sum* ./

# Download dependencies (cached if go.mod/go.sum unchanged)
RUN go mod download || true

# Copy all Go source files
COPY script/go_client/*.go ./

# Build all load test binaries (explicitly for linux/amd64)
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
    -ldflags="-w -s" \
    -o reserved_loadtest \
    reserved_loadtest.go types.go

RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
    -ldflags="-w -s" \
    -o concurrent_loadtest \
    concurrent_loadtest.go types.go

RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
    -ldflags="-w -s" \
    -tags full_reserved \
    -o full_reserved_loadtest \
    full_reserved_loadtest.go types.go

# ============= Runtime Stage =============
FROM python:3.11-slim-bookworm

# Install ca-certificates, make, bash, and build tools for confluent-kafka
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    make \
    bash \
    curl \
    wget \
    gcc \
    g++ \
    librdkafka-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv (Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Install k6
RUN wget -q https://github.com/grafana/k6/releases/download/v0.54.0/k6-v0.54.0-linux-amd64.tar.gz \
    && tar -xzf k6-v0.54.0-linux-amd64.tar.gz \
    && mv k6-v0.54.0-linux-amd64/k6 /usr/local/bin/ \
    && rm -rf k6-v0.54.0-linux-amd64*

WORKDIR /app

# Copy Python project files (build context: project root)
COPY pyproject.toml uv.lock ./

# Install Python dependencies
RUN uv sync --frozen --no-dev

# Copy Python source code
COPY src/ /app/src/
COPY script/*.py /app/script/

# Copy Go binaries from builder
COPY --from=builder /build/reserved_loadtest /app/script/go_client/reserved_loadtest
COPY --from=builder /build/concurrent_loadtest /app/script/go_client/concurrent_loadtest
COPY --from=builder /build/full_reserved_loadtest /app/script/go_client/full_reserved_loadtest

# Copy Makefiles for easy command execution
COPY script/go_client/Makefile /app/script/go_client/Makefile
COPY Makefile /app/Makefile

# Copy Alembic config (migrations are in src/platform/alembic, already copied via COPY src/)
COPY alembic.ini /app/alembic.ini

# Copy seating config (needed by both seed script and go_client)
COPY script/seating_config.json /app/script/seating_config.json
RUN ln -s /app/script/seating_config.json /app/script/go_client/seating_config.json

# Copy k6 scripts
COPY script/k6/ /app/k6/

# Make Go binaries executable
RUN chmod +x /app/script/go_client/reserved_loadtest \
    /app/script/go_client/concurrent_loadtest \
    /app/script/go_client/full_reserved_loadtest

# Create report directory
RUN mkdir -p /app/report

# Set working directory to go_client for convenience
WORKDIR /app/script/go_client

# Default: sleep infinity (for ECS Exec interactive usage)
CMD ["sleep", "infinity"]

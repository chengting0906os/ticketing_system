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

# Build all load test binaries for ARM64 (Graviton/t4g)
RUN CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build \
    -ldflags="-w -s" \
    -o reserved_loadtest \
    reserved_loadtest.go types.go

RUN CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build \
    -ldflags="-w -s" \
    -o concurrent_loadtest \
    concurrent_loadtest.go types.go

RUN CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build \
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
    git \
    librdkafka-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv (Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# ============= Install Go Runtime (ARM64) =============
ENV GO_VERSION=1.23.4
RUN wget -q https://go.dev/dl/go${GO_VERSION}.linux-arm64.tar.gz \
    && tar -C /usr/local -xzf go${GO_VERSION}.linux-arm64.tar.gz \
    && rm go${GO_VERSION}.linux-arm64.tar.gz
ENV PATH="/usr/local/go/bin:$PATH"
ENV GOPATH="/root/go"
ENV PATH="${GOPATH}/bin:$PATH"

# ============= Install k6 (ARM64) =============
ENV K6_VERSION=v0.54.0
RUN wget -q https://github.com/grafana/k6/releases/download/${K6_VERSION}/k6-${K6_VERSION}-linux-arm64.tar.gz \
    && tar -xzf k6-${K6_VERSION}-linux-arm64.tar.gz \
    && mv k6-${K6_VERSION}-linux-arm64/k6 /usr/local/bin/ \
    && rm -rf k6-${K6_VERSION}-linux-arm64*

# ============= Install AWS CLI (ARM64) =============
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o "awscliv2.zip" \
    && apt-get update && apt-get install -y unzip \
    && unzip awscliv2.zip \
    && ./aws/install \
    && rm -rf awscliv2.zip aws \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python project files (build context: project root)
COPY pyproject.toml uv.lock ./

# Install Python dependencies
RUN uv sync --frozen --no-dev

# Copy Python source code
COPY src/ /app/src/
COPY script/*.py /app/script/

# Copy Go source files (for on-the-fly compilation)
COPY script/go_client/*.go /app/script/go_client/
COPY script/go_client/go.mod script/go_client/go.sum* /app/script/go_client/

# Copy Go binaries from builder (pre-built for convenience)
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

# Default: sleep infinity (for interactive usage)
CMD ["sleep", "infinity"]

# ============= Build Stage =============
FROM golang:1.23-alpine AS builder

WORKDIR /build

# Copy Go module files
COPY go_client/go.mod go_client/go.sum* ./

# Download dependencies (cached if go.mod/go.sum unchanged)
RUN go mod download || true

# Copy all Go source files
COPY go_client/*.go ./

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
FROM alpine:3.19

# Install ca-certificates for HTTPS and make
RUN apk add --no-cache \
    ca-certificates \
    make \
    && rm -rf /var/cache/apk/*

WORKDIR /app

# Copy binaries from builder
COPY --from=builder /build/reserved_loadtest /app/reserved_loadtest
COPY --from=builder /build/concurrent_loadtest /app/concurrent_loadtest
COPY --from=builder /build/full_reserved_loadtest /app/full_reserved_loadtest

# Copy seating config
COPY seating_config.json /app/seating_config.json

# Make executable
RUN chmod +x /app/reserved_loadtest /app/concurrent_loadtest /app/full_reserved_loadtest

# Create report directory
RUN mkdir -p /app/report

# Default: run reserved_loadtest (can be overridden via ECS command)
CMD ["./reserved_loadtest", "-env", "local_dev", "-event", "1", "-workers", "20"]

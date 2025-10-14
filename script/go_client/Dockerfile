# ============= Build Stage =============
FROM golang:1.23-alpine AS builder

WORKDIR /build

# Copy Go module files
COPY go.mod go.sum* ./

# Download dependencies (cached if go.mod/go.sum unchanged)
RUN go mod download || true

# Copy source code
COPY main.go ./

# Build static binary (no CGO for smaller image)
RUN CGO_ENABLED=0 GOOS=linux go build \
    -ldflags="-w -s" \
    -o loadtest \
    main.go

# ============= Runtime Stage =============
FROM alpine:3.19

# Install AWS CLI and ca-certificates
RUN apk add --no-cache \
    ca-certificates \
    aws-cli \
    && rm -rf /var/cache/apk/*

WORKDIR /app

# Copy binary from builder
COPY --from=builder /build/loadtest /app/loadtest

# Make executable
RUN chmod +x /app/loadtest

# Create report directory
RUN mkdir -p /app/report

# Default command (can be overridden via ECS task override)
CMD ["./loadtest", \
     "-host", "${ALB_HOST}", \
     "-requests", "50000", \
     "-concurrency", "500", \
     "-clients", "10", \
     "-event", "1", \
     "-mode", "best_available", \
     "-quantity", "2"]

# Upload results to S3 on completion (using entrypoint script)
COPY <<'EOF' /app/entrypoint.sh
#!/bin/sh
set -e

# Run load test
./loadtest "$@"

# Upload results to S3 if bucket configured
if [ -n "$S3_BUCKET" ]; then
    echo "📤 Uploading results to s3://${S3_BUCKET}/"
    aws s3 cp report/ "s3://${S3_BUCKET}/$(date +%Y%m%d-%H%M%S)/" --recursive
fi
EOF

RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]

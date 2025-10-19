#!/usr/bin/env bash
#
# Test ECS Container Configuration Locally
# Purpose: Validate container startup, health checks, and environment variables before deploying to AWS
#
set -euo pipefail

SERVICE_NAME="${1:-ticketing-service}"
PORT="${2:-8100}"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Testing $SERVICE_NAME Container ===${NC}"

# Validate service name
if [[ "$SERVICE_NAME" != "ticketing-service" ]] && [[ "$SERVICE_NAME" != "seat-reservation-service" ]]; then
    echo -e "${RED}❌ Invalid service name. Use: ticketing-service or seat-reservation-service${NC}"
    exit 1
fi

# Set service-specific variables
if [[ "$SERVICE_NAME" == "ticketing-service" ]]; then
    IMAGE="987879449824.dkr.ecr.us-west-2.amazonaws.com/ticketing-service:latest"
    ENTRY_POINT="src.service.ticketing.main:app"
    PORT=8100
else
    IMAGE="987879449824.dkr.ecr.us-west-2.amazonaws.com/seat-reservation-service:latest"
    ENTRY_POINT="src.service.seat_reservation.main:app"
    PORT=8200
fi

CONTAINER_NAME="test-$SERVICE_NAME"

echo -e "${YELLOW}Step 1: Pulling latest image${NC}"
docker pull "$IMAGE"

echo -e "${YELLOW}Step 2: Starting container with ECS-equivalent configuration${NC}"
docker run -d \
    --name "$CONTAINER_NAME" \
    --network ticketing_system_default \
    -p "$PORT:$PORT" \
    -e SERVICE_NAME="$SERVICE_NAME" \
    -e LOG_LEVEL="INFO" \
    -e OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317" \
    -e OTEL_EXPORTER_OTLP_PROTOCOL="grpc" \
    -e POSTGRES_SERVER="postgres" \
    -e POSTGRES_USER="postgres" \
    -e POSTGRES_PASSWORD="postgres" \
    -e POSTGRES_DB="ticketing_system" \
    -e POSTGRES_PORT="5432" \
    -e KVROCKS_HOST="kvrocks" \
    -e KVROCKS_PORT="6666" \
    -e KAFKA_BOOTSTRAP_SERVERS="kafka:29092" \
    "$IMAGE" \
    sh -c "uv run granian $ENTRY_POINT --interface asgi --host 0.0.0.0 --port $PORT --workers 4"

echo -e "${YELLOW}Step 3: Waiting 10 seconds for startup${NC}"
sleep 10

echo -e "${YELLOW}Step 4: Checking container logs${NC}"
docker logs "$CONTAINER_NAME" 2>&1 | tail -20

echo -e "${YELLOW}Step 5: Running health check (ECS-equivalent)${NC}"
if docker exec "$CONTAINER_NAME" curl -f "http://localhost:$PORT/health"; then
    echo -e "${GREEN}✅ Health check PASSED${NC}"
else
    echo -e "${RED}❌ Health check FAILED${NC}"
    echo -e "${YELLOW}Container logs:${NC}"
    docker logs "$CONTAINER_NAME"
    docker rm -f "$CONTAINER_NAME"
    exit 1
fi

echo -e "${YELLOW}Step 6: Testing API endpoints${NC}"
if curl -f "http://localhost:$PORT/health"; then
    echo -e "${GREEN}✅ External health check PASSED${NC}"
else
    echo -e "${RED}❌ External health check FAILED${NC}"
    docker rm -f "$CONTAINER_NAME"
    exit 1
fi

echo -e "${YELLOW}Step 7: Cleaning up${NC}"
docker rm -f "$CONTAINER_NAME"

echo -e "${GREEN}=== All tests PASSED for $SERVICE_NAME ===${NC}"
echo -e "${GREEN}Container configuration is valid for ECS deployment${NC}"

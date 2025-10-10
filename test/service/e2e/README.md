# E2E Tests

End-to-end tests that require a fully running system (HTTP server + MQ consumers).

## Prerequisites

Before running E2E tests, you need to start all services:

### 1. Start Infrastructure (Postgres, Kafka, Kvrocks)

```bash
docker-compose up -d
```

### 2. Start HTTP Server

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Start MQ Consumers (in separate terminals)

```bash
# Terminal 1: Seat Reservation Consumer
EVENT_ID=1 PYTHONPATH=. uv run python -m src.service.seat_reservation.driving_adapter.mq_consumer.seat_reservation_mq_consumer

# Terminal 2: Ticketing Consumer
EVENT_ID=1 PYTHONPATH=. uv run python -m src.service.ticketing.driving_adapter.mq_consumer.ticketing_mq_consumer
```

## Running E2E Tests

Once all services are running:

```bash
# Run all E2E tests
uv run pytest test/e2e/ -v -m e2e

# Run specific E2E test
uv run pytest test/e2e/test_async_booking_flow.py -v
```

## What E2E Tests Cover

### `test_async_booking_flow.py`

Tests the complete async booking workflow:

1. **POST /api/booking** - Creates booking with `status='processing'`
2. **Wait 5 seconds** - MQ consumer processes seat reservation
3. **GET /api/booking/{id}** - Verifies `status='pending_payment'`

This validates:
- MQ event publishing works
- MQ consumers process events correctly
- Async state transitions complete successfully

## Troubleshooting

### Test Fails with "status='processing'"

The booking didn't transition to `pending_payment`. Check:

1. **MQ consumers are running** - Look for consumer logs
2. **Kafka is healthy** - `docker-compose ps` shows kafka running
3. **No errors in consumer logs** - Check for exceptions

### Connection Refused

The HTTP server isn't running at `http://0.0.0.0:8000`. Start it with:

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

### Database Conflicts

E2E tests use the same database as the running server. Clean up between runs:

```bash
# Reset database
make db-reset
```

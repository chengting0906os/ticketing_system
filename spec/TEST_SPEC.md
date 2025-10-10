# Testing Specification

## Test Structure

```plain
test/
├── conftest.py                    # Test fixtures and setup
├── service/
│   ├── e2e/                      # E2E tests (httpx + async)
│   ├── ticketing/integration/    # Integration tests with BDD
│   └── seat_reservation/         # Lua script integration tests
└── unit/                         # Unit tests
```

## E2E Tests

- **Framework**: httpx AsyncClient for async HTTP testing
- **Authentication**: Cookie-based auth with JWT tokens
- **Isolation**: Unique event IDs with timestamp-based generation
- **Cleanup**: Automatic seat release via cancellation after tests

## Integration Tests

- **BDD**: Gherkin syntax in `.feature` files for business scenarios
- **Database**: PostgreSQL with transaction rollback per test
- **Kvrocks**: Key prefix isolation (`KVROCKS_KEY_PREFIX=test_*`)
- **Lua Scripts**: Seat reservation atomicity testing

## Test Commands

```bash
make test          # All tests except E2E
make test-e2e      # E2E tests only
make test-bdd      # BDD integration tests
```

## Key Patterns

- **Async**: All tests use pytest-asyncio
- **Fixtures**: Shared setup in conftest.py
- **Isolation**: Unique IDs prevent parallel test conflicts
- **Real Services**: Integration tests use actual Kafka + Kvrocks

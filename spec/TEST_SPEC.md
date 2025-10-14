# Testing Specification

## Overview

This system uses a multi-layered testing strategy combining unit, integration, BDD, and E2E tests with support for parallel execution and real service dependencies.

## Test Structure

```plain
test/
├── conftest.py                    # Global fixtures and parallel test setup
├── bdd_steps_loader.py           # Consolidates all BDD step definitions
├── fixture_loader.py             # Consolidates service-specific fixtures
├── deployment/                   # CDK infrastructure tests (marked with @pytest.mark.cdk)
├── infrastructure/               # Platform tests (Kvrocks, load balancer, retry/DLQ)
├── service/
│   ├── e2e/                     # End-to-end async HTTP tests
│   ├── ticketing/
│   │   ├── fixtures.py          # Ticketing service fixtures
│   │   ├── integration/         # BDD tests with .feature files
│   │   │   ├── features/        # Gherkin scenarios
│   │   │   └── steps/           # Given/When/Then implementations
│   │   └── unit/                # Unit tests for ticketing domain
│   └── seat_reservation/
│       ├── fixtures.py          # Seat reservation fixtures
│       ├── integration/         # BDD + Lua script tests
│       └── unit/                # Unit tests for reservation logic
├── shared/                      # Reusable BDD steps (given.py, then.py, utils.py)
└── test_log/                    # Test execution logs (hourly rotation + gzip)
```

## Test Categories

### 1. Unit Tests
- **Location**: `test/service/{service}/unit/`
- **Purpose**: Test domain logic in isolation
- **Dependencies**: Mock external services
- **Speed**: Very fast (< 1s per test)
- **Example**: Ticket status transitions, price calculations

### 2. Integration Tests (BDD)
- **Location**: `test/service/{service}/integration/`
- **Framework**: pytest-bdd with Gherkin `.feature` files
- **Purpose**: Test service workflows with real dependencies
- **Dependencies**: Real PostgreSQL + Kvrocks + Kafka
- **Speed**: Medium (1-5s per scenario)
- **Example**: User registration flow, seat reservation atomicity

### 3. E2E Tests
- **Location**: `test/service/e2e/`
- **Framework**: httpx AsyncClient for async HTTP requests
- **Purpose**: Test complete user journeys across services
- **Authentication**: Cookie-based JWT tokens
- **Isolation**: Timestamp-based unique event IDs
- **Cleanup**: Automatic cancellation after test completion
- **Speed**: Slow (5-30s per test)
- **Example**: Book ticket → Reserve seat → Cancel booking

### 4. Infrastructure Tests
- **Location**: `test/infrastructure/`
- **Purpose**: Test platform components (Kvrocks pool, retry/DLQ, load balancer)
- **Dependencies**: Real Kvrocks + Kafka
- **Example**: Connection pool behavior, DLQ routing

### 5. CDK Tests
- **Location**: `test/deployment/`
- **Mark**: `@pytest.mark.cdk` (excluded by default)
- **Purpose**: Validate AWS CDK stack synthesis
- **Speed**: Very slow (1-2 min total, CPU intensive)
- **Run**: `make test-cdk` (separate from regular tests)

## Test Commands

```bash
# Run all tests except E2E and CDK
make test

# Run with output (show print statements)
make test-verbose

# Run E2E tests only
make test-e2e

# Run BDD integration tests only
make test-bdd

# Run CDK infrastructure tests (slow)
make test-cdk

# Run specific test file
make test test/service/ticketing/unit/test_event.py

# Run specific test function
make test test/service/ticketing/unit/test_event.py::test_create_event
```

## Parallel Testing

### pytest-xdist Worker Isolation
Tests run in parallel using pytest-xdist. Each worker gets isolated resources:

**Database Isolation**:
- Master worker: `ticketing_system_test_db`
- Worker N: `ticketing_system_test_db_gw{N}`
- Each database is created/reset independently

**Kvrocks Isolation**:
- Master worker: `test_*` key prefix
- Worker N: `test_gw{N}_*` key prefix
- Prevents key conflicts between parallel tests

**Configuration** (in conftest.py:32-39):
```python
worker_id = os.environ.get('PYTEST_XDIST_WORKER', 'master')
if worker_id == 'master':
    os.environ['POSTGRES_DB'] = 'ticketing_system_test_db'
    os.environ['KVROCKS_KEY_PREFIX'] = 'test_'
else:
    os.environ['POSTGRES_DB'] = f'ticketing_system_test_db_{worker_id}'
    os.environ['KVROCKS_KEY_PREFIX'] = f'test_{worker_id}_'
```

## Fixtures Architecture

### Global Fixtures (conftest.py)
**Auto-use Fixtures** (run before/after every test):
- `clean_kvrocks`: Clears Redis keys + resets async client per event loop
- `clean_database`: Truncates all tables with cached table list
- `clear_client_cookies`: Prevents auth state leakage between tests

**Session Fixtures** (created once per test session):
- `client`: FastAPI TestClient with `raise_server_exceptions=False`
- `seller_user`: Test seller account
- `buyer_user`: Test buyer account
- `another_buyer_user`: Second buyer for conflict testing

**Utility Fixtures**:
- `sample_event`: Mock event for unit tests
- `available_tickets`: Mock ticket data
- `execute_sql_statement`: Direct SQL execution helper
- `kvrocks_client_sync_for_test`: Sync Kvrocks client for async tests

### Service Fixtures
**Modular Organization**:
- `fixture_loader.py`: Imports all service fixtures
- `service/ticketing/fixtures.py`: Ticketing-specific fixtures
- `service/seat_reservation/fixtures.py`: Reservation-specific fixtures

**Benefits**:
- Service-specific fixtures stay close to their tests
- `conftest.py` remains clean by importing from loader
- Easy to add new service fixtures without modifying global config

### BDD Steps Organization
**Modular Step Definitions**:
- `bdd_steps_loader.py`: Imports all Given/When/Then steps
- Steps organized by service and domain:
  - `test/shared/`: Shared steps for common operations
  - `test/service/ticketing/integration/steps/`: Ticketing domain steps
  - `test/service/seat_reservation/integration/steps/`: Reservation domain steps

## Key Testing Patterns

### 1. Async Event Loop Management
**Problem**: Global async Kvrocks client holds reference to first event loop, causing "Event loop is closed" errors in subsequent tests.

**Solution** (conftest.py:214-250):
```python
@pytest.fixture(autouse=True, scope='function')
async def clean_kvrocks():
    # 1. Disconnect per-event-loop client
    await kvrocks_client.disconnect()

    # 2. Clean data with sync client
    keys = sync_client.keys(f'{key_prefix}*')
    if keys:
        sync_client.delete(*keys)

    yield

    # 3. Cleanup and disconnect again
    await kvrocks_client.disconnect()
```

### 2. Database Performance Optimization
**Table List Caching**: Cache table names to avoid repeated `pg_tables` queries (conftest.py:86).

**Fast Truncation**: Use `TRUNCATE` with `RESTART IDENTITY CASCADE` instead of individual `DELETE` statements (conftest.py:184).

### 3. Test Isolation Strategies
- **Unique IDs**: E2E tests use timestamp-based event IDs to prevent conflicts
- **Key Prefixes**: Kvrocks uses worker-specific prefixes (`test_gw0_*`)
- **Database Cleanup**: Truncate tables before each test, not after (fail-fast)
- **Cookie Clearing**: Auto-clear client cookies to prevent auth leakage

### 4. BDD Best Practices
- **Feature Files**: Write business scenarios in Gherkin syntax
- **Step Reusability**: Share common steps via `test/shared/`
- **Fixture Injection**: Access pytest fixtures in BDD steps
- **Async Steps**: All BDD steps support async operations

## Test Data Management

### Constants (util_constant.py)
```python
TEST_SELLER_EMAIL = "seller@example.com"
TEST_BUYER_EMAIL = "buyer@example.com"
DEFAULT_PASSWORD = "password123"
```

### Event Test Data (event_test_constants.py)
Centralized test event configurations for consistent test data.

### Shared Utilities (shared/utils.py)
Common helper functions like `create_user()` used across test suites.

## Test Logging

- **Location**: `test/test_log/`
- **Format**: `test_YYYY-MM-DD_HH.log`
- **Rotation**: Hourly with automatic gzip compression
- **Configuration**: Set via `TEST_LOG_DIR` environment variable (conftest.py:42-44)

## Running Tests

### Local Development
```bash
# Quick test run (parallel, all except E2E/CDK)
make test

# Debug mode (verbose output, sequential)
make test-verbose

# Specific test file
make test test/service/ticketing/unit/test_booking.py
```

### CI/CD
```bash
# Run all test suites in sequence
make test && make test-e2e && make test-cdk
```

## Troubleshooting

### "Event loop is closed" errors
- **Cause**: Async client not reset between tests
- **Fix**: Ensure `clean_kvrocks` fixture is auto-used (it is by default)

### Database migration failures
- **Cause**: Schema out of sync
- **Fix**: Run `make migrate-up` before testing

### Kvrocks key conflicts
- **Cause**: Keys not cleaned between tests
- **Fix**: Check `KVROCKS_KEY_PREFIX` is set correctly for your worker

### CDK tests timeout
- **Cause**: CDK synthesis is CPU-intensive
- **Fix**: Run CDK tests separately with `make test-cdk` (not in parallel)

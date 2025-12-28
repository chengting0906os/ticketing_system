# Ticketing System - Test Specification

## Overview

This document defines the test architecture, conventions, and best practices for the Ticketing System.

---

## 1. Test Strategy (Testing Pyramid)

```
        /\
       /  \        E2E Tests (10%)
      /----\       Full HTTP flow with real client
     /      \
    /--------\     Integration Tests (60%)
   /          \    BDD scenarios with DB & Kvrocks
  /------------\
 /              \  Unit Tests (30%)
/----------------\ Pure logic, mocked dependencies
```

### 1.1 Test Distribution

| Type | Ratio | Scope | Speed |
|------|-------|-------|-------|
| **Unit** | 30% | Single function/class, pure logic | Fast (ms) |
| **Integration** | 60% | BDD scenarios, DB & Kvrocks interaction | Medium (100ms~1s) |
| **E2E** | 10% | Full HTTP request/response cycle | Slow (1s+) |

### 1.2 When to Use Each Type

**Unit Tests (30%)**
- Business logic in use cases
- Data transformation functions
- Validation logic
- No database or Kvrocks dependencies
- Use mocks for external dependencies

**Integration Tests (60%)**
- BDD scenarios (Given/When/Then)
- Database operations (CRUD)
- Kvrocks state management
- API endpoint testing with TestClient
- All edge cases, validation errors

**E2E Tests (10%)**
- Critical user journeys
- Full booking flow
- Payment completion flow

### 1.3 BDD Test Scope

```
Feature: Booking Creation

Integration Test - All scenarios:
  [v] Buyer creates booking successfully (202)
  [v] Buyer creates booking with insufficient seats (400)
  [v] Buyer creates booking for sold out event (400)
  [v] Seller cannot create booking (403)
  [v] Unauthenticated user cannot create booking (401)
  ...
```

| Aspect | Unit Test | Integration Test |
|--------|-----------|------------------|
| Scope | Single component | Multiple components |
| Database | Mocked | Real (cleaned per test) |
| Kvrocks | Mocked | Real (cleaned per test) |
| Client | None | FastAPI TestClient |
| Speed | Fast | Medium |

---

## 2. Directory Structure

```
test/
├── conftest.py                    # Global fixtures (TestClient, DB cleanup)
├── loader.py                      # Imports all BDD step definitions
├── constants.py                   # Test constants (emails, passwords)
├── kvrocks_test_client.py         # Test-specific Kvrocks client
│
├── bdd_conftest/                  # Shared BDD step definitions
│   ├── __init__.py
│   ├── shared_step_utils.py       # Utility functions for steps
│   ├── given_step_conftest.py     # Common Given steps (authentication, setup)
│   ├── when_step_conftest.py      # Common When steps (HTTP actions)
│   └── then_step_conftest.py      # Common Then steps (assertions)
│
├── platform/                      # Platform-level tests
│   └── message_queue/
│       └── *_unit_test.py
│
└── service/
    ├── seat_reservation/          # Seat reservation service tests
    │   └── integration/
    │       └── *_integration_test.py
    │
    └── ticketing/                 # Ticketing service tests
        ├── booking/
        │   ├── conftest.py                        # Booking-specific steps
        │   └── *_integration_test.feature
        ├── event_ticketing/
        │   ├── conftest.py                        # Event-specific steps
        │   └── *_integration_test.feature
        ├── reservation/
        │   ├── conftest.py                        # Reservation-specific steps
        │   ├── fixtures.py                        # SSE test fixtures
        │   └── features/
        │       └── *_integration_test.feature
        └── user/
            └── *_integration_test.feature
```

---

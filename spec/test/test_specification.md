# ASDR Backend - Test Specification

## Overview

This document defines the test architecture, conventions, and best practices for ASDR Backend.

---

## 1. Test Strategy (Testing Pyramid)

```
        /\
       /  \        API Tests (10%)
      /----\       End-to-end HTTP flow validation
     /      \
    /--------\     Integration Tests (40%)
   /          \    Component interaction & BDD scenarios
  /------------\
 /              \  Unit Tests (50%)
/----------------\ Pure logic, no external dependencies
```

### 1.1 Test Distribution

| Type | Ratio | Scope | Speed |
|------|-------|-------|-------|
| **Unit** | 50% | Single function/class, pure logic | Fast (ms) |
| **Integration** | 40% | Multiple components, DB interaction | Medium (100ms~1s) |
| **API** | 10% | Full HTTP request/response cycle | Slow (1s+) |

### 1.2 When to Use Each Type

**Unit Tests (50%)**
- Business logic in services/utils
- Data transformation functions
- Validation logic
- No database or external service dependencies
- Use mocks for external dependencies

**Integration Tests (40%)**
- Detailed scenario testing for each endpoint
- All edge cases, validation errors, permission checks
- Database operations (CRUD)
- BDD scenarios (Given/When/Then)

**API Tests (10%)**
- One success + one failure per endpoint (smoke test)
- Full HTTP flow with `httpx.AsyncClient`
- CSRF token handling
- Session/cookie authentication
- Verify endpoint is accessible and basic flow works

### 1.3 API vs Integration Test Scope

```
Endpoint: POST /api/user/

API Test (10%) - Smoke test only:
  [v] Create user success (201)
  [v] Create user forbidden (403)

Integration Test (40%) - All scenarios:
  [v] Create user success (201)
  [v] Create user without permission (403)
  [v] Create user with duplicate username (400)
  [v] Create user with invalid password format (400)
  [v] Create user with missing required fields (422)
  [v] Create user with too long username (400)
  ...
```

| Aspect | API Test | Integration Test |
|--------|----------|------------------|
| Scope | 1 success + 1 failure per endpoint | All edge cases |
| Purpose | Verify HTTP flow works | Verify business logic |
| Client | `httpx.AsyncClient` | `SessionTestAsyncClient` |
| Speed | Slow | Medium |
| Coverage | Smoke test | Comprehensive |

---

## 2. Directory Structure

```
tests/
├── conftest.py                 # Global fixtures and test clients
├── glue_conftest.py            # Shared BDD step definitions
├── conftest_constants.py       # Test constants
│
├── unit/                       # Unit tests (50%)
│   └── {module}/
│       └── test_{component}.py
│
└── {module}/                   # Integration & API tests (50%)
    ├── __init__.py
    ├── conftest.py             # Module-specific fixtures
    ├── {module}_integration_test.feature   # Integration (40%)
    ├── {module}_integration_test.py
    ├── {module}_api_test.feature           # API (10%)
    └── {module}_api_test.py
```

---

## 3. Test Types & Patterns

### 3.1 Unit Tests (50%)

**File Pattern**: `tests/unit/{module}/test_{component}.py`

**Characteristics**:
- No `@pytest.mark.django_db` (or minimal DB usage)
- Heavy use of mocks
- Fast execution
- Test single responsibility

**Example**:
```python
# tests/unit/user/test_password_validator.py
import pytest
from asdr_app.services.user import validate_password

class TestPasswordValidator:
    def test_valid_password(self):
        assert validate_password("P@ssw0rd1") is True

    def test_password_too_short(self):
        assert validate_password("P@ss1") is False

    def test_password_missing_special_char(self):
        assert validate_password("Password1") is False
```

### 3.2 Integration Tests (40%)

**File Pattern**: `{module}_integration_test.feature` + `{module}_integration_test.py`

**Characteristics**:
- Uses `SessionTestAsyncClient`
- BDD style (Gherkin scenarios)
- Database interaction
- **Tests ALL scenarios**: success, failures, edge cases, validations

**Marker**: `@pytest.mark.django_db`

**Example** (comprehensive scenarios):
```gherkin
# user_integration_test.feature
Feature: User Management
  As an administrator
  I want to manage users
  So that I can control system access

  # ============ Create ============

  Scenario: Create a new user successfully
    Given I am logged in as superuser
    When I call POST "/api/user/" with
      | username   | password  |
      | testuser01 | P@ssw0rd1 |
    Then the response status code should be 201
    And the user should be created with
      | id        | username   | is_superuser |
      | {any_int} | testuser01 | false        |

  Scenario: Create user without superuser permission
    Given I am logged in as normal user
    When I call POST "/api/user/" with
      | username | password  |
      | newuser  | P@ssw0rd1 |
    Then the response status code should be 403

  Scenario: Create user with duplicate username
    Given I am logged in as superuser
    And a user exists with username "existinguser"
    When I call POST "/api/user/" with
      | username     | password  |
      | existinguser | P@ssw0rd1 |
    Then the response status code should be 400
    And the error message should contain "Account has been existed"

  Scenario: Create user with invalid password format
    Given I am logged in as superuser
    When I call POST "/api/user/" with
      | username | password |
      | newuser  | weak     |
    Then the response status code should be 400
    And the error message should contain "Password"

  # ============ Read ============

  Scenario: List all users
    Given I am logged in as superuser
    When I call GET "/api/user/"
    Then the response status code should be 200
    And the response data should be a list

  # ============ Update ============

  Scenario: Update own password
    Given I am logged in as superuser
    And a user exists with username "pwduser"
    And I am logged in as user "pwduser"
    When I call PUT "/api/user/{pwduser.id}" with
      | password     |
      | NewP@ssw0rd2 |
    Then the response status code should be 200

  Scenario: Update another user's password should fail
    Given I am logged in as superuser
    And a user exists with username "otheruser"
    And a user exists with username "attacker"
    And I am logged in as user "attacker"
    When I call PUT "/api/user/{otheruser.id}" with
      | password    |
      | Hacked@pwd1 |
    Then the response status code should be 403

  # ============ Delete ============

  Scenario: Delete a user successfully
    Given I am logged in as superuser
    And a user exists with username "usertodelete"
    When I call DELETE "/api/user/{usertodelete.id}"
    Then the response status code should be 204

  Scenario: Delete user without superuser permission
    Given I am logged in as normal user
    And a user exists with username "usertodelete2"
    When I call DELETE "/api/user/{usertodelete2.id}"
    Then the response status code should be 403
```

### 3.3 API Tests (10%)

**File Pattern**: `{module}_api_test.feature` + `{module}_api_test.py`

**Characteristics**:
- Uses `httpx.AsyncClient` with `ASGITransport`
- Full HTTP request/response cycle
- CSRF token validation
- **Smoke test only**: 1 success + 1 failure per endpoint

**Marker**: `@pytest.mark.django_db(transaction=True)`

**Example** (minimal smoke tests):
```gherkin
# user_api_test.feature
Feature: User API Endpoint
  Verify user API endpoints work correctly via full HTTP flow

  # POST /api/user/ - Create (1 success + 1 failure)
  Scenario: Create a new user successfully via API
    Given I am logged in as superuser via API
    When I create a user via API with
      | username    | password  |
      | apitestuser | P@ssw0rd1 |
    Then the response status code should be 201

  Scenario: Create user without superuser permission via API
    Given I am logged in as normal user via API
    When I create a user via API with
      | username | password  |
      | newuser  | P@ssw0rd1 |
    Then the response status code should be 403

  # GET /api/user/ - List (1 success)
  Scenario: List all users via API
    Given I am logged in as superuser via API
    When I list users via API
    Then the response status code should be 200
    And the response data should be a list

  # DELETE /api/user/{id} - Delete (1 success)
  Scenario: Delete a user successfully via API
    Given I am logged in as superuser via API
    And a user "usertodelete" exists via API
    When I delete user "usertodelete" via API
    Then the response status code should be 204
```

---

## 4. BDD Framework (pytest-bdd)

### 4.1 Tech Stack

- **pytest-bdd**: BDD test framework
- **Gherkin**: Scenario description syntax
- **pytest-asyncio**: Async test support
- **pytest-django**: Django integration

### 4.2 Feature File Structure

```gherkin
Feature: {Feature Name}
  As a {role}
  I want to {goal}
  So that {value}

  # ============ {Operation Type} ============

  Scenario: {Scenario Description}
    Given {precondition}
    When {action}
    Then {expected result}
```

### 4.3 Scenario Binding

```python
@pytest.mark.integration
@pytest.mark.django_db
@scenario('{feature_file}', '{scenario_name}')
def test_{snake_case_scenario_name}() -> None:
    pass
```

> **For detailed Step Patterns, see**: [BDD_PATTERNS.yaml](BDD_PATTERNS.yaml)

---

## 5. Test Clients

### 5.1 SessionTestAsyncClient (Integration Tests)

**Purpose**: Direct Ninja API testing without HTTP overhead

**Features**:
- Direct `request.user` assignment
- Session management support
- Provides `auser()` coroutine for `AsyncSessionAuth`

**Usage**:
```python
session_client.set_user(superuser)
response = await session_client.post('/user/', json=data)
```

### 5.2 AsyncCSRFClient (API Tests)

**Purpose**: Full HTTP flow testing

**Features**:
- Complete HTTP request/response cycle
- Automatic CSRF token handling
- Session cookie authentication

**Usage**:
```python
async with AsyncCSRFClient(transport=transport, base_url='https://testserver') as client:
    response = await client.post('/api/user/', json=data)
```

---

## 6. Step Definitions

### 6.1 Global Steps (`glue_conftest.py`)

Shared step definitions for all modules.

#### Given Steps
| Pattern | Description |
|---------|-------------|
| `a user exists with username "{username}"` | Create user via API |
| `users exist with` | Batch create users (datatable) |
| `I am logged in as "{username}" with password "{password}"` | Login as specified user |

#### When Steps
| Pattern | Description |
|---------|-------------|
| `I call POST "{endpoint}" with` | POST request |
| `I call GET "{endpoint}"` | GET request |
| `I call PUT "{endpoint}" with` | PUT request |
| `I call DELETE "{endpoint}"` | DELETE request |

#### Then Steps
| Pattern | Description |
|---------|-------------|
| `the response status code should be {status_code}` | Verify status code |
| `the error message should contain "{message}"` | Verify error message |
| `the response data "{key}" should be "{value}"` | Verify response field |
| `the response data should be a list` | Verify response is a list |

### 6.2 Module-Specific Steps

Define in `{module}_*_test.py` for module-specific logic.

> **For complete Pattern list, see**: [BDD_PATTERNS.yaml](BDD_PATTERNS.yaml)

---

## 7. Context Mechanism

### 7.1 Structure

```python
context = {
    'response': <Response>,           # HTTP response object
    'client': <TestClient>,           # Current test client
    'users': {                        # Created users
        'username': <User instance>,
    }
}
```

### 7.2 Endpoint Variable Substitution

```gherkin
Given a user exists with username "pwduser"
When I call PUT "/api/user/{pwduser.id}" with
  | password     |
  | NewP@ssw0rd2 |
```

`{pwduser.id}` resolves to `context['users']['pwduser'].pk`

---

## 8. Datatable Formats

### 8.1 Single Row (Most Common)

```gherkin
| field1 | field2 |
| value1 | value2 |
```

### 8.2 Multi-Row

```gherkin
| username | password  |
| user1    | P@ssw0rd1 |
| user2    | P@ssw0rd2 |
```

### 8.3 Special Values

| Value | Description |
|-------|-------------|
| `{any_int}` | Matches any integer |
| `true` | Boolean true or 1 |
| `false` | Boolean false or 0 |

---

## 9. Fixtures

### 9.1 Global Fixtures (`tests/conftest.py`)

| Fixture | Description |
|---------|-------------|
| `api_instance` | NinjaExtraAPI instance (session scope) |
| `session_client` | SessionTestAsyncClient instance |
| `api_superuser_client` | httpx client logged in as superuser |
| `api_normal_user_client` | httpx client logged in as normal user |
| `context` | Shared dict for BDD steps |

### 9.2 Module Fixtures

```python
# tests/{module}/conftest.py
@pytest.fixture
def superuser(db: None) -> User:
    """Create a superuser for testing."""
    ...
```

---

## 10. Markers

| Marker | Description |
|--------|-------------|
| `@pytest.mark.unit` | Unit tests |
| `@pytest.mark.integration` | Integration tests |
| `@pytest.mark.api` | API tests |
| `@pytest.mark.django_db` | Requires database access |
| `@pytest.mark.django_db(transaction=True)` | Full transaction support |

---

## 11. Naming Conventions

### 11.1 File Naming

| Type | Pattern |
|------|---------|
| Unit | `tests/unit/{module}/test_{component}.py` |
| Integration | `{module}_integration_test.feature` / `.py` |
| API | `{module}_api_test.feature` / `.py` |

### 11.2 Function Naming

```python
# Unit tests
def test_{action}_{condition}_{expected_result}():

# BDD tests
def test_{snake_case_scenario_name}():
```

---

## 12. Adding New Tests

### 12.1 Checklist

**Unit Test**:
- [ ] No database dependency (or minimal)
- [ ] Uses mocks for external services
- [ ] Tests single responsibility
- [ ] Fast execution (<100ms)

**Integration Test**:
- [ ] Feature file uses correct Gherkin syntax
- [ ] Scenario bound to test function
- [ ] Uses `@pytest.mark.integration`
- [ ] Steps defined in correct location

**API Test**:
- [ ] Only for critical user journeys
- [ ] Uses `@pytest.mark.django_db(transaction=True)`
- [ ] Tests full HTTP flow

---

## 13. Running Tests

```bash
# Run all tests
uv run pytest

# Run by type
uv run pytest tests/unit/                    # Unit tests only
uv run pytest -m integration                 # Integration tests only
uv run pytest -m api                         # API tests only

# Run specific module
uv run pytest tests/user/

# Generate report
uv run pytest --html=test_report.html

# Run lint check after tests
uv run ruff check .
```

---

## 14. Standard Test Password

All test users use: `P@ssw0rd1`

---

## 15. References

| Document | Description |
|----------|-------------|
| [BDD_PATTERNS.yaml](BDD_PATTERNS.yaml) | Step patterns, datatable formats, special values |
| [pytest-bdd docs](https://pytest-bdd.readthedocs.io/) | Official pytest-bdd documentation |
| [Django Ninja testing](https://django-ninja.rest-framework.com/guides/testing/) | Django Ninja testing guide |

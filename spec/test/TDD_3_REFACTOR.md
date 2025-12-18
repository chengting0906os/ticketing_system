# TDD Refactor Phase: Improving Code Quality

## Goal

In TDD's green phase, we made all tests pass (green light 🟢). Now we enter the refactor phase:

**Improve code quality while keeping all tests passing.**

Refactoring is not rewriting. It's a series of small steps to gradually improve the internal structure of code while maintaining external behavior.

---

## Core Principles

### 1. Test Protection Principle

**After each refactoring, ensure all tests still pass.**

```
Before refactor → run tests ✅ all pass
↓
Perform refactoring
↓
After refactor → run tests immediately ✅ must all pass
```

If tests fail, rollback immediately and find the problem.

### 2. Small Steps Principle

**Make one small refactoring at a time. Don't change too much at once.**

```
Step 1: small refactor → uv run pytest test/service/ticketing/ ✅
Step 2: small refactor → uv run pytest test/service/ticketing/ ✅
Step 3: small refactor → uv run pytest test/service/ticketing/ ✅
```

### 3. Preserve Behavior Principle

**Refactoring only changes internal structure, not external behavior.**

Don't add new features or change logic during refactoring.

---

## Common Improvement Directions

The purpose of refactoring is to improve code quality. Common improvements include:

- **Improve readability**: Clearer naming, shorter methods
- **Eliminate duplication**: Extract repeated code
- **Simplify logic**: Simplify complex conditionals
- **Improve structure**: Organize related code together

How to refactor depends on your judgment and experience with code quality.

### ⚠️ Key Reminder: Don't Force Refactoring

**If you don't find clear areas for improvement, don't force refactoring.**

The principle of refactoring is "improve code quality", not "refactor for the sake of refactoring".

```
❌ Don't do this:
- Code is already clean and clear, but still forcibly extract methods
- No duplication exists, but still artificially create generic logic
- Forcibly use design patterns, making code more complex

✅ Correct approach:
- Only refactor when there's real room for improvement
- If code is readable and has no duplication, keep it as is
- Follow the YAGNI principle (You Aren't Gonna Need It)
```

**Golden rule of refactoring**: Under test protection, make valuable improvements; skip if none exist.

---

## Refactoring Flow

```
1. Confirm tests pass (green light 🟢)
2. Perform refactoring
3. Run tests → confirm still passing ✅
4. If tests fail → rollback, find the problem
5. Complete refactoring → enter next TDD cycle
```

---

## Shared Step Definitions Refactoring in BDD Tests

### Purpose
Extract repeated BDD step definitions to `test/bdd_conftest/`, reducing duplication and improving maintainability.

### Problem: Duplicated Step Definitions

Before refactoring, each feature's conftest.py needs to define the same steps repeatedly:

```python
# test/service/ticketing/booking/conftest.py
@given('I am logged in as a buyer', target_fixture='client')
def given_logged_in_as_buyer(buyer_user, test_client, context):
    # Duplicated code
    test_client.headers['Authorization'] = f'Bearer {buyer_user.token}'
    context['client'] = test_client
    return test_client

@then(parsers.parse('the response status code should be {status_code:d}'))
def then_response_status_code(status_code, context):
    # Duplicated code
    response = context['response']
    assert response.status_code == status_code
```

**Drawbacks**:
- Large amount of duplicated code
- Need to modify multiple places when changing a step
- Violates DRY (Don't Repeat Yourself) principle

### Solution: Centralized Management with bdd_conftest

#### Step 1: Create Shared Step Definitions

Extract all shared steps to `test/bdd_conftest/`:

```python
# test/bdd_conftest/given_step_conftest.py
"""Common BDD Given Step Definitions."""

from typing import Any
from pytest_bdd import given, parsers


@given('I am logged in as a buyer', target_fixture='client')
def given_logged_in_as_buyer(
    buyer_user: Any,
    client: Any,
    context: dict[str, Any],
) -> Any:
    """Login as buyer user."""
    client.headers['Authorization'] = f'Bearer {buyer_user["token"]}'
    context['current_user'] = buyer_user
    return client


@given('I am logged in as a seller', target_fixture='client')
def given_logged_in_as_seller(
    seller_user: Any,
    client: Any,
    context: dict[str, Any],
) -> Any:
    """Login as seller user."""
    client.headers['Authorization'] = f'Bearer {seller_user["token"]}'
    context['current_user'] = seller_user
    return client
```

```python
# test/bdd_conftest/when_step_conftest.py
"""Common BDD When Step Definitions."""

from typing import Any
from fastapi.testclient import TestClient
from pytest_bdd import parsers, when
from pytest_bdd.model import Step

from test.bdd_conftest.shared_step_utils import (
    extract_table_data,
    resolve_endpoint_vars,
)


@when(parsers.parse('I call POST "{endpoint}" with'))
def when_call_post_with_data(
    step: Step,
    endpoint: str,
    client: TestClient,
    context: dict[str, Any],
) -> None:
    """Call POST API with table data."""
    resolved_endpoint = resolve_endpoint_vars(endpoint, context)
    data = extract_table_data(step)
    response = client.post(resolved_endpoint, json=data)
    context['response'] = response
    context['response_data'] = response.json() if response.content else None


@when(parsers.parse('I call GET "{endpoint}"'))
def when_call_get(
    endpoint: str,
    client: TestClient,
    context: dict[str, Any],
) -> None:
    """Call GET API."""
    resolved_endpoint = resolve_endpoint_vars(endpoint, context)
    response = client.get(resolved_endpoint)
    context['response'] = response
    context['response_data'] = response.json() if response.content else None
```

```python
# test/bdd_conftest/then_step_conftest.py
"""Common BDD Then Step Definitions."""

from typing import Any
import httpx
from pytest_bdd import parsers, then


@then(parsers.parse('the response status code should be {status_code:d}'))
def then_response_status_code(
    status_code: int,
    context: dict[str, Any],
) -> None:
    """Verify response status code."""
    response: httpx.Response = context['response']
    assert response.status_code == status_code, (
        f'Expected {status_code}, got {response.status_code}: {response.text}'
    )


@then('the response data should include:')
def then_response_data_should_include(
    step: Step,
    context: dict[str, Any],
) -> None:
    """Verify response data includes specified field-value pairs."""
    response_data = context.get('response_data')
    assert response_data is not None, 'Response data is empty'
    # ... validation logic
```

#### Step 2: Import in loader.py

```python
# test/loader.py
"""BDD Step Definitions Loader.

This module imports all step definitions to make them available to pytest-bdd.
"""

from test.bdd_conftest.given_step_conftest import *  # noqa: F401, F403
from test.bdd_conftest.when_step_conftest import *  # noqa: F401, F403
from test.bdd_conftest.then_step_conftest import *  # noqa: F401, F403
```

#### Step 3: Feature-specific conftest.py Only Defines Specific Steps

```python
# test/service/ticketing/booking/conftest.py
"""Booking-specific step definitions."""

from typing import Any
from pytest_bdd import given, parsers


@given(parsers.parse('an event exists with id "{event_id}"'))
def given_event_exists(
    event_id: str,
    context: dict[str, Any],
    async_session,
) -> None:
    """Create an event for testing."""
    # Booking-specific setup logic
    context['event_id'] = event_id
```

### Refactoring Comparison

#### Before Refactoring
```python
# Each feature's conftest.py has 50+ lines of duplicated step definitions
test/service/ticketing/booking/conftest.py      # 50+ lines
test/service/ticketing/event/conftest.py        # 50+ lines (duplicated)
test/service/ticketing/user/conftest.py         # 50+ lines (duplicated)
```

**Total lines**: ~150+ lines
**Maintainability**: Poor (need to modify multiple places when changing a step)

#### After Refactoring
```python
# Shared steps centrally managed
test/bdd_conftest/given_step_conftest.py    # Authentication steps
test/bdd_conftest/when_step_conftest.py     # HTTP action steps
test/bdd_conftest/then_step_conftest.py     # Assertion steps
test/service/ticketing/booking/conftest.py  # 20 lines (only booking-specific steps)
test/service/ticketing/event/conftest.py    # 20 lines (only event-specific steps)
```

**Total lines**: ~200 lines (more organized)
**Maintainability**: Excellent (shared steps only need one change)

---

## Feature-specific Step Definitions Management

### Purpose
Place feature-specific setup steps (like creating test data) in their respective conftest.py.

### Example: booking/conftest.py

```python
# test/service/ticketing/booking/conftest.py
"""Booking-specific step definitions."""

from typing import Any
from pytest_bdd import given, parsers
from sqlalchemy.ext.asyncio import AsyncSession


@given(parsers.parse('a booking exists with status "{status}"'))
def given_booking_exists(
    status: str,
    context: dict[str, Any],
    async_session: AsyncSession,
) -> None:
    """Create a booking with specified status for testing."""
    from src.service.ticketing.infra.repository.booking_command_repo_impl import (
        BookingCommandRepoImpl,
    )
    # Create booking with specified status
    repo = BookingCommandRepoImpl(session=async_session)
    booking = await repo.create(status=status, ...)
    context['booking'] = booking


@given('the booking has been paid')
def given_booking_paid(
    context: dict[str, Any],
) -> None:
    """Mark the booking as paid."""
    booking = context['booking']
    # Update booking status logic
```

### Example: event_ticketing/conftest.py

```python
# test/service/ticketing/event_ticketing/conftest.py
"""Event-specific step definitions."""

from typing import Any
from pytest_bdd import given, parsers


@given(parsers.parse('an event exists with name "{name}"'))
def given_event_exists(
    name: str,
    context: dict[str, Any],
    async_session,
) -> None:
    """Create an event for testing."""
    from src.service.ticketing.infra.repository.event_command_repo_impl import (
        EventCommandRepoImpl,
    )
    repo = EventCommandRepoImpl(session=async_session)
    event = await repo.create(name=name, ...)
    context['event'] = event
    context['event_id'] = str(event.id)


@given(parsers.parse('the event "{name}" has {count:d} available tickets'))
def given_event_has_tickets(
    name: str,
    count: int,
    context: dict[str, Any],
) -> None:
    """Create tickets for the event."""
    event = context['event']
    # Create tickets logic
```

---

## Refactoring Guidelines

### ✅ Should Be in bdd_conftest/

1. **Shared Given steps** (authentication, common setup)
2. **Shared When steps** (HTTP requests)
3. **Shared Then steps** (response validation)
4. **Shared utility functions** (table parsing, endpoint resolution)

### ✅ Should Be in Feature conftest.py

1. **Feature-specific Given steps** (create booking, create event)
2. **Feature-specific mock setup** (external service mocks)
3. **Feature-specific Then steps** (domain-specific assertions)

### ❌ Don't Do This

1. **Define steps in test files** (steps should be in conftest.py)
2. **Duplicate the same step** (use bdd_conftest/)
3. **Put business logic in steps** (steps only do setup/assertion)

---

## Refactoring Checklist

When refactoring BDD test steps, confirm:

- [ ] ✅ Shared steps moved to `test/bdd_conftest/`
- [ ] ✅ `test/loader.py` imports all step modules
- [ ] ✅ Feature conftest.py only defines specific steps
- [ ] ✅ All steps have clear docstrings
- [ ] ✅ All tests still pass 🟢
- [ ] ✅ Code lines significantly reduced or better organized

---

## Remember

The core spirit of refactoring:
1. **Improve code quality under test protection**
2. **Small steps, frequent testing**
3. **Only change structure, not behavior**

**Core thought**:
> Let step definitions focus on "what to do", not repeatedly defining "how to do it".

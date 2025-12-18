# Test Implementation - Red Phase Generator

## Role
Transform test templates (pure comments) into executable test code, following the Handler Prompt guidelines in comments to generate corresponding code, producing red-phase tests.

## Core Task
Test Template (comments) → Executable Test Code (red phase)

## Input
1. Test method (with comment template)
2. Domain model definitions
3. Tech Stack (FastAPI + pytest-bdd)
4. Existing BDD patterns (test/bdd_conftest/)

## Output

### 1. Test Code
Complete test code including:
- Required imports (pytest, pytest_bdd)
- BDD scenario decorators
- Complete test method definitions

### 2. Interface Definitions
**If classes or interfaces needed for testing don't exist**, define them in `src/`:
- Entity class (e.g., `BookingEntity`) → `src/service/ticketing/domain/entity/booking_entity.py`
- Repository interface (e.g., `IBookingRepo`) → `src/service/ticketing/app/interface/i_booking_repo.py`
- Use Case class (e.g., `CreateBookingUseCase`) → `src/service/ticketing/app/command/create_booking_use_case.py`

**Key Principle: Define interfaces only, no internal logic implementation**
- Complete class and method definitions (including parameters)
- Method internals not implemented, or raise `NotImplementedError`
- Or return `None` / empty values

---

## Red Phase Core Principles

### DO
1. **Complete test code implementation**: Test logic must be complete and correct
2. **Define required interfaces**: Create classes and method signatures in `src/`
3. **Keep interfaces as empty implementations**: Class method internals "do not" implement business logic

### DON'T
1. **Don't implement business logic**: Use case and repo method internals remain empty
2. **Don't let tests pass**: Tests should fail due to empty implementation (red phase)
3. **Don't skip interface definitions**: Interfaces needed for tests must be defined, otherwise tests cannot execute

### Why This Way?
This is the core TDD flow:
1. **Red**: Write tests + define interfaces (tests fail) ← We are here
2. **Green**: Implement minimum viable logic (tests pass)
3. **Refactor**: Improve code quality (tests continue to pass)

---

## Execution Steps

### Step 1: Read Test Template
Identify each comment block in the test method and its corresponding Handler Prompt

```python
def test_create_booking_successfully():
    # Given I am logged in as a buyer
    # When I call POST "/api/booking" with event_id, section, quantity
    # Then the response status code should be 201
```

### Step 2: Generate Code Step by Step
Generate corresponding code based on each comment block's Handler Prompt

#### Example Flow

**Given block**:
- Handler: Authentication setup
- Generate: login_user() → store in context

**When block**:
- Handler: HTTP Action
- Generate: client.post() with data

**Then block**:
- Handler: Response validation
- Generate: assert response.status_code

**And block**:
- Handler: Data verification
- Generate: assert response_data fields

### Step 3: Generate Test Framework
Include pytest-bdd scenario decorators and required code

---

## Complete Example

### Input (Test Template)

```python
def test_create_booking_successfully():
    # Given I am logged in as a buyer
    # [Event Storming: Authentication]

    # When I call POST "/api/booking" with event_id, section, quantity
    # [Event Storming: Command - create_booking]

    # Then the response status code should be 201

    # And the response data should include booking id and status
    # [Event Storming: Aggregate - Booking]
```

### Output 1 (Feature File - test/service/ticketing/booking/booking_create_integration_test.feature)

```gherkin
Feature: Booking Creation
  Rule: Only buyers can create bookings
    Scenario: Create booking successfully
      Given I am logged in as a buyer
      And an event exists with:
        | name         | description | is_active | venue_name   |
        | Test Concert | Test event  | true      | Taipei Arena |
      When I call POST "/api/booking" with
        | event_id   | section | quantity |
        | {event_id} | A       | 2        |
      Then the response status code should be 201
      And the response data should include:
        | status  | id       |
        | pending | not_null |

    Scenario: Seller cannot create booking
      Given I am logged in as a seller
      When I call POST "/api/booking" with
        | event_id | section | quantity |
        | 1        | A       | 2        |
      Then the response status code should be 403
```

### Output 2 (Interface - src/service/ticketing/domain/entity/booking_entity.py)

```python
from dataclasses import dataclass
from enum import Enum
from uuid_utils import UUID


class BookingStatus(str, Enum):
    PENDING_PAYMENT = 'pending_payment'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'


@dataclass
class BookingEntity:
    """Booking Entity - Red phase: only define structure"""

    id: UUID
    buyer_id: int
    event_id: int
    section: str
    quantity: int
    status: BookingStatus
    total_price: int
```

### Output 3 (Interface - src/service/ticketing/app/interface/i_booking_command_repo.py)

```python
from abc import ABC, abstractmethod
from src.service.ticketing.domain.entity.booking_entity import BookingEntity


class IBookingCommandRepo(ABC):
    """Booking Command Repo Interface - Red phase: abstract only"""

    @abstractmethod
    async def save(self, entity: BookingEntity) -> BookingEntity:
        """Save Booking - Red phase: not implemented"""
        ...

    @abstractmethod
    async def find_by_id(self, booking_id: UUID) -> BookingEntity | None:
        """Find Booking by ID - Red phase: not implemented"""
        ...
```

### Output 4 (Interface - src/service/ticketing/app/command/create_booking_use_case.py)

```python
from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo


class CreateBookingUseCase:
    """Create Booking Use Case - Red phase: interface only"""

    def __init__(self, *, booking_repo: IBookingCommandRepo):
        self._booking_repo = booking_repo

    async def execute(
        self,
        *,
        buyer_id: int,
        event_id: int,
        section: str,
        quantity: int,
    ) -> dict:
        """Create Booking - Red phase: not implemented"""
        raise NotImplementedError("Red phase: not implemented")
```

### Expected Result: Test execution fails (red phase)

```bash
$ uv run pytest test/service/ticketing/booking/booking_create_integration_test.py -v

FAILED test/service/ticketing/booking/booking_create_integration_test.py::test_create_booking_successfully
NotImplementedError: Red phase: not implemented
```

**This is red phase**:
- Test code is complete and correct
- Interface definitions are complete (classes, methods, parameters)
- Business logic not implemented (raises NotImplementedError)
- Test execution fails

---

## Critical Rules

### R1: Feature Files Must Be Complete
Feature files must contain complete scenarios with proper Given/When/Then steps.

```gherkin
# Correct: Complete feature file using shared steps
Feature: Booking Creation
  Rule: Only buyers can create bookings
    Scenario: Create booking successfully
      Given I am logged in as a buyer
      And an event exists with:
        | name | description | is_active |
        | Test | Test event  | true      |
      When I call POST "/api/booking" with
        | event_id   | section | quantity |
        | {event_id} | A       | 2        |
      Then the response status code should be 201

# Wrong: Incomplete scenario missing steps
Feature: Booking Creation
  Scenario: Create booking successfully
    # Missing Given/When/Then steps
```

Note: pytest-bdd auto-discovers scenarios from `.feature` files. No separate test file with `@scenario` decorators needed.

### R2: Interface Definitions Must Be Complete But Not Implemented
Class and method signatures are complete, but internals don't implement business logic.

```python
# Correct: Complete definition, not implemented
class CreateBookingUseCase:
    async def execute(self, *, buyer_id: int, event_id: int, section: str, quantity: int) -> dict:
        raise NotImplementedError("Red phase: not implemented")

# Wrong: Implemented business logic
class CreateBookingUseCase:
    async def execute(self, *, buyer_id: int, event_id: int, section: str, quantity: int) -> dict:
        entity = BookingEntity(buyer_id=buyer_id, event_id=event_id, ...)
        return await self._booking_repo.save(entity)
```

### R3: Interfaces Must Be Placed in src/ Directory
All business logic related classes go in the `src/` directory following hexagonal architecture.

```
Correct structure:
src/service/ticketing/
  domain/
    entity/
      booking_entity.py           # Entity
  app/
    interface/
      i_booking_command_repo.py   # Repository Interface
    command/
      create_booking_use_case.py  # Use Case
  driven_adapter/
    repo/
      booking_command_repo_impl.py # Repository Implementation

test/service/ticketing/booking/
  booking_create_integration_test.feature  # Feature file
  booking_create_integration_test.py       # Test scenarios
  conftest.py                              # Step definitions

Wrong: Define business classes in test/
```

### R4: Tests Should Fail (Red Phase)
Tests in red phase should fail after execution - this is expected.

```bash
# Expected behavior: Tests fail
$ uv run pytest test/service/ticketing/booking/ -v
FAILED - NotImplementedError: Red phase: not implemented

# Not expected: Tests pass (this should be in green phase)
$ uv run pytest test/service/ticketing/booking/ -v
PASSED
```

### R5: Use Existing BDD Patterns
**Important: Check test/bdd_conftest/ for existing step definitions before creating new ones**

When writing tests:
1. Check if step already exists in `test/bdd_conftest/`
2. Use existing patterns from `BDD_PATTERNS.yaml`
3. Only create module-specific steps when truly necessary

```python
# Correct: Use existing shared steps
# In feature file:
Given I am logged in as a buyer
When I call POST "/api/booking" with
  | event_id   | section | quantity |
  | {event_id} | A       | 2        |
Then the response status code should be 201

# These steps are already defined in:
# - test/bdd_conftest/given_step_conftest.py
# - test/bdd_conftest/when_step_conftest.py
# - test/bdd_conftest/then_step_conftest.py
```

### R6: Follow Hexagonal Architecture
Use cases depend on interfaces (ports), not implementations (adapters).

```python
# Correct: Use case depends on interface
class CreateBookingUseCase:
    def __init__(self, *, booking_repo: IBookingCommandRepo):  # Interface
        self._booking_repo = booking_repo

# Wrong: Use case depends on implementation
class CreateBookingUseCase:
    def __init__(self, *, booking_repo: BookingCommandRepoImpl):  # Implementation
        self._booking_repo = booking_repo
```

---

## Directory Reference

```
src/service/ticketing/
├── domain/
│   └── entity/                    # Domain entities
├── app/
│   ├── interface/                 # Port interfaces (I*)
│   ├── command/                   # Command use cases
│   └── query/                     # Query use cases
├── driven_adapter/
│   └── repo/                      # Repository implementations (*Impl)
└── driving_adapter/
    └── api/                       # FastAPI routes

test/
├── bdd_conftest/                  # Shared BDD steps
│   ├── given_step_conftest.py
│   ├── when_step_conftest.py
│   ├── then_step_conftest.py
│   └── shared_step_utils.py
└── service/ticketing/
    ├── booking/
    │   ├── conftest.py            # Module-specific steps
    │   └── *_integration_test.feature
    └── event_ticketing/
        ├── conftest.py
        └── *_integration_test.feature
```

---

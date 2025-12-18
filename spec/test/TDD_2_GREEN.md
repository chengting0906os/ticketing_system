# TDD Green Phase: Making Tests Pass

## Goal

In the TDD red phase, tests were written and confirmed to fail (red 🔴). Now entering the green phase:

**Write the minimum code to make tests pass, continuously trial-and-error until all tests turn green.**

---

## Core Principles

### 1. Minimum Increment Development

Only write the minimum code needed to pass tests, nothing more.

```python
# ❌ Doing too much (tests don't require these)
async def create_booking(self, *, buyer_id: int, event_id: int, section: str, quantity: int) -> dict:
    validate_event_status(event_id)        # No test for this
    log_operation(buyer_id, event_id)      # No test for this
    send_notification()                     # No test for this
    entity = BookingEntity(...)
    return await self._repo.save(entity)

# ✅ Just enough (only implement what tests require)
async def create_booking(self, *, buyer_id: int, event_id: int, section: str, quantity: int) -> dict:
    entity = BookingEntity(
        id=uuid.uuid7(),
        buyer_id=buyer_id,
        event_id=event_id,
        section=section,
        quantity=quantity,
        status=BookingStatus.PENDING_PAYMENT,
    )
    created = await self._repo.save(entity)
    return {'id': str(created.id), 'status': created.status.value}
```

### 2. Trial-and-Error Flow

```
1. Run tests → See which one fails
2. Write minimum code to fix
3. Run tests → Still failing?
4. Repeat 2-3 until all pass
```

**Don't write everything at once** - let tests drive you step by step.

---

## UseCase / Repository Responsibility Distribution

### Repository Responsibility: Data Access

- Responsible for storing, querying, deleting data
- Only manages CRUD operations, not business logic
- Encapsulates SQLAlchemy operations, converts Model to Entity

**Example (src/service/ticketing/driven_adapter/repo/booking_command_repo_impl.py)**:
```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
from src.service.ticketing.domain.entity.booking_entity import BookingEntity
from src.service.ticketing.driven_adapter.model.booking_model import Booking


class BookingCommandRepoImpl(IBookingCommandRepo):
    """Repository implementation - encapsulates SQLAlchemy operations"""

    def __init__(self, *, session: AsyncSession):
        self._session = session

    async def save(self, entity: BookingEntity) -> BookingEntity:
        """Encapsulate SQLAlchemy save logic"""
        booking = Booking(
            id=entity.id,
            buyer_id=entity.buyer_id,
            event_id=entity.event_id,
            section=entity.section,
            quantity=entity.quantity,
            status=entity.status.value,
            total_price=entity.total_price,
        )
        self._session.add(booking)
        await self._session.flush()
        return entity

    async def find_by_id(self, *, booking_id: UUID) -> BookingEntity | None:
        """Encapsulate SQLAlchemy query logic"""
        stmt = select(Booking).where(Booking.id == booking_id)
        result = await self._session.execute(stmt)
        booking = result.scalar_one_or_none()
        if not booking:
            return None
        return BookingEntity(
            id=booking.id,
            buyer_id=booking.buyer_id,
            event_id=booking.event_id,
            section=booking.section,
            quantity=booking.quantity,
            status=BookingStatus(booking.status),
            total_price=booking.total_price,
        )
```

**Key Principle**: Repository only handles Entity ↔ Model conversion and ORM operations. UseCase doesn't need to know SQLAlchemy details.

### UseCase Responsibility: Business Logic

- Responsible for implementing business rules and flows
- Read and store data through repositories
- **Must support dependency injection** (tests can inject repos)

**Example (src/service/ticketing/app/command/create_booking_use_case.py)**:
```python
import uuid_utils as uuid
from uuid_utils import UUID

from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
from src.service.ticketing.app.interface.i_event_query_repo import IEventQueryRepo
from src.service.ticketing.domain.entity.booking_entity import BookingEntity, BookingStatus
from src.service.ticketing.domain.exception import InsufficientSeatsError, EventNotFoundError


class CreateBookingUseCase:
    def __init__(
        self,
        *,
        booking_repo: IBookingCommandRepo,
        event_repo: IEventQueryRepo,
    ) -> None:
        """Initialize use case with injected repositories."""
        self._booking_repo = booking_repo
        self._event_repo = event_repo

    async def execute(
        self,
        *,
        buyer_id: int,
        event_id: int,
        section: str,
        quantity: int,
    ) -> dict:
        """Create a new booking."""
        # Business rule: Check event exists
        event = await self._event_repo.find_by_id(event_id=event_id)
        if not event:
            raise EventNotFoundError(f'Event {event_id} not found')

        # Business rule: Check seat availability
        available_seats = await self._event_repo.get_available_seats(
            event_id=event_id,
            section=section,
        )
        if available_seats < quantity:
            raise InsufficientSeatsError(f'Only {available_seats} seats available')

        # Create Entity
        booking_id = uuid.uuid7()
        entity = BookingEntity(
            id=booking_id,
            buyer_id=buyer_id,
            event_id=event_id,
            section=section,
            quantity=quantity,
            status=BookingStatus.PENDING_PAYMENT,
            total_price=quantity * event.price,
        )

        # Save through repo
        created = await self._booking_repo.save(entity)

        return {
            'id': str(created.id),
            'status': created.status.value,
            'total_price': created.total_price,
        }
```

### Why Dependency Injection?

**Allows tests and UseCase to use the same repo instance, making state verification easier.**

In this project, BDD tests perform integration testing through HTTP API. Dependency injection is mainly used for:
1. Injecting Mock Repo in unit tests
2. Using real repositories in integration tests with proper transaction management

---

## Hexagonal Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    Driving Adapters                         │
│  (FastAPI routes, CLI, Kafka consumers)                     │
├─────────────────────────────────────────────────────────────┤
│                    Application Layer                        │
│  (Use Cases - business logic orchestration)                 │
├─────────────────────────────────────────────────────────────┤
│                    Domain Layer                             │
│  (Entities, Value Objects, Domain Services)                 │
├─────────────────────────────────────────────────────────────┤
│                    Driven Adapters                          │
│  (Repository Impl, Message Queue, External Services)        │
└─────────────────────────────────────────────────────────────┘
```

**Direction of Dependencies**:
- Use Cases depend on Interfaces (ports), not Implementations
- Driven Adapters implement Interfaces
- Domain layer has no external dependencies

---

## Common Implementation Patterns

### Pattern 1: Simple CRUD

```python
# Use Case - just delegates to repo
class GetBookingUseCase:
    def __init__(self, *, booking_repo: IBookingQueryRepo):
        self._repo = booking_repo

    async def execute(self, *, booking_id: UUID) -> dict | None:
        booking = await self._repo.find_by_id(booking_id=booking_id)
        if not booking:
            return None
        return booking.to_dict()
```

### Pattern 2: Business Rule Validation

```python
# Use Case - validates before action
class CancelBookingUseCase:
    async def execute(self, *, booking_id: UUID, user_id: int) -> dict:
        booking = await self._repo.find_by_id(booking_id=booking_id)

        # Business rule: Only owner can cancel
        if booking.buyer_id != user_id:
            raise PermissionDeniedError('Not your booking')

        # Business rule: Can only cancel pending bookings
        if booking.status != BookingStatus.PENDING_PAYMENT:
            raise InvalidStateError('Cannot cancel non-pending booking')

        booking.status = BookingStatus.CANCELLED
        await self._repo.save(booking)
        return booking.to_dict()
```

### Pattern 3: Cross-Repository Operation

```python
# Use Case - coordinates multiple repos
class CreateBookingWithTicketsUseCase:
    def __init__(
        self,
        *,
        booking_repo: IBookingCommandRepo,
        ticket_repo: ITicketCommandRepo,
    ):
        self._booking_repo = booking_repo
        self._ticket_repo = ticket_repo

    async def execute(self, *, buyer_id: int, event_id: int, seat_ids: list[int]) -> dict:
        # Reserve tickets first
        tickets = await self._ticket_repo.reserve_seats(
            seat_ids=seat_ids,
            buyer_id=buyer_id,
        )

        # Create booking
        booking = BookingEntity(...)
        await self._booking_repo.save(booking)

        return {'booking_id': str(booking.id), 'tickets': len(tickets)}
```

---

## Completion Criteria

Green phase is complete when:

- ✅ Run `uv run pytest test/service/ticketing/booking/` all tests pass (green 🟢)
- ✅ No compilation/runtime errors
- ✅ Code is simple and direct

**Not required**:
- ❌ Elegant code (leave for refactoring phase)
- ❌ Performance optimization (leave for refactoring phase)
- ❌ Complete error handling (if tests don't require, don't do)

---

## Remember

1. **Tests drive you** - Don't guess what's needed, let failing tests tell you
2. **Minimum implementation** - Only write code needed to pass tests
3. **Dependency injection** - Use cases must support injecting repositories
4. **Trial-and-Error** - Run tests → Fix → Run again, continuous loop
5. **Follow hexagonal architecture** - Use cases depend on interfaces, not implementations

After completing green phase, enter refactoring phase ♻️

---

## Quick Reference: Running Tests

```bash
# Run specific test file
uv run pytest test/service/ticketing/booking/booking_create_integration_test.feature -v

# Run all booking tests
uv run pytest test/service/ticketing/booking/ -v

# Run with output
uv run pytest test/service/ticketing/booking/ -v -s

# Run single scenario by name
uv run pytest -k "Create booking successfully" -v
```

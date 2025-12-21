"""
BDD Step Definitions for Reservation Integration Tests

Links Gherkin feature files with actual test logic using
the existing handlers and fixtures.

Note: pytest-bdd steps must be synchronous, so we use
asyncio.get_event_loop().run_until_complete() for async operations.
"""

import asyncio
from collections.abc import Coroutine
import os
import random
import time
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
import uuid_utils as uuid

from src.platform.config.di import container
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.reservation.driven_adapter.state.seat_state_command_handler_impl import (
    SeatStateCommandHandlerImpl,
)
from src.service.ticketing.driven_adapter.state.init_event_and_tickets_state_handler_impl import (
    InitEventAndTicketsStateHandlerImpl,
)
from test.kvrocks_test_client import kvrocks_test_client


# Load all feature scenarios
scenarios('seat_reservation.feature')
scenarios('seat_release.feature')


# =============================================================================
# Constants
# =============================================================================
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', 'test_')
_EVENT_ID_MOD = 10_000_000
_EVENT_ID_RANDOM_MAX = 9999


# =============================================================================
# Helper Functions
# =============================================================================
def _run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run async coroutine in sync context."""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


def _generate_unique_event_id() -> int:
    """Generate unique event_id for test isolation."""
    return int(time.time() * 1_000_000) % _EVENT_ID_MOD + random.randint(1, _EVENT_ID_RANDOM_MAX)


def _parse_subsection(subsection: str) -> tuple[str, int]:
    """Parse 'A-1' format to ('A', 1)."""
    section, subsec_num = subsection.split('-')
    return section, int(subsec_num)


def _make_key(key: str) -> str:
    return f'{_KEY_PREFIX}{key}'


@pytest.fixture
def context() -> dict[str, Any]:
    """Shared test context for storing state between steps"""
    return {}


@pytest.fixture
def seat_handler() -> SeatStateCommandHandlerImpl:
    """Create seat state command handler with proper DI"""
    _run_async(kvrocks_client.initialize())
    return container.seat_state_command_handler()


@pytest.fixture
def init_handler() -> InitEventAndTicketsStateHandlerImpl:
    """Create seat initialization handler"""
    _run_async(kvrocks_client.initialize())
    return InitEventAndTicketsStateHandlerImpl()


@pytest.fixture(scope='function')
def unique_event_id() -> int:
    """Generate unique event_id for test isolation"""
    return _generate_unique_event_id()


# =============================================================================
# Given Steps
# =============================================================================
@given('an event with seating configuration is initialized')
def event_initialized(context: dict[str, Any]) -> None:
    """Initialize context for event configuration"""
    context['subsections'] = {}
    context['event_id'] = _generate_unique_event_id()


@given(parsers.parse('subsection "{subsection}" has {rows:d} rows with {cols:d} seats'))
def subsection_has_seats(
    context: dict[str, Any],
    init_handler: InitEventAndTicketsStateHandlerImpl,
    subsection: str,
    rows: int,
    cols: int,
) -> None:
    """Initialize subsection with specified dimensions"""
    section, subsec_num = _parse_subsection(subsection)

    # Store subsection config
    context['subsections'][subsection] = {
        'rows': rows,
        'cols': cols,
        'section': section,
        'subsection': subsec_num,
    }
    context['current_subsection'] = subsection

    # Build seating config
    config = {
        'rows': rows,
        'cols': cols,
        'sections': [{'name': section, 'price': 1000, 'subsections': subsec_num}],
    }

    _run_async(
        init_handler.initialize_seats_from_config(
            event_id=context['event_id'], seating_config=config
        )
    )


@given(parsers.parse('seat "{seat_id}" is already reserved'))
def seat_is_reserved(
    context: dict[str, Any],
    seat_handler: SeatStateCommandHandlerImpl,
    seat_id: str,
) -> None:
    """Reserve a specific seat"""
    section, subsec_num = _parse_subsection(context['current_subsection'])

    booking_id = str(uuid.uuid7())
    _run_async(
        seat_handler.reserve_seats_atomic(
            event_id=context['event_id'],
            booking_id=booking_id,
            buyer_id=99,
            mode='manual',
            section=section,
            subsection=subsec_num,
            quantity=1,
            seat_ids=[seat_id],
        )
    )
    # Store booking_id for release operations
    context['last_booking_id'] = booking_id


@given(parsers.parse('seats "{seat_ids}" are already reserved'))
def seats_are_reserved(
    context: dict[str, Any],
    seat_handler: SeatStateCommandHandlerImpl,
    seat_ids: str,
) -> None:
    """Reserve multiple specific seats"""
    section, subsec_num = _parse_subsection(context['current_subsection'])

    seats = [s.strip() for s in seat_ids.split(',')]
    booking_id = str(uuid.uuid7())
    _run_async(
        seat_handler.reserve_seats_atomic(
            event_id=context['event_id'],
            booking_id=booking_id,
            buyer_id=99,
            mode='manual',
            section=section,
            subsection=subsec_num,
            quantity=len(seats),
            seat_ids=seats,
        )
    )
    # Store booking_id for release operations
    context['last_booking_id'] = booking_id


@given(parsers.parse('seat "{seat_id}" bitfield status should be {expected_status:d}'))
def verify_bitfield_status_given(
    context: dict[str, Any],
    seat_id: str,
    expected_status: int,
) -> None:
    """Verify seat bitfield status (for Given/When steps)"""
    _verify_bitfield_status_sync(context, seat_id, expected_status)


# =============================================================================
# When Steps
# =============================================================================
@when(parsers.parse('I request to reserve seat "{seat_id}" in manual mode'))
def reserve_single_seat_manual(
    context: dict[str, Any],
    seat_handler: SeatStateCommandHandlerImpl,
    seat_id: str,
) -> None:
    """Reserve a single seat in manual mode"""
    section, subsec_num = _parse_subsection(context['current_subsection'])

    booking_id = str(uuid.uuid7())
    result = _run_async(
        seat_handler.reserve_seats_atomic(
            event_id=context['event_id'],
            booking_id=booking_id,
            buyer_id=1,
            mode='manual',
            section=section,
            subsection=subsec_num,
            quantity=1,
            seat_ids=[seat_id],
        )
    )
    context['result'] = result


@when(parsers.parse('I request to reserve seats "{seat_ids}" in manual mode'))
def reserve_multiple_seats_manual(
    context: dict[str, Any],
    seat_handler: SeatStateCommandHandlerImpl,
    seat_ids: str,
) -> None:
    """Reserve multiple seats in manual mode"""
    section, subsec_num = _parse_subsection(context['current_subsection'])

    seats = [s.strip() for s in seat_ids.split(',')]
    booking_id = str(uuid.uuid7())
    result = _run_async(
        seat_handler.reserve_seats_atomic(
            event_id=context['event_id'],
            booking_id=booking_id,
            buyer_id=1,
            mode='manual',
            section=section,
            subsection=subsec_num,
            quantity=len(seats),
            seat_ids=seats,
        )
    )
    context['result'] = result


@when(parsers.parse('I request {quantity:d} seats in best_available mode'))
def reserve_best_available(
    context: dict[str, Any],
    seat_handler: SeatStateCommandHandlerImpl,
    quantity: int,
) -> None:
    """Reserve seats using best_available mode"""
    subsection = context['current_subsection']
    section, subsec_num = _parse_subsection(subsection)
    config = context['subsections'][subsection]

    booking_id = str(uuid.uuid7())
    result = _run_async(
        seat_handler.reserve_seats_atomic(
            event_id=context['event_id'],
            booking_id=booking_id,
            buyer_id=1,
            mode='best_available',
            section=section,
            subsection=subsec_num,
            quantity=quantity,
            rows=config['rows'],
            cols=config['cols'],
            price=1000,
        )
    )
    context['result'] = result


@when(parsers.parse('I release seat "{seat_id}" in subsection "{subsection}"'))
def release_seat(
    context: dict[str, Any],
    seat_handler: SeatStateCommandHandlerImpl,
    seat_id: str,
    subsection: str,
) -> None:
    """Release a reserved seat"""
    section, subsec_num = _parse_subsection(subsection)
    booking_id = context.get('last_booking_id', str(uuid.uuid7()))

    results = _run_async(
        seat_handler.release_seats(
            booking_id=booking_id,
            seat_positions=[seat_id],
            event_id=context['event_id'],
            section=section,
            subsection=subsec_num,
        )
    )
    context['result'] = {'success': results.get(seat_id, False)}
    context['release_results'] = results


@when(parsers.parse('I release seats "{seat_ids}" in subsection "{subsection}"'))
def release_multiple_seats(
    context: dict[str, Any],
    seat_handler: SeatStateCommandHandlerImpl,
    seat_ids: str,
    subsection: str,
) -> None:
    """Release multiple reserved seats"""
    section, subsec_num = _parse_subsection(subsection)
    seats = [s.strip() for s in seat_ids.split(',')]
    booking_id = context.get('last_booking_id', str(uuid.uuid7()))

    results = _run_async(
        seat_handler.release_seats(
            booking_id=booking_id,
            seat_positions=seats,
            event_id=context['event_id'],
            section=section,
            subsection=subsec_num,
        )
    )
    # Count successful releases
    success_count = sum(1 for v in results.values() if v)
    context['result'] = {'success': success_count > 0, 'released_count': success_count}
    context['release_results'] = results


# =============================================================================
# Then Steps
# =============================================================================
@then('the reservation should succeed')
def reservation_should_succeed(context: dict[str, Any]) -> None:
    """Verify reservation succeeded"""
    assert context['result']['success'] is True


@then('the reservation should fail')
def reservation_should_fail(context: dict[str, Any]) -> None:
    """Verify reservation failed"""
    assert context['result']['success'] is False


@then('the release should succeed')
def release_should_succeed(context: dict[str, Any]) -> None:
    """Verify release succeeded"""
    assert context['result']['success'] is True


@then(parsers.parse('{count:d} seats should be reserved'))
def verify_seat_count(context: dict[str, Any], count: int) -> None:
    """Verify number of reserved seats"""
    assert len(context['result']['reserved_seats']) == count


@then(parsers.parse('{count:d} seats should be released'))
def verify_released_count(context: dict[str, Any], count: int) -> None:
    """Verify number of released seats"""
    assert context['result']['released_count'] == count


@then('all requested seats should have status RESERVED')
def all_requested_reserved(context: dict[str, Any]) -> None:
    """Verify all reserved seats have RESERVED status"""
    for seat_id in context['result']['reserved_seats']:
        _verify_seat_status_sync(context, seat_id, 'RESERVED')


@then('all seats in subsection should be AVAILABLE')
def all_seats_available(context: dict[str, Any]) -> None:
    """Verify all seats in current subsection are AVAILABLE"""
    subsection = context['current_subsection']
    config = context['subsections'][subsection]
    rows = config['rows']
    cols = config['cols']

    for row in range(1, rows + 1):
        for col in range(1, cols + 1):
            seat_id = f'{row}-{col}'
            _verify_seat_status_sync(context, seat_id, 'AVAILABLE')


@then(parsers.parse('seat "{seat_id}" should have status AVAILABLE'))
def seat_should_be_available(context: dict[str, Any], seat_id: str) -> None:
    """Verify seat has AVAILABLE status"""
    _verify_seat_status_sync(context, seat_id, 'AVAILABLE')


@then(parsers.parse('seat "{seat_id}" should have status RESERVED'))
def seat_should_be_reserved(context: dict[str, Any], seat_id: str) -> None:
    """Verify seat has RESERVED status"""
    _verify_seat_status_sync(context, seat_id, 'RESERVED')


@then(parsers.parse('I should receive consecutive seats "{seat_ids}"'))
def should_receive_consecutive_seats(context: dict[str, Any], seat_ids: str) -> None:
    """Verify received specific consecutive seats"""
    expected = [s.strip() for s in seat_ids.split(',')]
    assert context['result']['reserved_seats'] == expected


@then(parsers.parse('I should receive scattered seats "{seat_ids}"'))
def should_receive_scattered_seats(context: dict[str, Any], seat_ids: str) -> None:
    """Verify received specific scattered seats"""
    expected = set(s.strip() for s in seat_ids.split(','))
    assert set(context['result']['reserved_seats']) == expected


@then(parsers.parse('seat "{seat_id}" bitfield status should be {expected_status:d}'))
def verify_bitfield_status_then(
    context: dict[str, Any],
    seat_id: str,
    expected_status: int,
) -> None:
    """Verify seat bitfield status (for Then steps)"""
    _verify_bitfield_status_sync(context, seat_id, expected_status)


# =============================================================================
# Helper Functions (Sync versions)
# =============================================================================
def _verify_seat_status_sync(context: dict[str, Any], seat_id: str, expected_status: str) -> None:
    """Verify seat has expected status using bitfield"""
    # Note: Kvrocks only tracks AVAILABLE/RESERVED states now (2-bit for backward compat)
    status_map = {'AVAILABLE': 0, 'RESERVED': 1}
    _verify_bitfield_status_sync(context, seat_id, status_map[expected_status])


def _verify_bitfield_status_sync(
    context: dict[str, Any], seat_id: str, expected_status: int
) -> None:
    """Verify seat bitfield status directly (sync version)"""
    client = kvrocks_test_client.connect()

    subsection = context['current_subsection']
    section, subsec_num = _parse_subsection(subsection)
    config = context['subsections'][subsection]

    # Parse seat_id (format: "row-seat")
    row, seat = map(int, seat_id.split('-'))

    # Calculate seat_index (1-bit per seat: 0=available, 1=reserved)
    seat_index = (row - 1) * config['cols'] + (seat - 1)

    bf_key = _make_key(f'seats_bf:{context["event_id"]}:{section}-{subsec_num}')
    status = client.execute_command('BITFIELD', bf_key, 'GET', 'u1', seat_index)

    assert status == [expected_status], (
        f'Seat {seat_id} should have status {expected_status}, got {status}'
    )

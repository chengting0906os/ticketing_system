"""
BDD Step Definitions for Booking Tests

Booking-specific steps that extend the shared BDD patterns.
These steps handle complex booking scenarios that require:
- Multi-user/multi-event test setup (booking_list tests)
- Direct database setup for specific states
- Booking-specific verification (tickets, seat_positions)

Standard patterns from bdd_conftest/ are used where possible:
- Given: I am logged in as a seller/buyer, an event exists with:
- When: I call POST/GET/PATCH "{endpoint}" with
- Then: the response status code should be, the response data should include:
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

import bcrypt
from fastapi.testclient import TestClient
import orjson
from pytest_bdd import given, parsers, then, when
from pytest_bdd.model import Step
import uuid_utils as uuid

from src.platform.constant.route_constant import (
    BOOKING_GET,
    BOOKING_MY_BOOKINGS,
)
from test.bdd_conftest.shared_step_utils import (
    assert_response_status,
    extract_single_value,
    extract_table_data,
    login_user,
    resolve_table_vars,
)
from test.constants import (
    DEFAULT_PASSWORD,
    DEFAULT_SEATING_CONFIG_JSON,
    DEFAULT_VENUE_NAME,
)


# =============================================================================
# Helper Functions (Booking-specific)
# =============================================================================


def _store_response(context: dict[str, Any], response: Any) -> None:
    """Store response and response_data in context for verification steps."""
    context['response'] = response
    context['response_data'] = response.json() if response.content else None


def get_user_email_by_id(user_id: int) -> str:
    """Map user ID to email for booking_list multi-user tests.

    These IDs correspond to users created by 'users exist:' step.
    """
    user_email_map = {
        4: 'seller1@test.com',
        5: 'seller2@test.com',
        6: 'buyer1@test.com',
        7: 'buyer2@test.com',
        8: 'buyer3@test.com',
    }
    return user_email_map.get(user_id, f'user{user_id}@test.com')


def assert_nullable_field(
    data: dict[str, Any], field: str, expected: str, message: str | None = None
) -> None:
    if expected == 'not_null':
        assert data.get(field) is not None, message or f'{field} should not be null'
    elif expected == 'null':
        assert data.get(field) is None, message or f'{field} should be null'


def get_booking_details(client: TestClient, booking_id: int) -> dict[str, Any]:
    response = client.get(BOOKING_GET.format(booking_id=booking_id))
    assert_response_status(response, 200)
    return response.json()


# =============================================================================
# Given Steps (Booking-specific - not in shared patterns)
# =============================================================================


@given('a booking exists with:')
def create_booking_with_status(
    step: Step,
    client: TestClient,
    context: dict[str, Any],
    execute_sql_statement: Callable[..., list[dict[str, Any]] | None],
) -> None:
    """Create a booking with status from datatable."""
    raw_data = extract_table_data(step)
    booking_data = resolve_table_vars(raw_data, context)

    status = booking_data.get('status', 'pending_payment')
    event_id = int(booking_data.get('event_id') or context.get('event_id') or 1)
    buyer_id = int(booking_data.get('buyer_id') or context.get('buyer_id') or 1)
    total_price = int(booking_data['total_price'])
    booking_id = str(uuid.uuid7())

    execute_sql_statement(
        """
        INSERT INTO "booking" (id, buyer_id, event_id, section, subsection, quantity, total_price, status, seat_selection_mode, created_at, updated_at)
        VALUES (:id, :buyer_id, :event_id, :section, :subsection, :quantity, :total_price, :status, :seat_selection_mode, NOW(), NOW())
        """,
        {
            'id': booking_id,
            'buyer_id': buyer_id,
            'event_id': event_id,
            'section': 'A',
            'subsection': 1,
            'quantity': 2,
            'total_price': total_price,
            'status': status,  # Use actual status from test data
            'seat_selection_mode': 'manual',
        },
    )

    # Create reserved tickets
    available_tickets = execute_sql_statement(
        "SELECT id FROM ticket WHERE event_id = :event_id AND status = 'available' AND section = 'A' AND subsection = 1 ORDER BY id LIMIT 2",
        {'event_id': event_id},
        fetch=True,
    )

    ticket_ids = []
    seat_positions = []
    if available_tickets:
        for ticket in available_tickets:
            ticket_id = ticket['id']
            ticket_ids.append(ticket_id)
            execute_sql_statement(
                "UPDATE ticket SET status = 'reserved', buyer_id = :buyer_id WHERE id = :ticket_id",
                {'buyer_id': buyer_id, 'ticket_id': ticket_id},
            )
            ticket_info = execute_sql_statement(
                'SELECT row_number, seat_number FROM ticket WHERE id = :ticket_id',
                {'ticket_id': ticket_id},
                fetch=True,
            )
            if ticket_info:
                seat_positions.append(
                    f'{ticket_info[0]["row_number"]}-{ticket_info[0]["seat_number"]}'
                )

    if seat_positions:
        execute_sql_statement(
            'UPDATE booking SET seat_positions = :seat_positions WHERE id = :booking_id',
            {'booking_id': booking_id, 'seat_positions': seat_positions},
        )

    if status == 'completed':
        execute_sql_statement(
            'UPDATE "booking" SET status = \'completed\', paid_at = :paid_at WHERE id = :id',
            {'paid_at': datetime.now(), 'id': booking_id},
        )
    elif status == 'cancelled':
        execute_sql_statement(
            'UPDATE "booking" SET status = \'cancelled\' WHERE id = :id', {'id': booking_id}
        )
        execute_sql_statement(
            "UPDATE event SET status = 'available' WHERE id = :id", {'id': event_id}
        )

    context['booking'] = {'id': booking_id, 'status': status, 'event_id': event_id}
    if status == 'completed':
        context['booking']['paid_at'] = datetime.now().isoformat()
    context['buyer_id'] = buyer_id
    context['event_id'] = event_id
    context['ticket_ids'] = ticket_ids


@given('users exist:')
def create_users(
    step: Step,
    context: dict[str, Any],
    execute_sql_statement: Callable[..., list[dict[str, Any]] | None],
) -> None:
    """Create users for booking_list test."""
    rows = step.data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    context['users'] = {}
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        user_data = dict(zip(headers, values, strict=True))
        user_id = int(user_data['id'])
        hashed_password = bcrypt.hashpw(
            user_data['password'].encode('utf-8'), bcrypt.gensalt()
        ).decode('utf-8')
        execute_sql_statement(
            """
            INSERT INTO "user" (id, email, hashed_password, name, role, is_active, is_superuser, is_verified)
            VALUES (:id, :email, :hashed_password, :name, :role, true, false, true)
            """,
            {
                'id': user_id,
                'email': user_data['email'],
                'hashed_password': hashed_password,
                'name': user_data['name'],
                'role': user_data['role'],
            },
        )
        context['users'][user_id] = {
            'id': user_id,
            'email': user_data['email'],
            'name': user_data['name'],
            'role': user_data['role'],
        }
    execute_sql_statement(
        'SELECT setval(\'user_id_seq\', (SELECT COALESCE(MAX(id), 0) + 1 FROM "user"), false)', {}
    )


@given('events exist:')
def create_events(
    step: Step,
    context: dict[str, Any],
    execute_sql_statement: Callable[..., list[dict[str, Any]] | None],
) -> None:
    """Create events for booking_list test."""
    rows = step.data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    context['events'] = {}
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        event_data = dict(zip(headers, values, strict=True))
        event_id = int(event_data['id'])
        seller_id = int(event_data['seller_id'])
        execute_sql_statement(
            """
            INSERT INTO event (id, seller_id, name, description, is_active, status, venue_name, seating_config)
            VALUES (:id, :seller_id, :name, :description, :is_active, :status, :venue_name, :seating_config)
            """,
            {
                'id': event_id,
                'seller_id': seller_id,
                'name': event_data['name'],
                'description': f'Description for {event_data["name"]}',
                'is_active': True,
                'status': event_data['status'],
                'venue_name': event_data.get('venue_name', DEFAULT_VENUE_NAME),
                'seating_config': event_data.get('seating_config', DEFAULT_SEATING_CONFIG_JSON),
            },
        )
        context['events'][event_id] = {
            'id': event_id,
            'seller_id': seller_id,
            'name': event_data['name'],
            'status': event_data['status'],
        }
    execute_sql_statement(
        "SELECT setval('event_id_seq', (SELECT COALESCE(MAX(id), 0) + 1 FROM event), false)", {}
    )


def _create_tickets_for_booking(
    *,
    booking_id: str,
    event_id: int,
    section: str,
    subsection: int,
    quantity: int,
    total_price: int,
    buyer_id: int,
    status: str,
    explicit_seat_positions: list[str] | None,
    execute_sql_statement: Callable[..., list[dict[str, Any]] | None],
) -> list[str]:
    """Create tickets for a booking based on quantity or explicit seat positions."""
    if quantity <= 0:
        return []

    price_per_ticket = total_price // quantity
    ticket_status = 'sold' if status == 'paid' else 'reserved'

    # Use explicit seat_positions if provided, otherwise generate unique ones
    if explicit_seat_positions:
        seat_positions = explicit_seat_positions
    else:
        # Query max seat number for this event/section/subsection
        max_seat_result = execute_sql_statement(
            """
            SELECT COALESCE(MAX(seat_number), 0) as max_seat
            FROM ticket
            WHERE event_id = :event_id AND section = :section AND subsection = :subsection
            """,
            {'event_id': event_id, 'section': section, 'subsection': subsection},
            fetch=True,
        )
        start_seat = (max_seat_result[0]['max_seat'] if max_seat_result else 0) + 1
        seat_positions = [f'1-{start_seat + idx}' for idx in range(quantity)]

    for seat_pos in seat_positions:
        row_num, seat_num = seat_pos.split('-')
        execute_sql_statement(
            """
            INSERT INTO ticket (event_id, section, subsection, row_number, seat_number, price, status, buyer_id, created_at, updated_at)
            VALUES (:event_id, :section, :subsection, :row_number, :seat_number, :price, :status, :buyer_id, NOW(), NOW())
            """,
            {
                'event_id': event_id,
                'section': section,
                'subsection': subsection,
                'row_number': int(row_num),
                'seat_number': int(seat_num),
                'price': price_per_ticket,
                'status': ticket_status,
                'buyer_id': buyer_id,
            },
        )

    execute_sql_statement(
        'UPDATE booking SET seat_positions = :seat_positions WHERE id = :booking_id',
        {'booking_id': booking_id, 'seat_positions': seat_positions},
    )

    return seat_positions


@given('bookings exist:')
def create_bookings(
    step: Step,
    context: dict[str, Any],
    execute_sql_statement: Callable[..., list[dict[str, Any]] | None],
) -> None:
    """Create bookings for booking_list test."""
    rows = step.data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    context['bookings'] = {}

    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        booking_data = dict(zip(headers, values, strict=True))
        event_key = int(booking_data['event_id'])
        event_id = context.get('events', {}).get(event_key, {}).get('id', event_key)

        booking_id_input = booking_data['id']
        try:
            int(booking_id_input)
            booking_id = str(uuid.uuid7())
        except ValueError:
            booking_id = booking_id_input

        if 'section' in booking_data:
            section = booking_data['section']
            subsection = int(booking_data['subsection'])
            quantity = int(booking_data['quantity'])
            seat_selection_mode = booking_data.get('seat_selection_mode', 'best_available')
            seat_positions = (
                orjson.loads(booking_data['seat_positions'])
                if 'seat_positions' in booking_data
                else []
            )
        else:
            section_map = {1: ('A', 1), 2: ('B', 1), 3: ('C', 1), 4: ('D', 1)}
            section, subsection = section_map.get(event_id, ('A', 1))
            quantity = 1
            seat_selection_mode = 'best_available'
            seat_positions = []

        paid_at_sql = (
            ', NOW()'
            if booking_data.get('paid_at') == 'not_null' and booking_data['status'] == 'paid'
            else ''
        )
        paid_at_col = (
            ', paid_at'
            if booking_data.get('paid_at') == 'not_null' and booking_data['status'] == 'paid'
            else ''
        )

        buyer_id = int(booking_data['buyer_id'])
        status = booking_data['status']

        execute_sql_statement(
            f"""
            INSERT INTO "booking" (id, buyer_id, event_id, section, subsection, quantity, total_price, status, seat_selection_mode, seat_positions, created_at, updated_at{paid_at_col})
            VALUES (:id, :buyer_id, :event_id, :section, :subsection, :quantity, :total_price, :status, :seat_selection_mode, :seat_positions, NOW(), NOW(){paid_at_sql})
            """,
            {
                'id': booking_id,
                'buyer_id': buyer_id,
                'event_id': event_id,
                'section': section,
                'subsection': subsection,
                'quantity': quantity,
                'total_price': int(booking_data['total_price']),
                'status': status,
                'seat_selection_mode': seat_selection_mode,
                'seat_positions': seat_positions,
            },
        )

        # Create tickets automatically when status is 'paid' (paid bookings have tickets)
        if status == 'paid':
            # Use explicit seat_positions from data if provided (e.g., for manual selection tests)
            explicit_positions = seat_positions if seat_positions else None
            _create_tickets_for_booking(
                booking_id=booking_id,
                event_id=event_id,
                section=section,
                subsection=subsection,
                quantity=quantity,
                total_price=int(booking_data['total_price']),
                buyer_id=buyer_id,
                status=status,
                explicit_seat_positions=explicit_positions,
                execute_sql_statement=execute_sql_statement,
            )

        context['bookings'][int(booking_data['id'])] = {'id': booking_id}


# =============================================================================
# When Steps (Booking-specific - for multi-user booking_list tests)
# =============================================================================


@when(parsers.parse('{role} with id {user_id:d} requests their bookings'))
def user_requests_bookings(
    role: str,
    user_id: int,
    client: TestClient,
    context: dict[str, Any],  # noqa: ARG001
) -> None:
    login_user(client, get_user_email_by_id(user_id), DEFAULT_PASSWORD)
    response = client.get(f'{BOOKING_MY_BOOKINGS}?booking_status=')
    _store_response(context, response)


@when(parsers.parse('{role} with id {user_id:d} requests their bookings with status "{status}"'))
def user_requests_bookings_with_status(
    role: str,
    user_id: int,
    status: str,
    client: TestClient,
    context: dict[str, Any],  # noqa: ARG001
) -> None:
    login_user(client, get_user_email_by_id(user_id), DEFAULT_PASSWORD)
    response = client.get(f'{BOOKING_MY_BOOKINGS}?booking_status={status}')
    _store_response(context, response)


@when('buyer with id {buyer_id:d} requests booking details for booking {booking_id:d}')
def buyer_requests_booking_details(
    buyer_id: int, booking_id: int, client: TestClient, context: dict[str, Any]
) -> None:
    actual_booking_id = context.get('bookings', {}).get(booking_id, {}).get('id', str(booking_id))
    login_user(client, get_user_email_by_id(buyer_id), DEFAULT_PASSWORD)
    response = client.get(BOOKING_GET.format(booking_id=actual_booking_id))
    _store_response(context, response)
    context['booking_id'] = booking_id
    context['actual_booking_id'] = actual_booking_id


# =============================================================================
# Then Steps (Booking-specific verification)
# =============================================================================


@then('the booking status should remain:')
def verify_booking_status_remains(step: Step, client: TestClient, context: dict[str, Any]) -> None:
    rows = step.data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    expected_data = dict(zip(headers, values, strict=True))
    booking_data = get_booking_details(client, context['booking']['id'])
    for field, expected in expected_data.items():
        actual = booking_data.get(field)
        assert actual == expected, f'Booking {field} should remain "{expected}", but got "{actual}"'


@then('the tickets should have status:')
def verify_tickets_have_status(
    step: Step,
    execute_sql_statement: Callable[..., list[dict[str, Any]] | None],
    context: dict[str, Any],
) -> None:
    expected_data = extract_table_data(step)
    expected_status = expected_data['status']
    ticket_ids = context.get('ticket_ids', [])

    if not ticket_ids:
        raise ValueError('No ticket_ids found in state')

    for ticket_id in ticket_ids:
        result = execute_sql_statement(
            'SELECT id, status FROM ticket WHERE id = :ticket_id',
            {'ticket_id': ticket_id},
            fetch=True,
        )
        assert result, f'Ticket {ticket_id} not found in database'
        ticket = result[0]
        assert ticket['status'] == expected_status, (
            f"Expected ticket {ticket_id} status '{expected_status}', got '{ticket['status']}'"
        )


@then('the bookings should include:')
def verify_bookings_include(step: Step, context: dict[str, Any]) -> None:
    expected_bookings = []
    rows = step.data_table.rows
    headers = [cell.value for cell in rows[0].cells]

    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        expected_bookings.append(dict(zip(headers, values, strict=True)))

    response = context['response']
    actual_bookings = response.json()

    assert len(actual_bookings) >= len(expected_bookings)

    for expected in expected_bookings:
        expected_id_key = int(expected['id'])
        actual_booking_id = (
            context.get('bookings', {}).get(expected_id_key, {}).get('id', expected['id'])
        )

        found = False
        for actual in actual_bookings:
            if str(actual.get('id')) == str(actual_booking_id):
                if 'event_name' in expected:
                    assert actual.get('event_name') == expected['event_name']
                if 'total_price' in expected:
                    assert actual.get('total_price') == int(expected['total_price'])
                if 'status' in expected:
                    assert actual.get('status') == expected['status']
                for field in ['created_at', 'paid_at']:
                    if field in expected:
                        assert_nullable_field(actual, field, expected[field])
                found = True
                break
        assert found, f'Expected booking with id {expected["id"]} not found'


@then('all bookings should have status:')
def verify_all_bookings_have_status_single(step: Step, context: dict[str, Any]) -> None:
    expected_status = extract_single_value(step)
    response = context['response']
    bookings = response.json()
    for booking in bookings:
        assert booking.get('status') == expected_status


@then('the booking details should include:')
def verify_booking_details_include(step: Step, context: dict[str, Any]) -> None:
    rows = step.data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    expected_data = dict(zip(headers, values, strict=True))

    response = context['response']
    booking = response.json()

    if 'id' in expected_data:
        expected_id_key = int(expected_data['id'])
        expected_booking_id = (
            context.get('bookings', {}).get(expected_id_key, {}).get('id', str(expected_id_key))
        )
        assert str(booking.get('id')) == str(expected_booking_id)
    if 'event_name' in expected_data:
        assert booking.get('event_name') == expected_data['event_name']
    if 'status' in expected_data:
        assert booking.get('status') == expected_data['status']


@then('the booking with id {booking_id:d} should have seat_positions:')
def verify_booking_seat_positions(step: Step, context: dict[str, Any], booking_id: int) -> None:
    rows = step.data_table.rows
    expected_seats = [row.cells[0].value for row in rows]

    response = context['response']
    bookings = response.json()
    actual_booking_id = context.get('bookings', {}).get(booking_id, {}).get('id', str(booking_id))

    booking = next((b for b in bookings if str(b['id']) == str(actual_booking_id)), None)
    assert booking is not None, f'Booking {booking_id} not found'
    assert 'seat_positions' in booking
    actual_seats = booking['seat_positions']

    for expected_seat in expected_seats:
        assert expected_seat in actual_seats, f'Expected seat {expected_seat} not found'
    assert len(actual_seats) == len(expected_seats)


@then(parsers.parse('the booking should include {count:d} tickets with:'))
def verify_booking_includes_n_tickets(step: Step, context: dict[str, Any], count: int) -> None:
    """Verify the booking response includes N tickets with expected properties."""
    response = context['response']
    booking = response.json()

    assert 'tickets' in booking, 'Booking response should contain tickets field'
    tickets = booking['tickets']

    assert len(tickets) == count, f'Expected {count} tickets, got {len(tickets)}'

    # Parse expected properties from step table (single row describes all tickets)
    rows = step.data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    expected = dict(zip(headers, values, strict=True))

    # Verify all tickets have expected properties
    for ticket in tickets:
        if 'section' in expected:
            assert ticket.get('section') == expected['section'], (
                f'Expected section {expected["section"]}, got {ticket.get("section")}'
            )
        if 'subsection' in expected:
            assert ticket.get('subsection') == int(expected['subsection']), (
                f'Expected subsection {expected["subsection"]}, got {ticket.get("subsection")}'
            )
        if 'price' in expected:
            assert ticket.get('price') == int(expected['price']), (
                f'Expected price {expected["price"]}, got {ticket.get("price")}'
            )
        if 'status' in expected:
            assert ticket.get('status') == expected['status'], (
                f'Expected status {expected["status"]}, got {ticket.get("status")}'
            )

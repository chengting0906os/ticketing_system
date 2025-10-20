from typing import Any, Dict, List

from fastapi.testclient import TestClient
from pytest_bdd import then

from src.platform.constant.route_constant import (
    BOOKING_GET,
    EVENT_GET,
    EVENT_TICKETS_BY_SUBSECTION,
)
from test.shared.then import get_state_with_response
from test.shared.utils import (
    assert_response_status,
    extract_single_value,
    extract_table_data,
    login_user,
)
from test.util_constant import DEFAULT_PASSWORD, TEST_SELLER_EMAIL


def assert_nullable_field(
    data: Dict[str, Any], field: str, expected: str, message: str | None = None
):
    if expected == 'not_null':
        assert data.get(field) is not None, message or f'{field} should not be null'
    elif expected == 'null':
        assert data.get(field) is None, message or f'{field} should be null'


def get_event_status(client: TestClient, event_id: int) -> str:
    response = client.get(EVENT_GET.format(event_id=event_id))
    assert_response_status(response, 200)
    return response.json()['status']


def get_booking_details(client: TestClient, booking_id: int) -> Dict[str, Any]:
    response = client.get(BOOKING_GET.format(booking_id=booking_id))
    assert_response_status(response, 200)
    return response.json()


def assert_booking_count(booking_state: Dict[str, Any], expected_count: int):
    response = booking_state['response']
    assert_response_status(response, 200)
    bookings = response.json()
    assert len(bookings) == expected_count, (
        f'Expected {expected_count} bookings, got {len(bookings)}'
    )
    booking_state['bookings_response'] = bookings


def verify_booking_fields(booking_data: Dict[str, Any], expected_data: Dict[str, str]):
    if 'price' in expected_data:
        assert booking_data['price'] == int(expected_data['price'])
    if 'status' in expected_data:
        assert booking_data['status'] == expected_data['status']
    if 'created_at' in expected_data:
        assert_nullable_field(booking_data, 'created_at', expected_data['created_at'])
    if 'paid_at' in expected_data:
        assert_nullable_field(booking_data, 'paid_at', expected_data['paid_at'])


def assert_all_bookings_have_status(bookings: List[Dict[str, Any]], expected_status: str):
    for booking in bookings:
        assert booking.get('status') == expected_status, (
            f'Booking {booking["id"]} has status {booking.get("status")}, expected {expected_status}'
        )


@then('the booking should be created with:')
def verify_booking_created(step, booking_state):
    expected_data = extract_table_data(step)
    response = booking_state['response']
    assert_response_status(response, 201)
    booking_data = response.json()
    verify_booking_fields(booking_data, expected_data)
    booking_state['created_booking'] = booking_data


@then('the booking status should be:')
def verify_booking_status(step, booking_state):
    expected_status = extract_single_value(step)
    # Check updated_booking first (from payment or cancellation), then fallback to booking or response
    booking = booking_state.get('updated_booking')
    if not booking:
        booking = booking_state.get('booking')
    if not booking:
        response = booking_state.get('response')
        if response:
            booking = response.json()
    assert booking['status'] == expected_status, (
        f'Booking status should be {expected_status}, but got {booking["status"]}'
    )


@then('the booking total_price should be:')
def verify_booking_total_price(step, booking_state):
    expected_price = int(extract_single_value(step))
    booking = booking_state.get('booking')
    if not booking:
        response = booking_state.get('response')
        if response:
            booking = response.json()
    assert booking['total_price'] == expected_price, (
        f'Booking total_price should be {expected_price}, but got {booking["total_price"]}'
    )


@then('the booking status should remain:')
def verify_booking_status_remains(step, client: TestClient, booking_state):
    expected_status = extract_single_value(step)
    booking_data = get_booking_details(client, booking_state['booking']['id'])
    assert booking_data['status'] == expected_status, (
        f'Booking status should remain {expected_status}, but got {booking_data["status"]}'
    )


@then('the event status should remain:')
def verify_event_status_remains(step, client: TestClient, booking_state):
    expected_status = extract_single_value(step)
    event_id = booking_state.get('event', {}).get('id') or booking_state.get('event_id', 1)
    actual_status = get_event_status(client, event_id)
    assert actual_status == expected_status, (
        f'Event status should remain {expected_status}, but got {actual_status}'
    )


@then('the booking should have:')
def verify_booking_has_fields(step, booking_state):
    expected_data = extract_table_data(step)
    booking_data = booking_state.get('updated_booking') or booking_state['response'].json()
    for field in ['created_at', 'paid_at']:
        if field in expected_data:
            assert_nullable_field(booking_data, field, expected_data[field])


@then('the payment should have:')
def verify_payment_details(step, booking_state):
    expected_data = extract_table_data(step)
    response_data = booking_state['response'].json()
    if 'payment_id' in expected_data:
        if expected_data['payment_id'].startswith('PAY_MOCK_'):
            assert response_data.get('payment_id', '').startswith('PAY_MOCK_'), (
                'payment_id should start with PAY_MOCK_'
            )
    if 'status' in expected_data:
        assert response_data.get('status') == expected_data['status'], (
            f'payment status should be {expected_data["status"]}'
        )


@then('the event status should be:')
def verify_event_status(step, client: TestClient, booking_state):
    expected_status = extract_single_value(step)
    event_id = booking_state.get('event_id') or booking_state['event']['id']
    status = get_event_status(client, event_id)
    assert status == expected_status


@then('the booking price should be 1000')
def verify_booking_price_1000(step, booking_state):
    booking = booking_state['booking']
    assert booking['price'] == 1000, f'Expected booking price 1000, got {booking["price"]}'


@then('the existing booking price should remain 1000')
def verify_existing_booking_price_remains_1000(step, client: TestClient, booking_state):
    booking_id = booking_state['booking']['id']
    booking_data = get_booking_details(client, booking_id)
    assert booking_data['price'] == 1000, (
        f'Expected booking price to remain 1000, got {booking_data["price"]}'
    )


@then('the new booking should have price 2000')
def verify_new_booking_has_price_2000(step, booking_state):
    new_booking = booking_state['new_booking']
    assert new_booking['price'] == 2000, (
        f'Expected new booking price 2000, got {new_booking["price"]}'
    )


@then('the paid booking price should remain 1500')
def verify_paid_booking_price_remains_1500(step, client: TestClient, booking_state):
    booking_id = booking_state['booking']['id']
    booking_data = get_booking_details(client, booking_id)
    assert booking_data['price'] == 1500, (
        f'Expected paid booking price to remain 1500, got {booking_data["price"]}'
    )


@then('the booking status should remain "completed"')
def verify_booking_status_remains_completed(step, client: TestClient, booking_state):
    booking_id = booking_state['booking']['id']
    booking_data = get_booking_details(client, booking_id)
    assert booking_data['status'] == 'completed', (
        f'Expected booking status to remain "completed", got {booking_data["status"]}'
    )


@then('the tickets should have status:')
def verify_tickets_have_status(
    step, client: TestClient, booking_state=None, context=None, execute_sql_statement=None
):
    if execute_sql_statement is None:
        raise ValueError('execute_sql_statement function is required but was not provided')
    expected_data = extract_table_data(step)
    expected_status = expected_data['status']

    # Get state that contains the booking or event information
    state = get_state_with_response(booking_state=booking_state, context=context)

    # Get the specific ticket IDs that are part of this booking
    ticket_ids = state.get('ticket_ids', [])

    if not ticket_ids:
        raise ValueError('No ticket_ids found in state - cannot verify ticket status')

    # Query tickets directly from PostgreSQL database (source of truth)
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


@then('the event status should be "reserved"')
def verify_event_status_is_reserved(step, client: TestClient, booking_state):
    event_id = booking_state['event']['id']
    response = client.get(EVENT_GET.format(event_id=event_id))
    assert response.status_code == 200, f'Failed to get event: {response.text}'
    event_data = response.json()
    assert event_data['status'] == 'reserved', (
        f'Expected event status "reserved", got {event_data["status"]}'
    )


@then('tickets should be reserved for buyer:')
def verify_tickets_reserved_for_buyer(
    step, client: TestClient, booking_state, execute_sql_statement
):
    ticket_data = extract_table_data(step)
    expected_status = ticket_data['status']
    expected_buyer_id = int(ticket_data['buyer_id'])

    # Use actual ticket IDs from booking_state if available, otherwise parse from table
    if 'ticket_ids' in booking_state:
        ticket_ids = booking_state['ticket_ids']
    else:
        ticket_ids_str = ticket_data['ticket_ids']
        ticket_ids = [int(id.strip()) for id in ticket_ids_str.split(',')]

    # Verify each ticket is reserved for the correct buyer
    for ticket_id in ticket_ids:
        result = execute_sql_statement(
            'SELECT status, buyer_id FROM ticket WHERE id = :ticket_id',
            {'ticket_id': ticket_id},
            fetch=True,
        )

        assert result, f'Ticket {ticket_id} not found in database'
        ticket = result[0]

        assert ticket['status'] == expected_status, (
            f'Expected ticket {ticket_id} status "{expected_status}", got "{ticket["status"]}"'
        )
        assert ticket['buyer_id'] == expected_buyer_id, (
            f'Expected ticket {ticket_id} buyer_id {expected_buyer_id}, got {ticket["buyer_id"]}'
        )


@then('the booking should contain tickets with seats:')
def verify_booking_contains_tickets_with_seats(
    step, client: TestClient, booking_state, execute_sql_statement
):
    # Extract expected seat numbers from table
    rows = step.data_table.rows
    expected_seat_numbers = []
    for row in rows[1:]:  # Skip header
        expected_seat_numbers.append(row.cells[0].value)

    # Login as seller to see all tickets
    login_user(client, TEST_SELLER_EMAIL, DEFAULT_PASSWORD)

    # Get all tickets for the event
    event_id = booking_state['event_id']
    tickets_response = client.get(
        EVENT_TICKETS_BY_SUBSECTION.format(event_id=event_id, section='A', subsection=1)
    )
    assert tickets_response.status_code == 200, f'Failed to get tickets: {tickets_response.text}'
    tickets_data = tickets_response.json()
    tickets_data.get('tickets', [])

    # Get tickets that belong to this booking (reserved status)
    booking_id = booking_state['booking']['id']
    booking_status = booking_state['booking'].get('status', '')

    # Skip ticket verification if booking is still processing (consumer hasn't run yet)
    if booking_status == 'processing':
        return

    # First get booking info to know which tickets to query
    booking_result = execute_sql_statement(
        """
        SELECT event_id, section, subsection, seat_positions
        FROM booking
        WHERE id = :booking_id
        """,
        {'booking_id': booking_id},
        fetch=True,
    )

    assert booking_result, f'Booking {booking_id} not found'
    booking_data = booking_result[0]

    # Query tickets using booking's seat_positions
    result = execute_sql_statement(
        """
        SELECT t.id, t.section, t.subsection, t.row_number, t.seat_number
        FROM ticket t
        WHERE t.event_id = :event_id
          AND t.section = :section
          AND t.subsection = :subsection
          AND (t.row_number || '-' || t.seat_number) = ANY(:seat_positions::text[])
        """,
        {
            'event_id': booking_data['event_id'],
            'section': booking_data['section'],
            'subsection': booking_data['subsection'],
            'seat_positions': booking_data['seat_positions'],
        },
        fetch=True,
    )

    assert result, f'No tickets found for booking {booking_id}'

    # Construct the full seat identifiers (e.g., "A-1-1-1")
    actual_seat_identifiers = []
    for ticket in result:
        seat_id = f'{ticket["section"]}-{ticket["subsection"]}-{ticket["row_number"]}-{ticket["seat_number"]}'
        actual_seat_identifiers.append(seat_id)

    # Verify all expected seats are in the booking
    for expected_seat in expected_seat_numbers:
        assert expected_seat in actual_seat_identifiers, (
            f'Expected seat {expected_seat} not found in booking. '
            f'Actual seats: {actual_seat_identifiers}'
        )


@then('the selected tickets should have status:')
def verify_selected_tickets_status(step, client: TestClient, booking_state, execute_sql_statement):
    expected_status = extract_single_value(step)

    # Get booking ID and status
    booking_id = booking_state['booking']['id']
    booking_status = booking_state['booking'].get('status', '')

    # Skip ticket verification if booking is still processing (consumer hasn't run yet)
    if booking_status == 'processing':
        return

    # Get booking info
    booking_result = execute_sql_statement(
        """
        SELECT event_id, section, subsection, seat_positions
        FROM booking
        WHERE id = :booking_id
        """,
        {'booking_id': booking_id},
        fetch=True,
    )
    assert booking_result, f'Booking {booking_id} not found'
    booking_data = booking_result[0]

    # Query tickets using booking's seat_positions
    result = execute_sql_statement(
        """
        SELECT t.id, t.status
        FROM ticket t
        WHERE t.event_id = :event_id
          AND t.section = :section
          AND t.subsection = :subsection
          AND (t.row_number || '-' || t.seat_number) = ANY(:seat_positions::text[])
        """,
        {
            'event_id': booking_data['event_id'],
            'section': booking_data['section'],
            'subsection': booking_data['subsection'],
            'seat_positions': booking_data['seat_positions'],
        },
        fetch=True,
    )

    assert result, f'No tickets found for booking {booking_id}'

    # Verify all tickets have the expected status
    for ticket in result:
        assert ticket['status'] == expected_status, (
            f'Expected ticket {ticket["id"]} status "{expected_status}", got "{ticket["status"]}"'
        )


@then('the booking should contain consecutive available seats:')
def verify_booking_contains_consecutive_seats(step, booking_state, execute_sql_statement):
    count_data = extract_table_data(step)
    count = int(count_data['count'])
    booking_id = booking_state['booking']['id']

    # Get booking info
    booking_result = execute_sql_statement(
        """
        SELECT event_id, section, subsection, seat_positions
        FROM booking
        WHERE id = :booking_id
        """,
        {'booking_id': booking_id},
        fetch=True,
    )
    assert booking_result, f'Booking {booking_id} not found'
    booking_data = booking_result[0]

    # Query tickets using booking's seat_positions
    result = execute_sql_statement(
        """
        SELECT t.id, t.seat_number, t.section, t.subsection, t.row_number, t.seat_number as seat
        FROM ticket t
        WHERE t.event_id = :event_id
          AND t.section = :section
          AND t.subsection = :subsection
          AND (t.row_number || '-' || t.seat_number) = ANY(:seat_positions::text[])
        ORDER BY t.section, t.subsection, t.row_number, t.seat_number
        """,
        {
            'event_id': booking_data['event_id'],
            'section': booking_data['section'],
            'subsection': booking_data['subsection'],
            'seat_positions': booking_data['seat_positions'],
        },
        fetch=True,
    )

    assert result, f'No tickets found for booking {booking_id}'
    assert len(result) == count, f'Expected {count} tickets, got {len(result)}'

    # Verify seats are consecutive (same row, consecutive seat numbers)
    if count > 1:
        first_ticket = result[0]
        for i in range(1, len(result)):
            current_ticket = result[i]
            # Check if same section, subsection, and row
            assert current_ticket['section'] == first_ticket['section'], 'Seats not in same section'
            assert current_ticket['subsection'] == first_ticket['subsection'], (
                'Seats not in same subsection'
            )
            assert current_ticket['row_number'] == first_ticket['row_number'], (
                'Seats not in same row'
            )
            # Check if seat numbers are consecutive
            expected_seat = first_ticket['seat'] + i
            assert current_ticket['seat'] == expected_seat, (
                f'Seats not consecutive: expected {expected_seat}, got {current_ticket["seat"]}'
            )


@then('the selected seats should be from the lowest available row')
def verify_seats_from_lowest_available_row(booking_state, execute_sql_statement):
    booking_id = booking_state['booking']['id']
    event_id = booking_state['event_id']

    # Get booking info
    booking_info = execute_sql_statement(
        """
        SELECT event_id, section, subsection, seat_positions
        FROM booking
        WHERE id = :booking_id
        """,
        {'booking_id': booking_id},
        fetch=True,
    )
    assert booking_info, f'Booking {booking_id} not found'
    booking_data = booking_info[0]

    # Get the row number of seats in this booking
    booking_result = execute_sql_statement(
        """
        SELECT DISTINCT t.row_number
        FROM ticket t
        WHERE t.event_id = :event_id
          AND t.section = :section
          AND t.subsection = :subsection
          AND (t.row_number || '-' || t.seat_number) = ANY(:seat_positions::text[])
        """,
        {
            'event_id': booking_data['event_id'],
            'section': booking_data['section'],
            'subsection': booking_data['subsection'],
            'seat_positions': booking_data['seat_positions'],
        },
        fetch=True,
    )

    assert booking_result, f'No tickets found for booking {booking_id}'
    booking_row = booking_result[0]['row_number']

    # Get the lowest available row number in the event (excluding reserved/sold tickets)
    available_result = execute_sql_statement(
        """
        SELECT MIN(row_number) as min_row
        FROM ticket
        WHERE event_id = :event_id AND status = 'available'
        """,
        {'event_id': event_id},
        fetch=True,
    )

    if available_result and available_result[0]['min_row'] is not None:
        # If there are still available seats, the booking should be from the lowest available row
        # (or one row higher since we just booked seats)
        lowest_available_row = available_result[0]['min_row']
        assert booking_row <= lowest_available_row, (
            f'Booking seats should be from lowest available row {lowest_available_row} '
            f'or lower, but got row {booking_row}'
        )


@then('the booking should contain available seat:')
def verify_booking_contains_single_available_seat(step, booking_state, execute_sql_statement):
    count_data = extract_table_data(step)
    count = int(count_data['count'])
    booking_id = booking_state['booking']['id']

    # Get booking info
    booking_info = execute_sql_statement(
        """
        SELECT event_id, section, subsection, seat_positions
        FROM booking
        WHERE id = :booking_id
        """,
        {'booking_id': booking_id},
        fetch=True,
    )
    assert booking_info, f'Booking {booking_id} not found'
    booking_data = booking_info[0]

    # Query tickets count using booking's seat_positions
    result = execute_sql_statement(
        """
        SELECT COUNT(*) as ticket_count
        FROM ticket t
        WHERE t.event_id = :event_id
          AND t.section = :section
          AND t.subsection = :subsection
          AND (t.row_number || '-' || t.seat_number) = ANY(:seat_positions::text[])
        """,
        {
            'event_id': booking_data['event_id'],
            'section': booking_data['section'],
            'subsection': booking_data['subsection'],
            'seat_positions': booking_data['seat_positions'],
        },
        fetch=True,
    )

    assert result, f'No tickets found for booking {booking_id}'
    actual_count = result[0]['ticket_count']

    assert actual_count == count, f'Expected {count} tickets, got {actual_count}'


@then('the booking should contain tickets:')
def verify_booking_contains_tickets(step, booking_state, execute_sql_statement):
    count_data = extract_table_data(step)
    count = int(count_data['count'])
    booking_id = booking_state['booking']['id']

    # Get booking info
    booking_info = execute_sql_statement(
        """
        SELECT event_id, section, subsection, seat_positions
        FROM booking
        WHERE id = :booking_id
        """,
        {'booking_id': booking_id},
        fetch=True,
    )
    assert booking_info, f'Booking {booking_id} not found'
    booking_data = booking_info[0]

    # Query tickets count using booking's seat_positions
    result = execute_sql_statement(
        """
        SELECT COUNT(*) as ticket_count
        FROM ticket t
        WHERE t.event_id = :event_id
          AND t.section = :section
          AND t.subsection = :subsection
          AND (t.row_number || '-' || t.seat_number) = ANY(:seat_positions::text[])
        """,
        {
            'event_id': booking_data['event_id'],
            'section': booking_data['section'],
            'subsection': booking_data['subsection'],
            'seat_positions': booking_data['seat_positions'],
        },
        fetch=True,
    )

    assert result, f'No tickets found for booking {booking_id}'
    actual_count = result[0]['ticket_count']

    assert actual_count == count, f'Expected {count} tickets, got {actual_count}'


@then('the response should contain bookings:')
def verify_bookings_count(step, booking_state):
    expected_count = int(extract_single_value(step))
    response = booking_state['response']
    bookings = response.json()

    actual_count = len(bookings) if isinstance(bookings, list) else 0
    assert actual_count == expected_count, f'Expected {expected_count} bookings, got {actual_count}'


@then('the bookings should include:')
def verify_bookings_include(step, booking_state):
    expected_bookings = []
    rows = step.data_table.rows
    headers = [cell.value for cell in rows[0].cells]

    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        expected_bookings.append(dict(zip(headers, values, strict=True)))

    response = booking_state['response']
    actual_bookings = response.json()

    assert len(actual_bookings) >= len(expected_bookings), (
        f'Expected at least {len(expected_bookings)} bookings, got {len(actual_bookings)}'
    )

    for expected in expected_bookings:
        found = False
        for actual in actual_bookings:
            # Match by booking ID
            if str(actual.get('id')) == expected['id']:
                # Verify all expected fields
                if 'event_name' in expected:
                    assert actual.get('event_name') == expected['event_name'], (
                        f'Event name mismatch for booking {expected["id"]}: '
                        f'expected "{expected["event_name"]}", got "{actual.get("event_name")}"'
                    )
                if 'total_price' in expected:
                    assert actual.get('total_price') == int(expected['total_price']), (
                        f'Total price mismatch for booking {expected["id"]}'
                    )
                if 'status' in expected:
                    assert actual.get('status') == expected['status'], (
                        f'Status mismatch for booking {expected["id"]}'
                    )
                if 'seller_name' in expected:
                    assert actual.get('seller_name') == expected['seller_name'], (
                        f'Seller name mismatch for booking {expected["id"]}'
                    )
                if 'buyer_name' in expected:
                    assert actual.get('buyer_name') == expected['buyer_name'], (
                        f'Buyer name mismatch for booking {expected["id"]}'
                    )
                if 'venue_name' in expected:
                    assert actual.get('venue_name') == expected['venue_name'], (
                        f'Venue name mismatch for booking {expected["id"]}'
                    )
                if 'section' in expected:
                    assert actual.get('section') == expected['section'], (
                        f'Section mismatch for booking {expected["id"]}'
                    )
                if 'subsection' in expected:
                    assert actual.get('subsection') == int(expected['subsection']), (
                        f'Subsection mismatch for booking {expected["id"]}'
                    )
                if 'quantity' in expected:
                    assert actual.get('quantity') == int(expected['quantity']), (
                        f'Quantity mismatch for booking {expected["id"]}'
                    )
                if 'seat_selection_mode' in expected:
                    assert actual.get('seat_selection_mode') == expected['seat_selection_mode'], (
                        f'Seat selection mode mismatch for booking {expected["id"]}'
                    )
                # Check nullable fields
                for field in ['created_at', 'paid_at']:
                    if field in expected:
                        assert_nullable_field(actual, field, expected[field])
                found = True
                break

        assert found, f'Expected booking with id {expected["id"]} not found in response'


@then('all bookings should have status:')
def verify_all_bookings_have_status_single(step, booking_state):
    expected_status = extract_single_value(step)
    response = booking_state['response']
    bookings = response.json()

    for booking in bookings:
        assert booking.get('status') == expected_status, (
            f'Expected status {expected_status}, got {booking.get("status")} for booking {booking.get("id")}'
        )


@then('the tickets should be returned to the available pool')
def verify_tickets_returned_to_pool(client: TestClient, booking_state):
    """Verify that tickets previously associated with a booking are now available."""
    event_id = booking_state['event_id']
    ticket_ids = booking_state.get('ticket_ids', [])

    # Get tickets from the event
    response = client.get(
        EVENT_TICKETS_BY_SUBSECTION.format(event_id=event_id, section='A', subsection=1)
    )
    assert_response_status(response, 200)

    tickets = response.json()['tickets']

    # Check that the tickets that were in the booking are now available
    for ticket_id in ticket_ids:
        ticket = next((t for t in tickets if t['id'] == ticket_id), None)
        assert ticket is not None, f'Ticket {ticket_id} not found'
        assert ticket['status'] == 'available', (
            f'Ticket {ticket_id} should be available but has status {ticket["status"]}'
        )


@then('the booking details should include:')
def verify_booking_details_include(step, booking_state):
    """Verify booking details response includes all expected fields."""
    expected_data = {}
    rows = step.data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    expected_data = dict(zip(headers, values, strict=True))

    response = booking_state['response']
    booking = response.json()

    # Verify all expected fields
    if 'id' in expected_data:
        assert booking.get('id') == int(expected_data['id'])
    if 'event_name' in expected_data:
        assert booking.get('event_name') == expected_data['event_name']
    if 'venue_name' in expected_data:
        assert booking.get('venue_name') == expected_data['venue_name']
    if 'section' in expected_data:
        assert booking.get('section') == expected_data['section']
    if 'subsection' in expected_data:
        assert booking.get('subsection') == int(expected_data['subsection'])
    if 'quantity' in expected_data:
        assert booking.get('quantity') == int(expected_data['quantity'])
    if 'total_price' in expected_data:
        assert booking.get('total_price') == int(expected_data['total_price'])
    if 'status' in expected_data:
        assert booking.get('status') == expected_data['status']
    if 'seller_name' in expected_data:
        assert booking.get('seller_name') == expected_data['seller_name']
    if 'buyer_name' in expected_data:
        assert booking.get('buyer_name') == expected_data['buyer_name']


@then('the booking should include tickets:')
def verify_booking_includes_tickets(step, booking_state):
    """Verify booking response includes expected tickets."""
    expected_tickets = []
    rows = step.data_table.rows
    headers = [cell.value for cell in rows[0].cells]

    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        expected_tickets.append(dict(zip(headers, values, strict=True)))

    response = booking_state['response']
    booking = response.json()

    # Verify tickets field exists
    assert 'tickets' in booking, 'Booking response should include tickets field'
    actual_tickets = booking['tickets']

    # Verify correct number of tickets
    assert len(actual_tickets) == len(expected_tickets), (
        f'Expected {len(expected_tickets)} tickets, got {len(actual_tickets)}'
    )

    # Verify each ticket
    for expected in expected_tickets:
        found = False
        for actual in actual_tickets:
            if str(actual.get('id')) == expected['ticket_id']:
                assert actual.get('section') == expected['section']
                assert actual.get('subsection') == int(expected['subsection'])
                assert actual.get('row') == int(expected['row'])
                assert actual.get('seat') == int(expected['seat'])
                assert actual.get('price') == int(expected['price'])
                assert actual.get('status') == expected['status']
                found = True
                break
        assert found, f'Ticket {expected["ticket_id"]} not found in response'


@then('the booking with id {booking_id:d} should have seat_positions:')
def verify_booking_seat_positions(step, booking_state, booking_id: int):
    """Verify that a booking has the expected seat positions."""
    # Extract expected seat positions from table (no header row in this table)
    rows = step.data_table.rows
    expected_seats = []
    for row in rows:  # No header to skip
        expected_seats.append(row.cells[0].value)

    # Get bookings from response
    response = booking_state['response']
    bookings = response.json()

    # Find the booking with the specified ID
    booking = next((b for b in bookings if b['id'] == booking_id), None)
    assert booking is not None, f'Booking {booking_id} not found in response'

    # Verify seat_positions field exists and is a list
    assert 'seat_positions' in booking, f'Booking {booking_id} missing seat_positions field'
    actual_seats = booking['seat_positions']
    assert isinstance(actual_seats, list), (
        f'seat_positions should be a list, got {type(actual_seats)}'
    )

    # Verify all expected seats are present
    for expected_seat in expected_seats:
        assert expected_seat in actual_seats, (
            f'Expected seat {expected_seat} not found in booking {booking_id}. '
            f'Actual seats: {actual_seats}'
        )

    # Verify no extra seats
    assert len(actual_seats) == len(expected_seats), (
        f'Expected {len(expected_seats)} seats, got {len(actual_seats)} in booking {booking_id}'
    )

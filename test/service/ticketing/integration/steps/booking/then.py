from typing import Any, Dict, List

from fastapi.testclient import TestClient
from pytest_bdd import then
from test.shared.then import get_state_with_response
from test.shared.utils import (
    assert_response_status,
    extract_single_value,
    extract_table_data,
    login_user,
)
from test.util_constant import DEFAULT_PASSWORD, TEST_SELLER_EMAIL

from src.platform.constant.route_constant import (
    BOOKING_GET,
    EVENT_GET,
    EVENT_TICKETS_BY_SUBSECTION,
    USER_LOGIN,
)


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


@then('the booking status should remain "paid"')
def verify_booking_status_remains_paid(step, client: TestClient, booking_state):
    booking_id = booking_state['booking']['id']
    booking_data = get_booking_details(client, booking_id)
    assert booking_data['status'] == 'paid', (
        f'Expected booking status to remain "paid", got {booking_data["status"]}'
    )


@then('the tickets should have status:')
def _(step, client: TestClient, booking_state=None, context=None):
    expected_data = extract_table_data(step)
    expected_status = expected_data['status']

    # Get state that contains the booking or event information
    state = get_state_with_response(booking_state=booking_state, context=context)

    # Try to get event_id from various sources in priority booking
    event_id = None

    # First check if event_id is directly available in state (most common for booking test)
    if 'event_id' in state:
        event_id = state['event_id']

    # Then check the booking object for event_id
    elif 'booking' in state:
        event_id = state['booking'].get('event_id')

    # Then check if there's an event object
    elif 'event' in state:
        event_id = state['event']['id']

    # Finally check the response data
    elif 'response' in state and state['response'].status_code in [200, 201]:
        response_data = state['response'].json()
        if 'event_id' in response_data:
            event_id = response_data['event_id']
        elif 'event' in response_data:
            event_id = response_data['event']['id']

    assert event_id, 'Could not determine event_id for ticket status verification'

    if expected_status == 'sold':
        # Login as seller to see all tickets
        login_response = client.post(
            USER_LOGIN,
            data={'username': TEST_SELLER_EMAIL, 'password': DEFAULT_PASSWORD},
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )

        if login_response.status_code == 200:
            if 'fastapiusersauth' in login_response.cookies:
                client.cookies.set('fastapiusersauth', login_response.cookies['fastapiusersauth'])

    # Get tickets for the event (now with appropriate permissions)
    tickets_response = client.get(
        EVENT_TICKETS_BY_SUBSECTION.format(event_id=event_id, section='A', subsection=1)
    )
    assert tickets_response.status_code == 200, f'Failed to get tickets: {tickets_response.text}'

    tickets_data = tickets_response.json()
    tickets = tickets_data.get('tickets', [])

    # Get the specific ticket IDs that are part of this booking
    ticket_ids = state.get('ticket_ids', [])

    if expected_status == 'sold':
        # For "sold" status, check the specific tickets associated with this booking
        if ticket_ids:
            booking_tickets = [t for t in tickets if t['id'] in ticket_ids]

            if len(booking_tickets) > 0:
                sold_booking_tickets = [t for t in booking_tickets if t['status'] == 'sold']
                assert len(sold_booking_tickets) > 0, (
                    f"Expected booking tickets {ticket_ids} to be marked as 'sold' after payment, "
                    f'but found statuses: {[(t["id"], t["status"]) for t in booking_tickets]}'
                )
            else:
                sold_tickets = [t for t in tickets if t['status'] == 'sold']
                assert len(sold_tickets) > 0, (
                    f"Expected some tickets to be marked as 'sold' after payment, but found none. "
                    f'Found {len(tickets)} tickets with statuses: {set(t["status"] for t in tickets)}'
                )
        else:
            sold_tickets = [t for t in tickets if t['status'] == 'sold']
            assert len(sold_tickets) > 0, (
                f"Expected some tickets to be marked as 'sold' after payment, but found none. "
                f'Found {len(tickets)} tickets with statuses: {set(t["status"] for t in tickets)}'
            )
    elif expected_status == 'available' and ticket_ids:
        # For cancellation scenarios with specific ticket IDs
        booking_tickets = [t for t in tickets if t['id'] in ticket_ids]
        if booking_tickets:
            for ticket in booking_tickets:
                assert ticket['status'] == expected_status, (
                    f"Expected ticket status '{expected_status}', got '{ticket['status']}' for ticket {ticket['id']}"
                )
        else:
            # If specific ticket IDs not found, check if any tickets became available
            available_tickets = [t for t in tickets if t['status'] == 'available']
            assert len(available_tickets) > 0, (
                "Expected some tickets to be 'available' but found none"
            )
    else:
        # Default behavior: verify all tickets have expected status
        assert len(tickets) > 0, 'No tickets found for verification'
        matching_tickets = [t for t in tickets if t['status'] == expected_status]
        total_tickets = len(tickets)

        if len(matching_tickets) == 0:
            statuses = set(t['status'] for t in tickets)
            raise AssertionError(
                f"Expected tickets with status '{expected_status}' but found none. "
                f'Found {total_tickets} tickets with statuses: {statuses}'
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

    # Query database to get tickets associated with this booking using the new ticket_ids array
    result = execute_sql_statement(
        """
        SELECT t.id, t.section, t.subsection, t.row_number, t.seat_number
        FROM ticket t
        JOIN booking_ticket bt ON t.id = bt.ticket_id
        WHERE bt.booking_id = :booking_id
        """,
        {'booking_id': booking_id},
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

    # Query database to get tickets associated with this booking using the new ticket_ids array
    result = execute_sql_statement(
        """
        SELECT t.id, t.status
        FROM ticket t
        JOIN booking_ticket bt ON t.id = bt.ticket_id
        WHERE bt.booking_id = :booking_id
        """,
        {'booking_id': booking_id},
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

    # Query database to get tickets associated with this booking with their seat info using the new ticket_ids array
    result = execute_sql_statement(
        """
        SELECT t.id, t.seat_number, t.section, t.subsection, t.row_number, t.seat_number as seat
        FROM ticket t
        JOIN booking_ticket bt ON t.id = bt.ticket_id
        WHERE bt.booking_id = :booking_id
        ORDER BY t.section, t.subsection, t.row_number, t.seat_number
        """,
        {'booking_id': booking_id},
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

    # Get the row number of seats in this booking using the new ticket_ids array
    booking_result = execute_sql_statement(
        """
        SELECT DISTINCT t.row_number
        FROM ticket t
        JOIN booking_ticket bt ON t.id = bt.ticket_id
        WHERE bt.booking_id = :booking_id
        """,
        {'booking_id': booking_id},
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

    # Query database to get tickets associated with this booking
    result = execute_sql_statement(
        """
        SELECT COUNT(*) as ticket_count
        FROM ticket t
        JOIN booking_ticket bt ON t.id = bt.ticket_id
        WHERE bt.booking_id = :booking_id
        """,
        {'booking_id': booking_id},
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

    # Query database to get tickets associated with this booking
    result = execute_sql_statement(
        """
        SELECT COUNT(*) as ticket_count
        FROM ticket t
        JOIN booking_ticket bt ON t.id = bt.ticket_id
        WHERE bt.booking_id = :booking_id
        """,
        {'booking_id': booking_id},
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

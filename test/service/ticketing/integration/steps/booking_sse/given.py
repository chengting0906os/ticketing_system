"""Given steps for booking SSE feature tests"""

from datetime import datetime, timezone
from uuid import UUID

from pytest_bdd import given, parsers

from src.platform.constant.route_constant import BOOKING_BASE
from test.shared.utils import extract_table_data, login_user
from test.util_constant import DEFAULT_PASSWORD


@given('buyer1@test.com is logged in')
def buyer1_is_logged_in(client):
    """Log in buyer1@test.com"""
    login_user(client, 'buyer1@test.com', DEFAULT_PASSWORD)


@given('a booking exists with status "PROCESSING":')
def booking_exists_with_processing_status(step, client, booking_state, execute_cql_statement):
    data = extract_table_data(step)

    # Parse UUIDs
    booking_id = UUID(data['booking_id'])
    buyer_id = UUID(data['buyer_id'])
    event_id = UUID(data['event_id'])

    # The buyer created in Background might have a different UUID
    if booking_state and 'buyer' in booking_state:
        actual_buyer_id = booking_state['buyer'].get('id')
        if actual_buyer_id:
            buyer_id = (
                UUID(actual_buyer_id) if isinstance(actual_buyer_id, str) else actual_buyer_id
            )

    # Insert booking directly into database
    execute_cql_statement(
        """
        INSERT INTO "booking" (
            id, buyer_id, event_id, status, section, subsection,
            quantity, seat_selection_mode, total_price, created_at
        ) VALUES (
            :id, :buyer_id, :event_id, 'processing', 'A', 1,
            2, 'manual', 2000, :created_at
        )
        """,
        {
            'id': booking_id,
            'buyer_id': buyer_id,
            'event_id': event_id,
            'created_at': datetime.now(timezone.utc),
        },
    )

    # Store in booking_state for later use
    booking_state['booking'] = {
        'id': str(booking_id),
        'buyer_id': str(buyer_id),
        'event_id': str(event_id),
        'status': 'processing',
    }
    booking_state['buyer_id'] = buyer_id


@given('the booking has reserved seats:')
def booking_has_reserved_seats(step, booking_state):
    data = extract_table_data(step)
    seat_positions = data['seat_positions'].split(',')

    booking_state['booking']['seat_positions'] = seat_positions


@given(parsers.parse('a booking exists for {buyer_email}:'))
def booking_exists_for_buyer(buyer_email: str, step, client, booking_state, execute_cql_statement):
    """Create a booking for a specific buyer (for authorization tests)"""
    from datetime import datetime, timezone

    data = extract_table_data(step)

    # Parse UUIDs
    booking_id = UUID(data['booking_id'])
    buyer_id = UUID(data['buyer_id'])
    event_id = UUID(data['event_id'])

    # Get buyer and seller info from booking_state (created in Background)
    buyer = booking_state.get('another_buyer', {})
    seller = booking_state.get('seller', {})
    event = booking_state.get('event', {})

    # Insert booking directly into database
    execute_cql_statement(
        """
        INSERT INTO "booking" (
            id, buyer_id, event_id, status, section, subsection,
            quantity, seat_selection_mode, total_price, created_at,
            buyer_name, buyer_email, event_name, venue_name, seller_id, seller_name
        ) VALUES (
            :id, :buyer_id, :event_id, 'pending_payment', 'A', 1,
            2, 'manual', 2000, :created_at,
            :buyer_name, :buyer_email, :event_name, :venue_name, :seller_id, :seller_name
        )
        """,
        {
            'id': booking_id,
            'buyer_id': buyer_id,
            'event_id': event_id,
            'created_at': datetime.now(timezone.utc),
            'buyer_name': buyer.get('name', 'Test Buyer2'),
            'buyer_email': buyer_email,
            'event_name': event.get('name', 'Test Event'),
            'venue_name': 'Taipei Arena',
            'seller_id': UUID(seller.get('id', '019a1af7-0000-7002-0000-000000000020')),
            'seller_name': seller.get('name', 'Test Seller'),
        },
    )

    # Store booking info for test assertions
    booking_state['other_buyer_booking'] = {
        'id': str(booking_id),
        'buyer_id': str(buyer_id),
        'event_id': str(event_id),
        'owner_email': buyer_email,
    }


@given('buyer creates a booking for event {event_id}:')
def buyer_creates_booking_for_event(event_id: str, step, client, booking_state):
    data = extract_table_data(step)

    # Extract seat_positions if provided in the table
    seat_positions = None
    if 'seat_positions' in data:
        seat_positions = data['seat_positions'].split(',')

    booking_request = {
        'event_id': event_id,
        'section': data['section'],
        'subsection': int(data['subsection']),
        'quantity': int(data['quantity']),
        'seat_selection_mode': data['selection_mode'],
    }

    if seat_positions:
        booking_request['seat_positions'] = seat_positions

    response = client.post(BOOKING_BASE, json=booking_request)

    assert response.status_code == 201, f'Failed to create booking: {response.text}'

    booking_data = response.json()
    booking_state['booking'] = booking_data
    booking_state['response'] = response

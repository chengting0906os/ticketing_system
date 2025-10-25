import time
from uuid import UUID

from fastapi.testclient import TestClient
from pytest_bdd import when, parsers
from test.shared.utils import create_user, extract_table_data, login_user
from test.util_constant import (
    ANOTHER_BUYER_EMAIL,
    ANOTHER_BUYER_NAME,
    DEFAULT_PASSWORD,
    TEST_CARD_NUMBER,
)

from src.platform.constant.route_constant import (
    BOOKING_BASE,
    BOOKING_CANCEL,
    BOOKING_GET,
    BOOKING_MY_BOOKINGS,
    BOOKING_PAY,
)


@when('the buyer pays for the booking with:')
def buyer_pays_for_booking(step, client: TestClient, booking_state):
    payment_data = extract_table_data(step)
    booking_id = booking_state['booking']['id']
    response = client.post(
        BOOKING_PAY.format(booking_id=booking_id),
        json={'card_number': payment_data['card_number']},
    )
    booking_state['response'] = response

    # If payment was successful, fetch the updated booking details
    if response.status_code == 200:
        booking_response = client.get(BOOKING_GET.format(booking_id=booking_id))
        assert booking_response.status_code == 200, (
            f'Failed to get booking after payment: {booking_response.text}'
        )
        booking_state['updated_booking'] = booking_response.json()


@when('the buyer tries to pay for the booking again')
def buyer_tries_to_pay_again(step, client: TestClient, booking_state):
    response = client.post(
        BOOKING_PAY.format(booking_id=booking_state['booking']['id']),
        json={'card_number': TEST_CARD_NUMBER},
    )
    booking_state['response'] = response


@when('the buyer tries to pay for the booking')
def buyer_tries_to_pay(step, client: TestClient, booking_state):
    response = client.post(
        BOOKING_PAY.format(booking_id=booking_state['booking']['id']),
        json={'card_number': TEST_CARD_NUMBER},
    )
    booking_state['response'] = response


@when('another user tries to pay for the booking')
def another_user_tries_to_pay(step, client: TestClient, booking_state):
    create_user(client, ANOTHER_BUYER_EMAIL, DEFAULT_PASSWORD, ANOTHER_BUYER_NAME, 'buyer')
    login_user(client, ANOTHER_BUYER_EMAIL, DEFAULT_PASSWORD)
    response = client.post(
        BOOKING_PAY.format(booking_id=booking_state['booking']['id']),
        json={'card_number': TEST_CARD_NUMBER},
    )
    booking_state['response'] = response


@when('the buyer cancels the booking')
def buyer_cancels_booking(step, client: TestClient, booking_state):
    booking_id = booking_state['booking']['id']
    response = client.patch(BOOKING_CANCEL.format(booking_id=booking_id))
    booking_state['response'] = response
    if response.status_code == 200:
        # Fetch the updated booking details after cancellation
        booking_response = client.get(BOOKING_GET.format(booking_id=booking_id))
        assert booking_response.status_code == 200
        updated_booking = booking_response.json()
        booking_state['booking']['status'] = 'cancelled'
        booking_state['updated_booking'] = updated_booking


@when('the buyer tries to cancel the booking')
def buyer_tries_to_cancel(step, client: TestClient, booking_state):
    response = client.patch(BOOKING_CANCEL.format(booking_id=booking_state['booking']['id']))
    booking_state['response'] = response


@when("the user tries to cancel someone else's booking")
def user_tries_cancel_others_booking(step, client: TestClient, booking_state):
    response = client.patch(BOOKING_CANCEL.format(booking_id=booking_state['booking']['id']))
    booking_state['response'] = response


@when("the seller tries to cancel the buyer's booking")
def seller_tries_cancel_buyer_booking(step, client: TestClient, booking_state):
    response = client.patch(BOOKING_CANCEL.format(booking_id=booking_state['booking']['id']))
    booking_state['response'] = response


@when('the buyer tries to cancel a non-existent booking')
def buyer_tries_cancel_nonexistent(step, client: TestClient, booking_state):
    # Use a valid UUID format that doesn't exist in database
    # Using UUID with recognizable pattern: 00000000-0000-0000-0000-000000999999
    nonexistent_uuid = '00000000-0000-0000-0000-000000999999'
    response = client.patch(BOOKING_CANCEL.format(booking_id=nonexistent_uuid))
    booking_state['response'] = response


def get_user_email_by_id(user_id) -> str:
    """Map user ID to email address based on test setup. Supports both int and UUID."""
    # Support both integer IDs (legacy) and UUIDs
    user_email_map = {
        # Integer IDs (legacy)
        4: 'seller1@test.com',
        5: 'seller2@test.com',
        6: 'buyer1@test.com',
        7: 'buyer2@test.com',
        8: 'buyer3@test.com',
        # UUID IDs (new)
        '019a1af7-0000-7002-0000-000000000001': 'seller1@test.com',
        '019a1af7-0000-7002-0000-000000000002': 'seller2@test.com',
        '019a1af7-0000-7001-0000-000000000001': 'buyer1@test.com',
        '019a1af7-0000-7001-0000-000000000002': 'buyer2@test.com',
        '019a1af7-0000-7001-0000-000000000003': 'buyer3@test.com',
    }

    # Convert UUID to string for lookup
    lookup_key = str(user_id) if isinstance(user_id, UUID) else user_id
    return user_email_map.get(lookup_key, f'user{user_id}@test.com')


@when(parsers.parse('buyer with id {buyer_id} requests their bookings:'))
def buyer_requests_bookings_with_table(buyer_id, step, client: TestClient, booking_state):
    login_user(client, get_user_email_by_id(buyer_id), DEFAULT_PASSWORD)
    booking_status = extract_table_data(step).get('booking_status', '')
    response = client.get(f'{BOOKING_MY_BOOKINGS}?booking_status={booking_status}')
    booking_state['response'] = response


@when(parsers.parse('buyer with id {buyer_id} requests their bookings'))
def buyer_requests_bookings_no_table(buyer_id, client: TestClient, booking_state):
    login_user(client, get_user_email_by_id(buyer_id), DEFAULT_PASSWORD)
    response = client.get(f'{BOOKING_MY_BOOKINGS}?booking_status=')
    booking_state['response'] = response


@when(parsers.parse('seller with id {seller_id} requests their bookings'))
def seller_requests_bookings(seller_id, client: TestClient, booking_state):
    login_user(client, get_user_email_by_id(seller_id), DEFAULT_PASSWORD)
    response = client.get(f'{BOOKING_MY_BOOKINGS}?booking_status=')
    booking_state['response'] = response


@when(parsers.parse('buyer with id {buyer_id} requests their bookings with status "{status}"'))
def buyer_requests_bookings_with_status(buyer_id, status, client: TestClient, booking_state):
    login_user(client, get_user_email_by_id(buyer_id), DEFAULT_PASSWORD)
    response = client.get(f'{BOOKING_MY_BOOKINGS}?booking_status={status}')
    booking_state['response'] = response


@when(parsers.parse('buyer with id {buyer_id} requests booking details for booking {booking_id}'))
def buyer_requests_booking_details(buyer_id, booking_id, client: TestClient, booking_state):
    from src.platform.constant.route_constant import BOOKING_GET

    login_user(client, get_user_email_by_id(buyer_id), DEFAULT_PASSWORD)
    response = client.get(BOOKING_GET.format(booking_id=booking_id))
    booking_state['response'] = response
    booking_state['booking_id'] = booking_id


@when('buyer creates booking with manual seat selection:')
def buyer_creates_booking_with_manual_seat_selection(step, client: TestClient, booking_state):
    """Buyer creates booking with manual seat selection."""
    seat_data = extract_table_data(step)
    selected_seat_locations = seat_data['seat_positions'].split(',')

    # Convert seat location strings to the new dict format
    seat_positions = []

    for seat_location in selected_seat_locations:
        seat_location = seat_location.strip()
        # Parse seat location: section-subsection-row-seat
        parts = seat_location.split('-')
        if len(parts) == 4:
            section, subsection, row, seat = parts
            # Directly convert to row-seat format
            seat_positions.append(f'{row}-{seat}')

    # Create booking with manual seat selection
    if seat_positions:
        first_seat = selected_seat_locations[0].strip()
        parts = first_seat.split('-')
        section = parts[0]
        subsection = int(parts[1])
    else:
        section = 'A'
        subsection = 1

    booking_request = {
        'event_id': booking_state['event_id'],
        'section': section,
        'subsection': subsection,
        'seat_selection_mode': 'manual',
        'seat_positions': seat_positions,
        'quantity': len(seat_positions),
    }

    response = client.post(BOOKING_BASE, json=booking_request)
    booking_state['response'] = response

    # Store booking if created successfully
    if response.status_code == 201:
        booking_state['booking'] = response.json()
        booking_state['seat_positions'] = seat_positions


@when('buyer creates booking with best available seat selection:')
def buyer_creates_booking_with_best_available_seat_selection(
    step, client: TestClient, booking_state
):
    """Buyer creates booking with best available seat selection."""
    seat_data = extract_table_data(step)
    quantity = int(seat_data['quantity'])

    # Create booking with best available seat selection
    booking_request = {
        'event_id': booking_state['event_id'],
        'section': 'A',
        'subsection': 1,
        'seat_selection_mode': 'best_available',
        'seat_positions': [],
        'quantity': quantity,
    }

    response = client.post(BOOKING_BASE, json=booking_request)
    booking_state['response'] = response

    # Store booking if created successfully
    if response.status_code == 201:
        booking_state['booking'] = response.json()
        booking_state['selected_quantity'] = quantity


@when('wait for async processing:')
def wait_for_async_processing(step):
    """Wait for async processing to complete"""
    wait_data = extract_table_data(step)
    seconds = int(wait_data.get('seconds', 1))
    time.sleep(seconds)


@when('buyer creates booking with best available in section:')
def buyer_creates_booking_with_best_available_in_section(step, client: TestClient, booking_state):
    """Buyer creates booking with best available seat selection in specified section."""
    seat_data = extract_table_data(step)
    quantity = int(seat_data['quantity'])
    section = seat_data.get('section', 'A')
    subsection = int(seat_data.get('subsection', 1))

    # Create booking with best available seat selection
    booking_request = {
        'event_id': booking_state['event_id'],
        'section': section,
        'subsection': subsection,
        'seat_selection_mode': 'best_available',
        'seat_positions': [],
        'quantity': quantity,
    }

    response = client.post(BOOKING_BASE, json=booking_request)
    booking_state['response'] = response

    # Store booking if created successfully
    if response.status_code == 201:
        booking_state['booking'] = response.json()
        booking_state['selected_quantity'] = quantity

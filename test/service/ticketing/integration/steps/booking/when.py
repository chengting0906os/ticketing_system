import time

from fastapi.testclient import TestClient
from pytest_bdd import when
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
        assert booking_response.status_code == 200
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
    # Use a booking ID that doesn't exist (999999)
    response = client.patch(BOOKING_CANCEL.format(booking_id=999999))
    booking_state['response'] = response


def get_user_email_by_id(user_id: int) -> str:
    """Map user ID to email address based on test setup."""
    user_email_map = {
        4: 'seller1@test.com',
        5: 'seller2@test.com',
        6: 'buyer1@test.com',
        7: 'buyer2@test.com',
        8: 'buyer3@test.com',
    }
    return user_email_map.get(user_id, f'user{user_id}@test.com')


@when('buyer with id 6 requests their bookings:')
def buyer_6_requests_bookings(step, client: TestClient, booking_state):
    login_user(client, get_user_email_by_id(6), DEFAULT_PASSWORD)
    booking_status = extract_table_data(step).get('booking_status', '')
    response = client.get(f'{BOOKING_MY_BOOKINGS}?booking_status={booking_status}')
    booking_state['response'] = response


@when('buyer with id 8 requests their bookings')
def buyer_8_requests_bookings(step, client: TestClient, booking_state):
    login_user(client, get_user_email_by_id(8), DEFAULT_PASSWORD)
    response = client.get(f'{BOOKING_MY_BOOKINGS}?booking_status=')
    booking_state['response'] = response


@when('seller with id 4 requests their bookings')
def seller_4_requests_bookings(step, client: TestClient, booking_state):
    login_user(client, get_user_email_by_id(4), DEFAULT_PASSWORD)
    response = client.get(f'{BOOKING_MY_BOOKINGS}?booking_status=')
    booking_state['response'] = response


@when('buyer with id 6 requests their bookings with status "paid"')
def buyer_6_requests_bookings_paid(step, client: TestClient, booking_state):
    login_user(client, get_user_email_by_id(6), DEFAULT_PASSWORD)
    response = client.get(f'{BOOKING_MY_BOOKINGS}?booking_status=paid')
    booking_state['response'] = response


@when('buyer with id 6 requests their bookings with status "pending_payment"')
def buyer_6_requests_bookings_pending(step, client: TestClient, booking_state):
    login_user(client, get_user_email_by_id(6), DEFAULT_PASSWORD)
    response = client.get(f'{BOOKING_MY_BOOKINGS}?booking_status=pending_payment')
    booking_state['response'] = response


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

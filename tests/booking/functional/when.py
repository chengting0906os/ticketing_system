from fastapi.testclient import TestClient
from pytest_bdd import when

from src.shared.constant.route_constant import (
    BOOKING_BASE,
    BOOKING_CANCEL,
    BOOKING_GET,
    BOOKING_MY_BOOKINGS,
    BOOKING_PAY,
    EVENT_TICKETS_BY_SUBSECTION,
)
from tests.shared.utils import create_user, extract_table_data, login_user
from tests.util_constant import (
    ANOTHER_BUYER_EMAIL,
    ANOTHER_BUYER_NAME,
    BUYER2_EMAIL,
    DEFAULT_PASSWORD,
    TEST_CARD_NUMBER,
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
        booking_state['updated_booking'] = booking_response.json()  # Store full booking details


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
        booking_state['updated_booking'] = updated_booking  # Store full booking details


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
    # Try to cancel an booking that doesn't exist (using ID 999999)
    response = client.patch(BOOKING_CANCEL.format(booking_id=999999))
    booking_state['response'] = response


def get_user_email_by_id(user_id: int) -> str:
    """Map user ID to email based on booking list test setup."""
    user_mapping = {
        4: 'seller1@test.com',  # Test Seller1
        5: 'seller2@test.com',  # Test Seller2
        6: 'buyer1@test.com',  # Test Buyer1
        7: 'buyer2@test.com',  # Test Buyer2
        8: 'buyer3@test.com',  # Test Buyer3
    }
    return user_mapping.get(user_id, f'user{user_id}@test.com')


@when('buyer with id 6 requests their bookings:')
def buyer_6_requests_bookings(step, client: TestClient, booking_state):
    user_data = extract_table_data(step)
    login_user(client, user_data['email'], user_data['password'])
    response = client.get(f'{BOOKING_MY_BOOKINGS}?booking_status=')
    booking_state['response'] = response


@when('buyer with id 8 requests their bookings')
def buyer_8_requests_bookings(step, client: TestClient, booking_state):
    user_email = get_user_email_by_id(8)
    login_user(client, user_email, 'P@ssw0rd')
    response = client.get(f'{BOOKING_MY_BOOKINGS}?booking_status=')
    booking_state['response'] = response


@when('seller with id 4 requests their bookings')
def seller_4_requests_bookings(step, client: TestClient, booking_state):
    user_email = get_user_email_by_id(4)
    login_user(client, user_email, 'P@ssw0rd')
    response = client.get(f'{BOOKING_MY_BOOKINGS}?booking_status=')
    booking_state['response'] = response


@when('buyer with id 6 requests their bookings with status "paid"')
def buyer_6_requests_bookings_paid(step, client: TestClient, booking_state):
    user_email = get_user_email_by_id(6)
    login_user(client, user_email, 'P@ssw0rd')
    response = client.get(f'{BOOKING_MY_BOOKINGS}?booking_status=paid')
    booking_state['response'] = response


@when('buyer with id 6 requests their bookings with status "pending_payment"')
def buyer_6_requests_bookings_pending(step, client: TestClient, booking_state):
    user_email = get_user_email_by_id(6)
    login_user(client, user_email, 'P@ssw0rd')
    response = client.get(f'{BOOKING_MY_BOOKINGS}?booking_status=pending_payment')
    booking_state['response'] = response


# Keep old step definitions for backward compatibility
@when('buyer with id 4 requests their bookings')
def buyer_4_requests_bookings(step, client: TestClient, booking_state):
    login_user(client, BUYER2_EMAIL, DEFAULT_PASSWORD)
    response = client.get(f'{BOOKING_MY_BOOKINGS}?booking_status=')
    booking_state['response'] = response


@when('the buyer pays for the booking')
def buyer_pays_for_booking_simple(step, client: TestClient, booking_state):
    """Buyer pays for their booking."""
    # Login as buyer
    buyer = booking_state['buyer']
    login_user(client, buyer['email'], 'P@ssw0rd')

    # Pay for the booking
    booking_id = booking_state['booking']['id']
    response = client.post(
        BOOKING_PAY.format(booking_id=booking_id),
        json={'card_number': TEST_CARD_NUMBER},
    )
    assert response.status_code == 200, f'Failed to pay for booking: {response.text}'
    booking_state['payment_response'] = response
    booking_state['response'] = response  # Set response for Then steps

    # Fetch the updated booking details after payment
    booking_response = client.get(BOOKING_GET.format(booking_id=booking_id))
    assert booking_response.status_code == 200
    booking_state['updated_booking'] = booking_response.json()  # Store full booking details


@when('buyer cancels reservation:')
def buyer_cancels_reservation(step, client, context):
    """Buyer cancels their reservation."""
    data = extract_table_data(step)
    buyer_id = int(data['buyer_id'])
    booking_id = int(data['booking_id'])

    # Login as buyer - buyer_id 2 maps to buyer@test.com (from Background)
    if buyer_id == 2:
        buyer_email = 'buyer@test.com'
    else:
        buyer_email = f'buyer{buyer_id - 1}@test.com'
    login_user(client, buyer_email, DEFAULT_PASSWORD)

    # Cancel reservation
    response = client.patch(BOOKING_CANCEL.format(booking_id=booking_id))
    context['response'] = response


@when('buyer creates booking with tickets:')
def buyer_creates_booking_with_tickets(step, client: TestClient, booking_state):
    """Buyer creates booking with specific tickets."""
    # Use actual ticket IDs from the booking_state if available, otherwise parse from table
    if 'ticket_ids' in booking_state:
        ticket_ids = booking_state['ticket_ids']
    else:
        ticket_data = extract_table_data(step)
        ticket_ids_str = ticket_data['ticket_ids']
        ticket_ids = [int(id.strip()) for id in ticket_ids_str.split(',')]

    # Create booking with specific ticket IDs
    response = client.post(BOOKING_BASE, json={'ticket_ids': ticket_ids})
    booking_state['response'] = response

    # Store booking if created successfully
    if response.status_code == 201:
        booking_state['booking'] = response.json()


@when('buyer creates booking with manual seat selection:')
def buyer_creates_booking_with_manual_seat_selection(step, client: TestClient, booking_state):
    """Buyer creates booking with manual seat selection."""
    seat_data = extract_table_data(step)
    selected_seats = seat_data['selected_seats'].split(',')

    # Create booking with manual seat selection
    booking_request = {
        'seat_selection_mode': 'manual',
        'selected_seats': selected_seats,
    }

    response = client.post(BOOKING_BASE, json=booking_request)
    booking_state['response'] = response

    # Store booking if created successfully
    if response.status_code == 201:
        booking_state['booking'] = response.json()
        booking_state['selected_seats'] = selected_seats


@when('buyer creates booking with best available seat selection:')
def buyer_creates_booking_with_best_available_seat_selection(
    step, client: TestClient, booking_state
):
    """Buyer creates booking with best available seat selection."""
    seat_data = extract_table_data(step)
    quantity = int(seat_data['quantity'])

    # Create booking with best available seat selection
    booking_request = {
        'seat_selection_mode': 'best_available',
        'quantity': quantity,
    }

    response = client.post(BOOKING_BASE, json=booking_request)
    booking_state['response'] = response

    # Store booking if created successfully
    if response.status_code == 201:
        booking_state['booking'] = response.json()
        booking_state['selected_quantity'] = quantity


@when('buyer creates booking with legacy ticket selection:')
def buyer_creates_booking_with_legacy_ticket_selection(step, client: TestClient, booking_state):
    ticket_data = extract_table_data(step)
    ticket_ids_str = ticket_data['ticket_ids']

    # Get actual ticket IDs from the event
    event_id = booking_state['event_id']
    tickets_response = client.get(EVENT_TICKETS_BY_SUBSECTION.format(event_id=event_id))

    if tickets_response.status_code == 200:
        tickets_data = tickets_response.json()
        available_tickets = [
            t for t in tickets_data.get('tickets', []) if t['status'] == 'available'
        ]

        # Parse the requested ticket count
        requested_ids = ticket_ids_str.split(',')
        num_tickets = len(requested_ids)

        # Use actual available ticket IDs
        if len(available_tickets) >= num_tickets:
            ticket_ids = [available_tickets[i]['id'] for i in range(num_tickets)]
        else:
            # Fallback to parsed IDs if not enough tickets
            ticket_ids = [int(id.strip()) for id in requested_ids]
    else:
        # Fallback to parsed IDs
        ticket_ids = [int(id.strip()) for id in ticket_ids_str.split(',')]

    # Create booking with legacy ticket IDs approach
    booking_request = {'ticket_ids': ticket_ids}

    response = client.post(BOOKING_BASE, json=booking_request)
    booking_state['response'] = response

    # Store booking if created successfully
    if response.status_code == 201:
        booking_state['booking'] = response.json()
        booking_state['legacy_ticket_ids'] = ticket_ids

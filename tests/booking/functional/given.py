from datetime import datetime
import json

import bcrypt
from fastapi.testclient import TestClient
from pytest_bdd import given

from src.shared.constant.route_constant import (
    AUTH_LOGIN,
    BOOKING_BASE,
    BOOKING_CANCEL,
    BOOKING_GET,
    BOOKING_PAY,
    EVENT_BASE,
    EVENT_TICKETS_BY_SUBSECTION,
    EVENT_TICKETS_CREATE,
)
from tests.event_test_constants import (
    DEFAULT_SEATING_CONFIG,
    DEFAULT_SEATING_CONFIG_JSON,
    DEFAULT_VENUE_NAME,
    TAIPEI_ARENA,
)
from tests.shared.utils import create_user, extract_table_data, login_user
from tests.util_constant import (
    DEFAULT_PASSWORD,
    SELLER1_EMAIL,
    TEST_BUYER_EMAIL,
    TEST_BUYER_NAME,
    TEST_CARD_NUMBER,
    TEST_EVENT_DESCRIPTION,
    TEST_EVENT_NAME,
    TEST_SELLER_EMAIL,
    TEST_SELLER_NAME,
)


@given('a booking exists with status "pending_payment":')
def create_pending_booking(step, client: TestClient, booking_state, execute_sql_statement):
    booking_data = extract_table_data(step)
    expected_seller_id = int(booking_data['seller_id'])
    expected_buyer_id = int(booking_data['buyer_id'])

    # Create users directly in database with expected IDs to ensure consistency
    hashed_password = bcrypt.hashpw(DEFAULT_PASSWORD.encode('utf-8'), bcrypt.gensalt()).decode(
        'utf-8'
    )

    # Create seller with expected ID
    execute_sql_statement(
        """
        INSERT INTO "user" (id, email, hashed_password, name, role, is_active, is_superuser, is_verified)
        VALUES (:id, :email, :hashed_password, :name, :role, true, false, true)
        ON CONFLICT (id) DO UPDATE SET
            email = EXCLUDED.email,
            hashed_password = EXCLUDED.hashed_password,
            name = EXCLUDED.name,
            role = EXCLUDED.role
        """,
        {
            'id': expected_seller_id,
            'email': TEST_SELLER_EMAIL,
            'hashed_password': hashed_password,
            'name': TEST_SELLER_NAME,
            'role': 'seller',
        },
    )

    # Create buyer with expected ID
    execute_sql_statement(
        """
        INSERT INTO "user" (id, email, hashed_password, name, role, is_active, is_superuser, is_verified)
        VALUES (:id, :email, :hashed_password, :name, :role, true, false, true)
        ON CONFLICT (id) DO UPDATE SET
            email = EXCLUDED.email,
            hashed_password = EXCLUDED.hashed_password,
            name = EXCLUDED.name,
            role = EXCLUDED.role
        """,
        {
            'id': expected_buyer_id,
            'email': TEST_BUYER_EMAIL,
            'hashed_password': hashed_password,
            'name': TEST_BUYER_NAME,
            'role': 'buyer',
        },
    )

    # Update sequence to avoid conflicts
    execute_sql_statement(
        'SELECT setval(\'user_id_seq\', (SELECT COALESCE(MAX(id), 0) + 1 FROM "user"), false)', {}
    )

    seller_id = expected_seller_id
    buyer_id = expected_buyer_id

    login_response = client.post(
        AUTH_LOGIN,
        data={'username': TEST_SELLER_EMAIL, 'password': DEFAULT_PASSWORD},
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    assert login_response.status_code == 200, f'Seller login failed: {login_response.text}'
    if 'fastapiusersauth' in login_response.cookies:
        client.cookies.set('fastapiusersauth', login_response.cookies['fastapiusersauth'])

    event_response = client.post(
        EVENT_BASE,
        json={
            'name': TEST_EVENT_NAME,
            'description': TEST_EVENT_DESCRIPTION,
            'is_active': True,
            'venue_name': TAIPEI_ARENA,
            'seating_config': DEFAULT_SEATING_CONFIG,
        },
    )
    assert event_response.status_code == 201, f'Failed to create event: {event_response.text}'
    event = event_response.json()
    print(f'TDD DEBUG: Created event with ID: {event["id"]}')

    login_response = client.post(
        AUTH_LOGIN,
        data={'username': TEST_BUYER_EMAIL, 'password': DEFAULT_PASSWORD},
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    assert login_response.status_code == 200, f'Buyer login failed: {login_response.text}'
    if 'fastapiusersauth' in login_response.cookies:
        client.cookies.set('fastapiusersauth', login_response.cookies['fastapiusersauth'])
    # Check if tickets already exist for the event, if not, create them
    login_response = client.post(
        AUTH_LOGIN,
        data={'username': TEST_SELLER_EMAIL, 'password': DEFAULT_PASSWORD},
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    assert login_response.status_code == 200, f'Seller login failed: {login_response.text}'
    if 'fastapiusersauth' in login_response.cookies:
        client.cookies.set('fastapiusersauth', login_response.cookies['fastapiusersauth'])

    # First check if tickets already exist
    tickets_list_response = client.get(
        EVENT_TICKETS_BY_SUBSECTION.format(event_id=event['id'], section='A', subsection=1)
    )
    if tickets_list_response.status_code == 200:
        tickets_data = tickets_list_response.json()
        existing_tickets = tickets_data.get('tickets', [])

        # If no tickets exist, create them
        if not existing_tickets:
            ticket_price = (
                int(booking_data['total_price']) // 2
            )  # Create 2 tickets with half price each
            tickets_response = client.post(
                EVENT_TICKETS_CREATE.format(event_id=event['id']), json={'price': ticket_price}
            )
            assert tickets_response.status_code == 201, (
                f'Failed to create tickets: {tickets_response.text}'
            )
            print(f'TDD DEBUG: Created tickets for event {event["id"]}')

    # TDD FIX: Always refetch tickets after potential creation to ensure data consistency
    tickets_list_response = client.get(
        EVENT_TICKETS_BY_SUBSECTION.format(event_id=event['id'], section='A', subsection=1)
    )
    assert tickets_list_response.status_code == 200, (
        f'Failed to get tickets: {tickets_list_response.text}'
    )
    tickets_data = tickets_list_response.json()

    available_tickets = [t for t in tickets_data['tickets'] if t['status'] == 'available']
    # Validate that we have enough available tickets
    if len(available_tickets) < 2:
        raise AssertionError(
            f'TDD ERROR: Need at least 2 available tickets, but found {len(available_tickets)}'
        )

    # TDD FIX: Use the actual tickets returned by the API for this specific event
    ticket_ids = [available_tickets[0]['id'], available_tickets[1]['id']]

    # TDD FIX: Validate ticket IDs are correctly extracted from API response
    assert ticket_ids[0] > 0, f'TDD ERROR: Invalid ticket ID {ticket_ids[0]}'
    assert ticket_ids[1] > 0, f'TDD ERROR: Invalid ticket ID {ticket_ids[1]}'
    assert ticket_ids[0] != ticket_ids[1], f'TDD ERROR: Duplicate ticket IDs {ticket_ids}'

    print(f'TDD DEBUG: Event {event["id"]} - Final ticket IDs for booking creation: {ticket_ids}')

    # Switch back to buyer login
    login_response = client.post(
        AUTH_LOGIN,
        data={'username': TEST_BUYER_EMAIL, 'password': DEFAULT_PASSWORD},
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    assert login_response.status_code == 200, f'Buyer login failed: {login_response.text}'
    if 'fastapiusersauth' in login_response.cookies:
        client.cookies.set('fastapiusersauth', login_response.cookies['fastapiusersauth'])

    # Build the correct JSON payload based on available tickets
    # For manual mode, format as {ticket_id: 'section-subsection-row-seat'}
    seat_positions = [
        {
            available_tickets[0][
                'id'
            ]: f'{available_tickets[0]["section"]}-{available_tickets[0]["subsection"]}-{available_tickets[0]["row"]}-{available_tickets[0]["seat"]}'
        },
        {
            available_tickets[1][
                'id'
            ]: f'{available_tickets[1]["section"]}-{available_tickets[1]["subsection"]}-{available_tickets[1]["row"]}-{available_tickets[1]["seat"]}'
        },
    ]

    booking_response = client.post(
        BOOKING_BASE,
        json={
            'event_id': event['id'],
            'seat_selection_mode': 'manual',
            'seat_positions': seat_positions,
        },
    )
    assert booking_response.status_code == 201, f'Failed to create booking: {booking_response.text}'
    booking = booking_response.json()

    # TDD FIX: Validate the booking was created with the correct ticket IDs
    print(f'TDD DEBUG: Booking created successfully with ID: {booking["id"]}')
    print(f'TDD DEBUG: Booking response: {booking}')

    # TDD FIX: Verify the tickets were properly associated with the booking by querying them back
    post_booking_tickets_response = client.get(
        EVENT_TICKETS_BY_SUBSECTION.format(event_id=event['id'], section='A', subsection=1)
    )
    if post_booking_tickets_response.status_code == 200:
        post_booking_tickets = post_booking_tickets_response.json()['tickets']
        booking_associated_tickets = [t for t in post_booking_tickets if t['id'] in ticket_ids]
        print(
            f'TDD DEBUG: Post-booking ticket check - found {len(booking_associated_tickets)} tickets associated with booking'
        )
        for ticket in booking_associated_tickets:
            print(f'TDD DEBUG: Ticket {ticket["id"]} - status: {ticket["status"]}')

    booking_state['booking'] = booking
    booking_state['buyer_id'] = buyer_id
    booking_state['seller_id'] = seller_id
    booking_state['event_id'] = event['id']
    booking_state['ticket_ids'] = ticket_ids


@given('a booking exists with status "paid":')
def create_paid_booking(step, client: TestClient, booking_state, execute_sql_statement):
    booking_data = extract_table_data(step)
    create_pending_booking(step, client, booking_state, execute_sql_statement)
    if 'paid_at' in booking_data and booking_data['paid_at'] == 'not_null':
        execute_sql_statement(
            'UPDATE "booking" SET status = \'paid\', paid_at = :paid_at WHERE id = :id',
            {'paid_at': datetime.now(), 'id': booking_state['booking']['id']},
        )
        booking_state['booking']['status'] = 'paid'
        booking_state['booking']['paid_at'] = datetime.now().isoformat()


@given('a booking exists with status "cancelled":')
def create_cancelled_booking(step, client: TestClient, booking_state, execute_sql_statement):
    create_pending_booking(step, client, booking_state, execute_sql_statement)
    execute_sql_statement(
        'UPDATE "booking" SET status = \'cancelled\' WHERE id = :id',
        {'id': booking_state['booking']['id']},
    )
    execute_sql_statement(
        "UPDATE event SET status = 'available' WHERE id = :id", {'id': booking_state['event_id']}
    )
    booking_state['booking']['status'] = 'cancelled'


@given('users exist:')
def create_users(step, client: TestClient, booking_state, execute_sql_statement):
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    booking_state['users'] = {}
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        user_data = dict(zip(headers, values, strict=True))
        user_id = int(user_data['id'])
        hashed_password = bcrypt.hashpw(
            user_data['password'].encode('utf-8'), bcrypt.gensalt()
        ).decode('utf-8')
        execute_sql_statement(
            '\n                INSERT INTO "user" (id, email, hashed_password, name, role, is_active, is_superuser, is_verified)\n                VALUES (:id, :email, :hashed_password, :name, :role, true, false, true)\n            ',
            {
                'id': user_id,
                'email': user_data['email'],
                'hashed_password': hashed_password,
                'name': user_data['name'],
                'role': user_data['role'],
            },
        )
        booking_state['users'][user_id] = {
            'id': user_id,
            'email': user_data['email'],
            'name': user_data['name'],
            'role': user_data['role'],
        }
    execute_sql_statement(
        'SELECT setval(\'user_id_seq\', (SELECT COALESCE(MAX(id), 0) + 1 FROM "user"), false)', {}
    )


@given('events exist:')
def create_events(step, client: TestClient, booking_state, execute_sql_statement):
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    booking_state['events'] = {}
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        event_data = dict(zip(headers, values, strict=True))
        event_id = int(event_data['id'])
        seller_id = int(event_data['seller_id'])

        execute_sql_statement(
            '\n                INSERT INTO event (id, seller_id, name, description, is_active, status, venue_name, seating_config)\n                VALUES (:id, :seller_id, :name, :description, :is_active, :status, :venue_name, :seating_config)\n            ',
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
        booking_state['events'][event_id] = {
            'id': event_id,
            'seller_id': seller_id,
            'name': event_data['name'],
            'status': event_data['status'],
        }
    execute_sql_statement(
        "SELECT setval('event_id_seq', (SELECT COALESCE(MAX(id), 0) + 1 FROM event), false)", {}
    )


@given('bookings exist:')
def create_bookings(step, client: TestClient, booking_state, execute_sql_statement):
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    booking_state['bookings'] = {}
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        booking_data = dict(zip(headers, values, strict=True))
        event_key = int(booking_data['event_id'])
        if 'events' in booking_state and event_key in booking_state['events']:
            event_id = booking_state['events'][event_key]['id']
        else:
            event_id = event_key
        booking_id = int(booking_data['id'])
        # Generate unique ticket IDs for each booking to avoid constraint violations
        unique_ticket_ids = [
            booking_id * 1000,
            booking_id * 1000 + 1,
        ]  # Simple unique ID generation

        if booking_data.get('paid_at') == 'not_null' and booking_data['status'] == 'paid':
            execute_sql_statement(
                '\n                    INSERT INTO "booking" (id, buyer_id, seller_id, event_id, total_price, status, ticket_ids, created_at, updated_at, paid_at)\n                    VALUES (:id, :buyer_id, :seller_id, :event_id, :total_price, :status, :ticket_ids, NOW(), NOW(), NOW())\n                ',
                {
                    'id': booking_id,
                    'buyer_id': int(booking_data['buyer_id']),
                    'seller_id': int(booking_data['seller_id']),
                    'event_id': event_id,
                    'total_price': int(booking_data['total_price']),
                    'status': booking_data['status'],
                    'ticket_ids': unique_ticket_ids,
                },
            )
        else:
            execute_sql_statement(
                '\n                    INSERT INTO "booking" (id, buyer_id, seller_id, event_id, total_price, status, ticket_ids, created_at, updated_at)\n                    VALUES (:id, :buyer_id, :seller_id, :event_id, :total_price, :status, :ticket_ids, NOW(), NOW())\n                ',
                {
                    'id': booking_id,
                    'buyer_id': int(booking_data['buyer_id']),
                    'seller_id': int(booking_data['seller_id']),
                    'event_id': event_id,
                    'total_price': int(booking_data['total_price']),
                    'status': booking_data['status'],
                    'ticket_ids': unique_ticket_ids,
                },
            )
        booking_state['bookings'][int(booking_data['id'])] = {'id': booking_id}
    execute_sql_statement(
        'SELECT setval(\'booking_id_seq\', (SELECT COALESCE(MAX(id), 0) + 1 FROM "booking"), false)',
        {},
    )


@given('the buyer pays for the booking')
def buyer_pays_for_booking_given(client: TestClient, booking_state):
    """Given that the buyer has paid for the booking."""
    booking_id = booking_state['booking']['id']
    response = client.post(
        BOOKING_PAY.format(booking_id=booking_id),
        json={'card_number': TEST_CARD_NUMBER},
    )
    assert response.status_code == 200, f'Failed to pay for booking: {response.text}'

    # Fetch the updated booking details after payment
    booking_response = client.get(BOOKING_GET.format(booking_id=booking_id))
    assert booking_response.status_code == 200
    booking_state['updated_booking'] = booking_response.json()  # Store full booking details
    booking_state['booking']['status'] = 'paid'


@given('the buyer cancels the booking')
def buyer_cancels_booking_simple(client: TestClient, booking_state):
    """Given that the buyer has cancelled the booking."""
    booking_id = booking_state['booking']['id']
    response = client.patch(BOOKING_CANCEL.format(booking_id=booking_id))
    assert response.status_code == 200, f'Failed to cancel booking: {response.text}'
    booking_state['booking']['status'] = 'cancelled'
    booking_state['updated_booking'] = {'status': 'cancelled'}  # For Then step compatibility


@given('tickets exist for event:')
def tickets_exist_for_event(step, client, booking_state=None):
    data = extract_table_data(step)
    event_id = int(data['event_id'])
    price = int(data['price'])

    # Create seller1 user if it doesn't exist
    create_user(client, SELLER1_EMAIL, DEFAULT_PASSWORD, 'Test Seller 1', 'seller')

    # Login as seller1 to create event and tickets
    login_user(client, SELLER1_EMAIL, DEFAULT_PASSWORD)

    # Create event first (if it doesn't exist)
    # Use the correct seating config format that matches the ticket creation logic
    seating_config = {
        'sections': [
            {
                'name': 'A',
                'price': price,
                'subsections': [{'number': 1, 'rows': 25, 'seats_per_row': 20}],
            }
        ]
    }

    event_response = client.post(
        EVENT_BASE,
        json={
            'name': f'Test Event {event_id}',
            'description': 'Test event for tickets',
            'is_active': True,
            'venue_name': DEFAULT_VENUE_NAME,
            'seating_config': seating_config,
        },
    )

    if event_response.status_code != 201:
        # Event might already exist, that's okay
        pass
    else:
        # Use the actual event ID from creation
        event = event_response.json()
        event_id = event['id']

    # In this test environment, we know tickets are created with IDs 1, 2, 3, etc.
    ticket_ids = [1, 2]

    # Store ticket IDs for use in test steps if booking_state is available
    if booking_state is not None:
        booking_state['ticket_ids'] = ticket_ids
        booking_state['event_id'] = event_id


@given('an event exists with seating configuration:')
def create_event_with_seating_config(
    step, client: TestClient, booking_state, execute_sql_statement
):
    event_data = extract_table_data(step)

    # Ensure seller is logged in to create event
    login_user(client, TEST_SELLER_EMAIL, DEFAULT_PASSWORD)

    # Create event with seating configuration
    seating_config = json.loads(event_data['seating_config'])
    event_response = client.post(
        EVENT_BASE,
        json={
            'name': event_data['name'],
            'description': f'Event: {event_data["name"]}',
            'is_active': True,
            'venue_name': event_data['venue_name'],
            'seating_config': seating_config,
        },
    )
    assert event_response.status_code == 201, f'Failed to create event: {event_response.text}'
    event = event_response.json()

    # Check if tickets already exist for this event
    tickets_list_response = client.get(
        EVENT_TICKETS_BY_SUBSECTION.format(event_id=event['id'], section='A', subsection=1)
    )
    if tickets_list_response.status_code == 200:
        tickets_data = tickets_list_response.json()
        existing_tickets = tickets_data.get('tickets', [])

        # Only create tickets if none exist
        if not existing_tickets:
            tickets_response = client.post(
                EVENT_TICKETS_CREATE.format(event_id=event['id']),
                json={'price': seating_config['sections'][0]['price']},  # Use first section price
            )
            assert tickets_response.status_code == 201, (
                f'Failed to create tickets: {tickets_response.text}'
            )

    # IMPORTANT: Log back in as buyer since the Background says "I am logged in as buyer@test.com"
    login_user(client, TEST_BUYER_EMAIL, DEFAULT_PASSWORD)

    # Store event data in booking state
    booking_state['event'] = event
    booking_state['event_id'] = event['id']
    booking_state['seating_config'] = seating_config


@given('seats are already booked:')
def seats_already_booked(step, client: TestClient, booking_state, execute_sql_statement):
    # Get the seat numbers from the table
    rows = step.data_table.rows
    seat_numbers = []
    for row in rows[1:]:  # Skip header
        seat_numbers.append(row.cells[0].value)

    # Login as seller to access all tickets
    login_user(client, TEST_SELLER_EMAIL, DEFAULT_PASSWORD)

    # Get all tickets for the event
    event_id = booking_state['event_id']
    tickets_response = client.get(
        EVENT_TICKETS_BY_SUBSECTION.format(event_id=event_id, section='A', subsection=1)
    )
    assert tickets_response.status_code == 200, f'Failed to get tickets: {tickets_response.text}'
    tickets_data = tickets_response.json()
    tickets = tickets_data.get('tickets', [])

    # Find tickets by seat identifier and mark them as reserved
    for seat_number in seat_numbers:
        matching_ticket = None
        for ticket in tickets:
            if ticket.get('seat_identifier') == seat_number:
                matching_ticket = ticket
                break

        if matching_ticket:
            # Mark the ticket as reserved in the database
            execute_sql_statement(
                """
                UPDATE ticket
                SET status = 'reserved', buyer_id = NULL, reserved_at = NOW()
                WHERE id = :ticket_id
                """,
                {'ticket_id': matching_ticket['id']},
            )

    # IMPORTANT: Log back in as buyer since the Background says "I am logged in as buyer@test.com"
    login_user(client, TEST_BUYER_EMAIL, DEFAULT_PASSWORD)

    # Store the booked seat numbers for reference
    booking_state['booked_seats'] = seat_numbers

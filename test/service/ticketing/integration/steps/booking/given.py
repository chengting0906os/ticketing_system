from datetime import datetime
import json

import bcrypt
from fastapi.testclient import TestClient
from pytest_bdd import given
from test.event_test_constants import DEFAULT_SEATING_CONFIG_JSON, DEFAULT_VENUE_NAME
from test.shared.utils import extract_table_data, login_user
from test.util_constant import DEFAULT_PASSWORD, TEST_BUYER_EMAIL, TEST_SELLER_EMAIL

from src.platform.constant.route_constant import EVENT_BASE, EVENT_TICKETS_BY_SUBSECTION


@given('a booking exists with status "pending_payment":')
def create_pending_booking(step, client: TestClient, booking_state, execute_sql_statement):
    """Create a pending booking using existing event from Background"""
    booking_data = extract_table_data(step)

    # Assume event was created in Background (event_id=1)
    event_id = int(booking_data.get('event_id', 1))
    buyer_id = int(booking_data['buyer_id'])
    total_price = int(booking_data['total_price'])

    # Directly insert booking into database with pending_payment status
    execute_sql_statement(
        """
        INSERT INTO "booking" (buyer_id, event_id, section, subsection, quantity, total_price, status, seat_selection_mode, created_at, updated_at)
        VALUES (:buyer_id, :event_id, :section, :subsection, :quantity, :total_price, :status, :seat_selection_mode, NOW(), NOW())
        RETURNING id
        """,
        {
            'buyer_id': buyer_id,
            'event_id': event_id,
            'section': 'A',
            'subsection': 1,
            'quantity': 2,
            'total_price': total_price,
            'status': 'pending_payment',
            'seat_selection_mode': 'manual',
        },
    )

    # Get the created booking ID
    result = execute_sql_statement(
        'SELECT id FROM booking ORDER BY id DESC LIMIT 1',
        {},
        fetch=True,
    )
    booking_id = result[0]['id'] if result else 1

    booking_state['booking'] = {'id': booking_id, 'status': 'pending_payment', 'event_id': event_id}
    booking_state['buyer_id'] = buyer_id
    booking_state['event_id'] = event_id


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
            # Tickets are created automatically by event initialization
            pass

    # IMPORTANT: Log back in as buyer since the Background says "I am logged in as buyer@test.com"
    login_user(client, TEST_BUYER_EMAIL, DEFAULT_PASSWORD)

    # Store event data in booking state
    booking_state['event'] = event
    booking_state['event_id'] = event['id']
    booking_state['seating_config'] = seating_config


@given('users exist:')
def create_users(step, booking_state, execute_sql_statement):
    """Create users for booking_list test."""
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
def create_events(step, booking_state, execute_sql_statement):
    """Create events for booking_list test."""
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
        booking_state['events'][event_id] = {
            'id': event_id,
            'seller_id': seller_id,
            'name': event_data['name'],
            'status': event_data['status'],
        }
    execute_sql_statement(
        "SELECT setval('event_id_seq', (SELECT COALESCE(MAX(id), 0) + 1 FROM event), false)", {}
    )


@given('bookings with tickets exist:')
def create_bookings_with_tickets(step, booking_state, execute_sql_statement):
    """Create bookings with associated tickets for detailed testing."""
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]

    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        booking_data = dict(zip(headers, values, strict=True))

        booking_id = int(booking_data['booking_id'])
        buyer_id = int(booking_data['buyer_id'])
        event_id = int(booking_data['event_id'])
        section = booking_data['section']
        subsection = int(booking_data['subsection'])
        quantity = int(booking_data['quantity'])
        total_price = int(booking_data['total_price'])
        status = booking_data['status']
        seat_selection_mode = booking_data.get('seat_selection_mode', 'best_available')

        # Create booking
        if booking_data.get('paid_at') == 'not_null':
            execute_sql_statement(
                """
                INSERT INTO "booking" (id, buyer_id, event_id, section, subsection, quantity, total_price, status, seat_selection_mode, seat_positions, created_at, updated_at, paid_at)
                VALUES (:id, :buyer_id, :event_id, :section, :subsection, :quantity, :total_price, :status, :seat_selection_mode, :seat_positions, NOW(), NOW(), NOW())
                """,
                {
                    'id': booking_id,
                    'buyer_id': buyer_id,
                    'event_id': event_id,
                    'section': section,
                    'subsection': subsection,
                    'quantity': quantity,
                    'total_price': total_price,
                    'status': status,
                    'seat_selection_mode': seat_selection_mode,
                    'seat_positions': [],
                },
            )
        else:
            execute_sql_statement(
                """
                INSERT INTO "booking" (id, buyer_id, event_id, section, subsection, quantity, total_price, status, seat_selection_mode, seat_positions, created_at, updated_at)
                VALUES (:id, :buyer_id, :event_id, :section, :subsection, :quantity, :total_price, :status, :seat_selection_mode, :seat_positions, NOW(), NOW())
                """,
                {
                    'id': booking_id,
                    'buyer_id': buyer_id,
                    'event_id': event_id,
                    'section': section,
                    'subsection': subsection,
                    'quantity': quantity,
                    'total_price': total_price,
                    'status': status,
                    'seat_selection_mode': seat_selection_mode,
                    'seat_positions': [],
                },
            )

        # Create tickets if ticket_ids provided
        if 'ticket_ids' in booking_data:
            ticket_ids = [int(tid.strip()) for tid in booking_data['ticket_ids'].split(',')]
            for idx, ticket_id in enumerate(ticket_ids):
                # Create ticket - map booking status to ticket status
                ticket_status = 'sold' if status == 'paid' else 'reserved'
                execute_sql_statement(
                    """
                    INSERT INTO ticket (id, event_id, section, subsection, row_number, seat_number, price, status, buyer_id, created_at, updated_at)
                    VALUES (:id, :event_id, :section, :subsection, :row_number, :seat_number, :price, :status, :buyer_id, NOW(), NOW())
                    """,
                    {
                        'id': ticket_id,
                        'event_id': event_id,
                        'section': section,
                        'subsection': subsection,
                        'row_number': 1,
                        'seat_number': idx + 1,
                        'price': 1000,
                        'status': ticket_status,
                        'buyer_id': buyer_id,
                    },
                )
                # Link ticket to booking
                execute_sql_statement(
                    """
                    INSERT INTO booking_ticket (booking_id, ticket_id)
                    VALUES (:booking_id, :ticket_id)
                    """,
                    {
                        'booking_id': booking_id,
                        'ticket_id': ticket_id,
                    },
                )


@given('bookings exist:')
def create_bookings(step, booking_state, execute_sql_statement):
    """Create bookings for booking_list test."""
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

        # Get section/subsection/quantity/seat_selection_mode/seat_positions from table if provided
        if 'section' in booking_data:
            section = booking_data['section']
            subsection = int(booking_data['subsection'])
            quantity = int(booking_data['quantity'])
            seat_selection_mode = booking_data.get('seat_selection_mode', 'best_available')
            # Parse seat_positions from JSON string if provided
            if 'seat_positions' in booking_data:
                import json

                seat_positions = json.loads(booking_data['seat_positions'])
            else:
                seat_positions = []
        else:
            # Determine section/subsection from event_id (backward compatibility)
            # Event A (id=1) -> section A, subsection 1
            # Event B (id=2) -> section B, subsection 2
            # Event C (id=3) -> section C, subsection 3
            # Event D (id=4) -> section D, subsection 4
            section_map = {1: ('A', 1), 2: ('B', 2), 3: ('C', 3), 4: ('D', 4)}
            section, subsection = section_map.get(event_id, ('A', 1))
            quantity = 1
            seat_selection_mode = 'best_available'
            seat_positions = []

        if booking_data.get('paid_at') == 'not_null' and booking_data['status'] == 'paid':
            execute_sql_statement(
                """
                INSERT INTO "booking" (id, buyer_id, event_id, section, subsection, quantity, total_price, status, seat_selection_mode, seat_positions, created_at, updated_at, paid_at)
                VALUES (:id, :buyer_id, :event_id, :section, :subsection, :quantity, :total_price, :status, :seat_selection_mode, :seat_positions, NOW(), NOW(), NOW())
                """,
                {
                    'id': booking_id,
                    'buyer_id': int(booking_data['buyer_id']),
                    'event_id': event_id,
                    'section': section,
                    'subsection': subsection,
                    'quantity': quantity,
                    'total_price': int(booking_data['total_price']),
                    'status': booking_data['status'],
                    'seat_selection_mode': seat_selection_mode,
                    'seat_positions': seat_positions,
                },
            )
        else:
            execute_sql_statement(
                """
                INSERT INTO "booking" (id, buyer_id, event_id, section, subsection, quantity, total_price, status, seat_selection_mode, seat_positions, created_at, updated_at)
                VALUES (:id, :buyer_id, :event_id, :section, :subsection, :quantity, :total_price, :status, :seat_selection_mode, :seat_positions, NOW(), NOW())
                """,
                {
                    'id': booking_id,
                    'buyer_id': int(booking_data['buyer_id']),
                    'event_id': event_id,
                    'section': section,
                    'subsection': subsection,
                    'quantity': quantity,
                    'total_price': int(booking_data['total_price']),
                    'status': booking_data['status'],
                    'seat_selection_mode': seat_selection_mode,
                    'seat_positions': seat_positions,
                },
            )
        booking_state['bookings'][int(booking_data['id'])] = {'id': booking_id}
    execute_sql_statement(
        'SELECT setval(\'booking_id_seq\', (SELECT COALESCE(MAX(id), 0) + 1 FROM "booking"), false)',
        {},
    )

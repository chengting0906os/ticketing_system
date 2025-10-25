from datetime import datetime
import json
from uuid import UUID

import bcrypt
from fastapi.testclient import TestClient
from pytest_bdd import given

from src.platform.constant.route_constant import EVENT_BASE, EVENT_TICKETS_BY_SUBSECTION
from test.event_test_constants import DEFAULT_SEATING_CONFIG_JSON, DEFAULT_VENUE_NAME
from test.shared.utils import extract_table_data, login_user
from test.util_constant import DEFAULT_PASSWORD, TEST_BUYER_EMAIL, TEST_SELLER_EMAIL


@given('a booking exists with status "pending_payment":')
def create_pending_booking(step, client: TestClient, booking_state, execute_cql_statement):
    """Create a pending booking using existing event from Background"""
    booking_data = extract_table_data(step)

    # Get event_id from booking_state (created in Background)
    event_id = booking_state.get('event_id') or booking_state.get('event', {}).get('id')
    if not event_id:
        event_id_str = booking_data.get('event_id', '019a1af7-0000-7003-0000-000000000001')
        event_id = UUID(event_id_str) if isinstance(event_id_str, str) else event_id_str
    else:
        # Ensure event_id is a UUID object (HTTP responses return strings)
        event_id = UUID(event_id) if isinstance(event_id, str) else event_id

    # Get buyer_id from booking_state (actual ID from created user)
    # Fallback to table data for backward compatibility with other tests
    buyer_id_raw = booking_state.get('buyer', {}).get('id') or booking_data['buyer_id']
    buyer_id = UUID(buyer_id_raw) if isinstance(buyer_id_raw, str) else buyer_id_raw
    total_price = int(booking_data['total_price'])

    # Get denormalized data for ScyllaDB
    buyer = booking_state.get('buyer', {})
    event = booking_state.get('event', {})
    seller = booking_state.get('seller', {})

    # Convert seller_id to UUID if it's a string (from HTTP response)
    seller_id_raw = seller.get('id', '019a1af7-0000-7002-0000-000000000001')
    seller_id = UUID(seller_id_raw) if isinstance(seller_id_raw, str) else seller_id_raw

    # Directly insert booking into database with pending_payment status
    # ScyllaDB requires all denormalized fields
    execute_cql_statement(
        """
        INSERT INTO "booking" (buyer_id, event_id, section, subsection, quantity, total_price, status, seat_selection_mode, seat_positions, created_at, updated_at, buyer_name, buyer_email, event_name, venue_name, seller_id, seller_name)
        VALUES (:buyer_id, :event_id, :section, :subsection, :quantity, :total_price, :status, :seat_selection_mode, :seat_positions, currenttimestamp(), currenttimestamp(), :buyer_name, :buyer_email, :event_name, :venue_name, :seller_id, :seller_name)
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
            'seat_positions': [],
            'buyer_name': buyer.get('name', 'Test Buyer'),
            'buyer_email': buyer.get('email', 'buyer@test.com'),
            'event_name': event.get('name', 'Test Event'),
            'venue_name': 'Taipei Arena',
            'seller_id': seller_id,
            'seller_name': seller.get('name', 'Test Seller'),
        },
    )

    # Get the created booking ID (ScyllaDB uses timestamp-based IDs)
    result = execute_cql_statement(
        'SELECT id FROM "booking" WHERE buyer_id = :buyer_id ALLOW FILTERING',
        {'buyer_id': buyer_id},
        fetch=True,
    )
    booking_id = result[0]['id'] if result else 1

    # Create reserved tickets for this booking
    # Find available tickets from the event (ScyllaDB: query by partition key)
    available_tickets = execute_cql_statement(
        """SELECT id, row_number, seat_number FROM "ticket" WHERE event_id = :event_id AND section = :section AND subsection = :subsection AND status = 'available' LIMIT 2""",
        {'event_id': event_id, 'section': 'A', 'subsection': 1},
        fetch=True,
    )

    ticket_ids = []
    seat_positions = []
    if available_tickets:
        for ticket in available_tickets:
            ticket_id = ticket['id']
            row_num = ticket['row_number']
            seat_num = ticket['seat_number']
            ticket_ids.append(ticket_id)
            seat_positions.append(f'{row_num}-{seat_num}')

            # Update ticket to reserved status and link to booking
            # ScyllaDB: UPDATE requires partition key + clustering key
            execute_cql_statement(
                """UPDATE "ticket" SET status = 'reserved', buyer_id = :buyer_id WHERE event_id = :event_id AND section = :section AND subsection = :subsection AND row_number = :row_num AND seat_number = :seat_num""",
                {
                    'buyer_id': buyer_id,
                    'event_id': event_id,
                    'section': 'A',
                    'subsection': 1,
                    'row_num': row_num,
                    'seat_num': seat_num,
                },
            )

    # Update booking with seat_positions
    # ScyllaDB: WITH PRIMARY KEY (buyer_id, id), we must include both in WHERE clause
    if seat_positions:
        execute_cql_statement(
            'UPDATE "booking" SET seat_positions = :seat_positions WHERE buyer_id = :buyer_id AND id = :booking_id',
            {'buyer_id': buyer_id, 'booking_id': booking_id, 'seat_positions': seat_positions},
        )

    booking_state['booking'] = {'id': booking_id, 'status': 'pending_payment', 'event_id': event_id}
    booking_state['buyer_id'] = buyer_id
    booking_state['event_id'] = event_id
    booking_state['ticket_ids'] = ticket_ids


@given('a booking exists with status "completed":')
def create_completed_booking(step, client: TestClient, booking_state, execute_cql_statement):
    booking_data = extract_table_data(step)
    create_pending_booking(step, client, booking_state, execute_cql_statement)
    if 'paid_at' in booking_data and booking_data['paid_at'] == 'not_null':
        # ScyllaDB: With PRIMARY KEY (buyer_id, id), we must include both in WHERE clause
        # Ensure UUIDs are proper UUID objects, not strings
        buyer_id = booking_state['buyer_id']
        booking_id = booking_state['booking']['id']
        if isinstance(buyer_id, str):
            buyer_id = UUID(buyer_id)
        if isinstance(booking_id, str):
            booking_id = UUID(booking_id)

        execute_cql_statement(
            'UPDATE "booking" SET status = \'completed\', paid_at = :paid_at WHERE buyer_id = :buyer_id AND id = :id',
            {
                'paid_at': datetime.now(),
                'buyer_id': buyer_id,
                'id': booking_id,
            },
        )
        booking_state['booking']['status'] = 'completed'
        booking_state['booking']['paid_at'] = datetime.now().isoformat()


@given('a booking exists with status "cancelled":')
def create_cancelled_booking(step, client: TestClient, booking_state, execute_cql_statement):
    create_pending_booking(step, client, booking_state, execute_cql_statement)
    # ScyllaDB: With PRIMARY KEY (buyer_id, id), we must include both in WHERE clause
    # Ensure UUIDs are proper UUID objects, not strings
    buyer_id = booking_state['buyer_id']
    booking_id = booking_state['booking']['id']
    if isinstance(buyer_id, str):
        buyer_id = UUID(buyer_id)
    if isinstance(booking_id, str):
        booking_id = UUID(booking_id)

    execute_cql_statement(
        'UPDATE "booking" SET status = \'cancelled\' WHERE buyer_id = :buyer_id AND id = :id',
        {'buyer_id': buyer_id, 'id': booking_id},
    )

    # Ensure event_id is also a UUID object
    event_id = booking_state['event_id']
    if isinstance(event_id, str):
        event_id = UUID(event_id)

    execute_cql_statement(
        """UPDATE "event" SET status = 'available' WHERE id = :id""",
        {'id': event_id},
    )
    booking_state['booking']['status'] = 'cancelled'


@given('an event exists with seating configuration:')
def create_event_with_seating_config(
    step, client: TestClient, booking_state, execute_cql_statement
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
def create_users(step, booking_state, execute_cql_statement):
    """Create users for booking_list test."""
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    booking_state['users'] = {}
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        user_data = dict(zip(headers, values, strict=True))
        user_id = UUID(user_data['id'])
        hashed_password = bcrypt.hashpw(
            user_data['password'].encode('utf-8'), bcrypt.gensalt()
        ).decode('utf-8')
        execute_cql_statement(
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
    # Note: ScyllaDB uses timestamp-based ID generation, no sequence management needed


@given('events exist:')
def create_events(step, booking_state, execute_cql_statement):
    """Create events for booking_list test."""
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    booking_state['events'] = {}
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        event_data = dict(zip(headers, values, strict=True))
        event_id = UUID(event_data['id'])
        seller_id = UUID(event_data['seller_id'])

        execute_cql_statement(
            """
            INSERT INTO "event" (id, seller_id, name, description, is_active, status, venue_name, seating_config)
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
            'venue_name': event_data.get('venue_name', DEFAULT_VENUE_NAME),
            'seller_id': seller_id,
            'name': event_data['name'],
            'status': event_data['status'],
        }
    # Note: ScyllaDB uses timestamp-based ID generation, no sequence management needed


@given('bookings with tickets exist:')
def create_bookings_with_tickets(step, booking_state, execute_cql_statement):
    """Create bookings with associated tickets for detailed testing."""
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]

    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        booking_data = dict(zip(headers, values, strict=True))

        booking_id = UUID(booking_data['booking_id'])
        buyer_id = UUID(booking_data['buyer_id'])
        event_id = UUID(booking_data['event_id'])
        section = booking_data['section']
        subsection = int(booking_data['subsection'])
        quantity = int(booking_data['quantity'])
        total_price = int(booking_data['total_price'])
        status = booking_data['status']
        seat_selection_mode = booking_data.get('seat_selection_mode', 'best_available')

        # Get denormalized data for ScyllaDB
        buyer_info = booking_state.get('users', {}).get(buyer_id, {})
        event_info = booking_state.get('events', {}).get(event_id, {})
        seller_id = event_info.get('seller_id', 1)
        seller_info = booking_state.get('users', {}).get(seller_id, {})

        # Create booking
        if booking_data.get('paid_at') == 'not_null':
            execute_cql_statement(
                """
                INSERT INTO "booking" (id, buyer_id, event_id, section, subsection, quantity, total_price, status, seat_selection_mode, seat_positions, created_at, updated_at, paid_at, buyer_name, buyer_email, event_name, venue_name, seller_id, seller_name)
                VALUES (:id, :buyer_id, :event_id, :section, :subsection, :quantity, :total_price, :status, :seat_selection_mode, :seat_positions, currenttimestamp(), currenttimestamp(), currenttimestamp(), :buyer_name, :buyer_email, :event_name, :venue_name, :seller_id, :seller_name)
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
                    'buyer_name': buyer_info.get('name', f'Buyer {buyer_id}'),
                    'buyer_email': buyer_info.get('email', f'buyer{buyer_id}@test.com'),
                    'event_name': event_info.get('name', f'Event {event_id}'),
                    'venue_name': event_info.get('venue_name', 'Taipei Arena'),
                    'seller_id': seller_id,
                    'seller_name': seller_info.get('name', f'Seller {seller_id}'),
                },
            )
        else:
            execute_cql_statement(
                """
                INSERT INTO "booking" (id, buyer_id, event_id, section, subsection, quantity, total_price, status, seat_selection_mode, seat_positions, created_at, updated_at, buyer_name, buyer_email, event_name, venue_name, seller_id, seller_name)
                VALUES (:id, :buyer_id, :event_id, :section, :subsection, :quantity, :total_price, :status, :seat_selection_mode, :seat_positions, currenttimestamp(), currenttimestamp(), :buyer_name, :buyer_email, :event_name, :venue_name, :seller_id, :seller_name)
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
                    'buyer_name': buyer_info.get('name', f'Buyer {buyer_id}'),
                    'buyer_email': buyer_info.get('email', f'buyer{buyer_id}@test.com'),
                    'event_name': event_info.get('name', f'Event {event_id}'),
                    'venue_name': event_info.get('venue_name', 'Taipei Arena'),
                    'seller_id': seller_id,
                    'seller_name': seller_info.get('name', f'Seller {seller_id}'),
                },
            )

        # Create tickets if ticket_ids provided
        if 'ticket_ids' in booking_data:
            ticket_ids = [UUID(tid.strip()) for tid in booking_data['ticket_ids'].split(',')]
            seat_positions = []
            tickets_data = []

            for idx, ticket_id in enumerate(ticket_ids):
                # Create ticket - map booking status to ticket status
                ticket_status = 'sold' if status == 'paid' else 'reserved'
                row_number = 1
                seat_number = idx + 1

                execute_cql_statement(
                    """
                    INSERT INTO "ticket" (id, event_id, section, subsection, row_number, seat_number, price, status, buyer_id, created_at, updated_at)
                    VALUES (:id, :event_id, :section, :subsection, :row_number, :seat_number, :price, :status, :buyer_id, currenttimestamp(), currenttimestamp())
                    """,
                    {
                        'id': ticket_id,
                        'event_id': event_id,
                        'section': section,
                        'subsection': subsection,
                        'row_number': row_number,
                        'seat_number': seat_number,
                        'price': 1000,
                        'status': ticket_status,
                        'buyer_id': buyer_id,
                    },
                )

                # Build seat_positions list (format: "section-subsection-row-seat")
                seat_positions.append(f'{section}-{subsection}-{row_number}-{seat_number}')

                # Build tickets_data for denormalization in ScyllaDB
                tickets_data.append(
                    {
                        'id': str(ticket_id),
                        'section': section,
                        'subsection': str(subsection),
                        'row': str(row_number),
                        'seat': str(seat_number),
                        'price': '1000',
                        'status': ticket_status,
                    }
                )

            # Re-insert booking with tickets_data (ScyllaDB: easier than UPDATE for complex types)
            # Delete old booking first
            # ScyllaDB: With PRIMARY KEY (buyer_id, id), we must include both in WHERE clause
            execute_cql_statement(
                'DELETE FROM "booking" WHERE buyer_id = :buyer_id AND id = :booking_id',
                {'buyer_id': buyer_id, 'booking_id': booking_id},
            )

            # Re-insert with tickets_data (pass as Python list, not JSON string)
            if booking_data.get('paid_at') == 'not_null':
                execute_cql_statement(
                    """
                    INSERT INTO "booking" (id, buyer_id, event_id, section, subsection, quantity, total_price, status, seat_selection_mode, seat_positions, created_at, updated_at, paid_at, buyer_name, buyer_email, event_name, venue_name, seller_id, seller_name, tickets_data)
                    VALUES (:id, :buyer_id, :event_id, :section, :subsection, :quantity, :total_price, :status, :seat_selection_mode, :seat_positions, currenttimestamp(), currenttimestamp(), currenttimestamp(), :buyer_name, :buyer_email, :event_name, :venue_name, :seller_id, :seller_name, :tickets_data)
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
                        'seat_positions': seat_positions,
                        'buyer_name': buyer_info.get('name', f'Buyer {buyer_id}'),
                        'buyer_email': buyer_info.get('email', f'buyer{buyer_id}@test.com'),
                        'event_name': event_info.get('name', f'Event {event_id}'),
                        'venue_name': event_info.get('venue_name', 'Taipei Arena'),
                        'seller_id': seller_id,
                        'seller_name': seller_info.get('name', f'Seller {seller_id}'),
                        'tickets_data': tickets_data,  # Python list, not JSON
                    },
                )
            else:
                execute_cql_statement(
                    """
                    INSERT INTO "booking" (id, buyer_id, event_id, section, subsection, quantity, total_price, status, seat_selection_mode, seat_positions, created_at, updated_at, buyer_name, buyer_email, event_name, venue_name, seller_id, seller_name, tickets_data)
                    VALUES (:id, :buyer_id, :event_id, :section, :subsection, :quantity, :total_price, :status, :seat_selection_mode, :seat_positions, currenttimestamp(), currenttimestamp(), :buyer_name, :buyer_email, :event_name, :venue_name, :seller_id, :seller_name, :tickets_data)
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
                        'seat_positions': seat_positions,
                        'buyer_name': buyer_info.get('name', f'Buyer {buyer_id}'),
                        'buyer_email': buyer_info.get('email', f'buyer{buyer_id}@test.com'),
                        'event_name': event_info.get('name', f'Event {event_id}'),
                        'venue_name': event_info.get('venue_name', 'Taipei Arena'),
                        'seller_id': seller_id,
                        'seller_name': seller_info.get('name', f'Seller {seller_id}'),
                        'tickets_data': tickets_data,  # Python list, not JSON
                    },
                )


@given('bookings exist:')
def create_bookings(step, booking_state, execute_cql_statement):
    """Create bookings for booking_list test."""
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    booking_state['bookings'] = {}
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        booking_data = dict(zip(headers, values, strict=True))
        event_key = UUID(booking_data['event_id'])
        if 'events' in booking_state and event_key in booking_state['events']:
            event_id = booking_state['events'][event_key]['id']
        else:
            event_id = event_key
        booking_id = UUID(booking_data['id'])

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
            # Extract last byte from UUID to get numeric ID for mapping
            # Event A (019a1af7-0000-7003-0000-000000000001) -> section A, subsection 1
            # Event B (019a1af7-0000-7003-0000-000000000002) -> section B, subsection 2
            # Event C (019a1af7-0000-7003-0000-000000000003) -> section C, subsection 3
            # Event D (019a1af7-0000-7003-0000-000000000004) -> section D, subsection 4
            section_map = {
                UUID('019a1af7-0000-7003-0000-000000000001'): ('A', 1),
                UUID('019a1af7-0000-7003-0000-000000000002'): ('B', 2),
                UUID('019a1af7-0000-7003-0000-000000000003'): ('C', 3),
                UUID('019a1af7-0000-7003-0000-000000000004'): ('D', 4),
            }
            section, subsection = section_map.get(event_id, ('A', 1))
            quantity = 1
            seat_selection_mode = 'best_available'
            seat_positions = []

        # Get denormalized data for ScyllaDB
        buyer_id = UUID(booking_data['buyer_id'])
        buyer_info = booking_state.get('users', {}).get(buyer_id, {})
        event_info = booking_state.get('events', {}).get(event_id, {})
        seller_id = event_info.get('seller_id', 1)
        seller_info = booking_state.get('users', {}).get(seller_id, {})

        if booking_data.get('paid_at') == 'not_null' and booking_data['status'] == 'paid':
            execute_cql_statement(
                """
                INSERT INTO "booking" (id, buyer_id, event_id, section, subsection, quantity, total_price, status, seat_selection_mode, seat_positions, created_at, updated_at, paid_at, buyer_name, buyer_email, event_name, venue_name, seller_id, seller_name)
                VALUES (:id, :buyer_id, :event_id, :section, :subsection, :quantity, :total_price, :status, :seat_selection_mode, :seat_positions, currenttimestamp(), currenttimestamp(), currenttimestamp(), :buyer_name, :buyer_email, :event_name, :venue_name, :seller_id, :seller_name)
                """,
                {
                    'id': booking_id,
                    'buyer_id': buyer_id,
                    'event_id': event_id,
                    'section': section,
                    'subsection': subsection,
                    'quantity': quantity,
                    'total_price': int(booking_data['total_price']),
                    'status': booking_data['status'],
                    'seat_selection_mode': seat_selection_mode,
                    'seat_positions': seat_positions,
                    'buyer_name': buyer_info.get('name', f'Buyer {buyer_id}'),
                    'buyer_email': buyer_info.get('email', f'buyer{buyer_id}@test.com'),
                    'event_name': event_info.get('name', f'Event {event_id}'),
                    'venue_name': event_info.get('venue_name', 'Taipei Arena'),
                    'seller_id': seller_id,
                    'seller_name': seller_info.get('name', f'Seller {seller_id}'),
                },
            )
        else:
            execute_cql_statement(
                """
                INSERT INTO "booking" (id, buyer_id, event_id, section, subsection, quantity, total_price, status, seat_selection_mode, seat_positions, created_at, updated_at, buyer_name, buyer_email, event_name, venue_name, seller_id, seller_name)
                VALUES (:id, :buyer_id, :event_id, :section, :subsection, :quantity, :total_price, :status, :seat_selection_mode, :seat_positions, currenttimestamp(), currenttimestamp(), :buyer_name, :buyer_email, :event_name, :venue_name, :seller_id, :seller_name)
                """,
                {
                    'id': booking_id,
                    'buyer_id': buyer_id,
                    'event_id': event_id,
                    'section': section,
                    'subsection': subsection,
                    'quantity': quantity,
                    'total_price': int(booking_data['total_price']),
                    'status': booking_data['status'],
                    'seat_selection_mode': seat_selection_mode,
                    'seat_positions': seat_positions,
                    'buyer_name': buyer_info.get('name', f'Buyer {buyer_id}'),
                    'buyer_email': buyer_info.get('email', f'buyer{buyer_id}@test.com'),
                    'event_name': event_info.get('name', f'Event {event_id}'),
                    'venue_name': event_info.get('venue_name', 'Taipei Arena'),
                    'seller_id': seller_id,
                    'seller_name': seller_info.get('name', f'Seller {seller_id}'),
                },
            )
        booking_state['bookings'][UUID(booking_data['id'])] = {'id': booking_id}
    # Note: ScyllaDB uses timestamp-based ID generation, no sequence management needed

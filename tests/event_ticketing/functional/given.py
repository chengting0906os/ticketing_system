import json

import bcrypt
from fastapi.testclient import TestClient
from pytest_bdd import given

from src.shared.constant.route_constant import (
    EVENT_BASE,
    EVENT_TICKETS_CREATE,
    EVENT_TICKETS_RESERVE,
)
from tests.shared.utils import create_user, extract_table_data, login_user
from tests.util_constant import (
    BUYER1_EMAIL,
    DEFAULT_PASSWORD,
    EMPTY_LIST_SELLER_EMAIL,
    EMPTY_LIST_SELLER_NAME,
    LIST_SELLER_EMAIL,
    LIST_TEST_SELLER_NAME,
    SELLER1_EMAIL,
    SELLER2_EMAIL,
    TEST_SELLER_EMAIL,
    TEST_SELLER_NAME,
)


@given('a event exists')
def _(step, client: TestClient, event_state):
    row_data = extract_table_data(step)
    seller_email = TEST_SELLER_EMAIL
    create_user(client, seller_email, DEFAULT_PASSWORD, TEST_SELLER_NAME, 'seller')
    login_user(client, seller_email, DEFAULT_PASSWORD)
    request_data = {
        'name': row_data['name'],
        'description': row_data['description'],
        'is_active': row_data['is_active'].lower() == 'true',
    }
    from tests.event_test_constants import DEFAULT_SEATING_CONFIG_JSON, DEFAULT_VENUE_NAME
    from tests.shared.utils import parse_seating_config

    if 'venue_name' in row_data:
        request_data['venue_name'] = row_data['venue_name']
    else:
        request_data['venue_name'] = DEFAULT_VENUE_NAME

    if 'seating_config' in row_data:
        request_data['seating_config'] = parse_seating_config(row_data['seating_config'])
    else:
        request_data['seating_config'] = parse_seating_config(DEFAULT_SEATING_CONFIG_JSON)
    response = client.post(EVENT_BASE, json=request_data)
    assert response.status_code == 201, f'Failed to create event: {response.text}'
    event_data = response.json()
    event_state['event_id'] = event_data['id']
    event_state['original_event'] = event_data
    event_state['request_data'] = request_data


@given('a seller with events:')
def create_seller_with_events(step, client: TestClient, event_state, execute_sql_statement):
    import json

    created_user = create_user(
        client, LIST_SELLER_EMAIL, DEFAULT_PASSWORD, LIST_TEST_SELLER_NAME, 'seller'
    )
    seller_id = created_user['id'] if created_user else 1
    event_state['seller_id'] = seller_id
    event_state['created_events'] = []
    login_user(client, LIST_SELLER_EMAIL, DEFAULT_PASSWORD)
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        event_data = dict(zip(headers, values, strict=True))
        request_json = {
            'name': event_data['name'],
            'description': event_data['description'],
            'is_active': event_data['is_active'].lower() == 'true',
        }
        if 'venue_name' in event_data:
            request_json['venue_name'] = event_data['venue_name']
        if 'seating_config' in event_data:
            request_json['seating_config'] = json.loads(event_data['seating_config'])
        create_response = client.post(EVENT_BASE, json=request_json)
        if create_response.status_code == 201:
            created_event = create_response.json()
            event_id = created_event['id']
            if event_data['status'] != 'available':
                execute_sql_statement(
                    'UPDATE event SET status = :status WHERE id = :id',
                    {'status': event_data['status'], 'id': event_id},
                )
                created_event['status'] = event_data['status']
            event_state['created_events'].append(created_event)


@given('no available events exist')
def create_no_available_events(step, client: TestClient, event_state, execute_sql_statement):
    import json

    created_user = create_user(
        client, EMPTY_LIST_SELLER_EMAIL, DEFAULT_PASSWORD, EMPTY_LIST_SELLER_NAME, 'seller'
    )
    seller_id = created_user['id'] if created_user else 1
    event_state['seller_id'] = seller_id
    event_state['created_events'] = []
    login_user(client, EMPTY_LIST_SELLER_EMAIL, DEFAULT_PASSWORD)
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        event_data = dict(zip(headers, values, strict=True))
        request_json = {
            'name': event_data['name'],
            'description': event_data['description'],
            'is_active': event_data['is_active'].lower() == 'true',
        }
        if 'venue_name' in event_data:
            request_json['venue_name'] = event_data['venue_name']
        if 'seating_config' in event_data:
            request_json['seating_config'] = json.loads(event_data['seating_config'])
        create_response = client.post(EVENT_BASE, json=request_json)
        if create_response.status_code == 201:
            created_event = create_response.json()
            event_id = created_event['id']
            execute_sql_statement(
                'UPDATE event SET status = :status WHERE id = :id',
                {'status': event_data['status'], 'id': event_id},
            )
            created_event['status'] = event_data['status']
            event_state['created_events'].append(created_event)


@given('an event exists with:')
def event_exists(step, execute_sql_statement):
    event_data = extract_table_data(step)
    event_id = int(event_data['event_id'])
    expected_seller_id = int(event_data['seller_id'])

    # Use the seller_id as provided in the test scenario
    # The BDD steps should ensure the seller exists before the event is created
    actual_seller_id = expected_seller_id

    # Default config for all events (A-E sections with 2 subsections each, 250 per subsection)
    seating_config = {
        'sections': [
            {
                'name': 'A',
                'subsections': [
                    {'number': 1, 'rows': 10, 'seats_per_row': 25},
                    {'number': 2, 'rows': 10, 'seats_per_row': 25},
                ],
            },
            {
                'name': 'B',
                'subsections': [
                    {'number': 1, 'rows': 10, 'seats_per_row': 25},
                    {'number': 2, 'rows': 10, 'seats_per_row': 25},
                ],
            },
            {
                'name': 'C',
                'subsections': [
                    {'number': 1, 'rows': 10, 'seats_per_row': 25},
                    {'number': 2, 'rows': 10, 'seats_per_row': 25},
                ],
            },
            {
                'name': 'D',
                'subsections': [
                    {'number': 1, 'rows': 10, 'seats_per_row': 25},
                    {'number': 2, 'rows': 10, 'seats_per_row': 25},
                ],
            },
            {
                'name': 'E',
                'subsections': [
                    {'number': 1, 'rows': 10, 'seats_per_row': 25},
                    {'number': 2, 'rows': 10, 'seats_per_row': 25},
                ],
            },
        ]
    }

    event_info = {
        'name': 'Test Event',
        'description': 'Test Description',
        'venue_name': 'Large Arena',
        'seating_config': json.dumps(seating_config),
    }

    # Insert event with specific ID
    execute_sql_statement(
        """
        INSERT INTO event (id, name, description, seller_id, is_active, status, venue_name, seating_config)
        VALUES (:id, :name, :description, :seller_id, :is_active, :status, :venue_name, :seating_config)
        ON CONFLICT (id) DO NOTHING
        """,
        {
            'id': event_id,
            'name': event_info['name'],
            'description': event_info['description'],
            'seller_id': actual_seller_id,
            'is_active': True,
            'status': 'available',
            'venue_name': event_info['venue_name'],
            'seating_config': event_info['seating_config'],
        },
    )


@given('another seller and event exist with:')
def other_seller_event_exists(step, execute_sql_statement):
    """Create another seller and their event."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])
    seller_id = int(data['seller_id'])

    # Create seller2 through SQL (for this test scenario we need a different seller)
    hashed_password = bcrypt.hashpw(DEFAULT_PASSWORD.encode('utf-8'), bcrypt.gensalt()).decode(
        'utf-8'
    )

    execute_sql_statement(
        """
        INSERT INTO "user" (id, email, hashed_password, name, role, is_active, is_superuser, is_verified)
        VALUES (:id, :email, :hashed_password, :name, :role, true, false, true)
        ON CONFLICT (id) DO NOTHING
        """,
        {
            'id': seller_id,
            'email': SELLER2_EMAIL,
            'hashed_password': hashed_password,
            'name': 'Test Seller 2',
            'role': 'seller',
        },
    )

    # Create event owned by seller2
    execute_sql_statement(
        """
        INSERT INTO event (id, name, description, seller_id, is_active, status, venue_name, seating_config)
        VALUES (:id, :name, :description, :seller_id, :is_active, :status, :venue_name, :seating_config)
        ON CONFLICT (id) DO NOTHING
        """,
        {
            'id': event_id,
            'name': 'Test Event 2',
            'description': 'Test Description 2',
            'seller_id': seller_id,
            'is_active': True,
            'status': 'available',
            'venue_name': 'Another Arena',
            'seating_config': json.dumps(
                {
                    'sections': [
                        {
                            'name': 'A',
                            'subsections': [
                                {'number': 1, 'rows': 10, 'seats_per_row': 20},
                                {'number': 2, 'rows': 10, 'seats_per_row': 20},
                            ],
                        },
                        {
                            'name': 'B',
                            'subsections': [
                                {'number': 1, 'rows': 10, 'seats_per_row': 20},
                                {'number': 2, 'rows': 10, 'seats_per_row': 20},
                            ],
                        },
                        {
                            'name': 'C',
                            'subsections': [
                                {'number': 1, 'rows': 10, 'seats_per_row': 20},
                                {'number': 2, 'rows': 10, 'seats_per_row': 20},
                            ],
                        },
                        {
                            'name': 'D',
                            'subsections': [
                                {'number': 1, 'rows': 10, 'seats_per_row': 20},
                                {'number': 2, 'rows': 10, 'seats_per_row': 20},
                            ],
                        },
                        {
                            'name': 'E',
                            'subsections': [
                                {'number': 1, 'rows': 10, 'seats_per_row': 20},
                                {'number': 2, 'rows': 10, 'seats_per_row': 20},
                            ],
                        },
                    ]
                }
            ),
        },
    )


@given('all tickets exist with:')
def tickets_already_exist(step, client, execute_sql_statement):
    """Create all tickets for an event (setup for duplicate creation test)."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])
    price = int(data['price'])

    # Look up who owns this event to get their email
    result = execute_sql_statement(
        'SELECT u.email FROM event e JOIN "user" u ON e.seller_id = u.id WHERE e.id = :event_id',
        {'event_id': event_id},
        fetch=True,
    )

    if result:
        seller_email = result[0]['email']
    else:
        seller_email = SELLER1_EMAIL  # fallback

    # Login as the appropriate seller
    login_user(client, seller_email, DEFAULT_PASSWORD)

    # Create tickets
    response = client.post(EVENT_TICKETS_CREATE.format(event_id=event_id), json={'price': price})
    assert response.status_code == 201


@given('tickets exist for events:')
def tickets_exist_for_events(step, execute_sql_statement):
    """Create tickets for events."""
    rows = step.data_table.rows
    # Skip the header row
    for row in rows[1:]:
        event_id = int(row.cells[0].value)
        ticket_count = int(row.cells[1].value)
        price = int(row.cells[2].value)
        status = row.cells[3].value

        # Create tickets using the seating configuration
        for i in range(ticket_count):
            execute_sql_statement(
                """
                INSERT INTO ticket (event_id, section, subsection, row_number, seat_number, price, status)
                VALUES (:event_id, 'A', 1, :row_number, :seat_number, :price, :status)
                """,
                {
                    'event_id': event_id,
                    'row_number': (i // 10) + 1,
                    'seat_number': (i % 10) + 1,
                    'price': price,
                    'status': status,
                },
            )


@given('tickets are reserved:')
def tickets_are_reserved(step, client, execute_sql_statement):
    """Reserve tickets for testing availability."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])
    _ = int(data['buyer_id'])
    ticket_count = int(data['ticket_count'])

    # Login as buyer to reserve tickets
    login_user(client, BUYER1_EMAIL, DEFAULT_PASSWORD)

    # Reserve the specified number of tickets
    response = client.post(
        EVENT_TICKETS_RESERVE.format(event_id=event_id), json={'ticket_count': ticket_count}
    )
    assert response.status_code == 200, f'Failed to reserve tickets: {response.text}'


@given('tickets are sold:')
def tickets_are_sold(step, execute_sql_statement):
    """Mark tickets as sold for testing availability."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])
    ticket_count = int(data['ticket_count'])

    # Update the first available tickets to sold status
    execute_sql_statement(
        """
        UPDATE ticket SET status = 'sold'
        WHERE id IN (
            SELECT id FROM ticket
            WHERE event_id = :event_id AND status = 'available'
            ORDER BY section, subsection, row_number, seat_number
            LIMIT :ticket_count
        )
        """,
        {
            'event_id': event_id,
            'ticket_count': ticket_count,
        },
    )


@given('an event exists with price groups:')
def event_exists_with_price_groups(step, execute_sql_statement):
    """Create event with price group structure for status testing."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])
    seller_id = int(data['seller_id'])

    # Ensure seller exists first
    hashed_password = bcrypt.hashpw(DEFAULT_PASSWORD.encode('utf-8'), bcrypt.gensalt()).decode(
        'utf-8'
    )

    execute_sql_statement(
        """
        INSERT INTO "user" (id, email, hashed_password, name, role, is_active, is_superuser, is_verified)
        VALUES (:id, :email, :hashed_password, :name, :role, true, false, true)
        ON CONFLICT (id) DO NOTHING
        """,
        {
            'id': seller_id,
            'email': SELLER1_EMAIL,
            'hashed_password': hashed_password,
            'name': 'Test Seller1',
            'role': 'seller',
        },
    )

    # Price group seating configuration
    # 8800: subsections 1-4 (100 seats each)
    # 8000: subsections 5-6 (100 seats each)
    # 7500: subsections 7-10 (100 seats each)
    seating_config = {
        'sections': [
            {
                'name': 'A',
                'subsections': [
                    {'number': 1, 'rows': 10, 'seats_per_row': 10, 'price': 8800},
                    {'number': 2, 'rows': 10, 'seats_per_row': 10, 'price': 8800},
                    {'number': 3, 'rows': 10, 'seats_per_row': 10, 'price': 8800},
                    {'number': 4, 'rows': 10, 'seats_per_row': 10, 'price': 8800},
                    {'number': 5, 'rows': 10, 'seats_per_row': 10, 'price': 8000},
                    {'number': 6, 'rows': 10, 'seats_per_row': 10, 'price': 8000},
                    {'number': 7, 'rows': 10, 'seats_per_row': 10, 'price': 7500},
                    {'number': 8, 'rows': 10, 'seats_per_row': 10, 'price': 7500},
                    {'number': 9, 'rows': 10, 'seats_per_row': 10, 'price': 7500},
                    {'number': 10, 'rows': 10, 'seats_per_row': 10, 'price': 7500},
                ],
            },
        ]
    }

    event_info = {
        'name': 'Price Group Event',
        'description': 'Event with price groups for status testing',
        'venue_name': 'Status Arena',
        'seating_config': json.dumps(seating_config),
    }

    # Insert event with specific ID
    execute_sql_statement(
        """
        INSERT INTO event (id, name, description, seller_id, is_active, status, venue_name, seating_config)
        VALUES (:id, :name, :description, :seller_id, :is_active, :status, :venue_name, :seating_config)
        ON CONFLICT (id) DO NOTHING
        """,
        {
            'id': event_id,
            'name': event_info['name'],
            'description': event_info['description'],
            'seller_id': seller_id,
            'is_active': True,
            'status': 'available',
            'venue_name': event_info['venue_name'],
            'seating_config': event_info['seating_config'],
        },
    )


@given('all tickets exist for price groups with:')
def all_tickets_exist_for_price_groups(step, client):
    """Create all tickets for price group event."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])

    # Login as seller to create tickets
    login_user(client, SELLER1_EMAIL, DEFAULT_PASSWORD)

    # Create tickets for the price group event
    response = client.post(EVENT_TICKETS_CREATE.format(event_id=event_id), json={'price': 1000})
    assert response.status_code == 201


@given('some tickets are reserved:')
def some_tickets_are_reserved_for_subsection(step, client):
    """Reserve specific tickets in a subsection."""
    rows = step.data_table.rows[1:]  # Skip header
    for row in rows:
        event_id = int(row.cells[0].value)
        _ = int(row.cells[1].value)
        subsection = int(row.cells[2].value)
        ticket_count = int(row.cells[3].value)

        # Login as buyer
        login_user(client, BUYER1_EMAIL, DEFAULT_PASSWORD)

        # Reserve tickets from specific subsection
        response = client.post(
            EVENT_TICKETS_RESERVE.format(event_id=event_id),
            json={'ticket_count': ticket_count, 'section': 'A', 'subsection': subsection},
        )
        assert response.status_code == 200, f'Failed to reserve tickets: {response.text}'


@given('some tickets are sold:')
def some_tickets_are_sold_for_subsection(step, execute_sql_statement):
    """Mark specific tickets as sold in a subsection."""
    rows = step.data_table.rows[1:]  # Skip header
    for row in rows:
        event_id = int(row.cells[0].value)
        subsection = int(row.cells[1].value)
        ticket_count = int(row.cells[2].value)

        # Update tickets to sold status (PostgreSQL compatible)
        execute_sql_statement(
            """
            UPDATE ticket
            SET status = 'sold'
            WHERE id IN (
                SELECT id FROM ticket
                WHERE event_id = :event_id
                    AND subsection = :subsection
                    AND status = 'available'
                ORDER BY id
                LIMIT :ticket_count
            )
            """,
            {
                'event_id': event_id,
                'subsection': subsection,
                'ticket_count': ticket_count,
            },
        )

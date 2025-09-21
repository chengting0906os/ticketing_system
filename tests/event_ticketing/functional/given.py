import json

from fastapi.testclient import TestClient
from pytest_bdd import given

from src.shared.constant.route_constant import (
    EVENT_BASE,
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
    # Now includes price information for automatic ticket creation
    seating_config = {
        'sections': [
            {
                'name': 'A',
                'price': 3000,  # Default price for compatibility with tests
                'subsections': [
                    {'number': 1, 'rows': 5, 'seats_per_row': 10},
                    {'number': 2, 'rows': 5, 'seats_per_row': 10},
                ],
            },
            {
                'name': 'B',
                'price': 2000,
                'subsections': [
                    {'number': 1, 'rows': 5, 'seats_per_row': 10},
                ],
            },
            {
                'name': 'C',
                'price': 1500,
                'subsections': [
                    {'number': 1, 'rows': 5, 'seats_per_row': 10},
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

    # Create tickets manually since we're bypassing the CreateEventUseCase
    # Generate all tickets based on seating configuration
    for section in seating_config['sections']:
        section_name = section['name']
        section_price = section['price']
        subsections = section['subsections']

        for subsection in subsections:
            subsection_number = subsection['number']
            rows = subsection['rows']
            seats_per_row = subsection['seats_per_row']

            # Generate tickets for each seat
            for row in range(1, rows + 1):
                for seat in range(1, seats_per_row + 1):
                    execute_sql_statement(
                        """
                        INSERT INTO ticket (event_id, section, subsection, row_number, seat_number, price, status)
                        VALUES (:event_id, :section, :subsection, :row_number, :seat_number, :price, :status)
                        ON CONFLICT DO NOTHING
                        """,
                        {
                            'event_id': event_id,
                            'section': section_name,
                            'subsection': subsection_number,
                            'row_number': row,
                            'seat_number': seat,
                            'price': section_price,
                            'status': 'available',
                        },
                    )


@given('all tickets exist with:')
def tickets_already_exist(step, client, execute_sql_statement):
    data = extract_table_data(step)
    event_id = int(data['event_id'])
    price = int(data['price'])
    seller_email = SELLER1_EMAIL

    # First check if the event exists
    event_check = client.get(f'/api/event/{event_id}')
    print(f'DEBUG: Event {event_id} check status: {event_check.status_code}')
    if event_check.status_code != 200:
        print(f'DEBUG: Event check response: {event_check.text}')
        raise AssertionError(f'Event {event_id} does not exist')

    # Use the subsection endpoint to verify tickets exist
    login_user(client=client, email=seller_email, password=DEFAULT_PASSWORD)

    # Test with section A, subsection 1 to verify tickets exist
    from src.shared.constant.route_constant import EVENT_TICKETS_BY_SUBSECTION

    test_url = EVENT_TICKETS_BY_SUBSECTION.format(event_id=event_id, section='A', subsection=1)
    response = client.get(test_url)

    if response.status_code != 200:
        print(f'DEBUG: Failed to get tickets from {test_url} with status {response.status_code}')
        print(f'DEBUG: Response: {response.text}')
        raise AssertionError(f'Failed to verify tickets exist for event {event_id}')

    # Verify tickets exist and have the expected price
    tickets_data = response.json()
    if tickets_data['total_count'] == 0:
        raise AssertionError(
            f'No tickets found for event {event_id} section A subsection 1. Tickets should be created automatically with events.'
        )

    # Verify at least some tickets have the expected price
    tickets_with_price = [t for t in tickets_data['tickets'] if t['price'] == price]
    if not tickets_with_price:
        print(f'DEBUG: No tickets found with price {price}')
        print(
            f'DEBUG: Available ticket prices: {list(set(t["price"] for t in tickets_data["tickets"]))}'
        )
        raise AssertionError(f'No tickets found with expected price {price}')


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

import os
from unittest.mock import patch

from fastapi.testclient import TestClient
import orjson
from pytest_bdd import given

from src.platform.constant.route_constant import (
    EVENT_BASE,
)
from test.event_test_constants import DEFAULT_SEATING_CONFIG_JSON, DEFAULT_VENUE_NAME
from test.kvrocks_test_client import kvrocks_test_client
from test.shared.utils import create_user, extract_table_data, login_user, parse_seating_config
from test.util_constant import (
    DEFAULT_PASSWORD,
    EMPTY_LIST_SELLER_EMAIL,
    EMPTY_LIST_SELLER_NAME,
    LIST_SELLER_EMAIL,
    LIST_TEST_SELLER_NAME,
    TEST_SELLER_EMAIL,
    TEST_SELLER_NAME,
)


@given('an event exists with seating config:')
def event_exists_with_seating_config(step, client: TestClient, event_state, execute_sql_statement):
    """Create an event with specific seating configuration for get event tests."""
    row_data = extract_table_data(step)
    seller_email = TEST_SELLER_EMAIL

    # Check if seller exists, create if not
    existing_seller = execute_sql_statement(
        'SELECT id FROM "user" WHERE email = :email',
        {'email': seller_email},
        fetch=True,
    )

    if not existing_seller:
        create_user(client, seller_email, DEFAULT_PASSWORD, TEST_SELLER_NAME, 'seller')

    login_user(client, seller_email, DEFAULT_PASSWORD)

    # Prepare request data
    request_data = {
        'name': row_data['name'],
        'description': row_data['description'],
        'venue_name': row_data['venue_name'],
        'seating_config': parse_seating_config(row_data['seating_config']),
        'is_active': True,
    }

    # Create the event
    response = client.post(EVENT_BASE, json=request_data)
    assert response.status_code == 201, f'Failed to create event: {response.text}'

    event_data = response.json()
    event_state['event_id'] = event_data['id']
    event_state['original_event'] = event_data
    event_state['request_data'] = request_data


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
            request_json['seating_config'] = orjson.loads(event_data['seating_config'])
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
            request_json['seating_config'] = orjson.loads(event_data['seating_config'])
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

    # Default config for all events (A-C sections = 4 subsections total)
    # Now includes price information for automatic ticket creation
    seating_config = {
        'sections': [
            {
                'name': 'A',
                'price': 3000,  # Default price for compatibility with test
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
        'seating_config': orjson.dumps(seating_config).decode(),
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

    # Create tickets manually since we're bypassing the CreateEventAndTicketsUseCase
    # Generate all tickets based on seating configuration
    sections_list: list[dict] = seating_config['sections']
    for section in sections_list:
        section_name: str = section['name']
        section_price: int = section['price']
        subsections: list[dict] = section['subsections']

        for subsection in subsections:
            subsection_number: int = subsection['number']
            rows: int = subsection['rows']
            seats_per_row: int = subsection['seats_per_row']

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

    # Initialize Redis configuration for each subsection (critical for SSE test)
    client = kvrocks_test_client.connect()

    # Get key prefix for test isolation (same as SeatStateHandlerImpl)
    key_prefix = os.getenv('KVROCKS_KEY_PREFIX', '')

    # Clean up any existing Kvrocks data for this event to ensure test isolation
    # This prevents data pollution from previous test that used the same event_id
    # ✨ REMOVED: event_sections index (can query from event_state JSON)
    event_state_key = f'{key_prefix}event_state:{event_id}'

    # Try to read existing sections from event_state for cleanup
    try:
        config_json_raw = client.get(event_state_key)
        if config_json_raw:
            config_json_str = (
                config_json_raw.decode()
                if isinstance(config_json_raw, bytes)
                else str(config_json_raw)
            )
            existing_config = orjson.loads(config_json_str)
            for section_id in existing_config.get('sections', {}).keys():
                bf_key = f'{key_prefix}seats_bf:{event_id}:{section_id}'
                client.delete(bf_key)
    except Exception:
        pass  # Ignore errors during cleanup

    # Delete event-level keys
    client.delete(event_state_key)

    # Build unified event_state JSON with event_stats at top level
    event_state: dict = {
        'event_stats': {  # ✨ NEW: Event-level stats in JSON (no separate Hash)
            'available': 0,
            'reserved': 0,
            'sold': 0,
            'total': 0,
            'updated_at': int(1759562700),
        },
        'sections': {},
    }

    # Track total seats across all sections
    event_total_seats = 0

    sections_list2: list[dict] = seating_config['sections']  # type: ignore
    for section in sections_list2:
        section_name: str = section['name']
        section_price: int = section['price']

        # Create section if not exists (price stored at section level)
        if section_name not in event_state['sections']:
            event_state['sections'][section_name] = {
                'price': section_price,  # ✨ Price at section level (not duplicated)
                'subsections': {},
            }

        subsections_list: list[dict] = section['subsections']  # type: ignore
        for subsection in subsections_list:
            subsection_number: int = subsection['number']
            rows: int = subsection['rows']
            seats_per_row: int = subsection['seats_per_row']
            subsection_num_str = str(subsection_number)

            # ✨ REMOVED: event_sections index (can query from event_state JSON)

            # Build event_state JSON structure (hierarchical - stats at subsection level)
            total_seats = rows * seats_per_row
            event_state['sections'][section_name]['subsections'][subsection_num_str] = {
                'rows': rows,
                'seats_per_row': seats_per_row,
                'stats': {  # ✨ Stats at subsection level (replaces section_stats Hash)
                    'available': total_seats,
                    'reserved': 0,
                    'sold': 0,
                    'total': total_seats,
                    'updated_at': int(1759562700),  # Fixed timestamp for test
                },
            }

            # Aggregate for event-level stats
            event_total_seats += total_seats

            # ✨ REMOVED: section_stats Hash (stats now in event_state JSON)

    # Update event-level stats with aggregated totals
    event_state['event_stats']['available'] = event_total_seats
    event_state['event_stats']['total'] = event_total_seats

    # Write unified event config as JSON (single key per event)
    event_state_key = f'{key_prefix}event_state:{event_id}'
    event_state_json = orjson.dumps(event_state).decode()

    try:
        # Try JSON.SET first (Kvrocks native JSON support)
        client.execute_command('JSON.SET', event_state_key, '$', event_state_json)
    except Exception:
        # Fallback: Store as regular string if JSON commands not supported
        client.set(event_state_key, event_state_json)

    # Verify Kvrocks data is actually written (prevent race conditions in parallel tests)
    import time

    max_retries = 10
    for attempt in range(max_retries):
        # Check event_state exists
        # ✨ REMOVED: event_sections index check (can query from event_state JSON)
        if client.exists(event_state_key):
            break
        if attempt < max_retries - 1:
            time.sleep(0.15)
    else:
        raise RuntimeError(
            f'Failed to initialize Kvrocks data for event {event_id} after {max_retries} attempts'
        )


@given('Kvrocks seat initialization will fail')
def mock_kvrocks_failure(request):
    """
    Mock Kvrocks initialization to fail, testing compensating transaction.

    This simulates a distributed system failure scenario where:
    1. PostgreSQL commits successfully
    2. Kvrocks initialization fails
    3. Compensating transaction should delete PostgreSQL data
    """

    async def failing_init(*args, **kwargs):
        """Mock initialization that always fails"""
        return {
            'success': False,
            'error': 'Simulated Kvrocks connection failure',
            'total_seats': 0,
            'sections_count': 0,
        }

    # Patch the init_state_handler to return failure
    mock_patcher = patch(
        'src.service.ticketing.driven_adapter.state.init_event_and_tickets_state_handler_impl'
        '.InitEventAndTicketsStateHandlerImpl.initialize_seats_from_config',
        new=failing_init,
    )

    mock_patcher.start()

    # Register cleanup to stop the patcher after test
    request.addfinalizer(mock_patcher.stop)

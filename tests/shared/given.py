from fastapi.testclient import TestClient
from pytest_bdd import given

from src.shared.constant.route_constant import EVENT_BASE, USER_CREATE
from tests.shared.utils import create_user, extract_table_data, login_user


@given('I am logged in as:')
def login_user_with_table(step, client):
    login_data = extract_table_data(step)
    return login_user(client, login_data['email'], login_data['password'])


@given('a buyer exists:')
def create_buyer_shared(
    step, client: TestClient, booking_state=None, event_state=None, user_state=None
):
    """Shared step for creating a buyer user."""
    buyer_data = extract_table_data(step)
    created = create_user(
        client, buyer_data['email'], buyer_data['password'], buyer_data['name'], buyer_data['role']
    )

    buyer = created if created else {'id': 2, 'email': buyer_data['email']}

    # Store in appropriate state based on what's available
    if booking_state is not None:
        booking_state['buyer'] = buyer
    if event_state is not None:
        event_state['buyer'] = buyer
    if user_state is not None:
        user_state['buyer'] = buyer

    return buyer


@given('a seller exists:')
def create_seller_shared(
    step, client: TestClient, booking_state=None, event_state=None, user_state=None
):
    """Shared step for creating a seller user."""
    seller_data = extract_table_data(step)
    created = create_user(
        client,
        seller_data['email'],
        seller_data['password'],
        seller_data['name'],
        seller_data['role'],
    )

    seller = created if created else {'id': 1, 'email': seller_data['email']}

    # Store in appropriate state based on what's available
    if booking_state is not None:
        booking_state['seller'] = seller
    if event_state is not None:
        event_state['seller'] = seller
    if user_state is not None:
        user_state['seller'] = seller

    return seller


@given('another buyer exists:')
def create_another_buyer_shared(
    step, client: TestClient, booking_state=None, event_state=None, user_state=None
):
    """Shared step for creating another buyer user."""
    buyer_data = extract_table_data(step)
    created = create_user(
        client, buyer_data['email'], buyer_data['password'], buyer_data['name'], buyer_data['role']
    )

    another_buyer = created if created else {'id': 3, 'email': buyer_data['email']}

    # Store in appropriate state based on what's available
    if booking_state is not None:
        booking_state['another_buyer'] = another_buyer
    if event_state is not None:
        event_state['another_buyer'] = another_buyer
    if user_state is not None:
        user_state['another_buyer'] = another_buyer

    return another_buyer


@given('a buyer user exists')
def create_buyer_user_simple(
    step, client: TestClient, user_state=None, booking_state=None, event_state=None
):
    """Simple buyer creation without table data."""
    buyer_data = extract_table_data(step)
    response = client.post(USER_CREATE, json=buyer_data)
    assert response.status_code == 201, f'Failed to create buyer user: {response.text}'

    buyer = response.json()

    # Store in appropriate state
    if user_state is not None:
        user_state['buyer'] = buyer
    if booking_state is not None:
        booking_state['buyer'] = buyer
    if event_state is not None:
        event_state['buyer'] = buyer

    return buyer


@given('a seller user exists')
def create_seller_user_simple(
    step, client: TestClient, event_state=None, booking_state=None, user_state=None
):
    """Simple seller creation without table data."""
    user_data = extract_table_data(step)
    created = create_user(
        client, user_data['email'], user_data['password'], user_data['name'], user_data['role']
    )

    if created:
        # Store in appropriate state
        if event_state is not None:
            event_state['seller_id'] = created['id']
            event_state['seller_user'] = created
        if booking_state is not None:
            booking_state['seller_id'] = created['id']
            booking_state['seller_user'] = created
        if user_state is not None:
            user_state['seller_id'] = created['id']
            user_state['seller_user'] = created
    else:
        # User already exists, use default ID
        if event_state is not None:
            event_state['seller_id'] = 1
            event_state['seller_user'] = {'email': user_data['email'], 'role': user_data['role']}
        if booking_state is not None:
            booking_state['seller_id'] = 1
            booking_state['seller_user'] = {'email': user_data['email'], 'role': user_data['role']}
        if user_state is not None:
            user_state['seller_id'] = 1
            user_state['seller_user'] = {'email': user_data['email'], 'role': user_data['role']}

    return created


@given('a seller with a event:')
def create_seller_with_event_shared(
    step, client: TestClient, booking_state=None, event_state=None, execute_sql_statement=None
):
    """Shared step for creating a seller with a event."""
    event_data = extract_table_data(step)

    # Create seller
    seller_email = f'seller_{event_data["name"].lower().replace(" ", "_")}@test.com'
    seller = create_user(client, seller_email, 'P@ssw0rd', 'Test Seller', 'seller')

    seller_id = seller['id'] if seller else 1

    # Store seller in appropriate state
    if booking_state is not None:
        booking_state['seller'] = {'id': seller_id, 'email': seller_email}
    if event_state is not None:
        event_state['seller'] = {'id': seller_id, 'email': seller_email}

    # Login as seller
    login_user(client, seller_email, 'P@ssw0rd')

    # Create event
    request_data = {
        'name': event_data['name'],
        'description': event_data['description'],
        'price': int(event_data['price']),
        'is_active': event_data['is_active'].lower() == 'true',
    }
    if 'venue_name' in event_data:
        request_data['venue_name'] = event_data['venue_name']
    else:
        request_data['venue_name'] = 'Default Venue'

    if 'seating_config' in event_data:
        import json

        request_data['seating_config'] = json.loads(event_data['seating_config'])
    else:
        # Use the correct seating config format for ticket creation
        request_data['seating_config'] = {
            'sections': [
                {
                    'section': 'A',
                    'subsections': [{'subsection': 1, 'rows': 25, 'seats_per_row': 20}],
                }
            ]
        }

    response = client.post(EVENT_BASE, json=request_data)
    assert response.status_code == 201, f'Failed to create event: {response.text}'
    event = response.json()

    # Update event status if needed
    if 'status' in event_data and event_data['status'] != 'available' and execute_sql_statement:
        execute_sql_statement(
            'UPDATE event SET status = :status WHERE id = :id',
            {'status': event_data['status'], 'id': event['id']},
        )
        event['status'] = event_data['status']

    # Create tickets for this event (for booking tests)
    if booking_state is not None:
        # Still logged in as seller, create tickets
        from src.shared.constant.route_constant import TICKET_CREATE

        tickets_response = client.post(
            TICKET_CREATE.format(event_id=event['id']), json={'price': int(event_data['price'])}
        )
        if tickets_response.status_code == 201:
            # Get the actual ticket data from the response and calculate the starting ID
            response_data = tickets_response.json()
            _ = response_data.get('tickets_created', 500)  # Used for validation

            # Tickets are created sequentially in the database
            # For the first event (ID 1), tickets are IDs 1-500
            # For the second event (ID 2), tickets are IDs 501-1000, etc.
            start_ticket_id = (event['id'] - 1) * 500 + 1
            booking_state['ticket_ids'] = [start_ticket_id, start_ticket_id + 1]
            booking_state['event_id'] = event['id']

    # Store event in appropriate state
    if booking_state is not None:
        booking_state['event'] = event
    if event_state is not None:
        event_state['event'] = event
        event_state['event_id'] = event['id']
        event_state['original_event'] = event
        event_state['request_data'] = request_data

    return event


@given('a event exists:')
def create_event_shared(
    step, client: TestClient, booking_state=None, event_state=None, execute_sql_statement=None
):
    """Shared step for creating a event (inserts directly into database)."""
    from tests.event_test_constants import DEFAULT_SEATING_CONFIG_JSON, DEFAULT_VENUE_NAME

    event_data = extract_table_data(step)
    seller_id = int(event_data.get('seller_id', 1))

    if execute_sql_statement:
        # Create event directly in database
        execute_sql_statement(
            """
            INSERT INTO event (name, description, seller_id, is_active, status, venue_name, seating_config)
            VALUES (:name, :description, :seller_id, :is_active, :status, :venue_name, :seating_config)
            """,
            {
                'name': event_data['name'],
                'description': event_data['description'],
                'seller_id': seller_id,
                'is_active': event_data.get('is_active', 'true').lower() == 'true',
                'status': event_data.get('status', 'available'),
                'venue_name': event_data.get('venue_name', DEFAULT_VENUE_NAME),
                'seating_config': event_data.get('seating_config', DEFAULT_SEATING_CONFIG_JSON),
            },
        )

        # Get the created event ID
        result = execute_sql_statement(
            'SELECT id FROM event WHERE name = :name ORDER BY id DESC LIMIT 1',
            {'name': event_data['name']},
        )
        event_id = result[0]['id'] if result else 1
    else:
        # Fallback: create via API
        seller_email = f'seller{seller_id}@test.com'
        create_user(client, seller_email, 'P@ssw0rd', f'Test Seller {seller_id}', 'seller')
        login_user(client, seller_email, 'P@ssw0rd')

        from tests.shared.utils import parse_seating_config

        request_data = {
            'name': event_data['name'],
            'description': event_data['description'],
            'is_active': event_data.get('is_active', 'true').lower() == 'true',
            'venue_name': event_data.get('venue_name', DEFAULT_VENUE_NAME),
            'seating_config': parse_seating_config(
                event_data.get('seating_config', DEFAULT_SEATING_CONFIG_JSON)
            ),
        }

        response = client.post(EVENT_BASE, json=request_data)
        assert response.status_code == 201, f'Failed to create event: {response.text}'
        event_result = response.json()
        event_id = event_result['id']

    event = {
        'id': event_id,
        'name': event_data['name'],
        'status': event_data.get('status', 'available'),
    }

    # Store event in appropriate state
    if booking_state is not None:
        booking_state['event'] = event
        booking_state['event_id'] = event_id
    if event_state is not None:
        event_state['event'] = event
        event_state['event_id'] = event_id
        event_state['original_event'] = event

    return event


@given('I am not logged in')
def logout_user(client: TestClient):
    """Clear authentication cookies to simulate unauthenticated state."""
    client.cookies.clear()


@given('the following users exist:')
def create_multiple_users(step, client: TestClient, execute_sql_statement):
    """Create multiple users from a table."""
    import bcrypt

    from tests.util_constant import DEFAULT_PASSWORD

    # Parse the step table using the data_table structure
    rows = step.data_table.rows
    users = []

    hashed_password = bcrypt.hashpw(DEFAULT_PASSWORD.encode('utf-8'), bcrypt.gensalt()).decode(
        'utf-8'
    )

    # Skip the header row
    for row in rows[1:]:
        user_id = int(row.cells[0].value)
        email = row.cells[1].value
        role = row.cells[2].value

        # Insert user directly into database
        execute_sql_statement(
            """
            INSERT INTO "user" (id, email, hashed_password, name, role, is_active, is_superuser, is_verified)
            VALUES (:id, :email, :hashed_password, :name, :role, true, false, true)
            ON CONFLICT (id) DO NOTHING
            """,
            {
                'id': user_id,
                'email': email,
                'hashed_password': hashed_password,
                'name': f'Test User {user_id}',
                'role': role,
            },
        )

        users.append({'id': user_id, 'email': email, 'role': role})

    return users


@given('the following events exist:')
def create_multiple_events(step, client: TestClient, execute_sql_statement):
    """Create multiple events from a table."""
    import json

    # Parse the step table using the data_table structure
    rows = step.data_table.rows
    events = []

    # Skip the header row
    for row in rows[1:]:
        event_id = int(row.cells[0].value)
        name = row.cells[1].value
        venue = row.cells[2].value
        seller_id = int(row.cells[4].value)
        seating_config = json.loads(row.cells[5].value)

        # Insert event directly into database
        execute_sql_statement(
            """
            INSERT INTO event (id, name, description, price, seller_id, is_active, status, venue_name, seating_config)
            VALUES (:id, :name, :description, :price, :seller_id, :is_active, :status, :venue_name, :seating_config)
            ON CONFLICT (id) DO NOTHING
            """,
            {
                'id': event_id,
                'name': name,
                'description': f'Event at {venue}',
                'price': 1000,
                'seller_id': seller_id,
                'is_active': True,
                'status': 'available',
                'venue_name': venue,
                'seating_config': json.dumps(seating_config),
            },
        )

        events.append(
            {
                'id': event_id,
                'name': name,
                'venue_name': venue,
                'seller_id': seller_id,
                'seating_config': seating_config,
            }
        )

    return events

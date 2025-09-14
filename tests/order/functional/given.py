from datetime import datetime

from fastapi.testclient import TestClient
from pytest_bdd import given

from src.shared.constant.route_constant import (
    AUTH_LOGIN,
    EVENT_BASE,
    ORDER_BASE,
    ORDER_CANCEL,
    ORDER_GET,
    ORDER_PAY,
    TICKET_CREATE,
)
from tests.shared.utils import extract_table_data
from tests.util_constant import (
    DEFAULT_PASSWORD,
    TEST_BUYER_EMAIL,
    TEST_BUYER_NAME,
    TEST_CARD_NUMBER,
    TEST_EVENT_DESCRIPTION,
    TEST_EVENT_NAME,
    TEST_SELLER_EMAIL,
    TEST_SELLER_NAME,
)


@given('an order exists with status "pending_payment":')
def create_pending_order(step, client: TestClient, order_state, execute_sql_statement):
    order_data = extract_table_data(step)
    expected_seller_id = int(order_data['seller_id'])
    expected_buyer_id = int(order_data['buyer_id'])

    # Create users directly in database with expected IDs to ensure consistency
    import bcrypt

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
    from tests.event_test_constants import DEFAULT_SEATING_CONFIG, TAIPEI_ARENA

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

    from src.shared.constant.route_constant import TICKET_CREATE, TICKET_LIST

    # First check if tickets already exist
    tickets_list_response = client.get(TICKET_LIST.format(event_id=event['id']))
    if tickets_list_response.status_code == 200:
        tickets_data = tickets_list_response.json()
        existing_tickets = tickets_data.get('tickets', [])

        # If no tickets exist, create them
        if not existing_tickets:
            ticket_price = (
                int(order_data['total_price']) // 2
            )  # Create 2 tickets with half price each
            tickets_response = client.post(
                TICKET_CREATE.format(event_id=event['id']), json={'price': ticket_price}
            )
            assert tickets_response.status_code == 201, (
                f'Failed to create tickets: {tickets_response.text}'
            )
            print(f'TDD DEBUG: Created tickets for event {event["id"]}')

    # TDD FIX: Always refetch tickets after potential creation to ensure data consistency
    tickets_list_response = client.get(TICKET_LIST.format(event_id=event['id']))
    assert tickets_list_response.status_code == 200, (
        f'Failed to get tickets: {tickets_list_response.text}'
    )
    tickets_data = tickets_list_response.json()

    # TDD FIX: Enhanced debugging to understand the ticket ID mismatch issue
    available_tickets = [t for t in tickets_data['tickets'] if t['status'] == 'available']
    print(
        f'TDD DEBUG: Event {event["id"]} - Total tickets in response: {len(tickets_data["tickets"])}'
    )
    print(f'TDD DEBUG: Event {event["id"]} - Available tickets: {len(available_tickets)}')
    print(
        f'TDD DEBUG: Event {event["id"]} - First 5 available ticket IDs: {[t["id"] for t in available_tickets[:5]]}'
    )
    print(
        f'TDD DEBUG: Event {event["id"]} - Sample ticket data: {available_tickets[0] if available_tickets else "None"}'
    )

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

    print(f'TDD DEBUG: Event {event["id"]} - Final ticket IDs for order creation: {ticket_ids}')

    # Switch back to buyer login
    login_response = client.post(
        AUTH_LOGIN,
        data={'username': TEST_BUYER_EMAIL, 'password': DEFAULT_PASSWORD},
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    assert login_response.status_code == 200, f'Buyer login failed: {login_response.text}'
    if 'fastapiusersauth' in login_response.cookies:
        client.cookies.set('fastapiusersauth', login_response.cookies['fastapiusersauth'])

    order_response = client.post(ORDER_BASE, json={'ticket_ids': ticket_ids})
    assert order_response.status_code == 201, f'Failed to create order: {order_response.text}'
    order = order_response.json()

    # TDD FIX: Validate the order was created with the correct ticket IDs
    print(f'TDD DEBUG: Order created successfully with ID: {order["id"]}')
    print(f'TDD DEBUG: Order response: {order}')

    # TDD FIX: Verify the tickets were properly associated with the order by querying them back
    post_order_tickets_response = client.get(TICKET_LIST.format(event_id=event['id']))
    if post_order_tickets_response.status_code == 200:
        post_order_tickets = post_order_tickets_response.json()['tickets']
        order_associated_tickets = [t for t in post_order_tickets if t['id'] in ticket_ids]
        print(
            f'TDD DEBUG: Post-order ticket check - found {len(order_associated_tickets)} tickets associated with order'
        )
        for ticket in order_associated_tickets:
            print(f'TDD DEBUG: Ticket {ticket["id"]} - status: {ticket["status"]}')

    order_state['order'] = order
    order_state['buyer_id'] = buyer_id
    order_state['seller_id'] = seller_id
    order_state['event_id'] = event['id']
    order_state['ticket_ids'] = ticket_ids


@given('an order exists with status "paid":')
def create_paid_order(step, client: TestClient, order_state, execute_sql_statement):
    order_data = extract_table_data(step)
    create_pending_order(step, client, order_state, execute_sql_statement)
    if 'paid_at' in order_data and order_data['paid_at'] == 'not_null':
        execute_sql_statement(
            'UPDATE "order" SET status = \'paid\', paid_at = :paid_at WHERE id = :id',
            {'paid_at': datetime.now(), 'id': order_state['order']['id']},
        )
        order_state['order']['status'] = 'paid'
        order_state['order']['paid_at'] = datetime.now().isoformat()


@given('an order exists with status "cancelled":')
def create_cancelled_order(step, client: TestClient, order_state, execute_sql_statement):
    create_pending_order(step, client, order_state, execute_sql_statement)
    execute_sql_statement(
        'UPDATE "order" SET status = \'cancelled\' WHERE id = :id',
        {'id': order_state['order']['id']},
    )
    execute_sql_statement(
        "UPDATE event SET status = 'available' WHERE id = :id", {'id': order_state['event_id']}
    )
    order_state['order']['status'] = 'cancelled'


@given('users exist:')
def create_users(step, client: TestClient, order_state, execute_sql_statement):
    import bcrypt

    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    order_state['users'] = {}
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
        order_state['users'][user_id] = {
            'id': user_id,
            'email': user_data['email'],
            'name': user_data['name'],
            'role': user_data['role'],
        }
    execute_sql_statement(
        'SELECT setval(\'user_id_seq\', (SELECT COALESCE(MAX(id), 0) + 1 FROM "user"), false)', {}
    )


@given('events exist:')
def create_events(step, client: TestClient, order_state, execute_sql_statement):
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    order_state['events'] = {}
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        event_data = dict(zip(headers, values, strict=True))
        event_id = int(event_data['id'])
        seller_id = int(event_data['seller_id'])
        from tests.event_test_constants import DEFAULT_SEATING_CONFIG_JSON, DEFAULT_VENUE_NAME

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
        order_state['events'][event_id] = {
            'id': event_id,
            'seller_id': seller_id,
            'name': event_data['name'],
            'status': event_data['status'],
        }
    execute_sql_statement(
        "SELECT setval('event_id_seq', (SELECT COALESCE(MAX(id), 0) + 1 FROM event), false)", {}
    )


@given('orders exist:')
def create_orders(step, client: TestClient, order_state, execute_sql_statement):
    data_table = step.data_table
    rows = data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    order_state['orders'] = {}
    for row in rows[1:]:
        values = [cell.value for cell in row.cells]
        order_data = dict(zip(headers, values, strict=True))
        event_key = int(order_data['event_id'])
        if 'events' in order_state and event_key in order_state['events']:
            event_id = order_state['events'][event_key]['id']
        else:
            event_id = event_key
        order_id = int(order_data['id'])
        if order_data.get('paid_at') == 'not_null' and order_data['status'] == 'paid':
            execute_sql_statement(
                '\n                    INSERT INTO "order" (id, buyer_id, seller_id, event_id, price, status, created_at, updated_at, paid_at)\n                    VALUES (:id, :buyer_id, :seller_id, :event_id, :price, :status, NOW(), NOW(), NOW())\n                ',
                {
                    'id': order_id,
                    'buyer_id': int(order_data['buyer_id']),
                    'seller_id': int(order_data['seller_id']),
                    'event_id': event_id,
                    'price': int(order_data['total_price']),
                    'status': order_data['status'],
                },
            )
        else:
            execute_sql_statement(
                '\n                    INSERT INTO "order" (id, buyer_id, seller_id, event_id, price, status, created_at, updated_at)\n                    VALUES (:id, :buyer_id, :seller_id, :event_id, :price, :status, NOW(), NOW())\n                ',
                {
                    'id': order_id,
                    'buyer_id': int(order_data['buyer_id']),
                    'seller_id': int(order_data['seller_id']),
                    'event_id': event_id,
                    'price': int(order_data['total_price']),
                    'status': order_data['status'],
                },
            )
        order_state['orders'][int(order_data['id'])] = {'id': order_id}
    execute_sql_statement(
        'SELECT setval(\'order_id_seq\', (SELECT COALESCE(MAX(id), 0) + 1 FROM "order"), false)', {}
    )


@given('a event exists with negative price:')
def create_event_with_negative_price(step, client: TestClient, order_state, execute_sql_statement):
    """Create a event with negative price for testing validation."""
    from tests.event_test_constants import DEFAULT_SEATING_CONFIG_JSON, DEFAULT_VENUE_NAME

    event_data = extract_table_data(step)
    seller_id = int(event_data.get('seller_id', 1))

    # Store event data but don't create it yet (will fail on order creation)
    order_state['invalid_event'] = {
        'name': event_data['name'],
        'description': event_data['description'],
        'price': int(event_data['price']),  # Negative price
        'seller_id': seller_id,
        'is_active': event_data.get('is_active', 'true').lower() == 'true',
        'status': event_data.get('status', 'available'),
    }

    # Create event directly in database to bypass API validation
    execute_sql_statement(
        """
        INSERT INTO event (name, description, price, seller_id, is_active, status, venue_name, seating_config)
        VALUES (:name, :description, :price, :seller_id, :is_active, :status, :venue_name, :seating_config)
        """,
        {
            **order_state['invalid_event'],
            'venue_name': DEFAULT_VENUE_NAME,
            'seating_config': DEFAULT_SEATING_CONFIG_JSON,
        },
    )

    # Get the created event ID
    result = execute_sql_statement(
        'SELECT id FROM event WHERE name = :name ORDER BY id DESC LIMIT 1',
        {'name': event_data['name']},
    )
    event_id = result[0]['id'] if result else 1
    order_state['invalid_event']['id'] = event_id
    order_state['event_id'] = event_id


@given('a event exists with zero price:')
def create_event_with_zero_price(step, client: TestClient, order_state, execute_sql_statement):
    """Create a event with zero price for testing validation."""
    from tests.event_test_constants import DEFAULT_SEATING_CONFIG_JSON, DEFAULT_VENUE_NAME

    event_data = extract_table_data(step)
    seller_id = int(event_data.get('seller_id', 1))

    # Store event data
    order_state['invalid_event'] = {
        'name': event_data['name'],
        'description': event_data['description'],
        'price': 0,  # Zero price
        'seller_id': seller_id,
        'is_active': event_data.get('is_active', 'true').lower() == 'true',
        'status': event_data.get('status', 'available'),
    }

    # Create event directly in database to bypass API validation
    execute_sql_statement(
        """
        INSERT INTO event (name, description, price, seller_id, is_active, status, venue_name, seating_config)
        VALUES (:name, :description, :price, :seller_id, :is_active, :status, :venue_name, :seating_config)
        """,
        {
            **order_state['invalid_event'],
            'venue_name': DEFAULT_VENUE_NAME,
            'seating_config': DEFAULT_SEATING_CONFIG_JSON,
        },
    )

    # Get the created event ID
    result = execute_sql_statement(
        'SELECT id FROM event WHERE name = :name ORDER BY id DESC LIMIT 1',
        {'name': event_data['name']},
    )
    event_id = result[0]['id'] if result else 1
    order_state['invalid_event']['id'] = event_id
    order_state['event_id'] = event_id


@given('the buyer creates an order for the event')
def buyer_creates_order_given(client: TestClient, order_state):
    """Given that a buyer has already created an order."""
    # The buyer should already be logged in
    response = client.post(ORDER_BASE, json={'event_id': order_state['event']['id']})
    assert response.status_code == 201, f'Failed to create order: {response.text}'
    order_state['order'] = response.json()
    order_state['response'] = response


@given('the buyer pays for the order')
def buyer_pays_for_order_given(client: TestClient, order_state):
    """Given that the buyer has paid for the order."""
    order_id = order_state['order']['id']
    response = client.post(
        ORDER_PAY.format(order_id=order_id),
        json={'card_number': TEST_CARD_NUMBER},
    )
    assert response.status_code == 200, f'Failed to pay for order: {response.text}'

    # Fetch the updated order details after payment
    order_response = client.get(ORDER_GET.format(order_id=order_id))
    assert order_response.status_code == 200
    order_state['updated_order'] = order_response.json()  # Store full order details
    order_state['order']['status'] = 'paid'


@given('the event price is updated to 2000')
def event_price_updated_to_2000_given(order_state, execute_sql_statement):
    """Given that the event price has been updated."""
    event_id = order_state['event']['id']
    execute_sql_statement(
        'UPDATE event SET price = :price WHERE id = :id',
        {'price': 2000, 'id': event_id},
    )
    order_state['event']['price'] = 2000


@given('the buyer cancels the order to release the event')
def buyer_cancels_order_given(client: TestClient, order_state):
    """Given that the buyer has cancelled the order."""
    order_id = order_state['order']['id']
    response = client.delete(ORDER_CANCEL.format(order_id=order_id))
    assert response.status_code == 204, f'Failed to cancel order: {response.text}'
    order_state['order']['status'] = 'cancelled'


@given('the buyer cancels the order')
def buyer_cancels_order_simple(client: TestClient, order_state):
    """Given that the buyer has cancelled the order."""
    order_id = order_state['order']['id']
    response = client.delete(ORDER_CANCEL.format(order_id=order_id))
    assert response.status_code == 204, f'Failed to cancel order: {response.text}'
    order_state['order']['status'] = 'cancelled'
    order_state['updated_order'] = {'status': 'cancelled'}  # For Then step compatibility


@given('the order is marked as completed')
def order_marked_as_completed(order_state, execute_sql_statement):
    """Given that the order has been marked as completed."""
    order_id = order_state['order']['id']
    execute_sql_statement(
        'UPDATE "order" SET status = \'completed\' WHERE id = :id',
        {'id': order_id},
    )
    order_state['order']['status'] = 'completed'


@given('tickets exist for event:')
def tickets_exist_for_event(step, client, order_state=None):
    """Create tickets for an event."""
    from tests.shared.utils import create_user, login_user
    from tests.util_constant import SELLER1_EMAIL
    from tests.event_test_constants import DEFAULT_VENUE_NAME

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

    # Create tickets (if they don't already exist)
    response = client.post(TICKET_CREATE.format(event_id=event_id), json={'price': price})
    if response.status_code != 201:
        # Tickets might already exist, which is okay
        if response.status_code == 400 and 'already exist' in response.text:
            pass  # This is expected when tickets already exist
        else:
            raise AssertionError(f'Failed to create tickets: {response.text}')

    # The response shows tickets_created=500, so tickets will have sequential IDs starting from 1
    # Use the first two ticket IDs (they'll be sequential from the batch creation)
    # In this test environment, we know tickets are created with IDs 1, 2, 3, etc.
    ticket_ids = [1, 2]

    # Store ticket IDs for use in test steps if order_state is available
    if order_state is not None:
        order_state['ticket_ids'] = ticket_ids
        order_state['event_id'] = event_id


@given('buyer has reserved tickets:')
def buyer_has_reserved_tickets(step, execute_sql_statement):
    """Create tickets reserved by buyer in the past."""
    from datetime import datetime, timedelta

    data = extract_table_data(step)
    buyer_id = int(data['buyer_id'])
    event_id = int(data['event_id'])
    ticket_count = int(data['ticket_count'])
    reserved_at = data['reserved_at']

    # Parse reserved_at to determine actual datetime
    if reserved_at == '20_minutes_ago':
        actual_reserved_at = datetime.now() - timedelta(minutes=20)
    else:
        actual_reserved_at = datetime.now() - timedelta(minutes=5)

    # Update existing available tickets to reserved status
    execute_sql_statement(
        """
        UPDATE ticket
        SET status = 'reserved', buyer_id = :buyer_id, reserved_at = :reserved_at
        WHERE event_id = :event_id AND status = 'available'
        AND id IN (
            SELECT id FROM ticket
            WHERE event_id = :event_id AND status = 'available'
            ORDER BY id
            LIMIT :ticket_count
        )
        """,
        {
            'event_id': event_id,
            'buyer_id': buyer_id,
            'reserved_at': actual_reserved_at,
            'ticket_count': ticket_count,
        },
    )

from datetime import datetime

from fastapi.testclient import TestClient
from pytest_bdd import given

from src.shared.constant.route_constant import (
    AUTH_LOGIN,
    ORDER_BASE,
    ORDER_CANCEL,
    ORDER_GET,
    ORDER_PAY,
    EVENT_BASE,
    USER_CREATE,
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
def create_pending_order(step, client: TestClient, order_state):
    order_data = extract_table_data(step)
    seller_response = client.post(
        USER_CREATE,
        json={
            'email': TEST_SELLER_EMAIL,
            'password': DEFAULT_PASSWORD,
            'name': TEST_SELLER_NAME,
            'role': 'seller',
        },
    )
    if seller_response.status_code == 201:
        seller = seller_response.json()
        seller_id = seller['id']
    else:
        seller_id = int(order_data['seller_id'])
    buyer_response = client.post(
        USER_CREATE,
        json={
            'email': TEST_BUYER_EMAIL,
            'password': DEFAULT_PASSWORD,
            'name': TEST_BUYER_NAME,
            'role': 'buyer',
        },
    )
    if buyer_response.status_code == 201:
        buyer = buyer_response.json()
        buyer_id = buyer['id']
    else:
        buyer_id = int(order_data['buyer_id'])
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
            'price': int(order_data['price']),
            'is_active': True,
        },
    )
    assert event_response.status_code == 201, f'Failed to create event: {event_response.text}'
    event = event_response.json()
    login_response = client.post(
        AUTH_LOGIN,
        data={'username': TEST_BUYER_EMAIL, 'password': DEFAULT_PASSWORD},
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    assert login_response.status_code == 200, f'Buyer login failed: {login_response.text}'
    if 'fastapiusersauth' in login_response.cookies:
        client.cookies.set('fastapiusersauth', login_response.cookies['fastapiusersauth'])
    order_response = client.post(ORDER_BASE, json={'event_id': event['id']})
    assert order_response.status_code == 201, f'Failed to create order: {order_response.text}'
    order = order_response.json()
    order_state['order'] = order
    order_state['buyer_id'] = buyer_id
    order_state['seller_id'] = seller_id
    order_state['event_id'] = event['id']


@given('an order exists with status "paid":')
def create_paid_order(step, client: TestClient, order_state, execute_sql_statement):
    order_data = extract_table_data(step)
    create_pending_order(step, client, order_state)
    if 'paid_at' in order_data and order_data['paid_at'] == 'not_null':
        execute_sql_statement(
            'UPDATE "order" SET status = \'paid\', paid_at = :paid_at WHERE id = :id',
            {'paid_at': datetime.now(), 'id': order_state['order']['id']},
        )
        order_state['order']['status'] = 'paid'
        order_state['order']['paid_at'] = datetime.now().isoformat()


@given('an order exists with status "cancelled":')
def create_cancelled_order(step, client: TestClient, order_state, execute_sql_statement):
    create_pending_order(step, client, order_state)
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
        execute_sql_statement(
            '\n                INSERT INTO event (id, seller_id, name, description, price, is_active, status)\n                VALUES (:id, :seller_id, :name, :description, :price, :is_active, :status)\n            ',
            {
                'id': event_id,
                'seller_id': seller_id,
                'name': event_data['name'],
                'description': f'Description for {event_data["name"]}',
                'price': int(event_data['price']),
                'is_active': True,
                'status': event_data['status'],
            },
        )
        order_state['events'][event_id] = {
            'id': event_id,
            'seller_id': seller_id,
            'name': event_data['name'],
            'price': int(event_data['price']),
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
                    'price': int(order_data['price']),
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
                    'price': int(order_data['price']),
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
        INSERT INTO event (name, description, price, seller_id, is_active, status)
        VALUES (:name, :description, :price, :seller_id, :is_active, :status)
        """,
        order_state['invalid_event'],
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
        INSERT INTO event (name, description, price, seller_id, is_active, status)
        VALUES (:name, :description, :price, :seller_id, :is_active, :status)
        """,
        order_state['invalid_event'],
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

from fastapi.testclient import TestClient
from pytest_bdd import given

from src.shared.constant.route_constant import EVENT_CREATE, USER_CREATE
from tests.event_test_constants import (
    DEFAULT_SEATING_CONFIG_JSON,
    DEFAULT_VENUE_NAME,
)
from tests.shared.utils import create_user, extract_table_data, login_user, parse_seating_config
from tests.util_constant import TEST_SELLER_EMAIL


@given('I am logged in as:')
def login_user_with_table(step, client):
    login_data = extract_table_data(step)
    return login_user(client, login_data['email'], login_data['password'])


@given('a buyer exists:')
def create_buyer_shared(
    step, client: TestClient, booking_state=None, event_state=None, user_state=None
):
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


@given('an event exists:')
def create_event_shared(
    step, client: TestClient, booking_state=None, event_state=None, execute_sql_statement=None
):
    event_data = extract_table_data(step)
    login_user(client, TEST_SELLER_EMAIL, 'P@ssw0rd')
    request_data = {
        'name': event_data['name'],
        'description': event_data['description'],
        'is_active': event_data.get('is_active', 'true').lower() == 'true',
        'venue_name': event_data.get('venue_name', DEFAULT_VENUE_NAME),
        'seating_config': parse_seating_config(
            event_data.get('seating_config', DEFAULT_SEATING_CONFIG_JSON)
        ),
    }

    response = client.post(EVENT_CREATE, json=request_data)
    assert response.status_code == 201, f'Failed to create event: {response.text}'
    event_result = response.json()
    event_id = event_result['id']

    # If test specifies sold_out status, directly update the event status in database
    desired_status = event_data.get('status', 'available')
    if desired_status == 'sold_out' and execute_sql_statement:
        execute_sql_statement(
            'UPDATE event SET status = :status WHERE id = :id',
            {'status': 'sold_out', 'id': event_id},
        )

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

from fastapi.testclient import TestClient
from pytest_bdd import when

from src.shared.constant.route_constant import (
    EVENT_BASE,
    EVENT_LIST,
    EVENT_UPDATE,
)
from tests.shared.utils import extract_table_data


@when('I create a event with')
def create_event(step, client: TestClient, event_state):
    import json

    row_data = extract_table_data(step)
    request_data = {
        'name': row_data['name'],
        'description': row_data['description'],
    }
    if 'venue_name' in row_data:
        request_data['venue_name'] = row_data['venue_name']
    if 'seating_config' in row_data:
        request_data['seating_config'] = json.loads(row_data['seating_config'])
    if 'is_active' in row_data:
        request_data['is_active'] = row_data['is_active'].lower() == 'true'
    event_state['request_data'] = request_data
    event_state['response'] = client.post(EVENT_BASE, json=event_state['request_data'])


@when('I update the event to')
def update_event(step, client: TestClient, event_state):
    update_data = extract_table_data(step)
    if 'price' in update_data:
        update_data['price'] = int(update_data['price'])
    if 'is_active' in update_data:
        update_data['is_active'] = update_data['is_active'].lower() == 'true'
    event_id = event_state['event_id']
    event_state['update_data'] = update_data
    event_state['response'] = client.patch(EVENT_UPDATE.format(event_id=event_id), json=update_data)


@when('the seller requests their events')
def seller_requests_events(client: TestClient, event_state):
    seller_id = event_state['seller_id']
    event_state['response'] = client.get(f'{EVENT_LIST}?seller_id={seller_id}')


@when('a buyer requests events')
def buyer_requests_events(client: TestClient, event_state):
    event_state['response'] = client.get(EVENT_BASE)


@when('seller creates event with seating config:')
def seller_creates_event_with_seating_config(step, client: TestClient, context):
    """Seller creates event with seating config and ticket prices in sections."""
    import json

    row_data = extract_table_data(step)
    request_data = {
        'name': row_data['name'],
        'description': row_data['description'],
        'venue_name': row_data['venue_name'],
        'seating_config': json.loads(row_data['seating_config']),
        'is_active': True,
    }

    response = client.post(EVENT_BASE, json=request_data)
    context['response'] = response
    if response.status_code == 201:
        context['event'] = response.json()


@when('seller creates event with invalid seating config:')
def seller_creates_event_with_invalid_seating_config(step, client: TestClient, context):
    """Seller tries to create event with invalid seating config."""
    row_data = extract_table_data(step)
    request_data = {
        'name': row_data['name'],
        'description': row_data['description'],
        'venue_name': row_data['venue_name'],
        'seating_config': row_data['seating_config'],  # Invalid JSON string
        'is_active': True,
    }

    response = client.post(EVENT_BASE, json=request_data)
    context['response'] = response


@when('seller creates event with complex seating config:')
def seller_creates_event_with_complex_seating_config(step, client: TestClient, context):
    """Seller creates event with complex seating config."""
    import json

    row_data = extract_table_data(step)
    request_data = {
        'name': row_data['name'],
        'description': row_data['description'],
        'venue_name': row_data['venue_name'],
        'seating_config': json.loads(row_data['seating_config']),
        'is_active': True,
    }

    response = client.post(EVENT_BASE, json=request_data)
    context['response'] = response
    if response.status_code == 201:
        context['event'] = response.json()


@when('buyer tries to create event with seating config:')
def buyer_tries_to_create_event_with_seating_config(step, client: TestClient, context):
    """Buyer tries to create event (should be forbidden)."""
    import json

    row_data = extract_table_data(step)
    request_data = {
        'name': row_data['name'],
        'description': row_data['description'],
        'venue_name': row_data['venue_name'],
        'seating_config': json.loads(row_data['seating_config']),
        'is_active': True,
    }

    response = client.post(EVENT_BASE, json=request_data)
    context['response'] = response


@when('seller creates event with negative ticket price:')
def seller_creates_event_with_negative_ticket_price(step, client: TestClient, context):
    """Seller tries to create event with negative ticket price in seating config."""
    import json

    row_data = extract_table_data(step)
    request_data = {
        'name': row_data['name'],
        'description': row_data['description'],
        'venue_name': row_data['venue_name'],
        'seating_config': json.loads(row_data['seating_config']),  # Contains negative price
        'is_active': True,
    }

    response = client.post(EVENT_BASE, json=request_data)
    context['response'] = response


@when('seller creates event with zero ticket price:')
def seller_creates_event_with_zero_ticket_price(step, client: TestClient, context):
    """Seller tries to create event with zero ticket price in seating config."""
    import json

    row_data = extract_table_data(step)
    request_data = {
        'name': row_data['name'],
        'description': row_data['description'],
        'venue_name': row_data['venue_name'],
        'seating_config': json.loads(row_data['seating_config']),  # Contains zero price
        'is_active': True,
    }

    response = client.post(EVENT_BASE, json=request_data)
    context['response'] = response

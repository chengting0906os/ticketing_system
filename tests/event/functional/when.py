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
        'price': int(row_data['price']),
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

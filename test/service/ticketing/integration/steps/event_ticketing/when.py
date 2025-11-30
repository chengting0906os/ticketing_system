from typing import Any

from fastapi.testclient import TestClient
from pytest_bdd import when
from pytest_bdd.model import Step

from test.shared.utils import extract_table_data, login_user
from test.util_constant import BUYER1_EMAIL, DEFAULT_PASSWORD, SELLER1_EMAIL

from src.platform.constant.route_constant import (
    EVENT_BASE,
    EVENT_LIST,
    EVENT_TICKETS_BY_SUBSECTION,
    EVENT_UPDATE,
)


@when('I create a event with')
def create_event(step: Step, client: TestClient, event_state: dict[str, Any]) -> None:
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
def update_event(step: Step, client: TestClient, event_state: dict[str, Any]) -> None:
    update_data = extract_table_data(step)
    if 'price' in update_data:
        update_data['price'] = int(update_data['price'])
    if 'is_active' in update_data:
        update_data['is_active'] = update_data['is_active'].lower() == 'true'
    event_id = event_state['event_id']
    event_state['update_data'] = update_data
    event_state['response'] = client.patch(EVENT_UPDATE.format(event_id=event_id), json=update_data)


@when('the seller requests their events')
def seller_requests_events(client: TestClient, event_state: dict[str, Any]) -> None:
    seller_id = event_state['seller_id']
    event_state['response'] = client.get(f'{EVENT_LIST}?seller_id={seller_id}')


@when('a buyer requests events')
def buyer_requests_events(client: TestClient, event_state: dict[str, Any]) -> None:
    event_state['response'] = client.get(EVENT_BASE)


@when('seller creates event with seating config:')
def seller_creates_event_with_seating_config(
    step: Step, client: TestClient, context: dict[str, Any]
) -> None:
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
def seller_creates_event_with_invalid_seating_config(
    step: Step, client: TestClient, context: dict[str, Any]
) -> None:
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
def seller_creates_event_with_complex_seating_config(
    step: Step, client: TestClient, context: dict[str, Any]
) -> None:
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
def buyer_tries_to_create_event_with_seating_config(
    step: Step, client: TestClient, context: dict[str, Any]
) -> None:
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
def seller_creates_event_with_negative_ticket_price(
    step: Step, client: TestClient, context: dict[str, Any]
) -> None:
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
def seller_creates_event_with_zero_ticket_price(
    step: Step, client: TestClient, context: dict[str, Any]
) -> None:
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


"""When steps for event ticket BDD test."""


@when('seller lists all tickets with:')
def seller_lists_all_tickets(step: Step, client: TestClient, context: dict[str, Any]) -> None:
    """Seller lists all tickets for an event."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])

    # Login as seller
    login_user(client, SELLER1_EMAIL, DEFAULT_PASSWORD)

    # List all tickets
    response = client.get(
        EVENT_TICKETS_BY_SUBSECTION.format(event_id=event_id, section='A', subsection=1)
    )

    context['response'] = response


@when('seller lists tickets by section with:')
def seller_lists_tickets_by_section(
    step: Step, client: TestClient, context: dict[str, Any]
) -> None:
    """Seller lists tickets for specific section."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])
    section = data['section']

    # Login as seller
    login_user(client, SELLER1_EMAIL, DEFAULT_PASSWORD)

    # List tickets by section
    response = client.get(
        EVENT_TICKETS_BY_SUBSECTION.format(event_id=event_id, section=section, subsection=1)
    )

    context['response'] = response


@when('buyer lists available tickets with:')
def buyer_lists_available_tickets(step: Step, client: TestClient, context: dict[str, Any]) -> None:
    data = extract_table_data(step)
    event_id = int(data['event_id'])

    # Login as buyer
    login_user(client, BUYER1_EMAIL, DEFAULT_PASSWORD)

    # List available tickets
    response = client.get(
        EVENT_TICKETS_BY_SUBSECTION.format(event_id=event_id, section='A', subsection=1)
    )

    context['response'] = response


@when('buyer attempts to access section tickets with:')
def buyer_attempts_to_access_section_tickets(
    step: Step, client: TestClient, context: dict[str, Any]
) -> None:
    """Buyer attempts to access section-specific tickets (seller-only functionality)."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])
    section = data['section']

    # Login as buyer
    login_user(client, BUYER1_EMAIL, DEFAULT_PASSWORD)

    # Try to access section-specific tickets (should fail)
    response = client.get(
        EVENT_TICKETS_BY_SUBSECTION.format(event_id=event_id, section=section, subsection=1)
    )

    context['response'] = response


@when('buyer lists available tickets with detailed view:')
def buyer_lists_tickets_with_detail(
    step: Step, context: dict[str, Any], client: TestClient
) -> None:
    """Buyer lists tickets with detailed view for an event."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])

    login_user(client, BUYER1_EMAIL, DEFAULT_PASSWORD)
    response = client.get(
        EVENT_TICKETS_BY_SUBSECTION.format(event_id=event_id, section='A', subsection=1)
    )
    context['response'] = response


@when('buyer cancels the booking')
def buyer_cancels_booking(client: TestClient, context: dict[str, Any]) -> None:
    """Buyer cancels their booking."""
    booking_id = context.get('booking_id')
    if not booking_id:
        raise ValueError('No booking_id found in context')

    # Cancel the booking
    response = client.delete(f'/api/booking/{booking_id}')
    context['response'] = response


@when('I get the event details')
def get_event_details(client: TestClient, event_state: dict[str, Any]) -> None:
    """Get event details by ID."""
    event_id = event_state['event_id']
    event_state['response'] = client.get(f'{EVENT_BASE}/{event_id}')


@when('I get event with id 99999')
def get_nonexistent_event(client: TestClient, event_state: dict[str, Any]) -> None:
    """Try to get a non-existent event."""
    event_state['response'] = client.get(f'{EVENT_BASE}/99999')

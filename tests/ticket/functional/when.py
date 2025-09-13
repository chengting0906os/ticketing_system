"""When steps for ticket BDD tests."""

from pytest_bdd import when

from src.shared.constant.route_constant import TICKET_BASE
from tests.shared.utils import extract_table_data, login_user
from tests.util_constant import BUYER1_EMAIL, DEFAULT_PASSWORD, SELLER1_EMAIL


@when('seller creates tickets with:')
def seller_creates_tickets(step, client, context):
    """Seller creates all tickets for an event."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])
    price = int(data['price'])

    # Login as seller
    login_user(client, SELLER1_EMAIL, DEFAULT_PASSWORD)

    # Create tickets
    response = client.post(f'/api/ticket/events/{event_id}/tickets', json={'price': price})

    context['response'] = response


@when('buyer creates tickets with:')
def buyer_creates_tickets(step, client, context):
    """Buyer tries to create tickets for an event."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])
    price = int(data['price'])

    # Login as buyer
    login_user(client, BUYER1_EMAIL, DEFAULT_PASSWORD)

    # Try to create tickets
    response = client.post(f'/api/ticket/events/{event_id}/tickets', json={'price': price})

    context['response'] = response


@when('seller updates ticket price with:')
def seller_updates_ticket_prices(step, client, context):
    """Seller updates ticket prices for specific section."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])
    section = data['section']
    subsection = int(data['subsection'])
    price = int(data['price'])

    # Login as seller
    login_user(client, SELLER1_EMAIL, DEFAULT_PASSWORD)

    # Update ticket prices (this endpoint doesn't exist yet - will be implemented later)
    response = client.put(
        f'{TICKET_BASE}/events/{event_id}/tickets/section/{section}/subsection/{subsection}',
        json={'price': price},
    )

    context['response'] = response


@when('seller views tickets with:')
def seller_views_tickets(step, client, context):
    """Seller views tickets for specific section."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])
    section = data['section']

    # Login as seller
    login_user(client, SELLER1_EMAIL, DEFAULT_PASSWORD)

    # View tickets (this endpoint doesn't exist yet - will be implemented later)
    response = client.get(f'{TICKET_BASE}/events/{event_id}/tickets/section/{section}')

    context['response'] = response

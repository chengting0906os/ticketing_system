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


@when('seller lists all tickets with:')
def seller_lists_all_tickets(step, client, context):
    """Seller lists all tickets for an event."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])

    # Login as seller
    login_user(client, SELLER1_EMAIL, DEFAULT_PASSWORD)

    # List all tickets
    response = client.get(f'/api/ticket/events/{event_id}/tickets')

    context['response'] = response


@when('seller lists tickets by section with:')
def seller_lists_tickets_by_section(step, client, context):
    """Seller lists tickets for specific section."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])
    section = data['section']

    # Login as seller
    login_user(client, SELLER1_EMAIL, DEFAULT_PASSWORD)

    # List tickets by section
    response = client.get(f'/api/ticket/events/{event_id}/tickets/section/{section}')

    context['response'] = response


@when('buyer attempts to list tickets with:')
def buyer_attempts_to_list_tickets(step, client, context):
    """Buyer attempts to list tickets for an event."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])

    # Login as buyer
    login_user(client, BUYER1_EMAIL, DEFAULT_PASSWORD)

    # Try to list tickets
    response = client.get(f'/api/ticket/events/{event_id}/tickets')

    context['response'] = response


@when('buyer lists available tickets with:')
def buyer_lists_available_tickets(step, client, context):
    """Buyer lists available tickets for an event."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])

    # Login as buyer
    login_user(client, BUYER1_EMAIL, DEFAULT_PASSWORD)

    # List available tickets
    response = client.get(f'/api/ticket/events/{event_id}/tickets')

    context['response'] = response


@when('buyer attempts to access section tickets with:')
def buyer_attempts_to_access_section_tickets(step, client, context):
    """Buyer attempts to access section-specific tickets (seller-only functionality)."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])
    section = data['section']

    # Login as buyer
    login_user(client, BUYER1_EMAIL, DEFAULT_PASSWORD)

    # Try to access section-specific tickets (should fail)
    response = client.get(f'/api/ticket/events/{event_id}/tickets/section/{section}')

    context['response'] = response


@when('buyer lists available tickets with detailed view:')
def buyer_lists_tickets_with_detail(step, context, client):
    """Buyer lists tickets with detailed view for an event."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])

    login_user(client, BUYER1_EMAIL, DEFAULT_PASSWORD)
    response = client.get(f'/api/ticket/events/{event_id}/tickets')
    context['response'] = response

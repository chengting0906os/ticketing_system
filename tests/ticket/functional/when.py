"""When steps for ticket BDD tests."""

from pytest_bdd import when

from src.shared.constant.route_constant import (
    TICKET_BY_SECTION,
    TICKET_BY_SUBSECTION,
    TICKET_CLEANUP_EXPIRED,
    TICKET_CREATE,
    TICKET_LIST,
    TICKET_RESERVE,
)
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
    response = client.post(TICKET_CREATE.format(event_id=event_id), json={'price': price})

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
    response = client.post(TICKET_CREATE.format(event_id=event_id), json={'price': price})

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
        TICKET_BY_SUBSECTION.format(event_id=event_id, section=section, subsection=subsection),
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
    response = client.get(TICKET_BY_SECTION.format(event_id=event_id, section=section))

    context['response'] = response


@when('seller lists all tickets with:')
def seller_lists_all_tickets(step, client, context):
    """Seller lists all tickets for an event."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])

    # Login as seller
    login_user(client, SELLER1_EMAIL, DEFAULT_PASSWORD)

    # List all tickets
    response = client.get(TICKET_LIST.format(event_id=event_id))

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
    response = client.get(TICKET_BY_SECTION.format(event_id=event_id, section=section))

    context['response'] = response


@when('buyer attempts to list tickets with:')
def buyer_attempts_to_list_tickets(step, client, context):
    """Buyer attempts to list tickets for an event."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])

    # Login as buyer
    login_user(client, BUYER1_EMAIL, DEFAULT_PASSWORD)

    # Try to list tickets
    response = client.get(TICKET_LIST.format(event_id=event_id))

    context['response'] = response


@when('buyer lists available tickets with:')
def buyer_lists_available_tickets(step, client, context):
    """Buyer lists available tickets for an event."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])

    # Login as buyer
    login_user(client, BUYER1_EMAIL, DEFAULT_PASSWORD)

    # List available tickets
    response = client.get(TICKET_LIST.format(event_id=event_id))

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
    response = client.get(TICKET_BY_SECTION.format(event_id=event_id, section=section))

    context['response'] = response


@when('buyer lists available tickets with detailed view:')
def buyer_lists_tickets_with_detail(step, context, client):
    """Buyer lists tickets with detailed view for an event."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])

    login_user(client, BUYER1_EMAIL, DEFAULT_PASSWORD)
    response = client.get(TICKET_LIST.format(event_id=event_id))
    context['response'] = response


@when('buyer attempts to reserve too many tickets:')
def buyer_attempts_to_reserve_too_many_tickets(step, client, context, reservation_state):
    """Buyer attempts to reserve too many tickets (should fail due to 4-ticket limit)."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])
    ticket_count = int(data['ticket_count'])

    # Login as buyer
    login_user(client, BUYER1_EMAIL, DEFAULT_PASSWORD)

    # Attempt to reserve tickets
    response = client.post(
        TICKET_RESERVE.format(event_id=event_id), json={'ticket_count': ticket_count}
    )

    context['response'] = response


@when('buyer reserves tickets:')
def buyer_reserves_tickets(step, client, context, reservation_state):
    """Buyer reserves tickets for an event."""
    data = extract_table_data(step)
    buyer_id = int(data['buyer_id'])
    event_id = int(data['event_id'])
    ticket_count = int(data['ticket_count'])

    # Login as buyer - buyer_id 2 maps to buyer1@test.com, buyer_id 3 maps to buyer2@test.com
    buyer_email = f'buyer{buyer_id - 1}@test.com'
    login_user(client, buyer_email, DEFAULT_PASSWORD)

    # Reserve tickets
    response = client.post(
        TICKET_RESERVE.format(event_id=event_id), json={'ticket_count': ticket_count}
    )

    context['response'] = response
    if response.status_code == 200:
        reservation_state.reservation_data = response.json()


@when('buyer attempts to reserve tickets:')
def buyer_attempts_to_reserve_tickets(step, client, context):
    """Buyer attempts to reserve tickets for an event."""
    data = extract_table_data(step)
    buyer_id = int(data['buyer_id'])
    event_id = int(data['event_id'])
    ticket_count = int(data['ticket_count'])

    # Login as buyer - buyer_id 2 maps to buyer1@test.com, buyer_id 3 maps to buyer2@test.com
    buyer_email = f'buyer{buyer_id - 1}@test.com'
    login_user(client, buyer_email, DEFAULT_PASSWORD)

    # Attempt to reserve tickets
    response = client.post(
        TICKET_RESERVE.format(event_id=event_id), json={'ticket_count': ticket_count}
    )

    context['response'] = response


@when('buyer attempts to reserve same tickets:')
def buyer_attempts_to_reserve_same_tickets(step, client, context):
    """Buyer attempts to reserve tickets that are already reserved."""
    data = extract_table_data(step)
    buyer_id = int(data['buyer_id'])
    event_id = int(data['event_id'])
    ticket_count = int(data['ticket_count'])

    # Login as buyer - buyer_id 2 maps to buyer1@test.com, buyer_id 3 maps to buyer2@test.com
    buyer_email = f'buyer{buyer_id - 1}@test.com'
    login_user(client, buyer_email, DEFAULT_PASSWORD)

    # Attempt to reserve tickets
    response = client.post(
        TICKET_RESERVE.format(event_id=event_id), json={'ticket_count': ticket_count}
    )

    context['response'] = response


@when('system checks expired reservations')
def system_checks_expired_reservations(client, context):
    """System checks for expired reservations."""
    # Call the system endpoint to check for expired reservations
    response = client.post(TICKET_CLEANUP_EXPIRED)
    context['response'] = response


@when('buyer creates booking for reserved tickets:')
def buyer_creates_booking_for_reserved_tickets(step, client, context):
    """Create booking for specific reserved tickets."""
    data = extract_table_data(step)

    buyer_id = int(data['buyer_id'])
    event_id = int(data['event_id'])

    # Login as buyer
    buyer_email = f'buyer{buyer_id - 1}@test.com'  # buyer_id 2 -> buyer1@test.com
    login_user(client, buyer_email, DEFAULT_PASSWORD)

    # Create booking for reserved tickets
    response = client.post('/api/booking', json={'event_id': event_id})
    context['response'] = response
    context['client'] = client

    # Store booking_id for later use
    if response.status_code == 201:
        booking_data = response.json()
        context['booking_id'] = booking_data.get('id')


@when('buyer pays for the booking within time limit')
def buyer_pays_for_booking(step, client, context):
    """Pay for the booking within the time limit."""
    booking_id = context.get('booking_id')

    if not booking_id:
        raise ValueError('No booking_id found in context')

    # Make payment
    response = client.post(
        f'/api/booking/{booking_id}/pay',
        json={'card_number': '4111111111111111', 'payment_method': 'mock'},
    )
    context['response'] = response


@when('buyer cancels the booking')
def buyer_cancels_booking(client, context):
    """Buyer cancels their booking."""
    booking_id = context.get('booking_id')
    if not booking_id:
        raise ValueError('No booking_id found in context')

    # Cancel the booking
    response = client.delete(f'/api/booking/{booking_id}')
    context['response'] = response

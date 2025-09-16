"""Given steps for event ticket BDD tests."""

import json

import bcrypt
from pytest_bdd import given

from src.shared.constant.route_constant import EVENT_TICKETS_CREATE
from tests.shared.utils import extract_table_data, login_user
from tests.util_constant import DEFAULT_PASSWORD, SELLER1_EMAIL, SELLER2_EMAIL


@given('an event exists with:')
def event_exists(step, execute_sql_statement):
    event_data = extract_table_data(step)
    event_id = int(event_data['event_id'])
    expected_seller_id = int(event_data['seller_id'])

    # Use the seller_id as provided in the test scenario
    # The BDD steps should ensure the seller exists before the event is created
    actual_seller_id = expected_seller_id

    event_info = {
        'name': 'Test Event',
        'description': 'Test Description',
        'venue_name': 'Large Arena',
        'seating_config': json.dumps(
            {
                'sections': [
                    {
                        'name': 'A',
                        'subsections': [
                            {'number': 1, 'rows': 10, 'seats_per_row': 25},
                            {'number': 2, 'rows': 10, 'seats_per_row': 25},
                        ],
                    },
                    {
                        'name': 'B',
                        'subsections': [
                            {'number': 1, 'rows': 10, 'seats_per_row': 25},
                            {'number': 2, 'rows': 10, 'seats_per_row': 25},
                        ],
                    },
                    {
                        'name': 'C',
                        'subsections': [
                            {'number': 1, 'rows': 10, 'seats_per_row': 25},
                            {'number': 2, 'rows': 10, 'seats_per_row': 25},
                        ],
                    },
                    {
                        'name': 'D',
                        'subsections': [
                            {'number': 1, 'rows': 10, 'seats_per_row': 25},
                            {'number': 2, 'rows': 10, 'seats_per_row': 25},
                        ],
                    },
                    {
                        'name': 'E',
                        'subsections': [
                            {'number': 1, 'rows': 10, 'seats_per_row': 25},
                            {'number': 2, 'rows': 10, 'seats_per_row': 25},
                        ],
                    },
                ]
            }
        ),
    }

    # Insert event with specific ID
    execute_sql_statement(
        """
        INSERT INTO event (id, name, description, seller_id, is_active, status, venue_name, seating_config)
        VALUES (:id, :name, :description, :seller_id, :is_active, :status, :venue_name, :seating_config)
        ON CONFLICT (id) DO NOTHING
        """,
        {
            'id': event_id,
            'name': event_info['name'],
            'description': event_info['description'],
            'seller_id': actual_seller_id,
            'is_active': True,
            'status': 'available',
            'venue_name': event_info['venue_name'],
            'seating_config': event_info['seating_config'],
        },
    )


@given('another seller and event exist with:')
def other_seller_event_exists(step, execute_sql_statement):
    """Create another seller and their event."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])
    seller_id = int(data['seller_id'])

    # Create seller2 through SQL (for this test scenario we need a different seller)
    hashed_password = bcrypt.hashpw(DEFAULT_PASSWORD.encode('utf-8'), bcrypt.gensalt()).decode(
        'utf-8'
    )

    execute_sql_statement(
        """
        INSERT INTO "user" (id, email, hashed_password, name, role, is_active, is_superuser, is_verified)
        VALUES (:id, :email, :hashed_password, :name, :role, true, false, true)
        ON CONFLICT (id) DO NOTHING
        """,
        {
            'id': seller_id,
            'email': SELLER2_EMAIL,
            'hashed_password': hashed_password,
            'name': 'Test Seller 2',
            'role': 'seller',
        },
    )

    # Create event owned by seller2
    execute_sql_statement(
        """
        INSERT INTO event (id, name, description, seller_id, is_active, status, venue_name, seating_config)
        VALUES (:id, :name, :description, :seller_id, :is_active, :status, :venue_name, :seating_config)
        ON CONFLICT (id) DO NOTHING
        """,
        {
            'id': event_id,
            'name': 'Test Event 2',
            'description': 'Test Description 2',
            'seller_id': seller_id,
            'is_active': True,
            'status': 'available',
            'venue_name': 'Another Arena',
            'seating_config': json.dumps(
                {
                    'sections': [
                        {
                            'name': 'A',
                            'subsections': [
                                {'number': 1, 'rows': 10, 'seats_per_row': 20},
                                {'number': 2, 'rows': 10, 'seats_per_row': 20},
                            ],
                        },
                        {
                            'name': 'B',
                            'subsections': [
                                {'number': 1, 'rows': 10, 'seats_per_row': 20},
                                {'number': 2, 'rows': 10, 'seats_per_row': 20},
                            ],
                        },
                        {
                            'name': 'C',
                            'subsections': [
                                {'number': 1, 'rows': 10, 'seats_per_row': 20},
                                {'number': 2, 'rows': 10, 'seats_per_row': 20},
                            ],
                        },
                        {
                            'name': 'D',
                            'subsections': [
                                {'number': 1, 'rows': 10, 'seats_per_row': 20},
                                {'number': 2, 'rows': 10, 'seats_per_row': 20},
                            ],
                        },
                        {
                            'name': 'E',
                            'subsections': [
                                {'number': 1, 'rows': 10, 'seats_per_row': 20},
                                {'number': 2, 'rows': 10, 'seats_per_row': 20},
                            ],
                        },
                    ]
                }
            ),
        },
    )


@given('all tickets exist with:')
def tickets_already_exist(step, client):
    """Create all tickets for an event (setup for duplicate creation test)."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])
    price = int(data['price'])

    # Simple mapping based on event_id patterns from the feature file
    # Event 3 is owned by seller2 (from "another seller and event exist")
    # All other events are owned by seller1
    if event_id == 3:
        seller_email = SELLER2_EMAIL
    else:
        seller_email = SELLER1_EMAIL

    # Login as the appropriate seller
    login_user(client, seller_email, DEFAULT_PASSWORD)

    # Create tickets
    response = client.post(EVENT_TICKETS_CREATE.format(event_id=event_id), json={'price': price})
    assert response.status_code == 201


@given('mixed status tickets exist with:')
def mixed_status_tickets_exist(step, client, execute_sql_statement):
    """Create tickets with mixed status (some available, some sold)."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])
    sold_count = int(data['sold_count'])

    # Login as seller to create tickets
    login_user(client, SELLER1_EMAIL, DEFAULT_PASSWORD)

    # Create all tickets first
    response = client.post(EVENT_TICKETS_CREATE.format(event_id=event_id), json={'price': 1000})
    assert response.status_code == 201

    # Update some tickets to sold status via SQL
    # (This simulates tickets that were purchased by other buyers)
    execute_sql_statement(
        """
        UPDATE ticket
        SET status = 'sold'
        WHERE event_id = :event_id
        AND id IN (
            SELECT id FROM ticket
            WHERE event_id = :event_id
            ORDER BY id
            LIMIT :sold_count
        )
        """,
        {'event_id': event_id, 'sold_count': sold_count},
    )


# Removed duplicate step definition - using the one from booking/functional/given.py instead


@given('tickets exist with limited availability:')
def tickets_exist_with_limited_availability(step, client, execute_sql_statement):
    """Create tickets with limited availability."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])
    available_count = int(data['available_count'])
    sold_count = int(data['sold_count'])

    # Login as seller1 to create tickets
    login_user(client, SELLER1_EMAIL, DEFAULT_PASSWORD)

    # Create only the limited number of tickets
    for i in range(available_count + sold_count):
        execute_sql_statement(
            """
            INSERT INTO ticket (event_id, section, subsection, row_number, seat_number, price, status)
            VALUES (:event_id, 'A', 1, :row_number, :seat_number, 1000, :status)
            """,
            {
                'event_id': event_id,
                'row_number': (i // 10) + 1,
                'seat_number': (i % 10) + 1,
                'status': 'sold' if i < sold_count else 'available',
            },
        )


@given('tickets are already reserved:')
def tickets_are_already_reserved(step, execute_sql_statement):
    """Create tickets that are already reserved."""
    from datetime import datetime

    data = extract_table_data(step)
    event_id = int(data['event_id'])
    reserved_by = int(data['reserved_by'])
    ticket_count = int(data['ticket_count'])

    # Create reserved tickets
    now = datetime.now()

    for i in range(ticket_count):
        execute_sql_statement(
            """
            INSERT INTO ticket (event_id, section, subsection, row_number, seat_number, price, status, buyer_id, reserved_at)
            VALUES (:event_id, 'A', 1, :row_number, :seat_number, 1000, 'reserved', :buyer_id, :reserved_at)
            """,
            {
                'event_id': event_id,
                'row_number': (i // 10) + 1,
                'seat_number': (i % 10) + 1,
                'buyer_id': reserved_by,
                'reserved_at': now,
            },
        )


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


@given('buyer has active reservation:')
def buyer_has_active_reservation(step, execute_sql_statement):
    """Create an active reservation for a buyer."""
    from datetime import datetime

    data = extract_table_data(step)
    buyer_id = int(data['buyer_id'])
    event_id = int(data['event_id'])
    ticket_count = int(data['ticket_count'])
    reservation_id = int(data['reservation_id'])

    # Create reserved tickets
    now = datetime.now()

    for i in range(ticket_count):
        execute_sql_statement(
            """
            INSERT INTO ticket (id, event_id, section, subsection, row_number, seat_number, price, status, buyer_id, reserved_at)
            VALUES (:id, :event_id, 'A', 1, :row_number, :seat_number, 1000, 'reserved', :buyer_id, :reserved_at)
            """,
            {
                'id': reservation_id * 1000 + i,  # Generate unique IDs
                'event_id': event_id,
                'row_number': (i // 10) + 1,
                'seat_number': (i % 10) + 1,
                'buyer_id': buyer_id,
                'reserved_at': now,
            },
        )


@given('tickets exist for events:')
def tickets_exist_for_events(step, execute_sql_statement):
    """Create tickets for events."""
    rows = step.data_table.rows
    # Skip the header row
    for row in rows[1:]:
        event_id = int(row.cells[0].value)
        ticket_count = int(row.cells[1].value)
        price = int(row.cells[2].value)
        status = row.cells[3].value

        # Create tickets using the seating configuration
        for i in range(ticket_count):
            execute_sql_statement(
                """
                INSERT INTO ticket (event_id, section, subsection, row_number, seat_number, price, status)
                VALUES (:event_id, 'A', 1, :row_number, :seat_number, :price, :status)
                """,
                {
                    'event_id': event_id,
                    'row_number': (i // 10) + 1,
                    'seat_number': (i % 10) + 1,
                    'price': price,
                    'status': status,
                },
            )

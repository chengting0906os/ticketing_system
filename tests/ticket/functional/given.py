"""Given steps for ticket BDD tests."""

import json
import bcrypt

from pytest_bdd import given

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
        'price': 1000,
        'venue_name': 'Large Arena',
        'seating_config': json.dumps(
            {
                'sections': ['A', 'B', 'C', 'D', 'E'],
                'subsections': [1, 2],
                'rows_per_subsection': 10,
                'seats_per_row': 25,
                'total_capacity': 5000,
            }
        ),
    }

    # Insert event with specific ID
    execute_sql_statement(
        """
        INSERT INTO event (id, name, description, price, seller_id, is_active, status, venue_name, seating_config)
        VALUES (:id, :name, :description, :price, :seller_id, :is_active, :status, :venue_name, :seating_config)
        ON CONFLICT (id) DO NOTHING
        """,
        {
            'id': event_id,
            'name': event_info['name'],
            'description': event_info['description'],
            'price': event_info['price'],
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
        INSERT INTO event (id, name, description, price, seller_id, is_active, status, venue_name, seating_config)
        VALUES (:id, :name, :description, :price, :seller_id, :is_active, :status, :venue_name, :seating_config)
        ON CONFLICT (id) DO NOTHING
        """,
        {
            'id': event_id,
            'name': 'Test Event 2',
            'description': 'Test Description 2',
            'price': 2000,
            'seller_id': seller_id,
            'is_active': True,
            'status': 'available',
            'venue_name': 'Another Arena',
            'seating_config': json.dumps(
                {
                    'sections': ['A', 'B', 'C', 'D', 'E'],
                    'subsections': [1, 2, 3, 4, 5],
                    'rows_per_subsection': 10,
                    'seats_per_row': 20,
                    'total_capacity': 5000,
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
    response = client.post(f'/api/ticket/events/{event_id}/tickets', json={'price': price})
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
    response = client.post(f'/api/ticket/events/{event_id}/tickets', json={'price': 1000})
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

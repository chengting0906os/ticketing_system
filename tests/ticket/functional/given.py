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
    seller_id = int(event_data['seller_id'])

    # Skip user creation here - assume seller already exists from previous step

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
            'seller_id': seller_id,
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
def tickets_already_exist(
    step, execute_sql_statement, client
):  # execute_sql_statement unused - using API instead
    """Create all tickets for an event (setup for duplicate creation test)."""
    data = extract_table_data(step)
    event_id = int(data['event_id'])
    price = int(data['price'])

    # Login as seller
    login_user(client, SELLER1_EMAIL, DEFAULT_PASSWORD)

    # Create tickets
    response = client.post(f'/api/ticket/events/{event_id}/tickets', json={'price': price})
    assert response.status_code == 201

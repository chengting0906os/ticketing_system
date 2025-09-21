import json
from typing import Any, Dict

from fastapi.testclient import TestClient

from src.shared.constant.route_constant import AUTH_LOGIN, EVENT_BASE, USER_CREATE
from tests.event_test_constants import (
    DEFAULT_SEATING_CONFIG,
    DEFAULT_SEATING_CONFIG_JSON,
    DEFAULT_VENUE_NAME,
)


def extract_table_data(step) -> Dict[str, Any]:
    rows = step.data_table.rows
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    return dict(zip(headers, values, strict=True))


def extract_single_value(step, row_index: int = 0, col_index: int = 0) -> str:
    rows = step.data_table.rows
    return rows[row_index].cells[col_index].value


def login_user(client: TestClient, email: str, password: str) -> Any:
    """Helper function to login a user and set cookies."""
    login_response = client.post(
        AUTH_LOGIN,
        data={'username': email, 'password': password},
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    assert login_response.status_code == 200, f'Login failed: {login_response.text}'
    if 'fastapiusersauth' in login_response.cookies:
        client.cookies.set('fastapiusersauth', login_response.cookies['fastapiusersauth'])
    return login_response


def assert_response_status(response, expected_status: int, message: str | None = None):
    assert response.status_code == expected_status, (
        message or f'Expected {expected_status}, got {response.status_code}: {response.text}'
    )


def create_user(
    client: TestClient, email: str, password: str, name: str, role: str
) -> Dict[str, Any] | None:
    user_data = {
        'email': email,
        'password': password,
        'name': name,
        'role': role,
    }
    response = client.post(USER_CREATE, json=user_data)
    if response.status_code == 201:
        return response.json()
    elif response.status_code == 400:  # User already exists
        return None
    else:
        assert_response_status(response, 201, f'Failed to create {role} user')
        return None


def create_event(
    client: TestClient, name: str, description: str, price: int, is_active: bool = True
) -> Dict[str, Any]:
    event_data = {
        'name': name,
        'description': description,
        'price': price,
        'is_active': is_active,
    }
    response = client.post(EVENT_BASE, json=event_data)
    assert_response_status(response, 201, 'Failed to create event')
    return response.json()


def parse_seating_config(seating_config_str: str | None) -> dict:
    if not seating_config_str:
        return DEFAULT_SEATING_CONFIG
    try:
        return json.loads(seating_config_str)
    except (json.JSONDecodeError, TypeError):
        return DEFAULT_SEATING_CONFIG


def build_event_request_data(event_data: dict, include_venue_seating: bool = True) -> dict:
    request_data = {
        'name': event_data['name'],
        'description': event_data['description'],
        'price': int(event_data['price']),
        'is_active': event_data.get('is_active', 'true').lower() == 'true',
    }

    if include_venue_seating:
        request_data['venue_name'] = event_data.get('venue_name', DEFAULT_VENUE_NAME)
        request_data['seating_config'] = parse_seating_config(
            event_data.get('seating_config', DEFAULT_SEATING_CONFIG_JSON)
        )

    return request_data


def create_event_with_venue_seating(
    client: TestClient,
    event_data: dict,
    seller_login_required: bool = True,
    seller_email: str | None = None,
    seller_password: str = 'P@ssw0rd',
) -> tuple[Any, dict]:
    if seller_login_required and seller_email:
        login_user(client, seller_email, seller_password)

    request_data = build_event_request_data(event_data)
    response = client.post(EVENT_BASE, json=request_data)
    return response, request_data


def create_event_in_database(execute_sql_statement, event_data: dict, seller_id: int = 1) -> int:
    execute_sql_statement(
        """
        INSERT INTO event (name, description, price, seller_id, is_active, status, venue_name, seating_config)
        VALUES (:name, :description, :price, :seller_id, :is_active, :status, :venue_name, :seating_config)
        """,
        {
            'name': event_data['name'],
            'description': event_data['description'],
            'price': int(event_data['price']),
            'seller_id': seller_id,
            'is_active': event_data.get('is_active', 'true').lower() == 'true',
            'status': event_data.get('status', 'available'),
            'venue_name': event_data.get('venue_name', DEFAULT_VENUE_NAME),
            'seating_config': event_data.get('seating_config', DEFAULT_SEATING_CONFIG_JSON),
        },
    )

    # Get the created event ID
    result = execute_sql_statement(
        'SELECT id FROM event WHERE name = :name ORDER BY id DESC LIMIT 1',
        {'name': event_data['name']},
    )
    return result[0]['id'] if result else 1


def add_venue_seating_to_event_data(event_data: dict) -> dict:
    updated_data = event_data.copy()
    if 'venue_name' not in updated_data:
        updated_data['venue_name'] = DEFAULT_VENUE_NAME
    if 'seating_config' not in updated_data:
        updated_data['seating_config'] = DEFAULT_SEATING_CONFIG_JSON
    return updated_data

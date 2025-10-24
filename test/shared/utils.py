import json
from typing import Any, Dict

from fastapi.testclient import TestClient

from src.platform.constant.route_constant import EVENT_BASE, USER_CREATE, USER_LOGIN
from test.event_test_constants import (
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
        USER_LOGIN,
        json={'email': email, 'password': password},
    )
    assert login_response.status_code == 200, f'Login failed: {login_response.text}'
    if 'fastapiusersauth' in login_response.cookies:
        client.cookies.set('fastapiusersauth', login_response.cookies['fastapiusersauth'])
    return login_response


def assert_response_status(response, expected_status: int, message: str | None = None):
    response_text = getattr(response, 'text', getattr(response, 'content', 'N/A'))
    assert response.status_code == expected_status, (
        message or f'Expected {expected_status}, got {response.status_code}: {response_text}'
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
    """Build event request data from test table data.

    Args:
        event_data: Dictionary containing event fields from test table
        include_venue_seating: Whether to include venue and seating config

    Returns:
        Dictionary ready for POST request to event creation endpoint
    """
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

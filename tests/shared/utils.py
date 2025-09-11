from typing import Any, Dict

from fastapi.testclient import TestClient

from src.shared.constant.route_constant import AUTH_LOGIN


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
    """Helper function to assert response status code."""
    assert response.status_code == expected_status, (
        message or f'Expected {expected_status}, got {response.status_code}: {response.text}'
    )


def create_user(
    client: TestClient, email: str, password: str, name: str, role: str
) -> Dict[str, Any] | None:
    """Helper function to create a user. Returns None if user already exists."""
    from src.shared.constant.route_constant import USER_CREATE

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
    """Helper function to create a event."""
    from src.shared.constant.route_constant import EVENT_BASE

    event_data = {
        'name': name,
        'description': description,
        'price': price,
        'is_active': is_active,
    }
    response = client.post(EVENT_BASE, json=event_data)
    assert_response_status(response, 201, 'Failed to create event')
    return response.json()

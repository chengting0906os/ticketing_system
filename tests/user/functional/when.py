"""When steps for user BDD tests."""

from fastapi.testclient import TestClient
from pytest_bdd import when


@when('I send api')
def send_api_request(step, client: TestClient, user_state):
    data_table = step.data_table
    rows = data_table.rows

    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    row_data = dict(zip(headers, values, strict=True))

    user_state['request_data'] = {
        'email': row_data['email'],
        'password': row_data['password'],
        'name': row_data['name'],
        'role': row_data['role'],
    }

    user_state['response'] = client.post('/api/users', json=user_state['request_data'])


@when('I login with')
def login_with_credentials(step, client: TestClient, user_state):
    """Attempt to login with provided credentials."""
    data_table = step.data_table
    rows = data_table.rows
    
    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    login_data = dict(zip(headers, values, strict=True))
    
    user_state['login_data'] = login_data
    
    # FastAPI-users login endpoint expects username and password in form data
    form_data = {
        'username': login_data['email'],  # FastAPI-users uses 'username' field for email
        'password': login_data['password']
    }
    
    user_state['response'] = client.post(
        '/api/auth/login',
        data=form_data,  # Use form data, not JSON
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )

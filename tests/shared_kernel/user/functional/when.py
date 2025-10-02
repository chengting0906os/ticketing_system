from fastapi.testclient import TestClient
from pytest_bdd import when

from src.platform.constant.route_constant import USER_CREATE, USER_LOGIN
from tests.shared.utils import extract_table_data


@when('I send api')
def send_api_request(step, client: TestClient, user_state):
    row_data = extract_table_data(step)
    user_state['request_data'] = {
        'email': row_data['email'],
        'password': row_data['password'],
        'name': row_data['name'],
        'role': row_data['role'],
    }
    user_state['response'] = client.post(USER_CREATE, json=user_state['request_data'])


@when('I login with')
def login_with_credentials(step, client: TestClient, user_state):
    login_data = extract_table_data(step)
    user_state['login_data'] = login_data
    json_data = {'email': login_data['email'], 'password': login_data['password']}
    user_state['response'] = client.post(
        USER_LOGIN,
        json=json_data,
    )

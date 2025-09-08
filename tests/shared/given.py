from pytest_bdd import given

from tests.route_constant import AUTH_LOGIN
from tests.shared.utils import extract_table_data


@given('I am logged in as:')
def login_user_with_table(step, client):
    login_data = extract_table_data(step)
    response = client.post(
        AUTH_LOGIN,
        data={'username': login_data['email'], 'password': login_data['password']},
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    assert response.status_code == 200, f'Login failed: {response.text}'
    if 'fastapiusersauth' in response.cookies:
        client.cookies.set('fastapiusersauth', response.cookies['fastapiusersauth'])
    return response

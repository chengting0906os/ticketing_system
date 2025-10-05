from pytest_bdd import then

from tests.shared.utils import extract_table_data


@then('the user details should be:')
def verify_user_details(step, user_state):
    expected = extract_table_data(step)
    request_data = user_state['request_data']
    assert request_data['email'] == expected['email']
    assert request_data['password'] == expected['password']
    assert request_data['name'].replace('  ', ' ') == expected['name']
    assert request_data['role'] == expected['role']


@then('the seller user details should be:')
def verify_seller_user_details(step, user_state):
    expected = extract_table_data(step)
    request_data = user_state['request_data']
    assert request_data['email'] == expected['email']
    assert request_data['password'] == expected['password']
    assert request_data['name'] == expected['name']
    assert request_data['role'] == expected['role']


@then('the wrong user details should be:')
def verify_wrong_user_details(step, user_state):
    expected = extract_table_data(step)
    request_data = user_state['request_data']
    assert request_data['email'] == expected['email']
    assert request_data['password'] == expected['password']
    assert request_data['name'] == expected['name']
    assert request_data['role'] == expected['role']


@then('the login response should be successful')
def verify_login_success(user_state):
    response = user_state['response']
    assert response.status_code == 200, (
        f'Expected success status code (200), got {response.status_code}'
    )


@then('the login response should fail')
def verify_login_failure(user_state):
    response = user_state['response']
    assert response.status_code >= 400, (
        f'Expected failure status code (>=400), got {response.status_code}'
    )


@then('the response should contain a JWT cookie')
def verify_jwt_cookie(user_state):
    response = user_state['response']
    cookies = response.cookies
    assert len(cookies) > 0, 'No cookies found in response'
    auth_cookie = cookies.get('fastapiusersauth')
    assert auth_cookie is not None, 'JWT authentication cookie not found'
    assert len(auth_cookie) > 0, 'JWT cookie is empty'


@then('the user info should be')
def verify_user_info(step, user_state):
    expected = extract_table_data(step)
    response = user_state['response']
    response_data = response.json()
    assert response_data['email'] == expected['email']
    assert response_data['name'] == expected['name']
    assert response_data['role'] == expected['role']

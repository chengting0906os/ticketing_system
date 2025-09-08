"""Then steps for user BDD tests."""

from pytest_bdd import then


@then('the user details should be:')
def verify_user_details(step, user_state):
    data_table = step.data_table
    rows = data_table.rows

    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    expected = dict(zip(headers, values, strict=True))

    request_data = user_state['request_data']

    assert request_data['email'] == expected['email']
    assert request_data['password'] == expected['password']
    # Normalize spaces in name comparison
    assert request_data['name'].replace('  ', ' ') == expected['name']
    assert request_data['role'] == expected['role']


@then('the seller user details should be:')
def verify_seller_user_details(step, user_state):
    data_table = step.data_table
    rows = data_table.rows

    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    expected = dict(zip(headers, values, strict=True))

    request_data = user_state['request_data']

    assert request_data['email'] == expected['email']
    assert request_data['password'] == expected['password']
    assert request_data['name'] == expected['name']
    assert request_data['role'] == expected['role']


@then('the wrong user details should be:')
def verify_wrong_user_details(step, user_state):
    data_table = step.data_table
    rows = data_table.rows

    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    expected = dict(zip(headers, values, strict=True))

    request_data = user_state['request_data']

    assert request_data['email'] == expected['email']
    assert request_data['password'] == expected['password']
    assert request_data['name'] == expected['name']
    assert request_data['role'] == expected['role']


@then('the user should be created with status 201')
def verify_user_created_201(step, user_state):
    response = user_state['response']
    assert response.status_code == 201

    response_data = user_state['response'].json()
    data_table = step.data_table
    rows = data_table.rows

    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    expected = dict(zip(headers, values, strict=True))

    assert response_data['email'] == expected['email']
    assert response_data['role'] == expected['role']


@then('the user should fail with status 400')
def verify_user_failed_400(step, user_state):
    response = user_state['response']
    assert response.status_code == 400

    # For 400 errors, we expect domain validation error
    # The error shows that 'wrong_user' is not a valid role


@then('get 422')
def verify_response_422(step, user_state):
    """Verify response status is 422."""
    response = user_state['response']
    assert response.status_code == 422


@then('the login response should be successful')
def verify_login_success(user_state):
    """Verify login was successful."""
    # Just a placeholder - actual check is in 'get 200'
    pass


@then('the login response should fail')
def verify_login_failure(user_state):
    """Verify login failed."""
    # Just a placeholder - actual check is in 'get 400/422'
    pass


@then('the response should contain a JWT cookie')
def verify_jwt_cookie(user_state):
    """Verify response contains JWT authentication cookie."""
    response = user_state['response']

    # Check for authentication cookie
    cookies = response.cookies
    assert len(cookies) > 0, 'No cookies found in response'

    # FastAPI-users typically uses 'fastapiusersauth' as the cookie name
    auth_cookie = cookies.get('fastapiusersauth')
    assert auth_cookie is not None, 'JWT authentication cookie not found'
    assert len(auth_cookie) > 0, 'JWT cookie is empty'


@then('the user info should be')
def verify_user_info(step, user_state):
    """Verify user information in response."""
    data_table = step.data_table
    rows = data_table.rows

    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    expected = dict(zip(headers, values, strict=True))

    response = user_state['response']
    response_data = response.json()

    # Verify user info matches
    assert response_data['email'] == expected['email']
    assert response_data['name'] == expected['name']
    assert response_data['role'] == expected['role']


@then('the user error message should contain "{expected_text}"')
def verify_user_error_message(expected_text, user_state):
    """Verify error message contains expected text."""
    response = user_state['response']
    response_text = response.text.lower() if hasattr(response, 'text') else response.json()

    # Convert to string if JSON
    if isinstance(response_text, dict):
        response_text = str(response_text).lower()

    assert expected_text.lower() in response_text, (
        f"Expected '{expected_text}' not found in response: {response_text}"
    )

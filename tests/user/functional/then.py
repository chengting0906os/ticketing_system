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


@then('get 201')
def verify_response_201(step, user_state):
    response = user_state['response']
    if response.status_code != 201:
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
    assert response.status_code == 201

    response_data = user_state['response'].json()
    data_table = step.data_table
    rows = data_table.rows

    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    expected = dict(zip(headers, values, strict=True))

    assert response_data['email'] == expected['email']
    assert response_data['role'] == expected['role']


@then('get 400')
def verify_response_400(step, user_state):
    response = user_state['response']
    if response.status_code != 400:
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
    assert response.status_code == 400
    
    # For 400 errors, we expect domain validation error
    # The error shows that 'wrong_user' is not a valid role

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
    assert request_data['first_name'] == expected['first_name']
    assert request_data['last_name'] == expected['last_name']
    assert request_data['role'] == expected['role']


@then('get 201')
def verify_response_201(step, user_state):
    assert user_state['response'].status_code == 201

    response_data = user_state['response'].json()
    data_table = step.data_table
    rows = data_table.rows

    headers = [cell.value for cell in rows[0].cells]
    values = [cell.value for cell in rows[1].cells]
    expected = dict(zip(headers, values, strict=True))

    assert response_data['email'] == expected['email']
    assert response_data['role'] == expected['role']

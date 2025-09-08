from pytest_bdd import then


def get_state_with_response(user_state=None, product_state=None, order_state=None):
    for state in [order_state, product_state, user_state]:
        if state and state.get('response'):
            return state
    return order_state or product_state or user_state or {}


@then('get status code:')
def verify_status_code(step, user_state=None, product_state=None, order_state=None):
    data_table = step.data_table
    rows = data_table.rows
    expected_status = int(rows[0].cells[0].value)
    state = get_state_with_response(user_state, product_state, order_state)
    response = state['response']
    assert response.status_code == expected_status, (
        f'Expected {expected_status}, got {response.status_code}: {response.text}'
    )


@then('the error message should contain:')
def verify_error_message_with_table(step, user_state=None, product_state=None, order_state=None):
    data_table = step.data_table
    rows = data_table.rows
    expected_message = rows[0].cells[0].value
    state = get_state_with_response(user_state, product_state, order_state)
    response = state['response']
    response_data = response.json()
    if 'detail' in response_data:
        actual_message = response_data['detail']
        assert expected_message in actual_message, (
            f"Expected '{expected_message}' in '{actual_message}'"
        )
    else:
        raise AssertionError(f"No 'detail' field in response: {response_data}")

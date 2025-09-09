from pytest_bdd import then

from tests.shared.utils import assert_response_status, extract_single_value


def get_state_with_response(user_state=None, product_state=None, order_state=None):
    for state in [order_state, product_state, user_state]:
        if state and state.get('response'):
            return state
    return order_state or product_state or user_state or {}


@then('the response status code should be:')
def verify_status_code(step, user_state=None, product_state=None, order_state=None):
    expected_status = int(extract_single_value(step))
    state = get_state_with_response(user_state, product_state, order_state)
    response = state['response']
    assert_response_status(response, expected_status)


@then('the error message should contain:')
def verify_error_message_with_table(step, user_state=None, product_state=None, order_state=None):
    expected_text = extract_single_value(step)
    state = get_state_with_response(user_state, product_state, order_state)
    response = state['response']
    error_data = response.json()
    error_message = str(error_data.get('detail', ''))
    assert expected_text in error_message, (
        f'Expected "{expected_text}" in error message, got: {error_message}'
    )


@then('the order status should be:')
def verify_order_status_with_table(step, order_state=None):
    expected_status = extract_single_value(step)

    # If order_state has 'updated_order', use that, otherwise use 'order'
    if order_state and 'updated_order' in order_state:
        actual_status = order_state['updated_order']['status']
    elif order_state and 'order' in order_state:
        actual_status = order_state['order']['status']
    else:
        raise AssertionError('No order found in state to check status')

    assert actual_status == expected_status, (
        f'Expected order status "{expected_status}", got "{actual_status}"'
    )

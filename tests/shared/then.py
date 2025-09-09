from pytest_bdd import then
from tests.shared.utils import extract_single_value, assert_response_status


def get_state_with_response(user_state=None, product_state=None, order_state=None):
    for state in [order_state, product_state, user_state]:
        if state and state.get('response'):
            return state
    return order_state or product_state or user_state or {}


@then('get status code:')
def verify_status_code(step, user_state=None, product_state=None, order_state=None):
    expected_status = int(extract_single_value(step))
    state = get_state_with_response(user_state, product_state, order_state)
    response = state['response']
    assert_response_status(response, expected_status)


# Removed - using the newer version below that handles both formats


@then('the response should be:')
def verify_response_status(step, user_state=None, product_state=None, order_state=None):
    """Verify response status using datatable."""
    expected_status = int(extract_single_value(step))
    state = get_state_with_response(user_state, product_state, order_state)
    assert state['response'].status_code == expected_status, (
        f'Expected status {expected_status}, got {state["response"].status_code}'
    )


# Use the datatable version above instead: @then('the response should be:')


# Generic error message verification - supports both datatable and inline formats
@then('the error message should contain:')
def verify_error_message_with_table(step, user_state=None, product_state=None, order_state=None):
    """Verify error message using datatable."""
    expected_text = extract_single_value(step)
    state = get_state_with_response(user_state, product_state, order_state)
    response = state['response']
    error_data = response.json()
    error_message = str(error_data.get('detail', ''))
    assert expected_text in error_message, (
        f'Expected "{expected_text}" in error message, got: {error_message}'
    )


# Use the datatable version above instead: @then('the error message should contain:')


@then('the order status should be:')
def verify_order_status_with_table(step, order_state=None):
    """Verify order status using datatable."""
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


# Use the datatable version above instead: @then('the order status should be:')

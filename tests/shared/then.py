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


@then('the error message should contain:')
def verify_error_message_with_table(step, user_state=None, product_state=None, order_state=None):
    expected_message = extract_single_value(step)
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


@then('the response should be 400')
def response_should_be_400(user_state=None, product_state=None, order_state=None):
    """Verify response status is 400."""
    state = get_state_with_response(user_state, product_state, order_state)
    assert state['response'].status_code == 400, (
        f'Expected status 400, got {state["response"].status_code}'
    )


@then('the response should be 403')
def response_should_be_403(user_state=None, product_state=None, order_state=None):
    """Verify response status is 403."""
    state = get_state_with_response(user_state, product_state, order_state)
    assert state['response'].status_code == 403, (
        f'Expected status 403, got {state["response"].status_code}'
    )


@then('the response should be 404')
def response_should_be_404(user_state=None, product_state=None, order_state=None):
    """Verify response status is 404."""
    state = get_state_with_response(user_state, product_state, order_state)
    assert state['response'].status_code == 404, (
        f'Expected status 404, got {state["response"].status_code}'
    )

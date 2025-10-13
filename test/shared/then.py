from pytest_bdd import then
from test.shared.utils import assert_response_status, extract_single_value


def get_state_with_response(user_state=None, event_state=None, booking_state=None, context=None):
    # Check context first (used by ticket test)
    if context and context.get('response'):
        return context
    # Then check other states
    for state in [booking_state, event_state, user_state]:
        if state and state.get('response'):
            return state
    return context or booking_state or event_state or user_state or {}


@then('the response status code should be:')
def verify_status_code(step, user_state=None, event_state=None, booking_state=None, context=None):
    expected_status = int(extract_single_value(step))
    state = get_state_with_response(user_state, event_state, booking_state, context)
    response = state['response']
    assert_response_status(response, expected_status)


@then('the error message should contain:')
def verify_error_message_with_table(
    step, user_state=None, event_state=None, booking_state=None, context=None
):
    expected_text = extract_single_value(step)
    state = get_state_with_response(user_state, event_state, booking_state, context)
    response = state['response']
    error_data = response.json()
    error_message = str(error_data.get('detail', ''))
    # Case-insensitive partial match to be more flexible
    assert expected_text.lower() in error_message.lower(), (
        f'Expected "{expected_text}" in error message, got: {error_message}'
    )

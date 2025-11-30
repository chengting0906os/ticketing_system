from typing import Any

import httpx
from pytest_bdd import then
from pytest_bdd.model import Step

from test.shared.utils import assert_response_status, extract_single_value


def get_state_with_response(
    user_state: dict[str, Any] | None = None,
    event_state: dict[str, Any] | None = None,
    booking_state: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Helper to find the state dict containing the response.

    Note: This helper keeps optional defaults for backward compatibility
    with existing callers that only pass subset of states.
    """
    # Check context first (used by ticket test)
    if context and context.get('response'):
        return context
    # Then check other states
    for state in [booking_state, event_state, user_state]:
        if state and state.get('response'):
            return state
    return context or booking_state or event_state or user_state or {}


@then('the response status code should be:')
def verify_status_code(
    step: Step,
    user_state: dict[str, Any],
    event_state: dict[str, Any],
    booking_state: dict[str, Any],
    context: dict[str, Any],
) -> None:
    expected_status = int(extract_single_value(step))
    state = get_state_with_response(user_state, event_state, booking_state, context)
    response: httpx.Response = state['response']
    assert_response_status(response, expected_status)


@then('the error message should contain:')
def verify_error_message_with_table(
    step: Step,
    user_state: dict[str, Any],
    event_state: dict[str, Any],
    booking_state: dict[str, Any],
    context: dict[str, Any],
) -> None:
    expected_text = extract_single_value(step)
    state = get_state_with_response(user_state, event_state, booking_state, context)
    response: httpx.Response = state['response']
    error_data = response.json()
    error_message = str(error_data.get('detail', ''))
    # Case-insensitive partial match to be more flexible
    assert expected_text.lower() in error_message.lower(), (
        f'Expected "{expected_text}" in error message, got: {error_message}'
    )
